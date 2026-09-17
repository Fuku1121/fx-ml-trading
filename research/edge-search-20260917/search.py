"""Exploratory, cost-aware FX model search. Never connects to a trading account."""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from threadpoolctl import threadpool_limits
import feature_reference as reference

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'multicurrency-20260917'
PAIRS=('USDJPY','EURUSD','GBPUSD','AUDUSD')
BASE=reference.EXPECTED_LIVE_FEATURES
HORIZONS=(4,8,16)
POLICIES=('probability','cost_filtered','expected_return')


def closed_market(index):
    local=index.tz_convert('America/New_York')
    return (local.dayofweek==5)|((local.dayofweek==4)&(local.hour>=17))|((local.dayofweek==6)&(local.hour<17))


def history_ok(index):
    breaks=np.zeros(len(index),dtype=int);breaks[0]=1
    differences=index.to_series().diff()
    for i in np.flatnonzero((differences>pd.Timedelta(minutes=15)).to_numpy()):
        missing=pd.date_range(index[i-1]+pd.Timedelta(minutes=15),index[i]-pd.Timedelta(minutes=15),freq='15min')
        breaks[i]=not np.all(closed_market(missing))
    # The first 150 observations form the anchor; weekend closure adds no fake bars.
    return pd.Series(breaks,index=index).rolling(149,min_periods=149).sum().eq(0)&(np.arange(len(index))>=149)


def load_raw():
    data={}
    for pair in PAIRS:
        sides=[]
        for side in ('B','A'):
            f=pd.concat([pd.read_csv(SOURCE/'data'/f'{pair}_{year}_{side}.csv',index_col='timestamp',parse_dates=True) for year in range(2021,2027)])
            f.index=pd.to_datetime(f.index,utc=True)
            assert f.index.is_unique and f.index.is_monotonic_increasing
            sides.append(f)
        bid,ask=sides
        assert bid.index.equals(ask.index)
        valid=(bid.volume>0)&(ask.volume>0)&~closed_market(bid.index)
        data[pair]=(bid.loc[valid],ask.loc[valid])
    return data


def make_frames(raw):
    cross={}
    for pair,(bid,ask) in raw.items():
        cross[pair]=pd.DataFrame({f'{pair}_return_{h}':bid.close.pct_change(h) for h in (1,4,16)},index=bid.index)
    result={}
    for pair,(bid,ask) in raw.items():
        x=reference.make_live_features(bid)[BASE].copy()
        for other in PAIRS:
            if other!=pair:x=x.join(cross[other])
        assert not any(c.startswith(('target','long','short')) for c in x.columns)
        x['past_ok']=history_ok(bid.index)&x.notna().all(axis=1)
        x['entrymid']=(bid.open.shift(-1)+ask.open.shift(-1))/2
        pip=.01 if pair.endswith('JPY') else .0001
        # Known at decision time, conservative proxy for future round-trip costs.
        midclose=(bid.close+ask.close)/2
        x['estimated_cost']=2*(ask.close-bid.close)/midclose+.00005+.2*pip/midclose
        x['scale']=x.atr14.clip(lower=.00005)
        times=bid.index.to_series()
        for h in HORIZONS:
            exitmid=(bid.close.shift(-h)+ask.close.shift(-h))/2
            x[f'target{h}']=exitmid/x.entrymid-1
            x[f'long{h}']=(bid.close.shift(-h)-ask.open.shift(-1))/x.entrymid-.00005-.2*pip/x.entrymid
            x[f'short{h}']=(bid.open.shift(-1)-ask.close.shift(-h))/x.entrymid-.00005-.2*pip/x.entrymid
            spread=((ask.open.shift(-1)-bid.open.shift(-1))+(ask.close.shift(-h)-bid.close.shift(-h)))/(2*x.entrymid)
            x[f'extra_cost{h}']=spread+.3*pip/x.entrymid
            good=pd.Series(True,index=bid.index)
            for j in range(1,h+1):good &= times.shift(-j)-times==pd.Timedelta(minutes=j*15)
            # Avoid overnight rollover and swaps: entry and exit stay in one NY session.
            entry=(bid.index+pd.Timedelta(minutes=15)).tz_convert('America/New_York')+pd.Timedelta(hours=7)
            exit=(bid.index+pd.Timedelta(minutes=15*(h+1))).tz_convert('America/New_York')+pd.Timedelta(hours=7)
            x[f'eligible{h}']=x.past_ok&good&(entry.date==exit.date)
        x.attrs['market_index']=bid.index
        result[pair]=x
    return result


def trades_for(frame,h,p,expected,policy):
    if policy=='expected_return':
        side=np.where(expected>=0,1,-1)
        trigger=np.abs(expected)>frame.estimated_cost.to_numpy()*1.5
    else:
        side=np.where(p>=.5,1,-1)
        trigger=np.maximum(p,1-p)>=.58
        if policy=='cost_filtered':trigger &= side*expected>frame.estimated_cost.to_numpy()*1.5
    chosen=[];free=None
    for i,t in enumerate(frame.index):
        entry=t+pd.Timedelta(minutes=15)
        if trigger[i] and (free is None or entry>=free):
            chosen.append(i);free=entry+pd.Timedelta(minutes=h*15)
    indices=np.array(chosen,dtype=int);f=frame.iloc[indices]
    net=np.where(side[indices]>0,f[f'long{h}'],f[f'short{h}'])
    return pd.DataFrame({'signal_time':f.index,'entry':f.index+pd.Timedelta(minutes=15),
        'exit':f.index+pd.Timedelta(minutes=(h+1)*15),'side':side[indices],'net':net,
        'stress_net':net-f[f'extra_cost{h}'].to_numpy()})


def metrics(t,days):
    r=t.net.to_numpy();curve=np.r_[1,np.cumprod(1+r)]
    loss=-r[r<0].sum()
    return dict(trades=len(t),trades_per_day=len(t)/days,return_pct=(curve[-1]-1)*100,
        stress_return_pct=(np.prod(1+t.stress_net)-1)*100,
        profit_factor=float(r[r>0].sum()/loss) if loss else None,
        win_rate=float((r>0).mean()) if len(r) else None,
        closed_drawdown_pct=float((curve/np.maximum.accumulate(curve)-1).min()*100),
        mean_net_bps=float(r.mean()*1e4) if len(r) else None)


def train_one(pair,frame,h,features,year):
    name=f'{pair}_{h*15}m_{features}_{year}'
    folder=ROOT/'runs'/name;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'metrics.json').exists():return json.loads((folder/'metrics.json').read_text())
    cal_start=pd.Timestamp(f'{year-1}-01-01',tz='UTC')
    cal_end=pd.Timestamp(f'{year-1}-07-01',tz='UTC')
    test_start=pd.Timestamp(f'{year}-01-01',tz='UTC')
    test_end=pd.Timestamp('2026-09-01' if year==2026 else f'{year+1}-01-01',tz='UTC')
    label_end=frame.index+pd.Timedelta(minutes=(h+1)*15)
    eligible=frame[f'eligible{h}']
    train=frame.loc[eligible&(frame.index>=cal_start-pd.DateOffset(years=3))&(label_end<cal_start)]
    cal=frame.loc[eligible&(frame.index>=cal_start)&(label_end<cal_end)]
    test=frame.loc[eligible&(frame.index>=test_start)&(label_end<test_end)]
    validation=frame.loc[eligible&(frame.index>=cal_end)&(label_end<test_start)]
    columns=BASE+([c for c in frame if '_return_' in c] if features=='cross' else [])
    assert len(train)>15000 and len(cal)>3000 and len(test)>5000
    assert train.index[-1]+pd.Timedelta(minutes=(h+1)*15)<cal.index[0]
    print('TRAIN',name,len(columns),len(train),len(cal),flush=True)
    params=dict(learning_rate=.03,max_iter=250,max_leaf_nodes=15,min_samples_leaf=100,
        l2_regularization=10,early_stopping=False,random_state=42)
    classifier=HistGradientBoostingClassifier(**params).fit(train[columns],(train[f'target{h}']>0).astype(int))
    calibrator=IsotonicRegression(out_of_bounds='clip').fit(classifier.predict_proba(cal[columns])[:,1],(cal[f'target{h}']>0).astype(int))
    regressor=HistGradientBoostingRegressor(**params).fit(train[columns],(train[f'target{h}']/train.scale).clip(-10,10))
    # Normalize targets by current ATR; inverse scaling uses only current features.
    joblib.dump(dict(classifier=classifier,calibrator=calibrator,regressor=regressor,features=columns,horizon=h),folder/'models.joblib',compress=3)
    records=[]
    for period,sub,start,end in [('test',test,test_start,test_end),('validation',validation,cal_end,test_start)]:
        p=calibrator.predict(classifier.predict_proba(sub[columns])[:,1])
        expected=regressor.predict(sub[columns])*sub.scale.to_numpy()
        pd.DataFrame({'time':sub.index,'p_up':p,'expected_return':expected,'actual_return':sub[f'target{h}'].to_numpy()}).to_csv(folder/f'{period}_predictions.csv',index=False)
        market=frame.attrs['market_index'];market=market[(market>=start)&(market<end)]
        days=len(pd.Index((market.tz_convert('America/New_York')+pd.Timedelta(hours=7)).date).unique())
        for policy in POLICIES:
            t=trades_for(sub,h,p,expected,policy)
            t.to_csv(folder/f'{period}_{policy}_trades.csv',index=False)
            record=dict(name=name,pair=pair,horizon_minutes=h*15,features=features,year=year,period=period,policy=policy,
                market_days=days,predictions=len(sub),direction_accuracy=float(((p>=.5)==(sub[f'target{h}']>0)).mean()),**metrics(t,days))
            records.append(record)
    (folder/'metrics.json').write_text(json.dumps(records,indent=2))
    print('DONE',name,[(r['policy'],round(r['return_pct'],2),r['trades']) for r in records if r['period']=='test'],flush=True)
    return records


def main():
    protocol={'pairs':PAIRS,'horizons_minutes':[60,120,240],'feature_sets':['base41','base41_plus_other_pair_lag_returns'],
        'policies':POLICIES,'classifier_threshold':.58,'return_threshold':'1.5x cost estimate known at decision',
        'models':'HGB classifier plus ATR-scaled HGB regressor; smaller leaves constrained by min 100 samples and L2=10',
        'split':'2025: train2021-23/cal2024H1/validate2024H2; 2026: train2022-24/cal2025H1/validate2025H2',
        'cost':'actual bid/ask + 0.2 pip + 0.00005 roundtrip; stress double spread +0.5pip+same commission',
        'quality':'150 observed bars; expected weekend closure allowed without filling; intramarket gaps restart anchor; future gaps excluded from scoring',
        'positions':'next bar entry, one position per pair, no NY17 rollover crossing, fixed1x',
        'selection':'Exploratory 72 policies per year. Candidate must have >=30 trades and positive base/stress in BOTH 2025 and 2026; rank by minimum stress return, at most one per pair. Freeze before acquiring Sept holdout.',
        'holdout':'Do not download or inspect 2026-09-01 through 2026-09-16 quotes until candidates and model files are frozen. Evaluate selected candidates once; too short to prove future profitability.',
        'warning':'2025/2026 Jan-Aug have already been explored. Positive research results are not confirmation. Expected-return policy is a different signal definition, not a 58% probability claim.'}
    p=ROOT/'protocol.json'
    if not p.exists():p.write_text(json.dumps(protocol,indent=2))
    print('PREPARING FRAMES',flush=True)
    frames=make_frames(load_raw())
    records=[]
    for pair in PAIRS:
        for h in HORIZONS:
            for features in ('base','cross'):
                for year in (2025,2026):
                    records.extend(train_one(pair,frames[pair],h,features,year))
                    pd.DataFrame(records).to_csv(ROOT/'results.csv',index=False)
    print('ALL COMPLETE',len(records),flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=2):main()

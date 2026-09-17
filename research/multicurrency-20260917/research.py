"""Predefined chronological multi-currency experiment; never sends orders."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from threadpoolctl import threadpool_limits

HERE=Path(__file__).resolve().parent
import feature_reference as inference
PAIRS=('USDJPY','EURUSD','GBPUSD','AUDUSD')
FEATURES=inference.EXPECTED_LIVE_FEATURES


def price_targets(bid,ask):
    result=pd.DataFrame(index=bid.index)
    entrymid=(bid.open.shift(-1)+ask.open.shift(-1))/2
    result['entrymid']=entrymid
    for h in (2,4):
        exitmid=(bid.close.shift(-h)+ask.close.shift(-h))/2
        result[f'r{h}']=exitmid/entrymid-1
        result[f'long{h}']=(bid.close.shift(-h)-ask.open.shift(-1))/entrymid
        result[f'short{h}']=(bid.open.shift(-1)-ask.close.shift(-h))/entrymid
        result[f'spread{h}']=((ask.open.shift(-1)-bid.open.shift(-1))+(ask.close.shift(-h)-bid.close.shift(-h)))/(2*entrymid)
    return result


def load_pair(pair):
    sides={}
    for side in ('B','A'):
        chunks=[]
        for year in range(2021,2027):
            p=HERE/'data'/f'{pair}_{year}_{side}.csv'
            f=pd.read_csv(p,index_col='timestamp',parse_dates=True)
            f.index=pd.to_datetime(f.index,utc=True)
            start=pd.Timestamp(f'{year}-01-01',tz='UTC')
            end=pd.Timestamp('2026-09-01' if year==2026 else f'{year+1}-01-01',tz='UTC')
            assert f.index.min()-start<pd.Timedelta(days=7)
            assert end-f.index.max()<pd.Timedelta(days=7)
            assert (f.groupby(f.index.month).size()>1200).all()
            assert f.index.month.nunique()==(8 if year==2026 else 12)
            chunks.append(f)
        sides[side]=pd.concat(chunks).sort_index()
        assert sides[side].index.is_unique
    bid,ask=sides['B'],sides['A']
    assert bid.index.equals(ask.index), 'Bid/ask timestamps differ; investigate before training'
    cols=['open','high','low','close']
    assert (ask[cols]>=bid[cols]).all().all(), 'Negative quoted spread'
    # A provider's weekend placeholders are not executable observations.
    ny=bid.index.tz_convert('America/New_York')
    closed=(ny.dayofweek==5)|((ny.dayofweek==4)&(ny.hour>=17))|((ny.dayofweek==6)&(ny.hour<17))
    valid=(bid.volume>0)&(ask.volume>0)&~closed
    audit={'raw_rows':len(bid),'removed_zero_volume_or_weekend':int((~valid).sum())}
    bid,ask=bid.loc[valid],ask.loc[valid]
    x=inference.make_live_features(bid)[FEATURES].copy()
    stamps=pd.Series(bid.index,index=bid.index)
    eligible=x.notna().all(axis=1)
    # Require 150 actual consecutive past bars and four consecutive future bars.
    # Gaps, including market closures, restart feature eligibility; no filled bars.
    eligible &= (stamps-stamps.shift(149))==pd.Timedelta(minutes=149*15)
    for k in range(1,5):
        eligible &= stamps.shift(-k)-stamps==pd.Timedelta(minutes=15*k)
    x=x.join(price_targets(bid,ask))
    x=x.loc[eligible].copy()
    x.attrs['market_index']=bid.index
    audit.update(eligible_rows=len(x),first=str(x.index.min()),last=str(x.index.max()))
    (HERE/f'data_audit_{pair}.json').write_text(json.dumps(audit,indent=2))
    return x


def select_trades(frame,p,h):
    direction=np.where(p>=.5,1,-1)
    selected=[];free=None
    for i,t in enumerate(frame.index):
        entry=t+pd.Timedelta(minutes=15)
        if max(p[i],1-p[i])>=.58 and (free is None or entry>=free):
            selected.append(i);free=entry+pd.Timedelta(minutes=15*h)
    ix=np.asarray(selected,dtype=int)
    f=frame.iloc[ix]
    net=np.where(direction[ix]>0,f[f'long{h}'],f[f'short{h}'])
    # Additional adverse round-trip execution allowance: 0.2 pip, 0.5 pip stress.
    return pd.DataFrame({'signal_time':f.index,'entry':f.index+pd.Timedelta(minutes=15),
        'exit':f.index+pd.Timedelta(minutes=15*(h+1)),'side':direction[ix],
        'quoted_net':net,'spread':f[f'spread{h}'].to_numpy()})


def stats(trades,days):
    r=trades.net.to_numpy();curve=np.r_[1,np.cumprod(1+r)]
    loss=-r[r<0].sum()
    return {'trades':len(r),'trades_per_day':len(r)/days,'win_rate':float((r>0).mean()) if len(r) else None,
        'mean_net_bps':float(r.mean()*1e4) if len(r) else None,
        'profit_factor':float(r[r>0].sum()/loss) if loss else None,
        'return_pct':float((curve[-1]-1)*100),
        'closed_drawdown_pct':float((curve/np.maximum.accumulate(curve)-1).min()*100),
        'stress_return_pct':float((np.prod(1+trades.stress_net)-1)*100)}


def run(pair,data,year,h,kind):
    name=f'{pair}_{year}_{h*15}m_{kind}'
    folder=HERE/'runs'/name;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'metrics.json').exists():return json.loads((folder/'metrics.json').read_text())
    cal_start=pd.Timestamp(f'{year-1}-01-01',tz='UTC')
    test_start=pd.Timestamp(f'{year}-01-01',tz='UTC')
    test_end=pd.Timestamp('2026-09-01' if year==2026 else f'{year+1}-01-01',tz='UTC')
    label_end=data.index+pd.Timedelta(minutes=15*(h+1))
    train=data.loc[(data.index>=cal_start-pd.DateOffset(years=3))&(label_end<cal_start)]
    cal=data.loc[(data.index>=cal_start)&(label_end<test_start)]
    test=data.loc[(data.index>=test_start)&(label_end<test_end)]
    assert len(train)>15000 and len(cal)>5000 and len(test)>5000
    assert train.index[-1]+pd.Timedelta(minutes=15*(h+1))<cal.index[0]
    assert cal.index[-1]+pd.Timedelta(minutes=15*(h+1))<test.index[0]
    target=lambda f:(f[f'r{h}']>0).astype(int)
    print('TRAIN',name,len(train),len(cal),len(test),flush=True)
    model=(HistGradientBoostingClassifier(learning_rate=.05,max_iter=250,max_leaf_nodes=15,
        min_samples_leaf=30,l2_regularization=1,early_stopping=False,random_state=42)
        if kind=='HGB' else make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1500)))
    model.fit(train[FEATURES],target(train))
    calibration=IsotonicRegression(out_of_bounds='clip').fit(model.predict_proba(cal[FEATURES])[:,1],target(cal))
    raw=model.predict_proba(test[FEATURES])[:,1];p=calibration.predict(raw)
    trades=select_trades(test,p,h)
    # Convert pip allowances to return using contemporaneous mid entry price.
    entry=test.entrymid.reindex(pd.DatetimeIndex(trades.signal_time)).to_numpy()
    pip=.01 if pair.endswith('JPY') else .0001
    # Conservative commission reference: 25 JPY / million JPY each side.
    trades['net']=trades.quoted_net-.2*pip/entry-.00005
    trades['stress_net']=trades.quoted_net-trades.spread-.5*pip/entry-.00005
    market_index=data.attrs['market_index']
    market_index=market_index[(market_index>=test_start)&(market_index<test_end)]
    sessions=pd.Index((market_index.tz_convert('America/New_York')+pd.Timedelta(hours=7)).date).unique()
    days=len(sessions)
    pd.Series(sessions.astype(str)).to_csv(folder/'market_sessions.csv',index=False,header=['session'])
    result=dict(name=name,pair=pair,year=year,horizon_minutes=h*15,model=kind,rows=len(test),
        market_days=days,train_rows=len(train),cal_rows=len(cal),
        accuracy=float(((p>=.5)==target(test).to_numpy()).mean()),
        raw_accuracy=float(((raw>=.5)==target(test).to_numpy()).mean()),
        brier=float(np.mean((p-target(test).to_numpy())**2)),
        majority_accuracy=float(max(target(test).mean(),1-target(test).mean())),
        confidence_58=int((np.maximum(p,1-p)>=.58).sum()),**stats(trades,days))
    trades.to_csv(folder/'trades.csv',index=False)
    pd.DataFrame({'time':test.index,'p_up':p,'target':target(test).to_numpy()}).to_csv(folder/'predictions.csv',index=False)
    joblib.dump({'model':model,'calibrator':calibration,'features':FEATURES},folder/'research_model.joblib',compress=3)
    (folder/'metrics.json').write_text(json.dumps(result,indent=2))
    print('DONE',name,round(result['trades_per_day'],2),round(result['return_pct'],2),flush=True)
    return result


def main():
    protocol={'pairs':PAIRS,'test_years':[2025,2026],'2026_end_exclusive':'2026-09-01',
        'training':'3 years before calibration year; purged chronological split',
        'calibration':'preceding full year, isotonic','models':['HGB','standardized logistic'],
        'horizons_minutes':[30,60],'threshold':.58,'features':FEATURES,
        'execution':'next bar open at ask/bid; exit bid/ask at horizon close; nonoverlap per pair',
        'cost':'observed spread + 0.2 pip + 0.00005 commission per roundtrip; stress spread doubled + 0.5 pip + same commission',
        'quality':'150 consecutive positive-volume bars and 4 future bars; no fill',
        'position_size':'1x per independent pair; portfolio fixed 1/4 capital each',
        'limits':'No actual orders; observed quote OHLC not guaranteed fills; no swaps or intratrade drawdown; exploration across 32 conditions'}
    (HERE/'protocol.json').write_text(json.dumps(protocol,indent=2))
    results=[]
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--pair',choices=PAIRS)
    args=parser.parse_args()
    for pair in ([args.pair] if args.pair else PAIRS):
        data=load_pair(pair)
        for year in (2025,2026):
            for h in (2,4):
                for kind in ('HGB','logistic'):
                    results.append(run(pair,data,year,h,kind))
                    pd.DataFrame(results).to_csv(HERE/'results.csv',index=False)
    print('COMPLETE',len(results),flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=2):main()

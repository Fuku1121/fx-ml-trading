"""One additional-period probe of a weak research candidate, never a promotion."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import time
import requests
import numpy as np
import pandas as pd
import joblib
import dukascopy_python as duka
from threadpoolctl import threadpool_limits
from search import load_raw,make_frames,PAIRS,closed_market,trades_for,metrics

ROOT=Path(__file__).resolve().parent


def freeze_watchlist():
    """Separate low-sample research probe; original >=30-trade criteria stay failed."""
    path=ROOT/'watchlist_frozen.json'
    if path.exists():return json.loads(path.read_text())
    original=json.loads((ROOT/'frozen_candidates.json').read_text())
    f=pd.read_csv(ROOT/'results.csv');f=f[f.period=='test']
    watch=[]
    for (pair,h,features,policy),g in f.groupby(['pair','horizon_minutes','features','policy']):
        if len(g)==2 and (g.trades>0).all() and (g.stress_return_pct>0).all():
            model=ROOT/'runs'/f'{pair}_{h}m_{features}_2026'/'models.joblib'
            watch.append(dict(pair=pair,horizon_minutes=int(h),features=features,policy=policy,model=str(model),
                sha256=hashlib.sha256(model.read_bytes()).hexdigest(),historical=g.to_dict('records'),
                promotion_eligible=bool((g.trades>=30).all())))
    result=dict(frozen_at=datetime.now(timezone.utc).isoformat(),candidates=watch,
        original_selection_count=len(original['selected']),
        purpose='Additional-period diagnostic for positive-but-low-sample research ideas. Not relaxing adoption criteria; original selected list remains empty.',
        caution='USDJPY market outcomes in parts of September were previously observed in another forward audit; this is not a pristine research-wide holdout.',
        start='2026-09-01T00:00:00Z',end_exclusive='2026-09-16T00:00:00Z')
    path.write_text(json.dumps(result,indent=2))
    return result


def main():
    frozen=freeze_watchlist()
    print('FROZEN RESEARCH WATCHLIST',len(frozen['candidates']),flush=True)
    if not frozen['candidates']:return
    start=pd.Timestamp(frozen['start']);end=pd.Timestamp(frozen['end_exclusive'])
    folder=ROOT/'additional_period_data';folder.mkdir(exist_ok=True)
    original=requests.get
    def safe_get(*args,**kwargs):
        time.sleep(1);kwargs.setdefault('timeout',45)
        response=original(*args,**kwargs)
        if response.status_code==429:
            time.sleep(max(60,int(response.headers.get('Retry-After','60'))))
            response=original(*args,**kwargs)
        response.raise_for_status();return response
    duka.requests.get=safe_get
    raw=load_raw();manifest=[]
    for pair in PAIRS:
        more=[]
        for side in ('B','A'):
            path=folder/f'{pair}_{side}.csv'
            if not path.exists():
                print('ADDITIONAL DATA',pair,side,flush=True)
                f=duka.fetch(pair[:3]+'/'+pair[3:],duka.INTERVAL_MIN_15,side,start.to_pydatetime(),end.to_pydatetime(),max_retries=0,limit=2000)
                f=f[(f.index>=start)&(f.index<end)]
                assert len(f)>500 and f.index.is_unique
                f.to_csv(path)
            else:f=pd.read_csv(path,index_col='timestamp',parse_dates=True)
            f.index=pd.to_datetime(f.index,utc=True)
            more.append(f)
            manifest.append({'file':path.name,'rows':len(f),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        bid,ask=more;assert bid.index.equals(ask.index)
        valid=(bid.volume>0)&(ask.volume>0)&~closed_market(bid.index)
        raw[pair]=(pd.concat([raw[pair][0],bid.loc[valid]]),pd.concat([raw[pair][1],ask.loc[valid]]))
        assert raw[pair][0].index.is_unique
    (ROOT/'additional_period_manifest.json').write_text(json.dumps(manifest,indent=2))
    frames=make_frames(raw);results=[]
    for candidate in frozen['candidates']:
        model=Path(candidate['model']);assert hashlib.sha256(model.read_bytes()).hexdigest()==candidate['sha256']
        bundle=joblib.load(model);pair=candidate['pair'];h=bundle['horizon'];frame=frames[pair]
        f=frame.loc[frame[f'eligible{h}']&(frame.index>=start)&(frame.index+pd.Timedelta(minutes=(h+1)*15)<end)]
        p=bundle['calibrator'].predict(bundle['classifier'].predict_proba(f[bundle['features']])[:,1])
        expected=bundle['regressor'].predict(f[bundle['features']])*f.scale.to_numpy()
        t=trades_for(f,h,p,expected,candidate['policy'])
        market=frame.attrs['market_index'];market=market[(market>=start)&(market<end)]
        days=len(pd.Index((market.tz_convert('America/New_York')+pd.Timedelta(hours=7)).date).unique())
        name=f"{pair}_{h*15}m_{candidate['features']}_{candidate['policy']}"
        t.to_csv(ROOT/f'additional_{name}_trades.csv',index=False)
        pd.DataFrame({'time':f.index,'p_up':p,'expected_return':expected,'actual_return':f[f'target{h}'].to_numpy()}).to_csv(ROOT/f'additional_{name}_predictions.csv',index=False)
        result=dict(name=name,pair=pair,predictions=len(f),market_days=days,promotion_eligible=candidate['promotion_eligible'],**metrics(t,days))
        results.append(result);print('ADDITIONAL RESULT',result,flush=True)
    (ROOT/'additional_period_results.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    with threadpool_limits(limits=2):main()

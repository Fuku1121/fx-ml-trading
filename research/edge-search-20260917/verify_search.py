from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import joblib
from threadpoolctl import threadpool_limits
from search import make_frames,load_raw,metrics

ROOT=Path(__file__).resolve().parent


def main():
    frames=make_frames(load_raw());checks=[];total=0
    for folder in sorted((ROOT/'runs').iterdir()):
        records=json.loads((folder/'metrics.json').read_text())
        bundle=joblib.load(folder/'models.joblib');frame=frames[records[0]['pair']]
        for period in ('test','validation'):
            saved=pd.read_csv(folder/f'{period}_predictions.csv',parse_dates=['time'])
            f=frame.loc[pd.DatetimeIndex(saved.time)]
            p=bundle['calibrator'].predict(bundle['classifier'].predict_proba(f[bundle['features']])[:,1])
            expected=bundle['regressor'].predict(f[bundle['features']])*f.scale.to_numpy()
            err=float(np.max(np.abs(p-saved.p_up.to_numpy())))
            err_r=float(np.max(np.abs(expected-saved.expected_return.to_numpy())))
            assert err<1e-12 and err_r<1e-12
            checks.append({'run':folder.name,'period':period,'p_max_error':err,'expected_return_max_error':err_r})
        for record in records:
            t=pd.read_csv(folder/f"{record['period']}_{record['policy']}_trades.csv",parse_dates=['entry','exit'])
            assert (t.entry.iloc[1:].to_numpy()>=t.exit.iloc[:-1].to_numpy()).all()
            assert (t.stress_net<=t.net+1e-12).all()
            result=metrics(t,record['market_days'])
            assert result['trades']==record['trades']
            assert abs(result['return_pct']-record['return_pct'])<1e-8
            assert abs(result['stress_return_pct']-record['stress_return_pct'])<1e-8
            total+=1
    assert len(checks)==96 and total==288
    (ROOT/'verification.json').write_text(json.dumps({'prediction_replays':checks,'trade_summaries_checked':total,
        'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}},indent=2))
    print('PASS: 96 prediction replays and 288 trade summaries')


if __name__=='__main__':
    with threadpool_limits(limits=2):main()

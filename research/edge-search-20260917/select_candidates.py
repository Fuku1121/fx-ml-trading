"""Freeze a pre-specified historical selection before any fresh-period download."""
from pathlib import Path
import hashlib
import json
from datetime import datetime,timezone
import pandas as pd

ROOT=Path(__file__).resolve().parent


def main():
    records=[]
    for file in sorted((ROOT/'runs').glob('*/metrics.json')):records.extend(json.loads(file.read_text()))
    df=pd.DataFrame(records)
    assert len(df)==288 and len(df.loc[df.period=='test'])==144
    df.to_csv(ROOT/'results.csv',index=False)
    test=df.loc[df.period=='test']
    candidates=[]
    for (pair,h,features,policy),group in test.groupby(['pair','horizon_minutes','features','policy']):
        assert set(group.year)=={2025,2026}
        if (group.trades>=30).all() and (group.return_pct>0).all() and (group.stress_return_pct>0).all():
            folder=ROOT/'runs'/f'{pair}_{h}m_{features}_2026'
            candidates.append(dict(pair=pair,horizon_minutes=int(h),features=features,policy=policy,
                minimum_stress_return_pct=float(group.stress_return_pct.min()),
                model=str(folder/'models.joblib'),sha256=hashlib.sha256((folder/'models.joblib').read_bytes()).hexdigest(),
                historical=group.to_dict('records')))
    chosen=[]
    for pair in ('USDJPY','EURUSD','GBPUSD','AUDUSD'):
        possibilities=[c for c in candidates if c['pair']==pair]
        if possibilities:chosen.append(max(possibilities,key=lambda c:c['minimum_stress_return_pct']))
    result=dict(frozen_at=datetime.now(timezone.utc).isoformat(),all_eligible=candidates,selected=chosen,
        selection='Both years positive normal/stress, >=30 trades each; highest minimum stress return per pair',
        holdout_start='2026-09-01T00:00:00Z',holdout_end_exclusive='2026-09-16T00:00:00Z',
        protocol_sha256=hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest(),
        results_sha256=hashlib.sha256((ROOT/'results.csv').read_bytes()).hexdigest())
    path=ROOT/'frozen_candidates.json'
    if path.exists():raise RuntimeError('Selection already frozen; do not overwrite after holdout inspection')
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('HISTORICAL POSITIVE CONDITIONS',int((test.return_pct>0).sum()),'/',len(test))
    print('ELIGIBLE',len(candidates),'SELECTED',len(chosen))
    for c in chosen:print(c['pair'],c['horizon_minutes'],c['features'],c['policy'],c['minimum_stress_return_pct'])


if __name__=='__main__':main()

"""Replay saved models, verify immutable inputs and all experiment outputs."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from research import load_pair,PAIRS,FEATURES

ROOT=Path(__file__).resolve().parent


def main():
    manifest=json.loads((ROOT/'data_manifest.json').read_text())
    assert len(manifest)==48
    for item in manifest:
        path=ROOT/'data'/item['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        assert len(pd.read_csv(path))==item['rows']
    replay=[]
    for pair in PAIRS:
        data=load_pair(pair)
        for folder in sorted((ROOT/'runs').glob(pair+'_*')):
            bundle=joblib.load(folder/'research_model.joblib')
            saved=pd.read_csv(folder/'predictions.csv',parse_dates=['time'])
            frame=data.loc[pd.DatetimeIndex(saved.time)]
            p=bundle['calibrator'].predict(bundle['model'].predict_proba(frame[FEATURES])[:,1])
            error=float(np.max(np.abs(p-saved.p_up.to_numpy())))
            assert error<1e-12
            h=json.loads((folder/'metrics.json').read_text())['horizon_minutes']//15
            assert np.array_equal((frame[f'r{h}']>0).astype(int),saved.target)
            replay.append({'run':folder.name,'prediction_max_abs_error':error,'rows':len(saved)})
    assert len(replay)==32
    result={'input_files_checked':48,'prediction_runs_checked':32,'replay':replay,
        'python':sys.version,'packages':{name:importlib.metadata.version(name) for name in ['pandas','numpy','scikit-learn','joblib','dukascopy-python']},
        'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}}
    (ROOT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS 48 source files, 32 saved-model prediction replays',flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=2):main()

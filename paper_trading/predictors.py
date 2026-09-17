"""Frozen predictors. Only completed, aligned observation bars are accepted."""
from pathlib import Path
import json
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import InconsistentVersionWarning
import frozen_inference as reference

ROOT=Path(__file__).resolve().parent


class Predictors:
    def __init__(self,config):
        self.config=config
        manifest=json.loads((ROOT/'model/champion_manifest.json').read_text())
        with warnings.catch_warnings():
            warnings.simplefilter('error',InconsistentVersionWarning)
            reference.LIVE_MODEL=joblib.load(ROOT/'model/hgb_model.joblib')
            reference.LIVE_CALIBRATOR=joblib.load(ROOT/'model/calibrator.joblib')
            self.candidate=joblib.load(ROOT/'model/candidate.joblib')
        reference.LIVE_MANIFEST=manifest;reference.LIVE_FEATURES=manifest['features']
        assert manifest['features']==reference.EXPECTED_LIVE_FEATURES
        for attr,key in [('LIVE_CALIBRATION_METHOD','calibration'),('LIVE_THRESHOLD','threshold'),('LIVE_SESSION','session'),
            ('LIVE_SIZING_POLICY','sizing_policy'),('LIVE_SIZING_SCALE','sizing_scale'),('LIVE_BASE_COST','cost_per_trade_return')]:setattr(reference,attr,manifest[key])
        expected=reference.EXPECTED_LIVE_FEATURES+[f'{p}_return_{h}' for p in ('EURUSD','GBPUSD','AUDUSD') for h in (1,4,16)]
        assert self.candidate['features']==expected and self.candidate['horizon']==8

    def candidate_features(self,frames):
        x=reference.make_live_features(frames['OANDA:USD_JPY'])[reference.EXPECTED_LIVE_FEATURES].copy()
        for symbol in ('OANDA:EUR_USD','OANDA:GBP_USD','OANDA:AUD_USD'):
            other=frames[symbol]
            pair=symbol.split(':')[1].replace('_','')
            for h in (1,4,16):x[f'{pair}_return_{h}']=other.close.pct_change(h).reindex(x.index)
        return x

    def __call__(self,frames,at):
        base=reference.run_live_inference(frames['OANDA:USD_JPY'],as_of_utc=pd.Timestamp(at,unit='s',tz='UTC'))
        x=self.candidate_features(frames).iloc[[-1]][self.candidate['features']]
        if not np.isfinite(x.to_numpy()).all():raise RuntimeError('Nonfinite candidate features')
        raw=float(self.candidate['classifier'].predict_proba(x)[0,1])
        p=float(self.candidate['calibrator'].predict([raw])[0]);confidence=max(p,1-p);side=1 if p>=.5 else -1
        expected=float(self.candidate['regressor'].predict(x)[0])*max(float(x.atr14.iloc[0]),.00005)
        price=float(frames['OANDA:USD_JPY'].close.iloc[-1]);c=self.config
        estimate=2*c['assumed_spread_pips']*.01/price+c['commission_return_roundtrip']+c['slippage_pips_roundtrip']*.01/price
        prob_ok=confidence>=c['threshold'];edge_ok=side*expected>c['candidate_cost_multiplier']*estimate
        return {'base':{'p_up':float(base['calibrated_p_up']),'raw_p_up':float(base['raw_p_up']),
                    'confidence':float(base['confidence']),'side':1 if base['proposed_side']=='BUY' else -1,
                    'allowed':bool(base['threshold_allowed'] and base['session_allowed']),
                    'legacy_size':float(base['position_size']),'reason':'LOW_CONFIDENCE'},
            'candidate':{'p_up':p,'raw_p_up':raw,'confidence':confidence,'side':side,'allowed':bool(prob_ok and edge_ok),
                'expected_return':expected,'estimated_cost':estimate,'cost_basis':'fixed_spread_assumption',
                'reason':'LOW_CONFIDENCE' if not prob_ok else 'INSUFFICIENT_EXPECTED_MOVE'}}

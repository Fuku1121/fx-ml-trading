from pathlib import Path
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from engine import Engine
from runner import symbol_module
from quality import View
from history import frames_for
from predictors import Predictors
from backup import backup
from report import evaluate

ROOT=Path(__file__).resolve().parent
C=json.loads((ROOT/'protocol.json').read_text())
B=int(pd.Timestamp('2026-09-21 00:00:00Z').timestamp())


class Operations(unittest.TestCase):
    def test_shared_payload_is_partitioned_by_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions=[]
            try:
                payload={'type':'trade','data':[{'s':s,'t':B*1000,'p':150 if i==0 else 1.1+i*.01} for i,s in enumerate(C['symbols'])]}
                for symbol in C['symbols']:
                    session=symbol_module(symbol).Session(Path(directory)/symbol.split(':')[1],created=B-1,hours=24)
                    sessions.append(session);session.connect(B-1);session.receive(payload,B)
                    self.assertEqual(session.db.execute('SELECT COUNT(*) FROM ticks').fetchone()[0],1)
                    self.assertEqual(session.report('TEST')['symbol'],symbol)
            finally:
                for session in sessions:session.close()

    def test_history_alignment_and_stale_boundary_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);e=Engine(root,C,'test',created=B-1);sessions=[];views={}
            try:
                for symbol in C['symbols']:
                    session=symbol_module(symbol).Session(root/'feeds'/symbol.split(':')[1],created=B-1,hours=72)
                    sessions.append(session);views[symbol]=View(session)
                    with session.db:
                        for j in range(150):
                            stamp=B+j*900
                            session.db.execute('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?)',(stamp,150,151,149,150,1,1,'complete_observed_interval'))
                            session.db.execute('INSERT INTO ticks(event_ms,received,price,connection) VALUES(?,?,?,?)',((stamp+890)*1000,stamp+890,150,1))
                    views[symbol].refresh(B+150*900+6)
                args=frames_for(e,views,B+150*900+6)
                self.assertTrue(args[3]);self.assertEqual(len(args[1]),4)
                self.assertTrue(all(len(f)==150 for f in args[1].values()))
                source=sessions[-1].db
                with source:source.execute('UPDATE ticks SET event_ms=event_ms-60000 WHERE event_ms=?',((B+149*900+890)*1000,))
                args=frames_for(e,views,B+150*900+6)
                self.assertFalse(args[3]);self.assertEqual(args[2][C['symbols'][-1]]['last_observation_lag_seconds'],70)
            finally:
                for session in sessions:session.close()
                e.close()

    @unittest.skipUnless(all((ROOT / 'model' / name).is_file() for name in
        ('champion_manifest.json', 'hgb_model.joblib', 'calibrator.joblib', 'candidate.joblib')),
        'Private fitted model artifacts are not distributed with this reference code')
    def test_actual_models_produce_finite_predictions(self):
        index=pd.date_range('2026-09-21',periods=200,freq='15min',tz='UTC').as_unit('us')
        frames={}
        for i,symbol in enumerate(C['symbols']):
            close=(150 if i==0 else 1.1)*(1+.001*np.sin(np.arange(200)*.7+i)+np.arange(200)*.000001)
            frames[symbol]=pd.DataFrame({'open':close,'high':close*1.0002,'low':close*.9998,'close':close},index=index)
        with threadpool_limits(limits=2):
            predictor=Predictors(C);result=predictor(frames,index[-1].timestamp()+906)
        self.assertEqual(set(result),{'base','candidate'})
        self.assertTrue(all(np.isfinite(p['confidence']) and .5<=p['confidence']<=1 for p in result.values()))
        x=predictor.candidate_features(frames)
        for symbol in C['symbols'][1:]:
            name=symbol.split(':')[1].replace('_','')
            for h in (1,4,16):
                np.testing.assert_allclose(x[f'{name}_return_{h}'],frames[symbol].close.pct_change(h),equal_nan=True)

    def test_backup_and_report_do_not_mutate_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'state';e=Engine(root,C,'test',created=B)
            before=json.dumps(e.state,sort_keys=True)
            try:
                result=evaluate(root,at=B+100)
                self.assertEqual(result['accounts']['base_fixed']['closed_trades'],0)
                self.assertIsNone(result['accounts']['base_fixed']['win_rate'])
                target=backup(root,Path(directory)/'backups')
                with closing(sqlite3.connect(target/'comparison.sqlite3')) as db:
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                    self.assertEqual(json.dumps(json.loads(db.execute('SELECT data FROM state').fetchone()[0]),sort_keys=True),before)
                self.assertEqual(json.dumps(e.state,sort_keys=True),before)
            finally:e.close()


if __name__=='__main__':unittest.main()

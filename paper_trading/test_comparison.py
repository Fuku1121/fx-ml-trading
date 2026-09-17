from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
import pandas as pd
from engine import Engine,costs

ROOT=Path(__file__).resolve().parent
C=json.loads((ROOT/'protocol.json').read_text())
B=int(pd.Timestamp('2026-09-21 10:00:00',tz='UTC').timestamp())


def predict(frames,at):
    return {'base':{'confidence':.6,'p_up':.6,'side':1,'allowed':True,'legacy_size':1.5},
        'candidate':{'confidence':.6,'p_up':.4,'side':-1,'allowed':True}}


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.e=Engine(self.root,C,'bundle',created=B-1000)
        self.ident=0

    def tearDown(self):self.e.close();self.temp.cleanup()

    def step(self,at,ticks=(),bar=None,ready=True,fn=predict,**kwargs):
        self.e.atomic_step(ticks,bar,{}, {},ready,fn,at,**kwargs)

    def tick(self,at,price=150.):
        self.ident+=1;self.step(at,[(self.ident,int(at*1000),at,price)])

    def start(self):self.step(B+905,bar=B)

    def test_common_start_waits_for_all(self):
        self.step(B+905,bar=B,ready=False)
        self.assertIsNone(self.e.state['start']);self.assertEqual(self.e.db.execute('SELECT count(*) FROM decisions').fetchone()[0],0)
        self.start();self.assertEqual(self.e.state['end'],B+905+30*86400)

    def test_finalization_grace_does_not_consume_decision(self):
        self.start();self.e.disconnected(B+906)
        self.step(B+1801,bar=B+900,ready=False)
        self.assertEqual(self.e.state['last_bar'],B)
        self.step(B+1806,bar=B+900)
        self.assertEqual(self.e.state['last_bar'],B+900)
        self.assertEqual(self.e.db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],4)

    def test_quality_failure_is_recorded_near_deadline(self):
        self.start();self.e.disconnected(B+906)
        self.step(B+1826,bar=B+900,ready=False)
        rows=self.e.db.execute('SELECT data FROM decisions WHERE bar=?',(B+900,)).fetchall()
        self.assertEqual(len(rows),2)
        self.assertTrue(all(json.loads(r[0])['reason']=='SHARED_DATA_QUALITY' for r in rows))

    def test_both_models_skip_rollover(self):
        bar=int(pd.Timestamp('2026-09-21 20:30:00Z').timestamp())
        self.step(bar+905,bar=bar)
        rows=self.e.db.execute('SELECT data FROM decisions').fetchall()
        self.assertTrue(all(json.loads(r[0])['reason']=='ROLLOVER_WINDOW' for r in rows))

    def test_fill_uses_next_received_tick_and_no_duplicate_after_restart(self):
        self.start();self.tick(B+906)
        self.assertTrue(all(a['position'] for a in self.e.state['accounts'].values()))
        deadline=self.e.state['end'];self.e.close();self.e=Engine(self.root,C,'bundle')
        self.step(B+906,[(1,(B+906)*1000,B+906,150.)],bar=B)
        self.assertEqual(self.e.state['end'],deadline)
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM events WHERE kind='ENTRY'").fetchone()[0],3)
        for dt in range(60,7201,60):self.tick(B+906+dt,150.1)
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM trades').fetchone()[0],3)
        self.assertEqual(self.e.state['accounts']['base_fixed']['trades'],1)
        self.assertLess(self.e.state['accounts']['candidate_fixed']['equity'],C['initial_equity'])
        for a in self.e.state['accounts'].values():self.assertLessEqual(a['stress_equity'],a['equity']+1e-8)

    def test_stale_and_future_observations_never_enter(self):
        self.start()
        self.step(B+907,[(1,(B+901)*1000,B+907,150.),(2,(B+908)*1000,B+907,150.)])
        self.assertTrue(all(a['position'] is None for a in self.e.state['accounts'].values()))
        self.step(B+940);self.assertTrue(all(a['pending'] is None for a in self.e.state['accounts'].values()))

    def test_gap_halts_and_retains_open_positions(self):
        self.start();self.tick(B+906);self.tick(B+1030)
        self.assertEqual(self.e.state['phase'],'HALTED')
        self.assertTrue(self.e.state['accounts']['base_fixed']['position'])
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM trades').fetchone()[0],0)

    def test_no_ticks_halts_position(self):
        self.start();self.tick(B+906);self.step(B+1027)
        self.assertEqual(self.e.state['phase'],'HALTED')

    def test_rollback_is_atomic(self):
        def fail(*args):raise ValueError('test failure')
        original=json.dumps(self.e.state,sort_keys=True)
        with self.assertRaises(ValueError):self.step(B+905,bar=B,fn=fail)
        self.assertEqual(json.dumps(self.e.state,sort_keys=True),original)
        saved=json.loads(self.e.db.execute('SELECT data FROM state').fetchone()[0])
        self.assertEqual(json.dumps(saved,sort_keys=True),original)

    def test_changed_bundle_refused(self):
        with self.assertRaises(RuntimeError):Engine(self.root,C,'changed')

    def test_completion_does_not_start_new_experiment(self):
        def none(*args):return {name:{**p,'allowed':False} for name,p in predict(None,0).items()}
        self.step(B+905,bar=B,fn=none);end=self.e.state['end']
        self.step(end);self.assertEqual(self.e.state['phase'],'COMPLETED')
        self.e.close();self.e=Engine(self.root,C,'bundle');self.step(end+10000,bar=B+900)
        self.assertEqual(self.e.state['end'],end);self.assertEqual(self.e.state['phase'],'COMPLETED')

    def test_quality_revocation_halts_if_holding(self):
        self.start();self.tick(B+906);self.step(B+907,revoked=True)
        self.assertEqual(self.e.state['phase'],'HALTED')

    def test_disconnect_cancels_pending(self):
        self.start();self.e.disconnected(B+906);self.tick(B+907)
        self.assertTrue(all(a['position'] is None and a['pending'] is None for a in self.e.state['accounts'].values()))

    def test_delayed_inference_does_not_create_retroactive_entry(self):
        self.e.clock=lambda:B+950
        self.start();self.assertIsNone(self.e.state['start'])
        self.assertTrue(all(a['pending'] is None for a in self.e.state['accounts'].values()))

    def test_costs_identical_for_fixed_accounts(self):
        normal,stress=costs(C,150.)
        self.assertAlmostEqual(normal,.00005+.012/150)
        self.assertGreater(stress,normal)

    def test_warmup_timeout_does_not_extend(self):
        self.step(B-1000+7*86400)
        self.assertEqual(self.e.state['phase'],'HALTED')


if __name__=='__main__':unittest.main()

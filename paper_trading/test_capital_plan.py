import json
from pathlib import Path
import unittest
import pandas as pd
from capital_plan import replay,margin_fraction,anniversaries,evaluate_saved
import tempfile
import sqlite3
from contextlib import closing

ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/'capital_plan.json').read_text())
C=json.loads((ROOT/'protocol.json').read_text())
B=pd.Timestamp('2026-09-21 00:00Z').timestamp()


def entry(start=B,finish=B+60):
    return {'entry_time':start,'entry_price':150.,'exit_time':finish,'due':finish,
            'confidence':.65,'side':1,'bar':start-900}


class CapitalPlan(unittest.TestCase):
    def test_saved_observations_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'feeds/USD_JPY/observations.sqlite3';path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE ticks(id INTEGER,event_ms INTEGER,received REAL,price REAL)')
                db.execute('INSERT INTO ticks VALUES(1,?,?,?)',((B+60)*1000,B+60,151.5));db.commit()
            state={'start':B,'end':B+30*86400,'updated_at':B+60,'tick_id':1,
                'accounts':{'base_fixed':{'position':None},'candidate_fixed':{'position':None}}}
            result=evaluate_saved(root,state,[('base_fixed',entry())],B+60)
            account=result['accounts']['base_fixed']['normal']
            self.assertEqual(account['closed_trades'],1)
            self.assertGreater(account['realized_trading_pnl_jpy'],0)
            self.assertEqual(result['accounts']['candidate_fixed']['normal']['cash_balance_jpy'],30000)

    def test_initial_allocation_25x_and_costs(self):
        result=replay([entry()],lambda a,b:[(B+60,151.5)],B,B+60,P,C)
        trade=result['trades'][0]
        self.assertEqual(trade['units_usd'],5000)
        self.assertEqual(trade['effective_entry_leverage'],25)
        self.assertAlmostEqual(trade['pnl_jpy'],7500-750000*(.00005+.012/150))
        self.assertAlmostEqual(result['cash_balance_jpy']-30000,result['realized_trading_pnl_jpy'])

    def test_threshold_and_confidence_allocation(self):
        self.assertEqual(margin_fraction(100000,.58,P),1)
        low=margin_fraction(100001,.58,P);high=margin_fraction(100001,.75,P)
        self.assertLess(low,high);self.assertLessEqual(high,1)
        self.assertEqual(margin_fraction(100001,1.,P),1)

    def test_monthly_anniversary_not_every_30_days(self):
        start=pd.Timestamp('2026-01-31 10:00',tz='Asia/Tokyo').timestamp()
        end=pd.Timestamp('2026-03-31 10:00',tz='Asia/Tokyo').timestamp()
        expected=[pd.Timestamp(t,tz='Asia/Tokyo').timestamp() for t in ('2026-02-28 10:00','2026-03-31 10:00')]
        self.assertEqual(list(anniversaries(start,end)),expected)
        result=replay([],lambda a,b:[],start,end,P,C)
        self.assertEqual(result['cash_balance_jpy'],90000)
        self.assertEqual(result['total_contributions_jpy'],90000)
        self.assertEqual(result['realized_trading_pnl_jpy'],0)

    def test_deposit_does_not_resize_open_trade(self):
        anniversary=next(anniversaries(B,B+40*86400))
        start=anniversary-60;finish=anniversary+60
        result=replay([entry(start,finish)],lambda a,b:[(anniversary,150.),(finish,150.)],B,finish,P,C)
        self.assertEqual(result['total_contributions_jpy'],60000)
        self.assertEqual(result['trades'][0]['units_usd'],5000)
        self.assertAlmostEqual(result['cash_balance_jpy'],60000-result['trades'][0]['cost_jpy'])

    def test_observed_intratrade_margin_exit(self):
        result=replay([entry(finish=B+120)],lambda a,b:[(B+60,146.),(B+120,151.)],B,B+120,P,C)
        self.assertEqual(result['trades'][0]['reason'],'ASSUMED_MARGIN_STOP')
        self.assertEqual(result['trades'][0]['exit_price'],146.)
        self.assertLess(result['realized_trading_pnl_jpy'],0)

    def test_negative_balance_retained_and_not_rescued(self):
        result=replay([entry()],lambda a,b:[(B+60,140.)],B,B+40*86400,P,C)
        self.assertEqual(result['phase'],'INSOLVENT')
        self.assertLess(result['cash_balance_jpy'],0)
        self.assertEqual(result['total_contributions_jpy'],30000)

    def test_gap_is_unresolved_not_fake_profitable_exit(self):
        result=replay([entry(finish=B+300)],lambda a,b:[(B+300,155.)],B,B+300,P,C)
        self.assertEqual(result['phase'],'UNRESOLVED_DATA_GAP')
        self.assertEqual(result['closed_trades'],0)
        self.assertIsNotNone(result['open_position'])

    def test_repeated_report_does_not_double_deposit(self):
        first=replay([],lambda a,b:[],B,B+40*86400,P,C)
        second=replay([],lambda a,b:[],B,B+40*86400,P,C)
        self.assertEqual(first,second)
        self.assertEqual(first['total_contributions_jpy'],60000)

    def test_stress_cost_reduces_equity(self):
        normal=replay([entry()],lambda a,b:[(B+60,150.)],B,B+60,P,C)
        stress=replay([entry()],lambda a,b:[(B+60,150.)],B,B+60,P,C,True)
        self.assertLess(stress['cash_balance_jpy'],normal['cash_balance_jpy'])


if __name__=='__main__':unittest.main()

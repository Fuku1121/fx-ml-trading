import unittest
import numpy as np
import pandas as pd
from research import select_trades,stats,inference,FEATURES,price_targets


class ResearchChecks(unittest.TestCase):
    def test_bid_ask_prices_and_exit_horizon(self):
        idx=pd.date_range('2025-01-01',periods=6,freq='15min',tz='UTC')
        bid=pd.DataFrame({'open':[99,100,102,103,105,107],'close':[99,101,103,104,106,108]},index=idx)
        ask=bid+1
        r=price_targets(bid,ask).iloc[0]
        self.assertAlmostEqual(r.entrymid,100.5)
        self.assertAlmostEqual(r.long2,(103-101)/100.5)
        self.assertAlmostEqual(r.short2,(100-104)/100.5)
        self.assertAlmostEqual(r.long4,(106-101)/100.5)
        self.assertAlmostEqual(r.long2,r.r2-r.spread2)
        self.assertAlmostEqual(r.short2,-r.r2-r.spread2)

    def test_nonoverlap_and_threshold(self):
        f=pd.DataFrame({'long2':[-.001]*8,'short2':[.002]*8,'spread2':[.0001]*8},
            index=pd.date_range('2025-01-01',periods=8,freq='15min',tz='UTC'))
        trades=select_trades(f,np.array([.57,.6,.9,.6,.6,.2,.9,.6]),2)
        self.assertEqual(list(trades.side),[1,1,-1,1])
        self.assertTrue((trades.entry.iloc[1:].to_numpy()>=trades.exit.iloc[:-1].to_numpy()).all())
        self.assertEqual(trades.iloc[0].entry,f.index[2])
        self.assertAlmostEqual(trades.iloc[2].quoted_net,.002)

    def test_initial_loss_drawdown(self):
        t=pd.DataFrame({'net':[-.01,.005],'stress_net':[-.02,.004]})
        result=stats(t,10)
        self.assertAlmostEqual(result['closed_drawdown_pct'],-1)
        self.assertLess(result['stress_return_pct'],result['return_pct'])

    def test_no_trades(self):
        t=pd.DataFrame({'net':[],'stress_net':[]})
        self.assertEqual(stats(t,10)['return_pct'],0)

    def test_feature_causality(self):
        rng=np.random.default_rng(4)
        close=1+np.cumsum(rng.normal(0,.001,400))
        f=pd.DataFrame({'open':close+.0001,'close':close,'high':close+.001,'low':close-.001},
            index=pd.date_range('2025-01-01',periods=400,freq='15min',tz='UTC'))
        before=inference.make_live_features(f)[FEATURES]
        f.iloc[300:]*=1.1
        after=inference.make_live_features(f)[FEATURES]
        pd.testing.assert_frame_equal(before.iloc[:300],after.iloc[:300])


if __name__=='__main__':unittest.main()

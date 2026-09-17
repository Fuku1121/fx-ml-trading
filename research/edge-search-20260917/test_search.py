import unittest
import numpy as np
import pandas as pd
from search import history_ok,trades_for,metrics,closed_market,make_frames,BASE


class Checks(unittest.TestCase):
    def test_weekend_and_real_gap(self):
        index=pd.date_range('2025-01-06',periods=1000,freq='15min',tz='UTC')
        index=index[~closed_market(index)]
        valid=history_ok(index)
        sunday=pd.Timestamp('2025-01-12 22:00',tz='UTC')
        self.assertTrue(valid.loc[sunday])
        hole=pd.Timestamp('2025-01-08 10:00',tz='UTC')
        broken=index[index!=hole]
        valid=history_ok(broken)
        nextbar=hole+pd.Timedelta(minutes=15)
        i=broken.get_loc(nextbar)
        self.assertFalse(valid.iloc[i:i+149].any())
        self.assertTrue(valid.iloc[i+149])

    def test_known_cost_and_nonoverlap(self):
        idx=pd.date_range('2025-01-01',periods=10,freq='15min',tz='UTC')
        f=pd.DataFrame({'estimated_cost':.0001,'long4':.001,'short4':-.001,'extra_cost4':.0001},index=idx)
        p=np.repeat(.6,10);expected=np.repeat(.00014,10)
        self.assertEqual(len(trades_for(f,4,p,expected,'cost_filtered')),0)
        expected[:]=.0002
        t=trades_for(f,4,p,expected,'cost_filtered')
        self.assertEqual(len(t),3)
        self.assertTrue((t.entry.iloc[1:].to_numpy()>=t.exit.iloc[:-1].to_numpy()).all())
        self.assertLess(metrics(t,1)['stress_return_pct'],metrics(t,1)['return_pct'])

    def test_cross_features_causal(self):
        rng=np.random.default_rng(1)
        idx=pd.date_range('2025-01-06',periods=1000,freq='15min',tz='UTC')
        raw={}
        for pair in ('USDJPY','EURUSD','GBPUSD','AUDUSD'):
            c=1+np.cumsum(rng.normal(0,.0001,len(idx)))
            bid=pd.DataFrame({'open':c,'high':c+.0001,'low':c-.0001,'close':c,'volume':10},index=idx)
            ask=bid.copy();ask[['open','high','low','close']]+=.00005
            raw[pair]=(bid,ask)
        before=make_frames(raw)['EURUSD']
        for sides in raw.values():
            for frame in sides:frame.loc[idx[700]:,['open','high','low','close']]*=1.1
        after=make_frames(raw)['EURUSD']
        features=BASE+[c for c in before if '_return_' in c]
        pd.testing.assert_frame_equal(before.loc[:idx[699],features],after.loc[:idx[699],features])


if __name__=='__main__':unittest.main()

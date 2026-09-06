import unittest
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from fx_research.backtest import simulate_trade, run_backtest
from fx_research.data import load_bars
from fx_research.features import make_features
from fx_research.labels import prepare_data
from fx_research.metrics import strategy_stats
from fx_research.splits import outer_folds
from fx_research.signals import make_signals


def flat_bars(n=30):
    return pd.DataFrame(
        {"Open": 100.0, "High": 100.1, "Low": 99.9, "Close": 100.0},
        index=pd.date_range("2025-01-06", periods=n, freq="5min", tz="Asia/Tokyo"),
    )


def varied_bars(n=1500):
    rng = np.random.default_rng(7)
    close = 150 * np.exp(np.cumsum(rng.normal(0, 0.0006, n)))
    opening = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "Open": opening,
            "High": np.maximum(opening, close) + 0.03,
            "Low": np.minimum(opening, close) - 0.03,
            "Close": close,
        },
        index=pd.date_range("2025-01-06", periods=n, freq="5min", tz="Asia/Tokyo"),
    )


class BacktestTests(unittest.TestCase):
    def test_entry_and_time_exit_ignore_signal_close(self):
        bars = flat_bars()
        bars.iloc[0] = [99, 101, 98, 99]
        bars.loc[bars.index[6], ["High", "Close"]] = [101, 101]
        t = simulate_trade(bars, bars.index[0], "BUY", 0.05, 0.05, cost=0.001)
        self.assertEqual(t["entry_price"], 100)
        self.assertEqual(t["entry_time"], bars.index[1])
        self.assertEqual(t["exit_time"], bars.index[6] + pd.Timedelta(minutes=5))
        self.assertAlmostEqual(t["net_return"], 0.009)
        self.assertEqual(t["exit_reason"], "TIME")

    def test_sell_entry_notional_return(self):
        bars = flat_bars()
        bars.loc[bars.index[6], ["Low", "Close"]] = [98, 98]
        t = simulate_trade(bars, bars.index[0], "SELL", 0.05, 0.05, cost=0.001)
        self.assertAlmostEqual(t["net_return"], 0.019)

    def test_tp_sl_both_sides(self):
        for side, field, price, expected, reason in [
            ("BUY", "High", 102, 0.01, "TP"),
            ("BUY", "Low", 98, -0.01, "SL"),
            ("SELL", "Low", 98, 0.01, "TP"),
            ("SELL", "High", 102, -0.01, "SL"),
        ]:
            with self.subTest(side=side, reason=reason):
                bars = flat_bars()
                bars.loc[bars.index[1], field] = price
                t = simulate_trade(bars, bars.index[0], side, 0.01, 0.01, cost=0)
                self.assertEqual(t["exit_reason"], reason)
                self.assertAlmostEqual(t["net_return"], expected)

    def test_same_bar_sl_first(self):
        bars = flat_bars()
        bars.loc[bars.index[1], ["High", "Low"]] = [102, 98]
        for side in ["BUY", "SELL"]:
            t = simulate_trade(bars, bars.index[0], side, 0.01, 0.01, cost=0.001)
            self.assertAlmostEqual(t["net_return"], -0.011)
            self.assertEqual(t["exit_reason"], "SL")

    def test_stop_gap_uses_worse_open(self):
        for side, price in [("BUY", 97), ("SELL", 103)]:
            bars = flat_bars()
            bars.iloc[2] = [price, price + 0.1, price - 0.1, price]
            t = simulate_trade(bars, bars.index[0], side, 0.01, 0.01, cost=0)
            self.assertEqual(t["exit_reason"], "GAP_SL")
            self.assertAlmostEqual(t["net_return"], -0.03)

    def test_boundary_no_prices_after_evaluation(self):
        bars = flat_bars()
        self.assertIsNone(
            simulate_trade(
                bars, bars.index[0], "BUY", 0.01, 0.01, end_time=bars.index[6]
            )
        )
        self.assertIsNotNone(
            simulate_trade(
                bars, bars.index[0], "BUY", 0.01, 0.01, end_time=bars.index[7]
            )
        )
        self.assertIsNone(simulate_trade(bars, bars.index[-3], "BUY", 0.01, 0.01))

    def test_missing_bar_excluded(self):
        bars = flat_bars().drop(flat_bars().index[3])
        self.assertIsNone(simulate_trade(bars, bars.index[0], "BUY", 0.01, 0.01))

    def test_nonoverlap_uses_raw_positions_even_with_filtered_frame(self):
        bars = flat_bars()
        frame = bars.iloc[[0, 2, 6, 7, 12]]
        trades = run_backtest(bars, frame, np.ones(len(frame)), 0.01, 0.01)
        self.assertEqual(trades.signal_position.tolist(), [0, 6, 12])

    def test_early_tp_retains_horizon_lockout(self):
        bars = flat_bars()
        bars.loc[bars.index[1], "High"] = 102
        trades = run_backtest(bars, bars.iloc[:8], np.ones(8), 0.01, 0.01)
        self.assertEqual(trades.signal_position.tolist(), [0, 6])

    def test_invalid_signal_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(flat_bars(), flat_bars(), np.ones(2), 0.01, 0.01)


class MetricTests(unittest.TestCase):
    def test_initial_loss_in_drawdown(self):
        self.assertAlmostEqual(strategy_stats([-0.1])["max_dd"], -0.1)
        self.assertAlmostEqual(strategy_stats([-0.1, 0.05])["max_dd"], -0.1)

    def test_pf_and_empty(self):
        self.assertAlmostEqual(strategy_stats([0.02, -0.01])["profit_factor"], 2)
        self.assertEqual(strategy_stats([])["trades"], 0)
        self.assertTrue(np.isnan(strategy_stats([0])["profit_factor"]))
        self.assertTrue(np.isinf(strategy_stats([0.01])["profit_factor"]))


class FeatureAndSplitTests(unittest.TestCase):
    def test_future_prices_do_not_change_past_features(self):
        bars = varied_bars(180)
        before = make_features(bars)
        altered = bars.copy()
        altered.iloc[100:] *= 1.5
        after = make_features(altered)
        pd.testing.assert_frame_equal(before.iloc[:100], after.iloc[:100])
        pd.testing.assert_frame_equal(bars, varied_bars(180))

    def test_label_exact_prices_and_drop_tail(self):
        bars = varied_bars(180)
        data = prepare_data(bars)
        t = data.index[0]
        i = bars.index.get_loc(t)
        self.assertAlmostEqual(
            data.loc[t, "future_return"],
            bars.Close.iloc[i + 6] / bars.Open.iloc[i + 1] - 1,
        )
        self.assertTrue((data.index < bars.index[-6]).all())
        self.assertEqual(
            data.loc[t, "label_end"], bars.index[i + 6] + pd.Timedelta(minutes=5)
        )

    def test_fold_labels_do_not_cross_boundaries(self):
        data = prepare_data(varied_bars())
        folds = list(outer_folds(data))
        self.assertEqual(len(folds), 5)
        for fold in folds:
            self.assertLessEqual(fold.core.label_end.max(), fold.validation.index.min())
            self.assertLessEqual(fold.train.label_end.max(), fold.test.index.min())
        for a, b in zip(folds, folds[1:]):
            self.assertLess(a.test.index.max(), b.test.index.min())

    def test_quality_gate_and_tie_wait(self):
        result = make_signals(
            np.array([0.8, 0.8, 0.8]),
            np.array([0.7, 0.2, 0.5]),
            np.array([0.3, 0.8, 0.5]),
            0.6,
            0.5,
            np.array([0.4, 0.7, 0.9]),
            0.6,
        )
        np.testing.assert_array_equal(result, [0, -1, 0])


class DataTests(unittest.TestCase):
    def write_and_load(self, frame):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bars.csv"
            frame.to_csv(p, index_label="timestamp")
            return load_bars(p)

    def test_timezone_normalization(self):
        bars = flat_bars()
        bars.index = bars.index.tz_convert("UTC")
        loaded = self.write_and_load(bars)
        self.assertEqual(str(loaded.index.tz), "Asia/Tokyo")

    def test_naive_duplicate_and_bad_ohlc_rejected(self):
        naive = flat_bars()
        naive.index = naive.index.tz_localize(None)
        duplicate = pd.concat([flat_bars(), flat_bars()])
        bad = flat_bars()
        bad.iloc[0, 1] = 1
        for bars in [naive, duplicate, bad]:
            with self.subTest(), self.assertRaises(ValueError):
                self.write_and_load(bars)


if __name__ == "__main__":
    unittest.main()

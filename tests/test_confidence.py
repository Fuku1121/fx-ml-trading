import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from fx_research.confidence import (
    Settings, annual_splits, choose_threshold, load_prices,
    prepare_prices, run, select_trades,
)
from fx_research.confidence_features import FEATURES


def bars(index):
    rng = np.random.default_rng(42)
    close = 140 + np.cumsum(rng.normal(0, .04, len(index)))
    opening = close + rng.normal(0, .02, len(index))
    return pd.DataFrame({'open': opening, 'close': close,
                         'high': np.maximum(opening, close) + .02,
                         'low': np.minimum(opening, close) - .02}, index=index)


class ConfidenceTests(unittest.TestCase):
    def test_label_prices_and_gap_exclusion(self):
        index = pd.date_range('2020-01-01', periods=400, freq='15min', tz='UTC')
        source = bars(index.delete(300))
        frame = prepare_prices(source)
        signal = index[200]
        self.assertEqual(frame.loc[signal, 'entry_price'], source.loc[index[201], 'open'])
        self.assertEqual(frame.loc[signal, 'exit_price'], source.loc[index[202], 'close'])
        self.assertEqual(frame.loc[signal, 'label_end'], index[203])
        self.assertNotIn(index[298], frame.index)
        self.assertNotIn(index[299], frame.index)

    def test_features_do_not_read_future(self):
        index = pd.date_range('2020-01-01', periods=400, freq='15min', tz='UTC')
        source = bars(index)
        changed = source.copy()
        changed.loc[index[251]:] *= 2
        pd.testing.assert_frame_equal(prepare_prices(source).loc[:index[250], FEATURES],
                                      prepare_prices(changed).loc[:index[250], FEATURES])

    def test_year_boundaries_purge_unavailable_labels(self):
        index = pd.DatetimeIndex(['2016-06-01', '2017-12-31 23:15',
                                  '2017-12-31 23:45', '2018-12-31 23:15',
                                  '2018-12-31 23:45', '2019-06-01'], tz='UTC')
        data = pd.DataFrame({'label_end': index + pd.Timedelta(minutes=45)}, index=index)
        split = list(annual_splits(data, Settings(min_train_years=2)))[0]
        year, train, validation, final_train, test = split
        self.assertEqual(year, 2019)
        self.assertIn(index[1], train.index)
        self.assertNotIn(index[2], train.index)
        self.assertNotIn(index[4], validation.index)
        self.assertNotIn(index[4], final_train.index)
        self.assertTrue((test.label_end <= pd.Timestamp('2020-01-01', tz='UTC')).all())

    def predictions(self):
        index = pd.date_range('2020-01-01', periods=5, freq='15min', tz='UTC')
        return pd.DataFrame({'entry_time': index + pd.Timedelta(minutes=15),
                             'label_end': index + pd.Timedelta(minutes=45),
                             'confidence': [.6] * 5,
                             'gross_return': [.00002] * 5}, index=index)

    def test_nonoverlap_and_cost(self):
        data = self.predictions()
        trades = select_trades(data, .55, .00004)
        self.assertEqual(list(trades.index), list(data.index[::2]))
        np.testing.assert_allclose(trades.net_return, -.00002)
        self.assertTrue((trades.gross_return > 0).all())
        self.assertTrue((trades.net_return < 0).all())

    def test_negative_validation_winner_and_minimum_count(self):
        best, table = choose_threshold(self.predictions(),
            Settings(thresholds=(.5, .65), min_validation_trades=2))
        self.assertEqual(best, .5)
        self.assertLess(table.iloc[0].score, 0)
        self.assertFalse(table.iloc[1].eligible)

    def test_csv_rejects_implicit_timezone_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bars.csv'
            data = bars(pd.date_range('2020-01-01', periods=150, freq='15min'))
            data.to_csv(path)
            with self.assertRaisesRegex(ValueError, 'UTC offset'):
                load_prices(path)
            data.index = data.index.tz_localize('UTC')
            pd.concat([data, data.tail(1)]).to_csv(path)
            with self.assertRaisesRegex(ValueError, 'unique'):
                load_prices(path)

    def test_synthetic_annual_end_to_end(self):
        index = pd.DatetimeIndex([])
        for year in range(2016, 2022):
            part = pd.date_range(f'{year}-06-01', periods=400, freq='15min', tz='UTC')
            index = part if index.empty else index.append(part)
        with tempfile.TemporaryDirectory() as directory:
            path, output = Path(directory) / 'prices.csv', Path(directory) / 'result'
            bars(index).to_csv(path)
            result = run(path, output, Settings(trees=8, thresholds=(.5, .55),
                min_train_rows=100, min_eval_rows=20, min_validation_trades=2))
            self.assertEqual(list(result.side), ['ALL', 'BUY', 'SELL'])
            self.assertGreater(result.iloc[0].trades, 0)
            metadata = json.loads((output / 'run.json').read_text())
            self.assertEqual(metadata['evaluated_years'], 2)
            self.assertEqual(metadata['status'], 'completed')
            annual = pd.read_csv(output / 'annual.csv')
            self.assertEqual(list(annual.test_year), [2020, 2021])
            trades = pd.read_csv(output / 'trades.csv')
            entry = pd.to_datetime(trades.entry_time, utc=True)
            end = pd.to_datetime(trades.label_end, utc=True)
            self.assertTrue((entry.iloc[1:].reset_index(drop=True) >=
                             end.iloc[:-1].reset_index(drop=True)).all())
            with self.assertRaises(FileExistsError):
                run(path, output)


if __name__ == '__main__':
    unittest.main()

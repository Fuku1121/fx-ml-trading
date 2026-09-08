"""HGB分割時の計算維持と、価格・時間境界・保存処理を検証する。"""

import ast
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from fx_research.hgb import calibration, config, evaluation, features, trading
from fx_research.hgb.runner import run


def prices(index):
    rng = np.random.default_rng(19)
    close = 140 + rng.normal(0, .05, len(index)).cumsum()
    opening = close + rng.normal(0, .02, len(index))
    return pd.DataFrame({"open": opening, "close": close,
                         "high": np.maximum(opening, close) + .03,
                         "low": np.minimum(opening, close) - .03}, index=index)


def computational_ast(node):
    node = copy.deepcopy(node)
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.ClassDef)) and child.body:
            first = child.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                child.body.pop(0)
    return ast.dump(node, include_attributes=False)


class HGBTests(unittest.TestCase):
    def test_extracted_calculations_match_research_source(self):
        root = Path(__file__).resolve().parents[1]
        notebook = json.loads((root / "notebooks/archive/27_hgb_reintegration.ipynb")
                              .read_text(encoding="utf-8"))
        source = "".join([c for c in notebook["cells"] if c["cell_type"] == "code"][-1]["source"])
        nodes = ast.parse(source).body
        original = {n.name: n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        seen = set()
        for module in (features, calibration, trading, evaluation):
            for node in ast.parse(Path(module.__file__).read_text(encoding="utf-8")).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    self.assertEqual(computational_ast(node), computational_ast(original[node.name]))
                    seen.add(node.name)
        self.assertEqual(seen, set(original))
        # Verify the fixed candidate lists and model settings as well as functions.
        original_settings = {}
        selected = [n for n in nodes if isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name)
                    and (n.lineno < 80 or n.targets[0].id.endswith(("FEATURES", "ADDITIONS")))]
        exec(compile(ast.Module(body=selected, type_ignores=[]), "settings", "exec"), original_settings)
        for name, value in original_settings.items():
            if name.isupper():
                module = features if hasattr(features, name) else config
                self.assertEqual(getattr(module, name), value, name)

    def test_future_prices_do_not_change_past_features(self):
        index = pd.date_range("2020-01-01", periods=600, freq="15min", tz="UTC")
        bars = prices(index)
        changed = bars.copy()
        changed.loc[index[400]:] *= 1.2
        original = features.make_all_features(bars)
        modified = features.make_all_features(changed)
        pd.testing.assert_frame_equal(original.loc[:index[399], features.CHAMPION_FEATURES],
                                      modified.loc[:index[399], features.CHAMPION_FEATURES])

    def test_missing_bar_and_year_boundary(self):
        index = pd.date_range("2019-12-25", periods=900, freq="15min", tz="UTC")
        bars = prices(index.delete(500))
        data = features.prepare_dataset(bars, features.BASE_FEATURES)
        self.assertNotIn(index[498], data.index)
        self.assertNotIn(index[499], data.index)
        with patch.object(evaluation, "MIN_TRAIN_ROWS", 1), patch.object(evaluation, "MIN_EVAL_ROWS", 1):
            old = data.copy()
            old.index = old.index - pd.DateOffset(years=2)
            old["label_end"] = old.label_end - pd.DateOffset(years=2)
            split = evaluation.make_split(pd.concat([old, data]), 2020)
        boundary = pd.Timestamp("2020-01-01", tz="UTC")
        self.assertTrue((split["validation"].label_end <= boundary).all())
        self.assertTrue((split["final_train"].label_end <= boundary).all())

    def test_calibration_implementations_and_fallback(self):
        rng = np.random.default_rng(1)
        p = np.linspace(.1, .9, 1100)
        oof = pd.DataFrame({"prob": p, "target": rng.binomial(1, p)})
        for method in ("RAW", "PLATT", "ISOTONIC"):
            calibrator = calibration.fit_calibrator(method, oof)
            result = calibrator.predict(p)
            self.assertEqual(len(result), len(p))
            self.assertTrue(np.isfinite(result).all())
            self.assertTrue(((result >= 0) & (result <= 1)).all())
        self.assertIsInstance(calibration.fit_calibrator("ISOTONIC", oof.iloc[:500]),
                              calibration.RawCalibrator)

    def test_nonoverlap_and_sized_cost(self):
        index = pd.date_range("2020-01-01 21:00", periods=5, freq="15min", tz="UTC")
        predictions = pd.DataFrame({"confidence": .7, "gross_return": .001,
                                    "entry_time": index + pd.Timedelta(minutes=15),
                                    "label_end": index + pd.Timedelta(minutes=45)}, index=index)
        trades = trading.select_trades(predictions, .6, "UTC_21_24")
        self.assertEqual(list(trades.index), list(index[::2]))
        sized = trading.apply_sizing(trades, .6, "FIXED", 1.5, cost_multiplier=2)
        np.testing.assert_allclose(sized.net_return, 1.5 * (.001 - 2 * config.COST))

    def test_synthetic_hgb_pipeline_and_output_contract(self):
        index = pd.date_range("2016-06-01", periods=350, freq="15min", tz="UTC")
        for year in range(2017, 2022):
            index = index.append(pd.date_range(f"{year}-06-01", periods=350,
                                              freq="15min", tz="UTC"))
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            for module in (calibration, evaluation):
                stack.enter_context(patch.object(module, "MIN_TRAIN_ROWS", 80))
                stack.enter_context(patch.object(module, "MIN_EVAL_ROWS", 20))
            stack.enter_context(patch.dict(config.HGB_CONFIG, {"max_iter": 5}))
            stack.enter_context(patch.object(trading, "THRESHOLDS", [.5]))
            stack.enter_context(patch.object(trading, "MIN_VALIDATION_TRADES", 2))
            stack.enter_context(threadpool_limits(limits=1))
            path, output = Path(directory) / "prices.csv", Path(directory) / "result"
            prices(index).to_csv(path)
            summary = run(path, output, years=[2020, 2021])
            self.assertEqual(list(summary.feature_set), ["BASE", "CHAMPION"])
            self.assertTrue((summary.trades > 0).all())
            annual = pd.read_csv(output / "annual.csv")
            self.assertEqual(len(annual), 4)
            metadata = json.loads((output / "run.json").read_text())
            self.assertEqual(metadata["status"], "completed")
            self.assertEqual(metadata["input_rows"], len(index))
            with self.assertRaises(FileExistsError):
                run(path, output)


if __name__ == "__main__":
    unittest.main()

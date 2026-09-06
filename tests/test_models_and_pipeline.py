import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from fx_research import models, quality, config
from fx_research.labels import prepare_data
from fx_research.feature_sets import (
    move_features,
    direction_features,
    quality_market_features,
)
from fx_research.pipeline import run_experiment
from test_core import varied_bars


def small_forest(**kwargs):
    # Deliberately small forests for integration mechanics, not performance evaluation.
    kwargs["n_estimators"] = 8
    kwargs["n_jobs"] = 1
    return RandomForestClassifier(**kwargs)


class ModelTests(unittest.TestCase):
    def test_oof_predictions_are_from_strictly_past_training(self):
        frame = prepare_data(varied_bars(1400))
        train_ends, prediction_starts = [], []

        def fit(train, trees=180):
            train_ends.append(train.label_end.max())
            return object()

        def predict(model, future):
            prediction_starts.append(future.index.min())
            self.assertLessEqual(train_ends[-1], future.index.min())
            n = len(future)
            return np.full(n, 0.7), np.full(n, 0.6), np.full(n, 0.4)

        with (
            patch.object(quality, "fit_base_models", fit),
            patch.object(quality, "predict_base_models", predict),
        ):
            result = quality.create_quality_oof_dataset(frame)
        self.assertEqual(len(train_ends), config.QUALITY_OOF_SPLITS)
        self.assertIsNotNone(result)
        self.assertTrue(result.index.is_unique)
        self.assertTrue(result.index.is_monotonic_increasing)
        self.assertGreater(result.index.min(), frame.index.min())
        self.assertNotIn("future_return", result.columns)

    def test_quality_label_and_feature_allowlists(self):
        frame = pd.DataFrame({"future_return": [0.01, -0.01, 0.000001]})
        target, net = quality.make_quality_target(
            frame, np.array([0.8, 0.2, 0.8]), np.array([0.2, 0.8, 0.2])
        )
        np.testing.assert_array_equal(target, [1, 1, 0])
        np.testing.assert_allclose(net[:2], [0.01 - config.TRADING_COST] * 2)
        forbidden = {
            "future_return",
            "entry_price",
            "exit_price",
            "label_end",
            "move_target",
            "direction_target",
        }
        self.assertFalse(
            forbidden.intersection(
                move_features + direction_features + quality_market_features
            )
        )

    def test_move_one_class_skips(self):
        frame = prepare_data(varied_bars(700))
        frame["move_target"] = 1
        self.assertIsNone(models.fit_base_models(frame, trees=8))

    def test_end_to_end_synthetic_run(self):
        bars = varied_bars(2200)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv = root / "synthetic.csv"
            bars.to_csv(csv, index_label="timestamp")
            output = root / "run"
            with (
                patch.object(models, "RandomForestClassifier", small_forest),
                patch.object(quality, "RandomForestClassifier", small_forest),
                patch.object(config, "MOVE_PROB_LIST", [0.0]),
                patch.object(config, "DIRECTION_PROB_LIST", [0.5]),
                patch.object(config, "QUALITY_PROB_LIST", [0.0, 0.5]),
                patch.object(config, "TP_LIST", [0.001]),
                patch.object(config, "SL_LIST", [0.001]),
                patch.object(config, "MIN_VALIDATION_TRADES", 2),
            ):
                summary = run_experiment(csv, output)
            self.assertEqual(set(summary.strategy), {"BASE", "QUALITY"})
            run = json.loads((output / "run.json").read_text())
            self.assertEqual(run["status"], "completed")
            self.assertGreater(run["evaluated_folds"], 0)
            self.assertEqual(
                run["input_sha256"], hashlib.sha256(csv.read_bytes()).hexdigest()
            )
            folds = pd.read_csv(output / "folds.csv")
            self.assertEqual(len(folds), 5)
            trades = pd.read_csv(output / "trades.csv")
            self.assertGreater(len(trades), 0)
            self.assertTrue(set(trades.strategy) == {"BASE", "QUALITY"})
            np.testing.assert_allclose(
                trades.net_return, trades.gross_return - trades.cost, atol=1e-14
            )
            for (_, _), group in trades.groupby(["fold", "strategy"]):
                self.assertTrue((group.signal_position.diff().dropna() >= 6).all())
            with self.assertRaises(FileExistsError):
                run_experiment(csv, output)


class ArchiveTests(unittest.TestCase):
    def test_every_historical_code_cell_matches_source_hash(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (root / "results/legacy/provenance.json").read_text(encoding="utf-8")
        )
        for item in manifest["cells"]:
            archive = json.loads((root / item["archive"]).read_text(encoding="utf-8"))
            hashes = [
                hashlib.sha256("".join(c["source"]).encode()).hexdigest()
                for c in archive["cells"]
                if c["cell_type"] == "code"
            ]
            self.assertIn(item["source_sha256"], hashes)
        self.assertEqual(len(manifest["cells"]), 16)


if __name__ == "__main__":
    unittest.main()

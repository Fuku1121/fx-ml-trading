"""仕様固定後の特徴量の原本一致と取り込み資料の整合性を確認する。"""

import ast
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from fx_research.frozen import base_features, features


ROOT = Path(__file__).resolve().parents[1]


def sample_prices():
    rng = np.random.default_rng(2026)
    index = pd.date_range("2020-01-01", periods=650, freq="15min", tz="UTC")
    close = 140 + np.cumsum(rng.normal(0, .04, len(index)))
    opening = close + rng.normal(0, .02, len(index))
    return pd.DataFrame({"open": opening, "high": np.maximum(opening, close) + .02,
                         "low": np.minimum(opening, close) - .02, "close": close}, index=index)


class FrozenFeatureTests(unittest.TestCase):
    def test_reference_functions_and_feature_order_match_notebook(self):
        notebook = json.loads((ROOT / "notebooks/archive/30_clean_feature_tournament.ipynb")
                              .read_text(encoding="utf-8"))
        sources = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]
        for module, source in zip((base_features, features), sources):
            original = ast.parse(source)
            functions = {n.name: n for n in original.body if isinstance(n, ast.FunctionDef)}
            constants = {n.targets[0].id: n for n in original.body
                         if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
            extracted = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            for node in extracted.body:
                if isinstance(node, ast.FunctionDef):
                    self.assertEqual(ast.dump(node), ast.dump(functions[node.name]))
                elif isinstance(node, ast.Assign):
                    self.assertEqual(ast.dump(node), ast.dump(constants[node.targets[0].id]))
        self.assertEqual(features.FORMAL_BASE_FEATURES, base_features.BASE_FEATURES)
        self.assertEqual(len(features.FEATURE_SETS["BASE_PLUS_REGIME"]), 41)
        self.assertEqual(len(features.FEATURE_SETS["BASE_PLUS_VOL_REGIME"]), 54)

    def test_future_prices_do_not_change_past_feature_values(self):
        prices = sample_prices()
        original = features.make_final_tournament_features(prices)
        modified = prices.copy()
        modified.iloc[500:] *= 1.3
        altered = features.make_final_tournament_features(modified)
        columns = features.FEATURE_SETS["BASE_PLUS_REGIME"]
        pd.testing.assert_frame_equal(original.iloc[:500][columns], altered.iloc[:500][columns])

    def test_full_history_prefix_and_input_immutability(self):
        prices = sample_prices()
        before = prices.copy(deep=True)
        whole = features.make_final_tournament_features(prices)
        columns = features.FEATURE_SETS["BASE_PLUS_REGIME"]
        for end in (300, 450, 600):
            prefix = features.make_final_tournament_features(prices.iloc[:end])
            pd.testing.assert_series_equal(prefix.iloc[-1][columns], whole.iloc[end - 1][columns])
        pd.testing.assert_frame_equal(prices, before)

    def test_imported_evidence_and_error_history_are_preserved(self):
        manifest = json.loads((ROOT / "results/imported_fx3/provenance.json").read_text(encoding="utf-8"))
        self.assertEqual([c["source_cell_index"] for c in manifest["cells"]], list(range(59, 90)))
        failures = []
        for entry in manifest["cells"]:
            notebook = json.loads((ROOT / entry["archive"]).read_text(encoding="utf-8"))
            hashes = [hashlib.sha256("".join(c["source"]).encode()).hexdigest()
                      for c in notebook["cells"] if c["cell_type"] == "code"]
            self.assertIn(entry["archive_sha256"], hashes)
            # Text-mode normalization makes integrity checks portable across Git EOL settings.
            text = (ROOT / entry["output"]).read_text(encoding="utf-8")
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), entry["output_sha256"])
            if entry["syntax"] != "valid":
                failures.append(entry["source_cell_index"])
        self.assertEqual(failures, [82])
        status = json.loads((ROOT / "results/published/frozen_contract_saved.json").read_text())
        self.assertEqual(status["historical_replay_trades"], 300)
        self.assertEqual(status["forward_processed"], 0)
        self.assertFalse(status["real_orders"])
        annual = pd.read_csv(ROOT / "results/published/clean_annual_saved.csv")
        development = pd.read_csv(ROOT / "results/published/clean_development_saved.csv")
        self.assertEqual(len(annual), 21)
        for row in development.itertuples():
            count = annual.loc[(annual.feature_set == row.feature_set) & (annual.test_year < 2026), "trades"].sum()
            self.assertEqual(count, row.trades)


if __name__ == "__main__":
    unittest.main()

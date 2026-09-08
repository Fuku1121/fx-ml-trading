"""固定CSVを指定してHGB参照実装を実行し、設定と結果を保存する。

モデル・取引ルールは元セル58を保持する。入力検査とファイル保存は
今回追加した処理であり、保存済みの成績の再現を保証するものではない。
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import pandas as pd

from ..confidence import load_prices
from . import config
from .evaluation import evaluate_year
from .features import BASE_FEATURES, CHAMPION_FEATURES, prepare_dataset
from .trading import stats_of_returns


def run(csv_path, output_dir, years=None):
    """検査済みの入力で両候補を評価し、新しい出力フォルダへ保存する。"""
    csv_path, output_dir = Path(csv_path), Path(output_dir)
    bars = load_prices(csv_path)
    years = list(years) if years is not None else (
        config.DEVELOPMENT_YEARS + [config.CONFIRMATION_YEAR]
    )
    if not years or years != sorted(set(years)):
        raise ValueError("Evaluation years must be nonempty, unique and sorted.")
    output_dir.mkdir(parents=True, exist_ok=False)
    source_dir = Path(__file__).parent
    metadata = {
        "experiment": "hgb-cell58-reference",
        "status": "running",
        "years": years,
        "input_filename": csv_path.name,
        "input_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "input_rows": len(bars),
        "first_bar": str(bars.index.min()),
        "last_bar": str(bars.index.max()),
        "settings": {k: v for k, v in vars(config).items() if k.isupper()},
        "versions": {p: importlib.metadata.version(p)
                     for p in ("numpy", "pandas", "scikit-learn")},
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(source_dir.glob("*.py"))},
        "input_validator_sha256": hashlib.sha256(
            source_dir.parent.joinpath("confidence.py").read_bytes()
        ).hexdigest(),
        "units": "Decimal returns; win_rate is the fraction of net-positive trades.",
    }

    def save_metadata():
        (output_dir / "run.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

    save_metadata()
    annual, trade_tables, periods = [], [], []
    try:
        for name, features in (("BASE", BASE_FEATURES),
                               ("CHAMPION", CHAMPION_FEATURES)):
            data = prepare_dataset(bars, features)
            for year in years:
                print(f"{name}: evaluating {year}", flush=True)
                result = evaluate_year(data, features, year, name)
                periods.append({"feature_set": name, "test_year": year,
                                "status": "evaluated" if result else "insufficient_rows"})
                if result is not None:
                    row, trades = result
                    annual.append(row)
                    trade_tables.append(trades)

        annual_frame = pd.DataFrame(annual)
        trades = pd.concat(trade_tables) if trade_tables else pd.DataFrame()
        annual_frame.to_csv(output_dir / "annual.csv", index=False)
        trades.to_csv(output_dir / "trades.csv", index_label="signal_time")
        pd.DataFrame(periods).to_csv(output_dir / "period_status.csv", index=False)
        summaries = []
        for name in ("BASE", "CHAMPION"):
            selected = trades.loc[trades.feature_set == name] if not trades.empty else trades
            returns = selected.net_return if not selected.empty else []
            summaries.append({"feature_set": name, **stats_of_returns(returns)})
        summary = pd.DataFrame(summaries)
        summary.to_csv(output_dir / "summary.csv", index=False)
        metadata["status"] = "completed" if annual else "no_evaluable_years"
        metadata["summary_scope"] = "All requested years combined, including partial years."
        save_metadata()
        return summary
    except Exception as exc:
        metadata.update(status="failed", error_type=type(exc).__name__)
        save_metadata()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.csv, args.out).to_string(index=False))


if __name__ == "__main__":
    main()

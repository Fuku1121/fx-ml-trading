"""CSV-driven nested forward experiment. Never selects settings from outer Test."""

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .backtest import run_backtest
from .data import load_bars
from .labels import prepare_data
from .metrics import strategy_stats
from .models import fit_base_models, predict_base_models
from .quality import create_quality_oof_dataset, fit_quality_model, predict_quality
from .signals import make_signals
from .splits import outer_folds


def run_experiment(csv_path, output_dir):
    """Persist settings, every fold status, trades, score diagnostics and input hash.

    Model formulae/forest sizes retain the notebook baseline. Corrected accounting,
    stricter boundaries and fixed data input make this a new experiment version.
    """
    csv_path, output_dir = Path(csv_path), Path(output_dir)
    bars = load_bars(csv_path)
    data = prepare_data(bars)
    if len(data) < 600:
        raise ValueError(
            "Need at least 600 usable rows; this is only a technical minimum, not statistical sufficiency."
        )
    output_dir.mkdir(parents=True, exist_ok=False)
    versions = {
        name: importlib.metadata.version(name)
        for name in ["numpy", "pandas", "scikit-learn"]
    }
    source_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path(__file__).parent.glob("*.py")
    }
    metadata = {
        "status": "running",
        "experiment": "quality-v0.1-accounting-corrected",
        "input_filename": csv_path.name,
        "input_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "bar_rows": len(bars),
        "usable_rows": len(data),
        "first_bar": str(bars.index[0]),
        "last_bar": str(bars.index[-1]),
        "timezone": "Asia/Tokyo",
        "python": platform.python_version(),
        "versions": versions,
        "source_sha256": source_hashes,
        "config": {
            name: getattr(config, name) for name in dir(config) if name.isupper()
        },
        "notes": "No annualization. Closed-trade drawdown, no intratrade marking. Decimal return units.",
    }

    def save_metadata():
        (output_dir / "run.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

    save_metadata()
    rows, trade_frames, importance_frames, score_frames = [], [], [], []
    for fold in outer_folds(data):
        row = {
            "fold": fold.number,
            "status": "skipped",
            "reason": "",
            "train_rows": len(fold.train),
            "test_rows": len(fold.test),
            "test_start": str(fold.test.index[0]) if len(fold.test) else "",
            "test_end": str(fold.test.index[-1]) if len(fold.test) else "",
        }
        rows.append(row)
        print(f"Fold {fold.number}: preparing chronological training", flush=True)
        if len(fold.train) < 500 or not len(fold.test) or not len(fold.validation):
            row["reason"] = "insufficient_rows"
            continue
        oof = create_quality_oof_dataset(fold.core)
        quality = fit_quality_model(oof) if oof is not None else None
        base = fit_base_models(fold.core, trees=300)
        if quality is None or base is None:
            row["reason"] = "training_unavailable_or_one_class"
            continue
        probabilities = predict_base_models(base, fold.validation)
        quality_probabilities = predict_quality(
            quality, fold.validation, *probabilities
        )
        # Validation outcomes must be available before its boundary ends; original global df could look beyond it.
        val_end = fold.validation.index[-1] + pd.Timedelta(minutes=5)
        best, best_score = None, -np.inf
        for move, direction, tp, sl in itertools.product(
            config.MOVE_PROB_LIST,
            config.DIRECTION_PROB_LIST,
            config.TP_LIST,
            config.SL_LIST,
        ):
            signals = make_signals(*probabilities, move, direction)
            trades = run_backtest(
                bars, fold.validation, signals, tp, sl, end_time=val_end
            )
            if len(trades) < config.MIN_VALIDATION_TRADES:
                continue
            score = trades.net_return.mean() * np.sqrt(len(trades))
            if score > best_score:
                best_score, best = score, (move, direction, tp, sl)
        if best is None:
            row["reason"] = "no_base_setting_meets_min_validation_trades"
            continue
        move, direction, tp, sl = best
        best_quality, quality_score = None, -np.inf
        for threshold in config.QUALITY_PROB_LIST:
            signals = make_signals(
                *probabilities,
                move,
                direction,
                quality_prob=quality_probabilities,
                quality_t=threshold,
            )
            trades = run_backtest(
                bars, fold.validation, signals, tp, sl, end_time=val_end
            )
            if len(trades) < config.MIN_VALIDATION_TRADES:
                continue
            score = trades.net_return.mean() * np.sqrt(len(trades))
            if score > quality_score:
                quality_score, best_quality = score, threshold
        row["quality_filter_disabled"] = best_quality is None
        threshold = best_quality if best_quality is not None else 0.0
        row.update(
            move_threshold=move,
            direction_threshold=direction,
            tp=tp,
            sl=sl,
            quality_threshold=threshold,
        )
        final_oof = create_quality_oof_dataset(fold.train)
        final_quality = fit_quality_model(final_oof) if final_oof is not None else None
        final_base = fit_base_models(fold.train, trees=400)
        if final_quality is None or final_base is None:
            row["reason"] = "final_retraining_unavailable"
            continue
        test_probabilities = predict_base_models(final_base, fold.test)
        test_quality = predict_quality(final_quality, fold.test, *test_probabilities)
        test_end = fold.test.index[-1] + pd.Timedelta(minutes=5)
        score_frames.append(
            pd.DataFrame(
                {
                    "fold": fold.number,
                    "signal_time": fold.test.index,
                    "p_move": test_probabilities[0],
                    "p_up": test_probabilities[1],
                    "p_down": test_probabilities[2],
                    "p_quality": test_quality,
                }
            )
        )
        for strategy, q in [("BASE", None), ("QUALITY", test_quality)]:
            signals = make_signals(
                *test_probabilities,
                move,
                direction,
                quality_prob=q,
                quality_t=threshold,
            )
            trades = run_backtest(bars, fold.test, signals, tp, sl, end_time=test_end)
            row.update(
                {
                    f"{strategy.lower()}_{k}": v
                    for k, v in strategy_stats(trades.net_return).items()
                }
            )
            trades["strategy"], trades["fold"] = strategy, fold.number
            trade_frames.append(trades)
        model, names = final_quality
        importance_frames.append(
            pd.DataFrame(
                {
                    "fold": fold.number,
                    "feature": names,
                    "importance": model.feature_importances_,
                }
            )
        )
        row["status"], row["reason"] = "evaluated", ""
        print(
            f"Fold {fold.number}: BASE {row['base_trades']}, QUALITY {row['quality_trades']} trades",
            flush=True,
        )
    pd.DataFrame(rows).to_csv(output_dir / "folds.csv", index=False)
    trades = (
        pd.concat(trade_frames, ignore_index=True)
        if trade_frames
        else pd.DataFrame(
            columns=["strategy", "fold", "direction", "exit_time", "net_return"]
        )
    )
    trades.to_csv(output_dir / "trades.csv", index=False)
    summaries = []
    for strategy in ["BASE", "QUALITY"]:
        selected = trades.loc[trades.strategy == strategy].sort_values("exit_time")
        for side in ["ALL", "BUY", "SELL"]:
            subset = (
                selected if side == "ALL" else selected.loc[selected.direction == side]
            )
            summaries.append(
                {
                    "strategy": strategy,
                    "side": side,
                    **strategy_stats(subset.net_return),
                }
            )
    summary = pd.DataFrame(summaries)
    summary.to_csv(output_dir / "summary.csv", index=False)
    if importance_frames:
        pd.concat(importance_frames).to_csv(
            output_dir / "quality_importance.csv", index=False
        )
        pd.concat(score_frames).to_csv(output_dir / "test_scores.csv", index=False)
    metadata["status"] = "completed" if trade_frames else "no_evaluable_folds"
    metadata["evaluated_folds"] = sum(r["status"] == "evaluated" for r in rows)
    save_metadata()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="New output directory; existing paths are rejected.",
    )
    args = parser.parse_args()
    print(run_experiment(args.csv, args.out).to_string(index=False))


if __name__ == "__main__":
    main()

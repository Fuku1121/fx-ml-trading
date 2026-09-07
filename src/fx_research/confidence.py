"""Annual 15-minute Confidence research with label-availability boundaries.

Extracts the cell-35 model/threshold design; corrects timing and reporting.
Saved notebook results are not results of this corrected implementation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

from .confidence_features import FEATURES, make_features
from .metrics import strategy_stats


@dataclass(frozen=True)
class Settings:
    """Decimal cost and thresholds; keep these fixed before inspecting Test."""
    cost: float = 0.00004
    thresholds: tuple[float, ...] = (.50, .52, .54, .55, .56, .58, .60, .62, .65)
    trees: int = 250
    seed: int = 42
    min_train_years: int = 3
    min_train_rows: int = 5000
    min_eval_rows: int = 100
    min_validation_trades: int = 100

    def __post_init__(self):
        if not np.isfinite(self.cost) or self.cost < 0:
            raise ValueError('Cost must be finite and nonnegative.')
        if not self.thresholds or any(not .5 <= p <= 1 for p in self.thresholds):
            raise ValueError('Confidence thresholds must be in [0.5, 1].')
        if min(self.trees, self.min_train_years, self.min_train_rows,
               self.min_eval_rows, self.min_validation_trades) < 1:
            raise ValueError('Sample and tree counts must be positive.')


def load_prices(path):
    """Read original lowercase Dukascopy CSV; require explicit timestamp offsets."""
    frame = pd.read_csv(path, index_col=0)
    timestamps = pd.Series(frame.index.astype(str))
    if not timestamps.str.contains(r'(?:Z|[+-]\d{2}:?\d{2})$', regex=True).all():
        raise ValueError('Timestamps must include a UTC offset; no implicit timezone.')
    frame.index = pd.DatetimeIndex(pd.to_datetime(timestamps.to_numpy(), utc=True))
    columns = ['open', 'high', 'low', 'close']
    if not set(columns).issubset(frame.columns):
        raise ValueError(f'Expected lowercase OHLC columns: {columns}')
    frame = frame[columns].apply(pd.to_numeric, errors='raise')
    if frame.empty or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError('Input must be nonempty, unique and chronological.')
    if not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
        raise ValueError('Prices must be finite and positive.')
    if (frame.high < frame[['open', 'close', 'low']].max(axis=1)).any() or (frame.low > frame[['open', 'close', 'high']].min(axis=1)).any():
        raise ValueError('Inconsistent OHLC.')
    if ((frame.index.minute % 15 != 0) | (frame.index.second != 0) |
        (frame.index.microsecond != 0) | (frame.index.nanosecond != 0)).any():
        raise ValueError('Expected timestamps on a 15-minute grid.')
    return frame


def prepare_prices(bars):
    """Label availability is the CLOSE time of t+2, not its opening timestamp."""
    frame = make_features(bars).replace([np.inf, -np.inf], np.nan)
    times = pd.Series(bars.index, index=bars.index)
    frame['entry_time'] = times.shift(-1)
    frame['label_end'] = times.shift(-2) + pd.Timedelta(minutes=15)
    frame['entry_price'] = bars.open.shift(-1)
    frame['exit_price'] = bars.close.shift(-2)
    frame['future_return'] = frame.exit_price / frame.entry_price - 1
    frame['target'] = (frame.future_return > 0).astype(int)
    continuous = (times.shift(-1) - times).eq(pd.Timedelta(minutes=15)) & (times.shift(-2) - times).eq(pd.Timedelta(minutes=30))
    return frame.loc[continuous].dropna(subset=FEATURES + ['future_return', 'label_end']).copy()


def annual_splits(data, settings):
    """Purge outcomes unavailable at the start of the next year in UTC."""
    years = sorted(data.index.year.unique())
    for year in years:
        val_year = year - 1
        if len([y for y in years if y < val_year]) < settings.min_train_years or val_year not in years:
            continue
        val_start = pd.Timestamp(year=val_year, month=1, day=1, tz='UTC')
        test_start = pd.Timestamp(year=year, month=1, day=1, tz='UTC')
        test_end = pd.Timestamp(year=year+1, month=1, day=1, tz='UTC')
        train = data.loc[(data.index < val_start) & (data.label_end <= val_start)]
        validation = data.loc[(data.index >= val_start) & (data.index < test_start) & (data.label_end <= test_start)]
        final_train = data.loc[(data.index < test_start) & (data.label_end <= test_start)]
        test = data.loc[(data.index >= test_start) & (data.index < test_end) & (data.label_end <= test_end)]
        yield year, train, validation, final_train, test


def build_model(settings):
    return RandomForestClassifier(n_estimators=settings.trees, max_depth=8,
        min_samples_leaf=30, max_features='sqrt', class_weight='balanced',
        random_state=settings.seed, n_jobs=-1)


def predict(model, frame):
    classes = list(model.classes_)
    if classes != [0, 1]:
        raise ValueError('Both classes are required.')
    p_up = model.predict_proba(frame[FEATURES])[:, classes.index(1)]
    result = frame[['entry_time', 'label_end', 'entry_price', 'exit_price', 'future_return']].copy()
    result['p_up'] = p_up
    result['confidence'] = np.maximum(p_up, 1-p_up)
    result['direction_correct'] = (p_up >= .5) == (frame.future_return > 0)
    result['direction'] = np.where(p_up >= .5, 'BUY', 'SELL')
    result['gross_return'] = frame.future_return * np.where(p_up >= .5, 1, -1)
    return result


def select_trades(predictions, threshold, cost):
    """One position at a time, verified using actual entry/exit times."""
    candidates = predictions.loc[predictions.confidence >= threshold].sort_index()
    selected, next_entry = [], None
    for row in candidates.itertuples():
        if next_entry is not None and row.entry_time < next_entry:
            continue
        selected.append(row.Index)
        next_entry = row.label_end
    trades = candidates.loc[selected].copy()
    trades['net_return'] = trades.gross_return - cost
    trades['cost'] = cost
    trades.index.name = 'signal_time'
    return trades


def choose_threshold(predictions, settings):
    rows, best, best_score = [], None, -np.inf
    for threshold in settings.thresholds:
        trades = select_trades(predictions, threshold, settings.cost)
        stats = strategy_stats(trades.net_return)
        eligible = len(trades) >= settings.min_validation_trades
        score = stats['avg_return'] * np.sqrt(len(trades)) if eligible else np.nan
        rows.append({'threshold': threshold, 'eligible': eligible, 'score': score, **stats})
        # Preserve the original research choice even if every eligible score is negative.
        if eligible and score > best_score:
            best, best_score = threshold, score
    return best, pd.DataFrame(rows)


def run(csv_path, output_dir, settings=None):
    settings = settings or Settings()
    csv_path, output_dir = Path(csv_path), Path(output_dir)
    bars = load_prices(csv_path)
    data = prepare_prices(bars)
    if data.empty:
        raise ValueError('No usable observations after feature/label validation.')
    output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {'experiment': 'confidence-15m-v0.2-purged', 'status': 'running',
        'settings': asdict(settings), 'input_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        'input_filename': csv_path.name, 'first_bar': str(bars.index.min()), 'last_bar': str(bars.index.max()),
        'input_rows': len(bars), 'usable_rows': len(data), 'python': platform.python_version(),
        'versions': {p: importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn']},
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__), Path(__file__).with_name('confidence_features.py'), Path(__file__).with_name('metrics.py')]},
        'notes': 'Decimal returns; corrected implementation, not reproduction of imported metrics. Bid-based proxy plus constant round-trip cost.'}
    def save_meta():
        (output_dir/'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    save_meta()
    annual, validation_tables, trade_tables = [], [], []
    try:
        for year, train, val, final_train, test in annual_splits(data, settings):
            row = {'test_year': int(year), 'validation_year': int(year-1), 'status': 'skipped',
                'reason': '', 'train_rows': len(train), 'validation_rows': len(val), 'test_rows': len(test),
                'test_first_signal': str(test.index.min()), 'test_last_signal': str(test.index.max())}
            annual.append(row)
            print(f'Annual test {year}: train={len(train)}, validation={len(val)}, test={len(test)}', flush=True)
            if min(len(train), len(final_train)) < settings.min_train_rows or min(len(val), len(test)) < settings.min_eval_rows:
                row['reason'] = 'insufficient_rows'
                continue
            if train.target.nunique() < 2 or final_train.target.nunique() < 2:
                row['reason'] = 'single_training_class'
                continue
            model = build_model(settings).fit(train[FEATURES], train.target)
            threshold, table = choose_threshold(predict(model, val), settings)
            table['test_year'] = year
            validation_tables.append(table)
            if threshold is None:
                row['reason'] = 'no_threshold_meets_validation_count'
                continue
            final_model = build_model(settings).fit(final_train[FEATURES], final_train.target)
            predictions = predict(final_model, test)
            selected = select_trades(predictions, threshold, settings.cost)
            selected['test_year'] = year
            selected['threshold'] = threshold
            trade_tables.append(selected)
            stats = strategy_stats(selected.net_return)
            stats['net_win_rate'] = stats.pop('win_rate')
            row.update(status='evaluated', threshold=threshold,
                test_auc=roc_auc_score(test.target, predictions.p_up) if test.target.nunique()==2 else np.nan,
                direction_accuracy=selected.direction_correct.mean(), **stats)
            print(f'  threshold={threshold:.2f}, trades={len(selected)}, PF={stats["profit_factor"]:.4f}', flush=True)
        annual_frame = pd.DataFrame(annual, columns=list(dict.fromkeys(
            ['test_year','validation_year','status','reason'] + [k for r in annual for k in r])))
        annual_frame.to_csv(output_dir/'annual.csv',index=False)
        trades = pd.concat(trade_tables) if trade_tables else pd.DataFrame(columns=['net_return','gross_return','direction','direction_correct'])
        trades.to_csv(output_dir/'trades.csv',index_label='signal_time')
        search = pd.concat(validation_tables) if validation_tables else pd.DataFrame(columns=['test_year','threshold','eligible'])
        search.to_csv(output_dir/'validation_search.csv',index=False)
        summaries=[]
        for side in ['ALL','BUY','SELL']:
            subset = trades if side=='ALL' else trades.loc[trades.direction==side]
            stats = strategy_stats(subset.net_return)
            stats['net_win_rate'] = stats.pop('win_rate')
            summaries.append({'side':side,'direction_accuracy':subset.direction_correct.mean(),**stats})
        summary = pd.DataFrame(summaries)
        summary.to_csv(output_dir/'summary.csv',index=False)
        metadata['status'] = 'completed' if trade_tables else 'no_evaluable_years'
        metadata['evaluated_years'] = sum(r['status']=='evaluated' for r in annual)
        save_meta()
        return summary
    except Exception as exc:
        metadata.update(status='failed', error_type=type(exc).__name__)
        save_meta()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(run(args.csv, args.out).to_string(index=False))


if __name__ == '__main__':
    main()

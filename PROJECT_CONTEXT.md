# Project context — current handoff

USD/JPY 5-minute ML research, 6-bar holding horizon, RandomForest MOVE → Direction → Quality.
The supplied handoff is preserved in [docs/PROJECT_CONTEXT.original.md](docs/PROJECT_CONTEXT.original.md).

## Correction based on the supplied notebook

Trade Quality was already executed in FX.ipynb cell index 15. Saved results show BASE 404 trades,
average net return −0.003214%, PF 0.897677; QUALITY 275 trades, −0.003666%, PF 0.884695.
This does not support an improved aggregate expectancy. It is historical, unrerun evidence.
See [the research report](docs/RESEARCH.md) and [audit](docs/AUDIT.md).

## Current implementation

Historical source is archived without rewriting experiments. The current CSV-driven package
extracts the latest feature/model/Quality logic and explicitly corrects documented accounting
and evaluation-boundary issues. New results must not be described as reproducing old metrics.
The original market-data snapshot and environment lock are unavailable.

## Next work

1. Obtain an immutable, timezone-aware OHLC snapshot and record its provenance.
2. Run the corrected BASE / QUALITY experiment with fixed configuration.
3. Diagnose Quality score vs realized return and fold/side stability before changing labels.
4. Evaluate a fresh future holdout; repeated research has already inspected historical tests.

Preserve chronological validation, forward-only OOF and negative findings. Explain substantial
Python changes to the learner. No live trading, leverage optimization or cloud deployment yet.

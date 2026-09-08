# 2026-09-09 — HGB research update

- Import 23 additional code cells as archive stages17–27, retaining failed experiments and sanitized saved outputs.
- Explain Session, Exit, Calibration, Sizing, Risk Engine, Model and Feature comparisons.
- Publish latest HGB BASE30 / expanded50 tables with provenance; flag mixed-frequency resampling, repeated holdout inspection and outlier years.
- Add a results-reading notebook and preserve the previous RF overview.
- Existing executable model modules are unchanged; HGB remains a research prototype.

# Changelog

## 0.2.0 — Annual Confidence research

- Imported FX (1).ipynb research history with source hashes and saved outputs.
- Rewrote the reviewer-facing overview around 15-minute Confidence and annual nested validation.
- Added a corrected CSV-driven annual runner, label-availability purges and explicit metric names.
- Published an annual chart/table from saved output, clearly distinct from corrected results.
- Preserved 5-minute Quality experiments and negative findings.


## 0.1.0 — Repository organization

- Split original experiment cells into seven historical notebooks without changing cell source.
- Preserved saved text results with source-cell hashes; removed embedded images, rich HTML and execution metadata.
- Corrected the handoff: Quality had run and did not improve aggregate saved expectancy.
- Extracted current features, feature sets, RandomForest models and forward OOF Quality code.
- Added explicit CSV input, reproducibility metadata, fold status and trade-level output.
- Corrected SELL accounting, initial drawdown, evaluation cutoffs, gap-stop handling and raw-position lockout.
- Added tests and a GitHub Actions configuration. No real-data rerun or live deployment is claimed.

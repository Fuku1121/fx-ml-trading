# Changelog

## 0.1.0 — Repository organization

- Split original experiment cells into seven historical notebooks without changing cell source.
- Preserved saved text results with source-cell hashes; removed embedded images, rich HTML and execution metadata.
- Corrected the handoff: Quality had run and did not improve aggregate saved expectancy.
- Extracted current features, feature sets, RandomForest models and forward OOF Quality code.
- Added explicit CSV input, reproducibility metadata, fold status and trade-level output.
- Corrected SELL accounting, initial drawdown, evaluation cutoffs, gap-stop handling and raw-position lockout.
- Added tests and a GitHub Actions configuration. No real-data rerun or live deployment is claimed.

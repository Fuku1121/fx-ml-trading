# FX (3): clean-data validation and paper-system evidence

## 2026-09-17

- READMEを更新し、研究・過去再現・仮想運転の成績を分離。
- 9月12〜17日の品質監査、モデル比較、複数通貨と72候補探索を整理。
- 仮想売買コード、資金シナリオ、オフラインテスト、専用CIを追加。
- EC2での履歴準備開始と未設定の運用項目を記録。実注文なし。


- Preserve31 additional cells as archive stages28–36, including failed attempts.
- Supersede contaminated-data headline metrics with clean-yearly-data comparisons.
- Document the41-feature freeze,418-point prefix parity,300-trade historical replay and API-armed/zero-processed state.
- Extract pure current feature calculations for review; preserve previous reference implementations as historical.
- Add result tables, a non-executing contract snapshot, a reading notebook and current system guide.

# Readability and reference-code update

- Rewrite the overview for nontechnical readers; add a research introduction and glossary.
- Replace conflicting current/previous navigation with a single code guide.
- Extract the latest HGB calculations into configuration, features, calibration, trading and evaluation modules; preserve original function bodies computationally.
- Add explicit CSV execution and tracked result output, plus six HGB regression/integration checks.
- Keep original notebooks and published financial metrics unchanged.

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

# Project context — 2026-09-09

Purpose: explain USD/JPY ML research clearly to technical and recruiting readers, with traceable results and honest limitations.

- Latest supplied source: FX (2).ipynb, 60 cells; cells0–35 unchanged, new code36–58, empty59.
- Latest research: HGB / calibration / threshold-session / sizing / 30-minute exit. Compare BASE30 versus expanded50 features.
- Latest imported output: cell58, 266,510 resampled rows. BASE development PF2.949785 versus expanded2.017441. These are not independently rerun or audited performance.
- Mixed bar frequencies were detected in cells51/56. Cell57 resampling does not itself prove complete or consistent source bars.
- Priorities: raw-data provenance and 2022/2025 outlier-trade audit, matched-sample feature comparison, untouched future evaluation.
- 2026 has been repeatedly inspected; do not describe it as an untouched holdout.
- HGB reference functions now live in src/fx_research/hgb/ with an explicit CSV runner. Tests check source-AST equivalence and synthetic execution. Real-market rerun and production execution remain unverified.
- Read docs/RESEARCH_20260909.md and docs/HGB_METHODOLOGY.md; latest code is notebooks/archive/27_hgb_reintegration.ipynb.
- 27 archive stages; imported logs and hashes preserve errors and rejected experiments.
- GitHub is private. Do not change visibility or publish raw data, personal paths, account details or chat history without authorization.
- No broker execution or live trading is implemented.

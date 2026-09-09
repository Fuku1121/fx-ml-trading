# Current project context — FX (3)

- Latest source: FX (3).ipynb. Original cells0–58 unchanged; new59–89; empty90.
- Data contamination was investigated. Yearly15m-only rebuild:265,905 rows. Old cell58 PF2.950 is superseded, not current evidence.
- Clean tournament cell67: BASE30 vs BASE_PLUS_REGIME41 vs BASE_PLUS_VOL_REGIME54. Selected41-feature candidate; definitions differ from old50-feature experiment.
- Frozen version: champion_v1_base_plus_regime_20260909. Isotonic, threshold.58, ALL, STRONG, sizing scale1.7451299836342953,30-minute hold, no overlap.
- Reference entry nextOpen, exit previous-barClose at exit boundary; net=size*(gross-.00004).
- Saved cell83 historical replay300 trades, gross/net diff0. This is imported evidence, not independently rerun here.
- Saved cell89 Twelve Data connection fetched100/closed99, historical sent0, processed0, ARMED_WAITING_FOR_NEXT_BAR. No claim of forward performance or current ongoing operation.
- Actual model/calibrator/manifest/canonical CSV/runtime states were not supplied with notebook. Do not start background loops or API requests as part of repository organization.
- Keep frozen logic intact. Read docs/RESEARCH_FX3.md and docs/FROZEN_SYSTEM.md.
- Pure current feature reference: src/fx_research/frozen/. Previous cell58 reference: src/fx_research/hgb/.
- Repository private. No credentials, model binaries, live states or raw market data in Git.

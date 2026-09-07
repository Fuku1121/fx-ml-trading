# Current project context — September 2026

Current research: USD/JPY 15-minute BID prices, 30-minute hold, RandomForest direction prediction with Confidence selection.
Source: FX (1).ipynb cells 0–35. The newest saved experiment is cell 35 (annual nested selection).
It differs from the older 5-minute MOVE → Direction → Quality architecture, which remains historical.

Saved data: 265,905 rows, 2016-01-03 through 2026-09-01 UTC. Source CSV not included in the notebook.
Saved aggregate: 4,153 trades, net mean 0.0054519338%, PF 1.23789594, closed-trade max DD −3.04590698%.
All seven evaluation periods reported net mean >0 and PF>1; 2026 is partial.
These are imported outputs, not independently rerun or verified corrected results.

Current code: fx_research.confidence. It extracts the feature/model/threshold baseline and fixes label availability
at annual boundaries, discontinuous 30-minute paths, input validation and misleading Accuracy naming.
It has no MOVE, Quality, time decay, TP/SL, variable sizing or live execution.

Next: fixed-data replay of corrected code; side/session/year decomposition; time-dependent uncertainty;
realistic costs and a new untouched holdout. Do not promote recorded PF as a verified live edge.
Explain substantial Python changes to the learner and retain failed experiments.

Read README.md, docs/RESEARCH.md, docs/METHODOLOGY.md, docs/CONFIDENCE_AUDIT.md and docs/REPRODUCIBILITY.md.
Older handoff: docs/PROJECT_CONTEXT.original.md. Older Quality baseline: docs/QUALITY_BASELINE.md.

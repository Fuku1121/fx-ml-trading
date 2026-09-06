# PROJECT_CONTEXT.md

# USD/JPY Machine-Learning Trading Research --- Project Context

## 1. Project purpose

This repository researches short-horizon USD/JPY FX trading with Python
and machine learning.

The goal is **not** to claim that the current strategy is profitable.
The goal is to build a rigorous research pipeline that:

1.  generates trading hypotheses,
2.  tests them without look-ahead bias or data leakage,
3.  evaluates economic performance after costs,
4.  rejects approaches that fail out-of-sample,
5.  improves trade selection iteratively,
6.  later supports real-time signals and, only after sufficient
    validation, possible automated execution.

Current architecture:

``` text
USD/JPY 5-minute bars
        ↓
MOVE model
"Is a meaningful move likely over ~30 minutes?"
        ↓
Direction model
"If it moves, is UP or DOWN more likely?"
        ↓
Trade Quality model
"Is this individual candidate trade likely to have positive net return?"
        ↓
BUY / SELL / WAIT
```

## 2. Current baseline

-   Instrument: USD/JPY
-   Interval: 5-minute bars
-   Primary horizon: 30 minutes = 6 bars
-   60-minute horizon has also been tested
-   Main environment so far: Python + Jupyter Notebook
-   Main ML family so far: RandomForestClassifier
-   Entry convention: signal at `t`, enter at `Open(t+1)`
-   30-minute final time exit: `Close(t+6)`
-   Current emphasis: robust out-of-sample economic expectancy, not
    prediction accuracy alone

## 3. Development rule

The user is learning Python while building the system.

Whenever implementing or substantially modifying code:

-   explain each major block,
-   explain important new lines/concepts,
-   explain why the implementation is structured that way,
-   identify potential leakage or backtest bias,
-   avoid unexplained large code dumps when explanation is practical.

The user should be able to explain the project themselves, not merely
run copied code.

------------------------------------------------------------------------

# 4. Research history and decisions

## Stage 1 --- Direction-only prediction

The first approach predicted whether USD/JPY would be higher or lower
after a short horizon.

Approximate early performance:

-   Accuracy: \~52--53%
-   ROC-AUC: \~0.56

Overall predictive power was weak, although high-confidence predictions
sometimes had materially better directional accuracy.

### Decision

Do not trade every prediction. Investigate selective trading based on
model confidence.

------------------------------------------------------------------------

## Stage 2 --- MOVE + Direction decomposition

The task was split into two models.

### MOVE model

Estimate:

``` text
P(significant movement over the forecast horizon)
```

### Direction model

Estimate:

``` text
P(UP)
P(DOWN)
```

At one stage, MOVE classification reached approximately:

``` text
ROC-AUC ≈ 0.77
```

### Conclusion

Predicting whether a meaningful move occurs appeared easier than
predicting its direction.

The two-stage architecture became the baseline.

------------------------------------------------------------------------

## Stage 3 --- Walk-Forward validation

Simple train/test splits sometimes produced apparently strong win rates
and Profit Factors. These were not considered reliable.

Chronological Walk-Forward validation was introduced:

``` text
past → train
next future → test
advance through time
larger past → retrain
next future → test
```

Directional AUC varied substantially by fold. Approximate observed
examples included:

``` text
0.44, 0.65, 0.46, 0.66, 0.54
```

### Conclusion

Performance is regime-dependent and unstable across time.

USD/JPY should be treated as a non-stationary process. One profitable
period is not evidence of a persistent edge.

------------------------------------------------------------------------

## Stage 4 --- Regime analysis

Variables/conditions investigated included:

-   volatility
-   ATR
-   ADX
-   moving-average slope
-   trend vs range
-   high vs low volatility
-   Tokyo / London / New York sessions

At one stage approximate differences such as these appeared:

``` text
TREND AUC ≈ 0.63
RANGE AUC ≈ 0.52

HIGH VOL AUC ≈ 0.62
LOW VOL AUC ≈ 0.53
```

Later fold-level analysis showed that some high-volatility /
strong-trend periods still performed poorly.

### Conclusion

A simple rule such as:

``` text
high volatility + trend = good trade
```

is insufficient.

Regime information may be useful, but it is not a complete solution.

------------------------------------------------------------------------

## Stage 5 --- Time-decay weighting

Because market structure changes, recent observations were given greater
importance.

Approximate weighting:

``` text
weight = 0.5 ** (age_days / 20)
```

Interpretation:

``` text
current data → ~1.00
20 days old → ~0.50
40 days old → ~0.25
```

### Purpose

Keep older information while allowing the model to respond more strongly
to recent conditions.

------------------------------------------------------------------------

## Stage 6 --- Validation-based parameter selection

Early probability thresholds were manually fixed, e.g.:

``` text
MOVE >= 0.65
Direction >= 0.60
```

This was replaced by:

``` text
Train
  ↓
Validation
select probability thresholds / TP / SL
  ↓
Test
unseen evaluation only
```

### Critical rule

The Test set must never determine:

-   probability thresholds,
-   TP/SL,
-   features,
-   regime rules,
-   Quality threshold,
-   model hyperparameters.

A temporal gap equal to the forecast horizon should be maintained at
boundaries when required to prevent labels from crossing into the next
partition.

------------------------------------------------------------------------

## Stage 7 --- Shift from accuracy to economic expectancy

Some folds had relatively high win rates while average return was
negative.

Therefore:

``` text
high win rate ≠ profitable strategy
```

Primary evaluation shifted toward:

-   number of trades
-   average net return/trade
-   Profit Factor
-   average win/loss
-   payoff ratio
-   maximum drawdown
-   fold stability
-   BUY/SELL breakdown
-   MFE/MAE
-   equity curve

Central objective:

``` text
E[net return] > 0
```

after realistic costs.

------------------------------------------------------------------------

## Stage 8 --- MFE / MAE diagnosis

MFE = Maximum Favorable Excursion.

MAE = Maximum Adverse Excursion.

One analysis produced approximately:

### Winning trades

-   Average MFE: +0.066%
-   Average MAE: -0.026%

### Losing trades

-   Average MFE: +0.015%
-   Average MAE: -0.065%

### Interpretation

Many losing trades were not good trades ruined only by exit timing. They
tended to move very little in the predicted direction and then move
materially against the position.

### Conclusion

Entry/candidate quality is a major problem.

This result motivated the Trade Quality model.

------------------------------------------------------------------------

## Stage 9 --- 30-minute vs 60-minute horizon

A timing-definition inconsistency was identified and corrected.

Current intended convention:

``` text
signal = bar t
entry = Open(t+1)

30-minute horizon:
evaluate t+1 through t+6
time exit = Close(t+6)
```

Corrected comparison produced approximately:

  Metric                  30 min      60 min
  ------------------ ----------- -----------
  Trades                     101          83
  Win rate                60.40%      59.04%
  Avg return/trade     +0.00625%   +0.00678%
  Profit Factor            1.391       1.363
  Avg MFE               +0.0485%    +0.0605%
  Avg MAE               -0.0368%    -0.0609%
  Max DD                \~-0.55%    \~-0.46%

### Decision

30 minutes remains the primary horizon because it produced more
opportunities with substantially smaller adverse excursion and similar
expectancy.

Do not treat this as proof that 30 minutes is globally optimal.

------------------------------------------------------------------------

## Stage 10 --- Important caution about the earlier +0.006% result

An average return near:

``` text
+0.006% per trade
```

appeared in earlier tests with roughly 84--101 trades.

Later, stricter testing with more trades changed the sign of the result.

### Rule

Do **not** use +0.006% as an assumed stable future expectancy for
leverage/compound-growth projections.

It is an unstable historical experimental result, not an established
edge.

------------------------------------------------------------------------

## Stage 11 --- Formal Regime Filter

A Regime Filter was built using:

-   volatility quantiles
-   ADX
-   absolute MA50 slope

A larger test produced approximately:

### BASE

``` text
Trades:             354
Win rate:           53.67%
Average return:    -0.00179% / trade
Profit Factor:      0.931
Maximum drawdown:  -1.08%
Cumulative growth: ~-0.64%
```

### REGIME FILTER

``` text
Trades:             299
Win rate:           54.18%
Average return:    -0.00146% / trade
Profit Factor:      0.945
Maximum drawdown:  -0.96%
Cumulative growth: ~-0.44%
```

### Conclusion

Regime filtering slightly improved several metrics but did not create
positive expectancy:

``` text
average return < 0
Profit Factor < 1
```

Some folds improved substantially while others did not.

### Decision

Do not keep adding RSI/MACD/Bollinger/regime rules merely until the
backtest becomes positive. That would increase data-snooping/overfitting
risk.

Regime filtering is a completed useful experiment, but not the primary
current direction.

------------------------------------------------------------------------

# 5. Current research direction --- Trade Quality AI

Current hypothesis:

> Instead of classifying the entire market as good/bad, directly
> estimate whether each candidate trade is worth taking.

Architecture:

``` text
MOVE model
    ↓
Direction model
    ↓
candidate BUY/SELL
    ↓
Trade Quality model
    ↓
low quality → WAIT
high quality → TRADE
```

Target:

``` text
P(candidate trade has positive net return)
```

Candidate Quality features include:

-   p_move
-   p_up
-   p_down
-   `abs(p_up - p_down)` direction confidence
-   predicted direction
-   5m/15m/30m/1h/2h returns
-   volatility
-   ATR
-   ADX
-   RSI
-   MA distance
-   MA slope
-   distance from recent high/low
-   candle body/range/wicks
-   time-of-day cyclic features
-   weekday

------------------------------------------------------------------------

# 6. Critical Quality-model leakage rule

Never train Quality AI from Base-model predictions made on the same
observations used to train the Base model.

Bad:

``` text
train Base on A
predict A
use predictions on A to train Quality
```

Preferred:

``` text
past A → train Base
future B → generate forward/OOF predictions

past A+B → train Base
future C → generate forward/OOF predictions

combine B, C, ...
        ↓
train Quality
```

The Quality model should learn how the Base models behave on **unseen
observations**.

The final Outer Test must remain untouched until all choices for that
fold are fixed.

------------------------------------------------------------------------

# 7. Current Quality target

Initial target:

``` text
predicted-direction return - trading cost > 0
    → Quality = 1
otherwise
    → Quality = 0
```

A future explicit experiment may compare this with MFE/MAE-based labels.

Do not silently redefine the target. Alternative label definitions must
be treated as separate experiments.

------------------------------------------------------------------------

# 8. Current model family

Main model:

``` text
RandomForestClassifier
```

Typical settings/concepts:

-   balanced class weights
-   bounded tree depth
-   minimum leaf size
-   sqrt feature sampling
-   hundreds of trees
-   time-decay sample weights

Do not switch to XGBoost, LightGBM, neural networks, etc. merely to
improve apparent backtest performance.

Only increase model complexity after the evaluation pipeline is stable
and the baseline is well understood.

------------------------------------------------------------------------

# 9. Backtesting invariants

Unless an experiment explicitly changes one:

## Entry

``` text
signal at t
entry at Open(t+1)
```

Never enter at the same Close used to calculate the signal.

## Primary holding horizon

``` text
6 × 5-minute bars = 30 minutes
```

## TP/SL

TP/SL choices must come from Validation, not Test.

If TP and SL are both touched inside the same 5-minute OHLC bar and
intrabar ordering is unknowable:

``` text
assume SL occurred first
```

This is deliberately conservative.

## Costs

Recent code used a provisional approximation:

``` text
TRADING_COST ≈ 0.0000133
```

This is not yet a broker-accurate live cost.

Before live use, model:

-   spread,
-   session-dependent spread,
-   slippage,
-   execution latency,
-   fill/rejection behavior where relevant.

## Overlapping positions

Recent backtests generally ignore new signals while the existing
30-minute position is open.

Keep this rule explicit.

------------------------------------------------------------------------

# 10. Leakage checklist

Before trusting any result, verify:

-   features at `t` use only information available by `t`,
-   entry occurs after signal generation,
-   future labels never appear in features,
-   rolling windows are not centered,
-   Train precedes Validation,
-   Validation precedes Test,
-   Test never determines parameters,
-   Quality uses forward/OOF Base predictions,
-   horizon gaps protect temporal boundaries,
-   global future-dependent preprocessing is absent,
-   any future scaler/encoder is fit only on training data.

If any condition fails, treat the affected result as invalid.

------------------------------------------------------------------------

# 11. Current Quality experiment evaluation

Compare on identical unseen Test periods:

``` text
BASE
vs
QUALITY FILTER
```

Measure:

-   trade count
-   win rate
-   average net return/trade
-   Profit Factor
-   maximum drawdown
-   fold-by-fold return
-   BUY/SELL performance
-   equity curve

A Quality model should not be accepted merely because it reduces
hundreds of trades to a tiny handful with high apparent return.

It needs enough trades to evaluate and should improve multiple folds,
not only one lucky period.

------------------------------------------------------------------------

# 12. Sample-size philosophy

Approximate interpretation:

``` text
<100 OOS trades:
hypothesis only

~300–500:
useful diagnostic evidence

500–1000+:
more serious evaluation territory

1000+ across distinct regimes:
preferable
```

Sample size alone is insufficient. Stability across time/regimes
matters.

------------------------------------------------------------------------

# 13. Immediate next experiment

Complete and evaluate Trade Quality AI with nested chronological
validation.

Required workflow:

``` text
OUTER TRAIN
    │
    ├─ internal forward/OOF Base predictions
    │        ↓
    │   Quality training dataset
    │        ↓
    │   train Quality model
    │
    └─ Validation
             ├─ choose Base thresholds
             ├─ choose TP/SL
             └─ choose Quality threshold

then

retrain only from permitted historical data
             ↓
completely unseen OUTER TEST
             ↓
BASE vs QUALITY
```

After running it, answer:

1.  Did Quality improve average net return?
2.  Did PF exceed 1?
3.  Did drawdown improve?
4.  How many trades remain?
5.  Did multiple folds improve?
6.  Which Quality features dominate?
7.  Are those relationships economically plausible?
8.  Does improvement survive stricter costs?

------------------------------------------------------------------------

# 14. If Trade Quality succeeds

Proceed in this order:

1.  **Longer historical/OOS dataset**
    -   target at least 500--1000+ OOS trades.
2.  **Robustness testing**
    -   probability thresholds,
    -   TP/SL,
    -   holding horizon,
    -   cost assumptions,
    -   time-decay half-life,
    -   random seeds,
    -   training-window length.
3.  **Cost stress test**
    -   baseline cost,
    -   1.5×,
    -   2×,
    -   session-dependent spread if possible.
4.  **Stability analysis**
    -   month/quarter/year,
    -   session,
    -   volatility regime,
    -   trend/range,
    -   BUY vs SELL.

A real edge should not exist only at one exact parameter combination.

------------------------------------------------------------------------

# 15. If Trade Quality fails

Do not tune until it becomes profitable.

Diagnose:

-   Is Quality probability monotonic with realized return?
-   Does higher Quality probability improve win rate?
-   Are Quality labels too noisy?
-   Would MFE/MAE-based labels be more meaningful?
-   Is Direction prediction too weak?
-   Is MOVE useful while direction remains effectively unpredictable?
-   Are costs larger than the exploitable signal?

Possible future pivots:

-   expected-return regression/ranking,
-   candidate-trade ranking instead of binary Quality,
-   direct MFE/MAE prediction,
-   separate BUY/SELL models,
-   dynamic holding horizon,
-   abandon the strategy if no robust edge survives.

Failure is a valid research result.

------------------------------------------------------------------------

# 16. What not to do now

Do not immediately:

-   switch to 1-minute bars just for more samples,
-   add dozens of indicators,
-   add many more regime filters,
-   optimize against Test,
-   maximize R²,
-   combine Train and Test,
-   tune until profitability appears,
-   use leverage to rescue negative expectancy,
-   build live execution before robustness testing,
-   claim a profitable FX AI from current evidence.

R² is not the primary objective for the present classification/trading
architecture.

------------------------------------------------------------------------

# 17. Risk management comes after edge validation

The user has discussed 3×, 5× and 25× leverage.

These are later risk-management scenarios, not ways to convert negative
expectancy into positive expectancy.

After robust unlevered edge validation, investigate:

-   fixed-fraction sizing,
-   volatility-based sizing,
-   risk per trade,
-   daily loss limits,
-   maximum-DD stop,
-   consecutive-loss safeguards,
-   leverage caps,
-   broker margin/forced-liquidation rules.

------------------------------------------------------------------------

# 18. Real-time system --- later phase

After robust validation:

``` text
market data
    ↓
feature calculation
    ↓
MOVE
    ↓
Direction
    ↓
Quality
    ↓
risk manager
    ↓
signal
    ↓
phone notification
```

The first deployment should preferably be **signal-only/manual
execution**.

Only later consider broker API automated execution.

------------------------------------------------------------------------

# 19. Cloud deployment --- later phase

The user does not want a personal PC running continuously.

Potential later deployment:

-   cloud VM,
-   scheduled/cloud service,
-   containerized process.

Required operational controls:

-   restart recovery,
-   logging,
-   exception handling,
-   stale-data detection,
-   duplicate-order prevention,
-   secret management,
-   monitoring,
-   kill switch.

Never commit API keys, credentials, account data, or secrets to GitHub.

------------------------------------------------------------------------

# 20. Intended repository structure

``` text
fx-ml-trading/
├── PROJECT_CONTEXT.md
├── README.md
├── requirements.txt
├── .gitignore
│
├── src/
│   ├── data.py
│   ├── features.py
│   ├── labels.py
│   ├── models.py
│   ├── quality.py
│   ├── backtest.py
│   ├── metrics.py
│   └── risk.py
│
├── notebooks/
│   ├── 01_direction_baseline.ipynb
│   ├── 02_move_direction.ipynb
│   ├── 03_walk_forward.ipynb
│   ├── 04_regime_analysis.ipynb
│   ├── 05_mfe_mae.ipynb
│   ├── 06_horizon_comparison.ipynb
│   └── 07_trade_quality.ipynb
│
├── results/
│   ├── figures/
│   └── tables/
│
└── tests/
    ├── test_features.py
    ├── test_splits.py
    └── test_backtest.py
```

Notebooks = exploration/explanation.

`src/` = reusable research code.

------------------------------------------------------------------------

# 21. Important tests

The backtester is more important than model sophistication.

Tests should verify:

### Timing

``` text
signal t
entry t+1 Open
exit t+6 Close
```

### No future feature usage

Feature values at `t` should not depend on rows after `t`.

### Split gap

Training labels near a boundary must not use Validation/Test prices.

### TP/SL

Synthetic OHLC sequences should produce known expected returns.

### Same-bar TP and SL

Conservative SL-first behavior must be verified.

### Costs

Costs must be deducted exactly according to the chosen cost definition.

### Non-overlap

If the experiment assumes one position at a time, new entries must be
suppressed during an open 30-minute position.

------------------------------------------------------------------------

# 22. GitHub presentation philosophy

Do not hide failed experiments.

The research story is:

``` text
direction-only model
        ↓
weak overall predictability
        ↓
MOVE + Direction decomposition
        ↓
promising results
        ↓
Walk-Forward reveals instability
        ↓
regime hypothesis
        ↓
Regime Filter gives only limited improvement
        ↓
MFE/MAE reveals entry-quality problem
        ↓
Trade Quality hypothesis
        ↓
nested OOS evaluation
```

This demonstrates:

-   Python,
-   machine learning,
-   time-series methodology,
-   backtesting,
-   leakage awareness,
-   hypothesis testing,
-   risk awareness,
-   debugging,
-   willingness to reject weak results.

Do not market it as:

``` text
"AI that beats FX"
```

Prefer:

``` text
Machine Learning Research for Short-Horizon USD/JPY Trading
```

------------------------------------------------------------------------

# 23. Reproducibility requirements

Eventually document:

-   Python version,
-   dependencies,
-   random seeds,
-   data source,
-   data acquisition,
-   preprocessing,
-   timezone handling,
-   experiment configuration,
-   result tables,
-   timing/backtest tests.

Do not redistribute data if licensing does not permit it.

------------------------------------------------------------------------

# 24. Current conceptual progress

Informal project-management estimate:

``` text
research logic:              ~40%
statistical reliability:     still early
real-time infrastructure:    ~0–5%
automated execution/safety:  ~0%
overall complete system:     ~20–25%
```

This is not a mathematical measurement.

The project is beyond a toy model, but far from a validated live trading
system.

------------------------------------------------------------------------

# 25. Central research question

The project began with:

``` text
Can AI predict whether USD/JPY goes up or down?
```

It has evolved into:

``` text
Can we identify a sufficiently large set of candidate trades
whose out-of-sample net expected return is positive and robust
to changing market regimes and realistic transaction costs?
```

The goal is not high accuracy or high win rate by itself.

The goal is:

``` text
robust positive out-of-sample expectancy
after realistic costs,
with acceptable drawdown
and enough independent trades.
```

------------------------------------------------------------------------

# 26. Instructions for Codex

Before making architectural changes:

1.  Read this entire file.
2.  Preserve strict chronological validation.
3.  Never optimize against final Test data.
4.  Identify possible leakage before implementing experiments.
5.  Keep the 30-minute model as the current baseline unless evidence
    justifies changing it.
6.  Treat Regime Filter as a completed limited-benefit experiment.
7.  Prioritize Trade Quality AI now.
8.  Keep experiments reproducible.
9.  Separate notebooks from reusable `src/` modules.
10. Add tests for timing/backtesting logic before live deployment.
11. Explain major code sections and new Python concepts to the user.
12. Never interpret a profitable backtest as proof of future
    profitability.
13. Do not use leverage as a substitute for predictive edge.
14. Preserve negative/failed experiments.
15. Prefer simple defensible baselines over unnecessary complexity.
16. When a result changes the research conclusion, update this file.

------------------------------------------------------------------------

# 27. Immediate handoff state

At handoff:

-   USD/JPY 5-minute research is active.
-   30-minute horizon is the current baseline.
-   MOVE + Direction architecture exists.
-   Walk-Forward testing exists.
-   time-decay weighting exists.
-   Validation-based threshold selection exists.
-   TP/SL simulation exists.
-   MFE/MAE analysis exists.
-   30m vs 60m comparison has been performed.
-   Regime Filter was tested and provided only limited improvement.
-   The larger Regime test remained negative expectancy.
-   Trade Quality AI is the next major experiment.
-   A Quality implementation using forward/OOF Base predictions has been
    drafted.
-   Next task: run/verify Quality AI, inspect BASE vs QUALITY results,
    and decide whether the hypothesis survives out-of-sample testing.

**Do not skip directly to leverage optimization, cloud deployment, or
live trading.**

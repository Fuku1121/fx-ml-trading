# Verification record

## 2026-09-07: current 15-minute Confidence implementation

- Python 3.13.9 / Windows; numpy 2.4.4, pandas 3.0.3, scikit-learn 1.9.0.
- 30 unittest cases passed: 23 existing checks plus 7 new Confidence checks.
- New checks cover future-independent features, year-boundary label availability, missing-bar exclusion, actual non-overlap, costs, validation selection, CSV validation, and a synthetic annual Random Forest run.
- Synthetic data confirms execution and output contracts, not market performance.
- Saved outputs and original/archived code hashes are recorded in `results/imported_20260907/provenance.json`.
- The real-price 250-tree annual study has not been rerun. Published performance is imported from the supplied notebook and predates the boundary corrections.
- Current CI status will be available in GitHub Actions after publication.

## Previous 5-minute baseline checks

## Local checks

- Python 3.12.14 / Windows; exact core dependencies are in `requirements-verified.txt`.
- 23 unittest cases passed, including a synthetic end-to-end run with eight-tree forests and a reduced parameter grid.
- Synthetic integration verifies execution and output contracts; it does not evaluate the financial hypothesis.
- Historical code-cell SHA-256 values were checked against all 16 archived nonempty code cells.
- Source syntax compilation and Ruff F-rule checks passed. Current package/tests were formatted with Ruff.
- Markdown file links and notebook JSON structure were checked locally.

## GitHub Actions

- [Research checks run #1](https://github.com/Fuku1121/fx-ml-trading/actions/runs/34033128798) passed on Python 3.11 and 3.12 (Ubuntu).
- Both jobs completed package installation, unit tests and syntax compilation successfully.
- Verified source commit: `d0ac041ee7fb1e326596c1a5970838bf33d91e76`.

## Not yet verified

- The original market-data snapshot was not supplied. Full historical performance has not been reproduced.
- The default 180/300/400-tree research run was not executed against real prices.
- Jupyter UI execution has not been observed.
- Dependency ranges are supported installation targets, not a claim that every version was tested.

The original notebook and context file in Downloads were not modified.

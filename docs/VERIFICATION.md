# Verification record

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

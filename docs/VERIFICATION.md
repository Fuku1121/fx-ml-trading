# Verification record

## Local checks

- Python 3.12.14 / Windows; exact core dependencies are in `requirements-verified.txt`.
- 23 unittest cases passed, including a synthetic end-to-end run with eight-tree forests and a reduced parameter grid.
- Synthetic integration verifies execution and output contracts; it does not evaluate the financial hypothesis.
- Historical code-cell SHA-256 values were checked against all 16 archived nonempty code cells.
- Source syntax compilation and Ruff F-rule checks passed. Current package/tests were formatted with Ruff.
- Markdown file links and notebook JSON structure were checked locally.

## Not yet verified

- The original market-data snapshot was not supplied. Full historical performance has not been reproduced.
- The default 180/300/400-tree research run was not executed against real prices.
- Jupyter UI execution and GitHub Actions execution have not been observed.
- Dependency ranges are supported installation targets, not a claim that every version was tested.

The original notebook and context file in Downloads were not modified.

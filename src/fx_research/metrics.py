"""Trade-level, unlevered diagnostics; drawdown includes initial equity of 1."""

import numpy as np


def strategy_stats(returns):
    r = np.asarray(returns, dtype=float)
    if not np.isfinite(r).all() or (r <= -1).any():
        raise ValueError("Returns must be finite and greater than -100%.")
    if not len(r):
        return dict(
            trades=0,
            win_rate=np.nan,
            avg_return=np.nan,
            profit_factor=np.nan,
            max_dd=np.nan,
            total_growth=0.0,
        )
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = gains / losses if losses else (np.inf if gains else np.nan)
    equity = np.r_[1.0, np.cumprod(1 + r)]
    drawdown = equity / np.maximum.accumulate(equity) - 1
    return dict(
        trades=len(r),
        win_rate=float((r > 0).mean()),
        avg_return=float(r.mean()),
        profit_factor=float(pf),
        max_dd=float(drawdown.min()),
        total_growth=float(equity[-1] - 1),
    )

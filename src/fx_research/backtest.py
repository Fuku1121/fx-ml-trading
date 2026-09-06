"""OHLC simulation with fixed entry-notional returns and six-bar signal lockout.

Changes from the historical notebook are documented in docs/AUDIT.md.
The caller supplies prices explicitly; no mutable global DataFrame is used.
"""

import numpy as np
import pandas as pd

from .config import HORIZON_BARS, TRADING_COST


def simulate_trade(
    bars, signal_time, direction, tp, sl, *, end_time=None, cost=TRADING_COST
):
    if direction not in ("BUY", "SELL"):
        raise ValueError("direction must be BUY or SELL")
    if not (
        np.isfinite([tp, sl, cost]).all() and 0 < tp < 1 and 0 < sl < 1 and cost >= 0
    ):
        raise ValueError(
            "Require 0 < TP/SL < 1 and finite nonnegative round-trip cost."
        )
    signal_loc = bars.index.get_loc(signal_time)
    final_loc = signal_loc + HORIZON_BARS
    if final_loc >= len(bars):
        return None
    final_time = bars.index[final_loc] + pd.Timedelta(minutes=5)
    if end_time is not None and final_time > end_time:
        return None
    if bars.index[final_loc] - bars.index[signal_loc] != pd.Timedelta(
        minutes=5 * HORIZON_BARS
    ):
        return None
    side = 1 if direction == "BUY" else -1
    entry = float(bars.iloc[signal_loc + 1].Open)
    exit_loc, exit_price, reason = final_loc, float(bars.iloc[final_loc].Close), "TIME"
    for loc in range(signal_loc + 1, final_loc + 1):
        bar = bars.iloc[loc]
        open_return = side * (float(bar.Open) / entry - 1)
        # An opening gap through a stop fills at the worse opening price.
        if open_return <= -sl:
            exit_loc, exit_price, reason = loc, float(bar.Open), "GAP_SL"
            break
        # Profit-taking at the limit price; do not grant favorable gap improvement.
        if open_return >= tp:
            exit_loc, exit_price, reason = loc, entry * (1 + side * tp), "TP"
            break
        favorable = side * (float(bar.High if side == 1 else bar.Low) / entry - 1)
        adverse = side * (float(bar.Low if side == 1 else bar.High) / entry - 1)
        if adverse <= -sl:
            exit_loc, exit_price, reason = loc, entry * (1 - side * sl), "SL"
            break
        if favorable >= tp:
            exit_loc, exit_price, reason = loc, entry * (1 + side * tp), "TP"
            break
    gross = side * (exit_price / entry - 1)
    # Bar-resolution bookkeeping time, not a claim about tick-level execution time.
    exit_time = bars.index[exit_loc] + pd.Timedelta(minutes=5)
    return {
        "signal_time": signal_time,
        "entry_time": bars.index[signal_loc + 1],
        "exit_time": exit_time,
        "direction": direction,
        "entry_price": entry,
        "exit_price": exit_price,
        "exit_reason": reason,
        "gross_return": gross,
        "cost": cost,
        "net_return": gross - cost,
        "signal_position": signal_loc,
    }


def run_backtest(bars, frame, signals, tp, sl, *, end_time=None, cost=TRADING_COST):
    if len(frame) != len(signals) or not np.isin(signals, [-1, 0, 1]).all():
        raise ValueError("Signals must align one-to-one with frame and be -1, 0 or 1.")
    records = []
    next_signal_position = -1
    for time, signal in zip(frame.index, signals):
        position = bars.index.get_loc(time)
        if signal == 0 or position < next_signal_position:
            continue
        trade = simulate_trade(
            bars,
            time,
            "BUY" if signal == 1 else "SELL",
            tp,
            sl,
            end_time=end_time,
            cost=cost,
        )
        if trade is not None:
            records.append(trade)
            # Even an early TP/SL retains the historical fixed-horizon lockout.
            next_signal_position = position + HORIZON_BARS
    columns = [
        "signal_time",
        "entry_time",
        "exit_time",
        "direction",
        "entry_price",
        "exit_price",
        "exit_reason",
        "gross_return",
        "cost",
        "net_return",
        "signal_position",
    ]
    return pd.DataFrame.from_records(records, columns=columns)

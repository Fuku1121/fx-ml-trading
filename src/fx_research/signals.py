"""Threshold-based BUY=1 / SELL=-1 / WAIT=0 selection."""

import numpy as np


def make_signals(
    p_move, p_up, p_down, move_t, direction_t, quality_prob=None, quality_t=None
):
    buy = (p_move >= move_t) & (p_up >= direction_t) & (p_up > p_down)
    sell = (p_move >= move_t) & (p_down >= direction_t) & (p_down > p_up)
    if quality_prob is not None and quality_t is not None:
        quality_mask = quality_prob >= quality_t
        buy = buy & quality_mask
        sell = sell & quality_mask
    signals = np.zeros(len(p_move))
    signals[buy] = 1
    signals[sell] = -1
    return signals

"""Forward outcomes kept separate from model feature allowlists."""

import numpy as np
import pandas as pd

from .config import HORIZON_BARS, MOVE_THRESHOLD
from .feature_sets import move_features, direction_features, quality_market_features
from .features import make_features


def prepare_data(bars):
    """Build labels on original bar positions before dropping unavailable features.

    Timestamp convention: each input index denotes the bar's opening time.
    A label uses Open(t+1) through Close(t+6), available at index[t+6]+5min.
    Price-path gaps across the horizon are excluded, never filled.
    """
    frame = make_features(bars)
    frame["bar_position"] = np.arange(len(bars))
    frame["entry_price"] = bars.Open.shift(-1)
    frame["exit_price"] = bars.Close.shift(-HORIZON_BARS)
    frame["future_return"] = frame.exit_price / frame.entry_price - 1
    times = pd.Series(bars.index, index=bars.index)
    frame["label_end"] = times.shift(-HORIZON_BARS) + pd.Timedelta(minutes=5)
    complete = (times.shift(-HORIZON_BARS) - times).eq(
        pd.Timedelta(minutes=5 * HORIZON_BARS)
    )
    frame["move_target"] = frame.future_return.abs().gt(MOVE_THRESHOLD).astype(int)
    frame["direction_target"] = frame.future_return.gt(0).astype(int)
    required = list(
        dict.fromkeys(move_features + direction_features + quality_market_features)
    )
    required += ["future_return", "entry_price", "exit_price", "label_end"]
    return frame.loc[complete].dropna(subset=required).copy()

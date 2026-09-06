"""Local, immutable OHLC input; no network requests on import or execution."""

from pathlib import Path

import numpy as np
import pandas as pd


def load_bars(path: str | Path) -> pd.DataFrame:
    """Read bar-open timestamps with explicit offsets and normalize to Japan time."""
    frame = pd.read_csv(path)
    required = ["timestamp", "Open", "High", "Low", "Close"]
    if not set(required).issubset(frame.columns):
        raise ValueError(f"CSV must contain {required}")
    timestamps = frame.pop("timestamp").astype(str)
    if not timestamps.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).all():
        raise ValueError(
            "Every timestamp must include Z or a UTC offset; naive times are ambiguous."
        )
    frame.index = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True)).tz_convert(
        "Asia/Tokyo"
    )
    frame = frame[["Open", "High", "Low", "Close"]].apply(pd.to_numeric, errors="raise")
    if (
        frame.empty
        or not frame.index.is_monotonic_increasing
        or not frame.index.is_unique
    ):
        raise ValueError(
            "Bars must be nonempty, strictly chronological and unique; input is not silently sorted."
        )
    if not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
        raise ValueError("OHLC must be finite and positive.")
    if (frame.High < frame[["Open", "Close", "Low"]].max(axis=1)).any():
        raise ValueError("High is inconsistent with OHLC.")
    if (frame.Low > frame[["Open", "Close", "High"]].min(axis=1)).any():
        raise ValueError("Low is inconsistent with OHLC.")
    if (
        (frame.index.minute % 5 != 0)
        | (frame.index.second != 0)
        | (frame.index.microsecond != 0)
        | (frame.index.nanosecond != 0)
    ).any():
        raise ValueError("Bar timestamps must align to a five-minute grid.")
    return frame

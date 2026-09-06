"""Expanding chronological folds with explicit horizon purges."""

from dataclasses import dataclass

import pandas as pd

from .config import HORIZON_BARS, OUTER_SPLITS


@dataclass(frozen=True)
class Fold:
    number: int
    train: pd.DataFrame
    core: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def outer_folds(data):
    block = len(data) // (OUTER_SPLITS + 1)
    if block < 1:
        return
    for number in range(1, OUTER_SPLITS + 1):
        train_end = block * number
        test_start = train_end + HORIZON_BARS
        test_end = min(test_start + block, len(data))
        train = data.iloc[:train_end]
        cut = int(len(train) * 0.8)
        core = train.iloc[: max(0, cut - HORIZON_BARS)]
        validation = train.iloc[cut:]
        test = data.iloc[test_start:test_end]
        # Bar-open cutoffs are deliberately conservative: all outcomes are known before the next block.
        if len(validation) and len(core):
            if not (core.label_end <= validation.index[0]).all():
                raise ValueError("Training label crosses validation boundary.")
        if len(test) and len(train):
            if not (train.label_end <= test.index[0]).all():
                raise ValueError("Training label crosses test boundary.")
        yield Fold(number, train, core, validation, test)

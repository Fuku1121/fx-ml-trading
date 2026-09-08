"""前年の設定選択と翌年の評価を結び付ける。最初にevaluate_yearを読む。

出典: FX (2).ipynb セル58。計算式は原実験を保持。
"""

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .config import MIN_TRAIN_ROWS, MIN_EVAL_ROWS
from .calibration import (choose_calibration, expanding_oof, fit_calibrator,
                          fit_hgb, raw_probability)
from .trading import (prediction_frame, choose_threshold_session, select_trades,
                      choose_sizing, apply_sizing, stats_of_returns)

def make_split(data, test_year):
    """評価年の前年を設定選択に使い、各年境界で未確定ラベルを除外する。"""
    validation_year = test_year - 1
    val_start = pd.Timestamp(f'{validation_year}-01-01', tz='UTC')
    test_start = pd.Timestamp(f'{test_year}-01-01', tz='UTC')
    test_end = pd.Timestamp(f'{test_year + 1}-01-01', tz='UTC')
    train = data.loc[(data.index < val_start) & (data['label_end'] <= val_start)].copy()
    validation = data.loc[
        (data.index >= val_start)
        &
        (data.index < test_start)
        &
        (data["label_end"] <= test_start)
    ].copy()
    final_train = data.loc[
        (data.index < test_start)
        &
        (data["label_end"] <= test_start)
    ].copy()
    test = data.loc[
        (data.index >= test_start)
        &
        (data.index < test_end)
        &
        (data["label_end"] <= test_end)
    ].copy()
    if (
        len(train) < MIN_TRAIN_ROWS
        or len(validation) < MIN_EVAL_ROWS
        or len(test) < MIN_EVAL_ROWS
    ):
        return None
    return {
        "test_year": test_year,
        "validation_year": validation_year,
        "train": train,
        "validation": validation,
        "final_train": final_train,
        "test": test,
    }


def evaluate_year(data, features, test_year, feature_name):
    """過去で選択、再学習、翌年評価の順に実行し、年別集計と取引を返す。"""
    split = make_split(data, test_year)
    if split is None:
        return None
    train = split["train"]
    validation = split["validation"]
    final_train = split["final_train"]
    test = split["test"]
    # --------------------------------
    # Calibration selection
    # --------------------------------
    calibration, raw_val = choose_calibration(train, validation, features)
    train_oof = expanding_oof(train, features)
    val_calibrator = fit_calibrator(calibration, train_oof)
    p_val = np.clip(val_calibrator.predict(raw_val), 0, 1)
    val_pred = prediction_frame(validation, p_val)
    # --------------------------------
    # Threshold / Session
    # --------------------------------
    threshold, session, _ = choose_threshold_session(val_pred)
    val_selected = select_trades(val_pred, threshold, session)
    # --------------------------------
    # Position sizing
    # --------------------------------
    sizing_policy, scale = choose_sizing(val_selected, threshold)
    # --------------------------------
    # Test前に全historyで再fit
    # --------------------------------
    final_oof = expanding_oof(final_train, features)
    final_calibrator = fit_calibrator(calibration, final_oof)
    final_model = fit_hgb(final_train, features)
    raw_test = raw_probability(final_model, test, features)
    p_test = np.clip(final_calibrator.predict(raw_test), 0, 1)
    test_pred = prediction_frame(test, p_test)
    selected = select_trades(test_pred, threshold, session)
    final_trades = apply_sizing(
        selected,
        threshold,
        sizing_policy,
        scale,
        cost_multiplier=1.0
    )
    s = stats_of_returns(final_trades['net_return'])
    if test["target"].nunique() == 2:
        auc = roc_auc_score(test['target'], p_test)
    else:
        auc = np.nan
    result = {
        "feature_set": feature_name,
        "test_year": test_year,
        "validation_year": test_year - 1,
        "calibration": calibration,
        "threshold": threshold,
        "session": session,
        "sizing_policy": sizing_policy,
        "auc": auc,
        **s
    }
    final_trades = final_trades.copy()
    final_trades['feature_set'] = feature_name
    final_trades['test_year'] = test_year
    return (result, final_trades)

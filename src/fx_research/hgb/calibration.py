"""過去だけでモデルと確率の補正器を学習する。

出典: FX (2).ipynb セル58。計算式は原実験を保持。
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

from .config import RANDOM_STATE, HGB_CONFIG, MIN_TRAIN_ROWS, MIN_EVAL_ROWS, CALIBRATION_METHODS

def fit_hgb(data, features):
    """固定設定のHGBを指定した特徴列と過去の正解で学習する。"""
    model = HistGradientBoostingClassifier(**HGB_CONFIG)
    model.fit(data[features], data['target'])
    return model


def raw_probability(model, data, features):
    """学習済みモデルから上昇クラスの未校正確率を取り出す。"""
    return model.predict_proba(data[features])[:, 1]


class RawCalibrator:
    """校正を行わず、そのままの予測値を返す。"""
    def fit(self, p, y):
        return self
    def predict(self, p):
        return np.asarray(p)


class PlattCalibrator:
    """ロジスティック回帰で予測確率の偏りを補正する。"""
    def __init__(self):
        self.model = LogisticRegression(solver='lbfgs', random_state=RANDOM_STATE)
    def fit(self, p, y):
        self.model.fit(np.asarray(p).reshape(-1, 1), y)
        return self
    def predict(self, p):
        return self.model.predict_proba(np.asarray(p).reshape(-1, 1))[:, 1]


class IsotonicCalibrator:
    """単調な変換を学習して予測確率の偏りを補正する。"""
    def __init__(self):
        self.model = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
    def fit(self, p, y):
        self.model.fit(np.asarray(p), y)
        return self
    def predict(self, p):
        return np.asarray(self.model.predict(np.asarray(p)))


def expanding_oof(train, features):
    """各年を、その年より前の履歴で学習したモデルだけで予測する。"""
    years = sorted(train.index.year.unique())
    parts = []
    for y in years:
        prior = [yy for yy in years if yy < y]
        if len(prior) < 2:
            continue
        start = pd.Timestamp(f'{y}-01-01', tz='UTC')
        end = pd.Timestamp(f'{y + 1}-01-01', tz='UTC')
        hist = train.loc[(train.index < start) & (train['label_end'] <= start)]
        oof = train.loc[
            (train.index >= start)
            &
            (train.index < end)
            &
            (train["label_end"] <= end)
        ]
        if (
            len(hist) < MIN_TRAIN_ROWS
            or len(oof) < MIN_EVAL_ROWS
        ):
            continue
        if hist["target"].nunique() < 2:
            continue
        model = fit_hgb(hist, features)
        p = raw_probability(model, oof, features)
        parts.append(
            pd.DataFrame(
                {
                    "prob": p,
                    "target": oof["target"].values
                },
                index=oof.index
            )
        )
    if not parts:
        return pd.DataFrame(columns=['prob', 'target'])
    return pd.concat(parts).sort_index()


def fit_calibrator(method, oof):
    """過去のOOF予測から校正器を作る。件数不足時のRAW復帰も原仕様。"""
    if (
        method == "RAW"
        or len(oof) < 500
    ):
        return RawCalibrator()
    p = oof["prob"].values
    y = oof["target"].values
    if method == "PLATT":
        return PlattCalibrator().fit(p, y)
    if method == "ISOTONIC":
        if len(oof) < 1000:
            return RawCalibrator()
        return IsotonicCalibrator().fit(p, y)
    return RawCalibrator()


def choose_calibration(train, validation, features):
    """前年のBrier scoreを比較し、校正方式と未校正予測を返す。"""
    oof = expanding_oof(train, features)
    model = fit_hgb(train, features)
    raw_val = raw_probability(model, validation, features)
    rows = []
    for method in CALIBRATION_METHODS:
        cal = fit_calibrator(method, oof)
        p = np.clip(cal.predict(raw_val), 0, 1)
        brier = brier_score_loss(validation['target'], p)
        rows.append({'method': method, 'brier': brier})
    table = pd.DataFrame(rows).sort_values(['brier', 'method'])
    chosen = table.iloc[0]["method"]
    return chosen, raw_val

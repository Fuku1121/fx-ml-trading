"""元セル67の特徴量を抽出した参照実装。計算式と特徴順を維持する。

正規の全履歴を入力する。任意のtail(N)へ短縮すると符号特徴が変わり得る。
モデル・校正器・API・発注機能はこのモジュールに含まない。
"""

import numpy as np
import pandas as pd
from .base_features import make_base_features

FORMAL_BASE_FEATURES = [
    "return_1",
    "return_2",
    "return_4",
    "return_8",
    "return_16",
    "vol_4",
    "vol_8",
    "vol_16",
    "vol_32",
    "ma5_distance",
    "ma5_slope",
    "ma10_distance",
    "ma10_slope",
    "ma20_distance",
    "ma20_slope",
    "ma50_distance",
    "ma50_slope",
    "ma100_distance",
    "ma100_slope",
    "body",
    "upper_wick",
    "lower_wick",
    "range_pct",
    "rsi14",
    "atr14",
    "distance_high_16",
    "distance_low_16",
    "hour_sin",
    "hour_cos",
    "weekday",
]


REGIME_FEATURES = [
    "adx14",
    "adx28",
    "ma20_50_spread",
    "ma50_100_spread",
    "trend_strength_20",
    "trend_strength_50",
    "price_pos_20",
    "price_pos_50",
    "ma_alignment_score",
    "slope_alignment_score",
    "directional_persistence_16",
]


VOLATILITY_FEATURES = [
    "vol_64",
    "vol_96",
    "vol_ratio_4_32",
    "vol_ratio_8_32",
    "vol_ratio_16_64",
    "range_mean_8",
    "range_mean_32",
    "range_ratio_8_32",
    "range_z_20",
    "range_z_50",
    "abs_return_z_32",
    "abs_return_z_96",
    "gap_abs_1",
]


FEATURE_SETS = {
    "BASE":
        FORMAL_BASE_FEATURES,
    "BASE_PLUS_REGIME":
        FORMAL_BASE_FEATURES
        +
        REGIME_FEATURES,
    "BASE_PLUS_VOL_REGIME":
        FORMAL_BASE_FEATURES
        +
        VOLATILITY_FEATURES
        +
        REGIME_FEATURES,
}


def tournament_true_range(x):
    previous_close = x['close'].shift(1)
    return pd.concat(
        [
            x["high"]
            -
            x["low"],
            (
                x["high"]
                -
                previous_close
            ).abs(),
            (
                x["low"]
                -
                previous_close
            ).abs(),
        ],
        axis=1
    ).max(
        axis=1
    )


def tournament_calc_adx(
    x,
    period=14
):
    high = x['high']
    low = x['low']
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where(
            (
                up_move
                >
                down_move
            )
            &
            (
                up_move
                >
                0
            ),
            up_move,
            0.0
        ),
        index=x.index
    )
    minus_dm = pd.Series(
        np.where(
            (
                down_move
                >
                up_move
            )
            &
            (
                down_move
                >
                0
            ),
            down_move,
            0.0
        ),
        index=x.index
    )
    tr = tournament_true_range(x)
    tr_sum = tr.rolling(period).sum().replace(0, np.nan)
    plus_di = 100.0 * plus_dm.rolling(period).sum() / tr_sum
    minus_di = 100.0 * minus_dm.rolling(period).sum() / tr_sum
    denominator = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denominator
    return dx.rolling(period).mean() / 100.0


def tournament_rolling_z(
    series,
    window
):
    mean = series.rolling(window).mean()
    std = series.rolling(window).std().replace(0, np.nan)
    return (series - mean) / std


def make_final_tournament_features(
    bars_input
):
    raw = bars_input.copy()
    # --------------------------------------------------------
    # Exact CLEAN BASE features
    # --------------------------------------------------------
    base = make_base_features(bars_input)
    x = raw.copy()
    for feature in FORMAL_BASE_FEATURES:
        if feature not in base.columns:
            raise RuntimeError(f'BASE feature missing: {feature}')
        x[feature] = base[feature]
    eps = 1e-12
    # ========================================================
    # VOLATILITY 13
    # ========================================================
    x['vol_64'] = x['return_1'].rolling(64).std()
    x['vol_96'] = x['return_1'].rolling(96).std()
    x['vol_ratio_4_32'] = x['vol_4'] / (x['vol_32'].abs() + eps)
    x['vol_ratio_8_32'] = x['vol_8'] / (x['vol_32'].abs() + eps)
    x['vol_ratio_16_64'] = x['vol_16'] / (x['vol_64'].abs() + eps)
    x['range_mean_8'] = x['range_pct'].rolling(8).mean()
    x['range_mean_32'] = x['range_pct'].rolling(32).mean()
    x['range_ratio_8_32'] = x['range_mean_8'] / (x['range_mean_32'].abs() + eps)
    x['range_z_20'] = tournament_rolling_z(x['range_pct'], 20)
    x['range_z_50'] = tournament_rolling_z(x['range_pct'], 50)
    abs_return = x['return_1'].abs()
    x['abs_return_z_32'] = tournament_rolling_z(abs_return, 32)
    x['abs_return_z_96'] = tournament_rolling_z(abs_return, 96)
    x['gap_abs_1'] = (x['open'] / x['close'].shift(1) - 1).abs()
    # ========================================================
    # REGIME 11
    # ========================================================
    x['adx14'] = tournament_calc_adx(x, 14)
    x['adx28'] = tournament_calc_adx(x, 28)
    ma20 = x['close'].rolling(20).mean()
    ma50 = x['close'].rolling(50).mean()
    ma100 = x['close'].rolling(100).mean()
    x['ma20_50_spread'] = ma20 / ma50 - 1
    x['ma50_100_spread'] = ma50 / ma100 - 1
    true_range = tournament_true_range(x)
    atr14_absolute = true_range.rolling(14).mean()
    atr_safe = atr14_absolute.replace(0, np.nan)
    x['trend_strength_20'] = (x['close'] - ma20).abs() / atr_safe
    x['trend_strength_50'] = (x['close'] - ma50).abs() / atr_safe
    high20 = x['high'].rolling(20).max()
    low20 = x['low'].rolling(20).min()
    high50 = x['high'].rolling(50).max()
    low50 = x['low'].rolling(50).min()
    x['price_pos_20'] = (x['close'] - low20) / (high20 - low20).replace(0, np.nan) - 0.5
    x['price_pos_50'] = (x['close'] - low50) / (high50 - low50).replace(0, np.nan) - 0.5
    x[
        "ma_alignment_score"
    ] = (
        (
            ma20
            >
            ma50
        ).astype(
            float
        )
        +
        (
            ma50
            >
            ma100
        ).astype(
            float
        )
    ) / 2.0
    slope20 = ma20.pct_change()
    slope50 = ma50.pct_change()
    slope100 = ma100.pct_change()
    x[
        "slope_alignment_score"
    ] = (
        np.sign(
            slope20
        )
        +
        np.sign(
            slope50
        )
        +
        np.sign(
            slope100
        )
    ) / 3.0
    sign_return = np.sign(x['return_1'])
    x['directional_persistence_16'] = sign_return.rolling(16).mean().abs()
    return x.replace([np.inf, -np.inf], np.nan)

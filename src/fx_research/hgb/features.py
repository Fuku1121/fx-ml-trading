"""価格から説明変数と正解ラベルを作る。

出典: FX (2).ipynb セル58。計算式は原実験を保持。
"""

import numpy as np
import pandas as pd

BASE_FEATURES = [
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


REGIME_ADDITIONS = [
    "adx14",
    "plus_di14",
    "minus_di14",
    "ma20_vs_ma50",
    "ma50_vs_ma100",
    "trend_strength_20",
    "trend_strength_50",
    "breakout_pos_32",
    "range_position_64",
    "vol_ratio_8_32",
    "atr_ratio_7_28",
]


VOLATILITY_ADDITIONS = [
    "vol_2",
    "vol_6",
    "vol_12",
    "vol_24",
    "atr7",
    "atr28",
    "range_mean_4",
    "range_mean_16",
    "range_std_16",
    # Regimeと共通
    "vol_ratio_8_32",
    "atr_ratio_7_28",
    "breakout_pos_32",
    "trend_strength_20",
]


CHAMPION_FEATURES = list(
    dict.fromkeys(
        BASE_FEATURES
        + REGIME_ADDITIONS
        + VOLATILITY_ADDITIONS
    )
)


def calc_rsi(close, period=14):
    """過去の上昇幅・下落幅からRSIを計算する。原実験の欠損処理を保持する。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def make_all_features(b):
    """確定済みの価格と時刻から特徴量を作る。将来の正解ラベルは含めない。"""
    x = b.copy()
    # ------------------------
    # Returns
    # ------------------------
    for n in [1, 2, 4, 8, 16]:
        x[f"return_{n}"] = x["close"].pct_change(n)
    # ------------------------
    # BASE volatility
    # ------------------------
    for n in [4, 8, 16, 32]:
        x[f"vol_{n}"] = x["return_1"].rolling(n).std()
    # Champion volatility
    for n in [2, 6, 12, 24]:
        x[f"vol_{n}"] = x["return_1"].rolling(n).std()
    # ------------------------
    # Moving averages
    # ------------------------
    ma = {}
    for p in [5, 10, 20, 50, 100]:
        ma[p] = x["close"].rolling(p).mean()
        x[f'ma{p}_distance'] = x['close'] / ma[p] - 1
        x[f'ma{p}_slope'] = ma[p].pct_change()
    # ------------------------
    # Candle
    # ------------------------
    candle_range = (x['high'] - x['low']).replace(0, np.nan)
    x['body'] = (x['close'] - x['open']) / candle_range
    x['upper_wick'] = (x['high'] - x[['open', 'close']].max(axis=1)) / candle_range
    x['lower_wick'] = (x[['open', 'close']].min(axis=1) - x['low']) / candle_range
    x['range_pct'] = (x['high'] - x['low']) / x['close']
    # ------------------------
    # RSI
    # ------------------------
    x['rsi14'] = calc_rsi(x['close'], 14) / 100.0
    # ------------------------
    # True Range
    # ------------------------
    prev_close = x["close"].shift(1)
    tr = pd.concat(
        [
            x["high"] - x["low"],
            (x["high"] - prev_close).abs(),
            (x["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14_abs = tr.rolling(14).mean()
    x['atr14'] = atr14_abs / x['close']
    # extra ATR
    atr7_abs = tr.rolling(7).mean()
    atr28_abs = tr.rolling(28).mean()
    x['atr7'] = atr7_abs / x['close']
    x['atr28'] = atr28_abs / x['close']
    x['atr_ratio_7_28'] = atr7_abs / atr28_abs.replace(0, np.nan)
    # ------------------------
    # Recent high / low
    # ------------------------
    high16 = x["high"].rolling(16).max()
    low16 = x["low"].rolling(16).min()
    x['distance_high_16'] = (high16 - x['close']) / x['close']
    x['distance_low_16'] = (x['close'] - low16) / x['close']
    # ------------------------
    # Time
    # ------------------------
    hour = x.index.hour + x.index.minute / 60.0
    x['hour_sin'] = np.sin(2 * np.pi * hour / 24)
    x['hour_cos'] = np.cos(2 * np.pi * hour / 24)
    x['weekday'] = x.index.dayofweek / 4.0
    # ========================================================
    # REGIME
    # ========================================================
    x['ma20_vs_ma50'] = ma[20] / ma[50] - 1
    x['ma50_vs_ma100'] = ma[50] / ma[100] - 1
    x['trend_strength_20'] = (ma[20] / ma[20].shift(4) - 1).abs()
    x['trend_strength_50'] = (ma[50] / ma[50].shift(4) - 1).abs()
    high32 = x["high"].rolling(32).max()
    low32 = x["low"].rolling(32).min()
    width32 = (high32 - low32).replace(0, np.nan)
    x['breakout_pos_32'] = (x['close'] - low32) / width32
    high64 = x["high"].rolling(64).max()
    low64 = x["low"].rolling(64).min()
    width64 = (high64 - low64).replace(0, np.nan)
    x['range_position_64'] = (x['close'] - low64) / width64
    x['vol_ratio_8_32'] = x['vol_8'] / x['vol_32'].replace(0, np.nan)
    # ------------------------
    # ADX / DI
    # ------------------------
    up_move = x["high"].diff()
    down_move = -x["low"].diff()
    plus_dm = pd.Series(
        np.where(
            (up_move > down_move) & (up_move > 0),
            up_move,
            0.0
        ),
        index=x.index
    )
    minus_dm = pd.Series(
        np.where(
            (down_move > up_move) & (down_move > 0),
            down_move,
            0.0
        ),
        index=x.index
    )
    atr_wilder = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    plus_di = (
        100
        * plus_dm.ewm(
            alpha=1/14,
            adjust=False,
            min_periods=14
        ).mean()
        / atr_wilder.replace(0, np.nan)
    )
    minus_di = (
        100
        * minus_dm.ewm(
            alpha=1/14,
            adjust=False,
            min_periods=14
        ).mean()
        / atr_wilder.replace(0, np.nan)
    )
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    # 0-1へ
    x["plus_di14"] = plus_di / 100.0
    x["minus_di14"] = minus_di / 100.0
    x["adx14"] = adx / 100.0
    # ========================================================
    # VOLATILITY
    # ========================================================
    x['range_mean_4'] = x['range_pct'].rolling(4).mean()
    x['range_mean_16'] = x['range_pct'].rolling(16).mean()
    x['range_std_16'] = x['range_pct'].rolling(16).std()
    return x.replace([np.inf, -np.inf], np.nan)


def prepare_dataset(b, features):
    """特徴量と30分保有の正解を対応付け、欠測をまたぐ候補を除外する。"""
    x = make_all_features(b)
    times = pd.Series(b.index, index=b.index)
    x["entry_time"] = times.shift(-1)
    x['label_end'] = times.shift(-2) + pd.Timedelta(minutes=15)
    x['entry_price'] = b['open'].shift(-1)
    x['exit_price'] = b['close'].shift(-2)
    x['future_return'] = x['exit_price'] / x['entry_price'] - 1
    x['target'] = (x['future_return'] > 0).astype(int)
    # t -> t+1 -> t+2 が連続15分足か確認
    continuous = (
        (times.shift(-1) - times)
        .eq(pd.Timedelta(minutes=15))
        &
        (times.shift(-2) - times)
        .eq(pd.Timedelta(minutes=30))
    )
    required = (
        list(features)
        + [
            "entry_time",
            "label_end",
            "entry_price",
            "exit_price",
            "future_return",
            "target",
        ]
    )
    out = x.loc[continuous].dropna(subset=required).copy()
    return out

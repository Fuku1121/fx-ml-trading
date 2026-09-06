"""Trailing-window features extracted from the latest historical experiment."""

import numpy as np
import pandas as pd


def make_features(bars):
    """Use only prices through the signal bar; keep the original row index."""
    df = bars.copy()
    df["return_5m"] = df["Close"].pct_change(1)
    df["return_15m"] = df["Close"].pct_change(3)
    df["return_30m"] = df["Close"].pct_change(6)
    df["return_1h"] = df["Close"].pct_change(12)
    df["return_2h"] = df["Close"].pct_change(24)
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA5_distance"] = df["Close"] / df["MA5"] - 1
    df["MA20_distance"] = df["Close"] / df["MA20"] - 1
    df["MA50_distance"] = df["Close"] / df["MA50"] - 1
    df["MA5_slope"] = df["MA5"].pct_change(3)
    df["MA20_slope"] = df["MA20"].pct_change(3)
    df["MA50_slope"] = df["MA50"].pct_change(3)
    df["body"] = abs(df["Close"] - df["Open"]) / df["Open"]
    df["range"] = (df["High"] - df["Low"]) / df["Close"]
    df["upper_wick"] = (df["High"] - df[["Open", "Close"]].max(axis=1)) / df["Close"]
    df["lower_wick"] = (df[["Open", "Close"]].min(axis=1) - df["Low"]) / df["Close"]
    df["bullish"] = (df["Close"] > df["Open"]).astype(int)
    df["volatility_1h"] = df["return_5m"].rolling(12).std()
    df["volatility_2h"] = df["return_5m"].rolling(24).std()
    df["volatility_4h"] = df["return_5m"].rolling(48).std()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - 100 / (1 + rs)
    df["high_1h"] = df["High"].rolling(12).max()
    df["low_1h"] = df["Low"].rolling(12).min()
    df["distance_high_1h"] = df["Close"] / df["high_1h"] - 1
    df["distance_low_1h"] = df["Close"] / df["low_1h"] - 1
    df["hour"] = df.index.hour
    df["weekday"] = df.index.dayofweek
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    previous_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = abs(df["High"] - previous_close)
    tr3 = abs(df["Low"] - previous_close)
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR14"] = true_range.rolling(14).mean()
    df["ATR14_pct"] = df["ATR14"] / df["Close"]
    high_diff = df["High"].diff()
    low_diff = -df["Low"].diff()
    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)
    atr_adx = true_range.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr_adx
    minus_di = 100 * minus_dm.rolling(14).mean() / atr_adx
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    df["ADX14"] = dx.rolling(14).mean()
    return df.replace([np.inf, -np.inf], np.nan)

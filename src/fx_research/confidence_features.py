"""15-minute feature formulas preserved from FX (1).ipynb cell 35; UTC features."""
import numpy as np
import pandas as pd

FEATURES = ['return_1', 'return_2', 'return_4', 'return_8', 'return_16', 'vol_4', 'vol_8', 'vol_16', 'vol_32', 'ma5_distance', 'ma5_slope', 'ma10_distance', 'ma10_slope', 'ma20_distance', 'ma20_slope', 'ma50_distance', 'ma50_slope', 'ma100_distance', 'ma100_slope', 'body', 'upper_wick', 'lower_wick', 'range_pct', 'rsi14', 'atr14', 'distance_high_16', 'distance_low_16', 'hour_sin', 'hour_cos', 'weekday']

def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def make_features(data):
    x = data.copy()
    for n in [1, 2, 4, 8, 16]:
        x[f'return_{n}'] = x['close'].pct_change(n)
    for n in [4, 8, 16, 32]:
        x[f'vol_{n}'] = x['return_1'].rolling(n).std()
    for period in [5, 10, 20, 50, 100]:
        ma = x['close'].rolling(period).mean()
        x[f'ma{period}_distance'] = x['close'] / ma - 1
        x[f'ma{period}_slope'] = ma.pct_change()
    candle_range = (x['high'] - x['low']).replace(0, np.nan)
    x['body'] = (x['close'] - x['open']) / candle_range
    x['upper_wick'] = (x['high'] - x[['open', 'close']].max(axis=1)) / candle_range
    x['lower_wick'] = (x[['open', 'close']].min(axis=1) - x['low']) / candle_range
    x['range_pct'] = (x['high'] - x['low']) / x['close']
    x['rsi14'] = calculate_rsi(x['close'], 14) / 100
    prev_close = x['close'].shift(1)
    true_range = pd.concat([x['high'] - x['low'], (x['high'] - prev_close).abs(), (x['low'] - prev_close).abs()], axis=1).max(axis=1)
    x['atr14'] = true_range.rolling(14).mean() / x['close']
    high16 = x['high'].rolling(16).max()
    low16 = x['low'].rolling(16).min()
    x['distance_high_16'] = (high16 - x['close']) / x['close']
    x['distance_low_16'] = (x['close'] - low16) / x['close']
    hour = x.index.hour + x.index.minute / 60
    x['hour_sin'] = np.sin(2 * np.pi * hour / 24)
    x['hour_cos'] = np.cos(2 * np.pi * hour / 24)
    x['weekday'] = x.index.dayofweek / 4
    return x

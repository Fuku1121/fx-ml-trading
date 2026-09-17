"""Reference definitions from FX (4), cell 69. No notebook top-level execution."""
from pathlib import Path
import json
import math
import warnings
import joblib
import numpy as np
import pandas as pd
EXPECTED_CHAMPION = 'BASE_PLUS_REGIME'
EXPECTED_FEATURE_COUNT = 41
MIN_HISTORY_BARS = 150
REQUIRED_OHLC = ['open', 'high', 'low', 'close']

def find_frozen_champion_directory():
    if 'PRODUCTION_FREEZE_DIR' in globals():
        candidate = Path(str(PRODUCTION_FREEZE_DIR))
        if candidate.exists():
            return candidate
    root = Path('production_champion')
    if not root.exists():
        raise RuntimeError('production_champion フォルダが見つかりません。')
    candidates = sorted([p for p in root.iterdir() if p.is_dir() and p.name.startswith('champion_v1_base_plus_regime_') and (p / 'champion_manifest.json').exists()], key=lambda p: p.name)
    if not candidates:
        raise RuntimeError('BASE_PLUS_REGIMEのFreeze artifactが見つかりません。')
    return candidates[-1]
EXPECTED_LIVE_FEATURES = ['return_1', 'return_2', 'return_4', 'return_8', 'return_16', 'vol_4', 'vol_8', 'vol_16', 'vol_32', 'ma5_distance', 'ma5_slope', 'ma10_distance', 'ma10_slope', 'ma20_distance', 'ma20_slope', 'ma50_distance', 'ma50_slope', 'ma100_distance', 'ma100_slope', 'body', 'upper_wick', 'lower_wick', 'range_pct', 'rsi14', 'atr14', 'distance_high_16', 'distance_low_16', 'hour_sin', 'hour_cos', 'weekday', 'adx14', 'adx28', 'ma20_50_spread', 'ma50_100_spread', 'trend_strength_20', 'trend_strength_50', 'price_pos_20', 'price_pos_50', 'ma_alignment_score', 'slope_alignment_score', 'directional_persistence_16']

def normalize_live_bars(bars_input):
    if not isinstance(bars_input, pd.DataFrame):
        raise TypeError('bars_input must be pandas DataFrame.')
    x = bars_input.copy()
    x.columns = [str(c).strip().lower() for c in x.columns]
    missing = [c for c in REQUIRED_OHLC if c not in x.columns]
    if missing:
        raise RuntimeError(f'Missing OHLC columns: {missing}')
    x = x[REQUIRED_OHLC].copy()
    if not isinstance(x.index, pd.DatetimeIndex):
        raise RuntimeError('bars_input.index must be DatetimeIndex.')
    x.index = pd.to_datetime(x.index, utc=True, errors='coerce')
    if x.index.isna().any():
        raise RuntimeError('Invalid timestamps found.')
    x = x.sort_index()
    if x.index.duplicated().any():
        duplicates = int(x.index.duplicated().sum())
        raise RuntimeError(f'Duplicate timestamps: {duplicates}')
    bad_grid = x.index.minute % 15 != 0 | (x.index.second != 0) | (x.index.microsecond != 0)
    if np.asarray(bad_grid).any():
        raise RuntimeError('Non-15m timestamps found.')
    for c in REQUIRED_OHLC:
        x[c] = pd.to_numeric(x[c], errors='coerce')
    if x[REQUIRED_OHLC].isna().any().any():
        raise RuntimeError('OHLC contains NaN/non-numeric values.')
    if (x[REQUIRED_OHLC] <= 0).any().any():
        raise RuntimeError('OHLC contains non-positive prices.')
    bad_high = x['high'] < x[['open', 'low', 'close']].max(axis=1)
    bad_low = x['low'] > x[['open', 'high', 'close']].min(axis=1)
    if bad_high.any() or bad_low.any():
        raise RuntimeError('Invalid OHLC relationship found.')
    if len(x) < MIN_HISTORY_BARS:
        raise RuntimeError(f'Not enough historical bars.\nNeed at least: {MIN_HISTORY_BARS}\nReceived: {len(x)}')
    return x

def live_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def live_true_range(x):
    previous_close = x['close'].shift(1)
    return pd.concat([x['high'] - x['low'], (x['high'] - previous_close).abs(), (x['low'] - previous_close).abs()], axis=1).max(axis=1)

def live_adx(x, period=14):
    high = x['high']
    low = x['low']
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=x.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=x.index)
    tr = live_true_range(x)
    tr_sum = tr.rolling(period).sum().replace(0, np.nan)
    plus_di = 100.0 * plus_dm.rolling(period).sum() / tr_sum
    minus_di = 100.0 * minus_dm.rolling(period).sum() / tr_sum
    denominator = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denominator
    return dx.rolling(period).mean() / 100.0

def make_live_features(bars_input):
    x = normalize_live_bars(bars_input)
    for n in [1, 2, 4, 8, 16]:
        x[f'return_{n}'] = x['close'].pct_change(n)
    for n in [4, 8, 16, 32]:
        x[f'vol_{n}'] = x['return_1'].rolling(n).std()
    MA = {}
    for p in [5, 10, 20, 50, 100]:
        ma = x['close'].rolling(p).mean()
        MA[p] = ma
        x[f'ma{p}_distance'] = x['close'] / ma - 1
        x[f'ma{p}_slope'] = ma.pct_change()
    candle_range = (x['high'] - x['low']).replace(0, np.nan)
    x['body'] = (x['close'] - x['open']) / candle_range
    x['upper_wick'] = (x['high'] - x[['open', 'close']].max(axis=1)) / candle_range
    x['lower_wick'] = (x[['open', 'close']].min(axis=1) - x['low']) / candle_range
    x['range_pct'] = (x['high'] - x['low']) / x['close']
    x['rsi14'] = live_rsi(x['close'], 14) / 100.0
    true_range = live_true_range(x)
    atr14_absolute = true_range.rolling(14).mean()
    x['atr14'] = atr14_absolute / x['close']
    high16 = x['high'].rolling(16).max()
    low16 = x['low'].rolling(16).min()
    x['distance_high_16'] = (high16 - x['close']) / x['close']
    x['distance_low_16'] = (x['close'] - low16) / x['close']
    hour = x.index.hour + x.index.minute / 60.0
    x['hour_sin'] = np.sin(2 * np.pi * hour / 24.0)
    x['hour_cos'] = np.cos(2 * np.pi * hour / 24.0)
    x['weekday'] = x.index.dayofweek / 4.0
    x['adx14'] = live_adx(x, 14)
    x['adx28'] = live_adx(x, 28)
    ma20 = MA[20]
    ma50 = MA[50]
    ma100 = MA[100]
    x['ma20_50_spread'] = ma20 / ma50 - 1
    x['ma50_100_spread'] = ma50 / ma100 - 1
    atr_safe = atr14_absolute.replace(0, np.nan)
    x['trend_strength_20'] = (x['close'] - ma20).abs() / atr_safe
    x['trend_strength_50'] = (x['close'] - ma50).abs() / atr_safe
    high20 = x['high'].rolling(20).max()
    low20 = x['low'].rolling(20).min()
    high50 = x['high'].rolling(50).max()
    low50 = x['low'].rolling(50).min()
    x['price_pos_20'] = (x['close'] - low20) / (high20 - low20).replace(0, np.nan) - 0.5
    x['price_pos_50'] = (x['close'] - low50) / (high50 - low50).replace(0, np.nan) - 0.5
    x['ma_alignment_score'] = ((ma20 > ma50).astype(float) + (ma50 > ma100).astype(float)) / 2.0
    slope20 = ma20.pct_change()
    slope50 = ma50.pct_change()
    slope100 = ma100.pct_change()
    x['slope_alignment_score'] = (np.sign(slope20) + np.sign(slope50) + np.sign(slope100)) / 3.0
    x['directional_persistence_16'] = np.sign(x['return_1']).rolling(16).mean().abs()
    x = x.replace([np.inf, -np.inf], np.nan)
    return x

def live_calibrate_probability(raw_p_up):
    raw_p_up = float(raw_p_up)
    if LIVE_CALIBRATION_METHOD == 'RAW':
        calibrated = raw_p_up
    elif LIVE_CALIBRATION_METHOD == 'ISOTONIC':
        if not hasattr(LIVE_CALIBRATOR, 'predict'):
            raise RuntimeError('Isotonic calibrator invalid.')
        calibrated = float(LIVE_CALIBRATOR.predict([raw_p_up])[0])
    elif LIVE_CALIBRATION_METHOD == 'PLATT':
        if not hasattr(LIVE_CALIBRATOR, 'predict_proba'):
            raise RuntimeError('Platt calibrator invalid.')
        calibrated = float(LIVE_CALIBRATOR.predict_proba(np.array([[raw_p_up]]))[0, 1])
    else:
        raise RuntimeError(f'Unknown calibration method: {LIVE_CALIBRATION_METHOD}')
    return float(np.clip(calibrated, 0.0, 1.0))

def live_session_allowed(signal_time):
    signal_time = pd.Timestamp(signal_time)
    if signal_time.tzinfo is None:
        signal_time = signal_time.tz_localize('UTC')
    else:
        signal_time = signal_time.tz_convert('UTC')
    hour = int(signal_time.hour)
    if LIVE_SESSION == 'ALL':
        return True
    if LIVE_SESSION == 'UTC_13_24':
        return hour >= 13
    if LIVE_SESSION == 'UTC_21_24':
        return hour >= 21
    if LIVE_SESSION == 'EXCLUDE_08_13':
        return not 8 <= hour < 13
    raise RuntimeError(f'Unknown session policy: {LIVE_SESSION}')

def live_position_size(confidence):
    confidence = float(confidence)
    edge = (confidence - LIVE_THRESHOLD) / max(1.0 - LIVE_THRESHOLD, 1e-12)
    edge = float(np.clip(edge, 0.0, 1.0))
    if LIVE_SIZING_POLICY == 'FIXED':
        raw_size = 1.0
    elif LIVE_SIZING_POLICY == 'GENTLE':
        raw_size = 0.85 + 0.3 * edge
    elif LIVE_SIZING_POLICY == 'MODERATE':
        raw_size = 0.7 + 0.6 * edge
    elif LIVE_SIZING_POLICY == 'STRONG':
        raw_size = 0.5 + 1.0 * edge
    else:
        raise RuntimeError(f'Unknown sizing policy: {LIVE_SIZING_POLICY}')
    final_size = raw_size * LIVE_SIZING_SCALE
    return float(np.clip(final_size, 0.25, 2.0))

def run_live_inference(bars_input, position_is_open=False, as_of_utc=None):
    clean_bars = normalize_live_bars(bars_input)
    signal_time = clean_bars.index[-1]
    signal_bar_close_time = signal_time + pd.Timedelta(minutes=15)
    if as_of_utc is not None:
        as_of_utc = pd.Timestamp(as_of_utc)
        if as_of_utc.tzinfo is None:
            as_of_utc = as_of_utc.tz_localize('UTC')
        else:
            as_of_utc = as_of_utc.tz_convert('UTC')
        if signal_bar_close_time > as_of_utc:
            raise RuntimeError(f'Latest 15m bar is not closed yet.\nBar open : {signal_time}\nBar close: {signal_bar_close_time}\nNow      : {as_of_utc}')
    feature_frame = make_live_features(clean_bars)
    latest = feature_frame.loc[[signal_time], LIVE_FEATURES].copy()
    if latest.isna().any().any():
        missing_live_features = latest.columns[latest.isna().iloc[0]].tolist()
        raise RuntimeError(f'Latest signal has NaN features.\nMissing features: {missing_live_features}')
    raw_p_up = float(LIVE_MODEL.predict_proba(latest)[0, 1])
    calibrated_p_up = live_calibrate_probability(raw_p_up)
    if calibrated_p_up >= 0.5:
        proposed_side = 'BUY'
    else:
        proposed_side = 'SELL'
    confidence = float(max(calibrated_p_up, 1.0 - calibrated_p_up))
    session_allowed = live_session_allowed(signal_time)
    threshold_allowed = bool(confidence >= LIVE_THRESHOLD)
    if not session_allowed:
        action = 'NO_TRADE'
        reason = 'SESSION_BLOCKED'
        position_size = 0.0
    elif not threshold_allowed:
        action = 'NO_TRADE'
        reason = 'LOW_CONFIDENCE'
        position_size = 0.0
    elif bool(position_is_open):
        action = 'NO_TRADE'
        reason = 'OPEN_POSITION_OVERLAP_BLOCKED'
        position_size = 0.0
    else:
        action = proposed_side
        reason = 'TRADE_SIGNAL'
        position_size = live_position_size(confidence)
    if action in ['BUY', 'SELL']:
        planned_entry_time = signal_time + pd.Timedelta(minutes=15)
        planned_exit_time = planned_entry_time + pd.Timedelta(minutes=30)
    else:
        planned_entry_time = pd.NaT
        planned_exit_time = pd.NaT
    result = {'champion_version': LIVE_MANIFEST['champion_version'], 'champion': LIVE_MANIFEST['champion_name'], 'signal_time': signal_time, 'signal_bar_close_time': signal_bar_close_time, 'raw_p_up': raw_p_up, 'calibrated_p_up': calibrated_p_up, 'confidence': confidence, 'proposed_side': proposed_side, 'threshold': LIVE_THRESHOLD, 'threshold_allowed': threshold_allowed, 'session': LIVE_SESSION, 'session_allowed': session_allowed, 'position_was_open': bool(position_is_open), 'action': action, 'reason': reason, 'position_size': position_size, 'planned_entry_time': planned_entry_time, 'planned_exit_time': planned_exit_time, 'cost_assumption': LIVE_BASE_COST, 'feature_count': len(LIVE_FEATURES)}
    return result

def print_live_signal(result):
    print()
    print('=' * 90)
    print('FROZEN CHAMPION LIVE SIGNAL')
    print('=' * 90)
    print('Champion:', result['champion'])
    print('Version:', result['champion_version'])
    print('Signal bar:', result['signal_time'])
    print('Bar closed:', result['signal_bar_close_time'])
    print()
    print('Raw p_up:', f"{result['raw_p_up']:.8f}")
    print('Calibrated p_up:', f"{result['calibrated_p_up']:.8f}")
    print('Confidence:', f"{result['confidence']:.8f}")
    print('Threshold:', result['threshold'])
    print()
    print('Proposed side:', result['proposed_side'])
    print('Threshold allowed:', result['threshold_allowed'])
    print('Session allowed:', result['session_allowed'])
    print('Existing position:', result['position_was_open'])
    print()
    print('ACTION:', result['action'])
    print('Reason:', result['reason'])
    print('Position size:', result['position_size'])
    if result['action'] in ['BUY', 'SELL']:
        print()
        print('Planned entry:', result['planned_entry_time'])
        print('Planned exit:', result['planned_exit_time'])

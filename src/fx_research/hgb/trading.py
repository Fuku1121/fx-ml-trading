"""予測から取引を選び、取引量・コスト・成績を計算する。

出典: FX (2).ipynb セル58。計算式は原実験を保持。
"""

import math
import numpy as np
import pandas as pd

from .config import COST, THRESHOLDS, SESSIONS, SIZING_POLICIES, MIN_VALIDATION_TRADES

def stats_of_returns(r):
    """取引ごとの純損益から勝率・PF・複利成長・決済ベースDDを集計する。"""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return {
            "trades": 0,
            "win_rate": np.nan,
            "avg_return": np.nan,
            "profit_factor": np.nan,
            "growth": 0.0,
            "max_dd": np.nan,
            "return_to_dd": np.nan,
        }
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses > 0:
        pf = gains / losses
    elif gains > 0:
        pf = np.inf
    else:
        pf = np.nan
    equity = np.r_[1.0, np.cumprod(1 + r)]
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1
    max_dd = float(dd.min())
    growth = float(equity[-1] - 1)
    if (
        np.isfinite(max_dd)
        and max_dd < 0
    ):
        rdd = growth / abs(max_dd)
    else:
        rdd = np.nan
    return {
        "trades": int(len(r)),
        "win_rate": float((r > 0).mean()),
        "avg_return": float(r.mean()),
        "profit_factor": float(pf),
        "growth": growth,
        "max_dd": max_dd,
        "return_to_dd": float(rdd),
    }


def prediction_frame(data, calibrated_probability):
    """確率を方向・Confidence・方向付き損益へ変換する。"""
    p = np.asarray(calibrated_probability)
    direction_sign = np.where(p >= 0.5, 1.0, -1.0)
    out = data[['entry_time', 'label_end', 'future_return', 'target']].copy()
    out["p_up"] = p
    out['confidence'] = np.maximum(p, 1 - p)
    out['gross_return'] = data['future_return'].values * direction_sign
    return out


def session_mask(index, policy):
    """シグナル足の開始時刻が選択したUTC時間帯に入るかを判定する。"""
    hour = index.hour
    if policy == "ALL":
        return np.ones(len(index), dtype=bool)
    if policy == "UTC_13_24":
        return (hour >= 13) & (hour < 24)
    if policy == "UTC_21_24":
        return (hour >= 21) & (hour < 24)
    if policy == "EXCLUDE_08_13":
        return ~((hour >= 8) & (hour < 13))
    raise ValueError(policy)


def select_trades(pred, threshold, session):
    """閾値・時間帯で選別し、実際の保有時間が重ならない取引だけ残す。"""
    mask = (pred['confidence'] >= threshold) & session_mask(pred.index, session)
    candidates = pred.loc[mask].sort_index()
    selected = []
    next_free = None
    for row in candidates.itertuples():
        if (
            next_free is not None
            and row.entry_time < next_free
        ):
            continue
        selected.append(row.Index)
        next_free = row.label_end
    trades = candidates.loc[selected].copy()
    trades['base_net_return'] = trades['gross_return'] - COST
    return trades


def choose_threshold_session(validation_predictions):
    """前年の取引で閾値と時間帯を選ぶ。翌年の成績は参照しない。"""
    rows = []
    best = None
    best_key = None
    for threshold in THRESHOLDS:
        for session in SESSIONS:
            trades = select_trades(validation_predictions, threshold, session)
            s = stats_of_returns(trades['base_net_return'])
            eligible = s['trades'] >= MIN_VALIDATION_TRADES
            if eligible:
                score = s['avg_return'] * math.sqrt(s['trades'])
            else:
                score = np.nan
            rows.append(
                {
                    "threshold": threshold,
                    "session": session,
                    "eligible": eligible,
                    "score": score,
                    **s
                }
            )
            if not eligible:
                continue
            key = (
                score,
                (
                    s["profit_factor"]
                    if np.isfinite(
                        s["profit_factor"]
                    )
                    else -999
                ),
                s["trades"],
                -threshold
            )
            if (
                best_key is None
                or key > best_key
            ):
                best_key = key
                best = (threshold, session)
    if best is None:
        raise RuntimeError('Validationで十分な取引数を持つThreshold/Sessionがありません。')
    return (best[0], best[1], pd.DataFrame(rows))


def raw_size(confidence, threshold, policy):
    """Confidenceに応じた補正前の取引量を計算する。"""
    confidence = np.asarray(confidence)
    edge = (confidence - threshold) / max(1 - threshold, 1e-08)
    edge = np.clip(edge, 0, 1)
    if policy == "FIXED":
        return np.ones_like(edge)
    if policy == "GENTLE":
        return 0.85 + 0.30 * edge
    if policy == "MODERATE":
        return 0.70 + 0.60 * edge
    if policy == "STRONG":
        return 0.50 + 1.00 * edge
    raise ValueError(policy)


def choose_sizing(trades, threshold):
    """前年の平均取引量を揃えて候補を比較し、方式と補正係数を固定する。"""
    if trades.empty:
        return ('FIXED', 1.0)
    rows = []
    for policy in SIZING_POLICIES:
        raw = raw_size(trades['confidence'], threshold, policy)
        # 平均Exposureを1へ
        scale = 1.0 / raw.mean()
        size = raw * scale
        r = size * (trades['gross_return'].values - COST)
        s = stats_of_returns(r)
        rows.append({'policy': policy, 'scale': scale, **s})
    table = pd.DataFrame(rows)
    fixed = table.loc[table['policy'] == 'FIXED'].iloc[0]
    candidates = []
    for _, row in table.iterrows():
        if row["policy"] == "FIXED":
            continue
        if (
            row["avg_return"]
            >= fixed["avg_return"]
            and
            row["profit_factor"]
            >= fixed["profit_factor"]
            and
            row["return_to_dd"]
            >= fixed["return_to_dd"]
        ):
            candidates.append(row)
    if not candidates:
        return ('FIXED', 1.0)
    chosen = max(
        candidates,
        key=lambda r: (
            r["return_to_dd"],
            r["profit_factor"],
            r["avg_return"]
        )
    )
    return (chosen['policy'], float(chosen['scale']))


def apply_sizing(trades, threshold, policy, scale, cost_multiplier=1.0):
    """固定した方式と係数で取引量を計算し、コスト控除後の損益へ反映する。"""
    out = trades.copy()
    size = raw_size(out['confidence'], threshold, policy) * scale
    size = np.clip(size, 0.25, 2.0)
    out["position_size"] = size
    out['net_return'] = size * (out['gross_return'] - COST * cost_multiplier)
    return out

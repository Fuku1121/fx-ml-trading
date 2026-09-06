"""Quality labels remain directional time-exit return minus cost > 0 (not TP/SL labels)."""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from .config import TRADING_COST, HORIZON_BARS, HALF_LIFE_DAYS, QUALITY_OOF_SPLITS
from .feature_sets import quality_market_features
from .models import make_time_weights, fit_base_models, predict_base_models


def build_quality_features(frame, p_move, p_up, p_down):
    quality_x = frame[quality_market_features].copy()
    quality_x["p_move"] = p_move
    quality_x["p_up"] = p_up
    quality_x["p_down"] = p_down
    quality_x["direction_confidence"] = abs(p_up - p_down)
    quality_x["predicted_direction"] = (p_up >= p_down).astype(int)
    return quality_x


def make_quality_target(frame, p_up, p_down):
    predicted_buy = p_up >= p_down
    directional_return = np.where(
        predicted_buy, frame["future_return"].values, -frame["future_return"].values
    )
    net_return = directional_return - TRADING_COST
    quality_target = (net_return > 0).astype(int)
    return (quality_target, net_return)


def create_quality_oof_dataset(frame):
    initial_size = int(len(frame) * 0.4)
    remaining = len(frame) - initial_size
    block = max(remaining // QUALITY_OOF_SPLITS, 1)
    qx_list = []
    for split in range(QUALITY_OOF_SPLITS):
        val_start = initial_size + split * block
        if split == QUALITY_OOF_SPLITS - 1:
            val_end = len(frame)
        else:
            val_end = min(val_start + block, len(frame))
        train_end = val_start - HORIZON_BARS
        if train_end < 200:
            continue
        oof_train = frame.iloc[:train_end]
        oof_val = frame.iloc[val_start:val_end]
        if len(oof_val) == 0:
            continue
        models = fit_base_models(oof_train, trees=180)
        if models is None:
            continue
        p_move, p_up, p_down = predict_base_models(models, oof_val)
        quality_x = build_quality_features(oof_val, p_move, p_up, p_down)
        quality_y, _ = make_quality_target(oof_val, p_up, p_down)
        quality_x["quality_target"] = quality_y
        qx_list.append(quality_x)
    if len(qx_list) == 0:
        return None
    quality_data = pd.concat(qx_list).sort_index()
    return quality_data


def fit_quality_model(quality_data):
    quality_feature_names = [c for c in quality_data.columns if c != "quality_target"]
    if len(quality_data) < 100 or quality_data["quality_target"].nunique() < 2:
        return None
    weights = make_time_weights(quality_data.index, HALF_LIFE_DAYS)
    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=7,
        min_samples_leaf=20,
        max_features="sqrt",
        class_weight="balanced",
        random_state=123,
        n_jobs=-1,
    )
    model.fit(
        quality_data[quality_feature_names],
        quality_data["quality_target"],
        sample_weight=weights,
    )
    return (model, quality_feature_names)


def predict_quality(quality_bundle, frame, p_move, p_up, p_down):
    model, feature_names = quality_bundle
    x = build_quality_features(frame, p_move, p_up, p_down)
    probability = model.predict_proba(x[feature_names])[:, 1]
    return probability

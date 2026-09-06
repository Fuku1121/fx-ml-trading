"""Time-weighted RandomForest MOVE and conditional Direction models."""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from .config import HALF_LIFE_DAYS
from .feature_sets import move_features, direction_features


def make_time_weights(index, half_life_days):
    latest = index.max()
    age_days = (latest - index).total_seconds() / 86400
    weights = 0.5 ** (age_days / half_life_days)
    return np.array(weights)


def fit_base_models(train_frame, trees=250):
    if train_frame["move_target"].nunique() < 2:
        return None
    move_weights = make_time_weights(train_frame.index, HALF_LIFE_DAYS)
    move_model = RandomForestClassifier(
        n_estimators=trees,
        max_depth=8,
        min_samples_leaf=20,
        max_features="sqrt",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    move_model.fit(
        train_frame[move_features],
        train_frame["move_target"],
        sample_weight=move_weights,
    )
    direction_train = train_frame[train_frame["move_target"] == 1]
    if len(direction_train) < 50 or direction_train["direction_target"].nunique() < 2:
        return None
    direction_weights = make_time_weights(direction_train.index, HALF_LIFE_DAYS)
    direction_model = RandomForestClassifier(
        n_estimators=trees,
        max_depth=8,
        min_samples_leaf=15,
        max_features="sqrt",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    direction_model.fit(
        direction_train[direction_features],
        direction_train["direction_target"],
        sample_weight=direction_weights,
    )
    return (move_model, direction_model)


def predict_base_models(models, frame):
    move_model, direction_model = models
    p_move = move_model.predict_proba(frame[move_features])[:, 1]
    direction_prob = direction_model.predict_proba(frame[direction_features])
    class_map = {c: i for i, c in enumerate(direction_model.classes_)}
    p_down = direction_prob[:, class_map[0]]
    p_up = direction_prob[:, class_map[1]]
    return (p_move, p_up, p_down)

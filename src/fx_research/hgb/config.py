"""最新HGB比較の固定条件。評価結果を見ながら変更せず、別実験として管理する。

出典: FX (2).ipynb セル58。計算式は原実験を保持。
"""



RANDOM_STATE = 42


COST = 0.00004


DEVELOPMENT_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


CONFIRMATION_YEAR = 2026


THRESHOLDS = [0.55, 0.56, 0.58, 0.60, 0.62, 0.65]


SESSIONS = ['ALL', 'UTC_13_24', 'UTC_21_24', 'EXCLUDE_08_13']


SIZING_POLICIES = ['FIXED', 'GENTLE', 'MODERATE', 'STRONG']


CALIBRATION_METHODS = ['RAW', 'PLATT', 'ISOTONIC']


HGB_CONFIG = {
    "learning_rate": 0.05,
    "max_iter": 250,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 30,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": RANDOM_STATE,
}


MIN_TRAIN_ROWS = 10000


MIN_EVAL_ROWS = 500


MIN_VALIDATION_TRADES = 40



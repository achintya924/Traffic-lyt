"""Lightweight Poisson regression risk model for count forecasting (Phase 3.4)."""

from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

Granularity = Literal["hour", "day"]

MIN_TRAIN_POINTS = 30


def _parse_ts(ts_str: str) -> datetime:
    s = str(ts_str)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def build_training_rows(
    history: list[dict[str, object]],
    granularity: Granularity,
) -> tuple[list[dict[str, Any]], list[int], list[str]]:
    """
    Build feature dicts, target y, and timestamps from history.

    Features: dow (0=Mon), is_weekend (0/1), hour (0-23 only when granularity=="hour").
    """
    X_rows: list[dict[str, Any]] = []
    y_list: list[int] = []
    timestamps: list[str] = []
    for h in history:
        ts_str = str(h["ts"])
        dt = _parse_ts(ts_str)
        dow = dt.weekday()
        is_weekend = 1 if dow in (5, 6) else 0
        row: dict[str, Any] = {"dow": dow, "is_weekend": is_weekend}
        if granularity == "hour":
            row["hour"] = dt.hour
        y_list.append(int(h["count"]))
        timestamps.append(ts_str)
        X_rows.append(row)
    return X_rows, y_list, timestamps


def _dicts_to_array(X_dicts: list[dict[str, Any]], granularity: Granularity) -> np.ndarray:
    """Convert list of feature dicts to 2D array for sklearn (dow, [hour], is_weekend)."""
    if granularity == "hour":
        return np.array(
            [[d["dow"], d["hour"], d["is_weekend"]] for d in X_dicts],
            dtype=np.float64,
        )
    return np.array(
        [[d["dow"], d["is_weekend"]] for d in X_dicts],
        dtype=np.float64,
    )


def train_poisson_model(
    X_dicts: list[dict[str, Any]],
    y: list[int],
    granularity: Granularity,
    alpha: float = 0.1,
) -> tuple[Pipeline | None, dict[str, Any]]:
    """
    Train a Poisson regression pipeline (OneHotEncoder for dow/hour + passthrough is_weekend).
    Returns (fitted_pipeline, train_meta). Pipeline is None when insufficient_data.
    """
    train_meta: dict[str, Any] = {"insufficient_data": False}
    if len(y) < MIN_TRAIN_POINTS:
        train_meta["insufficient_data"] = True
        return None, train_meta
    X = _dicts_to_array(X_dicts, granularity)
    y_arr = np.array(y, dtype=np.float64)

    if granularity == "hour":
        # columns: 0=dow, 1=hour, 2=is_weekend
        ct = ColumnTransformer(
            [
                ("dow", OneHotEncoder(categories=[list(range(7))], sparse_output=False), [0]),
                ("hour", OneHotEncoder(categories=[list(range(24))], sparse_output=False), [1]),
                ("num", "passthrough", [2]),
            ],
            remainder="drop",
        )
    else:
        # columns: 0=dow, 1=is_weekend
        ct = ColumnTransformer(
            [
                ("dow", OneHotEncoder(categories=[list(range(7))], sparse_output=False), [0]),
                ("num", "passthrough", [1]),
            ],
            remainder="drop",
        )

    pipeline = Pipeline(
        [
            ("preprocess", ct),
            ("model", PoissonRegressor(alpha=alpha, max_iter=1000)),
        ]
    )
    pipeline.fit(X, y_arr)
    train_meta["n_samples"] = len(y)
    return pipeline, train_meta


def backtest(
    fitted: Pipeline,
    X_dicts: list[dict[str, Any]],
    y: list[int],
    granularity: Granularity,
) -> dict[str, Any]:
    """Use last 20% as test (min 5 points). Return mae, mape, test_points."""
    n = len(y)
    test_size = max(5, int(n * 0.2))
    if n < test_size + 1:
        return {"test_points": 0, "mae": 0.0, "mape": 0.0}
    X = _dicts_to_array(X_dicts, granularity)
    X_train, X_test = X[:-test_size], X[-test_size:]
    y_test = y[-test_size:]
    pred = fitted.predict(X_test)
    pred = np.maximum(pred, 0.0)
    mae = float(np.mean(np.abs(pred - y_test)))
    # MAPE with safe denominator max(actual, 1)
    denom = np.maximum(np.array(y_test, dtype=np.float64), 1.0)
    mape = float(np.mean(np.abs(pred - y_test) / denom) * 100.0)
    return {"test_points": test_size, "mae": round(mae, 4), "mape": round(mape, 4)}


def predict_future(
    fitted: Pipeline,
    last_ts: datetime,
    granularity: Granularity,
    horizon: int,
) -> list[dict[str, Any]]:
    """Generate future timestamps, build features, predict. Return list of {ts, expected, expected_rounded}."""
    step = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    out: list[dict[str, Any]] = []
    for step_i in range(1, horizon + 1):
        dt = last_ts + step * step_i
        dow = dt.weekday()
        is_weekend = 1 if dow in (5, 6) else 0
        if granularity == "hour":
            row = np.array([[dow, dt.hour, is_weekend]], dtype=np.float64)
        else:
            row = np.array([[dow, is_weekend]], dtype=np.float64)
        pred = fitted.predict(row)
        expected = float(max(0.0, pred[0]))
        out.append({
            "ts": dt.isoformat(),
            "expected": round(expected, 4),
            "expected_rounded": max(0, round(expected)),
        })
    return out


def get_last_ts_from_history(history: list[dict[str, object]]) -> datetime | None:
    """Return the datetime of the last history point, or None if empty."""
    if not history:
        return None
    return _parse_ts(str(history[-1]["ts"]))


def explain_coefficients(fitted_pipeline: Pipeline, top_k: int = 8) -> dict[str, Any]:
    """Extract feature names and coefficients; return top positive and top negative."""
    try:
        pre = fitted_pipeline.named_steps["preprocess"]
        model = fitted_pipeline.named_steps["model"]
        names = pre.get_feature_names_out()
        coefs = model.coef_
        if len(names) != len(coefs):
            return {"top_positive": [], "top_negative": []}
        pairs = [(str(n), float(c)) for n, c in zip(names, coefs)]
        pairs.sort(key=lambda x: x[1], reverse=True)
        top_positive = [{"feature": n, "coef": c} for n, c in pairs[:top_k] if c > 0]
        top_negative = [{"feature": n, "coef": c} for n, c in pairs[-top_k:] if c < 0]
        top_negative.reverse()
        return {"top_positive": top_positive, "top_negative": top_negative}
    except Exception:
        return {"top_positive": [], "top_negative": []}

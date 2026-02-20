"""
Phase 4.7: Shared helpers for standardized meta.eval and meta.explain.
"""
from __future__ import annotations

import re
from typing import Any

MAX_EXPLAIN_FEATURES = 10
DOW_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _humanize_feature(raw: str) -> str:
    """Convert encoded feature (e.g. preprocess__hour__x1_23.0) to human-readable label."""
    # preprocess__dow__x0_2.0 -> Day of week = Wednesday
    m = re.search(r"dow__x0_(\d+)(?:\.0)?$", raw, re.I)
    if m:
        idx = int(m.group(1))
        if 0 <= idx <= 6:
            return f"Day of week = {DOW_NAMES[idx]}"
        return f"Day of week = {idx}"

    # preprocess__hour__x1_23.0 -> Hour = 23
    m = re.search(r"hour__x1_(\d+)(?:\.0)?$", raw, re.I)
    if m:
        return f"Hour = {m.group(1)}"

    # preprocess__num__x2_1.0 -> Weekend (or is_weekend)
    m = re.search(r"num__x2_(1)(?:\.0)?$", raw, re.I)
    if m:
        return "Weekend"
    m = re.search(r"num__x2_(0)(?:\.0)?$", raw, re.I)
    if m:
        return "Weekday"

    return raw


def format_explainability(
    top_positive: list[dict[str, Any]],
    top_negative: list[dict[str, Any]],
    feature_name_map: dict[str, str] | None = None,
    max_features: int = MAX_EXPLAIN_FEATURES,
) -> dict[str, Any]:
    """
    Build standardized meta.explain schema from top_positive/top_negative.

    Each feature item: name, raw_feature, effect, coef, weight.
    Sorted by weight desc. Limited to max_features.
    """
    merged: list[dict[str, Any]] = []
    for item in top_positive or []:
        raw = str(item.get("feature", item.get("raw_feature", "")))
        coef = float(item.get("coef", 0))
        if coef <= 0:
            continue
        name = (feature_name_map or {}).get(raw) or _humanize_feature(raw)
        merged.append({
            "name": name,
            "raw_feature": raw,
            "effect": "increase",
            "coef": round(coef, 6),
            "weight": round(abs(coef), 6),
        })
    for item in top_negative or []:
        raw = str(item.get("feature", item.get("raw_feature", "")))
        coef = float(item.get("coef", 0))
        if coef >= 0:
            continue
        name = (feature_name_map or {}).get(raw) or _humanize_feature(raw)
        merged.append({
            "name": name,
            "raw_feature": raw,
            "effect": "decrease",
            "coef": round(coef, 6),
            "weight": round(abs(coef), 6),
        })

    merged.sort(key=lambda x: x["weight"], reverse=True)
    features = merged[:max_features]

    return {
        "features": features,
        "method": "linear_coefficients",
        "notes": "Poisson regression feature effects (higher weight = stronger impact).",
    }


def build_eval_meta(backtest_info: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Build standardized meta.eval from backtest results.

    Standard keys: mae, mape, rmse, smape, test_points, train_points,
    horizon, granularity, backtest_window (start_ts/end_ts if available).
    """
    if not backtest_info:
        return None

    metrics: dict[str, Any] = {}
    for k in ("mae", "mape", "rmse", "smape"):
        if k in backtest_info and backtest_info[k] is not None:
            v = backtest_info[k]
            metrics[k] = round(float(v), 6) if isinstance(v, (int, float)) else v

    result: dict[str, Any] = {"metrics": metrics if metrics else {}}
    for k in ("test_points", "train_points", "horizon", "granularity", "points_used", "window"):
        if k in backtest_info and backtest_info[k] is not None:
            result[k] = backtest_info[k]

    if "backtest_window" in backtest_info and backtest_info["backtest_window"]:
        result["backtest_window"] = backtest_info["backtest_window"]
    if "start_ts" in backtest_info and backtest_info["start_ts"]:
        result["backtest_window"] = result.get("backtest_window") or {}
        result["backtest_window"]["start_ts"] = backtest_info["start_ts"]
    if "end_ts" in backtest_info and backtest_info["end_ts"]:
        result["backtest_window"] = result.get("backtest_window") or {}
        result["backtest_window"]["end_ts"] = backtest_info["end_ts"]

    if not result.get("metrics") and not any(
        k in result for k in ("test_points", "train_points", "horizon", "granularity", "points_used", "window", "backtest_window")
    ):
        return None
    return result

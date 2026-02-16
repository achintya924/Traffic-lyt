"""
Predictive-oriented endpoints (time-series foundation + forecasting).

Example curl (timeseries):

  # Hourly series with bbox
  # curl "http://localhost:8000/predict/timeseries?granularity=hour&bbox=-74.1,40.6,-73.9,40.8"

  # Day with hour wrap + violation_type
  # curl "http://localhost:8000/predict/timeseries?granularity=day&hour_start=22&hour_end=2&violation_type=No%20Parking"

Example curl (forecast):

  # Forecast next 24 hours with bbox
  # curl "http://localhost:8000/predict/forecast?granularity=hour&horizon=24&bbox=-74.1,40.6,-73.9,40.8"

  # Forecast next 7 days with violation_type + hour wrap
  # curl "http://localhost:8000/predict/forecast?granularity=day&horizon=7&violation_type=No%20Parking&hour_start=22&hour_end=2"

Example curl (trends):

  # Daily trend with bbox
  # curl "http://localhost:8000/predict/trends?granularity=day&window=14&bbox=-74.1,40.6,-73.9,40.8"

  # Hourly trend with hour wrap + violation_type
  # curl "http://localhost:8000/predict/trends?granularity=hour&window=24&hour_start=22&hour_end=3&violation_type=No%20Parking"

Example curl (hotspots grid; omit end to use dataset max time for static data):
  # curl "http://localhost:8000/predict/hotspots/grid?cell_m=250&recent_days=7&baseline_days=30&bbox=-74.1,40.6,-73.9,40.8"

  # violation_type + hour wrap + bbox
  # curl "http://localhost:8000/predict/hotspots/grid?cell_m=300&recent_days=3&baseline_days=14&hour_start=22&hour_end=3&violation_type=NO%20PARKING&bbox=-74.1,40.6,-73.9,40.8"

Example curl (risk / Poisson regression):
  # hourly risk for bbox
  # curl "http://localhost:8000/predict/risk?granularity=hour&horizon=24&bbox=-74.1,40.6,-73.9,40.8"
  # daily risk for violation_type + hour wrap + bbox (add end to ensure data overlap with static data)
  # curl "http://localhost:8000/predict/risk?granularity=day&horizon=7&violation_type=NO%20PARKING&hour_start=22&hour_end=3&bbox=-74.1,40.6,-73.9,40.8&end=2024-12-28T23:59:59"
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_connection, get_engine
from app.predict.forecast import forecast_counts
from app.predict.hotspots import get_hotspot_grid
from app.predict.regression import (
    backtest,
    build_training_rows,
    explain_coefficients,
    get_last_ts_from_history,
    predict_future,
    train_poisson_model,
)
from app.predict.timeseries import get_counts_timeseries
from app.predict.trends import compute_trends
from app.queries.predict_sql import Granularity
from app.utils.time_anchor import (
    build_time_window_meta,
    compute_anchored_window,
    get_data_time_range,
)
from app.utils.violation_filters import ViolationFilters, get_violation_filters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predict", tags=["predict"])


def _filters_with_anchored_window(
    conn: Any,
    filters: ViolationFilters,
) -> tuple[ViolationFilters, dict[str, Any]]:
    """Phase 4.1: Return (filters_to_use, time_meta). When user has no start/end, anchor to data_max_ts."""
    data_min_ts, data_max_ts = get_data_time_range(conn, filters)
    effective_start, effective_end, anchor_ts, window_source = compute_anchored_window(
        filters, data_min_ts, data_max_ts
    )
    time_meta = build_time_window_meta(
        data_min_ts=data_min_ts,
        data_max_ts=data_max_ts,
        anchor_ts=anchor_ts,
        effective_start_ts=effective_start,
        effective_end_ts=effective_end,
        window_source=window_source,
        message="No data for the given filter scope." if data_max_ts is None else None,
    )
    if effective_start is not None and effective_end is not None:
        filters_to_use = ViolationFilters(
            start=effective_start,
            end=effective_end,
            hour_start=filters.hour_start,
            hour_end=filters.hour_end,
            violation_type=filters.violation_type,
            bbox=filters.bbox,
        )
    else:
        filters_to_use = filters
    return filters_to_use, time_meta


@router.get("/timeseries")
def timeseries(
    granularity: Granularity = Query(
        "hour",
        description="Aggregation granularity: 'hour' or 'day'",
    ),
    limit_history: int = Query(
        500,
        ge=1,
        le=5000,
        description="Maximum number of buckets to return (most recent).",
    ),
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    """
    Return a continuous time-series of counts for the given granularity.
    Phase 4.1: When start/end not provided, effective window is [data_min_ts, data_max_ts] (anchored).
    """
    engine = get_engine()
    if engine is None:
        return {
            "granularity": granularity,
            "series": [],
            "meta": {
                "points": 0,
                **build_time_window_meta(
                    data_min_ts=None,
                    data_max_ts=None,
                    anchor_ts=None,
                    effective_start_ts=None,
                    effective_end_ts=None,
                    window_source="anchored",
                    message="No database connection.",
                ),
            },
        }

    try:
        with get_connection() as conn:
            if conn is None:
                return {
                    "granularity": granularity,
                    "series": [],
                    "meta": {
                        "points": 0,
                        **build_time_window_meta(
                            data_min_ts=None,
                            data_max_ts=None,
                            anchor_ts=None,
                            effective_start_ts=None,
                            effective_end_ts=None,
                            window_source="anchored",
                            message="No connection.",
                        ),
                    },
                }
            filters_to_use, time_meta = _filters_with_anchored_window(conn, filters)
            series = get_counts_timeseries(conn, filters_to_use, granularity, limit_history)
    except Exception:
        logger.exception("predict/timeseries failed")
        raise HTTPException(status_code=500, detail="predict/timeseries failed")

    return {
        "granularity": granularity,
        "series": series,
        "meta": {"points": len(series), **time_meta},
    }


@router.get("/forecast")
def forecast(
    granularity: Granularity = Query(
        "hour",
        description="Aggregation granularity: 'hour' or 'day'",
    ),
    horizon: int | None = Query(
        None,
        ge=1,
        le=365,
        description="Number of future buckets to predict; default 24 for hour, 7 for day",
    ),
    model: str = Query(
        "ma",
        description="Forecast model: naive, ma, or ewm",
    ),
    window: int = Query(6, ge=1, description="Window size for ma model"),
    alpha: float = Query(0.3, ge=0.0, le=1.0, description="Smoothing factor for ewm model"),
    limit_history: int = Query(
        500,
        ge=1,
        le=5000,
        description="Maximum number of history buckets to use",
    ),
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    """
    Return history plus a simple forecast of violation counts for the current filters + bbox.
    """
    effective_horizon = horizon if horizon is not None else (24 if granularity == "hour" else 7)

    empty_time_meta = build_time_window_meta(
        data_min_ts=None,
        data_max_ts=None,
        anchor_ts=None,
        effective_start_ts=None,
        effective_end_ts=None,
        window_source="anchored",
        message="No database connection.",
    )
    engine = get_engine()
    if engine is None:
        return {
            "granularity": granularity,
            "model": {"name": model, "window": window, "alpha": alpha, "horizon": effective_horizon},
            "history": [],
            "forecast": [],
            "meta": {"history_points": 0, "forecast_points": 0, **empty_time_meta},
        }

    try:
        with get_connection() as conn:
            if conn is None:
                return {
                    "granularity": granularity,
                    "model": {"name": model, "window": window, "alpha": alpha, "horizon": effective_horizon},
                    "history": [],
                    "forecast": [],
                    "meta": {"history_points": 0, "forecast_points": 0, **empty_time_meta},
                }
            filters_to_use, time_meta = _filters_with_anchored_window(conn, filters)
            history = get_counts_timeseries(conn, filters_to_use, granularity, limit_history)
        forecast_list = forecast_counts(
            history,
            granularity,
            effective_horizon,
            model=model,
            window=window,
            alpha=alpha,
        )
    except Exception:
        logger.exception("predict/forecast failed")
        raise HTTPException(status_code=500, detail="predict/forecast failed")

    return {
        "granularity": granularity,
        "model": {"name": model, "window": window, "alpha": alpha, "horizon": effective_horizon},
        "history": history,
        "forecast": forecast_list,
        "meta": {
            "history_points": len(history),
            "forecast_points": len(forecast_list),
            **time_meta,
        },
    }


@router.get("/trends")
def trends(
    granularity: Granularity = Query(
        "day",
        description="Aggregation granularity: 'hour' or 'day'",
    ),
    window: int = Query(
        14,
        ge=3,
        le=180,
        description="Window size for recent/previous period comparison",
    ),
    limit_history: int = Query(
        500,
        ge=1,
        le=5000,
        description="Maximum number of history buckets (use at least 2*window for full metrics)",
    ),
    anomaly_z: float = Query(
        2.5,
        ge=1.0,
        le=6.0,
        description="Z-score threshold for anomaly detection",
    ),
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    """
    Return explainable trend metrics for violation counts (current filters + bbox). Phase 4.1: anchored window + meta.
    """
    empty_time_meta = build_time_window_meta(
        data_min_ts=None,
        data_max_ts=None,
        anchor_ts=None,
        effective_start_ts=None,
        effective_end_ts=None,
        window_source="anchored",
        message="No connection.",
    )
    engine = get_engine()
    if engine is None:
        return {
            "granularity": granularity,
            "trends": {
                "window": window,
                "recent_mean": 0.0,
                "prev_mean": 0.0,
                "pct_change": 0.0,
                "slope": 0.0,
                "trend_direction": "flat",
                "volatility": 0.0,
                "anomalies": [],
                "insufficient_data": True,
                "points_used": 0,
            },
            "meta": {"history_points": 0, **empty_time_meta},
        }

    try:
        with get_connection() as conn:
            if conn is None:
                return {
                    "granularity": granularity,
                    "trends": {
                        "window": window,
                        "recent_mean": 0.0,
                        "prev_mean": 0.0,
                        "pct_change": 0.0,
                        "slope": 0.0,
                        "trend_direction": "flat",
                        "volatility": 0.0,
                        "anomalies": [],
                        "insufficient_data": True,
                        "points_used": 0,
                    },
                    "meta": {"history_points": 0, **empty_time_meta},
                }
            filters_to_use, time_meta = _filters_with_anchored_window(conn, filters)
            history = get_counts_timeseries(conn, filters_to_use, granularity, limit_history)
        trends_result = compute_trends(history, window=window, anomaly_z=anomaly_z)
    except Exception:
        logger.exception("predict/trends failed")
        raise HTTPException(status_code=500, detail="predict/trends failed")

    return {
        "granularity": granularity,
        "trends": trends_result,
        "meta": {"history_points": len(history), **time_meta},
    }


@router.get("/hotspots/grid")
def hotspots_grid(
    cell_m: int = Query(
        250,
        ge=50,
        le=2000,
        description="Grid cell size in meters",
    ),
    recent_days: int = Query(
        7,
        ge=1,
        le=90,
        description="Recent window length in days",
    ),
    baseline_days: int = Query(
        30,
        ge=1,
        le=365,
        description="Baseline window length in days",
    ),
    limit: int = Query(
        3000,
        ge=1,
        le=10000,
        description="Maximum number of cells to return",
    ),
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    """
    Return grid cells with recent_count, baseline_count, risk score (0-100), and risk_level.
    Uses bbox + filters; bbox is recommended for performance.
    """
    empty_time_meta = build_time_window_meta(
        data_min_ts=None,
        data_max_ts=None,
        anchor_ts=None,
        effective_start_ts=None,
        effective_end_ts=None,
        window_source="anchored",
        message="No connection.",
    )
    engine = get_engine()
    if engine is None:
        return {
            "cells": [],
            "meta": {
                "cell_m": cell_m,
                "grid_size_deg": round(cell_m / 111320.0, 8),
                "recent_days": recent_days,
                "baseline_days": baseline_days,
                "points": 0,
                **empty_time_meta,
            },
        }

    try:
        with get_connection() as conn:
            if conn is None:
                return {
                    "cells": [],
                    "meta": {
                        "cell_m": cell_m,
                        "grid_size_deg": round(cell_m / 111320.0, 8),
                        "recent_days": recent_days,
                        "baseline_days": baseline_days,
                        "points": 0,
                        **empty_time_meta,
                    },
                }
            result = get_hotspot_grid(
                conn,
                filters,
                cell_m=cell_m,
                recent_days=recent_days,
                baseline_days=baseline_days,
                limit=limit,
            )
    except Exception:
        logger.exception("predict/hotspots/grid failed")
        raise HTTPException(status_code=500, detail="predict/hotspots/grid failed")

    return result


@router.get("/risk")
def risk(
    granularity: Granularity = Query(
        "hour",
        description="Aggregation granularity: 'hour' or 'day'",
    ),
    horizon: int | None = Query(
        None,
        ge=1,
        le=365,
        description="Forecast horizon; default 24 for hour, 7 for day",
    ),
    limit_history: int = Query(
        1000,
        ge=50,
        le=5000,
        description="Maximum history points for training",
    ),
    alpha: float = Query(
        0.1,
        ge=0.0,
        le=10.0,
        description="Poisson regression L2 regularization",
    ),
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    """
    Train a Poisson regression on time-series features (dow, hour, is_weekend) and predict next N buckets.
    Falls back to MA forecast when insufficient data (< 30 points).
    """
    effective_horizon = horizon if horizon is not None else (24 if granularity == "hour" else 7)
    empty_time_meta = build_time_window_meta(
        data_min_ts=None,
        data_max_ts=None,
        anchor_ts=None,
        effective_start_ts=None,
        effective_end_ts=None,
        window_source="anchored",
        message="No connection.",
    )
    engine = get_engine()
    if engine is None:
        return {
            "granularity": granularity,
            "model": {"name": "poisson_regression", "alpha": alpha, "horizon": effective_horizon},
            "history_points": 0,
            "metrics": {"mae": 0.0, "mape": 0.0, "test_points": 0},
            "explain": {"top_positive": [], "top_negative": []},
            "forecast": [],
            "meta": {"fallback_used": False, "insufficient_data": True, **empty_time_meta},
        }

    try:
        with get_connection() as conn:
            if conn is None:
                return {
                    "granularity": granularity,
                    "model": {"name": "poisson_regression", "alpha": alpha, "horizon": effective_horizon},
                    "history_points": 0,
                    "metrics": {"mae": 0.0, "mape": 0.0, "test_points": 0},
                    "explain": {"top_positive": [], "top_negative": []},
                    "forecast": [],
                    "meta": {"fallback_used": False, "insufficient_data": True, **empty_time_meta},
                }
            filters_to_use, time_meta = _filters_with_anchored_window(conn, filters)
            history = get_counts_timeseries(conn, filters_to_use, granularity, limit_history)

        X_rows, y_list, _ = build_training_rows(history, granularity)
        fitted, train_meta = train_poisson_model(X_rows, y_list, granularity, alpha=alpha)

        if fitted is None or train_meta.get("insufficient_data"):
            fallback = forecast_counts(
                history,
                granularity,
                effective_horizon,
                model="ma",
                window=6,
            )
            forecast_out = [
                {"ts": f["ts"], "expected": float(f["count"]), "expected_rounded": int(f["count"])}
                for f in fallback
            ]
            return {
                "granularity": granularity,
                "model": {"name": "poisson_regression", "alpha": alpha, "horizon": effective_horizon},
                "history_points": len(history),
                "metrics": {"mae": 0.0, "mape": 0.0, "test_points": 0},
                "explain": {"top_positive": [], "top_negative": []},
                "forecast": forecast_out,
                "meta": {"fallback_used": True, "insufficient_data": True, **time_meta},
            }

        metrics = backtest(fitted, X_rows, y_list, granularity)
        last_ts = get_last_ts_from_history(history)
        if last_ts is None:
            forecast_out = []
        else:
            forecast_out = predict_future(fitted, last_ts, granularity, effective_horizon)
        explain = explain_coefficients(fitted, top_k=8)

        return {
            "granularity": granularity,
            "model": {"name": "poisson_regression", "alpha": alpha, "horizon": effective_horizon},
            "history_points": len(history),
            "metrics": metrics,
            "explain": explain,
            "forecast": forecast_out,
            "meta": {"fallback_used": False, "insufficient_data": False, **time_meta},
        }
    except Exception:
        logger.exception("predict/risk failed")
        raise HTTPException(status_code=500, detail="predict/risk failed")


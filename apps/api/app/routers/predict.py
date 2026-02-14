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

Example curl (hotspots grid):

  # bbox + default windows
  # curl "http://localhost:8000/predict/hotspots/grid?cell_m=250&recent_days=7&baseline_days=30&bbox=-74.1,40.6,-73.9,40.8"

  # violation_type + hour wrap + bbox
  # curl "http://localhost:8000/predict/hotspots/grid?cell_m=300&recent_days=3&baseline_days=14&hour_start=22&hour_end=3&violation_type=NO%20PARKING&bbox=-74.1,40.6,-73.9,40.8"
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_connection, get_engine
from app.predict.forecast import forecast_counts
from app.predict.hotspots import get_hotspot_grid
from app.predict.timeseries import get_counts_timeseries
from app.predict.trends import compute_trends
from app.queries.predict_sql import Granularity
from app.utils.violation_filters import ViolationFilters, get_violation_filters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predict", tags=["predict"])


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

    Filters (start/end, hour_start/hour_end, violation_type, bbox) are reused from
    the shared violation_filters dependency, including bbox handling.
    """
    engine = get_engine()
    if engine is None:
        return {"granularity": granularity, "series": [], "meta": {"points": 0}}

    try:
        with get_connection() as conn:
            if conn is None:
                return {"granularity": granularity, "series": [], "meta": {"points": 0}}
            series = get_counts_timeseries(conn, filters, granularity, limit_history)
    except Exception:
        logger.exception("predict/timeseries failed")
        raise HTTPException(status_code=500, detail="predict/timeseries failed")

    return {
        "granularity": granularity,
        "series": series,
        "meta": {"points": len(series)},
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

    engine = get_engine()
    if engine is None:
        return {
            "granularity": granularity,
            "model": {"name": model, "window": window, "alpha": alpha, "horizon": effective_horizon},
            "history": [],
            "forecast": [],
            "meta": {"history_points": 0, "forecast_points": 0},
        }

    try:
        with get_connection() as conn:
            if conn is None:
                return {
                    "granularity": granularity,
                    "model": {"name": model, "window": window, "alpha": alpha, "horizon": effective_horizon},
                    "history": [],
                    "forecast": [],
                    "meta": {"history_points": 0, "forecast_points": 0},
                }
            history = get_counts_timeseries(conn, filters, granularity, limit_history)
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
        "meta": {"history_points": len(history), "forecast_points": len(forecast_list)},
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
    Return explainable trend metrics for violation counts (current filters + bbox).
    """
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
            "meta": {"history_points": 0},
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
                    "meta": {"history_points": 0},
                }
            history = get_counts_timeseries(conn, filters, granularity, limit_history)
        trends_result = compute_trends(history, window=window, anomaly_z=anomaly_z)
    except Exception:
        logger.exception("predict/trends failed")
        raise HTTPException(status_code=500, detail="predict/trends failed")

    return {
        "granularity": granularity,
        "trends": trends_result,
        "meta": {"history_points": len(history)},
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


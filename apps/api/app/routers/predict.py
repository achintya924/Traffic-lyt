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
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_connection, get_engine
from app.predict.forecast import forecast_counts
from app.predict.timeseries import get_counts_timeseries
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


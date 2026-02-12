"""
Predictive-oriented endpoints (time-series foundation).

Example curl:

  # Hourly series with bbox
  # curl "http://localhost:8000/predict/timeseries?granularity=hour&bbox=-74.1,40.6,-73.9,40.8"

  # Day with hour wrap + violation_type
  # curl "http://localhost:8000/predict/timeseries?granularity=day&hour_start=22&hour_end=2&violation_type=No%20Parking"
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_connection, get_engine
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


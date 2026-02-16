"""
GET /violations/stats — totals and top violation types with optional filters.
Phase 4.1: response includes meta with data_min_ts, data_max_ts, effective_window, window_source, timezone.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.time_anchor import (
    build_time_window_meta,
    compute_anchored_window,
    get_data_time_range,
)
from app.utils.violation_filters import ViolationFilters, build_violation_where, get_violation_filters

router = APIRouter(prefix="/violations", tags=["violations"])

_empty_meta = build_time_window_meta(
    data_min_ts=None,
    data_max_ts=None,
    anchor_ts=None,
    effective_start_ts=None,
    effective_end_ts=None,
    window_source="anchored",
    message="No connection.",
)


@router.get("/stats")
def violations_stats(
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    engine = get_engine()
    if engine is None:
        return {"total": 0, "min_time": None, "max_time": None, "top_types": [], "meta": _empty_meta}

    where_sql, params = build_violation_where(filters)

    totals_sql = f"""
        SELECT
            COUNT(*)::int AS total,
            MIN(occurred_at) AS min_time,
            MAX(occurred_at) AS max_time
        FROM violations
        {where_sql}
    """
    top_types_sql = f"""
        SELECT violation_type, COUNT(*)::int AS count
        FROM violations
        {where_sql}
        GROUP BY violation_type
        ORDER BY count DESC
        LIMIT 10
    """

    try:
        with get_connection() as conn:
            if conn is None:
                return {"total": 0, "min_time": None, "max_time": None, "top_types": [], "meta": _empty_meta}

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

            totals_row = conn.execute(text(totals_sql), params).fetchone()
            total = totals_row[0] or 0
            min_time: datetime | None = totals_row[1]
            max_time: datetime | None = totals_row[2]

            if total == 0:
                return {
                    "total": 0,
                    "min_time": None,
                    "max_time": None,
                    "top_types": [],
                    "meta": time_meta,
                }

            top_rows = conn.execute(text(top_types_sql), params).fetchall()
            top_types = [
                {"violation_type": row[0] or "", "count": row[1]}
                for row in top_rows
            ]

            return {
                "total": total,
                "min_time": min_time.isoformat() if min_time else None,
                "max_time": max_time.isoformat() if max_time else None,
                "top_types": top_types,
                "meta": time_meta,
            }
    except Exception:
        return {"total": 0, "min_time": None, "max_time": None, "top_types": [], "meta": _empty_meta}

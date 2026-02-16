"""
GET /aggregations/time/hour — violation counts per hour (0..23), with optional filters.
GET /aggregations/time/day — violation counts per day.
Note: Phase 4.1 time-window meta is added to endpoints that already return an object; these return raw lists for backward compatibility.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.violation_filters import ViolationFilters, build_violation_where, get_violation_filters

router = APIRouter(prefix="/aggregations/time", tags=["aggregations"])


@router.get("/hour")
def hour_aggregation(
    filters: ViolationFilters = Depends(get_violation_filters),
) -> list[dict[str, int]]:
    """Return counts per hour (0..23). Missing hours have count 0."""
    engine = get_engine()
    if engine is None:
        return [{"hour": h, "count": 0} for h in range(24)]

    where_sql, params = build_violation_where(filters)
    sql = f"""
        SELECT EXTRACT(HOUR FROM occurred_at)::int AS hour,
               COUNT(*)::int AS count
        FROM violations
        {where_sql}
        GROUP BY EXTRACT(HOUR FROM occurred_at)
        ORDER BY hour
    """
    try:
        with get_connection() as conn:
            if conn is None:
                return [{"hour": h, "count": 0} for h in range(24)]
            rows = conn.execute(text(sql), params).fetchall()
    except Exception:
        return [{"hour": h, "count": 0} for h in range(24)]

    # Fill all 24 hours; missing hours get count 0
    by_hour = {int(r[0]): int(r[1]) for r in rows}
    return [{"hour": h, "count": by_hour.get(h, 0)} for h in range(24)]


@router.get("/day")
def day_aggregation(
    filters: ViolationFilters = Depends(get_violation_filters),
) -> list[dict[str, int | str]]:
    """Return counts per day. Returns [] if no rows match."""
    engine = get_engine()
    if engine is None:
        return []

    where_sql, params = build_violation_where(filters)
    sql = f"""
        SELECT date_trunc('day', occurred_at)::date AS day,
               COUNT(*)::int AS count
        FROM violations
        {where_sql}
        GROUP BY date_trunc('day', occurred_at)
        ORDER BY day
    """
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            rows = conn.execute(text(sql), params).fetchall()
    except Exception:
        return []

    return [
        {"day": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]), "count": int(row[1])}
        for row in rows
    ]

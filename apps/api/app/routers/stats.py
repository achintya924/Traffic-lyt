"""
GET /violations/stats — totals and top violation types with optional filters.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.violation_filters import ViolationFilters, build_violation_where, get_violation_filters

router = APIRouter(prefix="/violations", tags=["violations"])


@router.get("/stats")
def violations_stats(
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    engine = get_engine()
    if engine is None:
        return {"total": 0, "min_time": None, "max_time": None, "top_types": []}

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
                return {"total": 0, "min_time": None, "max_time": None, "top_types": []}

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
            }
    except Exception:
        return {"total": 0, "min_time": None, "max_time": None, "top_types": []}

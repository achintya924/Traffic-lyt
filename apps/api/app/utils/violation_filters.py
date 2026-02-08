"""
Reusable violation filter helper (date, hour, violation_type).
Used by GET /violations/stats and can be reused in later phases.
"""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Query

from pydantic import BaseModel


class ViolationFilters(BaseModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    hour_start: Optional[int] = None  # 0..23
    hour_end: Optional[int] = None   # 0..23
    violation_type: Optional[str] = None


def get_violation_filters(
    start: Optional[datetime] = Query(None, description="Filter violations on or after this time"),
    end: Optional[datetime] = Query(None, description="Filter violations on or before this time"),
    hour_start: Optional[int] = Query(None, ge=0, le=23, description="Start hour (0-23)"),
    hour_end: Optional[int] = Query(None, ge=0, le=23, description="End hour (0-23), can wrap past midnight"),
    violation_type: Optional[str] = Query(None, description="Exact violation_type match"),
) -> ViolationFilters:
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="start must be <= end")
    return ViolationFilters(
        start=start,
        end=end,
        hour_start=hour_start,
        hour_end=hour_end,
        violation_type=violation_type.strip() if violation_type else None,
    )


def build_violation_where(filters: ViolationFilters) -> tuple[str, dict]:
    """
    Build WHERE clause and params for violations table.
    Returns (where_sql, params) for use with text() and conn.execute().
    where_sql is "" or " WHERE ... AND ..."; params is a dict for placeholders.
    """
    clauses: list[str] = []
    params: dict = {}

    if filters.start is not None:
        clauses.append("occurred_at >= :start")
        params["start"] = filters.start
    if filters.end is not None:
        clauses.append("occurred_at <= :end")
        params["end"] = filters.end
    if filters.violation_type:
        clauses.append("violation_type = :violation_type")
        params["violation_type"] = filters.violation_type

    # Hour filter: EXTRACT(HOUR FROM occurred_at)
    h_start, h_end = filters.hour_start, filters.hour_end
    if h_start is not None and h_end is not None:
        if h_start <= h_end:
            clauses.append("EXTRACT(HOUR FROM occurred_at) BETWEEN :hour_start AND :hour_end")
            params["hour_start"] = h_start
            params["hour_end"] = h_end
        else:
            # Wrap across midnight (e.g. 22 -> 2 means 22, 23, 0, 1, 2)
            clauses.append(
                "(EXTRACT(HOUR FROM occurred_at) >= :hour_start OR EXTRACT(HOUR FROM occurred_at) <= :hour_end)"
            )
            params["hour_start"] = h_start
            params["hour_end"] = h_end
    elif h_start is not None:
        clauses.append("EXTRACT(HOUR FROM occurred_at) = :hour_start")
        params["hour_start"] = h_start
    elif h_end is not None:
        clauses.append("EXTRACT(HOUR FROM occurred_at) = :hour_end")
        params["hour_end"] = h_end

    where_sql = " AND ".join(clauses)
    if where_sql:
        where_sql = " WHERE " + where_sql
    return (where_sql, params)

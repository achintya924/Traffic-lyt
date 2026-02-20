"""
Phase 4.9A: Data sufficiency guard for forecasting.
Compute recent activity metrics to flag insufficient data.
"""
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.utils.violation_filters import ViolationFilters, build_violation_where

RECENT_DAYS = 90
MIN_TOTAL_EVENTS = 30
MIN_NONZERO_DAYS = 10


def get_recent_activity(
    conn: Connection,
    filters: ViolationFilters,
    data_max_ts,
) -> dict:
    """
    Compute activity in the last RECENT_DAYS (anchored to data_max_ts).
    Returns {total_events_last_90d, nonzero_days_last_90d}.
    """
    if data_max_ts is None:
        return {"total_events_last_90d": 0, "nonzero_days_last_90d": 0}

    start_ts = data_max_ts - timedelta(days=RECENT_DAYS)
    scope = ViolationFilters(
        start=start_ts,
        end=data_max_ts,
        hour_start=filters.hour_start,
        hour_end=filters.hour_end,
        violation_type=filters.violation_type,
        bbox=filters.bbox,
    )
    where_sql, params = build_violation_where(scope)

    row = conn.execute(
        text(f"""
            SELECT
                COUNT(*)::int AS total,
                COUNT(DISTINCT date_trunc('day', occurred_at))::int AS nonzero_days
            FROM violations
            {where_sql}
        """),
        params,
    ).fetchone()

    total = int(row[0]) if row and row[0] is not None else 0
    nonzero_days = int(row[1]) if row and row[1] is not None else 0

    return {"total_events_last_90d": total, "nonzero_days_last_90d": nonzero_days}


def check_data_sufficiency(
    total_events: int,
    nonzero_days: int,
) -> dict | None:
    """
    Return data_quality dict if insufficient, else None.
    Thresholds: total_events < 30 OR nonzero_days < 10.
    """
    if total_events >= MIN_TOTAL_EVENTS and nonzero_days >= MIN_NONZERO_DAYS:
        return None
    return {
        "status": "insufficient_data",
        "reason": (
            f"Low recent activity: {total_events} events, {nonzero_days} nonzero days in last {RECENT_DAYS} days. "
            f"Thresholds: >= {MIN_TOTAL_EVENTS} events, >= {MIN_NONZERO_DAYS} nonzero days."
        ),
        "total_events_last_90d": total_events,
        "nonzero_days_last_90d": nonzero_days,
        "recommendation": "Zoom out or choose a larger area for a more reliable forecast.",
    }

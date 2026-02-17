"""
Phase 4.1: Time window anchoring. All relative windows anchor to dataset MAX(occurred_at)
for the SAME filter context (bbox, violation_type, hour, etc.). No wall-clock now().
"""
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.utils.violation_filters import ViolationFilters, build_violation_where

TIMEZONE = "UTC"


def filters_without_time(filters: ViolationFilters) -> ViolationFilters:
    """Same filter scope (bbox, violation_type, hour) but no start/end."""
    return ViolationFilters(
        start=None,
        end=None,
        hour_start=filters.hour_start,
        hour_end=filters.hour_end,
        violation_type=filters.violation_type,
        bbox=filters.bbox,
    )


def get_data_time_range(conn: Connection, filters: ViolationFilters) -> tuple[datetime | None, datetime | None]:
    """
    Compute MIN(occurred_at) and MAX(occurred_at) for the same non-time filter scope.
    Uses bbox, violation_type, hour_start/hour_end when present. Safe for viewport-scoped endpoints.
    Returns (min_ts, max_ts) as naive UTC datetimes; (None, None) if no rows.
    """
    scope = filters_without_time(filters)
    where_sql, params = build_violation_where(scope)
    row = conn.execute(
        text("SELECT MIN(occurred_at) AS min_ts, MAX(occurred_at) AS max_ts FROM violations" + where_sql),
        params,
    ).fetchone()
    if not row or row[0] is None or row[1] is None:
        return (None, None)

    def _norm(ts: Any) -> datetime | None:
        if ts is None:
            return None
        if isinstance(ts, date) and not isinstance(ts, datetime):
            ts = datetime.combine(ts, datetime.min.time())
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        return ts

    return (_norm(row[0]), _norm(row[1]))


def to_utc_iso(ts: datetime | None) -> str | None:
    """Normalize to UTC ISO 8601 string. Store/return in UTC."""
    if ts is None:
        return None
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return ts.isoformat() + "Z" if not ts.isoformat().endswith("Z") else ts.isoformat()


def build_time_window_meta(
    *,
    data_min_ts: datetime | None,
    data_max_ts: datetime | None,
    anchor_ts: datetime | None,
    effective_start_ts: datetime | None,
    effective_end_ts: datetime | None,
    window_source: str,
    effective_window_extra: dict[str, Any] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """
    Build the data freshness contract for API responses.
    window_source: "anchored" (relative window anchored to data_max_ts) or "absolute" (user provided start/end).
    """
    meta: dict[str, Any] = {
        "data_min_ts": to_utc_iso(data_min_ts),
        "data_max_ts": to_utc_iso(data_max_ts),
        "anchor_ts": to_utc_iso(anchor_ts),
        "effective_window": {
            "start_ts": to_utc_iso(effective_start_ts),
            "end_ts": to_utc_iso(effective_end_ts),
        },
        "window_source": window_source,
        "timezone": TIMEZONE,
    }
    if effective_window_extra:
        meta["effective_window"].update(effective_window_extra)
    if message is not None:
        meta["message"] = message
    return meta


def compute_anchored_window(
    filters: ViolationFilters,
    data_min_ts: datetime | None,
    data_max_ts: datetime | None,
    *,
    relative_days: int | None = None,
) -> tuple[datetime | None, datetime | None, datetime | None, str]:
    """
    Compute effective start/end and anchor for the request.
    Returns (effective_start_ts, effective_end_ts, anchor_ts, window_source).

    - If user provided start and end: use them, window_source="absolute", anchor_ts=data_max_ts.
    - If user did not provide end: anchor_ts = data_max_ts, end_ts = data_max_ts,
      start_ts = end_ts - relative_days (if given) else data_min_ts.
    """
    if data_max_ts is None:
        if filters.start is not None and filters.end is not None:
            return (filters.start, filters.end, None, "absolute")
        return (None, None, None, "anchored")

    if filters.start is not None and filters.end is not None:
        return (filters.start, filters.end, data_max_ts, "absolute")

    anchor_ts = data_max_ts
    end_ts = data_max_ts
    if relative_days is not None:
        start_ts = end_ts - timedelta(days=relative_days)
        if data_min_ts is not None:
            start_ts = max(start_ts, data_min_ts)
        if filters.start is not None:
            start_ts = max(start_ts, filters.start)
        return (start_ts, end_ts, anchor_ts, "anchored")

    start_ts = data_min_ts if data_min_ts is not None else end_ts
    if filters.start is not None:
        start_ts = max(start_ts, filters.start) if start_ts else filters.start
    return (start_ts, end_ts, anchor_ts, "anchored")

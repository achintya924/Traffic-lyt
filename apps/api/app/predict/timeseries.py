"""Time-series extraction helpers for violations counts."""

from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy.engine import Connection

from app.queries.predict_sql import Granularity, build_timeseries_sql
from app.utils.violation_filters import ViolationFilters, build_violation_where


def _align_to_boundary(ts: datetime | date, granularity: Literal["hour", "day"]) -> datetime:
    """Align a timestamp to the bucket boundary (naive datetime)."""
    if isinstance(ts, date) and not isinstance(ts, datetime):
        ts = datetime.combine(ts, datetime.min.time())
    if not isinstance(ts, datetime):
        raise TypeError(f"Expected datetime or date from DB, got {type(ts).__name__}: {ts!r}")
    # Strip tzinfo for consistent naive ISO output (match existing API).
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    if granularity == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unsupported granularity: {granularity}")


def get_counts_timeseries(
    conn: Connection,
    filters: ViolationFilters,
    granularity: Granularity,
    limit_history: int = 5000,
) -> list[dict[str, object]]:
    """
    Return a continuous time-series of violation counts.

    - Buckets by hour or day using date_trunc().
    - Applies the shared filter engine (start/end, hour wrap, violation_type, bbox).
    - Fills missing buckets in Python so the series is continuous; timestamps are
      aligned to bucket boundaries (hour: :00:00.0, day: midnight).
    - Truncates to at most `limit_history` buckets (most recent).
    """
    where_sql, params = build_violation_where(filters)
    sql = build_timeseries_sql(granularity, where_sql)

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return []

    # Normalize DB ts to boundary-aligned naive datetimes; ensure type safety.
    aligned_ts = []
    for row in rows:
        raw_ts = row[0]
        aligned_ts.append(_align_to_boundary(raw_ts, granularity))

    counts_map = {aligned_ts[i]: int(rows[i][1]) for i in range(len(rows))}
    start = min(aligned_ts)
    end = max(aligned_ts)

    step = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)

    series: list[dict[str, object]] = []
    current = start
    while current <= end:
        series.append({"ts": current.isoformat(), "count": counts_map.get(current, 0)})
        current += step

    # Keep only the most recent `limit_history` buckets if necessary.
    if limit_history > 0 and len(series) > limit_history:
        series = series[-limit_history:]

    return series


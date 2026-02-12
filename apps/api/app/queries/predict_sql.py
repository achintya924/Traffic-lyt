"""SQL builder for time-series violation counts."""

from typing import Literal

from sqlalchemy import text

Granularity = Literal["hour", "day"]


def build_timeseries_sql(granularity: Granularity, where_sql: str):
    """
    Build a SQLAlchemy TextClause to fetch bucketed counts by hour or day.

    The where_sql should come from the shared build_violation_where() helper and
    already include any filters (including bbox) as a WHERE ... clause or be empty.
    """
    if granularity == "hour":
        bucket_expr = "date_trunc('hour', occurred_at)"
    elif granularity == "day":
        bucket_expr = "date_trunc('day', occurred_at)"
    else:
        raise ValueError(f"Unsupported granularity: {granularity}")

    sql = f"""
        SELECT
            {bucket_expr} AS ts,
            COUNT(*)::int AS count
        FROM violations
        {where_sql}
        GROUP BY ts
        ORDER BY ts ASC
    """
    return text(sql)


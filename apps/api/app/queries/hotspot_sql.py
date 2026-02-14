"""SQL builder for hotspot risk grid (recent vs baseline window counts)."""

from sqlalchemy import text


def build_hotspot_grid_sql(
    where_recent_sql: str,
    where_baseline_sql: str,
) -> "text":
    """
    Build a single SQL query that returns grid cells with recent_count, baseline_count, ratio.

    Uses ST_SnapToGrid(geom, :grid_size_deg) in 4326; grid_size_deg should be cell_m / 111320.0.
    Expects params: grid_size_deg, recent_days, baseline_days, limit, plus all placeholders
    from where_recent_sql and where_baseline_sql (e.g. recent_start, recent_end, baseline_start, baseline_end,
    and shared: violation_type, hour_start, hour_end, bbox_min_lon, ...).
    """
    sql = f"""
    WITH recent AS (
        SELECT
            ST_X(ST_SnapToGrid(geom, :grid_size_deg)) AS gx,
            ST_Y(ST_SnapToGrid(geom, :grid_size_deg)) AS gy,
            COUNT(*)::int AS recent_count
        FROM violations
        {where_recent_sql}
        GROUP BY gx, gy
    ),
    baseline AS (
        SELECT
            ST_X(ST_SnapToGrid(geom, :grid_size_deg)) AS gx,
            ST_Y(ST_SnapToGrid(geom, :grid_size_deg)) AS gy,
            COUNT(*)::int AS baseline_count
        FROM violations
        {where_baseline_sql}
        GROUP BY gx, gy
    ),
    merged AS (
        SELECT
            COALESCE(r.gx, b.gx) AS cell_x,
            COALESCE(r.gy, b.gy) AS cell_y,
            COALESCE(r.recent_count, 0)::int AS recent_count,
            COALESCE(b.baseline_count, 0)::int AS baseline_count
        FROM recent r
        FULL OUTER JOIN baseline b ON r.gx = b.gx AND r.gy = b.gy
    )
    SELECT
        cell_x,
        cell_y,
        cell_x AS centroid_lon,
        cell_y AS centroid_lat,
        recent_count,
        baseline_count,
        (recent_count::float / GREATEST(:recent_days, 1)) / NULLIF(
            baseline_count::float / GREATEST(:baseline_days, 1) + 1e-9, 0
        ) AS ratio
    FROM merged
    ORDER BY ratio DESC NULLS LAST
    LIMIT :limit
    """
    return text(sql)

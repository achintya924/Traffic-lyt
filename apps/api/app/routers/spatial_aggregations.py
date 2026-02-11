"""
GET /aggregations/grid — spatial grid aggregation (count per cell).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.violation_filters import ViolationFilters, build_violation_where, get_violation_filters

router = APIRouter(prefix="/aggregations", tags=["aggregations"])


def parse_bbox(bbox: Optional[str]) -> Optional[tuple[float, float, float, float]]:
    """Parse 'minLon,minLat,maxLon,maxLat' into (min_lon, min_lat, max_lon, max_lat)."""
    if not bbox or not bbox.strip():
        return None
    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != 4:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
        if min_lon >= max_lon or min_lat >= max_lat:
            return None
        return (min_lon, min_lat, max_lon, max_lat)
    except ValueError:
        return None


@router.get("/grid")
def grid_aggregation(
    filters: ViolationFilters = Depends(get_violation_filters),
    cell_m: int = Query(250, ge=100, le=2000, description="Grid cell size in meters"),
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
) -> list[dict]:
    """Return grid cells with lat, lon (cell center in 4326) and count."""
    engine = get_engine()
    if engine is None:
        return []

    where_sql, params = build_violation_where(filters)
    params["cell_m"] = cell_m

    bbox_tuple = parse_bbox(bbox)
    if bbox_tuple is not None:
        min_lon, min_lat, max_lon, max_lat = bbox_tuple
        bbox_clause = " geom && ST_MakeEnvelope(:bbox_min_lon, :bbox_min_lat, :bbox_max_lon, :bbox_max_lat, 4326)"
        params["bbox_min_lon"] = min_lon
        params["bbox_min_lat"] = min_lat
        params["bbox_max_lon"] = max_lon
        params["bbox_max_lat"] = max_lat
        if where_sql:
            where_sql = where_sql + " AND" + bbox_clause
        else:
            where_sql = " WHERE" + bbox_clause

    sql = f"""
        WITH snapped AS (
            SELECT ST_SnapToGrid(ST_Transform(geom, 3857), :cell_m) AS cell_3857
            FROM violations
            {where_sql}
        )
        SELECT
            ST_Y(ST_Transform(cell_3857, 4326)) AS lat,
            ST_X(ST_Transform(cell_3857, 4326)) AS lon,
            COUNT(*)::int AS count
        FROM snapped
        GROUP BY cell_3857
        ORDER BY count DESC
    """
    try:
        with get_connection() as conn:
            if conn is None:
                return []
            rows = conn.execute(text(sql), params).fetchall()
    except Exception:
        return []

    return [
        {"lat": round(float(r[0]), 6), "lon": round(float(r[1]), 6), "count": int(r[2])}
        for r in rows
    ]

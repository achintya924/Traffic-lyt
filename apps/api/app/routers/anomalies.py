"""
Phase 5.5: Historical anomaly heatmap — grid-based z-score anomaly detection.
GET /api/anomalies/heatmap
"""
from collections import defaultdict
from datetime import datetime
from math import sqrt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit
from app.utils.response_cache import get_response_cache, make_response_key
from app.utils.time_anchor import to_utc_iso
from app.utils.violation_filters import _parse_bbox

ANOMALY_HEATMAP_TTL = 90

# ~100m grid cell size (degrees in 4326)
GRID_SIZE_DEG = 0.001

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


def _heatmap_signature(
    start_ts: str | None,
    end_ts: str | None,
    granularity: str,
    bbox: str | None,
    method: str,
    threshold: float,
    top_n: int,
) -> str:
    """Deterministic signature for heatmap cache key."""
    return f"s{start_ts or ''}|e{end_ts or ''}|g{granularity}|b{bbox or ''}|m{method}|t{threshold}|n{top_n}"


def _zscore_anomaly_weight(counts: list[int], threshold: float) -> tuple[int, float]:
    """
    Compute anomaly hits and weight for a cell.
    baseline = mean, stddev. z = (count - mean) / stddev. anomaly if z >= threshold.
    Returns (anomaly_hits, weight). weight = anomaly_hits.
    Handle stddev=0 safely: no anomalies (z undefined).
    """
    if not counts:
        return (0, 0.0)
    n = len(counts)
    mean = sum(counts) / n
    if n < 2:
        return (0, 0.0)
    variance = sum((x - mean) ** 2 for x in counts) / n
    stddev = sqrt(variance)
    if stddev <= 0:
        return (0, 0.0)
    anomaly_hits = 0
    for c in counts:
        z = (c - mean) / stddev
        if z >= threshold:
            anomaly_hits += 1
    return (anomaly_hits, float(anomaly_hits))


@router.get("/heatmap", dependencies=[Depends(rate_limit("stats"))])
def get_anomaly_heatmap(
    request: Request,
    start_ts: datetime | None = Query(None, description="Start of time window (ISO)"),
    end_ts: datetime | None = Query(None, description="End of time window (ISO)"),
    granularity: str = Query("day", description="day | hour"),
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    method: str = Query("zscore", description="zscore | ewm"),
    threshold: float = Query(3.0, ge=0.0, description="Anomaly threshold (z-score)"),
    top_n: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    """
    Anomaly heatmap: grid cells where violations spike anomalously vs baseline.
    Uses z-score: anomaly when (count - mean) / stddev >= threshold.
    Returns points (lat, lon, weight) for heatmap rendering.
    """
    if granularity not in ("hour", "day"):
        raise HTTPException(status_code=422, detail="granularity must be 'hour' or 'day'")
    if method not in ("zscore", "ewm"):
        raise HTTPException(status_code=422, detail="method must be 'zscore' or 'ewm'")
    if method == "ewm":
        raise HTTPException(status_code=422, detail="ewm method not implemented; use zscore")
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise HTTPException(status_code=422, detail="start_ts must be <= end_ts")

    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        base_params: dict[str, Any] = {}
        bbox_clause = ""
        if bbox:
            bbox_tuple = _parse_bbox(bbox)
            if bbox_tuple:
                min_lon, min_lat, max_lon, max_lat = bbox_tuple
                bbox_clause = " AND geom && ST_MakeEnvelope(:bbox_min_lon, :bbox_min_lat, :bbox_max_lon, :bbox_max_lat, 4326)"
                base_params["bbox_min_lon"] = min_lon
                base_params["bbox_min_lat"] = min_lat
                base_params["bbox_max_lon"] = max_lon
                base_params["bbox_max_lat"] = max_lat

        if start_ts is not None and end_ts is not None:
            effective_start = start_ts
            effective_end = end_ts
            anchor_ts = end_ts
            base_params["start_ts"] = start_ts
            base_params["end_ts"] = end_ts
        else:
            range_sql = f"""
                SELECT MIN(occurred_at), MAX(occurred_at)
                FROM violations
                WHERE 1=1 {bbox_clause}
            """
            range_row = conn.execute(text(range_sql), base_params).fetchone()
            data_max = range_row[1] if range_row and range_row[1] else None
            if not data_max:
                payload = _empty_heatmap_payload(request)
                return payload
            anchor_ts = data_max
            data_min = range_row[0] if range_row and range_row[0] else None
            effective_end = data_max
            effective_start = data_min if data_min else effective_end
            time_clause = ""
            base_params["start_ts"] = effective_start
            base_params["end_ts"] = effective_end

        anchor_ts_str = to_utc_iso(anchor_ts)
        effective_window = {
            "start_ts": to_utc_iso(effective_start),
            "end_ts": to_utc_iso(effective_end),
        }
        sig = _heatmap_signature(
            to_utc_iso(start_ts) if start_ts else None,
            to_utc_iso(end_ts) if end_ts else None,
            granularity,
            bbox,
            method,
            threshold,
            top_n,
        )
        resp_key = make_response_key("anomaly_heatmap", sig, anchor_ts_str, effective_window)
        resp_cache = get_response_cache()
        cached = resp_cache.get(resp_key)
        if cached is not None:
            request.state.response_cache_hit = True
            out = dict(cached)
            out["meta"] = {**cached.get("meta", {}), "response_cache": "hit"}
            return out

        trunc = "hour" if granularity == "hour" else "day"
        trunc_sql = f"date_trunc('{trunc}', occurred_at)"

        agg_sql = f"""
            SELECT
                ST_X(ST_SnapToGrid(geom, :grid_size)) AS cell_lon,
                ST_Y(ST_SnapToGrid(geom, :grid_size)) AS cell_lat,
                {trunc_sql} AS bucket_ts,
                COUNT(*)::int AS cnt
            FROM violations
            WHERE occurred_at >= :start_ts AND occurred_at <= :end_ts {bbox_clause}
            GROUP BY cell_lon, cell_lat, bucket_ts
            ORDER BY cell_lon, cell_lat, bucket_ts
        """
        base_params["grid_size"] = GRID_SIZE_DEG
        rows = conn.execute(text(agg_sql), base_params).fetchall()

        by_cell: dict[tuple[float, float], list[int]] = defaultdict(list)
        for r in rows:
            clon, clat, _, cnt = r[0], r[1], r[2], int(r[3])
            by_cell[(clon, clat)].append(cnt)

        points: list[dict[str, Any]] = []
        for (clon, clat), counts in by_cell.items():
            anomaly_hits, weight = _zscore_anomaly_weight(counts, threshold)
            if weight > 0:
                points.append({"lat": round(clat, 6), "lon": round(clon, 6), "weight": int(weight)})

        points.sort(key=lambda p: -p["weight"])
        points = points[:top_n]

        meta = {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": anchor_ts_str,
            "window": effective_window,
            "response_cache": "miss",
        }

        payload = {
            "points": points,
            "meta": meta,
        }
        resp_cache.set(resp_key, payload, ANOMALY_HEATMAP_TTL)
        return payload


def _empty_heatmap_payload(request: Request) -> dict[str, Any]:
    """Return empty heatmap when no data."""
    return {
        "points": [],
        "meta": {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": None,
            "window": {"start_ts": None, "end_ts": None},
            "response_cache": "miss",
        },
    }

"""
Phase 5.6: Early Warning Indicators — on-demand warning cards (zones scope).
GET /api/warnings
"""
from collections import defaultdict
from datetime import datetime, timedelta
from math import sqrt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit
from app.utils.response_cache import get_response_cache, make_response_key
from app.utils.time_anchor import to_utc_iso

from app.routers.zones_analytics import _compute_trend
from app.routers.zones_compare import WOW_DAYS, MOM_DAYS, _delta_percent_safe
from app.routers.anomalies import GRID_SIZE_DEG

WARNINGS_TTL = 90
TOP_ZONES_K = 50
ANOMALY_Z_THRESHOLD = 3.0
ANOMALY_CLUSTER_MIN_CELLS = 1


router = APIRouter(prefix="/api/warnings", tags=["warnings"])


def _warnings_signature(
    scope: str,
    bbox: str | None,
    start_ts: str | None,
    end_ts: str | None,
    limit: int,
) -> str:
    """Deterministic signature for warnings cache key."""
    return f"sc{scope}|b{bbox or ''}|s{start_ts or ''}|e{end_ts or ''}|l{limit}"


def _zscore_anomaly_cells(counts: list[int], threshold: float) -> int:
    """Count buckets where z >= threshold. stddev=0 -> 0."""
    if not counts or len(counts) < 2:
        return 0
    n = len(counts)
    mean = sum(counts) / n
    variance = sum((x - mean) ** 2 for x in counts) / n
    stddev = sqrt(variance)
    if stddev <= 0:
        return 0
    return sum(1 for c in counts if (c - mean) / stddev >= threshold)


def _severity_trend_up(pct: float) -> str:
    if pct >= 50:
        return "high"
    if pct >= 20:
        return "medium"
    return "low"


def _severity_spike(delta_percent: float, wow: bool) -> str:
    if wow:
        if delta_percent >= 80:
            return "high"
        if delta_percent >= 40:
            return "medium"
        return "low"
    if delta_percent >= 100:
        return "high"
    if delta_percent >= 50:
        return "medium"
    return "low"


def _severity_anomaly(cell_count: int) -> str:
    if cell_count >= 11:
        return "high"
    if cell_count >= 4:
        return "medium"
    return "low"


@router.get("", dependencies=[Depends(rate_limit("stats"))])
def get_warnings(
    request: Request,
    scope: str = Query("zones", description="zones | viewport"),
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat (viewport only)"),
    start_ts: datetime | None = Query(None),
    end_ts: datetime | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """
    Early warning indicators: zones (or viewport) that need attention.
    Zones scope: trend_up, wow_spike, mom_spike, anomaly_cluster.
    Viewport scope: 422 (not implemented).
    """
    if scope not in ("zones", "viewport"):
        raise HTTPException(status_code=422, detail="scope must be 'zones' or 'viewport'")
    if scope == "viewport":
        raise HTTPException(status_code=422, detail="viewport scope not implemented; use scope=zones")
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise HTTPException(status_code=422, detail="start_ts must be <= end_ts")

    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        base_params: dict[str, Any] = {}

        if start_ts is not None and end_ts is not None:
            effective_start = start_ts
            effective_end = end_ts
            anchor_ts = end_ts
            base_params["start_ts"] = start_ts
            base_params["end_ts"] = end_ts
        else:
            range_row = conn.execute(
                text("SELECT MIN(occurred_at), MAX(occurred_at) FROM violations"),
                base_params,
            ).fetchone()
            data_max = range_row[1] if range_row and range_row[1] else None
            if not data_max:
                payload = _empty_warnings_payload(request)
                return payload
            anchor_ts = data_max
            effective_end = data_max
            data_min = range_row[0] if range_row and range_row[0] else None
            effective_start = data_min if data_min else effective_end
            base_params["start_ts"] = effective_start
            base_params["end_ts"] = effective_end

        anchor_ts_str = to_utc_iso(anchor_ts)
        effective_window = {"start_ts": to_utc_iso(effective_start), "end_ts": to_utc_iso(effective_end)}
        sig = _warnings_signature(
            scope,
            bbox,
            to_utc_iso(start_ts) if start_ts else None,
            to_utc_iso(end_ts) if end_ts else None,
            limit,
        )
        resp_key = make_response_key("warnings", sig, anchor_ts_str, effective_window)
        resp_cache = get_response_cache()
        cached = resp_cache.get(resp_key)
        if cached is not None:
            request.state.response_cache_hit = True
            out = dict(cached)
            out["meta"] = {**cached.get("meta", {}), "response_cache": "hit"}
            return out

        top_zones_sql = """
            SELECT z.id, z.name, z.zone_type
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE v.occurred_at >= :start_ts AND v.occurred_at <= :end_ts
            GROUP BY z.id, z.name, z.zone_type
            ORDER BY COUNT(*) DESC
            LIMIT :k
        """
        base_params["k"] = TOP_ZONES_K
        zone_rows = conn.execute(text(top_zones_sql), base_params).fetchall()
        if not zone_rows:
            payload = _empty_warnings_payload(request, anchor_ts_str, effective_window)
            resp_cache.set(resp_key, payload, WARNINGS_TTL)
            return payload

        zone_ids = [r[0] for r in zone_rows]
        zones_by_id = {r[0]: {"id": r[0], "name": r[1], "zone_type": r[2]} for r in zone_rows}

        ts_sql = """
            SELECT z.id, date_trunc('day', v.occurred_at) AS bucket_ts, COUNT(*)::int AS cnt
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE z.id = ANY(:zone_ids) AND v.occurred_at >= :start_ts AND v.occurred_at <= :end_ts
            GROUP BY z.id, date_trunc('day', v.occurred_at)
            ORDER BY z.id, bucket_ts
        """
        base_params["zone_ids"] = zone_ids
        ts_rows = conn.execute(text(ts_sql), base_params).fetchall()

        wow_start = effective_end - timedelta(days=WOW_DAYS)
        wow_prev_end = wow_start
        wow_prev_start = wow_prev_end - timedelta(days=WOW_DAYS)
        mom_start = effective_end - timedelta(days=MOM_DAYS)
        mom_prev_end = mom_start
        mom_prev_start = mom_prev_end - timedelta(days=MOM_DAYS)

        wow_mom_params = {
            **base_params,
            "wow_curr_start": wow_start,
            "wow_curr_end": effective_end,
            "wow_prev_start": wow_prev_start,
            "wow_prev_end": wow_prev_end,
            "mom_curr_start": mom_start,
            "mom_curr_end": effective_end,
            "mom_prev_start": mom_prev_start,
            "mom_prev_end": mom_prev_end,
        }

        wow_mom_sql = """
            SELECT z.id,
                   SUM(CASE WHEN v.occurred_at >= :wow_curr_start AND v.occurred_at <= :wow_curr_end THEN 1 ELSE 0 END)::int AS wow_curr,
                   SUM(CASE WHEN v.occurred_at >= :wow_prev_start AND v.occurred_at < :wow_prev_end THEN 1 ELSE 0 END)::int AS wow_prev,
                   SUM(CASE WHEN v.occurred_at >= :mom_curr_start AND v.occurred_at <= :mom_curr_end THEN 1 ELSE 0 END)::int AS mom_curr,
                   SUM(CASE WHEN v.occurred_at >= :mom_prev_start AND v.occurred_at < :mom_prev_end THEN 1 ELSE 0 END)::int AS mom_prev
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE z.id = ANY(:zone_ids)
              AND v.occurred_at >= :mom_prev_start AND v.occurred_at <= :mom_curr_end
            GROUP BY z.id
        """
        wow_mom_rows = conn.execute(text(wow_mom_sql), wow_mom_params).fetchall()
        wow_mom_by_zone = {r[0]: (int(r[1]), int(r[2]), int(r[3]), int(r[4])) for r in wow_mom_rows}

        by_zone_ts: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in ts_rows:
            zid, bucket_ts, cnt = r[0], r[1], int(r[2])
            by_zone_ts[zid].append({"bucket_ts": bucket_ts, "count": cnt})

        grid_sql = f"""
            SELECT ST_X(ST_SnapToGrid(geom, :grid_size)) AS cell_lon,
                   ST_Y(ST_SnapToGrid(geom, :grid_size)) AS cell_lat,
                   date_trunc('day', occurred_at) AS bucket_ts,
                   COUNT(*)::int AS cnt
            FROM violations
            WHERE occurred_at >= :start_ts AND occurred_at <= :end_ts
            GROUP BY cell_lon, cell_lat, bucket_ts
        """
        grid_params = {**base_params, "grid_size": GRID_SIZE_DEG}
        grid_rows = conn.execute(text(grid_sql), grid_params).fetchall()

        by_cell: dict[tuple[float, float], list[int]] = defaultdict(list)
        for r in grid_rows:
            clon, clat, _, cnt = r[0], r[1], r[2], int(r[3])
            by_cell[(clon, clat)].append(cnt)

        anomaly_cells: list[tuple[float, float]] = []
        for (clon, clat), counts in by_cell.items():
            if _zscore_anomaly_cells(counts, ANOMALY_Z_THRESHOLD) >= 1:
                anomaly_cells.append((clon, clat))

        zone_anomaly_count: dict[int, int] = {}
        if anomaly_cells and zone_ids:
            max_cells = 500
            cells = anomaly_cells[:max_cells]
            values = ", ".join(f"({lon!r}::float, {lat!r}::float)" for lon, lat in cells)
            zone_anom_sql = f"""
                SELECT z.id, COUNT(*)::int AS cnt
                FROM zones z
                CROSS JOIN (VALUES {values}) AS p(cell_lon, cell_lat)
                WHERE z.id = ANY(:zone_ids)
                  AND ST_Contains(z.geom, ST_SetSRID(ST_MakePoint(p.cell_lon, p.cell_lat), 4326))
                GROUP BY z.id
            """
            zone_anom_params = {"zone_ids": zone_ids}
            for r in conn.execute(text(zone_anom_sql), zone_anom_params).fetchall():
                zone_anomaly_count[r[0]] = int(r[1])
        for zid in zone_ids:
            zone_anomaly_count.setdefault(zid, 0)

        warnings: list[dict[str, Any]] = []

        for zid in zone_ids:
            zone_info = zones_by_id[zid]

            ts_list = sorted(by_zone_ts.get(zid, []), key=lambda x: x["bucket_ts"])
            ts_desc = list(reversed(ts_list))
            trend_dir, trend_pct = _compute_trend(ts_desc)
            if trend_dir == "up" and trend_pct >= 10:
                warnings.append({
                    "warning_type": "trend_up",
                    "severity": _severity_trend_up(trend_pct),
                    "zone": zone_info,
                    "headline": f"Violations trending up {trend_pct:.0f}% in {zone_info['name']}",
                    "details": {"percent_change": trend_pct},
                    "recommendation_hint": "Monitor trend; consider increased patrol presence.",
                })

            wow_curr, wow_prev, mom_curr, mom_prev = wow_mom_by_zone.get(zid, (0, 0, 0, 0))
            wow_pct = _delta_percent_safe(wow_curr, wow_prev)
            if wow_pct >= 20:
                warnings.append({
                    "warning_type": "wow_spike",
                    "severity": _severity_spike(wow_pct, True),
                    "zone": zone_info,
                    "headline": f"Week-over-week spike +{wow_pct:.0f}% in {zone_info['name']}",
                    "details": {"delta_percent": wow_pct, "current_count": wow_curr, "previous_count": wow_prev},
                    "recommendation_hint": "Investigate cause of weekly spike.",
                })

            mom_pct = _delta_percent_safe(mom_curr, mom_prev)
            if mom_pct >= 30:
                warnings.append({
                    "warning_type": "mom_spike",
                    "severity": _severity_spike(mom_pct, False),
                    "zone": zone_info,
                    "headline": f"Month-over-month spike +{mom_pct:.0f}% in {zone_info['name']}",
                    "details": {"delta_percent": mom_pct, "current_count": mom_curr, "previous_count": mom_prev},
                    "recommendation_hint": "Review monthly trend; consider resource allocation.",
                })

            anom_count = zone_anomaly_count.get(zid, 0)
            if anom_count >= ANOMALY_CLUSTER_MIN_CELLS:
                warnings.append({
                    "warning_type": "anomaly_cluster",
                    "severity": _severity_anomaly(anom_count),
                    "zone": zone_info,
                    "headline": f"Anomaly cluster ({anom_count} cells) in {zone_info['name']}",
                    "details": {"anomaly_cell_count": anom_count},
                    "recommendation_hint": "Increase patrol presence; investigate hot spots.",
                })

        warnings.sort(key=lambda w: ({"high": 0, "medium": 1, "low": 2}[w["severity"]], w["zone"]["name"]))
        warnings = warnings[:limit]

        meta = {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": anchor_ts_str,
            "response_cache": "miss",
        }

        payload = {"warnings": warnings, "meta": meta}
        resp_cache.set(resp_key, payload, WARNINGS_TTL)
        return payload


def _empty_warnings_payload(
    request: Request,
    anchor_ts: str | None = None,
    window: dict | None = None,
) -> dict[str, Any]:
    """Return empty warnings payload."""
    return {
        "warnings": [],
        "meta": {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": anchor_ts,
            "response_cache": "miss",
        },
    }

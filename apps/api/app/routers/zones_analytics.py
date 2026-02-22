"""
Phase 5.2: Zone-level analytics — violations in a zone aggregated by time, top types, trend.
GET /api/zones/{zone_id}/analytics
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit
from app.utils.response_cache import get_response_cache, make_response_key
from app.utils.time_anchor import build_time_window_meta, to_utc_iso

ZONE_ANALYTICS_TTL = 90

router = APIRouter(prefix="/api/zones", tags=["zones"])


def _zone_analytics_meta(request: Request, anchor_ts: str | None = None) -> dict:
    """Meta with request_id and optional anchor_ts."""
    meta: dict[str, Any] = {}
    if hasattr(request.state, "request_id"):
        meta["request_id"] = getattr(request.state, "request_id", None)
    if anchor_ts is not None:
        meta["anchor_ts"] = anchor_ts
    return meta


def _compute_trend(time_series: list[dict[str, Any]], short_n: int = 7, long_n: int = 21) -> tuple[str, float]:
    """
    Compute trend from time_series (ordered by bucket_ts desc for most recent first).
    short_n: last N buckets for short avg.
    long_n: previous N buckets for long avg (before short window).
    Returns (trend_direction, percent_change).
    """
    counts = [x.get("count", 0) for x in time_series if isinstance(x.get("count"), (int, float))]
    if len(counts) < short_n + 1:
        return ("flat", 0.0)
    short_vals = counts[:short_n]
    long_vals = counts[short_n : short_n + long_n]
    if not long_vals:
        return ("flat", 0.0)
    short_avg = sum(short_vals) / len(short_vals)
    long_avg = sum(long_vals) / len(long_vals)
    if long_avg <= 0:
        return ("flat", 0.0)
    pct = ((short_avg - long_avg) / long_avg) * 100.0
    if pct > 5.0:
        return ("up", round(pct, 2))
    if pct < -5.0:
        return ("down", round(pct, 2))
    return ("flat", round(pct, 2))


def _zone_analytics_signature(
    zone_id: int,
    start_ts: str | None,
    end_ts: str | None,
    granularity: str,
) -> str:
    """Deterministic signature for zone analytics cache key."""
    return f"z{zone_id}|s{start_ts or ''}|e{end_ts or ''}|g{granularity}"


@router.get("/{zone_id}/analytics", dependencies=[Depends(rate_limit("stats"))])
def get_zone_analytics(
    request: Request,
    zone_id: int,
    start_ts: datetime | None = Query(None, description="Start of time window (ISO)"),
    end_ts: datetime | None = Query(None, description="End of time window (ISO)"),
    granularity: str = Query("day", description="hour | day"),
) -> dict[str, Any]:
    """
    Zone-level analytics: violations inside the zone, aggregated by time, top types, trend.
    Uses ST_Intersects(zone.geom, violations.geom).
    """
    if granularity not in ("hour", "day"):
        raise HTTPException(status_code=422, detail="granularity must be 'hour' or 'day'")
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise HTTPException(status_code=422, detail="start_ts must be <= end_ts")

    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        zone_row = conn.execute(
            text("SELECT id, name, zone_type FROM zones WHERE id = :id"),
            {"id": zone_id},
        ).fetchone()
        if not zone_row:
            raise HTTPException(status_code=404, detail="Zone not found")

        zone_info = {"id": zone_row[0], "name": zone_row[1], "zone_type": zone_row[2]}

        zone_filter = """
            FROM violations v
            INNER JOIN zones z ON z.id = :zone_id AND ST_Intersects(z.geom, v.geom)
        """
        base_params: dict[str, Any] = {"zone_id": zone_id}

        time_clauses: list[str] = []
        if start_ts is not None:
            time_clauses.append("v.occurred_at >= :start_ts")
            base_params["start_ts"] = start_ts
        if end_ts is not None:
            time_clauses.append("v.occurred_at <= :end_ts")
            base_params["end_ts"] = end_ts
        time_where = " AND " + " AND ".join(time_clauses) if time_clauses else ""

        if not time_clauses:
            data_range = conn.execute(
                text(f"""
                    SELECT MIN(v.occurred_at), MAX(v.occurred_at)
                    {zone_filter}
                """),
                base_params,
            ).fetchone()
            data_min, data_max = (data_range[0] if data_range else None, data_range[1] if data_range else None)
            effective_start = data_min
            effective_end = data_max
            anchor_ts = data_max
        else:
            effective_start = start_ts
            effective_end = end_ts
            anchor_ts = end_ts
            data_min, data_max = start_ts, end_ts

        anchor_ts_str = to_utc_iso(anchor_ts) if anchor_ts else None
        effective_window = {
            "start_ts": to_utc_iso(effective_start) if effective_start else None,
            "end_ts": to_utc_iso(effective_end) if effective_end else None,
        }
        sig = _zone_analytics_signature(
            zone_id,
            to_utc_iso(start_ts) if start_ts else None,
            to_utc_iso(end_ts) if end_ts else None,
            granularity,
        )
        resp_key = make_response_key("zone_analytics", sig, anchor_ts_str, effective_window)
        resp_cache = get_response_cache()
        cached = resp_cache.get(resp_key)
        if cached is not None:
            request.state.response_cache_hit = True
            out = dict(cached)
            out["meta"] = {**cached.get("meta", {}), "response_cache": "hit"}
            return out

        trunc = "hour" if granularity == "hour" else "day"
        trunc_sql = f"date_trunc('{trunc}', v.occurred_at)"

        time_where_sql = (" WHERE " + time_where.lstrip(" AND ")) if time_where else ""
        total_sql = f"SELECT COUNT(*)::int {zone_filter}{time_where_sql}"
        total_row = conn.execute(text(total_sql), base_params).fetchone()
        total_count = total_row[0] or 0 if total_row else 0

        time_series_sql = f"""
            SELECT {trunc_sql} AS bucket_ts, COUNT(*)::int AS cnt
            {zone_filter}
            {time_where_sql}
            GROUP BY {trunc_sql}
            ORDER BY bucket_ts ASC
        """
        ts_rows = conn.execute(text(time_series_sql), base_params).fetchall()
        def _ts_iso(val: Any) -> str:
            if val is None:
                return ""
            if hasattr(val, "isoformat"):
                s = val.isoformat()
                return s + "Z" if "Z" not in s and "+" not in s else s
            return str(val)

        time_series = [{"bucket_ts": _ts_iso(r[0]), "count": int(r[1])} for r in ts_rows]

        top_sql = f"""
            SELECT v.violation_type, COUNT(*)::int AS cnt
            {zone_filter}
            {time_where_sql}
            GROUP BY v.violation_type
            ORDER BY cnt DESC
            LIMIT 5
        """
        top_rows = conn.execute(text(top_sql), base_params).fetchall()
        top_violation_types = [{"violation_type": row[0] or "", "count": int(row[1])} for row in top_rows]

        time_series_desc = list(reversed(time_series))
        trend_direction, percent_change = _compute_trend(time_series_desc)

        time_meta = build_time_window_meta(
            data_min_ts=data_min,
            data_max_ts=data_max,
            anchor_ts=anchor_ts,
            effective_start_ts=effective_start,
            effective_end_ts=effective_end,
            window_source="absolute" if (start_ts and end_ts) else "anchored",
        )

        meta = {
            **_zone_analytics_meta(request, anchor_ts_str),
            **time_meta,
            "response_cache": "miss",
        }

        payload = {
            "zone": zone_info,
            "summary": {
                "total_count": total_count,
                "trend_direction": trend_direction,
                "percent_change": percent_change,
            },
            "time_series": time_series,
            "top_violation_types": top_violation_types,
            "meta": meta,
        }
        resp_cache.set(resp_key, payload, ZONE_ANALYTICS_TTL)
        return payload

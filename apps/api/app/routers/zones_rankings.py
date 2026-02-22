"""
Phase 5.3: Zone ranking — compare zones by risk, trend, or volume.
GET /api/zones/rankings
"""
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit
from app.utils.response_cache import get_response_cache, make_response_key
from app.utils.time_anchor import to_utc_iso

from app.routers.zones_analytics import _compute_trend

ZONE_RANKINGS_TTL = 90

router = APIRouter(prefix="/api/zones", tags=["zones"])


def _rankings_signature(
    start_ts: str | None,
    end_ts: str | None,
    granularity: str,
    limit: int,
    sort_by: str,
) -> str:
    """Deterministic signature for rankings cache key."""
    return f"s{start_ts or ''}|e{end_ts or ''}|g{granularity}|l{limit}|sb{sort_by}"


def _min_max_normalize(val: float, min_v: float, max_v: float) -> float:
    """Min-max scale to [0, 1]. Returns 0 if range is 0."""
    if max_v <= min_v:
        return 0.0
    return (val - min_v) / (max_v - min_v)


@router.get("/rankings", dependencies=[Depends(rate_limit("stats"))])
def get_zone_rankings(
    request: Request,
    start_ts: datetime | None = Query(None, description="Start of time window (ISO)"),
    end_ts: datetime | None = Query(None, description="End of time window (ISO)"),
    granularity: str = Query("day", description="hour | day"),
    limit: int = Query(10, ge=1, le=100),
    sort_by: str = Query("risk", description="risk | trend | volume"),
) -> dict[str, Any]:
    """
    Zone rankings: compare zones by risk (volume + positive trend), trend, or volume.
    Uses ST_Intersects for spatial filtering.
    """
    if granularity not in ("hour", "day"):
        raise HTTPException(status_code=422, detail="granularity must be 'hour' or 'day'")
    if sort_by not in ("risk", "trend", "volume"):
        raise HTTPException(status_code=422, detail="sort_by must be 'risk', 'trend', or 'volume'")
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise HTTPException(status_code=422, detail="start_ts must be <= end_ts")

    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        time_clauses: list[str] = []
        base_params: dict[str, Any] = {}
        if start_ts is not None:
            time_clauses.append("v.occurred_at >= :start_ts")
            base_params["start_ts"] = start_ts
        if end_ts is not None:
            time_clauses.append("v.occurred_at <= :end_ts")
            base_params["end_ts"] = end_ts
        time_where = (" AND " + " AND ".join(time_clauses)) if time_clauses else ""

        if not time_clauses:
            data_range = conn.execute(
                text("""
                    SELECT MIN(v.occurred_at), MAX(v.occurred_at)
                    FROM violations v
                    INNER JOIN zones z ON ST_Intersects(z.geom, v.geom)
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
        sig = _rankings_signature(
            to_utc_iso(start_ts) if start_ts else None,
            to_utc_iso(end_ts) if end_ts else None,
            granularity,
            limit,
            sort_by,
        )
        resp_key = make_response_key("zone_rankings", sig, anchor_ts_str, effective_window)
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

        rows_sql = f"""
            SELECT z.id, z.name, z.zone_type,
                   {trunc_sql} AS bucket_ts,
                   COUNT(*)::int AS cnt
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            {time_where_sql}
            GROUP BY z.id, z.name, z.zone_type, {trunc_sql}
            ORDER BY z.id, bucket_ts ASC
        """
        rows = conn.execute(text(rows_sql), base_params).fetchall()

        by_zone: dict[int, dict[str, Any]] = defaultdict(lambda: {"time_series": [], "total_count": 0})
        def _ts_iso(val: Any) -> str:
            if val is None:
                return ""
            if hasattr(val, "isoformat"):
                s = val.isoformat()
                return s + "Z" if "Z" not in s and "+" not in s else s
            return str(val)

        for r in rows:
            zid, name, zone_type, bucket_ts, cnt = r[0], r[1], r[2], r[3], int(r[4])
            if zid not in by_zone:
                by_zone[zid]["zone_id"] = zid
                by_zone[zid]["name"] = name
                by_zone[zid]["zone_type"] = zone_type
            by_zone[zid]["total_count"] += cnt
            by_zone[zid]["time_series"].append({"bucket_ts": _ts_iso(bucket_ts), "count": cnt})

        rankings_raw: list[dict[str, Any]] = []
        for zid, data in by_zone.items():
            ts = data["time_series"]
            ts_sorted = sorted(ts, key=lambda x: x["bucket_ts"])
            ts_desc = list(reversed(ts_sorted))
            trend_dir, pct = _compute_trend(ts_desc)
            rankings_raw.append({
                "zone_id": zid,
                "name": data["name"],
                "zone_type": data["zone_type"],
                "total_count": data["total_count"],
                "trend_direction": trend_dir,
                "percent_change": pct,
                "score": 0.0,
            })

        if not rankings_raw:
            payload = {
                "rankings": [],
                "meta": {
                    "request_id": getattr(request.state, "request_id", None),
                    "anchor_ts": anchor_ts_str,
                    "response_cache": "miss",
                },
            }
            resp_cache.set(resp_key, payload, ZONE_RANKINGS_TTL)
            return payload

        total_counts = [r["total_count"] for r in rankings_raw]
        pct_positive = [max(0, r["percent_change"]) for r in rankings_raw]
        min_total = min(total_counts)
        max_total = max(total_counts)
        min_pct = min(pct_positive)
        max_pct = max(pct_positive)

        for r in rankings_raw:
            if sort_by == "risk":
                norm_vol = _min_max_normalize(r["total_count"], min_total, max_total)
                norm_trend = _min_max_normalize(max(0, r["percent_change"]), min_pct, max_pct)
                r["score"] = round(norm_vol + norm_trend, 4)
            elif sort_by == "trend":
                r["score"] = round(r["percent_change"], 4)
            else:
                r["score"] = r["total_count"]

        rankings_raw.sort(key=lambda x: x["score"], reverse=True)
        rankings = rankings_raw[:limit]

        meta = {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": anchor_ts_str,
            "response_cache": "miss",
        }

        payload = {
            "rankings": rankings,
            "meta": meta,
        }
        resp_cache.set(resp_key, payload, ZONE_RANKINGS_TTL)
        return payload

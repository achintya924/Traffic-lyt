"""
Phase 5.4: Zone WoW/MoM comparison — current vs previous period.
GET /api/zones/{zone_id}/compare
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit
from app.utils.response_cache import get_response_cache, make_response_key
from app.utils.time_anchor import to_utc_iso

ZONE_COMPARE_TTL = 90

router = APIRouter(prefix="/api/zones", tags=["zones"])

WOW_DAYS = 7
MOM_DAYS = 30


def _compare_signature(
    zone_id: int,
    period: str,
    granularity: str,
    start_ts: str | None,
    end_ts: str | None,
) -> str:
    """Deterministic signature for compare cache key."""
    return f"z{zone_id}|p{period}|g{granularity}|s{start_ts or ''}|e{end_ts or ''}"


def _ts_iso(val: Any) -> str:
    """Serialize timestamp to ISO string."""
    if val is None:
        return ""
    if hasattr(val, "isoformat"):
        s = val.isoformat()
        return s + "Z" if "Z" not in s and "+" not in s else s
    return str(val)


def _trend_label(delta_percent: float, threshold: float = 5.0) -> str:
    """Map delta_percent to up|down|flat."""
    if delta_percent > threshold:
        return "up"
    if delta_percent < -threshold:
        return "down"
    return "flat"


def _delta_percent_safe(current: int, previous: int) -> float:
    """Percent change; 0 if previous is 0."""
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / previous) * 100.0, 2)


@router.get("/{zone_id}/compare", dependencies=[Depends(rate_limit("stats"))])
def get_zone_compare(
    request: Request,
    zone_id: int,
    period: str = Query(..., description="wow | mom"),
    granularity: str = Query("day", description="day | hour"),
    start_ts: datetime | None = Query(None, description="Current window start (optional)"),
    end_ts: datetime | None = Query(None, description="Current window end (optional)"),
) -> dict[str, Any]:
    """
    Zone WoW/MoM comparison: current vs previous period.
    WoW: 7-day windows. MoM: 30-day windows.
    Uses ST_Intersects for spatial filtering.
    """
    if period not in ("wow", "mom"):
        raise HTTPException(status_code=422, detail="period must be 'wow' or 'mom'")
    if granularity not in ("hour", "day"):
        raise HTTPException(status_code=422, detail="granularity must be 'hour' or 'day'")
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise HTTPException(status_code=422, detail="start_ts must be <= end_ts")

    duration_days = WOW_DAYS if period == "wow" else MOM_DAYS
    duration = timedelta(days=duration_days)

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

        if start_ts is not None and end_ts is not None:
            current_start = start_ts
            current_end = end_ts
            previous_end = start_ts
            previous_start = previous_end - duration
            anchor_ts = end_ts
        else:
            data_range = conn.execute(
                text(f"""
                    SELECT MIN(v.occurred_at), MAX(v.occurred_at)
                    {zone_filter}
                """),
                base_params,
            ).fetchone()
            data_max = data_range[1] if data_range and data_range[1] else None
            if not data_max:
                payload = _empty_compare_payload(zone_info, period, request)
                return payload
            anchor_ts = data_max
            current_end = data_max
            current_start = current_end - duration
            previous_end = current_start
            previous_start = previous_end - duration

        anchor_ts_str = to_utc_iso(anchor_ts)
        effective_window = {
            "start_ts": to_utc_iso(previous_start),
            "end_ts": to_utc_iso(current_end),
        }
        sig = _compare_signature(
            zone_id,
            period,
            granularity,
            to_utc_iso(start_ts) if start_ts else None,
            to_utc_iso(end_ts) if end_ts else None,
        )
        resp_key = make_response_key("zone_compare", sig, anchor_ts_str, effective_window)
        resp_cache = get_response_cache()
        cached = resp_cache.get(resp_key)
        if cached is not None:
            request.state.response_cache_hit = True
            out = dict(cached)
            out["meta"] = {**cached.get("meta", {}), "response_cache": "hit"}
            return out

        trunc = "hour" if granularity == "hour" else "day"
        trunc_sql = f"date_trunc('{trunc}', v.occurred_at)"

        base_params["prev_start"] = previous_start
        base_params["prev_end"] = previous_end
        base_params["curr_start"] = current_start
        base_params["curr_end"] = current_end

        agg_sql = f"""
            SELECT
                CASE
                    WHEN v.occurred_at >= :curr_start AND v.occurred_at <= :curr_end THEN 'current'
                    ELSE 'previous'
                END AS win,
                {trunc_sql} AS bucket_ts,
                v.violation_type,
                COUNT(*)::int AS cnt
            {zone_filter}
            WHERE v.occurred_at >= :prev_start AND v.occurred_at <= :curr_end
            GROUP BY 1, 2, 3
            ORDER BY win, bucket_ts, cnt DESC
        """
        rows = conn.execute(text(agg_sql), base_params).fetchall()

        current_by_bucket: dict[str, int] = defaultdict(int)
        current_by_type: dict[str, int] = defaultdict(int)
        previous_by_bucket: dict[str, int] = defaultdict(int)
        previous_by_type: dict[str, int] = defaultdict(int)

        for r in rows:
            win, bucket_ts, vtype, cnt = r[0], r[1], r[2] or "", int(r[3])
            ts_str = _ts_iso(bucket_ts)
            if win == "current":
                current_by_bucket[ts_str] += cnt
                current_by_type[vtype] += cnt
            else:
                previous_by_bucket[ts_str] += cnt
                previous_by_type[vtype] += cnt

        current_total = sum(current_by_bucket.values())
        previous_total = sum(previous_by_bucket.values())

        current_ts = [
            {"bucket_ts": ts, "count": c}
            for ts, c in sorted(current_by_bucket.items(), key=lambda x: x[0])
        ]
        previous_ts = [
            {"bucket_ts": ts, "count": c}
            for ts, c in sorted(previous_by_bucket.items(), key=lambda x: x[0])
        ]

        current_top = sorted(
            [{"violation_type": k, "count": v} for k, v in current_by_type.items()],
            key=lambda x: -x["count"],
        )[:5]
        previous_top = sorted(
            [{"violation_type": k, "count": v} for k, v in previous_by_type.items()],
            key=lambda x: -x["count"],
        )[:5]

        all_types = set(current_by_type.keys()) | set(previous_by_type.keys())
        shifts = []
        for vtype in sorted(all_types, key=lambda t: -(current_by_type.get(t, 0) + previous_by_type.get(t, 0)))[:10]:
            curr = current_by_type.get(vtype, 0)
            prev = previous_by_type.get(vtype, 0)
            delta = curr - prev
            dp = _delta_percent_safe(curr, prev)
            shifts.append({
                "violation_type": vtype,
                "current": curr,
                "previous": prev,
                "delta": delta,
                "delta_percent": dp,
            })

        delta_count = current_total - previous_total
        delta_percent = _delta_percent_safe(current_total, previous_total)
        trend_label = _trend_label(delta_percent)

        meta = {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": anchor_ts_str,
            "response_cache": "miss",
        }

        payload = {
            "zone": zone_info,
            "period": period,
            "current": {
                "window": {"start_ts": to_utc_iso(current_start), "end_ts": to_utc_iso(current_end)},
                "total_count": current_total,
                "time_series": current_ts,
                "top_violation_types": current_top,
            },
            "previous": {
                "window": {"start_ts": to_utc_iso(previous_start), "end_ts": to_utc_iso(previous_end)},
                "total_count": previous_total,
                "time_series": previous_ts,
                "top_violation_types": previous_top,
            },
            "delta": {
                "delta_count": delta_count,
                "delta_percent": delta_percent,
                "trend_label": trend_label,
                "violation_type_shifts": shifts,
            },
            "meta": meta,
        }
        resp_cache.set(resp_key, payload, ZONE_COMPARE_TTL)
        return payload


def _empty_compare_payload(
    zone_info: dict,
    period: str,
    request: Request,
) -> dict[str, Any]:
    """Return empty compare payload when no data in zone."""
    return {
        "zone": zone_info,
        "period": period,
        "current": {
            "window": {"start_ts": None, "end_ts": None},
            "total_count": 0,
            "time_series": [],
            "top_violation_types": [],
        },
        "previous": {
            "window": {"start_ts": None, "end_ts": None},
            "total_count": 0,
            "time_series": [],
            "top_violation_types": [],
        },
        "delta": {
            "delta_count": 0,
            "delta_percent": 0.0,
            "trend_label": "flat",
            "violation_type_shifts": [],
        },
        "meta": {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": None,
            "response_cache": "miss",
        },
    }

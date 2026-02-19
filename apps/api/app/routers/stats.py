"""
GET /violations/stats — totals and top violation types with optional filters.
Phase 4.1: response includes meta with data_min_ts, data_max_ts, effective_window, window_source, timezone.
Phase 4.3: response-level cache; meta.response_cache on every 200 response.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit
from app.utils.response_cache import get_response_cache, make_response_key, short_hash
from app.utils.signature import request_signature_stats
from app.utils.time_anchor import (
    build_time_window_meta,
    compute_anchored_window,
    get_data_time_range,
)
from app.utils.violation_filters import ViolationFilters, build_violation_where, get_violation_filters

router = APIRouter(prefix="/violations", tags=["violations"])

STATS_RESPONSE_TTL = 60

_empty_meta = build_time_window_meta(
    data_min_ts=None,
    data_max_ts=None,
    anchor_ts=None,
    effective_start_ts=None,
    effective_end_ts=None,
    window_source="anchored",
    message="No connection.",
)


@router.get("/stats", dependencies=[Depends(rate_limit("stats"))])
def violations_stats(
    filters: ViolationFilters = Depends(get_violation_filters),
) -> dict[str, Any]:
    _no_conn_rc = {"hit": False, "key_hash": None, "ttl_seconds": STATS_RESPONSE_TTL}
    engine = get_engine()
    if engine is None:
        return {"total": 0, "min_time": None, "max_time": None, "top_types": [], "meta": {**_empty_meta, "response_cache": _no_conn_rc}}

    where_sql, params = build_violation_where(filters)

    totals_sql = f"""
        SELECT
            COUNT(*)::int AS total,
            MIN(occurred_at) AS min_time,
            MAX(occurred_at) AS max_time
        FROM violations
        {where_sql}
    """
    top_types_sql = f"""
        SELECT violation_type, COUNT(*)::int AS count
        FROM violations
        {where_sql}
        GROUP BY violation_type
        ORDER BY count DESC
        LIMIT 10
    """

    try:
        with get_connection() as conn:
            if conn is None:
                return {"total": 0, "min_time": None, "max_time": None, "top_types": [], "meta": {**_empty_meta, "response_cache": _no_conn_rc}}

            data_min_ts, data_max_ts = get_data_time_range(conn, filters)
            effective_start, effective_end, anchor_ts, window_source = compute_anchored_window(
                filters, data_min_ts, data_max_ts
            )
            time_meta = build_time_window_meta(
                data_min_ts=data_min_ts,
                data_max_ts=data_max_ts,
                anchor_ts=anchor_ts,
                effective_start_ts=effective_start,
                effective_end_ts=effective_end,
                window_source=window_source,
                message="No data for the given filter scope." if data_max_ts is None else None,
            )
            anchor_ts_str = time_meta.get("anchor_ts") or time_meta.get("data_max_ts")
            effective_window = time_meta.get("effective_window")
            sig = request_signature_stats(
                anchor_ts=anchor_ts_str,
                bbox=filters.bbox,
                violation_type=filters.violation_type,
                hour_start=filters.hour_start,
                hour_end=filters.hour_end,
                start_iso=filters.start.isoformat() if filters.start else None,
                end_iso=filters.end.isoformat() if filters.end else None,
            )
            resp_key = make_response_key("stats", sig, anchor_ts_str, effective_window)
            resp_cache = get_response_cache()
            cached = resp_cache.get(resp_key)
            if cached is not None:
                out = dict(cached)
                out["meta"] = {**cached.get("meta", {}), "response_cache": {"hit": True, "key_hash": short_hash(resp_key), "ttl_seconds": STATS_RESPONSE_TTL}}
                return out

            totals_row = conn.execute(text(totals_sql), params).fetchone()
            total = totals_row[0] or 0
            min_time: datetime | None = totals_row[1]
            max_time: datetime | None = totals_row[2]

            if total == 0:
                payload = {
                    "total": 0,
                    "min_time": None,
                    "max_time": None,
                    "top_types": [],
                    "meta": {**time_meta, "response_cache": {"hit": False, "key_hash": short_hash(resp_key), "ttl_seconds": STATS_RESPONSE_TTL}},
                }
                resp_cache.set(resp_key, payload, STATS_RESPONSE_TTL)
                return payload

            top_rows = conn.execute(text(top_types_sql), params).fetchall()
            top_types = [
                {"violation_type": row[0] or "", "count": row[1]}
                for row in top_rows
            ]
            payload = {
                "total": total,
                "min_time": min_time.isoformat() if min_time else None,
                "max_time": max_time.isoformat() if max_time else None,
                "top_types": top_types,
                "meta": {**time_meta, "response_cache": {"hit": False, "key_hash": short_hash(resp_key), "ttl_seconds": STATS_RESPONSE_TTL}},
            }
            resp_cache.set(resp_key, payload, STATS_RESPONSE_TTL)
            return payload
    except Exception:
        return {"total": 0, "min_time": None, "max_time": None, "top_types": [], "meta": {**_empty_meta, "response_cache": _no_conn_rc}}

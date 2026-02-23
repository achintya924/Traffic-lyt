"""
Phase 5.8: Patrol allocation recommendations.
POST /api/patrol/allocate — given N units and a shift window, which zones get coverage and why.
"""
import hashlib
import os
from collections import defaultdict
from datetime import datetime, timedelta
from math import sqrt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.utils.rate_limiter import rate_limit
from app.utils.response_cache import get_response_cache, make_response_key
from app.utils.time_anchor import to_utc_iso

from app.routers.zones_analytics import _compute_trend
from app.routers.zones_compare import WOW_DAYS, MOM_DAYS, _delta_percent_safe
from app.routers.anomalies import GRID_SIZE_DEG

PATROL_ALLOCATE_TTL = 75
TOP_ZONES_K = 50
ANOMALY_Z_THRESHOLD = 3.0
ANOMALY_CLUSTER_MIN_CELLS = 1

router = APIRouter(prefix="/api/patrol", tags=["patrol"])


class PatrolAllocateRequest(BaseModel):
    units: int = Field(..., ge=1, le=50, description="Number of patrol units")
    period: str = Field("current", description="wow | mom | current")
    shift_hours: int = Field(6, ge=1, le=24, description="Shift window length in hours")
    end_ts: datetime | None = Field(None, description="Optional anchor end; else MAX(occurred_at)")
    strategy: str = Field("balanced", description="balanced | risk_max | trend_focus")
    exclude_zone_ids: list[int] = Field(default_factory=list, description="Zones to exclude")


def _canonical_request_dict(body: PatrolAllocateRequest) -> dict[str, Any]:
    """Build canonical dict from parsed model for deterministic cache key."""
    d = body.model_dump(exclude_none=True)
    d["period"] = (d.get("period") or "current").lower()
    d["strategy"] = (d.get("strategy") or "balanced").lower()
    excl = d.get("exclude_zone_ids") or []
    d["exclude_zone_ids"] = tuple(sorted(set(excl)))
    return d


def _patrol_signature(
    canonical: dict[str, Any],
    end_ts_str: str | None,
    anchor_ts: str | None,
) -> str:
    u = canonical.get("units", 0)
    p = canonical.get("period", "current")
    sh = canonical.get("shift_hours", 6)
    s = canonical.get("strategy", "balanced")
    ex = canonical.get("exclude_zone_ids", ())
    ex_str = ",".join(map(str, ex)) if ex else ""
    return f"u{u}|p{p}|sh{sh}|e{end_ts_str or ''}|s{s}|ex{ex_str}|a{anchor_ts or ''}"


def _zscore_anomaly_cells(counts: list[int], threshold: float) -> int:
    if not counts or len(counts) < 2:
        return 0
    n = len(counts)
    mean = sum(counts) / n
    variance = sum((x - mean) ** 2 for x in counts) / n
    stddev = sqrt(variance)
    if stddev <= 0:
        return 0
    return sum(1 for c in counts if (c - mean) / stddev >= threshold)


def _min_max_normalize(val: float, min_v: float, max_v: float) -> float:
    if max_v <= min_v:
        return 0.0
    return (val - min_v) / (max_v - min_v)


def _severity_score(severity: str) -> float:
    """Map severity to 0–1 for scoring."""
    if severity == "high":
        return 1.0
    if severity == "medium":
        return 0.5
    return 0.2


@router.post("/allocate", dependencies=[Depends(rate_limit("stats"))])
def allocate_patrol(request: Request, body: PatrolAllocateRequest) -> dict[str, Any]:
    """
    Patrol allocation: given N units and a shift window, recommend zones for coverage.
    Produces an ordered plan with assigned units, priority scores, and explainable reasons.
    """
    if body.period not in ("wow", "mom", "current"):
        raise HTTPException(status_code=422, detail="period must be 'wow', 'mom', or 'current'")
    if body.strategy not in ("balanced", "risk_max", "trend_focus"):
        raise HTTPException(status_code=422, detail="strategy must be 'balanced', 'risk_max', or 'trend_focus'")

    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with get_connection() as conn:
        if not conn:
            raise HTTPException(status_code=503, detail="Database connection failed")

        base_params: dict[str, Any] = {}
        if body.end_ts is not None:
            anchor_ts = body.end_ts
            effective_end = body.end_ts
            base_params["end_ts"] = body.end_ts
        else:
            row = conn.execute(
                text("SELECT MAX(occurred_at) FROM violations"),
                base_params,
            ).fetchone()
            effective_end = row[0] if row and row[0] else None
            anchor_ts = effective_end
            if not effective_end:
                return _empty_plan(request, anchor_ts)
            base_params["end_ts"] = effective_end

        if body.period == "current":
            effective_start = effective_end - timedelta(hours=body.shift_hours)
        elif body.period == "wow":
            effective_start = effective_end - timedelta(days=WOW_DAYS)
        else:
            effective_start = effective_end - timedelta(days=MOM_DAYS)

        base_params["start_ts"] = effective_start
        anchor_ts_str = to_utc_iso(anchor_ts)
        effective_window = {
            "start_ts": to_utc_iso(effective_start),
            "end_ts": to_utc_iso(effective_end),
        }
        canonical = _canonical_request_dict(body)
        end_ts_str = to_utc_iso(body.end_ts) if body.end_ts is not None else None
        sig = _patrol_signature(canonical, end_ts_str, anchor_ts_str)
        resp_key = make_response_key("patrol_allocate", sig, anchor_ts_str, effective_window)
        key_hash = hashlib.sha256(resp_key.encode()).hexdigest()[:12]

        resp_cache = get_response_cache()
        cached = resp_cache.get(resp_key)
        cache_status = "hit" if cached is not None else "miss"
        print(f"patrol_allocate cache={cache_status} key_hash={key_hash} anchor_ts={anchor_ts_str}", flush=True)

        if cached is not None:
            request.state.response_cache_hit = True
            out = dict(cached)
            out["meta"] = dict(cached.get("meta", {}))
            out["meta"]["response_cache"] = "hit"
            if os.getenv("DEBUG") == "1":
                out["meta"]["cache_key_hash"] = key_hash
            return out

        exclude_set = set(canonical.get("exclude_zone_ids", ()))

        zones_sql = """
            SELECT z.id, z.name, z.zone_type
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE v.occurred_at >= :start_ts AND v.occurred_at <= :end_ts
            GROUP BY z.id, z.name, z.zone_type
            ORDER BY COUNT(*) DESC
            LIMIT :k
        """
        params = {**base_params, "k": TOP_ZONES_K}
        zone_rows = conn.execute(text(zones_sql), params).fetchall()
        if not zone_rows:
            payload = _empty_plan(request, anchor_ts_str)
            if os.getenv("DEBUG") == "1":
                payload["meta"]["cache_key_hash"] = key_hash
            resp_cache.set(resp_key, payload, PATROL_ALLOCATE_TTL)
            return payload

        zones_by_id = {r[0]: {"id": r[0], "name": r[1], "zone_type": r[2]} for r in zone_rows}
        zone_ids = [r[0] for r in zone_rows if r[0] not in exclude_set]
        if not zone_ids:
            payload = _empty_plan(request, anchor_ts_str)
            if os.getenv("DEBUG") == "1":
                payload["meta"]["cache_key_hash"] = key_hash
            resp_cache.set(resp_key, payload, PATROL_ALLOCATE_TTL)
            return payload

        params["zone_ids"] = zone_ids

        ts_sql = """
            SELECT z.id, date_trunc('day', v.occurred_at) AS bucket_ts, COUNT(*)::int AS cnt
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE z.id = ANY(:zone_ids) AND v.occurred_at >= :start_ts AND v.occurred_at <= :end_ts
            GROUP BY z.id, date_trunc('day', v.occurred_at)
            ORDER BY z.id, bucket_ts
        """
        ts_rows = conn.execute(text(ts_sql), params).fetchall()

        wow_start = effective_end - timedelta(days=WOW_DAYS)
        wow_prev_end = wow_start
        wow_prev_start = wow_prev_end - timedelta(days=WOW_DAYS)
        mom_start = effective_end - timedelta(days=MOM_DAYS)
        mom_prev_end = mom_start
        mom_prev_start = mom_prev_end - timedelta(days=MOM_DAYS)

        wow_mom_params = {
            **params,
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

        grid_sql = """
            SELECT ST_X(ST_SnapToGrid(geom, :grid_size)) AS cell_lon,
                   ST_Y(ST_SnapToGrid(geom, :grid_size)) AS cell_lat,
                   date_trunc('day', occurred_at) AS bucket_ts,
                   COUNT(*)::int AS cnt
            FROM violations
            WHERE occurred_at >= :start_ts AND occurred_at <= :end_ts
            GROUP BY cell_lon, cell_lat, bucket_ts
        """
        grid_params = {**params, "grid_size": GRID_SIZE_DEG}
        grid_rows = conn.execute(text(grid_sql), grid_params).fetchall()

        by_cell: dict[tuple[float, float], list[int]] = defaultdict(list)
        for r in grid_rows:
            clon, clat, _, cnt = r[0], r[1], r[2], int(r[3])
            by_cell[(clon, clat)].append(cnt)

        anomaly_cells: list[tuple[float, float]] = []
        for (clon, clat), counts in by_cell.items():
            if _zscore_anomaly_cells(counts, ANOMALY_Z_THRESHOLD) >= 1:
                anomaly_cells.append((clon, clat))

        zone_anomaly_count: dict[int, int] = {zid: 0 for zid in zone_ids}
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
            for r in conn.execute(text(zone_anom_sql), {"zone_ids": zone_ids}).fetchall():
                zone_anomaly_count[r[0]] = int(r[1])

        candidates: list[dict[str, Any]] = []
        for zid in zone_ids:
            zone_info = zones_by_id[zid]
            ts_list = sorted(by_zone_ts.get(zid, []), key=lambda x: x["bucket_ts"])
            ts_desc = list(reversed(ts_list))
            trend_dir, trend_pct = _compute_trend(ts_desc)
            total_count = sum(x["count"] for x in ts_list)

            wow_curr, wow_prev, mom_curr, mom_prev = wow_mom_by_zone.get(zid, (0, 0, 0, 0))
            wow_pct = _delta_percent_safe(wow_curr, wow_prev)
            mom_pct = _delta_percent_safe(mom_curr, mom_prev)
            anom_count = zone_anomaly_count.get(zid, 0)

            trend_severity = "low"
            if trend_dir == "up" and trend_pct >= 10:
                trend_severity = "high" if trend_pct >= 50 else ("medium" if trend_pct >= 20 else "low")
            wow_severity = "low"
            if wow_pct >= 20:
                wow_severity = "high" if wow_pct >= 80 else ("medium" if wow_pct >= 40 else "low")
            mom_severity = "low"
            if mom_pct >= 30:
                mom_severity = "high" if mom_pct >= 100 else ("medium" if mom_pct >= 50 else "low")
            anomaly_severity = "low"
            if anom_count >= ANOMALY_CLUSTER_MIN_CELLS:
                anomaly_severity = "high" if anom_count >= 11 else ("medium" if anom_count >= 4 else "low")

            max_severity = max(
                _severity_score(trend_severity),
                _severity_score(wow_severity),
                _severity_score(mom_severity),
                _severity_score(anomaly_severity),
            )
            severity_presence = 1.0 if max_severity > 0 else 0.0

            candidates.append({
                "zone": zone_info,
                "zone_id": zid,
                "total_count": total_count,
                "trend_direction": trend_dir,
                "percent_change": trend_pct,
                "wow_delta_percent": wow_pct,
                "mom_delta_percent": mom_pct,
                "anomaly_cell_count": anom_count,
                "severity_presence": severity_presence,
                "max_severity": max_severity,
            })

        total_counts = [c["total_count"] for c in candidates]
        pct_changes = [max(0, c["percent_change"]) for c in candidates]
        wow_deltas = [max(0, c["wow_delta_percent"]) for c in candidates]
        mom_deltas = [max(0, c["mom_delta_percent"]) for c in candidates]
        anom_counts = [c["anomaly_cell_count"] for c in candidates]
        min_tc, max_tc = min(total_counts), max(total_counts)
        min_pct, max_pct = (min(pct_changes) if pct_changes else 0, max(pct_changes) if pct_changes else 1)
        min_wow, max_wow = (min(wow_deltas) if wow_deltas else 0, max(wow_deltas) if wow_deltas else 1)
        min_mom, max_mom = (min(mom_deltas) if mom_deltas else 0, max(mom_deltas) if mom_deltas else 1)
        min_anom, max_anom = (min(anom_counts), max(anom_counts))

        for c in candidates:
            norm_vol = _min_max_normalize(c["total_count"], min_tc, max_tc)
            norm_trend = _min_max_normalize(max(0, c["percent_change"]), min_pct, max_pct)
            norm_wow = _min_max_normalize(max(0, c["wow_delta_percent"]), min_wow, max_wow)
            norm_mom = _min_max_normalize(max(0, c["mom_delta_percent"]), min_mom, max_mom)
            norm_anom = _min_max_normalize(c["anomaly_cell_count"], min_anom, max_anom)

            if body.strategy == "risk_max":
                c["priority_score"] = round(0.5 * norm_vol + 0.3 * norm_anom + 0.2 * c["max_severity"], 4)
            elif body.strategy == "trend_focus":
                c["priority_score"] = round(0.4 * norm_trend + 0.35 * norm_wow + 0.25 * norm_mom, 4)
            else:
                c["priority_score"] = round(
                    0.35 * norm_vol + 0.25 * norm_trend + 0.2 * norm_anom + 0.2 * c["max_severity"], 4
                )

        candidates.sort(key=lambda x: (-x["priority_score"], x["zone"]["name"]))

        max_per_zone = 3 if body.strategy == "risk_max" else 2
        units_left = body.units
        plan: list[dict[str, Any]] = []
        assigned: dict[int, int] = {}
        plan_by_zid: dict[int, dict[str, Any]] = {}

        for c in candidates:
            if units_left <= 0:
                break
            zid = c["zone_id"]
            to_assign = min(1, units_left)
            assigned[zid] = assigned.get(zid, 0) + to_assign
            units_left -= to_assign
            reasons = _build_reasons(c)
            hint = _recommendation_hint(c, body.strategy)
            entry = {
                "zone": c["zone"],
                "assigned_units": to_assign,
                "priority_score": c["priority_score"],
                "reasons": reasons,
                "recommendation_hint": hint,
            }
            plan.append(entry)
            plan_by_zid[zid] = entry

        while units_left > 0:
            extra_assigned = False
            for c in candidates:
                if units_left <= 0:
                    break
                zid = c["zone_id"]
                current = assigned.get(zid, 0)
                if current >= max_per_zone:
                    continue
                extra = min(1, max_per_zone - current, units_left)
                if extra <= 0:
                    continue
                assigned[zid] = current + extra
                plan_by_zid[zid]["assigned_units"] += extra
                units_left -= extra
                extra_assigned = True
            if not extra_assigned:
                break

        meta: dict[str, Any] = {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": anchor_ts_str,
            "response_cache": "miss",
        }
        if os.getenv("DEBUG") == "1":
            meta["cache_key_hash"] = key_hash

        payload = {"plan": plan, "meta": meta}
        resp_cache.set(resp_key, payload, PATROL_ALLOCATE_TTL)
        return payload


def _build_reasons(c: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    if c["total_count"] >= 10:
        reasons.append({"signal": "high_volume", "value": c["total_count"]})
    if c["percent_change"] > 5:
        reasons.append({"signal": "trend_up", "value": round(c["percent_change"], 1)})
    if c["wow_delta_percent"] >= 20:
        reasons.append({"signal": "wow_spike", "value": round(c["wow_delta_percent"], 1)})
    if c["mom_delta_percent"] >= 30:
        reasons.append({"signal": "mom_spike", "value": round(c["mom_delta_percent"], 1)})
    if c["anomaly_cell_count"] >= ANOMALY_CLUSTER_MIN_CELLS:
        reasons.append({"signal": "anomaly_cluster", "value": c["anomaly_cell_count"]})
    if c["max_severity"] >= 0.5:
        reasons.append({"signal": "warning_high", "value": True})
    if not reasons:
        reasons.append({"signal": "volume", "value": c["total_count"]})
    return reasons


def _recommendation_hint(c: dict[str, Any], strategy: str) -> str:
    if c["anomaly_cell_count"] >= ANOMALY_CLUSTER_MIN_CELLS:
        return "Increase patrol presence; investigate hot spots."
    if c["wow_delta_percent"] >= 20 or c["mom_delta_percent"] >= 30:
        return "Investigate cause of spike; consider temporary coverage."
    if c["percent_change"] > 5:
        return "Monitor trend; consider increased patrol presence."
    return "Patrol presence during peak hours"


def _empty_plan(request: Request, anchor_ts: str | None) -> dict[str, Any]:
    return {
        "plan": [],
        "meta": {
            "request_id": getattr(request.state, "request_id", None),
            "anchor_ts": anchor_ts,
            "response_cache": "miss",
        },
    }

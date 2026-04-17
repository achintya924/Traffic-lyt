"""
Phase 5.11: Unified decision endpoint.
POST /api/decision/now — one answer to "what should I do right now?".
Combines forecast baseline + confidence (5.9C/5.10), zone-scoped warnings (5.6),
patrol allocation (5.8), and hotspots into a single actionable payload.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.policy.baseline import get_multi_zone_baseline
from app.utils.explainability import (
    explain_confidence,
    explain_forecast,
    explain_hotspot,
    explain_patrol,
    explain_verdict,
    explain_warning,
    make_explain,
)
from app.utils.response_cache import get_response_cache

from app.routers.anomalies import GRID_SIZE_DEG
from app.routers.patrol import (
    ANOMALY_CLUSTER_MIN_CELLS,
    ANOMALY_Z_THRESHOLD,
    _min_max_normalize,
    _severity_score,
    _zscore_anomaly_cells,
)
from app.routers.warnings import _severity_anomaly, _severity_spike, _severity_trend_up
from app.routers.zones_analytics import _compute_trend
from app.routers.zones_compare import MOM_DAYS, WOW_DAYS, _delta_percent_safe


DECISION_TTL = 60
DECISION_WINDOW_DAYS = 30
HOTSPOT_TOP_K = 10
PATROL_MAX_PER_ZONE = 2
SEVERITY_SORT = {"high": 0, "medium": 1, "low": 2}


router = APIRouter(prefix="/api/decision", tags=["decision"])


Horizon = Literal["24h", "30d"]


class DecisionRequest(BaseModel):
    zones: Annotated[list[str], Field(min_length=1, max_length=10)]
    horizon: Horizon = "24h"
    anchor_ts: datetime | None = None

    @field_validator("zones", mode="after")
    @classmethod
    def zones_strip(cls, v: list[str]) -> list[str]:
        return [z.strip() for z in v]

    @model_validator(mode="after")
    def zones_unique_non_empty(self):
        if not all(self.zones):
            raise ValueError("zones must be non-empty after stripping whitespace")
        if len(self.zones) != len(set(self.zones)):
            raise ValueError("zones must be unique")
        return self


def _iso_seconds(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    t = ts.replace(microsecond=0)
    s = t.isoformat()
    if "+00:00" in s:
        return s.replace("+00:00", "Z")
    if "Z" in s or "+" in s:
        return s
    return s + "Z"


def _normalize(req: DecisionRequest) -> dict[str, Any]:
    return {
        "zones": sorted(req.zones),
        "horizon": req.horizon,
        "anchor_ts": _iso_seconds(req.anchor_ts),
    }


def _cache_key(normalized: dict[str, Any]) -> str:
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "decision_now:" + sha256(raw.encode("utf-8")).hexdigest()


def _resolve_zone_records(conn, zone_refs: list[str]) -> list[dict[str, Any]]:
    """Resolve zone refs (name or stringified id) to {id, name, zone_type}."""
    rows = conn.execute(
        text(
            """
            SELECT id, name, zone_type
            FROM zones
            WHERE CAST(id AS TEXT) = ANY(:refs) OR name = ANY(:refs)
            """
        ),
        {"refs": zone_refs},
    ).fetchall()
    return [{"id": r[0], "name": r[1], "zone_type": r[2]} for r in rows]


def _compute_zone_signals(
    conn,
    zone_ids: list[int],
    effective_start: datetime,
    effective_end: datetime,
) -> dict[str, Any]:
    """Daily trend + wow/mom deltas + anomaly cell counts scoped to provided zones."""
    ts_rows = conn.execute(
        text(
            """
            SELECT z.id, date_trunc('day', v.occurred_at) AS bucket_ts, COUNT(*)::int AS cnt
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE z.id = ANY(:zone_ids)
              AND v.occurred_at >= :start_ts AND v.occurred_at <= :end_ts
            GROUP BY z.id, date_trunc('day', v.occurred_at)
            ORDER BY z.id, bucket_ts
            """
        ),
        {"zone_ids": zone_ids, "start_ts": effective_start, "end_ts": effective_end},
    ).fetchall()

    by_zone_ts: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_zone_total: dict[int, int] = defaultdict(int)
    for r in ts_rows:
        zid, bts, cnt = r[0], r[1], int(r[2])
        by_zone_ts[zid].append({"bucket_ts": bts, "count": cnt})
        by_zone_total[zid] += cnt

    wow_start = effective_end - timedelta(days=WOW_DAYS)
    wow_prev_end = wow_start
    wow_prev_start = wow_prev_end - timedelta(days=WOW_DAYS)
    mom_start = effective_end - timedelta(days=MOM_DAYS)
    mom_prev_end = mom_start
    mom_prev_start = mom_prev_end - timedelta(days=MOM_DAYS)

    wow_mom_rows = conn.execute(
        text(
            """
            SELECT z.id,
                   SUM(CASE WHEN v.occurred_at >= :wow_curr_start AND v.occurred_at <= :wow_curr_end THEN 1 ELSE 0 END)::int,
                   SUM(CASE WHEN v.occurred_at >= :wow_prev_start AND v.occurred_at < :wow_prev_end THEN 1 ELSE 0 END)::int,
                   SUM(CASE WHEN v.occurred_at >= :mom_curr_start AND v.occurred_at <= :mom_curr_end THEN 1 ELSE 0 END)::int,
                   SUM(CASE WHEN v.occurred_at >= :mom_prev_start AND v.occurred_at < :mom_prev_end THEN 1 ELSE 0 END)::int
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE z.id = ANY(:zone_ids)
              AND v.occurred_at >= :mom_prev_start AND v.occurred_at <= :mom_curr_end
            GROUP BY z.id
            """
        ),
        {
            "zone_ids": zone_ids,
            "wow_curr_start": wow_start,
            "wow_curr_end": effective_end,
            "wow_prev_start": wow_prev_start,
            "wow_prev_end": wow_prev_end,
            "mom_curr_start": mom_start,
            "mom_curr_end": effective_end,
            "mom_prev_start": mom_prev_start,
            "mom_prev_end": mom_prev_end,
        },
    ).fetchall()
    wow_mom_by_zone = {r[0]: (int(r[1]), int(r[2]), int(r[3]), int(r[4])) for r in wow_mom_rows}

    grid_rows = conn.execute(
        text(
            """
            SELECT ST_X(ST_SnapToGrid(v.geom, :grid_size)) AS cell_lon,
                   ST_Y(ST_SnapToGrid(v.geom, :grid_size)) AS cell_lat,
                   date_trunc('day', v.occurred_at) AS bucket_ts,
                   COUNT(*)::int AS cnt
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE z.id = ANY(:zone_ids)
              AND v.occurred_at >= :start_ts AND v.occurred_at <= :end_ts
            GROUP BY cell_lon, cell_lat, bucket_ts
            """
        ),
        {
            "zone_ids": zone_ids,
            "start_ts": effective_start,
            "end_ts": effective_end,
            "grid_size": GRID_SIZE_DEG,
        },
    ).fetchall()

    by_cell: dict[tuple[float, float], list[int]] = defaultdict(list)
    for r in grid_rows:
        by_cell[(r[0], r[1])].append(int(r[3]))
    anomaly_cells_xy = [
        (clon, clat)
        for (clon, clat), counts in by_cell.items()
        if _zscore_anomaly_cells(counts, ANOMALY_Z_THRESHOLD) >= 1
    ]

    zone_anom_count: dict[int, int] = {zid: 0 for zid in zone_ids}
    if anomaly_cells_xy:
        cells = anomaly_cells_xy[:500]
        values = ", ".join(f"({lon!r}::float, {lat!r}::float)" for lon, lat in cells)
        rows = conn.execute(
            text(
                f"""
                SELECT z.id, COUNT(*)::int
                FROM zones z
                CROSS JOIN (VALUES {values}) AS p(cell_lon, cell_lat)
                WHERE z.id = ANY(:zone_ids)
                  AND ST_Contains(z.geom, ST_SetSRID(ST_MakePoint(p.cell_lon, p.cell_lat), 4326))
                GROUP BY z.id
                """
            ),
            {"zone_ids": zone_ids},
        ).fetchall()
        for r in rows:
            zone_anom_count[r[0]] = int(r[1])

    return {
        "by_zone_ts": dict(by_zone_ts),
        "by_zone_total": dict(by_zone_total),
        "wow_mom_by_zone": wow_mom_by_zone,
        "zone_anom_count": zone_anom_count,
    }


def _build_warnings(
    zone_records: list[dict[str, Any]],
    signals: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for zone in zone_records:
        zid = zone["id"]
        ts_list = sorted(signals["by_zone_ts"].get(zid, []), key=lambda x: x["bucket_ts"])
        ts_desc = list(reversed(ts_list))
        trend_dir, trend_pct = _compute_trend(ts_desc)
        if trend_dir == "up" and trend_pct >= 10:
            out.append({
                "warning_type": "trend_up",
                "severity": _severity_trend_up(trend_pct),
                "zone": zone,
                "headline": f"Violations trending up {trend_pct:.0f}% in {zone['name']}",
                "details": {"percent_change": trend_pct},
                "recommendation_hint": "Monitor trend; consider increased patrol presence.",
            })

        wow_curr, wow_prev, mom_curr, mom_prev = signals["wow_mom_by_zone"].get(zid, (0, 0, 0, 0))
        wow_pct = _delta_percent_safe(wow_curr, wow_prev)
        if wow_pct >= 20:
            out.append({
                "warning_type": "wow_spike",
                "severity": _severity_spike(wow_pct, True),
                "zone": zone,
                "headline": f"Week-over-week spike +{wow_pct:.0f}% in {zone['name']}",
                "details": {"delta_percent": wow_pct, "current_count": wow_curr, "previous_count": wow_prev},
                "recommendation_hint": "Investigate cause of weekly spike.",
            })

        mom_pct = _delta_percent_safe(mom_curr, mom_prev)
        if mom_pct >= 30:
            out.append({
                "warning_type": "mom_spike",
                "severity": _severity_spike(mom_pct, False),
                "zone": zone,
                "headline": f"Month-over-month spike +{mom_pct:.0f}% in {zone['name']}",
                "details": {"delta_percent": mom_pct, "current_count": mom_curr, "previous_count": mom_prev},
                "recommendation_hint": "Review monthly trend; consider resource allocation.",
            })

        anom_count = signals["zone_anom_count"].get(zid, 0)
        if anom_count >= ANOMALY_CLUSTER_MIN_CELLS:
            out.append({
                "warning_type": "anomaly_cluster",
                "severity": _severity_anomaly(anom_count),
                "zone": zone,
                "headline": f"Anomaly cluster ({anom_count} cells) in {zone['name']}",
                "details": {"anomaly_cell_count": anom_count},
                "recommendation_hint": "Increase patrol presence; investigate hot spots.",
            })

    out.sort(key=lambda w: (SEVERITY_SORT[w["severity"]], w["zone"]["name"]))
    return out


def _build_patrol_plan(
    zone_records: list[dict[str, Any]],
    signals: dict[str, Any],
    units: int,
) -> dict[str, Any]:
    """Balanced allocation across requested zones using patrol.py scoring helpers."""
    if not zone_records or units <= 0:
        return {"strategy": "balanced", "units": max(0, units), "assignments": []}

    candidates: list[dict[str, Any]] = []
    for zone in zone_records:
        zid = zone["id"]
        total = int(signals["by_zone_total"].get(zid, 0))
        ts_list = sorted(signals["by_zone_ts"].get(zid, []), key=lambda x: x["bucket_ts"])
        ts_desc = list(reversed(ts_list))
        trend_dir, trend_pct = _compute_trend(ts_desc)
        wow_curr, wow_prev, mom_curr, mom_prev = signals["wow_mom_by_zone"].get(zid, (0, 0, 0, 0))
        wow_pct = _delta_percent_safe(wow_curr, wow_prev)
        mom_pct = _delta_percent_safe(mom_curr, mom_prev)
        anom_count = int(signals["zone_anom_count"].get(zid, 0))

        trend_sev = "low"
        if trend_dir == "up" and trend_pct >= 10:
            trend_sev = "high" if trend_pct >= 50 else ("medium" if trend_pct >= 20 else "low")
        wow_sev = "low"
        if wow_pct >= 20:
            wow_sev = "high" if wow_pct >= 80 else ("medium" if wow_pct >= 40 else "low")
        mom_sev = "low"
        if mom_pct >= 30:
            mom_sev = "high" if mom_pct >= 100 else ("medium" if mom_pct >= 50 else "low")
        anom_sev = "low"
        if anom_count >= ANOMALY_CLUSTER_MIN_CELLS:
            anom_sev = "high" if anom_count >= 11 else ("medium" if anom_count >= 4 else "low")

        max_sev = max(
            _severity_score(trend_sev),
            _severity_score(wow_sev),
            _severity_score(mom_sev),
            _severity_score(anom_sev),
        )
        candidates.append({
            "zone": zone,
            "zone_id": zid,
            "total_count": total,
            "percent_change": trend_pct,
            "wow_delta_percent": wow_pct,
            "mom_delta_percent": mom_pct,
            "anomaly_cell_count": anom_count,
            "max_severity": max_sev,
        })

    totals = [c["total_count"] for c in candidates]
    pcts = [max(0.0, c["percent_change"]) for c in candidates]
    anoms = [c["anomaly_cell_count"] for c in candidates]
    mint, maxt = min(totals), max(totals)
    minp, maxp = min(pcts), max(pcts)
    mina, maxa = min(anoms), max(anoms)

    for c in candidates:
        nv = _min_max_normalize(c["total_count"], mint, maxt)
        nt = _min_max_normalize(max(0.0, c["percent_change"]), minp, maxp)
        na = _min_max_normalize(c["anomaly_cell_count"], mina, maxa)
        c["priority_score"] = round(
            0.35 * nv + 0.25 * nt + 0.2 * na + 0.2 * c["max_severity"], 4
        )

    candidates.sort(key=lambda x: (-x["priority_score"], x["zone"]["name"]))

    assignments: list[dict[str, Any]] = []
    plan_by_zid: dict[int, dict[str, Any]] = {}
    assigned: dict[int, int] = {c["zone_id"]: 0 for c in candidates}
    units_left = units

    for c in candidates:
        if units_left <= 0:
            break
        entry = {
            "zone": c["zone"],
            "assigned_units": 1,
            "priority_score": c["priority_score"],
            "reasons": _reasons(c),
        }
        assignments.append(entry)
        plan_by_zid[c["zone_id"]] = entry
        assigned[c["zone_id"]] = 1
        units_left -= 1

    while units_left > 0:
        added = False
        for c in candidates:
            if units_left <= 0:
                break
            zid = c["zone_id"]
            if assigned.get(zid, 0) >= PATROL_MAX_PER_ZONE:
                continue
            if zid not in plan_by_zid:
                continue
            plan_by_zid[zid]["assigned_units"] += 1
            assigned[zid] += 1
            units_left -= 1
            added = True
        if not added:
            break

    return {"strategy": "balanced", "units": units, "assignments": assignments}


def _reasons(c: dict[str, Any]) -> list[dict[str, Any]]:
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
    if not reasons:
        reasons.append({"signal": "volume", "value": c["total_count"]})
    return reasons


def _fetch_hotspots(
    conn,
    zone_ids: list[int],
    effective_start: datetime,
    effective_end: datetime,
    top_k: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT ST_X(ST_SnapToGrid(v.geom, :grid_size)) AS cell_lon,
                   ST_Y(ST_SnapToGrid(v.geom, :grid_size)) AS cell_lat,
                   COUNT(*)::int AS cnt,
                   MIN(z.id) AS zone_id,
                   MIN(z.name) AS zone_name
            FROM zones z
            INNER JOIN violations v ON ST_Intersects(z.geom, v.geom)
            WHERE z.id = ANY(:zone_ids)
              AND v.occurred_at >= :start_ts AND v.occurred_at <= :end_ts
            GROUP BY cell_lon, cell_lat
            ORDER BY cnt DESC
            LIMIT :top_k
            """
        ),
        {
            "zone_ids": zone_ids,
            "start_ts": effective_start,
            "end_ts": effective_end,
            "grid_size": GRID_SIZE_DEG,
            "top_k": top_k,
        },
    ).fetchall()
    return [
        {
            "cell_lon": round(float(r[0]), 6),
            "cell_lat": round(float(r[1]), 6),
            "count": int(r[2]),
            "zone_id": r[3],
            "zone_name": r[4],
        }
        for r in rows
    ]


def _build_verdict(
    warnings_list: list[dict[str, Any]],
    hotspots: list[dict[str, Any]],
    confidence: dict[str, Any] | None,
) -> dict[str, str]:
    if warnings_list:
        top = warnings_list[0]
        return {
            "priority_action": top["recommendation_hint"],
            "reasoning": f"Top warning: {top['headline']} (severity={top['severity']}).",
        }
    if hotspots:
        top = hotspots[0]
        zone_label = top.get("zone_name") or f"zone {top.get('zone_id')}"
        return {
            "priority_action": "Focus patrols on identified hotspot cluster.",
            "reasoning": f"Top hotspot in {zone_label} with {top['count']} events in the last {DECISION_WINDOW_DAYS} days.",
        }
    label = (confidence or {}).get("confidence_label") or "unknown"
    return {
        "priority_action": "Monitor",
        "reasoning": (
            f"No active warnings or hotspots for the requested zones "
            f"(forecast confidence: {label})."
        ),
    }


@router.post("/now")
def decision_now(request: Request, body: DecisionRequest) -> dict[str, Any]:
    """
    Unified decision: combines forecast + confidence + warnings + patrol + hotspots
    scoped to the requested zones, plus a deterministic verdict.
    """
    if body.anchor_ts is not None:
        anchor_dt = body.anchor_ts
    else:
        anchor_dt = datetime.now(timezone.utc).replace(microsecond=0)

    anchor_ts_str = _iso_seconds(anchor_dt) or ""
    normalized = _normalize(body)
    normalized["anchor_ts"] = anchor_ts_str
    cache_key = _cache_key(normalized)
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex

    resp_cache = get_response_cache()
    cached = resp_cache.get(cache_key)
    if cached is not None:
        out = dict(cached)
        out["meta"] = {
            **cached.get("meta", {}),
            "request_id": request_id,
            "response_cache": {"status": "hit", "key": cache_key},
        }
        return out

    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    anchor_naive = anchor_dt.replace(tzinfo=None) if anchor_dt.tzinfo is not None else anchor_dt
    effective_end = anchor_naive
    effective_start = effective_end - timedelta(days=DECISION_WINDOW_DAYS)

    with get_connection() as conn:
        if conn is None:
            raise HTTPException(status_code=503, detail="Database connection failed")

        baseline_data = get_multi_zone_baseline(
            conn=conn,
            zones=normalized["zones"],
            horizon=body.horizon,
            anchor_ts=anchor_naive,
        )

        zone_records = _resolve_zone_records(conn, normalized["zones"])

        if zone_records:
            zone_ids = [z["id"] for z in zone_records]
            signals = _compute_zone_signals(conn, zone_ids, effective_start, effective_end)
            warnings_list = _build_warnings(zone_records, signals)
            patrol_block = _build_patrol_plan(zone_records, signals, units=len(zone_records))
            hotspots = _fetch_hotspots(conn, zone_ids, effective_start, effective_end, HOTSPOT_TOP_K)
        else:
            warnings_list = []
            patrol_block = {"strategy": "balanced", "units": 0, "assignments": []}
            hotspots = []

    overall_confidence = baseline_data.get("overall_confidence")
    forecast_block = {
        "horizon": body.horizon,
        "zones": baseline_data["zones"],
        "overall_total": baseline_data["overall_total"],
    }
    verdict = _build_verdict(warnings_list, hotspots, overall_confidence)

    explain: list[dict[str, Any]] = []
    explain.append(explain_confidence(overall_confidence).model_dump())
    for w in warnings_list:
        explain.append(explain_warning(w).model_dump())
    for h in hotspots:
        explain.append(explain_hotspot(h).model_dump())
    for a in patrol_block.get("assignments", []):
        explain.append(explain_patrol(a).model_dump())
    for z in forecast_block["zones"]:
        explain.append(
            explain_forecast(
                zone_id=z.get("zone_id"),
                total=float(z.get("total", 0.0) or 0.0),
                horizon=body.horizon,
            ).model_dump()
        )
    explain.append(
        make_explain(
            code="forecast_overall",
            message=(
                f"Combined forecast across {len(forecast_block['zones'])} zone(s): "
                f"~{round(float(forecast_block['overall_total'] or 0.0), 2)} expected "
                f"violations over the {body.horizon} horizon."
            ),
            details={
                "overall_total": forecast_block["overall_total"],
                "horizon": body.horizon,
                "zone_count": len(forecast_block["zones"]),
            },
        ).model_dump()
    )
    explain.append(explain_verdict(verdict).model_dump())

    payload = {
        "meta": {
            "request_id": request_id,
            "anchor_ts": anchor_ts_str,
            "response_cache": {"status": "miss", "key": cache_key},
        },
        "confidence": overall_confidence,
        "warnings": warnings_list,
        "hotspots": hotspots,
        "patrol": patrol_block,
        "forecast": forecast_block,
        "verdict": verdict,
        "explain": explain,
    }
    resp_cache.set(cache_key, payload, DECISION_TTL)
    return payload

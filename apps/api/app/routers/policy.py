"""
Phase 5.9A: Policy impact simulation — endpoint skeleton.
POST /api/policy/simulate returns placeholder results (no engine yet).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.db import get_connection, get_engine
from app.models.policy_simulation import (
    BaselineSimulatedBlock,
    DeltaBlock,
    ExplainEntry,
    PolicySimulationRequest,
    PolicySimulationResponse,
    PolicySimulationMeta,
    ResponseCacheMeta,
    ZoneDelta,
    ZoneTotal,
)
from app.policy.baseline import get_multi_zone_baseline
from app.utils.response_cache import get_response_cache
from app.utils.policy_normalization import normalize_policy_request, policy_cache_key

router = APIRouter(prefix="/api/policy", tags=["policy"])
POLICY_SIMULATION_TTL = 75


@router.post("/simulate")
def simulate_policy(request: Request, body: PolicySimulationRequest) -> PolicySimulationResponse:
    """
    Policy impact simulation (Phase 5.9A: contract only).
    Returns placeholder baseline/simulated (simulated == baseline, delta 0).
    """
    if body.anchor_ts is not None:
        anchor_dt = body.anchor_ts
    else:
        anchor_dt = datetime.now(timezone.utc).replace(microsecond=0)
    # Normalize to UTC ISO string (Z suffix)
    iso = anchor_dt.isoformat()
    anchor_ts_str = iso + "Z" if "Z" not in iso and "+" not in iso else iso.replace("+00:00", "Z")
    normalized = normalize_policy_request(body)
    normalized["anchor_ts"] = anchor_ts_str
    cache_key = policy_cache_key(normalized)
    resp_cache = get_response_cache()
    cached = resp_cache.get(cache_key)
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex

    if cached is not None:
        out = dict(cached)
        out["meta"] = {
            **cached.get("meta", {}),
            "request_id": request_id,
            "response_cache": {"status": "hit", "key": cache_key},
        }
        return PolicySimulationResponse.model_validate(out)

    engine = get_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    with get_connection() as conn:
        if conn is None:
            raise HTTPException(status_code=503, detail="Database connection failed")
        baseline_data = get_multi_zone_baseline(
            conn=conn,
            zones=normalized["zones"],
            horizon=body.horizon,
            anchor_ts=anchor_dt.replace(tzinfo=None) if anchor_dt.tzinfo is not None else anchor_dt,
        )

    baseline_zones = [ZoneTotal(zone_id=z["zone_id"], total=float(z["total"])) for z in baseline_data["zones"]]
    overall_total = float(baseline_data["overall_total"])

    baseline = BaselineSimulatedBlock(horizon=body.horizon, zones=baseline_zones, overall_total=overall_total)
    simulated = BaselineSimulatedBlock(horizon=body.horizon, zones=baseline_zones, overall_total=overall_total)

    delta_zones = [ZoneDelta(zone_id=z, delta=0.0, delta_pct=None) for z in normalized["zones"]]
    delta = DeltaBlock(zones=delta_zones, overall_delta=0.0, overall_delta_pct=None)

    explain: list[ExplainEntry] = [
        ExplainEntry(
            code="stub",
            message="Policy simulation not applied yet (Phase 5.9A contract only).",
            details={},
        ),
        ExplainEntry(
            code="interventions_received",
            message=f"Received {len(body.interventions)} intervention(s) (not applied).",
            details={"count": len(body.interventions), "types": [i.type for i in body.interventions]},
        ),
    ]

    meta = PolicySimulationMeta(
        request_id=request_id,
        anchor_ts=anchor_ts_str,
        response_cache=ResponseCacheMeta(status="miss", key=cache_key),
    )
    response = PolicySimulationResponse(
        meta=meta,
        baseline=baseline,
        simulated=simulated,
        delta=delta,
        explain=explain,
    )
    # Store full response; request_id is overwritten on cache hit return path.
    resp_cache.set(cache_key, response.model_dump(), POLICY_SIMULATION_TTL)
    return response

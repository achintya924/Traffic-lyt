"""
Phase 5.9A: Policy impact simulation — endpoint skeleton.
POST /api/policy/simulate returns placeholder results (no engine yet).
"""
import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.models.policy_simulation import (
    BaselineSimulatedBlock,
    DeltaBlock,
    ExplainEntry,
    PolicyHorizon,
    PolicySimulationRequest,
    PolicySimulationResponse,
    PolicySimulationMeta,
    ResponseCacheMeta,
    ZoneDelta,
    ZoneTotal,
)

router = APIRouter(prefix="/api/policy", tags=["policy"])


def _deterministic_baseline_total(zone_id: str) -> float:
    """Stable deterministic placeholder from zone_id (no DB). Scale to plausible float."""
    h = hashlib.sha256(zone_id.encode()).hexdigest()
    # first 8 hex chars -> int in [0, 2^32) -> scale to [10, 500)
    n = int(h[:8], 16)
    return 10.0 + (n % 490)


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

    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex

    baseline_zones = [ZoneTotal(zone_id=z, total=_deterministic_baseline_total(z)) for z in body.zones]
    overall_total = sum(zt.total for zt in baseline_zones)

    baseline = BaselineSimulatedBlock(horizon=body.horizon, zones=baseline_zones, overall_total=overall_total)
    simulated = BaselineSimulatedBlock(horizon=body.horizon, zones=baseline_zones, overall_total=overall_total)

    delta_zones = [ZoneDelta(zone_id=z, delta=0.0, delta_pct=None) for z in body.zones]
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
        response_cache=ResponseCacheMeta(status="miss", key=None),
    )

    return PolicySimulationResponse(
        meta=meta,
        baseline=baseline,
        simulated=simulated,
        delta=delta,
        explain=explain,
    )

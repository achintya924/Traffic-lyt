"""
Phase 5.9B: Canonical normalization for policy simulation requests.
"""
import json
from hashlib import sha256
from typing import Any

from app.models.policy_simulation import PolicySimulationRequest


def _iso_seconds(ts) -> str | None:
    if ts is None:
        return None
    t = ts.replace(microsecond=0)
    s = t.isoformat()
    if "Z" in s:
        return s
    if "+00:00" in s:
        return s.replace("+00:00", "Z")
    if "+" in s:
        return s
    return s + "Z"


def normalize_policy_request(req: PolicySimulationRequest) -> dict[str, Any]:
    """Return a JSON-serializable canonical dict for stable cache key generation."""
    zones = sorted(req.zones)
    interventions: list[dict[str, Any]] = []
    for i in req.interventions:
        if i.type == "enforcement_intensity":
            interventions.append({"type": i.type, "pct": round(float(i.pct), 2)})
        elif i.type == "patrol_units":
            interventions.append({"type": i.type, "from_units": i.from_units, "to_units": i.to_units})
        else:
            interventions.append({"type": i.type, "pct": round(float(i.pct), 2)})

    def _intervention_sort_key(v: dict[str, Any]) -> tuple:
        t = v["type"]
        if t == "enforcement_intensity":
            return (t, v["pct"])
        if t == "patrol_units":
            return (t, v["from_units"], v["to_units"])
        return (t, v.get("pct", 0.0))

    interventions.sort(key=_intervention_sort_key)

    return {
        "zones": zones,
        "horizon": req.horizon,
        "anchor_ts": _iso_seconds(req.anchor_ts),
        "interventions": interventions,
    }


def policy_cache_key(normalized: dict[str, Any]) -> str:
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "policy_simulation:" + sha256(raw.encode("utf-8")).hexdigest()

"""
Phase 5.9D: Policy simulation engine.
Phase 5.10: Forecast confidence threaded through baseline & simulated blocks.
Applies deterministic intervention multipliers to a forecast baseline.
Pure functions — no DB, no I/O, no side effects.
"""
from __future__ import annotations

from typing import Any

from app.models.policy_simulation import (
    BaselineSimulatedBlock,
    ConfidenceBlock,
    ConfidenceDetails,
    DeltaBlock,
    EnforcementIntensityIntervention,
    ExplainEntry,
    Intervention,
    PatrolUnitsIntervention,
    PeakHourReductionIntervention,
    PolicyHorizon,
    ZoneDelta,
    ZoneTotal,
)

_ENFORCEMENT_BASE_PCT = 100.0
_ENFORCEMENT_EFFECT_PER_10PCT = 0.04
_ENFORCEMENT_MAX_REDUCTION = 0.40
_ENFORCEMENT_NO_ENFORCE_BOOST = 0.20

_PATROL_EFFECT_PER_UNIT = 0.03
_PATROL_MAX_REDUCTION = 0.60

_PEAK_HOUR_SHARE = 0.35


def _enforcement_multiplier(pct: float) -> tuple[float, str]:
    delta_pct = pct - _ENFORCEMENT_BASE_PCT
    if delta_pct >= 0:
        raw_reduction = (delta_pct / 10.0) * _ENFORCEMENT_EFFECT_PER_10PCT
        reduction = min(raw_reduction, _ENFORCEMENT_MAX_REDUCTION)
        multiplier = round(1.0 - reduction, 6)
        detail = (
            f"Enforcement raised to {pct:.0f}% of baseline → "
            f"{reduction * 100:.1f}% fewer predicted violations."
        )
    else:
        boost = abs(delta_pct) / _ENFORCEMENT_BASE_PCT * _ENFORCEMENT_NO_ENFORCE_BOOST
        multiplier = round(1.0 + boost, 6)
        detail = (
            f"Enforcement lowered to {pct:.0f}% of baseline → "
            f"{boost * 100:.1f}% more predicted violations."
        )
    return multiplier, detail


def _patrol_multiplier(from_units: int, to_units: int) -> tuple[float, str]:
    delta = to_units - from_units
    if delta == 0:
        return 1.0, "No change in patrol units — baseline unchanged."
    raw = abs(delta) * _PATROL_EFFECT_PER_UNIT
    capped = min(raw, _PATROL_MAX_REDUCTION)
    if delta > 0:
        multiplier = round(1.0 - capped, 6)
        detail = (
            f"Patrol units increased {from_units} → {to_units} (+{delta}) → "
            f"{capped * 100:.1f}% fewer predicted violations."
        )
    else:
        multiplier = round(1.0 + capped, 6)
        detail = (
            f"Patrol units decreased {from_units} → {to_units} ({delta}) → "
            f"{capped * 100:.1f}% more predicted violations."
        )
    return multiplier, detail


def _peak_hour_multiplier(pct: float) -> tuple[float, str]:
    if pct <= 0:
        return 1.0, "No peak-hour reduction applied — baseline unchanged."
    suppressed_share = _PEAK_HOUR_SHARE * (pct / 100.0)
    multiplier = round(1.0 - suppressed_share, 6)
    detail = (
        f"Peak-hour reduction of {pct:.0f}% applied to ~{_PEAK_HOUR_SHARE * 100:.0f}% "
        f"of violations → {suppressed_share * 100:.1f}% overall reduction."
    )
    return multiplier, detail


def _resolve_intervention(
    intervention: Intervention,
) -> tuple[float, ExplainEntry]:
    if isinstance(intervention, EnforcementIntensityIntervention):
        m, detail = _enforcement_multiplier(intervention.pct)
        return m, ExplainEntry(
            code="enforcement_intensity",
            message=detail,
            details={"type": "enforcement_intensity", "pct": intervention.pct, "multiplier": m},
        )
    if isinstance(intervention, PatrolUnitsIntervention):
        m, detail = _patrol_multiplier(intervention.from_units, intervention.to_units)
        return m, ExplainEntry(
            code="patrol_units",
            message=detail,
            details={"type": "patrol_units", "from_units": intervention.from_units, "to_units": intervention.to_units, "multiplier": m},
        )
    if isinstance(intervention, PeakHourReductionIntervention):
        m, detail = _peak_hour_multiplier(intervention.pct)
        return m, ExplainEntry(
            code="peak_hour_reduction",
            message=detail,
            details={"type": "peak_hour_reduction", "pct": intervention.pct, "multiplier": m},
        )
    return 1.0, ExplainEntry(
        code="unknown_intervention",
        message="Unrecognised intervention — no effect applied.",
        details={"raw": str(intervention)},
    )


def _combined_multiplier(
    interventions: list[Intervention],
) -> tuple[float, list[ExplainEntry]]:
    combined = 1.0
    entries: list[ExplainEntry] = []
    for iv in interventions:
        m, entry = _resolve_intervention(iv)
        combined *= m
        entries.append(entry)
    return round(combined, 6), entries


def _build_confidence_block(overall_confidence: dict[str, Any] | None) -> ConfidenceBlock | None:
    if not overall_confidence:
        return None
    details_dict = overall_confidence.get("details") or {}
    details_model = ConfidenceDetails(**details_dict) if details_dict else None
    return ConfidenceBlock(
        score=float(overall_confidence.get("confidence_score", 0.0)),
        label=overall_confidence.get("confidence_label", "low"),
        details=details_model,
    )


def apply_simulation(
    baseline_data: dict[str, Any],
    interventions: list[Intervention],
    horizon: PolicyHorizon,
) -> tuple[BaselineSimulatedBlock, BaselineSimulatedBlock, DeltaBlock, list[ExplainEntry]]:
    multiplier, intervention_explains = _combined_multiplier(interventions)

    baseline_zones = [
        ZoneTotal(
            zone_id=z["zone_id"],
            total=float(z["total"]),
            confidence_score=z.get("confidence_score"),
            confidence_label=z.get("confidence_label"),
        )
        for z in baseline_data["zones"]
    ]
    baseline_overall = float(baseline_data["overall_total"])
    confidence_block = _build_confidence_block(baseline_data.get("overall_confidence"))

    baseline_block = BaselineSimulatedBlock(
        horizon=horizon,
        zones=baseline_zones,
        overall_total=baseline_overall,
        confidence=confidence_block,
    )

    simulated_zone_list = [
        ZoneTotal(
            zone_id=z.zone_id,
            total=round(z.total * multiplier, 4),
            confidence_score=z.confidence_score,
            confidence_label=z.confidence_label,
        )
        for z in baseline_zones
    ]
    simulated_overall = round(baseline_overall * multiplier, 4)
    simulated_block = BaselineSimulatedBlock(
        horizon=horizon,
        zones=simulated_zone_list,
        overall_total=simulated_overall,
        confidence=confidence_block,
    )

    baseline_map = {z.zone_id: z.total for z in baseline_zones}
    delta_zones = []
    for sz in simulated_zone_list:
        base_total = baseline_map[sz.zone_id]
        abs_delta = round(sz.total - base_total, 4)
        pct_delta = round((abs_delta / base_total) * 100, 2) if base_total != 0 else None
        delta_zones.append(ZoneDelta(zone_id=sz.zone_id, delta=abs_delta, delta_pct=pct_delta))

    overall_delta = round(simulated_overall - baseline_overall, 4)
    overall_delta_pct = (
        round((overall_delta / baseline_overall) * 100, 2) if baseline_overall != 0 else None
    )
    delta_block = DeltaBlock(
        zones=delta_zones, overall_delta=overall_delta, overall_delta_pct=overall_delta_pct
    )

    direction_word = "decrease" if overall_delta < 0 else ("increase" if overall_delta > 0 else "no change in")
    conf_score = confidence_block.score if confidence_block else None
    conf_label = confidence_block.label if confidence_block else None
    conf_suffix = (
        f" Forecast confidence: {conf_label} ({conf_score:.2f})."
        if conf_score is not None and conf_label is not None
        else ""
    )

    summary_entry = ExplainEntry(
        code="simulation_summary",
        message=(
            f"Combined effect of {len(interventions)} intervention(s): "
            f"combined multiplier {multiplier:.4f} → "
            f"{direction_word} of {abs(overall_delta):.1f} violations "
            f"({abs(overall_delta_pct or 0):.1f}%) over the {horizon} horizon."
            f"{conf_suffix}"
        ),
        details={
            "combined_multiplier": multiplier,
            "horizon": horizon,
            "overall_baseline": baseline_overall,
            "overall_simulated": simulated_overall,
            "overall_delta": overall_delta,
            "overall_delta_pct": overall_delta_pct,
            "confidence_score": conf_score,
            "confidence_label": conf_label,
        },
    )

    return baseline_block, simulated_block, delta_block, intervention_explains + [summary_entry]

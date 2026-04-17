"""
Phase 5.12: Shared explainability helpers.

Standardised builders for ExplainEntry items used across the decision, policy,
patrol and warnings routers. Pure functions — no DB, no I/O, no side effects.

Every helper returns an ExplainEntry. Routers serialise them as needed
(model_dump() for dict-returning routers, raw model for typed responses).
"""
from __future__ import annotations

from typing import Any

from app.models.explain import ExplainEntry


_HORIZON_PHRASES: dict[str, str] = {
    "24h": "next 24 hours",
    "30d": "next 30 days",
}


_WARNING_WHY: dict[str, str] = {
    "trend_up": "Daily volume is rising sharply versus the recent baseline.",
    "wow_spike": "Week-over-week volume jumped well above the prior week.",
    "mom_spike": "Month-over-month volume jumped well above the prior month.",
    "anomaly_cluster": "Several adjacent grid cells crossed the z-score threshold.",
}


def _round(value: Any, digits: int = 2) -> Any:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


def make_explain(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> ExplainEntry:
    """Base factory: always produces an ExplainEntry with non-null details."""
    return ExplainEntry(code=code, message=message, details=dict(details or {}))


def explain_confidence(confidence: Any) -> ExplainEntry:
    """
    Human-readable confidence reasoning.

    Accepts either a ConfidenceBlock (Pydantic model with .score/.label/.details)
    or a dict with confidence_score/confidence_label/details keys (baseline shape).
    Detects per-zone vs overall (weakest-link) form via the `rule` field.
    """
    if confidence is None:
        return make_explain(
            code="confidence_missing",
            message="No forecast confidence available — defaulting to low.",
            details={},
        )

    if hasattr(confidence, "score"):
        score = float(getattr(confidence, "score", 0.0) or 0.0)
        label = str(getattr(confidence, "label", "low") or "low")
        details_obj = getattr(confidence, "details", None)
        if details_obj is not None and hasattr(details_obj, "model_dump"):
            details_dict = details_obj.model_dump(exclude_none=True)
        elif isinstance(details_obj, dict):
            details_dict = dict(details_obj)
        else:
            details_dict = {}
    elif isinstance(confidence, dict):
        score = float(confidence.get("confidence_score", 0.0) or 0.0)
        label = str(confidence.get("confidence_label", "low") or "low")
        raw_details = confidence.get("details") or {}
        details_dict = dict(raw_details) if isinstance(raw_details, dict) else {}
    else:
        return make_explain(
            code="confidence_unknown_shape",
            message="Confidence payload was not recognised — treated as low.",
            details={"raw": str(confidence)},
        )

    rule = details_dict.get("rule")
    if rule:
        weakest = details_dict.get("weakest_zone_id")
        zone_count = details_dict.get("zone_count")
        zone_clause = f" across {zone_count} zone(s)" if zone_count else ""
        weakest_clause = f"; weakest zone: {weakest}" if weakest else ""
        message = (
            f"Overall forecast confidence is {label} ({score:.2f}) using "
            f"{rule} rule{zone_clause}{weakest_clause}."
        )
    else:
        n = details_dict.get("point_count")
        cv = details_dict.get("coefficient_of_variation")
        zr = details_dict.get("zero_ratio")
        bits: list[str] = []
        if n is not None:
            bits.append(f"{int(n)} historical point(s)")
        if cv is not None:
            bits.append(f"CV={float(cv):.2f}")
        if zr is not None:
            bits.append(f"zero-ratio={float(zr):.2f}")
        suffix = f" ({'; '.join(bits)})" if bits else ""
        message = f"Forecast confidence is {label} ({score:.2f}){suffix}."

    return make_explain(
        code="forecast_confidence",
        message=message,
        details={"score": _round(score, 4), "label": label, **details_dict},
    )


def explain_warning(warning: dict[str, Any]) -> ExplainEntry:
    """Why this warning was raised — driven by warning_type."""
    wtype = str(warning.get("warning_type", "unknown"))
    severity = str(warning.get("severity", "low"))
    zone = warning.get("zone") or {}
    zone_name = zone.get("name") or f"zone {zone.get('id', '?')}"
    headline = warning.get("headline") or wtype
    why = _WARNING_WHY.get(wtype, "Threshold conditions for this warning were met.")

    details_in = warning.get("details") or {}
    details_out: dict[str, Any] = {
        "warning_type": wtype,
        "severity": severity,
        "zone_id": zone.get("id"),
        "zone_name": zone.get("name"),
    }
    if isinstance(details_in, dict):
        details_out.update(details_in)

    message = f"{headline}. {why} (severity={severity})"

    return make_explain(
        code=f"warning_{wtype}",
        message=message,
        details=details_out,
    )


def explain_hotspot(hotspot: dict[str, Any]) -> ExplainEntry:
    """Why this cell is high risk — formats coordinates with zone context."""
    lon = hotspot.get("cell_lon")
    lat = hotspot.get("cell_lat")
    count = hotspot.get("count", 0)
    zone_name = hotspot.get("zone_name") or f"zone {hotspot.get('zone_id', '?')}"

    coord_str = (
        f"{float(lat):.4f},{float(lon):.4f}"
        if (lon is not None and lat is not None)
        else "unknown"
    )
    message = (
        f"Hotspot cell ({coord_str}) in {zone_name} accumulated "
        f"{int(count)} violations over the recent window."
    )
    return make_explain(
        code="hotspot_cell",
        message=message,
        details={
            "cell_lon": lon,
            "cell_lat": lat,
            "count": count,
            "zone_id": hotspot.get("zone_id"),
            "zone_name": hotspot.get("zone_name"),
        },
    )


def explain_patrol(assignment: dict[str, Any]) -> ExplainEntry:
    """Why this assignment exists — parses reasons[] into prose."""
    zone = assignment.get("zone") or {}
    zone_name = zone.get("name") or f"zone {zone.get('id', '?')}"
    units = int(assignment.get("assigned_units", 0))
    score = assignment.get("priority_score")
    reasons = assignment.get("reasons") or []

    reason_parts: list[str] = []
    for r in reasons:
        if not isinstance(r, dict):
            continue
        signal = r.get("signal", "signal")
        value = r.get("value")
        if signal == "high_volume":
            reason_parts.append(f"high volume ({value})")
        elif signal == "trend_up":
            reason_parts.append(f"upward trend (+{value}%)")
        elif signal == "wow_spike":
            reason_parts.append(f"week-over-week spike (+{value}%)")
        elif signal == "mom_spike":
            reason_parts.append(f"month-over-month spike (+{value}%)")
        elif signal == "anomaly_cluster":
            reason_parts.append(f"{value} anomalous cell(s)")
        elif signal == "warning_high":
            reason_parts.append("active high-severity warning")
        elif signal == "volume":
            reason_parts.append(f"volume baseline ({value})")
        else:
            reason_parts.append(f"{signal}={value}")

    reason_clause = "; ".join(reason_parts) if reason_parts else "default coverage"
    score_clause = f", priority {float(score):.2f}" if score is not None else ""
    message = (
        f"Assigned {units} unit(s) to {zone_name}{score_clause}. "
        f"Reasons: {reason_clause}."
    )

    return make_explain(
        code="patrol_assignment",
        message=message,
        details={
            "zone_id": zone.get("id"),
            "zone_name": zone.get("name"),
            "assigned_units": units,
            "priority_score": score,
            "reasons": reasons,
        },
    )


def explain_forecast(zone_id: Any, total: float, horizon: str) -> ExplainEntry:
    """What the forecast means for a single zone."""
    phrase = _HORIZON_PHRASES.get(horizon, horizon)
    total_val = _round(total, 2)
    message = (
        f"Forecast for zone {zone_id}: ~{total_val} expected violations "
        f"over the {phrase}."
    )
    return make_explain(
        code="forecast_zone",
        message=message,
        details={"zone_id": zone_id, "total": total_val, "horizon": horizon},
    )


def explain_verdict(verdict: dict[str, Any]) -> ExplainEntry:
    """Plain-English summary of the final recommendation."""
    action = str(verdict.get("priority_action") or "Monitor")
    reasoning = str(verdict.get("reasoning") or "No specific signals available.")
    message = f"Recommended action: {action} — {reasoning}"
    return make_explain(
        code="verdict",
        message=message,
        details={"priority_action": action, "reasoning": reasoning},
    )

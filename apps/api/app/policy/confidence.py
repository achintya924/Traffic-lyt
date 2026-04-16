"""
Phase 5.10: Forecast confidence scoring for policy baselines.
Pure functions — no DB, no I/O, no side effects.

Scores a zone's history on three weighted factors:
    * data_volume  (40%) — point count vs thresholds (10=medium, 30=high)
    * volatility   (35%) — coefficient of variation over nonzero counts
    * zero_ratio   (25%) — share of zero-count buckets (more zeros = lower)

Combined score -> label: >= 0.70 high, >= 0.40 medium, else low.
Multi-zone aggregation uses the weakest-link (min) rule so any single
low-confidence zone pulls the overall confidence down.
"""
from __future__ import annotations

import math
from typing import Any, Literal


ConfidenceLabel = Literal["low", "medium", "high"]

MIN_POINTS_MEDIUM = 10
MIN_POINTS_HIGH = 30

WEIGHT_VOLUME = 0.40
WEIGHT_VOLATILITY = 0.35
WEIGHT_ZERO_RATIO = 0.25

LABEL_HIGH_THRESHOLD = 0.70
LABEL_MEDIUM_THRESHOLD = 0.40


def _data_volume_score(n: int) -> float:
    if n >= MIN_POINTS_HIGH:
        return 1.0
    if n >= MIN_POINTS_MEDIUM:
        return 0.5 + 0.5 * (n - MIN_POINTS_MEDIUM) / (MIN_POINTS_HIGH - MIN_POINTS_MEDIUM)
    return max(0.0, (n / MIN_POINTS_MEDIUM) * 0.5)


def _volatility_score(counts: list[int]) -> tuple[float, float | None]:
    """Return (score, cv). Neutral 0.5 if fewer than 2 nonzero points."""
    nonzero = [c for c in counts if c > 0]
    if len(nonzero) < 2:
        return 0.5, None
    mean = sum(nonzero) / len(nonzero)
    if mean <= 0:
        return 0.5, None
    variance = sum((c - mean) ** 2 for c in nonzero) / len(nonzero)
    cv = math.sqrt(variance) / mean
    score = max(0.0, min(1.0, 1.0 - cv / 2.0))
    return score, cv


def _zero_ratio_score(counts: list[int]) -> tuple[float, float]:
    if not counts:
        return 0.0, 1.0
    zeros = sum(1 for c in counts if c == 0)
    ratio = zeros / len(counts)
    return max(0.0, 1.0 - ratio), ratio


def _label_for(score: float) -> ConfidenceLabel:
    if score >= LABEL_HIGH_THRESHOLD:
        return "high"
    if score >= LABEL_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def score_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Score a zone's forecast history into a confidence value + components.

    Returns dict with keys:
        confidence_score  float in [0, 1]
        confidence_label  'low'|'medium'|'high'
        details           component scores + weights + raw metrics
    """
    counts = [int(h.get("count", 0)) for h in history]
    n = len(counts)

    vol_score = _data_volume_score(n)
    vlt_score, cv = _volatility_score(counts)
    zr_score, zero_ratio = _zero_ratio_score(counts)

    combined = (
        WEIGHT_VOLUME * vol_score
        + WEIGHT_VOLATILITY * vlt_score
        + WEIGHT_ZERO_RATIO * zr_score
    )
    combined = round(max(0.0, min(1.0, combined)), 4)
    label = _label_for(combined)

    details = {
        "point_count": n,
        "volume_score": round(vol_score, 4),
        "volatility_score": round(vlt_score, 4),
        "coefficient_of_variation": round(cv, 4) if cv is not None else None,
        "zero_ratio": round(zero_ratio, 4),
        "zero_ratio_score": round(zr_score, 4),
        "weights": {
            "volume": WEIGHT_VOLUME,
            "volatility": WEIGHT_VOLATILITY,
            "zero_ratio": WEIGHT_ZERO_RATIO,
        },
    }

    return {
        "confidence_score": combined,
        "confidence_label": label,
        "details": details,
    }


def aggregate_zone_confidences(
    zone_confidences: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Weakest-link aggregation: overall score = min of per-zone scores.
    Input items need at least {zone_id, confidence_score, confidence_label}.
    """
    if not zone_confidences:
        return {
            "confidence_score": 0.0,
            "confidence_label": "low",
            "details": {
                "rule": "weakest_link",
                "weakest_zone_id": None,
                "zone_count": 0,
            },
        }

    weakest = min(zone_confidences, key=lambda z: float(z.get("confidence_score", 0.0)))
    score = round(float(weakest.get("confidence_score", 0.0)), 4)
    return {
        "confidence_score": score,
        "confidence_label": _label_for(score),
        "details": {
            "rule": "weakest_link",
            "weakest_zone_id": weakest.get("zone_id"),
            "zone_count": len(zone_confidences),
        },
    }

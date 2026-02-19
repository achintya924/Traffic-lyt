"""
Phase 4.2: Stable request signature for model cache keys.
Normalizes filters and params into a deterministic string for cache keying.
"""
from typing import Any

# Bump when feature engineering or model contract changes (invalidates old cache).
FEATURE_VERSION = "v1"

# Phase 4.3: Bump to invalidate response cache (used by response_cache.make_response_key).
RESPONSE_CACHE_VERSION = "v1"


def _normalize_bbox(bbox: str | None) -> str:
    """Normalize bbox to fixed decimals and canonical order: minLon,minLat,maxLon,maxLat."""
    if not bbox or not bbox.strip():
        return ""
    parts = [p.strip() for p in bbox.split(",")]
    if len(parts) != 4:
        return ""
    try:
        min_lon, min_lat, max_lon, max_lat = (round(float(p), 5) for p in parts)
    except ValueError:
        return ""
    return f"{min_lon},{min_lat},{max_lon},{max_lat}"


def _normalize_violation_type(v: str | None) -> str:
    """Canonical string for violation_type (sorted if multiple in future)."""
    if not v or not str(v).strip():
        return ""
    return str(v).strip()


def request_signature(
    *,
    endpoint_name: str,
    anchor_ts: str | None,
    granularity: str,
    bbox: str | None = None,
    violation_type: str | None = None,
    hour_start: int | None = None,
    hour_end: int | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    model_params: dict[str, Any] | None = None,
    feature_version: str = FEATURE_VERSION,
) -> str:
    """
    Build a deterministic cache key component from request context.
    anchor_ts should be the Phase 4.1 effective anchor (e.g. data_max_ts as ISO string).
    """
    parts = [
        f"ep={endpoint_name}",
        f"fv={feature_version}",
        f"gran={granularity}",
        f"anchor={anchor_ts or ''}",
        f"bbox={_normalize_bbox(bbox)}",
        f"vt={_normalize_violation_type(violation_type)}",
        f"h_start={hour_start if hour_start is not None else ''}",
        f"h_end={hour_end if hour_end is not None else ''}",
        f"start={start_iso or ''}",
        f"end={end_iso or ''}",
    ]
    if model_params:
        # Sort keys for determinism
        for k in sorted(model_params.keys()):
            v = model_params[k]
            if v is not None:
                parts.append(f"{k}={v}")
    return "|".join(parts)


def request_signature_stats(
    *,
    anchor_ts: str | None,
    bbox: str | None = None,
    violation_type: str | None = None,
    hour_start: int | None = None,
    hour_end: int | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    response_version: str = RESPONSE_CACHE_VERSION,
) -> str:
    """Deterministic signature for GET /violations/stats (no granularity)."""
    parts = [
        "ep=stats",
        f"rv={response_version}",
        f"anchor={anchor_ts or ''}",
        f"bbox={_normalize_bbox(bbox)}",
        f"vt={_normalize_violation_type(violation_type)}",
        f"h_start={hour_start if hour_start is not None else ''}",
        f"h_end={hour_end if hour_end is not None else ''}",
        f"start={start_iso or ''}",
        f"end={end_iso or ''}",
    ]
    return "|".join(parts)


def request_signature_hotspots(
    *,
    anchor_ts: str | None,
    cell_m: int,
    recent_days: int,
    baseline_days: int,
    limit: int,
    bbox: str | None = None,
    violation_type: str | None = None,
    hour_start: int | None = None,
    hour_end: int | None = None,
    start_iso: str | None = None,
    end_iso: str | None = None,
    response_version: str = RESPONSE_CACHE_VERSION,
) -> str:
    """Deterministic signature for GET /predict/hotspots/grid."""
    parts = [
        "ep=hotspots_grid",
        f"rv={response_version}",
        f"anchor={anchor_ts or ''}",
        f"bbox={_normalize_bbox(bbox)}",
        f"vt={_normalize_violation_type(violation_type)}",
        f"h_start={hour_start if hour_start is not None else ''}",
        f"h_end={hour_end if hour_end is not None else ''}",
        f"start={start_iso or ''}",
        f"end={end_iso or ''}",
        f"cell_m={cell_m}",
        f"recent_days={recent_days}",
        f"baseline_days={baseline_days}",
        f"limit={limit}",
    ]
    return "|".join(parts)

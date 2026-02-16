"""Hotspot risk scoring grid (Phase 3.3): recent vs baseline window counts. Phase 4.1: anchor to data_max_ts."""

from datetime import timedelta
from typing import Any

from sqlalchemy.engine import Connection

from app.queries.hotspot_sql import build_hotspot_grid_sql
from app.utils.time_anchor import (
    build_time_window_meta,
    get_data_time_range,
    to_utc_iso,
)
from app.utils.violation_filters import ViolationFilters, build_violation_where

METERS_PER_DEGREE_APPROX = 111320.0


def get_hotspot_grid(
    conn: Connection,
    filters: ViolationFilters,
    cell_m: int = 250,
    recent_days: int = 7,
    baseline_days: int = 30,
    limit: int = 5000,
) -> dict[str, Any]:
    """
    Return grid cells with recent_count, baseline_count, ratio, score (0-100), risk_level.
    Phase 4.1: anchor_end = filters.end or data_max_ts (same filter scope). Recent/baseline windows use that anchor.
    """
    grid_size_deg = cell_m / METERS_PER_DEGREE_APPROX
    data_min_ts, data_max_ts = get_data_time_range(conn, filters)

    if filters.end is not None:
        anchor_end = filters.end
        window_source = "absolute"
    else:
        anchor_end = data_max_ts
        window_source = "anchored"

    if anchor_end is None:
        time_meta = build_time_window_meta(
            data_min_ts=None,
            data_max_ts=None,
            anchor_ts=None,
            effective_start_ts=None,
            effective_end_ts=None,
            window_source="anchored",
            message="No data for the given filter scope.",
        )
        return {
            "cells": [],
            "meta": {
                "cell_m": cell_m,
                "grid_size_deg": round(grid_size_deg, 8),
                "recent_days": recent_days,
                "baseline_days": baseline_days,
                "points": 0,
                **time_meta,
            },
        }

    recent_start = anchor_end - timedelta(days=recent_days)
    baseline_end = recent_start
    baseline_start = baseline_end - timedelta(days=baseline_days)

    if filters.start is not None:
        baseline_start = max(baseline_start, filters.start)
        recent_start = max(recent_start, filters.start)
    if data_min_ts is not None:
        baseline_start = max(baseline_start, data_min_ts)
        recent_start = max(recent_start, data_min_ts)

    recent_filters = ViolationFilters(
        start=recent_start,
        end=anchor_end,
        hour_start=filters.hour_start,
        hour_end=filters.hour_end,
        violation_type=filters.violation_type,
        bbox=filters.bbox,
    )
    baseline_filters = ViolationFilters(
        start=baseline_start,
        end=baseline_end,
        hour_start=filters.hour_start,
        hour_end=filters.hour_end,
        violation_type=filters.violation_type,
        bbox=filters.bbox,
    )

    where_recent, params_recent = build_violation_where(recent_filters, param_prefix="recent_")
    where_baseline, params_baseline = build_violation_where(baseline_filters, param_prefix="baseline_")

    params = {
        "grid_size_deg": grid_size_deg,
        "recent_days": recent_days,
        "baseline_days": baseline_days,
        "limit": limit,
        **params_recent,
        **params_baseline,
    }

    sql = build_hotspot_grid_sql(where_recent, where_baseline)
    rows = conn.execute(sql, params).fetchall()

    time_meta = build_time_window_meta(
        data_min_ts=data_min_ts,
        data_max_ts=data_max_ts,
        anchor_ts=anchor_end,
        effective_start_ts=baseline_start,
        effective_end_ts=anchor_end,
        window_source=window_source,
        effective_window_extra={
            "recent": {"start_ts": to_utc_iso(recent_start), "end_ts": to_utc_iso(anchor_end)},
            "baseline": {"start_ts": to_utc_iso(baseline_start), "end_ts": to_utc_iso(baseline_end)},
        },
    )
    base_meta = {
        "cell_m": cell_m,
        "grid_size_deg": round(grid_size_deg, 8),
        "recent_days": recent_days,
        "baseline_days": baseline_days,
    }

    if not rows:
        return {
            "cells": [],
            "meta": {**base_meta, "points": 0, **time_meta},
        }

    ratios = []
    for r in rows:
        ratio_val = float(r[6]) if r[6] is not None else 0.0
        ratios.append(ratio_val)

    min_ratio = min(ratios)
    max_ratio = max(ratios)
    span = max_ratio - min_ratio

    cells: list[dict[str, Any]] = []
    for r in rows:
        cell_x, cell_y = float(r[0]), float(r[1])
        centroid_lon, centroid_lat = float(r[2]), float(r[3])
        recent_count = int(r[4])
        baseline_count = int(r[5])
        ratio_val = float(r[6]) if r[6] is not None else 0.0

        if span == 0:
            score = 0.0
        else:
            score = 100.0 * (ratio_val - min_ratio) / span

        if score >= 70:
            risk_level = "high"
        elif score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"

        cells.append({
            "centroid": [round(centroid_lon, 6), round(centroid_lat, 6)],
            "recent_count": recent_count,
            "baseline_count": baseline_count,
            "ratio": round(ratio_val, 6),
            "score": round(score, 2),
            "risk_level": risk_level,
        })

    return {
        "cells": cells,
        "meta": {**base_meta, "points": len(cells), **time_meta},
    }

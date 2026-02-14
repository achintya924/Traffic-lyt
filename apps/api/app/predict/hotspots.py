"""Hotspot risk scoring grid (Phase 3.3): recent vs baseline window counts."""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.queries.hotspot_sql import build_hotspot_grid_sql
from app.utils.violation_filters import ViolationFilters, build_violation_where

METERS_PER_DEGREE_APPROX = 111320.0


def _anchor_end_from_db(conn: Connection, filters: ViolationFilters) -> datetime | None:
    """When no end filter is set, use MAX(occurred_at) so static datasets still return hotspots."""
    no_time = ViolationFilters(
        start=None,
        end=None,
        hour_start=filters.hour_start,
        hour_end=filters.hour_end,
        violation_type=filters.violation_type,
        bbox=filters.bbox,
    )
    where_sql, params = build_violation_where(no_time)
    row = conn.execute(
        text("SELECT MAX(occurred_at) AS anchor FROM violations" + where_sql),
        params,
    ).fetchone()
    if not row or row[0] is None:
        return None
    anchor = row[0]
    if isinstance(anchor, date) and not isinstance(anchor, datetime):
        anchor = datetime.combine(anchor, datetime.min.time())
    elif getattr(anchor, "tzinfo", None) is not None:
        anchor = anchor.replace(tzinfo=None)
    return anchor


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

    anchor_end = filters.end, or MAX(occurred_at) when end is not set (for static datasets).
    recent = [anchor_end - recent_days, anchor_end]; baseline = [baseline_end - baseline_days, baseline_end].
    Clamps to filters.start when set.
    """
    grid_size_deg = cell_m / METERS_PER_DEGREE_APPROX
    if filters.end is not None:
        anchor_end = filters.end
    else:
        anchor_end = _anchor_end_from_db(conn, filters)
        if anchor_end is None:
            return {
                "cells": [],
                "meta": {
                    "cell_m": cell_m,
                    "grid_size_deg": round(grid_size_deg, 8),
                    "recent_days": recent_days,
                    "baseline_days": baseline_days,
                    "points": 0,
                },
            }
    recent_start = anchor_end - timedelta(days=recent_days)
    baseline_end = recent_start
    baseline_start = baseline_end - timedelta(days=baseline_days)

    if filters.start is not None:
        baseline_start = max(baseline_start, filters.start)
        recent_start = max(recent_start, filters.start)

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

    if not rows:
        return {
            "cells": [],
            "meta": {
                "cell_m": cell_m,
                "grid_size_deg": round(grid_size_deg, 8),
                "recent_days": recent_days,
                "baseline_days": baseline_days,
                "points": 0,
            },
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
        "meta": {
            "cell_m": cell_m,
            "grid_size_deg": round(grid_size_deg, 8),
            "recent_days": recent_days,
            "baseline_days": baseline_days,
            "points": len(cells),
        },
    }

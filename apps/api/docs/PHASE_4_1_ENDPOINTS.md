# Phase 4.1: Time window anchoring – endpoints updated

All relative time windows anchor to the dataset’s **MAX(occurred_at)** for the **same filter context** (bbox, violation_type, hour_start/hour_end). No wall-clock `now()`.

## Data freshness contract in responses

Responses that support it include a **meta** object (or top-level keys) with:

- **data_min_ts**: minimum `occurred_at` in the effective filter scope (UTC ISO 8601)
- **data_max_ts**: maximum `occurred_at` in that scope (the anchor)
- **anchor_ts**: timestamp used as anchor (generally = data_max_ts)
- **effective_window**: `{ start_ts, end_ts }` actually used (and for hotspots: `recent` / `baseline` sub-ranges)
- **window_source**: `"anchored"` (relative window anchored to data) or `"absolute"` (user provided start/end)
- **timezone**: `"UTC"`

When there is no data for the scope, `data_min_ts` / `data_max_ts` / `anchor_ts` and effective_window may be null and **message** may be set.

## Endpoints updated for Phase 4.1

| Endpoint | Change |
|----------|--------|
| **GET /predict/timeseries** | When start/end not provided, effective window = [data_min_ts, data_max_ts]. Response **meta** includes data_min_ts, data_max_ts, anchor_ts, effective_window, window_source, timezone. |
| **GET /predict/forecast** | Uses anchored filters when no start/end. **meta** includes time contract. |
| **GET /predict/trends** | Uses anchored filters when no start/end. **meta** includes time contract. |
| **GET /predict/hotspots/grid** | Anchors to data_max_ts when end not provided (already did in 3.3; now uses shared `get_data_time_range`). **meta** includes data_min_ts, data_max_ts, anchor_ts, effective_window (recent + baseline), window_source, timezone. No data → 200 with empty cells and meta with nulls + message. |
| **GET /predict/risk** | Uses anchored filters when no start/end. **meta** includes time contract. |
| **GET /violations/stats** | **meta** added with data_min_ts, data_max_ts, anchor_ts, effective_window, window_source, timezone. |

## Endpoints not changed (backward compatibility)

- **GET /aggregations/time/hour**, **GET /aggregations/time/day** – return raw lists; adding meta would require a new response shape and break existing clients. They still use the same filter semantics (user start/end when provided).

## Shared utility

- **app/utils/time_anchor.py**: `get_data_time_range(conn, filters)`, `compute_anchored_window(...)`, `build_time_window_meta(...)`, `filters_without_time(...)`, `to_utc_iso(...)`.

# Phase 4.9A: 30-Day Area Forecast + Data Sufficiency

## Overview

- **30-day daily forecast**: Use `granularity=day` and `horizon=30` for area-level forecast over the next 30 days.
- **Data sufficiency guard**: Returns `meta.data_quality` when recent activity is too low to trust the forecast.

## Query params

| Param | Default | Description |
|-------|---------|-------------|
| granularity | hour | `hour` or `day` |
| horizon | 24 (hour) / 30 (day) | Number of future buckets |
| model | ma | naive, ma, ewm |
| window | 6 | MA window size |
| alpha | 0.3 | EWM smoothing |
| limit_history | 500 | History points |
| bbox | — | Bounding box (required for area) |

## Response summary

```json
{
  "summary": {
    "expected_total": 150,
    "horizon": 30,
    "granularity": "day",
    "scope": "viewport"
  }
}
```

## data_quality warning

When recent activity is below thresholds:

```json
{
  "meta": {
    "data_quality": {
      "status": "insufficient_data",
      "reason": "Low recent activity: 15 events, 5 nonzero days in last 90 days...",
      "total_events_last_90d": 15,
      "nonzero_days_last_90d": 5,
      "recommendation": "Zoom out or choose a larger area for a more reliable forecast."
    }
  }
}
```

Thresholds (tuneable):

- `total_events_last_90d < 30` OR `nonzero_days_last_90d < 10` → insufficient

## UI messaging

- When `meta.data_quality.status == "insufficient_data"`:
  - Show: "Not enough recent data in this view. Zoom out for a more reliable forecast."
- Normal case:
  - Hour: "Expected ~X violations over next 24h"
  - Day: "Expected ~X violations over next 30 days"

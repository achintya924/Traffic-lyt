# Phase 4.4: API rate limiting (in-memory)

Minimal in-process rate limiting to protect heavy endpoints from accidental abuse.

## Groups and limits (default)

| Group   | Limit          | Endpoints                                                                 |
|---------|----------------|---------------------------------------------------------------------------|
| predict | 30 req/min     | /predict/risk, /predict/forecast, /predict/trends, /predict/hotspots/grid |
| stats   | 60 req/min     | /violations/stats                                                         |
| internal| unlimited      | /internal/cache (DEBUG only)                                              |

## Protected endpoints

- **GET /predict/risk**
- **GET /predict/forecast**
- **GET /predict/trends**
- **GET /predict/hotspots/grid**
- **GET /violations/stats**

## Not rate-limited

- **GET /internal/cache** (DEBUG only)
- **GET /health**, **GET /db-check**, **GET /violations**
- **GET /predict/timeseries** (not in Phase 4.4 scope)
- Aggregation endpoints

## 429 response

When limit exceeded:

- **Status:** HTTP 429
- **Body:** `{ "detail": "Rate limit exceeded", "group": "...", "retry_after_seconds": N }`
- **Header:** `Retry-After: N` (seconds until window resets)

## Client identification

- Uses `request.client.host` (client IP).
- If `DEBUG=true`, also honors `X-Forwarded-For` (first value). Avoid in production due to spoofing risk.

## Tuning via env (optional)

- **RATE_LIMIT_PREDICT**: Override predict group limit (e.g. `RATE_LIMIT_PREDICT=60`).
- **RATE_LIMIT_STATS**: Override stats group limit (e.g. `RATE_LIMIT_STATS=120`).
- **RATE_LIMIT_DISABLED**: Set to `true`/`1`/`yes` to disable all rate limiting (e.g. for tests).

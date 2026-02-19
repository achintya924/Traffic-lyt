# Phase 4.3: In-memory response cache (LRU + TTL)

Response-level caching for heavy endpoints so identical requests return a cached JSON payload without recomputation. Complements Phase 4.2 model cache: **when response cache hits, the request short-circuits** (no DB, no model training).

## Components

- **app/utils/response_cache.py**: `ResponseCache` (LRU + TTL), `make_response_key()`, `get_response_cache()`, `short_hash()` (from model_registry). `RESPONSE_CACHE_VERSION` for global invalidation.
- **app/utils/signature.py**: `request_signature_stats()`, `request_signature_hotspots()`, `RESPONSE_CACHE_VERSION`; existing `request_signature()` used for risk/forecast.

## Cached endpoints and TTLs

| Endpoint | Default TTL |
|----------|-------------|
| GET /violations/stats | 60 s |
| GET /predict/risk | 60 s |
| GET /predict/forecast | 45 s |
| GET /predict/hotspots/grid | 60 s |

## Key composition

Response key is deterministic and includes:

- **Endpoint name** (stats, risk, forecast, hotspots_grid)
- **Request signature**: normalized bbox (5 decimals), violation_type, hour_start/hour_end, start/end, and endpoint-specific params (e.g. cell_m, recent_days, baseline_days for hotspots; alpha, horizon, limit_history for risk).
- **anchor_ts** from Phase 4.1 (e.g. data_max_ts as UTC ISO).
- **effective_window** (start_ts, end_ts) so different time windows yield different keys.
- **RESPONSE_CACHE_VERSION** (e.g. `v1`). Bump to invalidate all response cache entries.

Stored key format: `resp:{endpoint}:{sha256(...)}`.

## meta.response_cache shape

Every cached endpoint adds to response **meta**:

- **hit** (bool): Whether the response came from the response cache.
- **key_hash** (str): Short (12-char) hash of the cache key.
- **ttl_seconds** (number): TTL used for this entry.

Example (miss): `"response_cache": { "hit": false, "key_hash": "a1b2c3d4e5f6", "ttl_seconds": 60 }`  
Example (hit):  `"response_cache": { "hit": true, "key_hash": "a1b2c3d4e5f6", "ttl_seconds": 60 }`

## Relationship with Phase 4.2 model cache

- **Response cache is checked first.** If there is a response-cache hit, the handler returns the cached payload (with `meta.response_cache.hit` set to `true`) and does **not** run DB queries or model registry lookup. So no double compute.
- If response cache misses, the handler runs as before (including model cache for risk/forecast). The new response is then stored in the response cache and returned with `meta.response_cache.hit: false` and `meta.model_cache` unchanged when present.

## Cache safety

- Only 200 responses are cached; errors are not cached.
- Cached values are JSON-serializable (dict/list/str/number/null).
- No-data responses (e.g. empty stats) are cached with the same TTL.

## Internal endpoint

**GET /internal/cache** (DEBUG=true) returns:

- **model_registry**: Phase 4.2 stats (hits, misses, evictions, keys_count, size).
- **response_cache**: Phase 4.3 stats (hits, misses, evictions, keys_count).

## Tests

- **tests/test_response_cache.py**: meta shape, same params → second request hit, different bbox/start-end → miss, TTL expiry, make_response_key determinism.

Run:

```bash
docker compose -f infra/docker-compose.yml exec api pytest -q -v tests/test_response_cache.py tests/test_model_cache.py tests/test_stats.py
```

# Phase 4.2: Model lifecycle + training cache

In-process model registry to avoid retraining on every request. No Redis, Celery, or external infra.

## Components

- **app/utils/model_registry.py**: `ModelRegistry` (LRU + TTL eviction), `CacheEntry`, `get_registry()`, `make_model_key()`, `short_hash()`.
- **app/utils/signature.py**: `request_signature()` for deterministic cache keys (bbox normalized, anchor_ts from Phase 4.1 meta, model params, feature_version).

## Cache key

Key is built from:

- Endpoint name (`risk`, `forecast`)
- **anchor_ts** (Phase 4.1: `data_max_ts` or effective anchor as UTC ISO string) so new data invalidates cache.
- Normalized filters: bbox (5 decimals), violation_type, hour_start/hour_end, start/end ISO.
- Granularity and model params (alpha, horizon, window, alpha for ewm, etc.).
- **feature_version** (`v1`). Bump to invalidate all entries when features or model contract change.

Stored key format: `{endpoint}:{sha256(full_signature)}` so `invalidate_prefix("risk:")` clears all risk entries.

## TTL defaults

| Endpoint   | TTL        |
|-----------|------------|
| /predict/risk    | 600 s (10 min) |
| /predict/forecast | 120 s (2 min)  |

## What is cached

- **Risk**: Trained Poisson pipeline (fitted sklearn Pipeline), `last_ts_iso`, `explain` (coefficients), `metrics` (backtest mae/mape), `history_points`. No raw data arrays.
- **Forecast**: Computed `{ history, forecast }` (the series arrays). TTL shorter because computation is cheaper.

## Response meta

Predictive responses include **meta.model_cache**:

- **hit** (bool): Whether the result came from cache.
- **key_hash** (str): Short (12-char) hash of the cache key; do not expose full key.
- **ttl_seconds** (int/float): TTL used for this entry.

Example (miss): `"model_cache": { "hit": false, "key_hash": "a1b2c3d4e5f6", "ttl_seconds": 600 }`  
Example (hit):  `"model_cache": { "hit": true, "key_hash": "a1b2c3d4e5f6", "ttl_seconds": 600 }`

## Registry config

- **max_items** default: 256. Eviction: expired (TTL) first, then LRU by `last_access`.
- **Thread-safe**: `threading.Lock` around get/set/stats.

## Internal endpoint

- **GET /internal/cache**: Returns `registry.stats()` (hits, misses, evictions, keys_count, size) when **DEBUG=true**. Otherwise returns `{ "error": "disabled", "message": "Set DEBUG=true to enable" }`.

## Logging

- `model_cache_hit` / `model_cache_miss` at INFO with `endpoint`, `key_hash`, `elapsed_ms`.

## Tests

- **tests/test_model_cache.py**: Same params → second request cache hit; different bbox or start/end → different key (miss); meta.model_cache shape and keys.

Run:  
`docker compose -f infra/docker-compose.yml exec api pytest -q -v tests/test_model_cache.py tests/test_time_anchor.py tests/test_stats.py`

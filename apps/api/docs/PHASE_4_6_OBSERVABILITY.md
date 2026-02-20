# Phase 4.6: Observability lite

Request IDs, structured logging, minimal metrics. No external infra.

## Request ID

- If `X-Request-ID` header present, use it; else generate `uuid4().hex` (32 chars).
- Stored on `request.state.request_id`.
- Response header `X-Request-ID` echoes the value.

## Structured logs

Each request logs one completion line as JSON:

```json
{"event": "request_complete", "request_id": "abc123...", "method": "GET", "path": "/violations/stats", "status_code": 200, "elapsed_ms": 45, "client_ip": "127.0.0.1", "response_cache_hit": true}
```

Standard fields (included when present):

- `event`: `request_complete` or `request_error`
- `request_id`
- `method`, `path`, `status_code`, `elapsed_ms`, `client_ip`
- `response_cache_hit`, `model_cache_hit` (bool)
- `rate_limited`, `retry_after_seconds` (when 429)
- `error_type` (on `request_error`)
- `slow`: true when elapsed_ms >= SLOW_THRESHOLD_MS

## Internal metrics (DEBUG only)

**GET /internal/metrics** (requires `DEBUG=true`):

```json
{
  "uptime_seconds": 1234.56,
  "model_registry": {"hits": 10, "misses": 5, "evictions": 0, "keys_count": 5, "size": 5},
  "response_cache": {"hits": 20, "misses": 5, "evictions": 0, "keys_count": 5},
  "rate_limiter": {"allowed": {"predict": 30, "stats": 60}, "blocked": {"predict": 2}}
}
```

## View logs

```bash
docker compose -f infra/docker-compose.yml logs -f api
```

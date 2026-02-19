# Phase 4.5: Query profiling and index optimization

## Profiling targets

| Endpoint | Core queries | Location |
|----------|--------------|----------|
| GET /violations/stats | totals_sql, top_types_sql; get_data_time_range | stats.py, violation_filters, time_anchor |
| GET /predict/hotspots/grid | CTE with recent/baseline counts on violations | hotspot_sql.py, hotspots.py |
| GET /predict/risk | get_counts_timeseries (date_trunc + GROUP BY); get_data_time_range | predict_sql.py, timeseries.py, time_anchor |

## Indexes (idempotent)

| Index | Type | Purpose |
|-------|------|---------|
| idx_violations_geom | GIST | bbox filter `geom && ST_MakeEnvelope(...)` |
| idx_violations_occurred_at | B-tree | time range, MIN/MAX, date_trunc |
| idx_violations_type_occurred | B-tree composite | violation_type + occurred_at filters |

## Apply indexes

```bash
# From repo root
docker compose -f infra/docker-compose.yml exec db psql -U trafficlyt -d trafficlyt -c "
CREATE INDEX IF NOT EXISTS idx_violations_geom ON violations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_violations_occurred_at ON violations (occurred_at);
CREATE INDEX IF NOT EXISTS idx_violations_type_occurred ON violations (violation_type, occurred_at);
"
```

Or pipe the SQL file:
```bash
cat apps/api/db/001_indexes_phase4_5.sql | docker compose -f infra/docker-compose.yml exec -T db psql -U trafficlyt -d trafficlyt
```

## EXPLAIN commands (inside db container)

Connect:
```bash
docker compose -f infra/docker-compose.yml exec db psql -U trafficlyt -d trafficlyt
```

### Stats (totals)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)::int AS total, MIN(occurred_at) AS min_time, MAX(occurred_at) AS max_time
FROM violations
WHERE geom && ST_MakeEnvelope(-74.1, 40.6, -73.9, 40.8, 4326);
```

### Stats (top types)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT violation_type, COUNT(*)::int AS count
FROM violations
WHERE geom && ST_MakeEnvelope(-74.1, 40.6, -73.9, 40.8, 4326)
GROUP BY violation_type
ORDER BY count DESC
LIMIT 10;
```

### Time anchor (data range)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT MIN(occurred_at) AS min_ts, MAX(occurred_at) AS max_ts
FROM violations
WHERE geom && ST_MakeEnvelope(-74.1, 40.6, -73.9, 40.8, 4326);
```

### Hotspots (representative)

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH recent AS (
  SELECT ST_X(ST_SnapToGrid(geom, 0.00224)) AS gx, ST_Y(ST_SnapToGrid(geom, 0.00224)) AS gy,
         COUNT(*)::int AS recent_count
  FROM violations
  WHERE occurred_at >= '2024-12-18 01:51:00' AND occurred_at <= '2024-12-25 01:51:00'
    AND geom && ST_MakeEnvelope(-74.1, 40.6, -73.9, 40.8, 4326)
  GROUP BY gx, gy
),
baseline AS (
  SELECT ST_X(ST_SnapToGrid(geom, 0.00224)) AS gx, ST_Y(ST_SnapToGrid(geom, 0.00224)) AS gy,
         COUNT(*)::int AS baseline_count
  FROM violations
  WHERE occurred_at >= '2024-11-18 01:51:00' AND occurred_at < '2024-12-18 01:51:00'
    AND geom && ST_MakeEnvelope(-74.1, 40.6, -73.9, 40.8, 4326)
  GROUP BY gx, gy
)
SELECT COALESCE(r.gx, b.gx) AS cell_x, COALESCE(r.gy, b.gy) AS cell_y,
       COALESCE(r.recent_count, 0)::int, COALESCE(b.baseline_count, 0)::int
FROM recent r FULL OUTER JOIN baseline b ON r.gx = b.gx AND r.gy = b.gy
LIMIT 3000;
```

### Timeseries (risk / forecast input)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT date_trunc('hour', occurred_at) AS ts, COUNT(*)::int AS count
FROM violations
WHERE geom && ST_MakeEnvelope(-74.1, 40.6, -73.9, 40.8, 4326)
GROUP BY ts
ORDER BY ts ASC;
```

## Before/after

After applying indexes, rerun EXPLAIN and verify:

- `idx_violations_geom` used for bbox filter (Index Scan using idx_violations_geom)
- `idx_violations_occurred_at` or `idx_violations_type_occurred` used for time predicates when applicable
- Execution time and "Buffers: shared hit" improved vs sequential scan

## Timing middleware

Every request is logged with method, path, status, elapsed_ms. Requests above 300ms are logged as WARNING.

Override via `SLOW_THRESHOLD_MS` env (e.g. `SLOW_THRESHOLD_MS=500`).

## View timing logs

View request timing via docker logs:

```bash
docker compose -f infra/docker-compose.yml logs -f api
```

Example output:
```
request_timing method=GET path=/violations/stats status=200 elapsed_ms=45
slow_request method=GET path=/predict/hotspots/grid status=200 elapsed_ms=320
```

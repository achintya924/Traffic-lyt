-- Phase 4.5: Idempotent index creation for violations table.
-- Run: psql $DATABASE_URL -f apps/api/db/001_indexes_phase4_5.sql
-- Or: docker compose exec db psql -U trafficlyt -d trafficlyt -f /path/to/001_indexes_phase4_5.sql
-- (copy file into container or run via: cat 001_indexes_phase4_5.sql | docker compose exec -T db psql -U trafficlyt -d trafficlyt)

-- GIST on geom (likely already from ingest_nyc)
CREATE INDEX IF NOT EXISTS idx_violations_geom ON violations USING GIST (geom);

-- B-tree on occurred_at (likely already from ingest_nyc)
CREATE INDEX IF NOT EXISTS idx_violations_occurred_at ON violations (occurred_at);

-- Composite for common filter: violation_type + occurred_at
CREATE INDEX IF NOT EXISTS idx_violations_type_occurred ON violations (violation_type, occurred_at);

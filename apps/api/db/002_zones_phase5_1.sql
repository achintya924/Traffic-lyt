-- Phase 5.1: Zones table for named areas (polygon + optional bbox).
-- Run: psql $DATABASE_URL -f apps/api/db/002_zones_phase5_1.sql
-- Or: docker compose exec db psql -U trafficlyt -d trafficlyt -f /path/to/002_zones_phase5_1.sql

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS zones (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    zone_type TEXT NOT NULL DEFAULT 'custom',
    geom GEOMETRY(Polygon, 4326) NOT NULL,
    bbox_minx DOUBLE PRECISION,
    bbox_miny DOUBLE PRECISION,
    bbox_maxx DOUBLE PRECISION,
    bbox_maxy DOUBLE PRECISION,
    tags JSONB,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_zones_name_unique ON zones (LOWER(name));
CREATE INDEX IF NOT EXISTS idx_zones_geom ON zones USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_zones_zone_type ON zones (zone_type);

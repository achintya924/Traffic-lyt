-- Migration: add city column to violations and zones tables
-- Run against an existing database to enable multi-city support.
-- Safe to run multiple times (uses IF NOT EXISTS / column check).

-- violations table
ALTER TABLE violations ADD COLUMN IF NOT EXISTS city VARCHAR(50) DEFAULT 'nyc';
CREATE INDEX IF NOT EXISTS idx_violations_city ON violations (city);

-- Backfill London rows based on coordinate range
UPDATE violations
SET city = 'london'
WHERE city = 'nyc'
  AND raw_lat BETWEEN 51.2 AND 51.8
  AND raw_lon BETWEEN -0.6 AND 0.4;

-- zones table
ALTER TABLE zones ADD COLUMN IF NOT EXISTS city VARCHAR(50) DEFAULT 'nyc';

-- Backfill London zones by name
UPDATE zones
SET city = 'london'
WHERE city = 'nyc'
  AND name IN (
    'Bloomsbury', 'Camden Town', 'Hampstead', 'Kentish Town',
    'Kings Cross', 'Gospel Oak', 'Holborn', 'Swiss Cottage'
  );

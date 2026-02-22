"""
Initialize zones table (Phase 5.1).
Run: python -m app.scripts.init_zones
  (from container: docker compose exec api python -m app.scripts.init_zones)
"""
import logging
import os

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ZONES_DDL = """
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
"""


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        raise SystemExit(1)

    engine = create_engine(database_url, pool_pre_ping=True)
    logger.info("Creating zones table and indexes")
    with engine.connect() as conn:
        for stmt in ZONES_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    logger.info("Zones table ready")


if __name__ == "__main__":
    main()

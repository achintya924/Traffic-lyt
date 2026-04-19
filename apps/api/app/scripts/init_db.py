"""
Initialize the Traffic-lyt database schema against any PostgreSQL instance.

Creates the PostGIS extension, violations table, and zones table with all
required indexes. Safe to run repeatedly — all statements use IF NOT EXISTS.

Usage:
    DATABASE_URL=postgresql://user:pass@host:5432/dbname python -m app.scripts.init_db

Works against Railway (or any remote Postgres) without Railway CLI —
just set DATABASE_URL to the connection string shown in the Railway dashboard.
"""
import logging
import os
import sys

from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL — matches schemas used by ingest_nyc.py, generate_synthetic_data.py,
#        init_zones.py, and init_nyc_zones.py exactly.
# ---------------------------------------------------------------------------

_STEPS = [
    (
        "Enable PostGIS extension",
        "CREATE EXTENSION IF NOT EXISTS postgis",
    ),
    (
        "Create violations table",
        """
        CREATE TABLE IF NOT EXISTS violations (
            id             SERIAL PRIMARY KEY,
            occurred_at    TIMESTAMP,
            violation_type TEXT,
            geom           GEOMETRY(Point, 4326) NOT NULL,
            raw_lat        DOUBLE PRECISION,
            raw_lon        DOUBLE PRECISION
        )
        """,
    ),
    (
        "Create violations spatial index",
        "CREATE INDEX IF NOT EXISTS idx_violations_geom ON violations USING GIST (geom)",
    ),
    (
        "Create violations time index",
        "CREATE INDEX IF NOT EXISTS idx_violations_occurred_at ON violations (occurred_at)",
    ),
    (
        "Create zones table",
        """
        CREATE TABLE IF NOT EXISTS zones (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            zone_type  TEXT NOT NULL DEFAULT 'custom',
            geom       GEOMETRY(Polygon, 4326) NOT NULL,
            bbox_minx  DOUBLE PRECISION,
            bbox_miny  DOUBLE PRECISION,
            bbox_maxx  DOUBLE PRECISION,
            bbox_maxy  DOUBLE PRECISION,
            tags       JSONB,
            created_at TIMESTAMP DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW() NOT NULL
        )
        """,
    ),
    (
        "Create zones unique-name index",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_zones_name_unique ON zones (LOWER(name))",
    ),
    (
        "Create zones spatial index",
        "CREATE INDEX IF NOT EXISTS idx_zones_geom ON zones USING GIST (geom)",
    ),
    (
        "Create zones type index",
        "CREATE INDEX IF NOT EXISTS idx_zones_zone_type ON zones (zone_type)",
    ),
]


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error(
            "DATABASE_URL is not set. "
            "Export it before running:\n"
            "  DATABASE_URL=postgresql://user:pass@host:5432/dbname "
            "python -m app.scripts.init_db"
        )
        sys.exit(1)

    # Mask password in log output
    safe_url = database_url
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(database_url)
        if parsed.password:
            safe_url = urlunparse(parsed._replace(
                netloc=f"{parsed.username}:***@{parsed.hostname}"
                       + (f":{parsed.port}" if parsed.port else "")
            ))
    except Exception:
        pass

    logger.info("Connecting to: %s", safe_url)

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Connection OK")
    except Exception as exc:
        logger.error("Cannot connect to database: %s", exc)
        sys.exit(1)

    total = len(_STEPS)
    with engine.connect() as conn:
        for i, (description, sql) in enumerate(_STEPS, start=1):
            try:
                conn.execute(text(sql.strip()))
                conn.commit()
                logger.info("[%d/%d] ✓  %s", i, total, description)
            except Exception as exc:
                conn.rollback()
                logger.error("[%d/%d] ✗  %s — %s", i, total, description, exc)
                sys.exit(1)

    logger.info(
        "Schema initialisation complete. "
        "Next steps:\n"
        "  • Load data:  python -m app.scripts.generate_synthetic_data\n"
        "  • Add zones:  python -m app.scripts.init_nyc_zones"
    )


if __name__ == "__main__":
    main()

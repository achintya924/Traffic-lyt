"""
Ingest NYC violations sample CSV into PostGIS violations table.
Run: python -m app.scripts.ingest_nyc
  (from container: docker compose exec api python -m app.scripts.ingest_nyc)
"""
import csv
import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NYC approximate bounds
NYC_LAT_MIN, NYC_LAT_MAX = 40.4774, 40.9176
NYC_LON_MIN, NYC_LON_MAX = -74.2591, -73.7004

TABLE_DDL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS violations (
    id SERIAL PRIMARY KEY,
    occurred_at TIMESTAMP,
    violation_type TEXT,
    geom GEOMETRY(Point, 4326) NOT NULL,
    raw_lat DOUBLE PRECISION,
    raw_lon DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_violations_geom ON violations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_violations_occurred_at ON violations (occurred_at);
"""


def parse_float(s: str | None) -> float | None:
    if s is None or s.strip() == "":
        return None
    try:
        return float(s.strip())
    except ValueError:
        return None


def in_nyc_bounds(lat: float, lon: float) -> bool:
    return (
        NYC_LAT_MIN <= lat <= NYC_LAT_MAX
        and NYC_LON_MIN <= lon <= NYC_LON_MAX
    )


def main() -> None:
    data_dir = os.getenv("DATA_DIR", "/data")
    csv_path = Path(data_dir) / "nyc_violations_sample.csv"
    if not csv_path.exists():
        logger.error("CSV not found: %s", csv_path)
        raise SystemExit(1)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        raise SystemExit(1)

    engine = create_engine(database_url, pool_pre_ping=True)

    # Create table and indexes
    logger.info("Ensuring PostGIS and violations table exist")
    with engine.connect() as conn:
        for stmt in TABLE_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()

    # Read and validate rows
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            lat = parse_float(raw.get("latitude"))
            lon = parse_float(raw.get("longitude"))
            if lat is None or lon is None:
                continue
            if not in_nyc_bounds(lat, lon):
                continue
            issue_date = (raw.get("issue_date") or "").strip()
            violation_time = (raw.get("violation_time") or "").strip()
            occurred_at = None
            if issue_date:
                # Optional: combine with time if present (HH:MM)
                if violation_time:
                    occurred_at = f"{issue_date} {violation_time}:00"
                else:
                    occurred_at = f"{issue_date} 00:00:00"
            rows.append({
                "occurred_at": occurred_at or None,
                "violation_type": (raw.get("violation_type") or "").strip() or None,
                "lat": lat,
                "lon": lon,
            })

    logger.info("Valid rows: %d (from %s)", len(rows), csv_path)

    if not rows:
        logger.warning("No valid rows to insert")
        return

    # Truncate and load in batches
    batch_size = 500
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE violations RESTART IDENTITY"))
        conn.commit()

    # Use CAST(... AS TIMESTAMP) instead of ::timestamp so SQLAlchemy doesn't treat "::" as a second parameter
    insert_sql = text("""
        INSERT INTO violations (occurred_at, violation_type, geom, raw_lat, raw_lon)
        VALUES (
            CAST(:occurred_at AS TIMESTAMP),
            :violation_type,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
            :lat,
            :lon
        )
    """)

    inserted = 0
    with engine.connect() as conn:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            for r in batch:
                conn.execute(
                    insert_sql,
                    {
                        "occurred_at": r["occurred_at"],
                        "violation_type": r["violation_type"],
                        "lat": r["lat"],
                        "lon": r["lon"],
                    },
                )
            conn.commit()
            inserted += len(batch)
            logger.info("Inserted batch: %d rows (total %d)", len(batch), inserted)

    logger.info("Ingest complete: %d rows", inserted)


if __name__ == "__main__":
    main()

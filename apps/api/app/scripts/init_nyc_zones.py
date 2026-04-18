"""
Replace auto-generated test zones with realistic named NYC neighborhood zones.

Run: python -m app.scripts.init_nyc_zones
  (from container: docker compose -f infra/docker-compose.yml exec api python -m app.scripts.init_nyc_zones)

Each zone is created as a rectangular polygon using ST_MakeEnvelope(minx, miny, maxx, maxy, 4326).
Existing zones are deleted first so this script is safe to re-run.
"""
import logging
import os

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# (name, zone_type, minx, miny, maxx, maxy)
NYC_ZONES = [
    ("Midtown Manhattan",  "neighborhood", -74.00, 40.745, -73.97, 40.765),
    ("Lower Manhattan",    "neighborhood", -74.02, 40.700, -73.99, 40.720),
    ("Brooklyn Downtown",  "neighborhood", -74.00, 40.685, -73.97, 40.705),
    ("Williamsburg",       "neighborhood", -73.97, 40.705, -73.94, 40.725),
    ("Astoria Queens",     "neighborhood", -73.94, 40.765, -73.91, 40.785),
    ("South Bronx",        "neighborhood", -73.93, 40.815, -73.90, 40.835),
    ("Harlem",             "neighborhood", -73.96, 40.800, -73.93, 40.820),
    ("Upper East Side",    "neighborhood", -73.97, 40.765, -73.95, 40.785),
]

_INSERT_SQL = text("""
    INSERT INTO zones (name, zone_type, geom, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy)
    VALUES (
        :name,
        :zone_type,
        ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326),
        :minx,
        :miny,
        :maxx,
        :maxy
    )
""")


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        raise SystemExit(1)

    engine = create_engine(database_url, pool_pre_ping=True)

    with engine.connect() as conn:
        deleted = conn.execute(text("DELETE FROM zones")).rowcount
        conn.commit()
        logger.info("Deleted %d existing zone(s).", deleted)

        for name, zone_type, minx, miny, maxx, maxy in NYC_ZONES:
            conn.execute(_INSERT_SQL, {
                "name":      name,
                "zone_type": zone_type,
                "minx":      minx,
                "miny":      miny,
                "maxx":      maxx,
                "maxy":      maxy,
            })
            conn.commit()
            logger.info(
                "Inserted zone: %s  [%.4f,%.4f → %.4f,%.4f]",
                name, minx, miny, maxx, maxy,
            )

    logger.info("Done. %d NYC neighborhood zones inserted.", len(NYC_ZONES))


if __name__ == "__main__":
    main()

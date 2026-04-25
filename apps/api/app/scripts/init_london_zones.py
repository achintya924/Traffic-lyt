"""
Initialise the zones table with 8 Camden Borough ward zones.

Run: python -m app.scripts.init_london_zones
  (from container: docker compose exec api python -m app.scripts.init_london_zones)

Existing zones are deleted first so this script is safe to re-run.
Coordinates are WGS-84 decimal degrees (EPSG:4326).
"""
import logging
import os

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# (name, zone_type, minLon, minLat, maxLon, maxLat)
CAMDEN_ZONES = [
    ("Bloomsbury",    "neighborhood", -0.138, 51.514, -0.110, 51.528),
    ("Camden Town",   "neighborhood", -0.155, 51.534, -0.128, 51.548),
    ("Hampstead",     "neighborhood", -0.185, 51.547, -0.148, 51.568),
    ("Kentish Town",  "neighborhood", -0.152, 51.544, -0.128, 51.558),
    ("Kings Cross",   "neighborhood", -0.130, 51.526, -0.106, 51.538),
    ("Gospel Oak",    "neighborhood", -0.165, 51.552, -0.140, 51.564),
    ("Holborn",       "neighborhood", -0.125, 51.510, -0.097, 51.524),
    ("Swiss Cottage", "neighborhood", -0.178, 51.538, -0.155, 51.552),
]

_INSERT_SQL = text("""
    INSERT INTO zones (name, zone_type, geom, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy, city)
    VALUES (
        :name,
        :zone_type,
        ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326),
        :minx,
        :miny,
        :maxx,
        :maxy,
        :city
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

        for name, zone_type, minx, miny, maxx, maxy in CAMDEN_ZONES:
            conn.execute(_INSERT_SQL, {
                "name":      name,
                "zone_type": zone_type,
                "minx":      minx,
                "miny":      miny,
                "maxx":      maxx,
                "maxy":      maxy,
                "city":      "london",
            })
            conn.commit()
            logger.info(
                "Inserted zone: %-16s  [%.3f, %.3f → %.3f, %.3f]",
                name, minx, miny, maxx, maxy,
            )

    logger.info("Done. %d Camden ward zones inserted.", len(CAMDEN_ZONES))


if __name__ == "__main__":
    main()

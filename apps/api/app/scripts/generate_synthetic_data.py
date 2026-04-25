"""
Generate and insert a synthetic NYC traffic violations dataset (50k–80k records).
Designed to produce data dense enough for meaningful forecasting, hotspot
detection, and zone analytics.

Run: python -m app.scripts.generate_synthetic_data
  (from container: docker compose exec api python -m app.scripts.generate_synthetic_data)

Properties:
  - 65,000 records spanning 2022-01-01 → 2024-12-31
  - Spatially concentrated around 5 NYC hotspots + 15% random noise
  - Weekday/weekend ratio 1.4:1, peak-hour bias, monthly seasonality
  - Per-week WoW variance ±20% for realistic time-series texture
  - Fixed RNG seed (42) for reproducibility
"""
import logging
import os
import time
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

N_RECORDS      = int(os.getenv("COUNT", "65000"))
BATCH_SIZE     = 5_000
PROGRESS_EVERY = 5_000
RNG_SEED       = 42
BATCH_RETRY_MAX   = 3
BATCH_SLEEP_SEC   = 0.5

DATE_START = date(2022, 1, 1)
DATE_END   = date(2024, 12, 31)

# (lat_center, lon_center, spread_degrees, share_of_total)
# Shares must sum to (1.0 - NOISE_PROB)
HOTSPOTS = [
    (40.754, -73.984, 0.015, 0.30),   # Midtown Manhattan      — highest density
    (40.713, -74.006, 0.012, 0.21),   # Lower Manhattan        — high density
    (40.692, -73.990, 0.015, 0.17),   # Brooklyn Downtown      — medium-high
    (40.728, -73.944, 0.018, 0.10),   # Queens                 — medium
    (40.837, -73.886, 0.016, 0.07),   # Bronx                  — medium
]
NOISE_PROB = 0.15   # uniform scatter across all of NYC

NYC_LAT_MIN, NYC_LAT_MAX = 40.4774, 40.9176
NYC_LON_MIN, NYC_LON_MAX = -74.2591, -73.7004

# (label, probability)  — must sum to 1.0
VIOLATION_TYPES = [
    ("NO STANDING",        0.30),
    ("NO PARKING",         0.25),
    ("EXPIRED METER",      0.20),
    ("FIRE HYDRANT",       0.10),
    ("DOUBLE PARKING",     0.10),
    ("BUS LANE VIOLATION", 0.05),
]

# Hour-of-day weights (index = hour 0–23)
# Three peaks: 8–9 am, 12–1 pm, 5–7 pm
HOUR_WEIGHTS = [
    0.40, 0.25, 0.20, 0.20, 0.30, 0.55,   # 00–05  night / very early
    1.00, 2.20, 3.60, 3.10, 2.20, 2.60,   # 06–11  morning peak
    3.60, 3.00, 2.20, 2.10, 2.50, 3.60,   # 12–17  midday / afternoon
    4.00, 3.60, 2.80, 1.80, 1.10, 0.65,   # 18–23  evening peak / night
]

# Monthly seasonality multipliers (Jan=index 0 … Dec=index 11)
MONTH_WEIGHTS = [
    0.85, 0.80, 0.90, 0.95, 1.00, 1.10,
    1.15, 1.15, 1.05, 1.00, 0.90, 0.85,
]


# ---------------------------------------------------------------------------
# Generation helpers
# ---------------------------------------------------------------------------

def _build_day_weights(
    rng: np.random.Generator,
) -> tuple[list[date], np.ndarray]:
    """Return (all_dates, normalised_weights) for the full date range.

    Incorporates:
      - weekday vs weekend ratio (1.4 : 1)
      - monthly seasonality via MONTH_WEIGHTS
      - per-ISO-week WoW variance of ±20%
    """
    all_dates: list[date] = []
    d = DATE_START
    while d <= DATE_END:
        all_dates.append(d)
        d += timedelta(days=1)

    # One shared random multiplier per ISO week for WoW variance
    week_factor: dict[tuple[int, int], float] = {}
    for d in all_dates:
        iso = d.isocalendar()
        key = (iso.year, iso.week)
        if key not in week_factor:
            week_factor[key] = rng.uniform(0.80, 1.20)

    weights = np.zeros(len(all_dates))
    for i, d in enumerate(all_dates):
        iso = d.isocalendar()
        weights[i] = (
            (1.4 if d.weekday() < 5 else 1.0)   # weekday vs weekend
            * MONTH_WEIGHTS[d.month - 1]          # seasonal
            * week_factor[(iso.year, iso.week)]   # WoW noise
        )

    weights /= weights.sum()
    return all_dates, weights


def _generate_spatial(
    rng: np.random.Generator,
    n: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (lats, lons) arrays of length n using hotspot gaussians + noise."""
    spatial_probs = np.array([h[3] for h in HOTSPOTS] + [NOISE_PROB], dtype=float)
    cluster_ids   = rng.choice(len(spatial_probs), size=n, p=spatial_probs)

    lats = np.empty(n)
    lons = np.empty(n)

    for ci, (clat, clon, spread, _) in enumerate(HOTSPOTS):
        mask  = cluster_ids == ci
        count = int(mask.sum())
        if count:
            lats[mask] = rng.normal(clat, spread, count)
            lons[mask] = rng.normal(clon, spread, count)

    noise_mask  = cluster_ids == len(HOTSPOTS)
    noise_count = int(noise_mask.sum())
    if noise_count:
        lats[noise_mask] = rng.uniform(NYC_LAT_MIN, NYC_LAT_MAX, noise_count)
        lons[noise_mask] = rng.uniform(NYC_LON_MIN, NYC_LON_MAX, noise_count)

    return lats, lons


def generate_records(rng: np.random.Generator) -> list[dict]:
    logger.info("Building date-weight distribution over %s → %s…", DATE_START, DATE_END)
    all_dates, day_weights = _build_day_weights(rng)
    day_indices = rng.choice(len(all_dates), size=N_RECORDS, p=day_weights)

    logger.info("Sampling hours…")
    hour_probs = np.array(HOUR_WEIGHTS, dtype=float)
    hour_probs /= hour_probs.sum()
    hours   = rng.choice(24, size=N_RECORDS, p=hour_probs)
    minutes = rng.integers(0, 60, size=N_RECORDS)
    seconds = rng.integers(0, 60, size=N_RECORDS)

    logger.info("Sampling violation types…")
    v_labels  = [vt[0] for vt in VIOLATION_TYPES]
    v_probs   = np.array([vt[1] for vt in VIOLATION_TYPES], dtype=float)
    v_indices = rng.choice(len(v_labels), size=N_RECORDS, p=v_probs)

    logger.info("Sampling spatial points across %d hotspots + noise…", len(HOTSPOTS))
    lats, lons = _generate_spatial(rng, N_RECORDS)

    logger.info("Assembling %d records…", N_RECORDS)
    records: list[dict] = []
    for i in range(N_RECORDS):
        d  = all_dates[day_indices[i]]
        ts = datetime(
            d.year, d.month, d.day,
            int(hours[i]), int(minutes[i]), int(seconds[i]),
        )
        records.append({
            "occurred_at":    ts.strftime("%Y-%m-%d %H:%M:%S"),
            "violation_type": v_labels[v_indices[i]],
            "lat":            float(lats[i]),
            "lon":            float(lons[i]),
            "city":           "nyc",
        })
    return records


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_INSERT_SQL = text("""
    INSERT INTO violations (occurred_at, violation_type, geom, raw_lat, raw_lon, city)
    VALUES (
        CAST(:occurred_at AS TIMESTAMP),
        :violation_type,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
        :lat,
        :lon,
        :city
    )
""")


def _ensure_table(engine) -> None:
    ddl = """
    CREATE EXTENSION IF NOT EXISTS postgis;

    CREATE TABLE IF NOT EXISTS violations (
        id           SERIAL PRIMARY KEY,
        occurred_at  TIMESTAMP,
        violation_type TEXT,
        geom         GEOMETRY(Point, 4326) NOT NULL,
        raw_lat      DOUBLE PRECISION,
        raw_lon      DOUBLE PRECISION
    );

    CREATE INDEX IF NOT EXISTS idx_violations_geom        ON violations USING GIST (geom);
    CREATE INDEX IF NOT EXISTS idx_violations_occurred_at ON violations (occurred_at);
    """
    with engine.connect() as conn:
        for stmt in ddl.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _insert_batch(engine, batch: list[dict]) -> None:
    """Insert one batch, retrying up to BATCH_RETRY_MAX times on OperationalError."""
    for attempt in range(1, BATCH_RETRY_MAX + 1):
        try:
            with engine.connect() as conn:
                for r in batch:
                    conn.execute(_INSERT_SQL, r)
                conn.commit()
            return
        except OperationalError as exc:
            if attempt == BATCH_RETRY_MAX:
                logger.error(
                    "Batch failed after %d attempts: %s", BATCH_RETRY_MAX, exc
                )
                raise
            wait = attempt * 5
            logger.warning(
                "OperationalError on attempt %d/%d — reconnecting in %ds: %s",
                attempt, BATCH_RETRY_MAX, wait, exc,
            )
            time.sleep(wait)
            # Dispose the pool so the next connect() gets a fresh connection.
            engine.dispose()


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        raise SystemExit(1)

    engine = create_engine(database_url, pool_pre_ping=True)

    logger.info("Ensuring violations table exists…")
    _ensure_table(engine)

    # ── Resume support ───────────────────────────────────────────────────────
    # Check how many rows are already present so a partial run can continue
    # from where it left off instead of truncating and starting over.
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM violations WHERE city = 'nyc'")).scalar() or 0

    rng     = np.random.default_rng(RNG_SEED)
    records = generate_records(rng)

    if existing >= len(records):
        logger.info(
            "Database already contains %d records (target %d). Nothing to do.",
            existing, len(records),
        )
        return

    if existing > 0:
        logger.info(
            "Resuming from record %d (skipping %d already-inserted rows).",
            existing, existing,
        )
        records = records[existing:]
    else:
        logger.info("Fresh run — deleting existing NYC violations…")
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM violations WHERE city = 'nyc'"))
            conn.commit()

    logger.info(
        "Inserting %d records in batches of %d (sleep %ds between batches)…",
        len(records), BATCH_SIZE, BATCH_SLEEP_SEC,
    )
    inserted = existing
    total    = existing + len(records)

    for batch_start in range(0, len(records), BATCH_SIZE):
        batch = records[batch_start : batch_start + BATCH_SIZE]
        _insert_batch(engine, batch)
        inserted += len(batch)
        if inserted % PROGRESS_EVERY == 0 or inserted == total:
            logger.info(
                "Progress: %d / %d records inserted (%.1f%%)",
                inserted, total, 100.0 * inserted / total,
            )
        if batch_start + BATCH_SIZE < len(records):
            time.sleep(BATCH_SLEEP_SEC)

    logger.info("Done. %d synthetic violation records in database.", inserted)


if __name__ == "__main__":
    main()

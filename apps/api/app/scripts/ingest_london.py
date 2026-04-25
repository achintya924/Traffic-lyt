"""
Ingest Camden Borough PCN (Penalty Charge Notice) data into the violations table.

Source file: data/london_pcn.csv
Run: python -m app.scripts.ingest_london
  (from container: docker compose exec api python -m app.scripts.ingest_london)

~209,656 of the 348,222 rows carry coordinates; the rest are skipped.
"""
import logging
import os
import time
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# London (Camden) bounding box
LON_LAT_MIN, LON_LAT_MAX = 51.2, 51.8
LON_LON_MIN, LON_LON_MAX = -0.6, 0.4

BATCH_SIZE      = 2_000
PROGRESS_EVERY  = 10_000
BATCH_RETRY_MAX = 3
BATCH_SLEEP_SEC = 1

# "Contravention Date" format: "29/11/2024 03:52:00 PM"
DATE_FMT = "%d/%m/%Y %I:%M:%S %p"

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


def _parse_date(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, DATE_FMT)
    except ValueError:
        return None


def _violation_type(row: "pd.Series") -> str:
    for col in ("Contravention Code Description", "Ticket Description"):
        val = str(row.get(col, "") or "").strip()
        if val:
            return val[:100]
    return "UNKNOWN"


BASE_DIR = os.path.dirname(      # Traffic-lyt/
    os.path.dirname(              # apps/
        os.path.dirname(          # api/
            os.path.dirname(      # app/
                os.path.dirname(  # scripts/
                    os.path.abspath(__file__)  # ingest_london.py
                )
            )
        )
    )
)
CSV_PATH = os.path.join(BASE_DIR, "data", "london_pcn.csv")


def main() -> None:
    logger.info("Resolved CSV path: %s", CSV_PATH)
    if not os.path.exists(CSV_PATH):
        logger.error("CSV not found: %s", CSV_PATH)
        raise SystemExit(1)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        raise SystemExit(1)

    # ── Load CSV ─────────────────────────────────────────────────────────────
    logger.info("Reading %s …", CSV_PATH)
    df = pd.read_csv(CSV_PATH, dtype=str, low_memory=False)
    total_rows = len(df)
    logger.info("Total rows in file: %d", total_rows)

    # ── Filter: require both Latitude and Longitude ──────────────────────────
    has_coords = (
        df["Latitude"].notna() & (df["Latitude"].str.strip() != "") &
        df["Longitude"].notna() & (df["Longitude"].str.strip() != "")
    )
    skipped_no_coords = int((~has_coords).sum())
    df = df[has_coords].copy()
    logger.info(
        "Rows with coordinates: %d  |  skipped (no coords): %d",
        len(df), skipped_no_coords,
    )

    # ── Convert coordinate columns to float ──────────────────────────────────
    df["_lat"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["_lon"] = pd.to_numeric(df["Longitude"], errors="coerce")

    # ── Build validated row list ──────────────────────────────────────────────
    logger.info("Parsing and validating rows …")
    rows: list[dict] = []
    skipped_validation = 0

    for _, row in df.iterrows():
        lat = row["_lat"]
        lon = row["_lon"]

        # Validate coordinates
        if pd.isna(lat) or pd.isna(lon):
            skipped_validation += 1
            continue
        if not (LON_LAT_MIN <= lat <= LON_LAT_MAX):
            skipped_validation += 1
            continue
        if not (LON_LON_MIN <= lon <= LON_LON_MAX):
            skipped_validation += 1
            continue

        # Parse timestamp
        occurred_at = _parse_date(str(row.get("Contravention Date", "") or ""))
        if occurred_at is None:
            skipped_validation += 1
            continue

        rows.append({
            "occurred_at":    occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
            "violation_type": _violation_type(row),
            "lat":            float(lat),
            "lon":            float(lon),
            "city":           "london",
        })

    logger.info(
        "Valid rows to insert: %d  |  skipped (validation): %d",
        len(rows), skipped_validation,
    )

    if not rows:
        logger.warning("No valid rows to insert — aborting.")
        return

    # ── DB setup ─────────────────────────────────────────────────────────────
    engine = create_engine(database_url, pool_pre_ping=True)

    # ── Resume: count London rows already present ─────────────────────────────
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT COUNT(*) FROM violations WHERE raw_lat BETWEEN 51.2 AND 51.8")
        ).scalar() or 0

    if existing >= len(rows):
        logger.info(
            "Database already contains %d London rows (target %d). Nothing to do.",
            existing, len(rows),
        )
        return

    if existing > 0:
        logger.info("Resuming from row %d — skipping %d already-inserted rows.", existing, existing)
        rows = rows[existing:]
    else:
        logger.info("Fresh run — deleting existing London violations…")
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM violations WHERE city = 'london'"))
            conn.commit()

    total_to_insert = existing + len(rows)
    logger.info("Inserting %d rows in batches of %d (sleep %ds between batches) …",
                len(rows), BATCH_SIZE, BATCH_SLEEP_SEC)

    inserted = existing
    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]

        # Retry loop
        for attempt in range(1, BATCH_RETRY_MAX + 1):
            try:
                with engine.connect() as conn:
                    for r in batch:
                        conn.execute(_INSERT_SQL, {
                            "occurred_at":    r["occurred_at"],
                            "violation_type": r["violation_type"],
                            "lat":            r["lat"],
                            "lon":            r["lon"],
                            "city":           r["city"],
                        })
                    conn.commit()
                break  # success
            except OperationalError as exc:
                if attempt == BATCH_RETRY_MAX:
                    logger.error("Batch failed after %d attempts: %s", BATCH_RETRY_MAX, exc)
                    raise
                logger.warning(
                    "OperationalError on attempt %d/%d — reconnecting in 3s: %s",
                    attempt, BATCH_RETRY_MAX, exc,
                )
                time.sleep(3)
                engine.dispose()

        inserted += len(batch)
        if inserted % PROGRESS_EVERY == 0 or inserted == total_to_insert:
            logger.info(
                "Progress: %d / %d inserted (%.1f%%)",
                inserted, total_to_insert, 100.0 * inserted / total_to_insert,
            )
        if batch_start + BATCH_SIZE < len(rows):
            time.sleep(BATCH_SLEEP_SEC)

    # ── Final summary ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info("Total rows in file       : %d", total_rows)
    logger.info("Skipped (no coords)      : %d", skipped_no_coords)
    logger.info("Skipped (validation)     : %d", skipped_validation)
    logger.info("Inserted                 : %d", inserted)
    logger.info("─" * 60)


if __name__ == "__main__":
    main()

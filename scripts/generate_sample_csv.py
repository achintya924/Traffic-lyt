"""
One-off script to generate data/nyc_violations_sample.csv.
Run from repo root: python scripts/generate_sample_csv.py
"""
import csv
import random
from pathlib import Path

# NYC approximate bounds (Manhattan + boroughs)
NYC_LAT_MIN, NYC_LAT_MAX = 40.4774, 40.9176
NYC_LON_MIN, NYC_LON_MAX = -74.2591, -73.7004

VIOLATION_TYPES = [
    "No Parking",
    "Parking in No Standing Zone",
    "Expired Meter",
    "Double Parking",
    "Blocking Driveway",
    "Street Cleaning",
    "No Standing",
    "Fire Hydrant",
    "Bus Stop",
    "Expired Registration",
]

def main():
    out = Path(__file__).resolve().parent.parent / "data" / "nyc_violations_sample.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 2500
    random.seed(42)
    rows = []
    for i in range(n):
        lat = round(random.uniform(NYC_LAT_MIN, NYC_LAT_MAX), 6)
        lon = round(random.uniform(NYC_LON_MIN, NYC_LON_MAX), 6)
        # issue_date YYYY-MM-DD, violation_time optional HH:MM
        year = random.randint(2022, 2024)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        issue_date = f"{year}-{month:02d}-{day:02d}"
        hour = random.randint(0, 23)
        minute = random.randint(0, 59)
        violation_time = f"{hour:02d}:{minute:02d}"
        violation_type = random.choice(VIOLATION_TYPES)
        rows.append({
            "latitude": lat,
            "longitude": lon,
            "violation_time": violation_time,
            "violation_type": violation_type,
            "issue_date": issue_date,
        })
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["latitude", "longitude", "violation_time", "violation_type", "issue_date"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")

if __name__ == "__main__":
    main()

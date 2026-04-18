# Traffic-lyt

**NYC traffic violation analytics platform** — spatial hotspot detection, zone-level trend analysis, early warnings, patrol allocation, policy simulation, and unified decision support.

![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-black?style=flat-square&logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-316192?style=flat-square&logo=postgresql&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostGIS-3.4-4479A1?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)

---

## Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Interactive Map** | Live violation markers, animated heatmap overlay, hotspot grid, forecast risk layer |
| 2 | **Zone Analytics** | Per-neighborhood totals, time-series, top violation types, trend direction |
| 3 | **Zone Rankings** | Sort zones by risk score, trend velocity, or raw volume |
| 4 | **Early Warnings** | Automatic warning cards for trend spikes, WoW/MoM anomalies, and anomaly clusters |
| 5 | **Patrol Allocation** | Deterministic unit-assignment recommendations across zones with reason chips |
| 6 | **Policy Simulator** | Model enforcement interventions (intensity, patrol units, peak-hour reduction) against a forecast baseline |
| 7 | **Decision Dashboard** | Unified "what should I do right now?" recommendation — verdict, confidence, hotspots, patrol plan, forecast |
| 8 | **Export & Reporting** | CSV export on Zones, Patrol, and Policy pages; printable Decision report via browser print dialog |

---

## Screenshots

> _Add screenshots here after first run._

| Page | Screenshot |
|------|-----------|
| Map | ![Map page — violation markers and heatmap overlay](docs/screenshots/map.png) |
| Decision Dashboard | ![Decision Dashboard — verdict card and patrol recommendation](docs/screenshots/decision.png) |
| Patrol Allocation | ![Patrol Allocation — priority-ranked zone list](docs/screenshots/patrol.png) |
| Policy Simulator | ![Policy Simulator — baseline vs simulated comparison bars](docs/screenshots/policy.png) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), TypeScript, Leaflet, CSS |
| Backend | FastAPI 0.115, SQLAlchemy 2, scikit-learn, numpy |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Infrastructure | Docker Compose |

---

## Quick Start

### Prerequisites

- Docker Desktop (WSL2 or Hyper-V backend on Windows)
- `docker compose` v2

```bash
docker --version
docker compose version
```

### 1 — Clone and configure

```bash
git clone <repo-url>
cd Traffic-lyt
cp .env.example .env          # defaults work out of the box
```

### 2 — Start the stack

```bash
docker compose -f infra/docker-compose.yml up --build
```

First build pulls PostGIS and installs all deps (~2 min). Subsequent starts are fast.

| Service | URL |
|---------|-----|
| Web app | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

### 3 — Initialise zones

```bash
docker compose -f infra/docker-compose.yml exec api python -m app.scripts.init_nyc_zones
```

Inserts 8 realistic NYC neighborhood zones (Midtown Manhattan, Lower Manhattan, Brooklyn Downtown, Williamsburg, Astoria Queens, South Bronx, Harlem, Upper East Side).

### 4 — Load violation data

**Recommended — synthetic dataset (65 k records, 2022–2024):**

```bash
docker compose -f infra/docker-compose.yml exec api python -m app.scripts.generate_synthetic_data
# shortcut: make gen-data
```

**Alternative — real NYC open-data sample (~2 500 records):**

```bash
docker compose -f infra/docker-compose.yml exec api python -m app.scripts.ingest_nyc
# shortcut: make ingest
```

### 5 — Open the app

Go to **http://localhost:3000** and use the nav bar: Map → Zones → Warnings → Patrol → Policy → Decision.

---

## Makefile Targets

```bash
make up        # docker compose up -d
make build     # docker compose up --build -d
make down      # docker compose down
make ingest    # ingest real NYC sample CSV
make gen-data  # generate + insert 65 k synthetic records
```

---

## API Endpoints

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness — `{"status":"ok"}` |
| GET | `/db-check` | DB connectivity |

### Violations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/violations` | Raw points (`limit`, `offset`, bbox, type filters) |
| GET | `/violations/stats` | Aggregate stats (totals, top types, optional filters) |

### Aggregations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/aggregations/time/hour` | Counts by hour of day |
| GET | `/aggregations/time/day` | Counts by date |
| GET | `/aggregations/grid` | Spatial grid aggregation |

### Predictions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/predict/timeseries` | Historical time-series |
| GET | `/predict/forecast` | Short-term violation forecast |
| GET | `/predict/trends` | Zone trend signals |
| GET | `/predict/hotspots/grid` | Grid-based hotspot detection |
| GET | `/predict/risk` | Risk score per grid cell |

### Zones

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/zones` | Create a zone (GeoJSON Polygon body) |
| GET | `/api/zones` | List zones (`limit`, `offset`, `zone_type`, `search`) |
| GET | `/api/zones/{id}` | Zone detail + geometry |
| DELETE | `/api/zones/{id}` | Delete a zone |
| GET | `/api/zones/rankings` | Rank by `risk` \| `trend` \| `volume` |
| GET | `/api/zones/{id}/analytics` | Totals, time-series, top types, trend |
| GET | `/api/zones/{id}/compare` | WoW / MoM delta comparison |

### Anomalies & Warnings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/anomalies/heatmap` | Z-score anomaly heatmap points |
| GET | `/api/warnings` | Warning cards for zones exceeding thresholds |

### Decision Support

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/patrol/allocate` | Allocate N units across zones by strategy |
| POST | `/api/policy/simulate` | Simulate an enforcement intervention |
| POST | `/api/decision/now` | Unified action recommendation |

---

## Folder Structure

```
Traffic-lyt/
├── apps/
│   ├── api/                        # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py             # App factory + router registration
│   │   │   ├── db.py               # SQLAlchemy engine + connection helper
│   │   │   ├── routers/            # One module per API group
│   │   │   ├── scripts/
│   │   │   │   ├── init_nyc_zones.py          # Insert 8 NYC zones
│   │   │   │   ├── generate_synthetic_data.py # 65 k synthetic records
│   │   │   │   └── ingest_nyc.py              # Real NYC CSV ingestion
│   │   │   ├── predict/            # Forecasting, hotspots, trends, risk
│   │   │   ├── policy/             # Baseline + simulation engine
│   │   │   ├── queries/            # Reusable SQL builders
│   │   │   └── utils/              # Rate limiter, cache, explainability
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── web/                        # Next.js 14 frontend
│       └── app/
│           ├── components/         # NavBar, CachePill, ZoneMultiSelect …
│           ├── lib/
│           │   ├── api.ts          # Typed fetch helpers for every endpoint
│           │   └── csv.ts          # Client-side CSV export utility
│           ├── map/                # /map  — Leaflet map + heatmap
│           ├── zones/              # /zones — rankings + compare panel
│           ├── warnings/           # /warnings — live warning cards
│           ├── patrol/             # /patrol — allocation form + map
│           ├── policy/             # /policy — intervention simulator
│           ├── decision/           # /decision — unified action dashboard
│           └── globals.css
├── data/                           # nyc_violations_sample.csv
├── infra/
│   └── docker-compose.yml
├── Makefile
└── README.md
```

---

## Troubleshooting

**Port already in use (3000 / 8000 / 5432)**
Find the process (`netstat -ano | findstr :8000` on Windows) and stop it, or change the host port mapping in `infra/docker-compose.yml`.

**`No module named app.scripts.*` inside container**
The Dockerfile copies source at build time. Rebuild the api image after adding new scripts:
```bash
docker compose -f infra/docker-compose.yml up --build -d api
```

**API returns empty results after fresh start**
Zones and violation data must be loaded after every fresh database (see Quick Start steps 3–4).

**Wipe everything and start fresh**
```bash
docker compose -f infra/docker-compose.yml down -v   # removes pgdata volume
docker compose -f infra/docker-compose.yml up --build
# then re-run init_nyc_zones + generate_synthetic_data
```

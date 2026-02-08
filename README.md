# Traffic-lyt

NYC-first traffic/parking violations analytics.

- **Phase 0:** Repo scaffolding + local infra (Docker, FastAPI, Next.js, PostGIS).
- **Phase 1:** Data in, data out — load sample CSV, violations API, map UI.
- **Phase 2.0:** Violation filters, GET /violations/stats, map shows filtered total; API tests (pytest).

## Repo structure

```
traffic-lyt/
├── apps/
│   ├── api/          # FastAPI (app.main, app.scripts.ingest_nyc)
│   └── web/          # Next.js + TypeScript (/map)
├── data/             # Sample CSV for ingestion
├── infra/
│   └── docker-compose.yml
├── scripts/          # One-off helpers (e.g. generate sample CSV)
├── .env.example
├── .gitignore
├── Makefile          # make ingest, make up, make down
└── README.md
```

## Prerequisites

- **Windows:** Docker Desktop with WSL2 or Hyper-V backend.
- **Docker & Compose:** Required.

Check from a terminal (PowerShell or Git Bash):

```powershell
docker --version
docker compose version
```

You should see version output for both. If `docker compose` is missing, use `docker-compose` (with hyphen) and substitute that in the commands below.

## Setup

1. **Clone or open the repo** and go to the repo root:

   ```powershell
   cd "c:\Users\Achintya Singh\Documents\Traffic-lyt"
   ```

2. **Create env file** from the example:

   ```powershell
   copy .env.example .env
   ```

   Edit `.env` if you want different DB credentials or API URL. Defaults work for local Docker.

## Run (one command)

From the **repo root**:

```powershell
docker compose -f infra/docker-compose.yml up --build
```

- First run will build the API and web images and pull PostGIS; later runs are faster.
- When you see the API and web logs and no errors, the stack is up.

**Endpoints:**

| Service | URL |
|--------|-----|
| Web | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| DB (host) | localhost:5432 |

The web app calls the API from the **browser** using `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`). Container-to-container: the API uses hostname `db` for PostgreSQL; the web does not call the API from inside the container.

## Sanity checks (curl)

With the stack running, from another terminal:

```powershell
curl http://localhost:8000/health
# Expect: {"status":"ok"}

curl http://localhost:8000/db-check
# Expect: {"db":"ok"}
```

Then open http://localhost:3000 — you should see "Traffic-lyt Phase 0 ✅" and the same health/db-check payloads on the page.

---

## Phase 1: Data and map

### 1. Start the stack

From the **repo root**:

```powershell
docker compose -f infra/docker-compose.yml up --build
```

Wait until all services are healthy (db, then api, then web).

### 2. Ingest sample data

With the stack running, in another terminal from the repo root:

**Option A — Make (if you have `make`):**

```powershell
make ingest
```

**Option B — Docker Compose directly (Windows/PowerShell):**

```powershell
docker compose -f infra/docker-compose.yml exec api python -m app.scripts.ingest_nyc
```

You should see log lines like: `Valid rows: 2500`, `Inserted batch: 500 rows`, `Ingest complete: 2500 rows`. Sample data lives in `data/nyc_violations_sample.csv` and is mounted into the API container at `/data`.

### 3. Open the map

- In the browser go to **http://localhost:3000/map**, or use the “View violations map →” link on the home page.
- The map loads violations from `GET /violations?limit=500` and shows markers in NYC. Pan and zoom to explore.

### Phase 1 API

- **GET /violations?limit=500** — Returns violation points (id, lat, lon, occurred_at, violation_type). Default limit 500, max 5000.

No extra environment variables or API keys are required for Phase 1.

---

## Phase 2.0: Stats endpoint and tests

### GET /violations/stats

Returns aggregate stats for violations, with optional filters (date range, hour, violation type).

**Response:** `{ "total": int, "min_time": datetime|null, "max_time": datetime|null, "top_types": [ {"violation_type": str, "count": int}, ... ] }`

**Query params (all optional):** `start`, `end` (ISO datetime), `hour_start`, `hour_end` (0–23), `violation_type` (exact string).

**Example curl (stack running):**

```powershell
curl "http://localhost:8000/violations/stats"
curl "http://localhost:8000/violations/stats?violation_type=No%20Parking"
curl "http://localhost:8000/violations/stats?hour_start=22&hour_end=2"
```

### Run API tests

Assumes the stack is up and sample data has been ingested (Phase 1). From **repo root**:

```powershell
docker compose -f infra/docker-compose.yml exec api pytest tests/test_stats.py -v
```

To run from a local shell (with `DATABASE_URL` set to your running Postgres, e.g. in `.env`):

```powershell
cd apps\api
pip install -r requirements.txt
pytest tests/test_stats.py -v
```

### Manual verification

```powershell
curl -s "http://localhost:8000/violations/stats" | ConvertFrom-Json
curl -s "http://localhost:8000/violations/stats?hour_start=-1"
# Expect 422 for invalid hour
```

---

## Troubleshooting

### Ports already in use (3000, 8000, 5432)

- **Error like:** "port is already allocated" or "bind: address already in use".

**Fix:**

1. Stop the stack (see below).
2. Find what is using the port (e.g. 8000):

   ```powershell
   netstat -ano | findstr :8000
   ```

3. Either stop that process or change the port in `infra/docker-compose.yml` (e.g. `"8001:8000"` for the API and set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001` in `.env` for the web).

### API or web exits immediately

- Check logs: `docker compose -f infra/docker-compose.yml logs api` (or `web` / `db`).
- **API:** Ensure `DATABASE_URL` is set in the compose file (it is by default from env). If the DB is not ready, the API may fail; it waits for the db healthcheck.
- **Web:** Ensure build completed; check `docker compose -f infra/docker-compose.yml logs web` for Node errors.

### DB connection errors in /db-check

- Confirm the `db` service is healthy: `docker compose -f infra/docker-compose.yml ps`. All should show "healthy" after a minute.
- Ensure `.env` has the same `POSTGRES_*` values as in `infra/docker-compose.yml` (compose builds `DATABASE_URL` from those).

### Docker Desktop not running

- Start Docker Desktop and wait until it’s fully up, then run the compose command again.

## Stop and remove volumes

**Stop only (data kept):**

```powershell
docker compose -f infra/docker-compose.yml down
```

**Stop and remove DB volume (fresh DB next time):**

```powershell
docker compose -f infra/docker-compose.yml down -v
```

Then start again with `docker compose -f infra/docker-compose.yml up --build`.

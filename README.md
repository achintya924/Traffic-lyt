# Traffic-lyt

NYC-first traffic/parking violations analytics. Phase 0: repo scaffolding + local infra.

## Repo structure

```
traffic-lyt/
├── apps/
│   ├── api/          # FastAPI
│   └── web/          # Next.js + TypeScript
├── infra/
│   └── docker-compose.yml
├── .env.example
├── .gitignore
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

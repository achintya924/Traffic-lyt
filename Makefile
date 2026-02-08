# Traffic-lyt — run from repo root

.PHONY: up build down ingest

up:
	docker compose -f infra/docker-compose.yml up -d

build:
	docker compose -f infra/docker-compose.yml up --build -d

down:
	docker compose -f infra/docker-compose.yml down

ingest:
	docker compose -f infra/docker-compose.yml exec api python -m app.scripts.ingest_nyc

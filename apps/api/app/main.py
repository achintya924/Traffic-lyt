import os
from contextlib import contextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

app = FastAPI(title="Traffic-lyt API")

_cors_origins_raw = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_db_engine: Engine | None = None


def get_engine() -> Engine | None:
    global _db_engine
    if _db_engine is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            return None
        _db_engine = create_engine(url, pool_pre_ping=True)
    return _db_engine


@contextmanager
def get_connection():
    engine = get_engine()
    if engine is None:
        yield None
        return
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-check")
def db_check():
    engine = get_engine()
    if engine is None:
        return {"db": "error", "message": "DATABASE_URL not set"}
    try:
        with get_connection() as conn:
            if conn is None:
                return {"db": "error", "message": "DATABASE_URL not set"}
            conn.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as e:
        return {"db": "error", "message": str(e)}


@app.get("/violations")
def violations(
    limit: int = Query(default=500, ge=1, le=5000),
):
    """Return violation points for map display. Ordered by id desc."""
    engine = get_engine()
    if engine is None:
        return {"error": "DATABASE_URL not set", "violations": []}
    try:
        with get_connection() as conn:
            if conn is None:
                return {"error": "No connection", "violations": []}
            # Return id, lat, lon, occurred_at, violation_type from geom
            result = conn.execute(
                text("""
                    SELECT id,
                           ST_Y(geom::geometry) AS lat,
                           ST_X(geom::geometry) AS lon,
                           occurred_at,
                           violation_type
                    FROM violations
                    ORDER BY id DESC
                    LIMIT :lim
                """),
                {"lim": limit},
            )
            rows = result.fetchall()
            out = [
                {
                    "id": r[0],
                    "lat": round(float(r[1]), 6),
                    "lon": round(float(r[2]), 6),
                    "occurred_at": r[3].isoformat() if r[3] else None,
                    "violation_type": r[4],
                }
                for r in rows
            ]
            return {"violations": out}
    except Exception as e:
        return {"error": str(e), "violations": []}

import os
from contextlib import contextmanager

from fastapi import FastAPI
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

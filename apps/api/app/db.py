"""Database engine and connection helper. Shared by main and routers to avoid circular imports."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

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

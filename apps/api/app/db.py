"""Database engine and connection helper. Shared by main and routers to avoid circular imports."""
import logging
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_db_engine: Engine | None = None


def get_engine() -> Engine | None:
    global _db_engine
    if _db_engine is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            logger.error(
                "DATABASE_URL environment variable is not set. "
                "All database operations will fail. "
                "Set DATABASE_URL to a valid PostgreSQL connection string "
                "(e.g. postgresql://user:pass@host:5432/dbname)."
            )
            return None
        _db_engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
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

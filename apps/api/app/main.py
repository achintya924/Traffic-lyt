import os
import time

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db import get_connection, get_engine
from app.routers import predict, spatial_aggregations, stats, time_aggregations, zones, zones_analytics, zones_rankings
from app.utils.model_registry import get_registry
from app.utils.rate_limiter import get_limiter
from app.utils.response_cache import get_response_cache
from app.utils.timing_middleware import TimingMiddleware

from app.middleware.request_id import RequestIdMiddleware

_start_time = time.monotonic()

app = FastAPI(title="Traffic-lyt API")
app.include_router(stats.router)
app.include_router(time_aggregations.router)
app.include_router(spatial_aggregations.router)
app.include_router(predict.router)
app.include_router(zones_rankings.router)
app.include_router(zones.router)
app.include_router(zones_analytics.router)

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
app.add_middleware(TimingMiddleware)  # Phase 4.5+4.6: timing + structured logging
app.add_middleware(RequestIdMiddleware)  # Phase 4.6: X-Request-ID (outermost, runs first)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/internal/cache")
def internal_cache():
    """Phase 4.2 + 4.3: Model registry and response cache stats. Guarded by DEBUG=true."""
    if os.getenv("DEBUG", "").lower() not in ("1", "true", "yes"):
        return {"error": "disabled", "message": "Set DEBUG=true to enable"}
    return {
        "model_registry": get_registry().stats(),
        "response_cache": get_response_cache().stats(),
    }


@app.get("/internal/metrics")
def internal_metrics():
    """Phase 4.6: Lightweight metrics. Guarded by DEBUG=true."""
    if os.getenv("DEBUG", "").lower() not in ("1", "true", "yes"):
        return {"error": "disabled", "message": "Set DEBUG=true to enable"}
    return {
        "uptime_seconds": round(time.monotonic() - _start_time, 2),
        "model_registry": get_registry().stats(),
        "response_cache": get_response_cache().stats(),
        "rate_limiter": get_limiter().stats(),
    }


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

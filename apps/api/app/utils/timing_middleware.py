"""
Phase 4.5: Request timing middleware.
Logs method, path, status, elapsed_ms. Logs WARNING for slow requests.
Override via SLOW_THRESHOLD_MS env (default 300).
"""
import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

SLOW_THRESHOLD_MS = int(os.getenv("SLOW_THRESHOLD_MS", "300"))
logger = logging.getLogger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """Log request timing; WARNING for requests above SLOW_THRESHOLD_MS."""

    def __init__(self, app, slow_threshold_ms: int = SLOW_THRESHOLD_MS):
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        method = request.method
        path = request.url.path
        status = response.status_code
        log_msg = f"request method={method} path={path} status={status} elapsed_ms={elapsed_ms}"
        if elapsed_ms >= self.slow_threshold_ms:
            logger.warning("slow_request %s", log_msg)
        else:
            logger.info("request_timing %s", log_msg)
        return response

"""
Phase 4.5 + 4.6: Request timing and structured completion logging.
Requires RequestIdMiddleware (outermost) to set request.state.request_id.
"""
import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.observability import log_event

SLOW_THRESHOLD_MS = int(os.getenv("SLOW_THRESHOLD_MS", "300"))
logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class TimingMiddleware(BaseHTTPMiddleware):
    """Log request completion as structured JSON; WARNING for slow requests."""

    def __init__(self, app, slow_threshold_ms: int = SLOW_THRESHOLD_MS):
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - t0) * 1000)
            request_id = getattr(request.state, "request_id", None)
            log_event(
                logger,
                "request_error",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=500,
                elapsed_ms=elapsed_ms,
                client_ip=_client_ip(request),
                error_type=type(e).__name__,
            )
            raise
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        request_id = getattr(request.state, "request_id", None)
        state = getattr(request, "state", None) or object()
        fields = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "client_ip": _client_ip(request),
            "response_cache_hit": getattr(state, "response_cache_hit", None),
            "model_cache_hit": getattr(state, "model_cache_hit", None),
            "rate_limited": getattr(state, "rate_limited", None),
            "retry_after_seconds": getattr(state, "retry_after_seconds", None),
        }
        if elapsed_ms >= self.slow_threshold_ms:
            fields["slow"] = True
        log_event(logger, "request_complete", **fields)
        return response

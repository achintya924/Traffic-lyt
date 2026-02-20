"""
Phase 4.6: Request ID middleware.
Uses X-Request-ID if present; else generates uuid4 hex. Stores on request.state and echoes in response.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _get_or_create_request_id(request: Request) -> str:
    existing = request.headers.get("X-Request-ID")
    if existing and existing.strip():
        return existing.strip()
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _get_or_create_request_id(request)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

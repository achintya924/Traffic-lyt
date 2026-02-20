"""
Phase 4.4: In-memory rate limiting (fixed-window counter).
Thread-safe; no external deps.
"""
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

# Limits: requests per minute per (client, group)
DEFAULT_LIMITS: dict[str, int] = {
    "predict": 30,
    "stats": 60,
    "other": 60,
}


@dataclass
class WindowEntry:
    count: int
    window_start: float


class RateLimiter:
    """Fixed-window counter. Key: (client_id, group). Purges stale entries periodically."""

    def __init__(self, limits: dict[str, int] | None = None):
        self._limits = limits or DEFAULT_LIMITS.copy()
        self._store: dict[tuple[str, str], WindowEntry] = {}
        self._lock = threading.Lock()
        self._window_seconds = 60.0
        self._purge_after_seconds = 120.0
        self._last_purge = time.monotonic()
        self._allowed: dict[str, int] = {}
        self._blocked: dict[str, int] = {}

    def _purge_if_needed(self) -> None:
        now = time.monotonic()
        if now - self._last_purge < self._purge_after_seconds:
            return
        self._last_purge = now
        stale = [
            k
            for k, v in self._store.items()
            if now - v.window_start > self._purge_after_seconds
        ]
        for k in stale:
            del self._store[k]

    def check(self, client_id: str, group: str) -> tuple[bool, int]:
        """
        Check if request is allowed. Returns (allowed, retry_after_seconds).
        retry_seconds is 0 if allowed; else seconds until window resets.
        """
        limit = self._limits.get(group, self._limits.get("other", 60))
        if limit <= 0:
            return True, 0
        key = (client_id, group)
        now = time.monotonic()
        with self._lock:
            self._purge_if_needed()
            entry = self._store.get(key)
            if entry is None:
                self._store[key] = WindowEntry(count=1, window_start=now)
                self._allowed[group] = self._allowed.get(group, 0) + 1
                return True, 0
            elapsed = now - entry.window_start
            if elapsed >= self._window_seconds:
                entry.count = 1
                entry.window_start = now
                self._allowed[group] = self._allowed.get(group, 0) + 1
                return True, 0
            entry.count += 1
            if entry.count <= limit:
                self._allowed[group] = self._allowed.get(group, 0) + 1
                return True, 0
            self._blocked[group] = self._blocked.get(group, 0) + 1
            retry_after = max(1, int(self._window_seconds - elapsed))
            return False, retry_after

    def stats(self) -> dict[str, Any]:
        """Return allowed/blocked counts per group (Phase 4.6)."""
        with self._lock:
            return {
                "allowed": dict(self._allowed),
                "blocked": dict(self._blocked),
            }


_limiter: RateLimiter | None = None
_limiter_lock = threading.Lock()


def get_limiter() -> RateLimiter:
    global _limiter
    with _limiter_lock:
        if _limiter is None:
            limits = DEFAULT_LIMITS.copy()
            if os.getenv("RATE_LIMIT_PREDICT"):
                try:
                    limits["predict"] = int(os.getenv("RATE_LIMIT_PREDICT", "30"))
                except ValueError:
                    pass
            if os.getenv("RATE_LIMIT_STATS"):
                try:
                    limits["stats"] = int(os.getenv("RATE_LIMIT_STATS", "60"))
                except ValueError:
                    pass
            _limiter = RateLimiter(limits=limits)
        return _limiter


def _client_id(request: Request) -> str:
    use_xff = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    if use_xff:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(group: str):
    """FastAPI dependency. Raises HTTP 429 if rate limit exceeded. Skip when RATE_LIMIT_DISABLED=true."""

    def _dependency(request: Request):
        if os.getenv("RATE_LIMIT_DISABLED", "").lower() in ("1", "true", "yes"):
            return None
        limiter = get_limiter()
        client_id = _client_id(request)
        allowed, retry_after = limiter.check(client_id, group)
        if allowed:
            return None
        request.state.rate_limited = True
        request.state.retry_after_seconds = retry_after
        raise HTTPException(
            status_code=429,
            detail={
                "detail": "Rate limit exceeded",
                "group": group,
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    return _dependency

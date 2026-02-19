"""
Phase 4.3: In-memory response-level cache (LRU + TTL) for heavy endpoints.
JSON-serializable payloads only; thread-safe; no external deps.
"""
import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.utils.model_registry import short_hash


# Bump to invalidate all response cache entries.
RESPONSE_CACHE_VERSION = "v1"


@dataclass
class ResponseCacheEntry:
    value: Any
    created_at: float
    last_access: float
    ttl_seconds: float


class ResponseCache:
    """
    In-memory cache for JSON-serializable response payloads.
    LRU + TTL eviction; thread-safe.
    """

    def __init__(self, max_items: int = 256):
        self._max_items = max_items
        self._store: dict[str, ResponseCacheEntry] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Any | None:
        """Return cached value if present and not expired; update last_access. Else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            now = time.monotonic()
            if entry.ttl_seconds > 0 and (now - entry.created_at) > entry.ttl_seconds:
                del self._store[key]
                self._evictions += 1
                self._misses += 1
                return None
            entry.last_access = now
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        """Store value with TTL. Evicts LRU if over max_items."""
        now = time.monotonic()
        entry = ResponseCacheEntry(
            value=value,
            created_at=now,
            last_access=now,
            ttl_seconds=ttl_seconds,
        )
        with self._lock:
            self._evict_if_needed(key)
            self._store[key] = entry

    def _evict_if_needed(self, exclude_key: str | None = None) -> None:
        now = time.monotonic()
        to_remove = [
            k
            for k, e in self._store.items()
            if k != exclude_key and e.ttl_seconds > 0 and (now - e.created_at) > e.ttl_seconds
        ]
        for k in to_remove:
            del self._store[k]
            self._evictions += 1
        while len(self._store) >= self._max_items and exclude_key is not None:
            lru_key = min(
                (k for k in self._store if k != exclude_key),
                key=lambda k: self._store[k].last_access,
                default=None,
            )
            if lru_key is None:
                break
            del self._store[lru_key]
            self._evictions += 1

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "keys_count": len(self._store),
            }

    def cleanup_expired(self) -> int:
        now = time.monotonic()
        with self._lock:
            to_remove = [
                k
                for k, e in self._store.items()
                if e.ttl_seconds > 0 and (now - e.created_at) > e.ttl_seconds
            ]
            for k in to_remove:
                del self._store[k]
                self._evictions += 1
            return len(to_remove)

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in to_remove:
                del self._store[k]
            return len(to_remove)


_response_cache: ResponseCache | None = None
_response_cache_lock = threading.Lock()


def get_response_cache(max_items: int = 256) -> ResponseCache:
    global _response_cache
    with _response_cache_lock:
        if _response_cache is None:
            _response_cache = ResponseCache(max_items=max_items)
        return _response_cache


def make_response_key(
    endpoint_name: str,
    request_signature: str,
    anchor_ts: str | None,
    effective_window: dict[str, Any] | None,
    response_version: str = RESPONSE_CACHE_VERSION,
) -> str:
    """
    Deterministic cache key for response cache.
    effective_window should have start_ts, end_ts (or nulls).
    """
    start_ts = (effective_window or {}).get("start_ts") or ""
    end_ts = (effective_window or {}).get("end_ts") or ""
    raw = "|".join([
        f"resp:{endpoint_name}",
        request_signature,
        str(anchor_ts or ""),
        str(start_ts),
        str(end_ts),
        response_version,
    ])
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"resp:{endpoint_name}:{h}"

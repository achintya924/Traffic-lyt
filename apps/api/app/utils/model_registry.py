"""
Phase 4.2: In-process model cache (model registry).
LRU-ish eviction + TTL, thread-safe, no external deps.
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    created_at: float
    last_access: float
    ttl_seconds: float
    meta: dict[str, Any] = field(default_factory=dict)
    size_estimate: int = 0


def _default_size_estimate(_key: str, _value: Any) -> int:
    """Rough size for eviction ordering; override if needed."""
    return 1


class ModelRegistry:
    """
    In-memory cache keyed by string. Thread-safe.
    Eviction: max_items (LRU by last_access) + TTL (expired entries removed on get/set/cleanup).
    """

    def __init__(
        self,
        max_items: int = 256,
        size_estimator: Callable[[str, Any], int] | None = None,
    ):
        self._max_items = max_items
        self._size_estimator = size_estimator or _default_size_estimate
        self._store: dict[str, CacheEntry] = {}
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

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Store value with TTL. Evicts oldest (by last_access) if over max_items or expired."""
        now = time.monotonic()
        size_est = self._size_estimator(key, value)
        entry = CacheEntry(
            value=value,
            created_at=now,
            last_access=now,
            ttl_seconds=ttl_seconds,
            meta=meta or {},
            size_estimate=size_est,
        )
        with self._lock:
            self._evict_if_needed(key)
            self._store[key] = entry

    def _evict_if_needed(self, exclude_key: str | None = None) -> None:
        """Remove expired entries, then by LRU until len <= max_items."""
        now = time.monotonic()
        to_remove: list[str] = []
        for k, e in self._store.items():
            if k == exclude_key:
                continue
            if e.ttl_seconds > 0 and (now - e.created_at) > e.ttl_seconds:
                to_remove.append(k)
        for k in to_remove:
            del self._store[k]
            self._evictions += 1
        while len(self._store) >= self._max_items and exclude_key is not None:
            # Evict LRU
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
        """Return hits, misses, evictions, size, keys_count."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "keys_count": len(self._store),
                "size": sum(e.size_estimate for e in self._store.values()),
            }

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys starting with prefix. Returns count removed."""
        with self._lock:
            to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in to_remove:
                del self._store[k]
            return len(to_remove)

    def invalidate(self, predicate: Callable[[str], bool]) -> int:
        """Remove keys for which predicate(key) is True. Returns count removed."""
        with self._lock:
            to_remove = [k for k in self._store if predicate(k)]
            for k in to_remove:
                del self._store[k]
            return len(to_remove)

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
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


# Singleton used by predict endpoints
_registry: ModelRegistry | None = None
_registry_lock = threading.Lock()


def get_registry(max_items: int = 256) -> ModelRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ModelRegistry(max_items=max_items)
        return _registry


def make_model_key(
    endpoint_name: str,
    filters_signature: str,
    anchor_ts: str | None,
    granularity: str,
    model_params: dict[str, Any] | None = None,
    feature_version: str = "v1",
) -> str:
    """
    Produce a stable cache key with prefix for invalidate_prefix.
    filters_signature should come from request_signature() or equivalent.
    """
    parts = [
        endpoint_name,
        filters_signature,
        str(anchor_ts or ""),
        granularity,
        feature_version,
    ]
    if model_params:
        for k in sorted(model_params.keys()):
            parts.append(f"{k}={model_params[k]}")
    raw = "|".join(parts)
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{endpoint_name}:{h}"


def short_hash(key: str) -> str:
    """Short hash for logging/response meta (first 12 chars)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

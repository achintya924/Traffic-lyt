"""
Phase 4.3: Response-level cache (LRU + TTL).
Assumes DB running for cache-miss paths. Run:
  pytest apps/api/tests/test_response_cache.py -v
  or: docker compose -f infra/docker-compose.yml exec api pytest tests/test_response_cache.py -v
"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils.response_cache import ResponseCache, make_response_key, short_hash

client = TestClient(app)


def test_response_cache_meta_shape():
    """GET /violations/stats and /predict/risk include meta.response_cache with hit, key_hash, ttl_seconds."""
    r = client.get("/violations/stats")
    assert r.status_code == 200
    data = r.json()
    assert "meta" in data
    assert "response_cache" in data["meta"]
    rc = data["meta"]["response_cache"]
    assert "hit" in rc
    assert "key_hash" in rc
    assert "ttl_seconds" in rc


def test_stats_same_params_second_hit():
    """Same params to /violations/stats twice => second response has response_cache.hit true (if DB has data)."""
    r1 = client.get("/violations/stats")
    assert r1.status_code == 200
    if r1.json().get("meta", {}).get("response_cache", {}).get("key_hash") is None:
        pytest.skip("No DB: key_hash not set")
    r2 = client.get("/violations/stats")
    assert r2.status_code == 200
    assert r2.json().get("meta", {}).get("response_cache", {}).get("hit") is True


def test_risk_same_params_second_hit():
    """Same params to /predict/risk twice => second has response_cache.hit true (short-circuits model + DB)."""
    params = {"granularity": "hour", "horizon": 24, "bbox": "-74.1,40.6,-73.9,40.8"}
    r1 = client.get("/predict/risk", params=params)
    assert r1.status_code == 200
    if r1.json().get("meta", {}).get("response_cache", {}).get("key_hash") is None:
        pytest.skip("No DB: key_hash not set")
    r2 = client.get("/predict/risk", params=params)
    assert r2.status_code == 200
    assert r2.json().get("meta", {}).get("response_cache", {}).get("hit") is True


def test_different_bbox_miss():
    """Different bbox => different response key => cache miss."""
    r1 = client.get("/violations/stats", params={"bbox": "-74.1,40.6,-73.9,40.8"})
    r2 = client.get("/violations/stats", params={"bbox": "-74.2,40.5,-73.8,40.9"})
    assert r1.status_code == 200 and r2.status_code == 200
    h1 = r1.json().get("meta", {}).get("response_cache", {}).get("key_hash")
    h2 = r2.json().get("meta", {}).get("response_cache", {}).get("key_hash")
    if h1 is None and h2 is None:
        pytest.skip("No DB")
    assert h1 != h2


def test_different_start_end_miss():
    """Different start/end => different key => miss."""
    r1 = client.get("/violations/stats")
    assert r1.status_code == 200
    r2 = client.get(
        "/violations/stats",
        params={"start": "2024-01-01T00:00:00", "end": "2024-01-31T23:59:59"},
    )
    assert r2.status_code == 200
    h1 = r1.json().get("meta", {}).get("response_cache", {}).get("key_hash")
    h2 = r2.json().get("meta", {}).get("response_cache", {}).get("key_hash")
    if h1 is None and h2 is None:
        pytest.skip("No DB")
    assert h1 != h2


def test_make_response_key_deterministic():
    """make_response_key is deterministic; different inputs => different key."""
    sig = "ep=stats|anchor=2024-01-15T12:00:00Z|bbox=-74,40.7,-73.9,40.8"
    key1 = make_response_key("stats", sig, "2024-01-15T12:00:00Z", {"start_ts": "2024-01-01Z", "end_ts": "2024-01-15Z"})
    key2 = make_response_key("stats", sig, "2024-01-15T12:00:00Z", {"start_ts": "2024-01-01Z", "end_ts": "2024-01-15Z"})
    assert key1 == key2
    assert key1.startswith("resp:stats:")
    key3 = make_response_key("stats", sig, "2024-01-15T13:00:00Z", {"start_ts": "2024-01-01Z", "end_ts": "2024-01-15Z"})
    assert key3 != key1


def test_response_cache_ttl_expiry():
    """TTL expiry: entry not returned after ttl (patch or 1s TTL + sleep)."""
    cache = ResponseCache(max_items=10)
    cache.set("k1", {"x": 1}, ttl_seconds=0.1)
    assert cache.get("k1") is not None
    time.sleep(0.15)
    assert cache.get("k1") is None


def test_forecast_has_response_cache():
    """GET /predict/forecast includes meta.response_cache."""
    r = client.get("/predict/forecast", params={"granularity": "hour", "horizon": 24})
    assert r.status_code == 200
    assert "response_cache" in r.json().get("meta", {})


def test_hotspots_has_response_cache():
    """GET /predict/hotspots/grid includes meta.response_cache."""
    r = client.get("/predict/hotspots/grid", params={"bbox": "-74.1,40.6,-73.9,40.8"})
    assert r.status_code == 200
    assert "response_cache" in r.json().get("meta", {})

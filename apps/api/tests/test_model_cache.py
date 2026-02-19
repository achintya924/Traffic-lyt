"""
Phase 4.2: Model cache (registry) behavior.
Assumes DB is running with ingested data. Run:
  pytest apps/api/tests/test_model_cache.py -v
  or: docker compose -f infra/docker-compose.yml exec api pytest tests/test_model_cache.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils.model_registry import make_model_key, short_hash
from app.utils.signature import request_signature

client = TestClient(app)


def test_model_key_deterministic():
    """Same inputs produce same key; different inputs produce different key."""
    sig = request_signature(
        endpoint_name="risk",
        anchor_ts="2024-01-15T12:00:00Z",
        granularity="hour",
        bbox="-74.0,40.7,-73.9,40.8",
        model_params={"alpha": 0.1, "horizon": 24},
    )
    key1 = make_model_key("risk", sig, "2024-01-15T12:00:00Z", "hour", model_params={"alpha": 0.1, "horizon": 24})
    key2 = make_model_key("risk", sig, "2024-01-15T12:00:00Z", "hour", model_params={"alpha": 0.1, "horizon": 24})
    assert key1 == key2
    assert key1.startswith("risk:")
    key3 = make_model_key("risk", sig, "2024-01-15T13:00:00Z", "hour", model_params={"alpha": 0.1, "horizon": 24})
    assert key3 != key1
    key4 = make_model_key("risk", sig, "2024-01-15T12:00:00Z", "day", model_params={"alpha": 0.1, "horizon": 24})
    assert key4 != key1


def test_short_hash_stable():
    """short_hash is deterministic and 12 chars."""
    h = short_hash("risk:abc123")
    assert len(h) == 12
    assert short_hash("risk:abc123") == h


def test_risk_meta_has_model_cache():
    """GET /predict/risk response meta includes model_cache with hit, key_hash, ttl_seconds."""
    response = client.get("/predict/risk", params={"granularity": "hour", "horizon": 24})
    assert response.status_code == 200
    data = response.json()
    assert "meta" in data
    assert "model_cache" in data["meta"]
    mc = data["meta"]["model_cache"]
    assert "hit" in mc
    assert isinstance(mc["hit"], bool)
    assert "key_hash" in mc
    assert "ttl_seconds" in mc
    assert isinstance(mc["ttl_seconds"], (int, float))


def test_risk_second_request_cache_hit():
    """Two identical /predict/risk requests: second response has cache hit (Phase 4.3: response_cache, else model_cache)."""
    params = {"granularity": "hour", "horizon": 24, "bbox": "-74.1,40.6,-73.9,40.8"}
    r1 = client.get("/predict/risk", params=params)
    assert r1.status_code == 200
    meta1 = r1.json().get("meta", {})
    if meta1.get("model_cache", {}).get("key_hash") is None:
        pytest.skip("No DB or no data: key_hash is None")
    r2 = client.get("/predict/risk", params=params)
    assert r2.status_code == 200
    meta2 = r2.json().get("meta", {})
    assert meta1.get("model_cache", {}).get("key_hash") == meta2.get("model_cache", {}).get("key_hash")
    # Phase 4.3: response cache short-circuits first, so second request has response_cache.hit
    assert meta2.get("response_cache", {}).get("hit") is True or meta2.get("model_cache", {}).get("hit") is True


def test_risk_different_bbox_cache_miss():
    """Different bbox yields different key -> cache miss on second (different) request."""
    r1 = client.get("/predict/risk", params={"granularity": "hour", "horizon": 24, "bbox": "-74.1,40.6,-73.9,40.8"})
    assert r1.status_code == 200
    r2 = client.get("/predict/risk", params={"granularity": "hour", "horizon": 24, "bbox": "-74.2,40.5,-73.8,40.9"})
    assert r2.status_code == 200
    hash1 = r1.json().get("meta", {}).get("model_cache", {}).get("key_hash")
    hash2 = r2.json().get("meta", {}).get("model_cache", {}).get("key_hash")
    if hash1 is None and hash2 is None:
        pytest.skip("No DB or no data: key_hash not set")
    assert hash1 != hash2


def test_risk_different_anchor_or_window_cache_miss():
    """Different start/end (effective window) yields different key -> different key_hash."""
    r1 = client.get("/predict/risk", params={"granularity": "day", "horizon": 7})
    assert r1.status_code == 200
    r2 = client.get(
        "/predict/risk",
        params={
            "granularity": "day",
            "horizon": 7,
            "start": "2024-01-01T00:00:00",
            "end": "2024-01-31T23:59:59",
        },
    )
    assert r2.status_code == 200
    hash1 = r1.json().get("meta", {}).get("model_cache", {}).get("key_hash")
    hash2 = r2.json().get("meta", {}).get("model_cache", {}).get("key_hash")
    if hash1 is None and hash2 is None:
        pytest.skip("No DB or no data: key_hash not set")
    assert hash1 != hash2


def test_forecast_meta_has_model_cache():
    """GET /predict/forecast response meta includes model_cache."""
    response = client.get("/predict/forecast", params={"granularity": "hour", "horizon": 24})
    assert response.status_code == 200
    data = response.json()
    assert "meta" in data and "model_cache" in data["meta"]
    mc = data["meta"]["model_cache"]
    assert "hit" in mc and "key_hash" in mc and "ttl_seconds" in mc


def test_forecast_second_request_cache_hit():
    """Two identical /predict/forecast requests: second has cache hit (Phase 4.3: response_cache, else model_cache)."""
    params = {"granularity": "hour", "horizon": 24, "bbox": "-74.1,40.6,-73.9,40.8"}
    r1 = client.get("/predict/forecast", params=params)
    assert r1.status_code == 200
    if r1.json().get("meta", {}).get("model_cache", {}).get("key_hash") is None:
        pytest.skip("No DB or no data: key_hash is None")
    r2 = client.get("/predict/forecast", params=params)
    assert r2.status_code == 200
    meta2 = r2.json().get("meta", {})
    assert meta2.get("response_cache", {}).get("hit") is True or meta2.get("model_cache", {}).get("hit") is True

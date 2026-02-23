"""
Phase 5.6: Early Warning Indicators tests.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_warnings_returns_200_for_zones():
    """GET /api/warnings?scope=zones returns 200."""
    r = client.get("/api/warnings", params={"scope": "zones"})
    assert r.status_code == 200
    data = r.json()
    assert "warnings" in data
    assert "meta" in data
    assert isinstance(data["warnings"], list)
    assert "response_cache" in data["meta"]
    assert "anchor_ts" in data["meta"] or data["warnings"]  # anchor_ts when data exists


def test_warnings_invalid_scope_returns_422():
    """GET /api/warnings?scope=invalid returns 422."""
    r = client.get("/api/warnings", params={"scope": "invalid"})
    assert r.status_code == 422


def test_warnings_viewport_returns_422():
    """GET /api/warnings?scope=viewport returns 422 (not implemented)."""
    r = client.get("/api/warnings", params={"scope": "viewport"})
    assert r.status_code == 422


def test_warnings_respects_limit():
    """GET /api/warnings?scope=zones&limit=3 returns at most 3 warnings."""
    r = client.get("/api/warnings", params={"scope": "zones", "limit": 3})
    assert r.status_code == 200
    assert len(r.json()["warnings"]) <= 3


def test_warnings_response_cache_miss_then_hit():
    """First request has response_cache 'miss', second identical request has 'hit'."""
    params = {"scope": "zones", "limit": 5}
    r1 = client.get("/api/warnings", params=params)
    assert r1.status_code == 200
    assert r1.json()["meta"]["response_cache"] == "miss"
    r2 = client.get("/api/warnings", params=params)
    assert r2.status_code == 200
    assert r2.json()["meta"]["response_cache"] == "hit"


def test_warnings_empty_list_when_no_data():
    """When no zones or no violations, warnings is empty list (stable behavior)."""
    r = client.get("/api/warnings", params={"scope": "zones"})
    assert r.status_code == 200
    data = r.json()
    assert data["warnings"] == [] or all(
        "warning_type" in w and "severity" in w and "zone" in w and "headline" in w
        for w in data["warnings"]
    )

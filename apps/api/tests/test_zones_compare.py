"""
Phase 5.4: Zone WoW/MoM compare tests.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[-74.02, 40.70], [-73.95, 40.70], [-73.95, 40.80], [-74.02, 40.80], [-74.02, 40.70]]
    ],
}


@pytest.fixture(scope="module")
def ensure_zones_table():
    """Ensure zones table exists."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "app.scripts.init_zones"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"init_zones failed: {result.stderr}")
    yield


@pytest.fixture
def sample_zone(ensure_zones_table):
    """Create a sample zone for compare tests."""
    payload = {
        "name": f"Compare Zone {uuid.uuid4().hex[:8]}",
        "zone_type": "custom",
        "polygon": VALID_POLYGON,
    }
    r = client.post("/api/zones", json=payload)
    if r.status_code not in (200, 201):
        pytest.skip("Could not create zone")
    return r.json()


def test_compare_valid_zone_returns_200(ensure_zones_table, sample_zone):
    """GET /api/zones/{zone_id}/compare?period=wow returns 200."""
    zone_id = sample_zone["id"]
    r = client.get(f"/api/zones/{zone_id}/compare", params={"period": "wow"})
    assert r.status_code == 200
    data = r.json()
    assert "zone" in data
    assert data["zone"]["id"] == zone_id
    assert "period" in data
    assert data["period"] == "wow"
    assert "current" in data
    assert "previous" in data
    assert "delta" in data
    assert "meta" in data
    assert "window" in data["current"]
    assert "total_count" in data["current"]
    assert "time_series" in data["current"]
    assert "top_violation_types" in data["current"]
    assert "delta_count" in data["delta"]
    assert "delta_percent" in data["delta"]
    assert "trend_label" in data["delta"]
    assert "violation_type_shifts" in data["delta"]


def test_compare_invalid_zone_returns_404(ensure_zones_table):
    """GET /api/zones/{zone_id}/compare returns 404 for non-existent zone."""
    r = client.get("/api/zones/999999999/compare", params={"period": "wow"})
    assert r.status_code == 404


def test_compare_invalid_period_returns_422(ensure_zones_table, sample_zone):
    """GET /api/zones/{zone_id}/compare?period=invalid returns 422."""
    r = client.get(
        f"/api/zones/{sample_zone['id']}/compare",
        params={"period": "invalid"},
    )
    assert r.status_code == 422


def test_compare_response_cache_miss_then_hit(ensure_zones_table, sample_zone):
    """First request has response_cache 'miss', second identical request has 'hit'."""
    zone_id = sample_zone["id"]
    params = {"period": "mom", "granularity": "day"}
    r1 = client.get(f"/api/zones/{zone_id}/compare", params=params)
    assert r1.status_code == 200
    assert r1.json()["meta"]["response_cache"] == "miss"
    r2 = client.get(f"/api/zones/{zone_id}/compare", params=params)
    assert r2.status_code == 200
    assert r2.json()["meta"]["response_cache"] == "hit"


def test_compare_delta_handles_previous_zero_safely(ensure_zones_table):
    """Delta math handles previous_total=0 without crash; delta_percent defined."""
    from app.routers.zones_compare import _delta_percent_safe

    assert _delta_percent_safe(0, 0) == 0.0
    assert _delta_percent_safe(10, 0) == 100.0
    assert _delta_percent_safe(5, 10) == -50.0
    assert _delta_percent_safe(15, 10) == 50.0

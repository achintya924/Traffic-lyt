"""
Phase 5.3: Zone rankings tests.
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
    """Create a sample zone for rankings tests."""
    payload = {
        "name": f"Rankings Zone {uuid.uuid4().hex[:8]}",
        "zone_type": "custom",
        "polygon": VALID_POLYGON,
    }
    r = client.post("/api/zones", json=payload)
    if r.status_code not in (200, 201):
        pytest.skip("Could not create zone")
    return r.json()


def test_rankings_returns_200(ensure_zones_table):
    """GET /api/zones/rankings returns 200."""
    r = client.get("/api/zones/rankings")
    assert r.status_code == 200
    data = r.json()
    assert "rankings" in data
    assert "meta" in data
    assert "request_id" in data["meta"] or "anchor_ts" in data["meta"]
    assert "response_cache" in data["meta"]
    assert isinstance(data["rankings"], list)


def test_rankings_limit_respected(ensure_zones_table, sample_zone):
    """GET /api/zones/rankings?limit=3 returns at most 3 items."""
    r = client.get("/api/zones/rankings", params={"limit": 3})
    assert r.status_code == 200
    rankings = r.json()["rankings"]
    assert len(rankings) <= 3


def test_rankings_sort_by_volume(ensure_zones_table, sample_zone):
    """GET /api/zones/rankings?sort_by=volume sorts by total_count descending."""
    r = client.get("/api/zones/rankings", params={"sort_by": "volume", "limit": 20})
    assert r.status_code == 200
    rankings = r.json()["rankings"]
    if len(rankings) >= 2:
        for i in range(len(rankings) - 1):
            assert rankings[i]["total_count"] >= rankings[i + 1]["total_count"]
    for item in rankings:
        assert "zone_id" in item
        assert "name" in item
        assert "zone_type" in item
        assert "total_count" in item
        assert "trend_direction" in item
        assert "percent_change" in item
        assert "score" in item


def test_rankings_invalid_sort_by_returns_422(ensure_zones_table):
    """GET /api/zones/rankings?sort_by=invalid returns 422."""
    r = client.get("/api/zones/rankings", params={"sort_by": "invalid"})
    assert r.status_code == 422


def test_rankings_response_cache_miss_then_hit(ensure_zones_table):
    """First request has response_cache 'miss', second identical request has 'hit'."""
    params = {"limit": 99}
    r1 = client.get("/api/zones/rankings", params=params)
    assert r1.status_code == 200
    assert r1.json()["meta"]["response_cache"] == "miss"
    r2 = client.get("/api/zones/rankings", params=params)
    assert r2.status_code == 200
    assert r2.json()["meta"]["response_cache"] == "hit"

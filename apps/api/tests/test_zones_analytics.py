"""
Phase 5.2: Zone analytics tests.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.zones_analytics import _compute_trend

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
    """Create a sample zone for analytics tests."""
    payload = {
        "name": f"Analytics Zone {uuid.uuid4().hex[:8]}",
        "zone_type": "custom",
        "polygon": VALID_POLYGON,
    }
    r = client.post("/api/zones", json=payload)
    if r.status_code not in (200, 201):
        pytest.skip("Could not create zone")
    return r.json()


def test_analytics_returns_200_for_valid_zone(ensure_zones_table, sample_zone):
    """GET /api/zones/{zone_id}/analytics returns 200 for valid zone."""
    zone_id = sample_zone["id"]
    r = client.get(f"/api/zones/{zone_id}/analytics")
    assert r.status_code == 200
    data = r.json()
    assert "zone" in data
    assert data["zone"]["id"] == zone_id
    assert "summary" in data
    assert "total_count" in data["summary"]
    assert "trend_direction" in data["summary"]
    assert "percent_change" in data["summary"]
    assert "time_series" in data
    assert "top_violation_types" in data
    assert "meta" in data


def test_analytics_invalid_zone_returns_404(ensure_zones_table):
    """GET /api/zones/{zone_id}/analytics returns 404 for non-existent zone."""
    r = client.get("/api/zones/999999999/analytics")
    assert r.status_code == 404


def test_analytics_response_cache_miss_then_hit(ensure_zones_table, sample_zone):
    """First request has response_cache 'miss', second identical request has 'hit'."""
    zone_id = sample_zone["id"]
    url = f"/api/zones/{zone_id}/analytics"
    r1 = client.get(url)
    assert r1.status_code == 200
    assert r1.json()["meta"]["response_cache"] == "miss"
    r2 = client.get(url)
    assert r2.status_code == 200
    assert r2.json()["meta"]["response_cache"] == "hit"


def test_analytics_invalid_granularity_returns_422(ensure_zones_table, sample_zone):
    """GET /api/zones/{zone_id}/analytics with invalid granularity returns 422."""
    r = client.get(f"/api/zones/{sample_zone['id']}/analytics", params={"granularity": "month"})
    assert r.status_code == 422


def test_trend_computation_up():
    """Trend direction 'up' when short avg > long avg by >5%."""
    ts = [
        {"bucket_ts": "1", "count": 10},
        {"bucket_ts": "2", "count": 10},
        {"bucket_ts": "3", "count": 10},
        {"bucket_ts": "4", "count": 10},
        {"bucket_ts": "5", "count": 10},
        {"bucket_ts": "6", "count": 10},
        {"bucket_ts": "7", "count": 10},
        {"bucket_ts": "8", "count": 10},
        {"bucket_ts": "9", "count": 10},
        {"bucket_ts": "10", "count": 10},
        {"bucket_ts": "11", "count": 10},
        {"bucket_ts": "12", "count": 10},
        {"bucket_ts": "13", "count": 10},
        {"bucket_ts": "14", "count": 10},
        {"bucket_ts": "15", "count": 10},
        {"bucket_ts": "16", "count": 10},
        {"bucket_ts": "17", "count": 10},
        {"bucket_ts": "18", "count": 10},
        {"bucket_ts": "19", "count": 10},
        {"bucket_ts": "20", "count": 10},
        {"bucket_ts": "21", "count": 10},
        {"bucket_ts": "22", "count": 10},
        {"bucket_ts": "23", "count": 10},
        {"bucket_ts": "24", "count": 10},
        {"bucket_ts": "25", "count": 20},
        {"bucket_ts": "26", "count": 20},
        {"bucket_ts": "27", "count": 20},
        {"bucket_ts": "28", "count": 20},
        {"bucket_ts": "29", "count": 20},
    ]
    ts_desc = list(reversed(ts))
    direction, pct = _compute_trend(ts_desc, short_n=7, long_n=21)
    assert direction == "up"
    assert pct > 5


def test_trend_computation_flat():
    """Trend direction 'flat' when short avg ≈ long avg."""
    ts = [{"bucket_ts": str(i), "count": 10} for i in range(30)]
    ts_desc = list(reversed(ts))
    direction, pct = _compute_trend(ts_desc, short_n=7, long_n=21)
    assert direction == "flat"
    assert abs(pct) <= 5


def test_trend_computation_insufficient_data():
    """Trend is flat when fewer than short_n + 1 buckets."""
    ts = [{"bucket_ts": "1", "count": 10}, {"bucket_ts": "2", "count": 20}]
    direction, pct = _compute_trend(ts, short_n=7, long_n=21)
    assert direction == "flat"
    assert pct == 0.0

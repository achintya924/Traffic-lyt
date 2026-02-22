"""
Phase 5.1: Zone system tests.
Assumes DB is running. Run init_zones first: python -m app.scripts.init_zones
Or: docker compose exec api python -m app.scripts.init_zones
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Valid GeoJSON Polygon (Manhattan bbox, closed ring)
VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[-74.02, 40.70], [-73.95, 40.70], [-73.95, 40.80], [-74.02, 40.80], [-74.02, 40.70]]
    ],
}

# Invalid: only 2 points (too few)
INVALID_POLYGON_FEW_POINTS = {
    "type": "Polygon",
    "coordinates": [[[-74.0, 40.7], [-73.9, 40.7]]],
}

# Invalid: self-intersecting bowtie
INVALID_POLYGON_SELF_INTERSECT = {
    "type": "Polygon",
    "coordinates": [
        [[-74.0, 40.7], [-73.9, 40.8], [-74.0, 40.8], [-73.9, 40.7], [-74.0, 40.7]]
    ],
}


@pytest.fixture(scope="module")
def ensure_zones_table():
    """Ensure zones table exists before tests."""
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


def test_create_zone_success(ensure_zones_table):
    """POST /api/zones creates a zone and returns id, name, zone_type, bbox, created_at."""
    payload = {
        "name": f"Test Zone {uuid.uuid4().hex[:8]}",
        "zone_type": "custom",
        "polygon": VALID_POLYGON,
    }
    r = client.post("/api/zones", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["name"] == payload["name"]
    assert data["zone_type"] == "custom"
    assert "bbox" in data
    assert "created_at" in data
    assert "meta" in data


def test_create_zone_invalid_polygon_fails(ensure_zones_table):
    """POST /api/zones with invalid polygon returns 422."""
    payload = {
        "name": "Bad Zone",
        "zone_type": "custom",
        "polygon": INVALID_POLYGON_FEW_POINTS,
    }
    r = client.post("/api/zones", json=payload)
    assert r.status_code == 422


def test_create_zone_self_intersect_fails(ensure_zones_table):
    """POST /api/zones with self-intersecting polygon returns 422."""
    payload = {
        "name": "Bowtie Zone",
        "zone_type": "custom",
        "polygon": INVALID_POLYGON_SELF_INTERSECT,
    }
    r = client.post("/api/zones", json=payload)
    assert r.status_code == 422


def test_list_zones_returns_created_zone(ensure_zones_table):
    """GET /api/zones returns created zones."""
    r = client.get("/api/zones")
    assert r.status_code == 200
    data = r.json()
    assert "zones" in data
    assert "total" in data
    assert isinstance(data["zones"], list)
    if data["zones"]:
        z = data["zones"][0]
        assert "id" in z
        assert "name" in z
        assert "zone_type" in z


def test_get_zone_by_id(ensure_zones_table):
    """GET /api/zones/{id} returns zone with geometry."""
    list_r = client.get("/api/zones")
    assert list_r.status_code == 200
    zones_list = list_r.json().get("zones", [])
    if not zones_list:
        pytest.skip("No zones created")
    zone_id = zones_list[0]["id"]
    r = client.get(f"/api/zones/{zone_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == zone_id
    assert "geom" in data
    assert "meta" in data


def test_delete_zone(ensure_zones_table):
    """DELETE /api/zones/{id} removes zone."""
    payload = {
        "name": f"To Delete {uuid.uuid4().hex[:8]}",
        "zone_type": "custom",
        "polygon": VALID_POLYGON,
    }
    create_r = client.post("/api/zones", json=payload)
    assert create_r.status_code in (200, 201)
    zone_id = create_r.json()["id"]
    del_r = client.delete(f"/api/zones/{zone_id}")
    assert del_r.status_code == 200
    get_r = client.get(f"/api/zones/{zone_id}")
    assert get_r.status_code == 404

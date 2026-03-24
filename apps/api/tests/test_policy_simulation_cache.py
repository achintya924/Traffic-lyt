"""
Phase 5.9B: Policy simulation cache behavior tests.
"""
import subprocess
import sys
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
def require_db():
    r = client.get("/db-check")
    if r.status_code != 200 or r.json().get("db") != "ok":
        pytest.skip("Database unavailable")
    yield


@pytest.fixture(scope="module")
def ensure_zones_table(require_db):
    result = subprocess.run(
        [sys.executable, "-m", "app.scripts.init_zones"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"init_zones failed: {result.stderr}")
    yield


@pytest.fixture
def policy_zones(ensure_zones_table):
    suffix = uuid.uuid4().hex[:8]
    z1 = client.post(
        "/api/zones",
        json={"name": f"Policy Cache Zone A {suffix}", "zone_type": "custom", "polygon": VALID_POLYGON},
    )
    z2 = client.post(
        "/api/zones",
        json={"name": f"Policy Cache Zone B {suffix}", "zone_type": "custom", "polygon": VALID_POLYGON},
    )
    if z1.status_code not in (200, 201) or z2.status_code not in (200, 201):
        pytest.skip("Could not create policy cache test zones")
    return [str(z1.json()["id"]), str(z2.json()["id"])]


def _payload(
    *,
    zones=None,
    anchor_ts="2024-01-15T12:00:00Z",
    interventions=None,
):
    return {
        "zones": zones if zones is not None else ["1", "2"],
        "horizon": "24h",
        "anchor_ts": anchor_ts,
        "interventions": interventions if interventions is not None else [{"type": "enforcement_intensity", "pct": 20}],
    }


def test_policy_cache_miss_then_hit(policy_zones):
    p = _payload(zones=policy_zones)
    r1 = client.post("/api/policy/simulate", json=p)
    r2 = client.post("/api/policy/simulate", json=p)
    assert r1.status_code == 200 and r2.status_code == 200
    j1 = r1.json()
    j2 = r2.json()
    assert j1["meta"]["response_cache"]["status"] == "miss"
    assert j2["meta"]["response_cache"]["status"] == "hit"
    assert j1["meta"]["response_cache"]["key"] == j2["meta"]["response_cache"]["key"]


def test_policy_cache_zone_order_independence(policy_zones):
    r1 = client.post("/api/policy/simulate", json=_payload(zones=[policy_zones[0], policy_zones[1]]))
    r2 = client.post("/api/policy/simulate", json=_payload(zones=[policy_zones[1], policy_zones[0]]))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["meta"]["response_cache"]["status"] == "hit"
    assert r1.json()["meta"]["response_cache"]["key"] == r2.json()["meta"]["response_cache"]["key"]


def test_policy_cache_intervention_order_independence(policy_zones):
    i1 = [
        {"type": "enforcement_intensity", "pct": 20},
        {"type": "peak_hour_reduction", "pct": 12},
    ]
    i2 = [
        {"type": "peak_hour_reduction", "pct": 12},
        {"type": "enforcement_intensity", "pct": 20},
    ]
    r1 = client.post("/api/policy/simulate", json=_payload(zones=policy_zones, interventions=i1))
    r2 = client.post("/api/policy/simulate", json=_payload(zones=policy_zones, interventions=i2))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["meta"]["response_cache"]["status"] == "hit"
    assert r1.json()["meta"]["response_cache"]["key"] == r2.json()["meta"]["response_cache"]["key"]


def test_policy_cache_numeric_normalization_pct(policy_zones):
    r1 = client.post(
        "/api/policy/simulate",
        json=_payload(zones=policy_zones, interventions=[{"type": "enforcement_intensity", "pct": 20}]),
    )
    r2 = client.post(
        "/api/policy/simulate",
        json=_payload(zones=policy_zones, interventions=[{"type": "enforcement_intensity", "pct": 20.0}]),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["meta"]["response_cache"]["status"] == "hit"
    assert r1.json()["meta"]["response_cache"]["key"] == r2.json()["meta"]["response_cache"]["key"]


def test_policy_cache_anchor_sensitivity(policy_zones):
    r1 = client.post("/api/policy/simulate", json=_payload(zones=policy_zones, anchor_ts="2024-01-15T12:00:00Z"))
    r2 = client.post("/api/policy/simulate", json=_payload(zones=policy_zones, anchor_ts="2024-01-15T12:00:01Z"))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["meta"]["response_cache"]["status"] in ("miss", "hit")
    assert r2.json()["meta"]["response_cache"]["status"] in ("miss", "hit")
    assert r1.json()["meta"]["response_cache"]["key"] != r2.json()["meta"]["response_cache"]["key"]

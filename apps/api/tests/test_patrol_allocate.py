"""
Phase 5.8: Patrol allocation tests.
Requires DB with zones and violations (e.g. docker compose up).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def require_db():
    """Skip tests if DB unavailable."""
    r = client.post("/api/patrol/allocate", json={"units": 1})
    if r.status_code == 503:
        pytest.skip("Database unavailable; run with docker compose up")
    yield


def test_allocate_returns_200(require_db):
    """POST /api/patrol/allocate with valid request returns 200."""
    r = client.post(
        "/api/patrol/allocate",
        json={"units": 3, "strategy": "balanced"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "plan" in data
    assert "meta" in data
    assert "response_cache" in data["meta"]
    assert isinstance(data["plan"], list)
    for item in data["plan"]:
        assert "zone" in item
        assert "id" in item["zone"]
        assert "name" in item["zone"]
        assert "zone_type" in item["zone"]
        assert "assigned_units" in item
        assert item["assigned_units"] >= 1
        assert "priority_score" in item
        assert "reasons" in item
        assert "recommendation_hint" in item
        assert isinstance(item["reasons"], list)


def test_allocate_invalid_units_returns_422():
    """POST /api/patrol/allocate with invalid units returns 422."""
    r = client.post(
        "/api/patrol/allocate",
        json={"units": 0},
    )
    assert r.status_code == 422
    r2 = client.post(
        "/api/patrol/allocate",
        json={"units": 51},
    )
    assert r2.status_code == 422


def test_allocate_invalid_strategy_returns_422():
    """POST /api/patrol/allocate with invalid strategy returns 422."""
    r = client.post(
        "/api/patrol/allocate",
        json={"units": 3, "strategy": "invalid"},
    )
    assert r.status_code == 422


def test_allocate_exclude_zone_ids_respected(require_db):
    """exclude_zone_ids removes zones from the plan."""
    r1 = client.post(
        "/api/patrol/allocate",
        json={"units": 5, "strategy": "balanced"},
    )
    assert r1.status_code == 200
    plan1 = r1.json()["plan"]
    zone_ids = [p["zone"]["id"] for p in plan1]
    if not zone_ids:
        pytest.skip("No zones in plan to exclude")
    exclude = [zone_ids[0]]
    r2 = client.post(
        "/api/patrol/allocate",
        json={"units": 5, "strategy": "balanced", "exclude_zone_ids": exclude},
    )
    assert r2.status_code == 200
    plan2 = r2.json()["plan"]
    plan2_ids = [p["zone"]["id"] for p in plan2]
    assert exclude[0] not in plan2_ids


def test_allocate_deterministic_output(require_db):
    """Same inputs produce same plan ordering."""
    payload = {"units": 3, "strategy": "risk_max", "period": "current", "shift_hours": 6}
    r1 = client.post("/api/patrol/allocate", json=payload)
    r2 = client.post("/api/patrol/allocate", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    plan1 = r1.json()["plan"]
    plan2 = r2.json()["plan"]
    assert len(plan1) == len(plan2)
    for i, (p1, p2) in enumerate(zip(plan1, plan2)):
        assert p1["zone"]["id"] == p2["zone"]["id"], f"Mismatch at index {i}"
        assert p1["assigned_units"] == p2["assigned_units"]


def test_allocate_response_cache_miss_then_hit(require_db):
    """First request has response_cache 'miss', second identical request has 'hit'."""
    payload = {"units": 2, "strategy": "trend_focus", "period": "mom"}
    r1 = client.post("/api/patrol/allocate", json=payload)
    assert r1.status_code == 200
    assert r1.json()["meta"]["response_cache"] == "miss"
    r2 = client.post("/api/patrol/allocate", json=payload)
    assert r2.status_code == 200
    assert r2.json()["meta"]["response_cache"] == "hit"

"""
Phase 5.9A: Policy simulation contract and validation tests.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FIXED_ANCHOR = "2024-01-15T12:00:00Z"


def test_simulate_happy_path():
    """POST /api/policy/simulate with valid body returns 200 and contract shape."""
    payload = {
        "zones": ["zone_a"],
        "horizon": "24h",
        "anchor_ts": FIXED_ANCHOR,
        "interventions": [{"type": "enforcement_intensity", "pct": 20}],
    }
    r = client.post("/api/policy/simulate", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "meta" in data
    assert "baseline" in data
    assert "simulated" in data
    assert "delta" in data
    assert "explain" in data

    assert data["meta"]["anchor_ts"] == FIXED_ANCHOR
    assert data["meta"]["response_cache"]["status"] == "miss"
    assert data["meta"]["response_cache"]["key"] is None

    assert data["simulated"]["zones"] == data["baseline"]["zones"]
    assert data["simulated"]["overall_total"] == data["baseline"]["overall_total"]
    assert data["delta"]["overall_delta"] == 0
    assert data["delta"]["overall_delta_pct"] is None
    for zd in data["delta"]["zones"]:
        assert zd["delta"] == 0
        assert zd["delta_pct"] is None

    codes = [e["code"] for e in data["explain"]]
    assert "stub" in codes


def test_simulate_zones_empty_422():
    """zones: [] returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={"zones": [], "horizon": "24h", "interventions": [{"type": "enforcement_intensity", "pct": 10}]},
    )
    assert r.status_code == 422


def test_simulate_zones_duplicate_422():
    """zones with duplicates returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={"zones": ["zone_a", "zone_a"], "horizon": "24h", "interventions": [{"type": "enforcement_intensity", "pct": 10}]},
    )
    assert r.status_code == 422


def test_simulate_zones_over_10_422():
    """zones > 10 returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={
            "zones": [f"z{i}" for i in range(11)],
            "horizon": "24h",
            "interventions": [{"type": "enforcement_intensity", "pct": 10}],
        },
    )
    assert r.status_code == 422


def test_simulate_interventions_empty_422():
    """interventions: [] returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={"zones": ["zone_a"], "horizon": "24h", "interventions": []},
    )
    assert r.status_code == 422


def test_simulate_interventions_over_5_422():
    """interventions > 5 returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={
            "zones": ["zone_a"],
            "horizon": "24h",
            "interventions": [{"type": "enforcement_intensity", "pct": 10}] * 6,
        },
    )
    assert r.status_code == 422


def test_simulate_enforcement_pct_invalid_422():
    """enforcement_intensity pct -1 or 201 returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={"zones": ["zone_a"], "horizon": "24h", "interventions": [{"type": "enforcement_intensity", "pct": -1}]},
    )
    assert r.status_code == 422
    r2 = client.post(
        "/api/policy/simulate",
        json={"zones": ["zone_a"], "horizon": "24h", "interventions": [{"type": "enforcement_intensity", "pct": 201}]},
    )
    assert r2.status_code == 422


def test_simulate_patrol_units_same_422():
    """patrol_units with to_units == from_units returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={"zones": ["zone_a"], "horizon": "24h", "interventions": [{"type": "patrol_units", "from_units": 3, "to_units": 3}]},
    )
    assert r.status_code == 422


def test_simulate_peak_hour_reduction_over_90_422():
    """peak_hour_reduction pct 91 returns 422."""
    r = client.post(
        "/api/policy/simulate",
        json={"zones": ["zone_a"], "horizon": "24h", "interventions": [{"type": "peak_hour_reduction", "pct": 91}]},
    )
    assert r.status_code == 422


def test_simulate_determinism():
    """Same payload (including anchor_ts) yields same baseline per zone; compare excluding request_id."""
    payload = {
        "zones": ["zone_x", "zone_y"],
        "horizon": "30d",
        "anchor_ts": FIXED_ANCHOR,
        "interventions": [{"type": "enforcement_intensity", "pct": 50}],
    }
    r1 = client.post("/api/policy/simulate", json=payload)
    r2 = client.post("/api/policy/simulate", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200

    d1 = r1.json()
    d2 = r2.json()

    # Exclude request_id for comparison
    def without_request_id(d):
        out = dict(d)
        out["meta"] = {k: v for k, v in out["meta"].items() if k != "request_id"}
        return out

    b1 = without_request_id(d1)
    b2 = without_request_id(d2)
    assert b1["meta"] == b2["meta"]
    assert d1["baseline"] == d2["baseline"]
    assert d1["simulated"] == d2["simulated"]
    assert d1["delta"] == d2["delta"]
    assert d1["explain"] == d2["explain"]

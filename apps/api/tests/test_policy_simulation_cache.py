"""
Phase 5.9B: Policy simulation cache behavior tests.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _payload(
    *,
    zones=None,
    anchor_ts="2024-01-15T12:00:00Z",
    interventions=None,
):
    return {
        "zones": zones if zones is not None else ["zone_a", "zone_b"],
        "horizon": "24h",
        "anchor_ts": anchor_ts,
        "interventions": interventions if interventions is not None else [{"type": "enforcement_intensity", "pct": 20}],
    }


def test_policy_cache_miss_then_hit():
    p = _payload()
    r1 = client.post("/api/policy/simulate", json=p)
    r2 = client.post("/api/policy/simulate", json=p)
    assert r1.status_code == 200 and r2.status_code == 200
    j1 = r1.json()
    j2 = r2.json()
    assert j1["meta"]["response_cache"]["status"] == "miss"
    assert j2["meta"]["response_cache"]["status"] == "hit"
    assert j1["meta"]["response_cache"]["key"] == j2["meta"]["response_cache"]["key"]


def test_policy_cache_zone_order_independence():
    r1 = client.post("/api/policy/simulate", json=_payload(zones=["a", "b"]))
    r2 = client.post("/api/policy/simulate", json=_payload(zones=["b", "a"]))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["meta"]["response_cache"]["status"] == "hit"
    assert r1.json()["meta"]["response_cache"]["key"] == r2.json()["meta"]["response_cache"]["key"]


def test_policy_cache_intervention_order_independence():
    i1 = [
        {"type": "enforcement_intensity", "pct": 20},
        {"type": "peak_hour_reduction", "pct": 12},
    ]
    i2 = [
        {"type": "peak_hour_reduction", "pct": 12},
        {"type": "enforcement_intensity", "pct": 20},
    ]
    r1 = client.post("/api/policy/simulate", json=_payload(interventions=i1))
    r2 = client.post("/api/policy/simulate", json=_payload(interventions=i2))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["meta"]["response_cache"]["status"] == "hit"
    assert r1.json()["meta"]["response_cache"]["key"] == r2.json()["meta"]["response_cache"]["key"]


def test_policy_cache_numeric_normalization_pct():
    r1 = client.post(
        "/api/policy/simulate",
        json=_payload(interventions=[{"type": "enforcement_intensity", "pct": 20}]),
    )
    r2 = client.post(
        "/api/policy/simulate",
        json=_payload(interventions=[{"type": "enforcement_intensity", "pct": 20.0}]),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["meta"]["response_cache"]["status"] == "hit"
    assert r1.json()["meta"]["response_cache"]["key"] == r2.json()["meta"]["response_cache"]["key"]


def test_policy_cache_anchor_sensitivity():
    r1 = client.post("/api/policy/simulate", json=_payload(anchor_ts="2024-01-15T12:00:00Z"))
    r2 = client.post("/api/policy/simulate", json=_payload(anchor_ts="2024-01-15T12:00:01Z"))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["meta"]["response_cache"]["status"] in ("miss", "hit")
    assert r2.json()["meta"]["response_cache"]["status"] in ("miss", "hit")
    assert r1.json()["meta"]["response_cache"]["key"] != r2.json()["meta"]["response_cache"]["key"]

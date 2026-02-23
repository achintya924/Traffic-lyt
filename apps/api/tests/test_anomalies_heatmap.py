"""
Phase 5.5: Anomaly heatmap tests.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.anomalies import _zscore_anomaly_weight

client = TestClient(app)


def test_heatmap_returns_200():
    """GET /api/anomalies/heatmap returns 200."""
    r = client.get("/api/anomalies/heatmap")
    assert r.status_code == 200
    data = r.json()
    assert "points" in data
    assert "meta" in data
    assert isinstance(data["points"], list)
    assert "request_id" in data["meta"] or "anchor_ts" in data["meta"]
    assert "window" in data["meta"]
    assert "response_cache" in data["meta"]


def test_heatmap_invalid_method_returns_422():
    """GET /api/anomalies/heatmap?method=invalid returns 422."""
    r = client.get("/api/anomalies/heatmap", params={"method": "invalid"})
    assert r.status_code == 422


def test_heatmap_ewm_not_implemented_returns_422():
    """GET /api/anomalies/heatmap?method=ewm returns 422 (ewm not implemented)."""
    r = client.get("/api/anomalies/heatmap", params={"method": "ewm"})
    assert r.status_code == 422


def test_heatmap_respects_top_n():
    """GET /api/anomalies/heatmap?top_n=3 returns at most 3 points."""
    r = client.get("/api/anomalies/heatmap", params={"top_n": 3})
    assert r.status_code == 200
    assert len(r.json()["points"]) <= 3


def test_heatmap_response_cache_miss_then_hit():
    """First request has response_cache 'miss', second identical request has 'hit'."""
    params = {"top_n": 99, "granularity": "day"}
    r1 = client.get("/api/anomalies/heatmap", params=params)
    assert r1.status_code == 200
    assert r1.json()["meta"]["response_cache"] == "miss"
    r2 = client.get("/api/anomalies/heatmap", params=params)
    assert r2.status_code == 200
    assert r2.json()["meta"]["response_cache"] == "hit"


def test_zscore_handles_stddev_zero_safely():
    """_zscore_anomaly_weight handles stddev=0 without crash."""
    hits, weight = _zscore_anomaly_weight([5, 5, 5, 5], 3.0)
    assert hits == 0
    assert weight == 0.0


def test_zscore_empty_counts():
    """_zscore_anomaly_weight with empty list returns 0."""
    hits, weight = _zscore_anomaly_weight([], 3.0)
    assert hits == 0
    assert weight == 0.0


def test_zscore_single_count():
    """_zscore_anomaly_weight with single count (no stddev) returns 0."""
    hits, weight = _zscore_anomaly_weight([10], 3.0)
    assert hits == 0
    assert weight == 0.0

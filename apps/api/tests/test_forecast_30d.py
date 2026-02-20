"""
Phase 4.9A: 30-day daily forecast + data sufficiency.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_forecast_daily_30_shape():
    """GET /predict/forecast?granularity=day&horizon=30 returns 30 forecast points and summary.expected_total."""
    r = client.get(
        "/predict/forecast",
        params={"granularity": "day", "horizon": 30, "bbox": "-74.1,40.6,-73.9,40.8"},
    )
    assert r.status_code == 200
    data = r.json()
    forecast = data.get("forecast", [])
    assert len(forecast) == 30
    assert "summary" in data
    assert "expected_total" in data["summary"]
    assert data["summary"]["horizon"] == 30
    assert data["summary"]["granularity"] == "day"
    assert data["summary"]["scope"] == "viewport"
    for f in forecast:
        assert "ts" in f
        assert "count" in f


def test_forecast_daily_includes_meta_quality():
    """Forecast response includes meta.data_quality (may be None or insufficient_data)."""
    r = client.get(
        "/predict/forecast",
        params={"granularity": "day", "horizon": 30, "bbox": "-74.1,40.6,-73.9,40.8"},
    )
    assert r.status_code == 200
    data = r.json()
    meta = data.get("meta", {})
    assert "data_quality" in meta
    dq = meta["data_quality"]
    if dq is not None:
        assert dq.get("status") == "insufficient_data"
        assert "total_events_last_90d" in dq
        assert "nonzero_days_last_90d" in dq
        assert "recommendation" in dq


def test_cache_key_changes_with_granularity():
    """Same params but different granularity => different response (cache miss)."""
    bbox = "-74.05,40.65,-73.95,40.75"
    r1 = client.get("/predict/forecast", params={"granularity": "hour", "horizon": 24, "bbox": bbox})
    r2 = client.get("/predict/forecast", params={"granularity": "day", "horizon": 24, "bbox": bbox})
    assert r1.status_code == 200 and r2.status_code == 200
    d1 = r1.json()
    d2 = r2.json()
    assert d1["granularity"] == "hour"
    assert d2["granularity"] == "day"
    assert len(d1["forecast"]) == 24
    assert len(d2["forecast"]) == 24
    assert d1["forecast"][0]["ts"] != d2["forecast"][0]["ts"]

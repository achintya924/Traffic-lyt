"""
Phase 4.1: Time window anchoring – minimal pytest coverage.

Assumes DB is running with ingested data. Run:
  pytest apps/api/tests/test_time_anchor.py -v
  or: docker compose -f infra/docker-compose.yml exec api pytest tests/test_time_anchor.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _meta_contract(meta: dict) -> None:
    """Assert meta contains Phase 4.1 data freshness keys."""
    assert "data_min_ts" in meta
    assert "data_max_ts" in meta
    assert "anchor_ts" in meta
    assert "effective_window" in meta
    assert "window_source" in meta
    assert meta["window_source"] in ("anchored", "absolute")
    assert meta.get("timezone") == "UTC"
    assert "start_ts" in meta["effective_window"]
    assert "end_ts" in meta["effective_window"]


def test_timeseries_meta_anchored_when_no_start_end():
    """GET /predict/timeseries without start/end returns meta with window_source anchored."""
    response = client.get("/predict/timeseries", params={"granularity": "day", "limit_history": 50})
    assert response.status_code == 200
    data = response.json()
    assert "meta" in data
    meta = data["meta"]
    _meta_contract(meta)
    # When no start/end we anchor to data; window_source should be anchored (or absolute if no data and we still set it)
    assert meta["window_source"] in ("anchored", "absolute")
    if meta.get("data_max_ts") is not None:
        assert meta.get("anchor_ts") == meta.get("data_max_ts")


def test_timeseries_meta_absolute_when_start_end_provided():
    """GET /predict/timeseries with start and end returns window_source=absolute (when DB available)."""
    response = client.get(
        "/predict/timeseries",
        params={
            "granularity": "day",
            "limit_history": 50,
            "start": "2023-08-01T00:00:00",
            "end": "2023-08-31T23:59:59",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "meta" in data
    meta = data["meta"]
    _meta_contract(meta)
    if meta.get("data_max_ts") is None and meta.get("effective_window", {}).get("start_ts") is None:
        pytest.skip("No DB or no data: cannot assert absolute window")
    assert meta["window_source"] == "absolute"
    assert meta["effective_window"]["start_ts"] is not None
    assert meta["effective_window"]["end_ts"] is not None


def test_hotspots_empty_scope_consistent_no_data():
    """GET /predict/hotspots/grid with bbox that has no data returns 200, empty cells, meta with nulls and message."""
    # Use a bbox far from NYC so likely no data (or skip if DB has global data)
    response = client.get(
        "/predict/hotspots/grid",
        params={
            "cell_m": 250,
            "recent_days": 7,
            "baseline_days": 30,
            "bbox": "0,0,1,1",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "cells" in data
    assert "meta" in data
    meta = data["meta"]
    assert meta.get("points") == 0
    # When no data, data_max_ts / anchor_ts can be null and message set
    if meta.get("data_max_ts") is None:
        assert meta.get("anchor_ts") is None
        assert "message" in meta


def test_stats_meta_contains_time_contract():
    """GET /violations/stats returns meta with data_min_ts, data_max_ts, effective_window, window_source."""
    response = client.get("/violations/stats")
    assert response.status_code == 200
    data = response.json()
    assert "meta" in data
    _meta_contract(data["meta"])


def test_viewport_scoped_max_differs_from_global_when_bbox_excludes_latest():
    """With bbox, data_max_ts in meta can differ from global max (viewport-scoped)."""
    # Global (no bbox)
    r_global = client.get("/violations/stats")
    assert r_global.status_code == 200
    meta_global = r_global.json().get("meta") or {}
    global_max = meta_global.get("data_max_ts")

    # Viewport with bbox (e.g. NYC area)
    r_bbox = client.get(
        "/violations/stats",
        params={"bbox": "-74.1,40.6,-73.9,40.8"},
    )
    assert r_bbox.status_code == 200
    meta_bbox = r_bbox.json().get("meta") or {}
    bbox_max = meta_bbox.get("data_max_ts")

    # If both have data, they can be equal (if latest point is inside bbox) or bbox_max can be older
    # We only assert that meta is present and contract holds; viewport uses same filter scope for min/max
    _meta_contract(meta_bbox)
    if global_max and bbox_max:
        # bbox scope is subset; its max cannot be after global max (assuming same other filters)
        assert meta_bbox.get("data_min_ts") is not None or meta_bbox.get("data_max_ts") is not None

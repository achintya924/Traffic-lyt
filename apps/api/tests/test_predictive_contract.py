"""
Phase 4.7: Predictive contract helpers (build_eval_meta, format_explainability).
"""
import json

import pytest

from app.utils.predictive_contract import build_eval_meta, format_explainability


def test_format_explainability_returns_stable_schema():
    """format_explainability returns dict with features, method, notes."""
    out = format_explainability([], [])
    assert "features" in out
    assert "method" in out
    assert "notes" in out
    assert isinstance(out["features"], list)
    assert out["method"] == "linear_coefficients"


def test_format_explainability_sorted_by_weight_desc():
    """Features are sorted by weight descending."""
    top_pos = [{"feature": "a", "coef": 0.1}, {"feature": "b", "coef": 0.5}]
    top_neg = [{"feature": "c", "coef": -0.3}]
    out = format_explainability(top_pos, top_neg)
    weights = [f["weight"] for f in out["features"]]
    assert weights == sorted(weights, reverse=True)
    assert weights[0] == 0.5
    assert weights[1] == 0.3
    assert weights[2] == 0.1


def test_format_explainability_json_safe():
    """Output is JSON-serializable."""
    top_pos = [{"feature": "dow__x0_2.0", "coef": 0.25}]
    out = format_explainability(top_pos, [])
    s = json.dumps(out)
    parsed = json.loads(s)
    assert parsed["features"][0]["name"] == "Day of week = Wednesday"
    assert parsed["features"][0]["raw_feature"] == "dow__x0_2.0"
    assert parsed["features"][0]["effect"] == "increase"
    assert parsed["features"][0]["coef"] == 0.25
    assert parsed["features"][0]["weight"] == 0.25


def test_format_explainability_humanize_hour():
    """hour__x1_23.0 -> Hour = 23."""
    out = format_explainability([{"feature": "hour__x1_23.0", "coef": 0.4}], [])
    assert out["features"][0]["name"] == "Hour = 23"
    assert out["features"][0]["raw_feature"] == "hour__x1_23.0"


def test_format_explainability_limit():
    """Limit to max_features (default 10)."""
    top_pos = [{"feature": f"f{i}", "coef": 1.0 - i * 0.1} for i in range(15)]
    out = format_explainability(top_pos, [], max_features=5)
    assert len(out["features"]) == 5


def test_build_eval_meta_expected_keys():
    """build_eval_meta returns metrics, test_points, etc when provided."""
    info = {"mae": 1.2, "mape": 15.0, "test_points": 20, "train_points": 80, "horizon": 24, "granularity": "hour"}
    out = build_eval_meta(info)
    assert out is not None
    assert "metrics" in out
    assert out["metrics"]["mae"] == 1.2
    assert out["metrics"]["mape"] == 15.0
    assert out["test_points"] == 20
    assert out["train_points"] == 80
    assert out["horizon"] == 24
    assert out["granularity"] == "hour"


def test_build_eval_meta_returns_none_for_empty():
    """build_eval_meta returns None for empty or null input."""
    assert build_eval_meta(None) is None
    assert build_eval_meta({}) is None


def test_build_eval_meta_points_used_window():
    """build_eval_meta accepts points_used and window (trends)."""
    out = build_eval_meta({"points_used": 28, "window": 14})
    assert out is not None
    assert out["points_used"] == 28
    assert out["window"] == 14


# --- Endpoint-level tests ---

@pytest.fixture
def predict_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_risk_meta_contains_explain_with_features(predict_client):
    """GET /predict/risk response meta contains meta.explain.features (list) with required keys."""
    r = predict_client.get(
        "/predict/risk",
        params={"granularity": "hour", "horizon": 24, "bbox": "-74.1,40.6,-73.9,40.8"},
    )
    assert r.status_code == 200
    data = r.json()
    meta = data.get("meta", {})
    assert "explain" in meta
    explain = meta["explain"]
    assert "features" in explain
    assert isinstance(explain["features"], list)
    assert "method" in explain
    for feat in explain["features"]:
        assert "name" in feat
        assert "raw_feature" in feat
        assert "effect" in feat
        assert "coef" in feat
        assert "weight" in feat


def test_risk_meta_contains_eval(predict_client):
    """GET /predict/risk response meta contains meta.eval (dict or null)."""
    r = predict_client.get(
        "/predict/risk",
        params={"granularity": "hour", "horizon": 24, "bbox": "-74.1,40.6,-73.9,40.8"},
    )
    assert r.status_code == 200
    meta = r.json().get("meta", {})
    assert "eval" in meta
    eval_meta = meta["eval"]
    if eval_meta is not None:
        assert "metrics" in eval_meta
        assert isinstance(eval_meta["metrics"], dict)
        if eval_meta["metrics"]:
            assert "mae" in eval_meta["metrics"] or "mape" in eval_meta["metrics"]


def test_forecast_meta_contains_eval(predict_client):
    """GET /predict/forecast response meta contains meta.eval (null for ma/ewm)."""
    r = predict_client.get(
        "/predict/forecast",
        params={"granularity": "hour", "horizon": 24, "bbox": "-74.1,40.6,-73.9,40.8"},
    )
    assert r.status_code == 200
    meta = r.json().get("meta", {})
    assert "eval" in meta
    assert meta.get("explain") is None

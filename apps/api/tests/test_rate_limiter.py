"""
Phase 4.4: Rate limiting.
Run: pytest apps/api/tests/test_rate_limiter.py -v
  or: docker compose -f infra/docker-compose.yml exec api pytest tests/test_rate_limiter.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_stats_under_limit_returns_200(rate_limit_enabled):
    """N requests under limit → 200."""
    for _ in range(5):
        r = client.get("/violations/stats")
        assert r.status_code == 200


def test_stats_exceeds_limit_returns_429(rate_limit_enabled):
    """Exceed stats limit (60/min) → 429 with Retry-After header."""
    # Make 61 requests; last should be 429
    responses = []
    for _ in range(61):
        responses.append(client.get("/violations/stats"))
    ok_count = sum(1 for r in responses if r.status_code == 200)
    fail_count = sum(1 for r in responses if r.status_code == 429)
    assert fail_count >= 1, "At least one request should be rate-limited"
    failed = next(r for r in responses if r.status_code == 429)
    assert "Retry-After" in failed.headers
    data = failed.json()
    assert data.get("detail", {}).get("detail") == "Rate limit exceeded"
    assert "group" in data.get("detail", {})
    assert "retry_after_seconds" in data.get("detail", {})


def test_predict_under_limit_returns_200(rate_limit_enabled):
    """Predict endpoints under limit → 200."""
    for _ in range(5):
        r = client.get("/predict/risk", params={"granularity": "hour", "horizon": 24})
        assert r.status_code == 200


def test_predict_exceeds_limit_returns_429(rate_limit_enabled):
    """Exceed predict limit (30/min) → 429."""
    responses = []
    for _ in range(32):
        responses.append(client.get("/predict/risk", params={"granularity": "hour", "horizon": 24}))
    fail_count = sum(1 for r in responses if r.status_code == 429)
    assert fail_count >= 1
    failed = next(r for r in responses if r.status_code == 429)
    assert "Retry-After" in failed.headers
    data = failed.json()
    assert "detail" in data
    assert data.get("detail", {}).get("group") == "predict"


def test_internal_cache_not_rate_limited():
    """GET /internal/cache is not rate-limited (or returns 200/disabled)."""
    r = client.get("/internal/cache")
    assert r.status_code == 200

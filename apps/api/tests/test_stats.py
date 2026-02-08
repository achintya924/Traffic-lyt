"""
Minimal pytest coverage for GET /violations/stats.
Assumes DB is running (e.g. via docker compose) and contains ingested sample data.
Run: pytest apps/api/tests/test_stats.py -v
  or from repo root: docker compose -f infra/docker-compose.yml exec api pytest tests/test_stats.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_violations_stats_returns_200_and_expected_keys():
    """GET /violations/stats returns 200 and JSON has total, min_time, max_time, top_types."""
    response = client.get("/violations/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "min_time" in data
    assert "max_time" in data
    assert "top_types" in data
    assert isinstance(data["top_types"], list)


def test_violations_stats_invalid_hour_start_returns_422():
    """invalid hour_start=-1 returns 422."""
    response = client.get("/violations/stats?hour_start=-1")
    assert response.status_code == 422


def test_violations_stats_start_after_end_returns_422():
    """start > end returns 422."""
    response = client.get(
        "/violations/stats",
        params={"start": "2024-01-02T00:00:00", "end": "2024-01-01T00:00:00"},
    )
    assert response.status_code == 422


def test_violations_stats_filtered_total_lte_unfiltered():
    """Filtering by violation_type yields total <= unfiltered total."""
    unfiltered = client.get("/violations/stats")
    assert unfiltered.status_code == 200
    total_unfiltered = unfiltered.json()["total"]

    # Get one violation's type from /violations?limit=1
    violations_res = client.get("/violations?limit=1")
    assert violations_res.status_code == 200
    violations = violations_res.json().get("violations") or []
    if not violations or violations[0].get("violation_type") is None:
        pytest.skip("No violation with violation_type in DB")
    vtype = violations[0]["violation_type"]

    filtered = client.get("/violations/stats", params={"violation_type": vtype})
    assert filtered.status_code == 200
    total_filtered = filtered.json()["total"]
    assert total_filtered <= total_unfiltered

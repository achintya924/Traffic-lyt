"""
Phase 4.6: Request ID, structured logging, internal metrics.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

UUID_HEX_RE = re.compile(r"^[a-f0-9]{32}$")


def test_request_id_echo():
    """Send X-Request-ID header; assert same in response header."""
    req_id = "abc123def456"
    r = client.get("/health", headers={"X-Request-ID": req_id})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == req_id


def test_request_id_generated():
    """No X-Request-ID; assert response has X-Request-ID and looks uuid hex."""
    r = client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) == 32
    assert UUID_HEX_RE.match(rid)


def test_internal_metrics_debug_guard():
    """When DEBUG not set, /internal/metrics returns disabled message."""
    r = client.get("/internal/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert "disabled" in data.get("error", "").lower()


def test_internal_metrics_when_debug(monkeypatch):
    """When DEBUG=true, /internal/metrics returns expected keys."""
    monkeypatch.setenv("DEBUG", "true")
    r = client.get("/internal/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "uptime_seconds" in data
    assert "model_registry" in data
    assert "response_cache" in data
    assert "rate_limiter" in data
    rl = data["rate_limiter"]
    assert "allowed" in rl
    assert "blocked" in rl

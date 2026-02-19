"""
Pytest configuration. Disable rate limiting by default so other tests are not affected.
test_rate_limiter.py overrides this to test rate limit behavior.
"""
import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _disable_rate_limit_for_tests():
    """Disable rate limiting so stats, cache, etc. tests are not blocked by limits."""
    os.environ["RATE_LIMIT_DISABLED"] = "true"
    yield
    os.environ.pop("RATE_LIMIT_DISABLED", None)


@pytest.fixture
def rate_limit_enabled(monkeypatch):
    """Re-enable rate limiting for tests that need it (e.g. test_rate_limiter)."""
    monkeypatch.delitem(os.environ, "RATE_LIMIT_DISABLED", raising=False)

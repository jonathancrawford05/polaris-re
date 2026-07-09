"""
Tests for the API security layer (``polaris_re/api/auth.py``).

Slice 2 of the Production Hardening & Observability epic (ROADMAP 6.2): optional,
default-off API-key authentication and rate limiting, exposed as two Starlette
middlewares plus their environment-driven configuration helpers.

All tests are deterministic and clock-independent (per the ADR-074 guard): the
rate limiter's clock is injected via a fake so window behaviour is exercised by
advancing a counter, never by sleeping or reading the wall clock. Configuration
is driven through ``monkeypatch.setenv`` so no test mutates global state that
outlives it.
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_re.api.auth import (
    API_KEY_HEADER,
    API_KEYS_ENV,
    RATE_LIMIT_ENV,
    APIKeyAuthMiddleware,
    RateLimitMiddleware,
    SlidingWindowRateLimiter,
    configured_api_keys,
    configured_rate_limit,
)
from polaris_re.api.main import app as real_app
from polaris_re.api.observability import (
    ACCESS_LOGGER_NAME,
    CORRELATION_ID_HEADER,
    RequestContextMiddleware,
)


class _FakeClock:
    """A monotonic-looking clock whose value only moves when advanced."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class _CapturingHandler(logging.Handler):
    """Collect emitted records for assertion (bypasses the JSON formatter)."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def access_records():
    """Attach a capturing handler to the access logger for the test's span."""
    logger = logging.getLogger(ACCESS_LOGGER_NAME)
    handler = _CapturingHandler()
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)


def _build_app(limiter: SlidingWindowRateLimiter | None = None) -> FastAPI:
    """A minimal app carrying the production middleware stack + probe/protected routes."""
    app = FastAPI()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/echo")
    def echo_get() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/echo")
    def echo_post() -> dict[str, bool]:
        return {"ok": True}

    # Reverse registration order → request flow:
    #   RequestContext (outer) → RateLimit → Auth (inner) → endpoint.
    app.add_middleware(APIKeyAuthMiddleware)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
    app.add_middleware(RequestContextMiddleware)
    return app


# ---------------------------------------------------------------------------
# Configuration parsing
# ---------------------------------------------------------------------------


class TestConfiguredApiKeys:
    def test_unset_is_empty(self, monkeypatch):
        monkeypatch.delenv(API_KEYS_ENV, raising=False)
        assert configured_api_keys() == frozenset()

    def test_blank_is_empty(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, "   ")
        assert configured_api_keys() == frozenset()

    def test_parses_comma_separated_and_trims(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, " k1 , k2 ,, k3 ")
        assert configured_api_keys() == frozenset({"k1", "k2", "k3"})


class TestConfiguredRateLimit:
    def test_unset_is_none(self, monkeypatch):
        monkeypatch.delenv(RATE_LIMIT_ENV, raising=False)
        assert configured_rate_limit() is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("100/minute", (100, 60.0)),
            ("10/second", (10, 1.0)),
            ("5/hour", (5, 3600.0)),
            ("7", (7, 60.0)),  # bare count defaults to per-minute
            ("3/m", (3, 60.0)),
        ],
    )
    def test_parses_valid(self, monkeypatch, value, expected):
        monkeypatch.setenv(RATE_LIMIT_ENV, value)
        assert configured_rate_limit() == expected

    @pytest.mark.parametrize("value", ["", "  ", "abc", "0/minute", "-5", "10/fortnight"])
    def test_malformed_is_none(self, monkeypatch, value):
        monkeypatch.setenv(RATE_LIMIT_ENV, value)
        assert configured_rate_limit() is None


# ---------------------------------------------------------------------------
# Sliding-window limiter (unit, fake clock)
# ---------------------------------------------------------------------------


class TestSlidingWindowRateLimiter:
    def test_allows_up_to_limit_then_blocks(self):
        clock = _FakeClock()
        limiter = SlidingWindowRateLimiter(time_fn=clock)
        assert limiter.allow("c", 2, 60.0) is True
        assert limiter.allow("c", 2, 60.0) is True
        assert limiter.allow("c", 2, 60.0) is False

    def test_window_eviction_reallows(self):
        clock = _FakeClock()
        limiter = SlidingWindowRateLimiter(time_fn=clock)
        assert limiter.allow("c", 1, 60.0) is True
        assert limiter.allow("c", 1, 60.0) is False
        clock.advance(61.0)
        # The first hit has aged out of the trailing window → allowed again.
        assert limiter.allow("c", 1, 60.0) is True

    def test_keys_are_isolated(self):
        clock = _FakeClock()
        limiter = SlidingWindowRateLimiter(time_fn=clock)
        assert limiter.allow("a", 1, 60.0) is True
        assert limiter.allow("a", 1, 60.0) is False
        # A different client has its own independent budget.
        assert limiter.allow("b", 1, 60.0) is True

    def test_boundary_timestamp_is_evicted(self):
        clock = _FakeClock()
        limiter = SlidingWindowRateLimiter(time_fn=clock)
        assert limiter.allow("c", 1, 10.0) is True  # hit at t=0
        clock.advance(10.0)  # cutoff == 0, and t0 <= cutoff → evicted
        assert limiter.allow("c", 1, 10.0) is True


# ---------------------------------------------------------------------------
# API-key auth middleware (integration, minimal app)
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    def test_disabled_when_no_keys(self, monkeypatch):
        monkeypatch.delenv(API_KEYS_ENV, raising=False)
        client = TestClient(_build_app())
        assert client.get("/api/v1/echo").status_code == 200

    def test_rejects_missing_key(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, "secret")
        client = TestClient(_build_app())
        resp = client.get("/api/v1/echo")
        assert resp.status_code == 401
        assert "detail" in resp.json()

    def test_rejects_invalid_key(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, "secret")
        client = TestClient(_build_app())
        resp = client.get("/api/v1/echo", headers={API_KEY_HEADER: "wrong"})
        assert resp.status_code == 401

    def test_accepts_valid_x_api_key(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, "secret,other")
        client = TestClient(_build_app())
        resp = client.get("/api/v1/echo", headers={API_KEY_HEADER: "other"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_accepts_valid_bearer_token(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, "secret")
        client = TestClient(_build_app())
        resp = client.get("/api/v1/echo", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200

    def test_probe_endpoints_exempt(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, "secret")
        client = TestClient(_build_app())
        # Health is reachable without a key even when auth is enabled.
        assert client.get("/health").status_code == 200

    def test_auth_failure_logged_with_correlation_id(self, monkeypatch, access_records):
        monkeypatch.setenv(API_KEYS_ENV, "secret")
        client = TestClient(_build_app())
        resp = client.get("/api/v1/echo", headers={"X-Request-ID": "cid-auth"})
        assert resp.status_code == 401
        # The 401 response still carries the correlation header (outer middleware).
        assert resp.headers.get(CORRELATION_ID_HEADER) == "cid-auth"
        failures = [r for r in access_records if getattr(r, "status_code", None) == 401]
        assert failures
        assert failures[-1].correlation_id == "cid-auth"
        assert failures[-1].path == "/api/v1/echo"


# ---------------------------------------------------------------------------
# Rate-limit middleware (integration, injected fake clock)
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    def test_disabled_when_unset(self, monkeypatch):
        monkeypatch.delenv(RATE_LIMIT_ENV, raising=False)
        client = TestClient(_build_app())
        for _ in range(5):
            assert client.get("/api/v1/echo").status_code == 200

    def test_trips_past_threshold(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV, "2/minute")
        limiter = SlidingWindowRateLimiter(time_fn=_FakeClock())
        client = TestClient(_build_app(limiter=limiter))
        assert client.get("/api/v1/echo").status_code == 200
        assert client.get("/api/v1/echo").status_code == 200
        resp = client.get("/api/v1/echo")
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "60"

    def test_window_reset_reallows(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV, "1/minute")
        clock = _FakeClock()
        client = TestClient(_build_app(limiter=SlidingWindowRateLimiter(time_fn=clock)))
        assert client.get("/api/v1/echo").status_code == 200
        assert client.get("/api/v1/echo").status_code == 429
        clock.advance(61.0)
        assert client.get("/api/v1/echo").status_code == 200

    def test_probe_exempt_from_rate_limit(self, monkeypatch):
        monkeypatch.setenv(RATE_LIMIT_ENV, "1/minute")
        client = TestClient(_build_app(limiter=SlidingWindowRateLimiter(time_fn=_FakeClock())))
        for _ in range(5):
            assert client.get("/health").status_code == 200

    def test_rate_limit_logged_with_correlation_id(self, monkeypatch, access_records):
        monkeypatch.setenv(RATE_LIMIT_ENV, "1/minute")
        client = TestClient(_build_app(limiter=SlidingWindowRateLimiter(time_fn=_FakeClock())))
        client.get("/api/v1/echo", headers={"X-Request-ID": "cid-rl"})
        resp = client.get("/api/v1/echo", headers={"X-Request-ID": "cid-rl"})
        assert resp.status_code == 429
        blocked = [r for r in access_records if getattr(r, "status_code", None) == 429]
        assert blocked
        assert blocked[-1].correlation_id == "cid-rl"


# ---------------------------------------------------------------------------
# Real-app wiring / backward compatibility
# ---------------------------------------------------------------------------


class TestRealAppWiring:
    def test_security_middlewares_installed(self):
        installed = {m.cls for m in real_app.user_middleware}
        assert APIKeyAuthMiddleware in installed
        assert RateLimitMiddleware in installed

    def test_default_off_leaves_endpoints_open(self, monkeypatch):
        monkeypatch.delenv(API_KEYS_ENV, raising=False)
        monkeypatch.delenv(RATE_LIMIT_ENV, raising=False)
        client = TestClient(real_app)
        # No key configured → the protected pricing endpoint is reachable and
        # fails only on body validation (422), never on auth (401).
        resp = client.post("/api/v1/price", json={})
        assert resp.status_code == 422

    def test_real_app_enforces_key_when_configured(self, monkeypatch):
        monkeypatch.setenv(API_KEYS_ENV, "prod-key")
        client = TestClient(real_app)
        # Without a key → 401 before the endpoint body runs.
        assert client.post("/api/v1/price", json={}).status_code == 401
        # Health probe stays open.
        assert client.get("/health").status_code == 200
        # With the key → passes auth, reaches validation (422 on empty body).
        resp = client.post("/api/v1/price", json={}, headers={API_KEY_HEADER: "prod-key"})
        assert resp.status_code == 422

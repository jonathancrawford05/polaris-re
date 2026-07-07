"""
Tests for the API observability layer (``polaris_re/api/observability.py``).

Slice 1 of the Production Hardening & Observability epic (ROADMAP 6.2):
structured JSON access logging with correlation IDs and per-request
duration, exposed as a Starlette middleware and a JSON log formatter.

All tests are deterministic and clock-independent (per the ADR-074 guard):
durations are only asserted to be non-negative floats, never compared to a
wall-clock value, and correlation IDs are pinned via request headers wherever
an exact value is asserted.
"""

import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app
from polaris_re.api.observability import (
    ACCESS_LOGGER_NAME,
    CORRELATION_ID_HEADER,
    RESPONSE_TIME_HEADER,
    JsonLogFormatter,
    RequestContextMiddleware,
    configure_api_logging,
    correlation_id_var,
)

client = TestClient(app)


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


# ---------------------------------------------------------------------------
# Correlation-id header propagation
# ---------------------------------------------------------------------------


class TestCorrelationHeader:
    def test_generates_correlation_id_when_absent(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        cid = resp.headers.get(CORRELATION_ID_HEADER)
        assert cid
        # A generated id is a valid uuid4 hex string.
        uuid.UUID(cid)

    def test_echoes_incoming_request_id(self):
        supplied = "trace-abc-123"
        resp = client.get("/health", headers={"X-Request-ID": supplied})
        assert resp.headers.get(CORRELATION_ID_HEADER) == supplied

    def test_echoes_incoming_correlation_id_header(self):
        supplied = "corr-xyz-789"
        resp = client.get("/health", headers={"X-Correlation-ID": supplied})
        assert resp.headers.get(CORRELATION_ID_HEADER) == supplied

    def test_distinct_ids_across_requests(self):
        a = client.get("/health").headers[CORRELATION_ID_HEADER]
        b = client.get("/health").headers[CORRELATION_ID_HEADER]
        assert a != b


# ---------------------------------------------------------------------------
# Response-time header
# ---------------------------------------------------------------------------


class TestResponseTime:
    def test_response_time_header_present_and_nonnegative(self):
        resp = client.get("/health")
        raw = resp.headers.get(RESPONSE_TIME_HEADER)
        assert raw is not None
        assert float(raw) >= 0.0


# ---------------------------------------------------------------------------
# Access log record
# ---------------------------------------------------------------------------


class TestAccessLog:
    def test_access_log_emitted_with_fields(self, access_records):
        client.get("/health", headers={"X-Request-ID": "cid-1"})
        completed = [r for r in access_records if getattr(r, "path", None) == "/health"]
        assert completed
        rec = completed[-1]
        assert rec.method == "GET"
        assert rec.status_code == 200
        assert rec.correlation_id == "cid-1"
        assert isinstance(rec.duration_ms, float)
        assert rec.duration_ms >= 0.0

    def test_failing_status_recorded(self, access_records):
        # An unknown route → 404, still logged with the real status code.
        client.get("/no-such-route")
        recs = [r for r in access_records if getattr(r, "path", None) == "/no-such-route"]
        assert recs
        assert recs[-1].status_code == 404


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    def test_formats_record_as_json_with_correlation_id(self):
        formatter = JsonLogFormatter()
        record = logging.LogRecord(
            name=ACCESS_LOGGER_NAME,
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request completed",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "cid-42"
        record.method = "POST"
        record.status_code = 201
        record.duration_ms = 12.5
        out = json.loads(formatter.format(record))
        assert out["message"] == "request completed"
        assert out["level"] == "INFO"
        assert out["logger"] == ACCESS_LOGGER_NAME
        assert out["correlation_id"] == "cid-42"
        assert out["method"] == "POST"
        assert out["status_code"] == 201
        assert out["duration_ms"] == 12.5

    def test_formatter_omits_correlation_when_unset(self):
        formatter = JsonLogFormatter()
        record = logging.LogRecord(
            name="polaris_re.api",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        out = json.loads(formatter.format(record))
        assert "correlation_id" not in out
        assert out["message"] == "hello"

    def test_formatter_uses_context_var_fallback(self):
        formatter = JsonLogFormatter()
        token = correlation_id_var.set("ctx-cid")
        try:
            record = logging.LogRecord(
                name="polaris_re.api",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="hi",
                args=(),
                exc_info=None,
            )
            out = json.loads(formatter.format(record))
            assert out["correlation_id"] == "ctx-cid"
        finally:
            correlation_id_var.reset(token)


# ---------------------------------------------------------------------------
# Configuration + wiring
# ---------------------------------------------------------------------------


class TestConfigure:
    def test_configure_is_idempotent(self):
        logger = configure_api_logging()
        first = sum(isinstance(h.formatter, JsonLogFormatter) for h in logger.handlers)
        configure_api_logging()
        second = sum(isinstance(h.formatter, JsonLogFormatter) for h in logger.handlers)
        assert first == second == 1
        assert logger.propagate is False

    def test_middleware_installed_on_app(self):
        assert any(m.cls is RequestContextMiddleware for m in app.user_middleware)

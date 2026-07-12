"""
Tests for the Prometheus metrics surface (``polaris_re/api/metrics.py``).

Slice 3 of the Production Hardening & Observability epic (ROADMAP 6.2): a
dependency-free ``/metrics`` endpoint in Prometheus text-exposition format
(v0.0.4), fed by a request-counting + latency-histogram middleware.

All tests are deterministic and clock-independent (ADR-074 guard): durations are
either observed directly into a registry or produced by real (non-negative)
request handling, and are only ever asserted non-negative / cumulative — never
compared to a wall-clock value.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_re.api.auth import API_KEY_HEADER, API_KEYS_ENV
from polaris_re.api.main import app as real_app
from polaris_re.api.metrics import (
    DEFAULT_BUCKETS,
    METRICS_CONTENT_TYPE,
    UNMATCHED_PATH_LABEL,
    MetricsMiddleware,
    MetricsRegistry,
    render_latest,
)

# ---------------------------------------------------------------------------
# MetricsRegistry — unit
# ---------------------------------------------------------------------------


def test_counter_increments_per_method_path_status() -> None:
    reg = MetricsRegistry()
    reg.observe("POST", "/api/v1/price", 200, 0.01)
    reg.observe("POST", "/api/v1/price", 200, 0.02)
    reg.observe("POST", "/api/v1/price", 422, 0.001)
    text = reg.render()
    assert 'polaris_http_requests_total{method="POST",path="/api/v1/price",status="200"} 2' in text
    assert 'polaris_http_requests_total{method="POST",path="/api/v1/price",status="422"} 1' in text


def test_histogram_buckets_are_cumulative() -> None:
    reg = MetricsRegistry()
    # 0.03s falls in the 0.05 bucket and every larger bucket, but not 0.025.
    reg.observe("GET", "/health", 200, 0.03)
    text = reg.render()
    line_025 = (
        'polaris_http_request_duration_seconds_bucket{method="GET",path="/health",le="0.025"} 0'
    )
    line_05 = (
        'polaris_http_request_duration_seconds_bucket{method="GET",path="/health",le="0.05"} 1'
    )
    line_inf = (
        'polaris_http_request_duration_seconds_bucket{method="GET",path="/health",le="+Inf"} 1'
    )
    assert line_025 in text
    assert line_05 in text
    assert line_inf in text
    assert 'polaris_http_request_duration_seconds_count{method="GET",path="/health"} 1' in text


def test_histogram_sum_accumulates() -> None:
    reg = MetricsRegistry()
    reg.observe("GET", "/health", 200, 0.1)
    reg.observe("GET", "/health", 200, 0.2)
    text = reg.render()
    # sum = 0.3 (rendered without a stale trailing count series colliding)
    sum_lines = [
        ln
        for ln in text.splitlines()
        if ln.startswith('polaris_http_request_duration_seconds_sum{method="GET",path="/health"}')
    ]
    assert len(sum_lines) == 1
    assert float(sum_lines[0].rsplit(" ", 1)[1]) == pytest.approx(0.3)


def test_negative_duration_is_clamped_to_zero() -> None:
    # A monotonic clock never goes backwards, but guard the histogram anyway so
    # a clock quirk cannot produce a negative observation.
    reg = MetricsRegistry()
    reg.observe("GET", "/health", 200, -1.0)
    text = reg.render()
    # Clamped to 0.0 → falls in the smallest bucket.
    smallest = f'le="{DEFAULT_BUCKETS[0]}"'
    bucket_line = next(
        ln for ln in text.splitlines() if "_bucket" in ln and "/health" in ln and smallest in ln
    )
    assert bucket_line.rsplit(" ", 1)[1] == "1"


def test_label_values_are_escaped() -> None:
    reg = MetricsRegistry()
    reg.observe('GET"x', "/a\\b", 200, 0.0)
    text = reg.render()
    assert 'method="GET\\"x"' in text
    assert 'path="/a\\\\b"' in text


def test_render_ends_with_newline() -> None:
    reg = MetricsRegistry()
    reg.observe("GET", "/health", 200, 0.0)
    assert reg.render().endswith("\n")


# ---------------------------------------------------------------------------
# MetricsMiddleware — integration on a minimal app
# ---------------------------------------------------------------------------


def _app_with_metrics(registry: MetricsRegistry) -> FastAPI:
    app = FastAPI()
    app.add_middleware(MetricsMiddleware, registry=registry)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    return app


def test_middleware_records_matched_route_template() -> None:
    reg = MetricsRegistry()
    client = TestClient(_app_with_metrics(reg))
    client.get("/ping")
    client.get("/ping")
    text = reg.render()
    assert 'polaris_http_requests_total{method="GET",path="/ping",status="200"} 2' in text


def test_middleware_collapses_unmatched_paths() -> None:
    reg = MetricsRegistry()
    client = TestClient(_app_with_metrics(reg))
    # Two distinct never-routed URLs must NOT create two path labels.
    client.get("/does-not-exist-a")
    client.get("/does-not-exist-b")
    text = reg.render()
    assert (
        f'polaris_http_requests_total{{method="GET",path="{UNMATCHED_PATH_LABEL}",status="404"}} 2'
        in text
    )
    assert "does-not-exist-a" not in text
    assert "does-not-exist-b" not in text


# ---------------------------------------------------------------------------
# /metrics endpoint — real app wiring
# ---------------------------------------------------------------------------


def test_metrics_endpoint_exposes_prometheus_format() -> None:
    client = TestClient(real_app)
    # Generate at least one request so a series exists.
    client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == METRICS_CONTENT_TYPE
    body = resp.text
    assert "# TYPE polaris_http_requests_total counter" in body
    assert "# TYPE polaris_http_request_duration_seconds histogram" in body


def test_metrics_endpoint_exempt_from_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    # With keys configured, a protected endpoint needs a key but /metrics does not.
    monkeypatch.setenv(API_KEYS_ENV, "secret-key")
    client = TestClient(real_app)
    assert client.get("/metrics").status_code == 200
    # Sanity: a protected endpoint is still gated (missing key -> 401).
    assert client.post("/api/v1/price", json={}).status_code == 401
    # ...and passes auth (then 422 on the empty body) with the key present.
    assert (
        client.post("/api/v1/price", json={}, headers={API_KEY_HEADER: "secret-key"}).status_code
        == 422
    )


def test_render_latest_defaults_to_process_registry() -> None:
    # Smoke: the module-level default registry renders without error and carries
    # the metric preamble.
    text = render_latest()
    assert "polaris_http_requests_total" in text

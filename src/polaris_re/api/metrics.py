"""
Prometheus metrics for the Polaris RE REST API.

Slice 3 of the Production Hardening & Observability epic (ROADMAP 6.2). Exposes
a ``/metrics`` endpoint in the Prometheus text-exposition format (v0.0.4) so an
ops team can point a Prometheus scraper (and a Grafana dashboard) at the service
without any code changes.

Design notes:
    - **Dependency-free.** Consistent with Slices 1-2 (observability + security),
      this module uses only the standard library — no ``prometheus-client``. It
      hand-renders the text-exposition format, keeping the ``api`` extra
      installable with no new runtime dependency (ADR-135).
    - **Bounded label cardinality.** The ``path`` label is the *matched route
      template* (e.g. ``/api/v1/price``), never the raw request path. Requests
      that never reach the router — a 404, or a 401/429 short-circuit from the
      security middlewares — collapse to a single ``__unmatched__`` label so an
      attacker spraying random URLs cannot explode the metric's cardinality.
    - **Clock-safe.** Durations use ``time.perf_counter`` (monotonic); the
      histogram only ever accumulates non-negative observations. No test reads
      the wall clock (ADR-074 guard).
    - **Thread-safe.** A single process-wide :class:`MetricsRegistry` is mutated
      under a lock, so concurrent worker threads (uvicorn's threadpool) record
      cleanly.
"""

import threading
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

__all__ = [
    "DEFAULT_BUCKETS",
    "METRICS_CONTENT_TYPE",
    "METRICS_PATH",
    "REGISTRY",
    "UNMATCHED_PATH_LABEL",
    "MetricsMiddleware",
    "MetricsRegistry",
    "render_latest",
]

# The endpoint a Prometheus server scrapes.
METRICS_PATH = "/metrics"

# Content type for Prometheus text exposition format version 0.0.4.
METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Label used when a request never matches a route (404) or is short-circuited by
# a security middleware (401/429) before routing — keeps cardinality bounded.
UNMATCHED_PATH_LABEL = "__unmatched__"

# Default histogram buckets (seconds), matching Prometheus client conventions.
DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_REQUESTS_METRIC = "polaris_http_requests_total"
_DURATION_METRIC = "polaris_http_request_duration_seconds"


def _escape_label_value(value: str) -> str:
    """Escape a label value per the Prometheus text-exposition spec."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(method: str, path: str, status: str | None = None) -> str:
    """Render a sorted, escaped ``{k="v",...}`` label block (empty if no labels)."""
    pairs = [("method", method), ("path", path)]
    if status is not None:
        pairs.append(("status", status))
    body = ",".join(f'{key}="{_escape_label_value(val)}"' for key, val in pairs)
    return "{" + body + "}"


class MetricsRegistry:
    """In-process accumulator for request counts and latency histograms.

    Keyed by ``(method, path_template)``. ``path_template`` is the matched route
    path (or :data:`UNMATCHED_PATH_LABEL`), so cardinality is bounded by the set
    of declared routes rather than by arbitrary request URLs.
    """

    def __init__(self, buckets: tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        # Buckets are stored sorted; a synthetic ``+Inf`` bucket is emitted at
        # render time (it always equals the total count).
        self._buckets: tuple[float, ...] = tuple(sorted(buckets))
        self._lock = threading.Lock()
        # (method, path, status) -> count
        self._request_counts: dict[tuple[str, str, str], int] = {}
        # (method, path) -> per-bucket cumulative counts (aligned with _buckets)
        self._hist_buckets: dict[tuple[str, str], list[int]] = {}
        # (method, path) -> (sum_seconds, count)
        self._hist_totals: dict[tuple[str, str], list[float]] = {}

    def observe(self, method: str, path: str, status: int, duration_seconds: float) -> None:
        """Record one handled request: bump its counter and histogram."""
        duration_seconds = max(0.0, duration_seconds)
        with self._lock:
            count_key = (method, path, str(status))
            self._request_counts[count_key] = self._request_counts.get(count_key, 0) + 1

            hist_key = (method, path)
            buckets = self._hist_buckets.get(hist_key)
            if buckets is None:
                buckets = [0] * len(self._buckets)
                self._hist_buckets[hist_key] = buckets
                self._hist_totals[hist_key] = [0.0, 0.0]
            for i, upper in enumerate(self._buckets):
                if duration_seconds <= upper:
                    buckets[i] += 1
            totals = self._hist_totals[hist_key]
            totals[0] += duration_seconds
            totals[1] += 1.0

    def render(self) -> str:
        """Render the current state as Prometheus text exposition (v0.0.4)."""
        lines: list[str] = []
        with self._lock:
            request_counts = dict(self._request_counts)
            hist_buckets = {k: list(v) for k, v in self._hist_buckets.items()}
            hist_totals = {k: list(v) for k, v in self._hist_totals.items()}

        lines.append(f"# HELP {_REQUESTS_METRIC} Total HTTP requests processed by the API.")
        lines.append(f"# TYPE {_REQUESTS_METRIC} counter")
        for (method, path, status), count in sorted(request_counts.items()):
            lines.append(f"{_REQUESTS_METRIC}{_labels(method, path, status)} {count}")

        lines.append(f"# HELP {_DURATION_METRIC} HTTP request latency in seconds.")
        lines.append(f"# TYPE {_DURATION_METRIC} histogram")
        for (method, path), buckets in sorted(hist_buckets.items()):
            total_sum, total_count = hist_totals[(method, path)]
            # observe() increments every bucket whose upper bound the
            # observation satisfies, so each stored bucket count is already
            # cumulative (Prometheus histogram semantics) — emit it directly.
            for i, upper in enumerate(self._buckets):
                le = _format_float(upper)
                lines.append(
                    f"{_DURATION_METRIC}_bucket"
                    f'{{method="{_escape_label_value(method)}",'
                    f'path="{_escape_label_value(path)}",le="{le}"}} {buckets[i]}'
                )
            inf_count = int(total_count)
            lines.append(
                f"{_DURATION_METRIC}_bucket"
                f'{{method="{_escape_label_value(method)}",'
                f'path="{_escape_label_value(path)}",le="+Inf"}} {inf_count}'
            )
            lines.append(
                f"{_DURATION_METRIC}_sum{_labels(method, path)} {_format_float(total_sum)}"
            )
            lines.append(f"{_DURATION_METRIC}_count{_labels(method, path)} {inf_count}")

        return "\n".join(lines) + "\n"


def _format_float(value: float) -> str:
    """Render a float for Prometheus exposition without spurious precision."""
    if value == int(value):
        return str(int(value))
    return repr(value)


# Process-wide default registry the middleware writes to and the ``/metrics``
# endpoint reads from. Tests may construct their own registry and pass it to a
# fresh middleware to isolate state.
REGISTRY = MetricsRegistry()


def _path_label(request: Request) -> str:
    """Matched route template for ``request``, or :data:`UNMATCHED_PATH_LABEL`.

    Using the route template (populated by Starlette's router during
    ``call_next``) rather than ``request.url.path`` keeps the ``path`` label
    bounded to the declared route set. A request that never routes (404, or a
    401/429 short-circuit from a security middleware) has no route in scope and
    collapses to a single ``__unmatched__`` label.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return UNMATCHED_PATH_LABEL


def render_latest(registry: MetricsRegistry = REGISTRY) -> str:
    """Render ``registry`` (defaults to the process-wide one) for ``/metrics``."""
    return registry.render()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and latency for every request into a registry.

    Placed *inside* ``RequestContextMiddleware`` but *outside* the security
    middlewares, so 401/429 rejections are still counted (they collapse to the
    ``__unmatched__`` path label because they never reach the router).
    """

    def __init__(self, app: ASGIApp, registry: MetricsRegistry | None = None) -> None:
        super().__init__(app)
        self._registry = registry if registry is not None else REGISTRY

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = time.perf_counter() - start
            self._registry.observe(
                request.method,
                _path_label(request),
                status_code,
                duration_seconds,
            )

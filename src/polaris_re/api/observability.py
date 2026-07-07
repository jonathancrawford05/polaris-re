"""
Observability primitives for the Polaris RE REST API.

Slice 1 of the Production Hardening & Observability epic (ROADMAP 6.2). Adds:

- ``JsonLogFormatter`` — renders each log record as a single-line JSON object
  (timestamp, level, logger, message, correlation id, and any structured
  ``extra`` fields), so logs are machine-parseable by an aggregator.
- ``RequestContextMiddleware`` — assigns a **correlation id** to every request
  (echoing an inbound ``X-Request-ID`` / ``X-Correlation-ID`` header, otherwise
  generating a uuid4), times the request on a monotonic clock, emits a
  structured access-log record, and returns the correlation id and duration to
  the caller as response headers.
- ``configure_api_logging`` — idempotently attaches the JSON handler to a
  dedicated, non-propagating access logger.

Design notes:
    - The middleware is dependency-free (standard-library ``logging`` +
      ``uuid`` only); OpenTelemetry / Prometheus wiring is a later slice.
    - Durations use ``time.perf_counter`` (monotonic), never the wall clock,
      and are reported in milliseconds. Tests assert only non-negativity.
    - The correlation id is also published on a ``ContextVar`` so any engine
      log emitted while handling the request can be stamped with it; the JSON
      formatter falls back to that context var when a record carries no
      explicit ``correlation_id``.
"""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

__all__ = [
    "ACCESS_LOGGER_NAME",
    "CORRELATION_ID_HEADER",
    "REQUEST_ID_HEADERS",
    "RESPONSE_TIME_HEADER",
    "JsonLogFormatter",
    "RequestContextMiddleware",
    "configure_api_logging",
    "correlation_id_var",
]

# Inbound headers a client may set to propagate its own trace id (first match
# wins); the canonical name is echoed back on the response.
REQUEST_ID_HEADERS: tuple[str, ...] = ("X-Request-ID", "X-Correlation-ID")
CORRELATION_ID_HEADER = "X-Correlation-ID"
RESPONSE_TIME_HEADER = "X-Response-Time-Ms"

ACCESS_LOGGER_NAME = "polaris_re.api.access"

# Sentinel for "no correlation id in scope" — distinguishes an unset context
# from a legitimately empty id.
_UNSET = "-"

correlation_id_var: ContextVar[str] = ContextVar("polaris_correlation_id", default=_UNSET)

# LogRecord attributes that are intrinsic to the record and must not be treated
# as user-supplied structured ``extra`` fields when serialising.
_RESERVED_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "correlation_id",
}


class JsonLogFormatter(logging.Formatter):
    """Render a :class:`logging.LogRecord` as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = getattr(record, "correlation_id", None) or correlation_id_var.get()
        if correlation_id and correlation_id != _UNSET:
            payload["correlation_id"] = correlation_id

        # Merge structured extras (fields attached via ``logger.info(..., extra=)``)
        # without clobbering the intrinsic keys above.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_api_logging(level: int = logging.INFO) -> logging.Logger:
    """Attach the JSON handler to the access logger, idempotently.

    Safe to call multiple times (e.g. once at import and again from a test):
    a JSON handler is added only if the logger does not already carry one. The
    access logger does **not** propagate to the root logger, so JSON access
    lines never double up with the application's own handlers.
    """
    logger = logging.getLogger(ACCESS_LOGGER_NAME)
    if not any(isinstance(h.formatter, JsonLogFormatter) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def _incoming_correlation_id(request: Request) -> str | None:
    """Return the first non-empty inbound trace-id header, if any."""
    for header in REQUEST_ID_HEADERS:
        value = request.headers.get(header)
        if value:
            return value
    return None


def _access_fields(
    request: Request,
    status_code: int,
    duration_ms: float,
    correlation_id: str,
) -> dict[str, object]:
    """Structured fields describing one handled request."""
    return {
        "correlation_id": correlation_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 3),
        "client": request.client.host if request.client else None,
    }


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a correlation id, time the request, and emit a JSON access log."""

    def __init__(self, app: ASGIApp, logger: logging.Logger | None = None) -> None:
        super().__init__(app)
        self._logger = logger or logging.getLogger(ACCESS_LOGGER_NAME)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = _incoming_correlation_id(request) or uuid.uuid4().hex
        token = correlation_id_var.set(correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self._logger.exception(
                "request failed",
                extra=_access_fields(request, 500, duration_ms, correlation_id),
            )
            raise
        finally:
            correlation_id_var.reset(token)

        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        response.headers[RESPONSE_TIME_HEADER] = f"{duration_ms:.3f}"
        # The context var was already reset in the ``finally`` above, so the
        # correlation id is passed explicitly via ``extra`` here — do not rely on
        # the ``correlation_id_var`` fallback for this record, which would render
        # the ``_UNSET`` sentinel ("-") at this point.
        self._logger.info(
            "request completed",
            extra=_access_fields(request, response.status_code, duration_ms, correlation_id),
        )
        return response

"""
Optional API security for the Polaris RE REST API.

Slice 2 of the Production Hardening & Observability epic (ROADMAP 6.2). Adds two
**default-off** middlewares that wrap the existing app without touching the
pricing path:

- ``APIKeyAuthMiddleware`` — when a non-empty key set is configured (from the
  ``POLARIS_API_KEYS`` environment variable, comma-separated), every request to
  a protected endpoint must present a matching key via the ``X-API-Key`` header
  or an ``Authorization: Bearer <key>`` header. A missing or invalid key returns
  ``401`` with a JSON ``detail`` body and a correlation-stamped access-log
  record. When no keys are configured the middleware is a pure pass-through, so
  the API behaves exactly as it did before this slice.
- ``RateLimitMiddleware`` — when ``POLARIS_API_RATE_LIMIT`` is configured (e.g.
  ``"100/minute"``), requests from a single client past the threshold within the
  rolling window return ``429``. When unset the middleware is a pure
  pass-through. The per-client key is the resolved client IP: behind an ingress
  the immediate peer is the proxy, so ``X-Forwarded-For`` is consulted — but
  only when the peer is a configured **trusted proxy** (``POLARIS_TRUSTED_PROXIES``),
  since the header is otherwise spoofable (Slice 3, ADR-135). With no trusted
  proxies configured the immediate peer address is used, unchanged.

Design notes:
    - **Dependency-free.** Consistent with Slice 1's observability core, both
      middlewares use only the standard library. The rate limiter is a
      hand-rolled sliding-window log rather than pulling in ``slowapi`` (see
      ADR-134): it keeps the ``api`` extra installing with no new runtime
      dependency and, because its clock is injectable, is deterministically
      testable without reading the wall clock (ADR-074 guard).
    - **Default-off / backward-compatible.** Configuration is read from the
      environment on **each** request, so an unset environment is a no-op and
      the pre-existing API tests pass unchanged. This mirrors the modeling
      epics' "default values preserve behaviour" pattern.
    - **Correlation-aware.** Both middlewares run *inside* the
      ``RequestContextMiddleware`` (Slice 1), so a rejection is logged with the
      request's correlation id via the shared ``correlation_id_var`` and the
      ``401``/``429`` response still carries the ``X-Correlation-ID`` header.
    - **Probes stay open.** Liveness/readiness and the API docs
      (``/health``, ``/version``, ``/docs``, ``/redoc``, ``/openapi.json``) are
      exempt from both auth and rate limiting so orchestrators and browsers can
      always reach them.
"""

import hmac
import ipaddress
import logging
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from polaris_re.api.observability import ACCESS_LOGGER_NAME, correlation_id_var

__all__ = [
    "API_KEYS_ENV",
    "API_KEY_HEADER",
    "AUTHORIZATION_HEADER",
    "EXEMPT_PATHS",
    "FORWARDED_FOR_HEADER",
    "RATE_LIMIT_ENV",
    "TRUSTED_PROXIES_ENV",
    "APIKeyAuthMiddleware",
    "RateLimitMiddleware",
    "SlidingWindowRateLimiter",
    "client_ip",
    "configured_api_keys",
    "configured_rate_limit",
    "configured_trusted_proxies",
]

# Header names a client may use to present its API key.
API_KEY_HEADER = "X-API-Key"
AUTHORIZATION_HEADER = "Authorization"
_BEARER_PREFIX = "bearer "

# Standard proxy header carrying the original client chain (left-most = client).
FORWARDED_FOR_HEADER = "X-Forwarded-For"

# Environment variables that drive the (default-off) security surfaces.
API_KEYS_ENV = "POLARIS_API_KEYS"
RATE_LIMIT_ENV = "POLARIS_API_RATE_LIMIT"
TRUSTED_PROXIES_ENV = "POLARIS_TRUSTED_PROXIES"

# Endpoints that must stay reachable without a key and without being throttled:
# orchestrator probes, the interactive API documentation, and the Prometheus
# metrics scrape target (a scraper cannot present a key).
EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/health", "/version", "/metrics", "/docs", "/redoc", "/openapi.json"}
)

# Rolling-window period aliases → seconds.
_PERIOD_SECONDS: dict[str, float] = {
    "second": 1.0,
    "sec": 1.0,
    "s": 1.0,
    "minute": 60.0,
    "min": 60.0,
    "m": 60.0,
    "hour": 3600.0,
    "hr": 3600.0,
    "h": 3600.0,
}


def configured_api_keys() -> frozenset[str]:
    """Return the currently configured API keys, read from the environment.

    ``POLARIS_API_KEYS`` is a comma-separated list; surrounding whitespace and
    empty entries are ignored. An unset or blank variable yields an empty set,
    which the auth middleware treats as "authentication disabled".
    """
    raw = os.environ.get(API_KEYS_ENV, "")
    return frozenset(key.strip() for key in raw.split(",") if key.strip())


def configured_rate_limit() -> tuple[int, float] | None:
    """Return ``(max_requests, window_seconds)`` from the environment, or ``None``.

    ``POLARIS_API_RATE_LIMIT`` accepts ``"<count>/<period>"`` (e.g.
    ``"100/minute"``) or a bare ``"<count>"`` (interpreted as per-minute).
    Period aliases: ``second``/``sec``/``s``, ``minute``/``min``/``m``,
    ``hour``/``hr``/``h``. An unset, blank, or malformed value yields ``None``
    (rate limiting disabled).
    """
    raw = os.environ.get(RATE_LIMIT_ENV, "").strip()
    if not raw:
        return None
    count_part, _, period_part = raw.partition("/")
    try:
        count = int(count_part.strip())
    except ValueError:
        return None
    if count <= 0:
        return None
    period_key = period_part.strip().lower() or "minute"
    window = _PERIOD_SECONDS.get(period_key)
    if window is None:
        return None
    return count, window


@dataclass
class SlidingWindowRateLimiter:
    """A per-key sliding-window request-log rate limiter.

    ``allow(key, max_requests, window_seconds)`` records a hit and reports
    whether the key is within its limit over the trailing ``window_seconds``.
    The clock is injectable (``time_fn``) so tests can advance time
    deterministically without touching the wall clock (ADR-074 guard); it
    defaults to :func:`time.monotonic`, which never runs backwards.

    State is kept in-process (one deque of hit-timestamps per key). This is
    correct for a single replica; a multi-replica deployment would swap in a
    shared backend (noted as a follow-up).
    """

    time_fn: Callable[[], float] = time.monotonic
    _hits: dict[str, deque[float]] = field(default_factory=dict)

    def allow(self, key: str, max_requests: int, window_seconds: float) -> bool:
        """Record a request for ``key`` and return ``True`` if within the limit."""
        now = self.time_fn()
        cutoff = now - window_seconds
        bucket = self._hits.get(key)
        if bucket is None:
            bucket = deque()
            self._hits[key] = bucket
        # Drop timestamps that have aged out of the trailing window.
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
        return True


def configured_trusted_proxies() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Return the trusted-proxy networks from the environment, or an empty tuple.

    ``POLARIS_TRUSTED_PROXIES`` is a comma-separated list of IP addresses or
    CIDR ranges (e.g. ``"10.0.0.0/8, 192.168.1.5"``). A bare address is treated
    as a /32 (or /128) network. Unparseable entries are ignored. When empty
    (the default), ``X-Forwarded-For`` is never trusted and the immediate peer
    address is used for rate-limit keying — the pre-Slice-3 behaviour.
    """
    raw = os.environ.get(TRUSTED_PROXIES_ENV, "")
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in raw.split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            # Silently skip malformed entries — a bad config line must not open
            # the trust boundary or crash the request path.
            continue
    return tuple(networks)


def _ip_in_networks(
    address: str,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    """True if ``address`` parses and falls within any of ``networks``."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def client_ip(
    request: Request,
    trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] | None = None,
) -> str:
    """Resolve the originating client IP, honouring ``X-Forwarded-For`` safely.

    ``X-Forwarded-For`` is client-supplied and therefore spoofable, so it is
    only consulted when the immediate peer is itself a **trusted proxy** (an
    entry in ``POLARIS_TRUSTED_PROXIES``). In that case the client is the
    right-most address in the forwarded chain that is *not* itself a trusted
    proxy — the first hop the trusted infrastructure actually saw. When no
    proxies are trusted (the default), or the peer is untrusted, or the header
    is absent/empty, the immediate peer address is returned unchanged.
    """
    peer = request.client.host if request.client else "unknown"
    networks = configured_trusted_proxies() if trusted_proxies is None else trusted_proxies
    if not networks or not _ip_in_networks(peer, networks):
        return peer

    forwarded = request.headers.get(FORWARDED_FOR_HEADER, "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    # Walk right-to-left, skipping trusted-proxy hops; the first untrusted hop
    # is the real client. If every hop is trusted (or none parse), fall back to
    # the peer address.
    for hop in reversed(hops):
        if not _ip_in_networks(hop, networks):
            return hop
    return peer


def _client_key(request: Request) -> str:
    """Rate-limit / audit key for a request — the resolved client IP."""
    return client_ip(request)


def _presented_key(request: Request) -> str | None:
    """Extract the API key a request presents, if any.

    Prefers the explicit ``X-API-Key`` header; otherwise accepts an
    ``Authorization: Bearer <key>`` header (case-insensitive scheme).
    """
    header_key = request.headers.get(API_KEY_HEADER)
    if header_key:
        return header_key.strip()
    authorization = request.headers.get(AUTHORIZATION_HEADER, "")
    if authorization.lower().startswith(_BEARER_PREFIX):
        candidate = authorization[len(_BEARER_PREFIX) :].strip()
        if candidate:
            return candidate
    return None


def _key_is_valid(presented: str, keys: frozenset[str]) -> bool:
    """Constant-time membership test for the presented key.

    Uses :func:`hmac.compare_digest` per candidate rather than a plain
    ``presented in keys`` so a timing side-channel cannot reveal how many
    leading bytes of a configured key were guessed correctly. (The *number* of
    configured keys can still be inferred from timing, but the key contents —
    the material secret — cannot.)
    """
    return any(hmac.compare_digest(presented, key) for key in keys)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Require a valid API key when keys are configured; otherwise pass through."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        exempt_paths: frozenset[str] = EXEMPT_PATHS,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(app)
        self._exempt = exempt_paths
        self._logger = logger or logging.getLogger(ACCESS_LOGGER_NAME)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        keys = configured_api_keys()
        if not keys or request.url.path in self._exempt:
            return await call_next(request)

        presented = _presented_key(request)
        if presented is None or not _key_is_valid(presented, keys):
            reason = "missing API key" if presented is None else "invalid API key"
            self._logger.warning(
                "authentication failed",
                extra={
                    "correlation_id": correlation_id_var.get(),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 401,
                    "client": _client_key(request),
                    "reason": reason,
                },
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
                headers={"WWW-Authenticate": API_KEY_HEADER},
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Throttle a client past the configured threshold; otherwise pass through."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: SlidingWindowRateLimiter | None = None,
        exempt_paths: frozenset[str] = EXEMPT_PATHS,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(app)
        # A single limiter instance persists hit-history across requests; the
        # threshold itself is re-read from the environment each request so the
        # feature stays default-off and reconfigurable without an app rebuild.
        self._limiter = limiter if limiter is not None else SlidingWindowRateLimiter()
        self._exempt = exempt_paths
        self._logger = logger or logging.getLogger(ACCESS_LOGGER_NAME)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        limit = configured_rate_limit()
        if limit is None or request.url.path in self._exempt:
            return await call_next(request)

        max_requests, window_seconds = limit
        key = _client_key(request)
        if not self._limiter.allow(key, max_requests, window_seconds):
            self._logger.warning(
                "rate limit exceeded",
                extra={
                    "correlation_id": correlation_id_var.get(),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 429,
                    "client": key,
                    "limit": f"{max_requests}/{window_seconds:g}s",
                },
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(int(window_seconds))},
            )
        return await call_next(request)

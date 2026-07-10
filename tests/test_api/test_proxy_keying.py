"""
Tests for proxy-aware client-IP resolution (``polaris_re/api/auth.py``).

Slice 3 of the Production Hardening & Observability epic (ROADMAP 6.2), closing
the PR #134 review [P2]: behind an ingress the rate limiter must key on the real
client, not the proxy IP — but ``X-Forwarded-For`` is spoofable, so it is only
trusted when the immediate peer is a configured trusted proxy
(``POLARIS_TRUSTED_PROXIES``). Default (no trusted proxies) preserves the
pre-Slice-3 behaviour of keying on the immediate peer.

``client_ip`` is exercised directly against synthetic requests so the peer
address is controllable (the TestClient always reports ``testclient`` as the
peer). Deterministic and clock-independent (ADR-074 guard).
"""

import pytest
from starlette.requests import Request

from polaris_re.api.auth import (
    TRUSTED_PROXIES_ENV,
    client_ip,
    configured_trusted_proxies,
)


def _request(peer: str | None, xff: str | None = None) -> Request:
    """Build a minimal HTTP request with a given peer and optional XFF header."""
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/price",
        "query_string": b"",
        "headers": headers,
        "client": (peer, 4321) if peer is not None else None,
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# configured_trusted_proxies
# ---------------------------------------------------------------------------


def test_trusted_proxies_unset_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TRUSTED_PROXIES_ENV, raising=False)
    assert configured_trusted_proxies() == ()


def test_trusted_proxies_parses_ip_and_cidr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8, 192.168.1.5 , bad-entry")
    networks = configured_trusted_proxies()
    # Two valid entries; the malformed one is skipped, not fatal.
    assert len(networks) == 2
    rendered = {str(n) for n in networks}
    assert "10.0.0.0/8" in rendered
    assert "192.168.1.5/32" in rendered


# ---------------------------------------------------------------------------
# client_ip — trust boundary
# ---------------------------------------------------------------------------


def test_default_uses_peer_and_ignores_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TRUSTED_PROXIES_ENV, raising=False)
    req = _request(peer="203.0.113.7", xff="9.9.9.9")
    # No trusted proxies: XFF must be ignored even when present (anti-spoof).
    assert client_ip(req) == "203.0.113.7"


def test_untrusted_peer_ignores_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8")
    req = _request(peer="203.0.113.7", xff="9.9.9.9")
    # Peer is not in the trusted range → XFF is not honoured.
    assert client_ip(req) == "203.0.113.7"


def test_trusted_peer_resolves_client_from_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8")
    req = _request(peer="10.1.2.3", xff="198.51.100.23")
    assert client_ip(req) == "198.51.100.23"


def test_trusted_peer_skips_trusted_hops_in_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8")
    # Chain: real client -> edge (untrusted-looking public) -> internal proxies.
    # Right-most non-trusted hop is the real first hop the trusted infra saw.
    req = _request(peer="10.0.0.9", xff="198.51.100.23, 10.9.9.9, 10.0.0.9")
    assert client_ip(req) == "198.51.100.23"


def test_trusted_peer_all_hops_trusted_falls_back_to_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8")
    req = _request(peer="10.0.0.9", xff="10.1.1.1, 10.2.2.2")
    # Every hop is trusted infrastructure → no external client to attribute.
    assert client_ip(req) == "10.0.0.9"


def test_trusted_peer_without_xff_uses_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8")
    req = _request(peer="10.0.0.9", xff=None)
    assert client_ip(req) == "10.0.0.9"


def test_missing_client_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8")
    req = _request(peer=None, xff="9.9.9.9")
    assert client_ip(req) == "unknown"


def test_explicit_trusted_proxies_argument_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Passing networks explicitly bypasses the environment read entirely.
    monkeypatch.setenv(TRUSTED_PROXIES_ENV, "10.0.0.0/8")
    req = _request(peer="10.0.0.9", xff="198.51.100.23")
    # An empty explicit tuple means "trust nobody" → peer wins despite env.
    assert client_ip(req, trusted_proxies=()) == "10.0.0.9"

"""Boot the real deployed entry points and smoke-test them end to end.

These tests are deliberately *not* run in the fast unit matrix (``make test``
excludes ``slow``): they spawn a real ``uvicorn`` server and shell out to the
``polaris`` console script, which is heavier than an in-process test. A
dedicated CI ``smoke`` job selects them with ``-m smoke`` (well inside a ~30s
budget) so a broken boot / crashing entry point gates the merge.

Every subprocess is bounded by an explicit timeout and torn down in a fixture,
and every date in the price payload is pinned (ADR-074) — nothing here touches
the wall clock.
"""

import json
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.slow]

# Repo root: tests/smoke/test_smoke_entrypoints.py -> ../../
REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_INFORCE = REPO_ROOT / "data" / "qa" / "golden_inforce.csv"
GOLDEN_CONFIG = REPO_ROOT / "data" / "qa" / "golden_config_flat.json"

# How long a real uvicorn boot may take before we call it a failure, and how
# long each CLI entry point may run.
_BOOT_TIMEOUT_S = 30.0
_CLI_TIMEOUT_S = 180.0

# A single pinned policy — the real /api/v1/price request body (dates fixed per
# ADR-074, no wall-clock dependency).
_SMOKE_POLICY = {
    "policy_id": "SMOKE001",
    "issue_age": 40,
    "attained_age": 40,
    "sex": "M",
    "smoker": False,
    "underwriting_class": "PREFERRED",
    "face_amount": 500_000.0,
    "annual_premium": 1_200.0,
    "policy_term": 20,
    "duration_inforce": 0,
    "issue_date": "2025-01-01",
    "valuation_date": "2025-01-01",
}
_SMOKE_PRICE_REQUEST = {
    "policies": [_SMOKE_POLICY],
    "projection_horizon_years": 20,
    "discount_rate": 0.06,
    "hurdle_rate": 0.10,
    "cession_pct": 0.90,
}


def _free_port() -> int:
    """Reserve an ephemeral TCP port and hand back its number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _polaris_cli_argv() -> list[str]:
    """The real ``polaris`` CLI entry point as a subprocess argv prefix.

    Runs the console-script module through the current interpreter
    (``python -m polaris_re.cli``) so the test uses the same environment the
    suite runs under, independent of whether ``polaris`` is on ``PATH``.
    """
    return [sys.executable, "-m", "polaris_re.cli"]


@pytest.fixture(scope="module")
def live_server() -> Iterator[str]:
    """Launch a real uvicorn server as a subprocess; yield its base URL.

    Fails loudly if the process dies during boot or never answers ``/health``
    within :data:`_BOOT_TIMEOUT_S`.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "polaris_re.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + _BOOT_TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                pytest.fail(f"uvicorn exited during boot (code {proc.returncode}):\n{out}")
            try:
                resp = httpx.get(f"{base_url}/health", timeout=1.0)
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            proc.terminate()
            out = proc.stdout.read() if proc.stdout else ""
            pytest.fail(f"uvicorn did not answer /health within {_BOOT_TIMEOUT_S}s:\n{out}")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


# ---------------------------------------------------------------------------
# Real uvicorn server — liveness, metrics, and a real pricing request
# ---------------------------------------------------------------------------


def test_health_endpoint_live(live_server: str) -> None:
    """The real server answers the liveness/readiness probe."""
    resp = httpx.get(f"{live_server}/health", timeout=5.0)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_metrics_endpoint_live(live_server: str) -> None:
    """The Prometheus metrics endpoint boots and emits exposition text."""
    resp = httpx.get(f"{live_server}/metrics", timeout=5.0)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    # A HELP/TYPE header for the request counter proves the registry wired up.
    assert "polaris_http_requests_total" in resp.text


def test_price_endpoint_live(live_server: str) -> None:
    """A real /api/v1/price request runs the full pipeline over the wire."""
    resp = httpx.post(
        f"{live_server}/api/v1/price",
        json=_SMOKE_PRICE_REQUEST,
        timeout=60.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The response must carry real priced output for both the cedant (NET) and
    # the reinsurer perspectives — proof the full pipeline ran, not just that
    # the endpoint returned parseable JSON.
    for key in ("pv_profits", "reinsurer_pv_profits", "premium_sufficiency", "n_policies"):
        assert key in body, f"missing {key!r} in price response: {body}"
    assert body["n_policies"] == 1, body


# ---------------------------------------------------------------------------
# Real CLI console script — price and benchmark entry points
# ---------------------------------------------------------------------------


def test_cli_price_entrypoint(tmp_path: Path) -> None:
    """`polaris price` runs on the golden deal and writes valid JSON."""
    out_path = tmp_path / "smoke_price.json"
    result = subprocess.run(
        [
            *_polaris_cli_argv(),
            "price",
            "--inforce",
            str(GOLDEN_INFORCE),
            "--config",
            str(GOLDEN_CONFIG),
            "-o",
            str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_CLI_TIMEOUT_S,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert out_path.exists(), "polaris price did not write its -o output file"
    # The written file must be parseable JSON (not a truncated/half-written dump).
    parsed = json.loads(out_path.read_text())
    assert isinstance(parsed, dict) and parsed, "price output JSON is empty"


def test_cli_benchmark_entrypoint() -> None:
    """`polaris benchmark --pack closed-form` runs and every case passes."""
    result = subprocess.run(
        [*_polaris_cli_argv(), "benchmark", "--pack", "closed-form"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_CLI_TIMEOUT_S,
    )
    # A non-zero exit means a reference case regressed — the smoke gate should
    # fail loudly rather than let a broken benchmark entry point merge.
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

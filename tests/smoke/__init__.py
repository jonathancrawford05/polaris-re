"""Smoke tests — boot the real entry points and exercise them end to end.

Unlike the unit/integration suites (which drive the app in-process via
``TestClient`` and import the CLI functions directly), these tests launch the
**actual deployed entry points** — a real ``uvicorn`` server process and the
``polaris`` console script as subprocesses — and assert they boot and answer.

They exist to catch "won't boot / endpoint 500s" regressions that in-process
tests structurally cannot see: broken ASGI lifespan startup, packaging /
console-script wiring, import-time failures, and a benchmark or price entry
point that crashes only when invoked as a real process. See ADR-168.
"""

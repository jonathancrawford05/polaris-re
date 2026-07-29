"""
Polaris RE — service layer.

The engine-invocation composition root shared by every host of the pricing
engine (the FastAPI REST API, an MCP server, batch scripts, notebooks). Each
service function takes a typed Pydantic request and returns a typed response,
driving the core engine in-process with **no web-framework dependency** — so the
same engine path can be reached without ``fastapi`` / ``uvicorn``.

Exposes the deal-pricing workflow (:func:`run_price`) and the stress-scenario
and Monte-Carlo-UQ workflows (:func:`run_scenario` / :func:`run_uq`), all
extracted from the matching FastAPI route bodies (MCP-server epic, ADR-170 /
ADR-172; ``docs/PLAN_mcp_server.md``).
"""

from polaris_re.services.pricing import (
    PolicyInput,
    PriceRequest,
    PriceResponse,
    ScenarioRequest,
    ScenarioResponse,
    ScenarioSummary,
    UQRequest,
    UQResponse,
    run_price,
    run_scenario,
    run_uq,
)

__all__ = [
    "PolicyInput",
    "PriceRequest",
    "PriceResponse",
    "ScenarioRequest",
    "ScenarioResponse",
    "ScenarioSummary",
    "UQRequest",
    "UQResponse",
    "run_price",
    "run_scenario",
    "run_uq",
]

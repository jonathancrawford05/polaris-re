"""
Polaris RE — service layer.

The engine-invocation composition root shared by every host of the pricing
engine (the FastAPI REST API, an MCP server, batch scripts, notebooks). Each
service function takes a typed Pydantic request and returns a typed response,
driving the core engine in-process with **no web-framework dependency** — so the
same engine path can be reached without ``fastapi`` / ``uvicorn``.

Currently exposes the deal-pricing workflow (:func:`run_price`); the scenario and
Monte-Carlo-UQ workflows are extracted here in a later slice of the MCP-server
epic (``docs/PLAN_mcp_server.md``).
"""

from polaris_re.services.pricing import (
    PolicyInput,
    PriceRequest,
    PriceResponse,
    run_price,
)

__all__ = ["PolicyInput", "PriceRequest", "PriceResponse", "run_price"]

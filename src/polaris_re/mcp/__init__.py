"""
Polaris RE — MCP (Model Context Protocol) server package.

An in-process stdio MCP server exposing the read-only pricing engine to agent
hosts (Claude Code / Claude Desktop). Every tool is a thin wrapper over the
shared service layer :func:`polaris_re.services.pricing.run_price`, so an MCP
call, a REST API request, and a batch script all drive one engine path.

See :mod:`polaris_re.mcp.server` for the tools (``polaris_price_block`` /
``polaris_price``), the ``polaris://capabilities`` resource, and the
``polaris-mcp`` console entry point. Design and slice plan:
``docs/PLAN_mcp_server.md`` (ADR-171).
"""

from polaris_re.mcp.server import (
    PriceBlockResult,
    build_price_request_from_block,
    load_sample_block_ids,
    main,
    mcp,
)

__all__ = [
    "PriceBlockResult",
    "build_price_request_from_block",
    "load_sample_block_ids",
    "main",
    "mcp",
]

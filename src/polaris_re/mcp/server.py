"""
Polaris RE — MCP (Model Context Protocol) server.

Exposes the deterministic, read-only pricing engine to agent hosts (Claude Code /
Claude Desktop) as an **in-process** stdio MCP server (MCP-server epic Slice 2;
``docs/PLAN_mcp_server.md``). Every tool is a thin wrapper over the shared
service-layer entry point :func:`polaris_re.services.pricing.run_price` (extracted
in Slice 1, ADR-170) — the same in-process engine path the FastAPI
``POST /api/v1/price`` route delegates to — so an MCP tool call, an API request,
and a batch script all invoke one engine path with no second mapping to drift.

Design anchors (from the plan, LOCKED 2026-07-27):

* **In-process, not an HTTP proxy.** The tool calls ``run_price`` directly; no
  ``uvicorn`` / deployed API is required. Works fully offline.
* **Reuse the Pydantic contracts as the tool schemas.** ``polaris_price`` takes a
  :class:`~polaris_re.services.pricing.PriceRequest`; FastMCP derives the tool
  input schema from it. No hand-copied schema.
* **Workflow tools, not a raw endpoint dump.** The headline tool
  ``polaris_price_block`` takes an *inforce reference* (a file path or a built-in
  sample id like ``"golden"``) plus high-level deal params — mirroring the CLI's
  ``--inforce X.csv --config Y.json`` — instead of a 25-field ``policies[]`` array.
  ``polaris_price`` remains for programmatic callers that carry inline policies.
* **Compact-by-default output.** Each pricing tool returns a
  :class:`PriceBlockResult`: a short ``summary`` headline (cedant / reinsurer PV
  profits + IRR, peak capital) plus the full typed ``price`` response. The large
  per-year ``profit_by_year`` arrays are cleared unless ``detail=true`` so a call
  does not flood an agent's context.
* **Read-only annotations.** Every pricing tool advertises
  ``readOnlyHint / idempotentHint = True`` and ``destructiveHint / openWorldHint =
  False`` — true because the engine mutates nothing.
* **Explicit ``valuation_date`` (ADR-074 guard).** ``polaris_price_block`` requires
  a valuation date and re-values the block to it (deriving each policy's attained
  age / duration in force from its issue date); the server never defaults to
  ``date.today()`` so a quote is always reproducible.

Run it: ``polaris-mcp`` (console script) or ``uv run polaris-mcp``. The committed
project-scope ``.mcp.json`` at the repo root registers it for a cloned checkout
with no manual ``claude mcp add``.
"""

import os
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from polaris_re.analytics.capital_base import (
    SUPPORTED_CAPITAL_MODELS,
    CapitalModelId,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType, Sex, SmokerStatus
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.services.pricing import (
    PolicyInput,
    PriceRequest,
    PriceResponse,
    run_price,
)
from polaris_re.utils.date_utils import months_between

__all__ = [
    "PriceBlockResult",
    "build_price_request_from_block",
    "load_sample_block_ids",
    "main",
    "mcp",
]

# Read-only, side-effect-free, idempotent, closed-world: the engine mutates
# nothing, so a host may call these tools freely. Shared by every pricing tool.
_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=False,
)

# Built-in sample blocks: id -> path relative to ``$POLARIS_DATA_DIR`` (default
# "data"). The golden QA block is the realistic headline sample the plan calls
# for (mirrors what the CLI and the golden regression check price).
_SAMPLE_BLOCKS: dict[str, str] = {"golden": "qa/golden_inforce.csv"}

# The four valid treaty strings; ``treaty_type=None`` means gross-only (no
# treaty). Kept in lockstep with ``services.pricing._build_treaty``.
_TREATY_TYPES: tuple[str, ...] = ("YRT", "Coinsurance", "Modco", "FWCoinsurance")

# Product types ``run_price`` can actually dispatch (products/dispatch.py
# registers TERM / WHOLE_LIFE / UNIVERSAL_LIFE). Matches the REST API's
# documented ``product_type`` surface. DI / CI / ANNUITY exist in the
# ``ProductType`` enum but have no pricing engine, so they are not advertised —
# requesting one yields an actionable tool error.
_PRICEABLE_PRODUCT_TYPES: tuple[str, ...] = (
    ProductType.TERM.value,
    ProductType.WHOLE_LIFE.value,
    ProductType.UNIVERSAL_LIFE.value,
)


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------


class PriceBlockResult(BaseModel):
    """Compact-by-default MCP pricing result.

    ``summary`` is a short human headline (cedant / reinsurer PV profits + IRR,
    peak capital) so an agent reads the answer without parsing the full payload.
    ``price`` is the full typed :class:`PriceResponse`; its large per-year
    ``profit_by_year`` / ``reinsurer_profit_by_year`` arrays are cleared unless the
    tool was called with ``detail=true`` (context safety). At ``detail=true``,
    ``price`` is byte-identical to ``run_price(request)`` and the REST API.
    """

    summary: str = Field(
        description=(
            "One-line headline: cedant and reinsurer PV profits and IRR, plus "
            "peak required capital when a capital model was applied."
        )
    )
    price: PriceResponse = Field(
        description=(
            "Full structured pricing response. The per-year profit arrays are "
            "cleared unless the tool was called with detail=true."
        )
    )


# ---------------------------------------------------------------------------
# Helpers — inforce resolution, block loading, request assembly, summary
# ---------------------------------------------------------------------------


def load_sample_block_ids() -> dict[str, str]:
    """Return the built-in sample-block id -> data-relative path mapping."""
    return dict(_SAMPLE_BLOCKS)


def _data_dir() -> Path:
    """Resolve ``$POLARIS_DATA_DIR`` (default ``data``)."""
    return Path(os.environ.get("POLARIS_DATA_DIR", "data"))


def _resolve_inforce_path(inforce: str) -> Path:
    """Resolve an inforce reference to a readable CSV path.

    ``inforce`` is either a built-in sample id (e.g. ``"golden"`` →
    ``$POLARIS_DATA_DIR/qa/golden_inforce.csv``) or a filesystem path (absolute,
    or relative to the process CWD). Raises :class:`ToolError` with actionable
    guidance when the reference does not resolve to an existing file.
    """
    if inforce in _SAMPLE_BLOCKS:
        path = _data_dir() / _SAMPLE_BLOCKS[inforce]
        if not path.is_file():
            raise ToolError(
                f"Sample block {inforce!r} maps to {path}, which does not exist. "
                "Set POLARIS_DATA_DIR to the repo's data/ directory (the .mcp.json "
                "sets it to ./data), or pass an explicit inforce file path."
            )
        return path

    path = Path(inforce)
    if not path.is_file():
        known = ", ".join(sorted(_SAMPLE_BLOCKS))
        raise ToolError(
            f"inforce {inforce!r} is neither a known sample id ({known}) nor an "
            "existing file. Pass a built-in sample id or a path to a normalised "
            "Polaris RE inforce CSV (see InforceBlock.from_csv columns)."
        )
    return path


def build_price_request_from_block(
    *,
    inforce: str,
    valuation_date: date,
    product_type: str = "TERM",
    treaty_type: str | None = "YRT",
    cession_pct: float = 0.90,
    discount_rate: float = 0.06,
    hurdle_rate: float = 0.10,
    projection_horizon_years: int = 20,
    reserve_basis: ReserveBasis = ReserveBasis.NET_PREMIUM,
    capital_model: CapitalModelId | None = None,
    available_capital: float | None = None,
    flat_qx: float = 0.003,
    flat_lapse: float = 0.05,
    acquisition_cost_per_policy: float = 0.0,
    maintenance_cost_per_policy_per_year: float = 0.0,
) -> PriceRequest:
    """Assemble a :class:`PriceRequest` from an inforce reference + deal params.

    The block is loaded via :meth:`InforceBlock.from_csv` (which validates the
    source CSV's own age/duration columns against its embedded valuation date,
    ADR-074) and then **re-valued to** ``valuation_date``: each policy's
    ``attained_age`` and ``duration_inforce`` are re-derived from its
    ``issue_date`` so the assembled block is internally consistent at the pinned
    valuation date. This is the actuarial "value this block as of <date>"
    semantics and keeps the run reproducible (never ``date.today()``).

    ``run_price`` prices a single product engine, so only the policies whose
    ``product_type`` matches ``product_type`` are included (a sample block such as
    ``"golden"`` mixes TERM and WHOLE_LIFE); the assembled request's
    ``n_policies`` reflects the filtered count, and a block with no matching
    policies raises :class:`ToolError` naming the product types it does contain.

    Raises :class:`PolarisValidationError` / ``ValueError`` for an unusable block
    (e.g. a valuation date before a policy's issue date yields a negative
    duration, rejected by ``PolicyInput``); callers map these to a tool error.
    """
    try:
        wanted = ProductType(product_type)
    except ValueError as exc:
        valid = ", ".join(e.value for e in ProductType)
        raise ToolError(f"Unknown product_type {product_type!r}. Valid: {valid}.") from exc

    block: InforceBlock = InforceBlock.from_csv(_resolve_inforce_path(inforce))
    matched = [p for p in block.policies if p.product_type == wanted]
    if not matched:
        present = ", ".join(sorted({p.product_type.value for p in block.policies}))
        raise ToolError(
            f"No {wanted.value} policies in inforce {inforce!r} "
            f"(it contains: {present}). Set product_type to one of those, since a "
            "single price run covers one product engine."
        )

    policies: list[PolicyInput] = []
    for p in matched:
        derived_months = months_between(p.issue_date, valuation_date)
        policies.append(
            PolicyInput(
                policy_id=p.policy_id,
                issue_age=p.issue_age,
                attained_age=p.issue_age + derived_months // 12,
                sex="M" if p.sex == Sex.MALE else "F",
                smoker=p.smoker_status == SmokerStatus.SMOKER,
                underwriting_class=p.underwriting_class,
                face_amount=p.face_amount,
                annual_premium=p.annual_premium,
                policy_term=p.policy_term,
                duration_inforce=derived_months,
                issue_date=p.issue_date,
                valuation_date=valuation_date,
                # Policy leaves these None for non-UL products; PolicyInput
                # wants floats (default 0.0), so coalesce.
                account_value=p.account_value if p.account_value is not None else 0.0,
                credited_rate=p.credited_rate if p.credited_rate is not None else 0.0,
            )
        )

    return PriceRequest(
        policies=policies,
        product_type=product_type,
        treaty_type=treaty_type,
        cession_pct=cession_pct,
        discount_rate=discount_rate,
        hurdle_rate=hurdle_rate,
        projection_horizon_years=projection_horizon_years,
        reserve_basis=reserve_basis,
        capital_model=capital_model,
        available_capital=available_capital,
        flat_qx=flat_qx,
        flat_lapse=flat_lapse,
        acquisition_cost_per_policy=acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
    )


def _fmt_money(value: float | None) -> str:
    """Format a dollar figure compactly, tolerating ``None``."""
    return "n/a" if value is None else f"${value:,.0f}"


def _fmt_pct(value: float | None) -> str:
    """Format a rate as a percentage, tolerating ``None``."""
    return "n/a" if value is None else f"{value * 100:.2f}%"


def _summarise(response: PriceResponse) -> str:
    """Build the one-line headline for :class:`PriceBlockResult`."""
    parts = [
        f"{response.n_policies} policies, {response.projection_months} months, "
        f"basis {response.reserve_basis.value}.",
        f"Cedant PV profit {_fmt_money(response.pv_profits)} (IRR {_fmt_pct(response.irr)}).",
        f"Reinsurer PV profit {_fmt_money(response.reinsurer_pv_profits)} "
        f"(IRR {_fmt_pct(response.reinsurer_irr)}).",
    ]
    if response.peak_capital is not None:
        parts.append(f"Peak cedant capital {_fmt_money(response.peak_capital)}.")
    return " ".join(parts)


def _to_block_result(response: PriceResponse, *, detail: bool) -> PriceBlockResult:
    """Wrap a :class:`PriceResponse` in the compact result, gating big arrays.

    ``detail=False`` (default) clears the per-year profit arrays for context
    safety; ``detail=True`` returns them so ``price`` is byte-identical to
    ``run_price``.
    """
    if detail:
        priced = response
    else:
        priced = response.model_copy(update={"profit_by_year": [], "reinsurer_profit_by_year": []})
    return PriceBlockResult(summary=_summarise(response), price=priced)


def _price(request: PriceRequest, *, detail: bool) -> PriceBlockResult:
    """Run ``run_price`` and map any domain failure to an actionable tool error."""
    try:
        response = run_price(request)
    except (PolarisValidationError, ValueError) as exc:
        raise ToolError(f"Pricing failed: {exc}") from exc
    return _to_block_result(response, detail=detail)


# ---------------------------------------------------------------------------
# Server + tools
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "polaris-re",
    instructions=(
        "Polaris RE is a read-only life-reinsurance pricing engine. Use "
        "polaris_price_block to price a named sample block (e.g. 'golden') or an "
        "inforce CSV with high-level deal params; use polaris_price for inline "
        "policies. Read the polaris://capabilities resource for the valid product "
        "types, treaty types, capital models, reserve bases, and sample block ids. "
        "Every pricing tool requires an explicit valuation_date so quotes are "
        "reproducible; results are compact by default (pass detail=true for the "
        "full per-year profit arrays)."
    ),
)


@mcp.tool(
    title="Price an inforce block",
    annotations=_READ_ONLY,
)
def polaris_price_block(
    valuation_date: date,
    inforce: str = "golden",
    product_type: str = "TERM",
    treaty_type: str | None = "YRT",
    cession_pct: float = 0.90,
    discount_rate: float = 0.06,
    hurdle_rate: float = 0.10,
    projection_horizon_years: int = 20,
    reserve_basis: ReserveBasis = ReserveBasis.NET_PREMIUM,
    capital_model: CapitalModelId | None = None,
    available_capital: float | None = None,
    flat_qx: float = 0.003,
    flat_lapse: float = 0.05,
    acquisition_cost_per_policy: float = 0.0,
    maintenance_cost_per_policy_per_year: float = 0.0,
    detail: bool = False,
) -> PriceBlockResult:
    """Price a reinsurance deal on a named sample block or an inforce CSV.

    ``inforce`` is a built-in sample id (``"golden"`` — the committed QA block) or
    a path to a normalised Polaris RE inforce CSV. ``valuation_date`` is required
    and re-values the block to that date (no ``date.today()`` default). Returns
    both cedant (NET) and reinsurer views: PV profits, IRR, break-even, profit
    margin — plus regulatory capital / return-on-capital when ``capital_model`` is
    set. Output is compact by default; pass ``detail=true`` for the full per-year
    profit arrays.

    ``flat_qx`` / ``flat_lapse`` drive the demo flat-rate assumption table this
    engine path uses (0.003 / 0.05 mirror the golden QA block); a production run
    would load real tables server-side.
    """
    request = build_price_request_from_block(
        inforce=inforce,
        valuation_date=valuation_date,
        product_type=product_type,
        treaty_type=treaty_type,
        cession_pct=cession_pct,
        discount_rate=discount_rate,
        hurdle_rate=hurdle_rate,
        projection_horizon_years=projection_horizon_years,
        reserve_basis=reserve_basis,
        capital_model=capital_model,
        available_capital=available_capital,
        flat_qx=flat_qx,
        flat_lapse=flat_lapse,
        acquisition_cost_per_policy=acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
    )
    return _price(request, detail=detail)


@mcp.tool(
    title="Price inline policies",
    annotations=_READ_ONLY,
)
def polaris_price(request: PriceRequest, detail: bool = False) -> PriceBlockResult:
    """Price a deal from a full inline ``PriceRequest`` (programmatic callers).

    Identical engine path to ``polaris_price_block`` but takes the complete typed
    request — an explicit ``policies[]`` array plus every deal parameter — for
    callers that already hold structured policy data. Output is compact by
    default; pass ``detail=true`` for the full per-year profit arrays.
    """
    return _price(request, detail=detail)


@mcp.resource(
    "polaris://capabilities",
    name="polaris_capabilities",
    title="Polaris RE pricing capabilities",
    mime_type="application/json",
)
def polaris_capabilities() -> dict[str, object]:
    """Enumerate the valid enums so an agent discovers them instead of guessing.

    Lists supported product types, treaty types (``treaty_type=null`` means
    gross-only), regulatory capital models, reserve bases, and the built-in
    sample block ids.
    """
    return {
        "product_types": list(_PRICEABLE_PRODUCT_TYPES),
        "treaty_types": list(_TREATY_TYPES),
        "treaty_null_means": "gross-only (no treaty applied)",
        "capital_models": list(SUPPORTED_CAPITAL_MODELS),
        "reserve_bases": [e.value for e in ReserveBasis],
        "sample_blocks": load_sample_block_ids(),
    }


def main() -> None:
    """Console-script entry point: run the stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

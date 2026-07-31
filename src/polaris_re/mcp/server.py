"""
Polaris RE — MCP (Model Context Protocol) server.

Exposes the deterministic, read-only pricing engine to agent hosts (Claude Code /
Claude Desktop) as an **in-process** stdio MCP server (MCP-server epic Slices 2-3;
``docs/PLAN_mcp_server.md``). Every tool is a thin wrapper over a shared
service-layer entry point in :mod:`polaris_re.services.pricing` — ``run_price``
(Slice 1, ADR-170), ``run_scenario`` and ``run_uq`` (Slice 3, ADR-172) — the same
in-process engine paths the FastAPI ``/api/v1/price`` / ``/scenario`` / ``/uq``
routes delegate to, so an MCP tool call, an API request, and a batch script all
invoke one engine path with no second mapping to drift.

Tools: ``polaris_price_block`` / ``polaris_price`` (deal pricing),
``polaris_run_scenario`` (standard stress set) and ``polaris_run_uq`` (Monte-Carlo
profit bands), plus the ``polaris://capabilities`` resource.

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

import argparse
import os
from datetime import date
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette

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
    ScenarioRequest,
    ScenarioResponse,
    UQRequest,
    UQResponse,
    run_price,
    run_scenario,
    run_uq,
)
from polaris_re.utils.date_utils import months_between

__all__ = [
    "PriceBlockResult",
    "ScenarioBlockResult",
    "UQBlockResult",
    "build_http_app",
    "build_price_request_from_block",
    "build_scenario_request_from_block",
    "build_uq_request_from_block",
    "load_sample_block_ids",
    "main",
    "mcp",
    "resolve_transport",
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
# Transport configuration (stdio default; optional streamable-HTTP)
# ---------------------------------------------------------------------------

# stdio is the default transport — it is what Claude Code / Claude Desktop spawn.
# The optional streamable-HTTP (stateless JSON) transport is a transport of the
# *same* in-process server (not a proxy to the REST API) for the remote / shared
# deployment case; it reuses the REST API's ``APIKeyAuthMiddleware``.
_TRANSPORT_ENV = "POLARIS_MCP_TRANSPORT"
_HOST_ENV = "POLARIS_MCP_HOST"
_PORT_ENV = "POLARIS_MCP_PORT"
_ALLOWED_HOSTS_ENV = "POLARIS_MCP_ALLOWED_HOSTS"
_ALLOWED_ORIGINS_ENV = "POLARIS_MCP_ALLOWED_ORIGINS"

_DEFAULT_HTTP_HOST = "127.0.0.1"
_DEFAULT_HTTP_PORT = 8000

# Spellings accepted for each transport (env value or ``--transport`` flag).
_STDIO_ALIASES: frozenset[str] = frozenset({"", "stdio"})
_HTTP_ALIASES: frozenset[str] = frozenset({"http", "streamable-http", "streamable_http"})
# The ``--transport`` flag accepts exactly the spellings the env var does (minus the
# empty-string stdio default, which is expressed by omitting the flag) — one source of
# truth so the flag and $POLARIS_MCP_TRANSPORT never diverge.
_TRANSPORT_CHOICES: tuple[str, ...] = tuple(sorted((_STDIO_ALIASES | _HTTP_ALIASES) - {""}))


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


class ScenarioBlockResult(BaseModel):
    """Compact MCP stress-scenario result (mirrors :class:`PriceBlockResult`).

    ``summary`` is a short human headline — the base run plus each stressed
    scenario's PV profit and IRR under the effective perspective — so an agent
    reads the stress deltas without parsing the full payload. ``scenario`` is the
    full typed :class:`ScenarioResponse` (already compact: a per-scenario summary
    list, no per-year arrays), byte-identical to ``run_scenario(request)`` and the
    REST API.
    """

    summary: str = Field(
        description=(
            "One-line headline: the effective perspective and each scenario's PV "
            "profit and IRR (base first), so the stress deltas read at a glance."
        )
    )
    scenario: ScenarioResponse = Field(description="Full structured scenario response.")


class UQBlockResult(BaseModel):
    """Compact MCP Monte-Carlo-UQ result (mirrors :class:`PriceBlockResult`).

    ``summary`` is a short human headline — the base PV profit plus the P5 / P50 /
    P95 band and the 95% VaR / CVaR under the effective perspective. ``uq`` is the
    full typed :class:`UQResponse` (already compact: scalar percentiles, no
    per-scenario arrays), byte-identical to ``run_uq(request)`` and the REST API.
    """

    summary: str = Field(
        description=(
            "One-line headline: the effective perspective, base PV profit, the "
            "P5/P50/P95 profit band, and the 95% VaR / CVaR."
        )
    )
    uq: UQResponse = Field(description="Full structured uncertainty-quantification response.")


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


def _actionable_param_error(exc: ValidationError) -> ToolError:
    """Turn a pydantic request-validation failure into an actionable tool error.

    An out-of-range deal parameter (e.g. ``cession_pct=1.5``) otherwise surfaces
    as a raw ``pydantic_core.ValidationError`` with a docs URL — opaque to an
    agent. This names each offending field, the constraint that was violated
    (which states the valid range), and the rejected value, then points at the
    ``polaris://capabilities`` resource for the valid enums.
    """
    problems: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "(request)"
        got = repr(err.get("input"))
        if len(got) > 60:
            got = got[:57] + "..."
        problems.append(f"{loc} — {err['msg']} (got {got})")
    joined = "; ".join(problems)
    return ToolError(
        f"Invalid pricing parameter(s): {joined}. See the polaris://capabilities "
        "resource for valid enums and ranges."
    )


def _load_block_policies(
    *,
    inforce: str,
    valuation_date: date,
    product_type: str,
) -> list[PolicyInput]:
    """Load an inforce reference into re-valued :class:`PolicyInput` rows.

    Shared by every ``build_*_request_from_block`` helper (price / scenario / uq)
    so the three tools resolve, filter, and re-value a block identically.

    The block is loaded via :meth:`InforceBlock.from_csv` (which validates the
    source CSV's own age/duration columns against its embedded valuation date,
    ADR-074) and then **re-valued to** ``valuation_date``: each policy's
    ``attained_age`` and ``duration_inforce`` are re-derived from its
    ``issue_date`` so the assembled block is internally consistent at the pinned
    valuation date. This is the actuarial "value this block as of <date>"
    semantics and keeps the run reproducible (never ``date.today()``).

    Every engine workflow prices a single product engine, so only the policies
    whose ``product_type`` matches ``product_type`` are returned (a sample block
    such as ``"golden"`` mixes TERM and WHOLE_LIFE). A block with no matching
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
            "single run covers one product engine."
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
    return policies


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

    The block is loaded and re-valued to ``valuation_date`` via
    :func:`_load_block_policies` (ADR-074 semantics; only ``product_type``
    policies are kept, since ``run_price`` prices one product engine). The
    assembled request's ``n_policies`` reflects the filtered count.
    """
    policies = _load_block_policies(
        inforce=inforce, valuation_date=valuation_date, product_type=product_type
    )
    try:
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
    except ValidationError as exc:
        raise _actionable_param_error(exc) from exc


def build_scenario_request_from_block(
    *,
    inforce: str,
    valuation_date: date,
    product_type: str = "TERM",
    treaty_type: str | None = "YRT",
    cession_pct: float = 0.90,
    discount_rate: float = 0.06,
    hurdle_rate: float = 0.10,
    projection_horizon_years: int = 20,
    perspective: str = "reinsurer",
    flat_qx: float = 0.003,
    flat_lapse: float = 0.05,
    acquisition_cost_per_policy: float = 0.0,
    maintenance_cost_per_policy_per_year: float = 0.0,
) -> ScenarioRequest:
    """Assemble a :class:`ScenarioRequest` from an inforce reference + deal params.

    Loads and re-values the block exactly as :func:`build_price_request_from_block`
    does (via :func:`_load_block_policies`), then wraps it in the scenario contract.
    The ``perspective`` (``"reinsurer"`` default, ADR-078) is downgraded to
    ``"cedant"`` inside ``run_scenario`` when no treaty is configured.
    """
    policies = _load_block_policies(
        inforce=inforce, valuation_date=valuation_date, product_type=product_type
    )
    try:
        return ScenarioRequest(
            policies=policies,
            product_type=product_type,
            treaty_type=treaty_type,
            cession_pct=cession_pct,
            discount_rate=discount_rate,
            hurdle_rate=hurdle_rate,
            projection_horizon_years=projection_horizon_years,
            perspective=perspective,  # type: ignore[arg-type]
            flat_qx=flat_qx,
            flat_lapse=flat_lapse,
            acquisition_cost_per_policy=acquisition_cost_per_policy,
            maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
        )
    except ValidationError as exc:
        raise _actionable_param_error(exc) from exc


def build_uq_request_from_block(
    *,
    inforce: str,
    valuation_date: date,
    product_type: str = "TERM",
    treaty_type: str | None = "YRT",
    cession_pct: float = 0.90,
    discount_rate: float = 0.06,
    hurdle_rate: float = 0.10,
    projection_horizon_years: int = 20,
    perspective: str = "reinsurer",
    n_scenarios: int = 200,
    seed: int = 42,
    mortality_log_sigma: float = 0.10,
    lapse_log_sigma: float = 0.15,
    interest_rate_sigma: float = 0.005,
    flat_qx: float = 0.003,
    flat_lapse: float = 0.05,
    acquisition_cost_per_policy: float = 0.0,
    maintenance_cost_per_policy_per_year: float = 0.0,
) -> UQRequest:
    """Assemble a :class:`UQRequest` from an inforce reference + deal params.

    Loads and re-values the block exactly as :func:`build_price_request_from_block`
    does (via :func:`_load_block_policies`), then wraps it in the Monte-Carlo-UQ
    contract. ``seed`` (default 42) makes the sampled distribution reproducible;
    ``n_scenarios`` sets the sample count and the sigmas the assumption spreads.
    """
    policies = _load_block_policies(
        inforce=inforce, valuation_date=valuation_date, product_type=product_type
    )
    try:
        return UQRequest(
            policies=policies,
            product_type=product_type,
            treaty_type=treaty_type,
            cession_pct=cession_pct,
            discount_rate=discount_rate,
            hurdle_rate=hurdle_rate,
            projection_horizon_years=projection_horizon_years,
            perspective=perspective,  # type: ignore[arg-type]
            n_scenarios=n_scenarios,
            seed=seed,
            mortality_log_sigma=mortality_log_sigma,
            lapse_log_sigma=lapse_log_sigma,
            interest_rate_sigma=interest_rate_sigma,
            flat_qx=flat_qx,
            flat_lapse=flat_lapse,
            acquisition_cost_per_policy=acquisition_cost_per_policy,
            maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
        )
    except ValidationError as exc:
        raise _actionable_param_error(exc) from exc


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


def _summarise_scenario(response: ScenarioResponse) -> str:
    """Build the one-line headline for :class:`ScenarioBlockResult`.

    Lists each scenario's PV profit and IRR under the effective perspective so an
    agent reads the stress deltas at a glance (the ``ScenarioRunner`` puts the
    base run first).
    """
    parts = [f"{response.n_scenarios} scenarios ({response.perspective} view):"]
    parts.extend(
        f"{s.scenario_name} PV profit {_fmt_money(s.pv_profits)} (IRR {_fmt_pct(s.irr)})."
        for s in response.scenarios
    )
    return " ".join(parts)


def _summarise_uq(response: UQResponse) -> str:
    """Build the one-line headline for :class:`UQBlockResult`.

    Reports the base PV profit, the P5 / P50 / P95 band, and the 95% VaR / CVaR
    under the effective perspective.
    """
    return (
        f"{response.n_scenarios} sims, seed {response.seed} ({response.perspective} view). "
        f"Base PV profit {_fmt_money(response.base_pv_profit)} "
        f"(IRR {_fmt_pct(response.base_irr)}). "
        f"PV profit band P5 {_fmt_money(response.p5_pv_profit)} / "
        f"P50 {_fmt_money(response.p50_pv_profit)} / P95 {_fmt_money(response.p95_pv_profit)}. "
        f"95% VaR {_fmt_money(response.var_95)}, CVaR {_fmt_money(response.cvar_95)}."
    )


def _scenario(request: ScenarioRequest) -> ScenarioBlockResult:
    """Run ``run_scenario`` and map any domain failure to an actionable tool error."""
    try:
        response = run_scenario(request)
    except (PolarisValidationError, ValueError) as exc:
        raise ToolError(f"Scenario analysis failed: {exc}") from exc
    return ScenarioBlockResult(summary=_summarise_scenario(response), scenario=response)


def _uq(request: UQRequest) -> UQBlockResult:
    """Run ``run_uq`` and map any domain failure to an actionable tool error."""
    try:
        response = run_uq(request)
    except (PolarisValidationError, ValueError) as exc:
        raise ToolError(f"Uncertainty quantification failed: {exc}") from exc
    return UQBlockResult(summary=_summarise_uq(response), uq=response)


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
        "Use polaris_run_scenario to stress the block under the standard scenario "
        "set (mortality shock, lapse stress, rate shock) and read the PV/IRR delta, "
        "and polaris_run_uq for Monte-Carlo profit bands (P5/P50/P95, VaR/CVaR). "
        "Every tool requires an explicit valuation_date so quotes are reproducible "
        "(polaris_run_uq also takes a seed); the price tools are compact by default "
        "(pass detail=true for the full per-year profit arrays)."
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


@mcp.tool(
    title="Stress an inforce block",
    annotations=_READ_ONLY,
)
def polaris_run_scenario(
    valuation_date: date,
    inforce: str = "golden",
    product_type: str = "TERM",
    treaty_type: str | None = "YRT",
    cession_pct: float = 0.90,
    discount_rate: float = 0.06,
    hurdle_rate: float = 0.10,
    projection_horizon_years: int = 20,
    perspective: str = "reinsurer",
    flat_qx: float = 0.003,
    flat_lapse: float = 0.05,
    acquisition_cost_per_policy: float = 0.0,
    maintenance_cost_per_policy_per_year: float = 0.0,
) -> ScenarioBlockResult:
    """Run the standard stress-scenario set on a named sample block or inforce CSV.

    Applies the pre-defined stress scenarios (base, mortality shock, lapse stress,
    rate shock) to the block and returns each scenario's PV profit, profit margin,
    and IRR — so an agent can read the stress sensitivity of a deal. ``inforce`` and
    ``valuation_date`` behave exactly as in ``polaris_price_block`` (the block is
    re-valued to the pinned date). ``perspective`` (``"reinsurer"`` default,
    ADR-078) is downgraded to ``"cedant"`` when ``treaty_type`` is null.

    ``flat_qx`` / ``flat_lapse`` drive the demo flat-rate assumption table this
    engine path uses (0.003 / 0.05 mirror the golden QA block).
    """
    request = build_scenario_request_from_block(
        inforce=inforce,
        valuation_date=valuation_date,
        product_type=product_type,
        treaty_type=treaty_type,
        cession_pct=cession_pct,
        discount_rate=discount_rate,
        hurdle_rate=hurdle_rate,
        projection_horizon_years=projection_horizon_years,
        perspective=perspective,
        flat_qx=flat_qx,
        flat_lapse=flat_lapse,
        acquisition_cost_per_policy=acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
    )
    return _scenario(request)


@mcp.tool(
    title="Monte-Carlo UQ on an inforce block",
    annotations=_READ_ONLY,
)
def polaris_run_uq(
    valuation_date: date,
    inforce: str = "golden",
    product_type: str = "TERM",
    treaty_type: str | None = "YRT",
    cession_pct: float = 0.90,
    discount_rate: float = 0.06,
    hurdle_rate: float = 0.10,
    projection_horizon_years: int = 20,
    perspective: str = "reinsurer",
    n_scenarios: int = 200,
    seed: int = 42,
    mortality_log_sigma: float = 0.10,
    lapse_log_sigma: float = 0.15,
    interest_rate_sigma: float = 0.005,
    flat_qx: float = 0.003,
    flat_lapse: float = 0.05,
    acquisition_cost_per_policy: float = 0.0,
    maintenance_cost_per_policy_per_year: float = 0.0,
) -> UQBlockResult:
    """Run Monte-Carlo uncertainty quantification on a sample block or inforce CSV.

    Samples assumption multipliers from LogNormal (mortality, lapse) and Normal
    (interest-rate) distributions and returns the profit distribution: base PV
    profit, the P5 / P50 / P95 band, the 95% VaR / CVaR, and the margin band — so
    an agent can read the downside risk of a deal. ``inforce`` and
    ``valuation_date`` behave exactly as in ``polaris_price_block``. ``seed``
    (default 42) makes the sampled distribution reproducible (ADR-074 discipline);
    ``n_scenarios`` sets the sample count and the sigmas the assumption spreads.
    ``perspective`` (``"reinsurer"`` default, ADR-078) is downgraded to ``"cedant"``
    when ``treaty_type`` is null.
    """
    request = build_uq_request_from_block(
        inforce=inforce,
        valuation_date=valuation_date,
        product_type=product_type,
        treaty_type=treaty_type,
        cession_pct=cession_pct,
        discount_rate=discount_rate,
        hurdle_rate=hurdle_rate,
        projection_horizon_years=projection_horizon_years,
        perspective=perspective,
        n_scenarios=n_scenarios,
        seed=seed,
        mortality_log_sigma=mortality_log_sigma,
        lapse_log_sigma=lapse_log_sigma,
        interest_rate_sigma=interest_rate_sigma,
        flat_qx=flat_qx,
        flat_lapse=flat_lapse,
        acquisition_cost_per_policy=acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
    )
    return _uq(request)


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


def resolve_transport(override: str | None = None) -> str:
    """Resolve the transport to serve on: ``"stdio"`` (default) or ``"http"``.

    ``override`` (the ``--transport`` flag) wins; otherwise ``$POLARIS_MCP_TRANSPORT``
    is consulted, defaulting to stdio. Accepts ``"http"`` / ``"streamable-http"`` for
    the HTTP transport. An unrecognised value raises an actionable ``ValueError``.
    """
    raw = (override if override is not None else os.environ.get(_TRANSPORT_ENV, "")).strip().lower()
    if raw in _STDIO_ALIASES:
        return "stdio"
    if raw in _HTTP_ALIASES:
        return "http"
    raise ValueError(
        f"Unknown MCP transport {raw!r}. Use 'stdio' (default) or 'http' "
        f"(via --transport or ${_TRANSPORT_ENV})."
    )


def _csv_env(name: str) -> list[str]:
    """Parse a comma-separated environment variable into a list (blanks dropped)."""
    return [entry.strip() for entry in os.environ.get(name, "").split(",") if entry.strip()]


def _configured_allowed_hosts(host: str) -> list[str]:
    """Host-header allowlist for the HTTP transport (DNS-rebinding protection).

    ``$POLARIS_MCP_ALLOWED_HOSTS`` (comma-separated) is honoured verbatim when set.
    Otherwise the secure default permits only loopback and the configured bind
    ``host`` — each as both a bare name and a ``name:*`` wildcard-port pattern, since
    a real ``Host`` header carries the port. An operator binding to a public name
    must set the env var (matching the REST API's explicit-config posture).
    """
    explicit = _csv_env(_ALLOWED_HOSTS_ENV)
    if explicit:
        return explicit
    hosts: list[str] = []
    for base in ("127.0.0.1", "localhost", host):
        for form in (base, f"{base}:*"):
            if form not in hosts:
                hosts.append(form)
    return hosts


def build_http_app(*, host: str = _DEFAULT_HTTP_HOST) -> Starlette:
    """Build the streamable-HTTP (stateless JSON) ASGI app for the MCP server.

    This is a *transport of the single in-process* :data:`mcp` server (LOCKED
    decision #1 in ``docs/PLAN_mcp_server.md`` — not a proxy to the REST API): it
    serves the same tools over the same engine path as stdio. The app is wrapped in
    the REST API's :class:`~polaris_re.api.auth.APIKeyAuthMiddleware`, so a shared
    deployment authenticates with the same ``POLARIS_API_KEYS`` as the API — and,
    exactly like stdio, the endpoint is open when no keys are configured.

    ``APIKeyAuthMiddleware`` is imported lazily so the default stdio path (what
    Claude Code / Claude Desktop spawn) never pulls in the ``[api]`` FastAPI stack;
    the HTTP transport is the shared-deployment case, which installs it.
    """
    from polaris_re.api.auth import APIKeyAuthMiddleware

    # Stateless JSON: no per-connection session affinity, so any replica behind a
    # load balancer can answer any request — the shape API-key auth expects.
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    mcp.settings.transport_security = TransportSecuritySettings(
        allowed_hosts=_configured_allowed_hosts(host),
        allowed_origins=_csv_env(_ALLOWED_ORIGINS_ENV),
    )
    # The session manager is lazily built and cached on first call; drop it so the
    # HTTP settings above take effect. stdio never touches the session manager.
    mcp._session_manager = None

    app = mcp.streamable_http_app()
    # Added last → outermost: an unauthenticated request is rejected before it
    # reaches the transport-security check or the MCP handler.
    app.add_middleware(APIKeyAuthMiddleware)
    return app


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polaris-mcp",
        description="Polaris RE MCP server (stdio by default; optional streamable-HTTP).",
    )
    parser.add_argument(
        "--transport",
        choices=_TRANSPORT_CHOICES,
        default=None,
        help=f"Transport to serve on. Overrides ${_TRANSPORT_ENV} (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help=f"HTTP bind host (http only). Overrides ${_HOST_ENV} (default: {_DEFAULT_HTTP_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"HTTP bind port (http only). Overrides ${_PORT_ENV} (default: {_DEFAULT_HTTP_PORT}).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Console-script entry point: run the MCP server (stdio default, or HTTP)."""
    args = _build_arg_parser().parse_args(argv)
    if resolve_transport(args.transport) == "stdio":
        mcp.run()
        return

    host = args.host or os.environ.get(_HOST_ENV) or _DEFAULT_HTTP_HOST
    port = (
        args.port if args.port is not None else int(os.environ.get(_PORT_ENV, _DEFAULT_HTTP_PORT))
    )
    import uvicorn

    uvicorn.run(build_http_app(host=host), host=host, port=port)


if __name__ == "__main__":
    main()

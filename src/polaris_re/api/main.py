"""
Polaris RE — REST API (FastAPI).

Exposes the core Polaris RE pricing engine over HTTP for integration
with downstream systems, dashboards, and workflow automation.

Endpoints:
    GET  /health                       — liveness / readiness probe
    GET  /version                      — package version information
    POST /api/v1/price                 — run full pricing pipeline (cedant + reinsurer views)
    POST /api/v1/scenario              — run scenario analysis
    POST /api/v1/uq                    — run Monte Carlo uncertainty quantification
    POST /api/v1/ifrs17/bba            — compute IFRS 17 BBA measurement
    POST /api/v1/ifrs17/paa            — compute IFRS 17 PAA measurement
    POST /api/v1/ifrs17/movement       — IFRS 17 analysis-of-change (movement) table
    POST /api/v1/ingest                — ingest raw cedant inforce data
    POST /api/v1/rate-schedule         — generate YRT rate schedule for a target IRR
    POST /api/v1/portfolio             — aggregate a multi-deal book
    POST /api/v1/portfolio/scenarios   — run a portfolio under a stress-scenario set

All request and response bodies are JSON, validated via Pydantic models.
NumPy arrays are serialised as lists. Dates are ISO-8601 strings.

Running locally:
    uvicorn polaris_re.api.main:app --reload --port 8000

Production:
    uvicorn polaris_re.api.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, model_validator

import polaris_re

if TYPE_CHECKING:
    from polaris_re.analytics.portfolio import Portfolio
from polaris_re.analytics.alm import DualDurationGap, dual_duration_gap
from polaris_re.analytics.capital_base import CapitalModelId, capital_model_for
from polaris_re.analytics.ifrs17 import (
    IFRS17CohortManager,
    IFRS17ContractInput,
    IFRS17Measurement,
)
from polaris_re.analytics.premium_sufficiency import (
    PremiumSufficiencyResult,
    PremiumSufficiencyTester,
)
from polaris_re.analytics.profit_test import (
    ProfitResultWithCapital,
    ProfitTester,
    ProfitTestResult,
)
from polaris_re.analytics.scenario import ScenarioRunner
from polaris_re.analytics.uq import MonteCarloUQ, UQParameters
from polaris_re.api.auth import APIKeyAuthMiddleware, RateLimitMiddleware
from polaris_re.api.metrics import (
    METRICS_CONTENT_TYPE,
    MetricsMiddleware,
    render_latest,
)
from polaris_re.api.observability import (
    RequestContextMiddleware,
    configure_api_logging,
)
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.asset import AssetPortfolio
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.pipeline import derive_capital_nar, load_valuation_mortality
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty
from polaris_re.reinsurance.expense_allowance import ExpenseAllowance
from polaris_re.reinsurance.experience_refund import ExperienceRefund
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import MortalityTableArray

__all__ = ["app"]

app = FastAPI(
    title="Polaris RE API",
    description=(
        "Life reinsurance cash flow projection and deal pricing engine. "
        "Provides endpoints for profit testing, scenario analysis, "
        "Monte Carlo UQ, and IFRS 17 measurement."
    ),
    version=polaris_re.__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Observability + security + metrics (ROADMAP 6.2, Slices 1-3). Starlette runs
# middleware in **reverse** registration order (the last-added is outermost /
# runs first), so the order below yields the request flow:
#   RequestContextMiddleware  (outermost — assigns the correlation id)
#     → MetricsMiddleware     (count + time every request, incl. 401/429)
#       → RateLimitMiddleware (throttle floods before doing auth work)
#         → APIKeyAuthMiddleware (reject unauthorised callers)
#           → endpoint
# Auth and rate limiting run *inside* the request-context middleware, so a
# 401/429 is logged with the request's correlation id and the response still
# carries the X-Correlation-ID header. Metrics sits *outside* the security
# middlewares so rejections are still counted (they collapse to the
# ``__unmatched__`` path label because they never reach the router). All three
# added surfaces are default-off or read-only: with no POLARIS_API_KEYS /
# POLARIS_API_RATE_LIMIT configured the security middlewares are pure
# pass-throughs, and metrics collection never touches the pricing path — so the
# pre-existing API behaviour is unchanged.
configure_api_logging()
app.add_middleware(APIKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(PolarisValidationError)
def _polaris_validation_error_handler(
    request: Request, exc: PolarisValidationError
) -> JSONResponse:
    """Map a domain ``PolarisValidationError`` to HTTP 422.

    Domain validators on nested request models (e.g. the
    ``ExpenseAllowance`` sliding-scale monotonicity check, ADR-119) raise
    ``PolarisValidationError`` during FastAPI's request-body parsing — before
    any endpoint body runs, so the per-endpoint ``except`` blocks that already
    map this error to 422 never see it. Registering it app-wide keeps a
    malformed payload a clean 422 (the semantic half of request validation,
    matching the ADR-074 date-consistency guard) instead of a 500.
    """
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str
    version: str


class PolicyInput(BaseModel):
    """Minimal policy specification for API requests."""

    policy_id: str = Field(description="Unique policy identifier.")
    issue_age: int = Field(ge=18, le=80, description="Age at issue.")
    attained_age: int = Field(ge=18, le=120, description="Current attained age.")
    sex: str = Field(description="'M' or 'F'.")
    smoker: bool = Field(default=False, description="True if smoker.")
    underwriting_class: str = Field(default="STANDARD", description="Underwriting class.")
    face_amount: float = Field(gt=0.0, description="Policy face amount in USD.")
    annual_premium: float = Field(gt=0.0, description="Annual gross premium in USD.")
    policy_term: int | None = Field(
        default=20, ge=1, le=40, description="Policy term in years. None for permanent products."
    )
    duration_inforce: int = Field(default=0, ge=0, description="Months in force at valuation date.")
    issue_date: date = Field(description="Policy issue date (ISO 8601).")
    valuation_date: date = Field(description="Valuation date (ISO 8601).")
    account_value: float = Field(default=0.0, ge=0.0, description="UL account value at valuation.")
    credited_rate: float = Field(
        default=0.0, ge=0.0, le=0.20, description="UL credited interest rate."
    )


class PriceRequest(BaseModel):
    """Request body for /api/v1/price."""

    policies: list[PolicyInput] = Field(min_length=1, description="List of policies to price.")
    product_type: str = Field(
        default="TERM",
        description="Product type: 'TERM', 'WHOLE_LIFE', or 'UL'.",
    )
    treaty_type: str | None = Field(
        default="YRT",
        description="Treaty type: 'YRT', 'Coinsurance', 'Modco', or null for gross only.",
    )
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(ge=0.0, le=1.0, default=0.06)
    hurdle_rate: float = Field(ge=0.0, le=1.0, default=0.10)
    cession_pct: float = Field(
        ge=0.0, le=1.0, default=0.90, description="Treaty cession percentage."
    )
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001, description="Flat mortality rate (demo).")
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05, description="Flat annual lapse rate.")
    acquisition_cost_per_policy: float = Field(
        default=0.0, ge=0.0, description="One-time acquisition expense per policy in dollars."
    )
    maintenance_cost_per_policy_per_year: float = Field(
        default=0.0, ge=0.0, description="Annual per-policy maintenance expense in dollars."
    )
    yrt_loading: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Loading over expected mortality for YRT rate derivation (e.g. 0.10 = 10%).",
    )
    modco_interest_rate: float = Field(
        default=0.045,
        ge=0.0,
        le=0.20,
        description="Modco interest rate (used only for Modco treaty type).",
    )
    capital_model: CapitalModelId | None = Field(
        default=None,
        description=(
            "Regulatory-capital model: 'licat' (Canada OSFI, ADR-047/048), "
            "'rbc' (US NAIC RBC, ADR-098), or 'solvency2' (EU SCR, ADR-100). "
            "When set, cedant and reinsurer profit tests run with the selected "
            "jurisdiction's per-product factor model and the response gains "
            "return_on_capital, peak_capital, pv_capital, pv_capital_strain, "
            "and capital_adjusted_irr (ADR-049/101). Default: not applied."
        ),
    )
    available_capital: float | None = Field(
        default=None,
        gt=0.0,
        description=(
            "Company-supplied available capital / TAC / own funds used as the "
            "regulatory solvency-ratio numerator (ADR-103/104). When set with "
            "``capital_model``, the response gains ``capital_ratio`` and "
            "``reinsurer_capital_ratio`` = available capital / that side's "
            "required capital (LICAT total ratio / RBC ACL ratio / EU solvency "
            "ratio). Must be positive and requires ``capital_model`` (a ratio "
            "needs a jurisdictional denominator). Default: not applied."
        ),
    )
    yrt_rate_table_path: str | None = Field(
        default=None,
        description=(
            "Server-side path (relative to ``POLARIS_DATA_DIR``) to a "
            "directory of tabular YRT rate CSVs (ADR-052). When set, the "
            "engine bills YRT premiums from the table indexed by (age, "
            "sex, smoker, duration_years) instead of the implied flat "
            "rate. Path traversal is rejected: the resolved path must "
            "live within ``POLARIS_DATA_DIR``."
        ),
    )
    yrt_rate_table_select_period: int = Field(
        default=3,
        ge=1,
        le=50,
        description=(
            "Number of select-period columns (dur_1..dur_N) in the tabular "
            "YRT rate CSVs. Used only with ``yrt_rate_table_path``."
        ),
    )
    yrt_rate_table_label: str | None = Field(
        default=None,
        description=(
            "Filename label for the tabular YRT rate CSVs. Defaults to "
            "``'yrt'`` so files are ``yrt_male_ns.csv`` etc. Used only "
            "with ``yrt_rate_table_path``."
        ),
    )
    yrt_rate_table_smoker_distinct: bool = Field(
        default=True,
        description=(
            "When True (default), expect separate ``_ns`` and ``_smoker`` "
            "files per sex. When False, expect a single ``_unknown`` file "
            "per sex. Used only with ``yrt_rate_table_path``."
        ),
    )
    sufficiency_target_margin: float = Field(
        default=0.0,
        ge=0.0,
        lt=1.0,
        description=(
            "Premium-sufficiency target profit margin as a fraction of PV "
            "premiums, in [0, 1) (ADR-083). The response's premium_sufficiency "
            "block reports the premium 'sufficient' when its post-cost margin "
            "ratio meets this target. Default 0.0 tests bare cost coverage. "
            "Discounted at the valuation discount_rate, not the profit hurdle."
        ),
    )
    reserve_basis: ReserveBasis = Field(
        default=ReserveBasis.NET_PREMIUM,
        description=(
            "Reserve valuation basis (reserve-basis epic): NET_PREMIUM "
            "(default), CRVM, VM20, or GAAP. Lets a reinsurer reproduce the "
            "cedant's reserve method, which drives the YRT NAR, the coinsurance "
            "reserve transfer, and the profit signature. NET_PREMIUM is "
            "byte-identical to prior responses; a non-default basis changes the "
            "reserve (and therefore the priced numbers). An unsupported basis "
            "for the product yields HTTP 422."
        ),
    )
    valuation_mortality: str | None = Field(
        default=None,
        description=(
            "Prescribed statutory valuation mortality table for the statutory "
            "reserve bases (Reserve-Basis Exactness epic, ADR-125): a named "
            "source id ('CSO_2001', 'SOA_VBT_2015', 'CIA_2014', or 'flat'), "
            "loaded server-side from ``$POLARIS_DATA_DIR/mortality_tables``. "
            "When set, CRVM and the VM-20 NPR floor value on this table "
            "(static — no improvement scale) so the reinsurer reproduces the "
            "cedant's statutory reserve exactly instead of the pricing "
            "best-estimate table; NET_PREMIUM and the VM-20 deterministic "
            "reserve always ignore it. None (default) is byte-identical to "
            "prior responses. An unknown source id yields HTTP 422."
        ),
    )
    asset_portfolio: AssetPortfolio | None = Field(
        default=None,
        description=(
            "Optional backing asset portfolio (Asset/ALM epic, Slice 4b). When "
            "supplied, the response gains an ``alm_duration_gap`` block holding the "
            "asset-liability duration gap on both the reinsurer-view (ceded "
            "reserve — the headline) and cedant-view (retained reserve) "
            "liabilities. The JSON shape mirrors ``AssetPortfolio`` (a non-empty "
            "list of ``bonds`` plus an optional ``portfolio_id``). Purely additive: "
            "no priced number changes, and the block is null when omitted. For a "
            "YRT treaty the ceded reserve is ~0, so the reinsurer side is null and "
            "the cedant side carries the gap."
        ),
    )
    alm_valuation_yield: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Common flat effective-annual yield both sides of the duration gap are "
            "measured at (Asset/ALM epic). None (default) defers to ``discount_rate`` "
            "so a single rate isolates the asset-vs-liability timing mismatch. Used "
            "only when ``asset_portfolio`` is supplied."
        ),
    )
    expense_allowance: ExpenseAllowance | None = Field(
        default=None,
        description=(
            "Optional sliding-scale expense allowance (expense-allowance epic, "
            "ADR-119). A per-treaty allowance quoted as a % of ceded premium with "
            "a first-year vs renewal split and an optional loss-ratio sliding "
            "scale. Applied inside the YRT / Coinsurance treaty as a "
            "reinsurer→cedant transfer folded into the expense line, preserving "
            "``net + ceded == gross``. JSON shape mirrors ``ExpenseAllowance``. "
            "Ignored for Modco / gross. None (default) is byte-identical."
        ),
    )
    experience_refund: ExperienceRefund | None = Field(
        default=None,
        description=(
            "Optional experience refund / profit sharing (expense-allowance epic, "
            "ADR-121). A share of the favourable accumulated experience above a "
            "retention, applied as a single terminal reinsurer→cedant transfer "
            "(net of any expense allowance already paid) folded into the expense "
            "line, preserving ``net + ceded == gross``. JSON shape mirrors "
            "``ExperienceRefund``. Ignored for Modco / gross. None (default) is "
            "byte-identical."
        ),
    )

    @model_validator(mode="after")
    def _available_capital_requires_capital_model(self) -> "PriceRequest":
        """``available_capital`` is only meaningful with a ``capital_model``.

        The solvency ratio is available capital / required capital; without a
        capital model there is no jurisdictional denominator, so reject the
        combination (422) rather than silently ignoring the numerator (ADR-104).
        """
        if self.available_capital is not None and self.capital_model is None:
            raise ValueError(
                "available_capital requires capital_model (the solvency ratio "
                "needs a jurisdictional required-capital denominator)."
            )
        return self


class PriceResponse(BaseModel):
    """Response body for /api/v1/price.

    Returns both cedant (NET post-treaty) and reinsurer perspectives.
    The reinsurer view is computed by re-labelling CEDED cash flows as NET
    before passing to ProfitTester (ADR-039).
    """

    hurdle_rate: float
    # Cedant (NET) view
    pv_profits: float
    pv_premiums: float
    profit_margin: float | None  # None when pv_premiums <= 0 (ADR-041)
    irr: float | None
    breakeven_year: int | None
    total_undiscounted_profit: float
    profit_by_year: list[float]
    # Reinsurer view
    reinsurer_pv_profits: float
    reinsurer_profit_margin: float | None  # None when pv_premiums <= 0 (ADR-041)
    reinsurer_irr: float | None
    reinsurer_breakeven_year: int | None
    reinsurer_total_undiscounted_profit: float
    reinsurer_profit_by_year: list[float]
    # Regulatory-capital block — populated only when capital_model is set
    # (licat / rbc / solvency2; ADR-049/101). Cedant view
    peak_capital: float | None = None
    pv_capital: float | None = None
    pv_capital_strain: float | None = None
    return_on_capital: float | None = None
    capital_adjusted_irr: float | None = None
    # Regulatory solvency ratio (ADR-104): the echoed numerator and the
    # cedant-view ratio = available_capital / cedant required capital. Both
    # None unless available_capital was supplied alongside capital_model.
    available_capital: float | None = None
    capital_ratio: float | None = None
    # Reinsurer view
    reinsurer_peak_capital: float | None = None
    reinsurer_pv_capital: float | None = None
    reinsurer_pv_capital_strain: float | None = None
    reinsurer_return_on_capital: float | None = None
    reinsurer_capital_adjusted_irr: float | None = None
    reinsurer_capital_ratio: float | None = None
    # Premium-sufficiency block (ADR-083). Always populated: the cedant view
    # on the NET cash flows, the reinsurer view on the ceded cash flows
    # re-viewed as NET (mirrors the cedant view when no treaty is configured).
    # Discounted at the valuation discount_rate, not the profit hurdle.
    premium_sufficiency: dict[str, float | bool | None] | None = None
    reinsurer_premium_sufficiency: dict[str, float | bool | None] | None = None
    # Metadata
    n_policies: int
    projection_months: int
    # Reserve basis the run was priced on (reserve-basis epic). Echoes the
    # request's reserve_basis so a client can confirm which basis drove the
    # reserve, NAR, and profit numbers in this response.
    reserve_basis: ReserveBasis = ReserveBasis.NET_PREMIUM
    # Asset-liability duration gap (Asset/ALM epic, Slice 4b-2b). Populated only
    # when ``asset_portfolio`` was supplied; None otherwise (the block is purely
    # additive, so existing responses are unchanged except for this null field).
    # Carries the reinsurer-view (ceded reserve — headline) and cedant-view
    # (retained reserve) gaps; either side is null when its reserve is ~0 (e.g. the
    # ceded reserve of a YRT treaty).
    alm_duration_gap: DualDurationGap | None = None


class ScenarioRequest(BaseModel):
    """Request body for /api/v1/scenario."""

    policies: list[PolicyInput] = Field(min_length=1)
    product_type: str = Field(
        default="TERM", description="Product type: 'TERM', 'WHOLE_LIFE', or 'UL'."
    )
    treaty_type: str | None = Field(
        default="YRT", description="Treaty type: 'YRT', 'Coinsurance', 'Modco', or null."
    )
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(ge=0.0, le=1.0, default=0.06)
    hurdle_rate: float = Field(ge=0.0, le=1.0, default=0.10)
    cession_pct: float = Field(ge=0.0, le=1.0, default=0.90)
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001)
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05)
    acquisition_cost_per_policy: float = Field(default=0.0, ge=0.0)
    maintenance_cost_per_policy_per_year: float = Field(default=0.0, ge=0.0)
    yrt_loading: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Loading over expected mortality for YRT rate derivation.",
    )
    modco_interest_rate: float = Field(default=0.045, ge=0.0, le=0.20)
    expense_allowance: ExpenseAllowance | None = Field(
        default=None,
        description=(
            "Optional sliding-scale expense allowance threaded onto the YRT / "
            "Coinsurance treaty (expense-allowance epic, ADR-119). See "
            "/api/v1/price for the semantics. Ignored for Modco. None (default) "
            "is byte-identical."
        ),
    )
    experience_refund: ExperienceRefund | None = Field(
        default=None,
        description=(
            "Optional experience refund threaded onto the YRT / Coinsurance "
            "treaty (expense-allowance epic, ADR-121). See /api/v1/price for the "
            "semantics. Ignored for Modco. None (default) is byte-identical."
        ),
    )
    perspective: Literal["reinsurer", "cedant"] = Field(
        default="reinsurer",
        description=(
            "Profit-test perspective (ADR-078). 'reinsurer' reports the ceded "
            "economics re-viewed as NET (matches POST /api/v1/price and "
            "polaris price / scenario); 'cedant' reports the cedant's retained "
            "net position. When no treaty is configured the reinsurer view is "
            "undefined and is downgraded to 'cedant'."
        ),
    )


class ScenarioSummary(BaseModel):
    """Results for a single scenario."""

    scenario_name: str
    pv_profits: float
    profit_margin: float | None  # None when pv_premiums <= 0 (ADR-041)
    irr: float | None


class ScenarioResponse(BaseModel):
    """Response body for /api/v1/scenario."""

    scenarios: list[ScenarioSummary]
    n_scenarios: int
    perspective: Literal["reinsurer", "cedant"] = Field(
        description="Effective profit-test perspective that produced these results (ADR-078)."
    )


class UQRequest(BaseModel):
    """Request body for /api/v1/uq."""

    policies: list[PolicyInput] = Field(min_length=1)
    product_type: str = Field(
        default="TERM", description="Product type: 'TERM', 'WHOLE_LIFE', or 'UL'."
    )
    treaty_type: str | None = Field(
        default="YRT", description="Treaty type: 'YRT', 'Coinsurance', 'Modco', or null."
    )
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(ge=0.0, le=1.0, default=0.06)
    hurdle_rate: float = Field(ge=0.0, le=1.0, default=0.10)
    cession_pct: float = Field(ge=0.0, le=1.0, default=0.90)
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001)
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05)
    n_scenarios: int = Field(ge=10, le=10_000, default=200)
    seed: int = Field(default=42)
    mortality_log_sigma: float = Field(ge=0.0, le=1.0, default=0.10)
    lapse_log_sigma: float = Field(ge=0.0, le=1.0, default=0.15)
    interest_rate_sigma: float = Field(ge=0.0, le=0.10, default=0.005)
    acquisition_cost_per_policy: float = Field(default=0.0, ge=0.0)
    maintenance_cost_per_policy_per_year: float = Field(default=0.0, ge=0.0)
    yrt_loading: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Loading over expected mortality for YRT rate derivation.",
    )
    modco_interest_rate: float = Field(default=0.045, ge=0.0, le=0.20)
    expense_allowance: ExpenseAllowance | None = Field(
        default=None,
        description=(
            "Optional sliding-scale expense allowance threaded onto the YRT / "
            "Coinsurance treaty (expense-allowance epic, ADR-119). See "
            "/api/v1/price for the semantics. Ignored for Modco. None (default) "
            "is byte-identical."
        ),
    )
    experience_refund: ExperienceRefund | None = Field(
        default=None,
        description=(
            "Optional experience refund threaded onto the YRT / Coinsurance "
            "treaty (expense-allowance epic, ADR-121). See /api/v1/price for the "
            "semantics. Ignored for Modco. None (default) is byte-identical."
        ),
    )
    perspective: Literal["reinsurer", "cedant"] = Field(
        default="reinsurer",
        description=(
            "Profit-test perspective (ADR-078). 'reinsurer' reports the ceded "
            "economics re-viewed as NET (matches polaris price / scenario / uq); "
            "'cedant' reports the cedant's retained net position. When no treaty "
            "is configured the reinsurer view is undefined and is downgraded to "
            "'cedant'."
        ),
    )


class UQResponse(BaseModel):
    """Response body for /api/v1/uq."""

    n_scenarios: int
    seed: int
    base_pv_profit: float
    base_irr: float | None
    p5_pv_profit: float
    p50_pv_profit: float
    p95_pv_profit: float
    var_95: float
    cvar_95: float
    p5_profit_margin: float
    p50_profit_margin: float
    p95_profit_margin: float
    perspective: Literal["reinsurer", "cedant"] = Field(
        description="Effective profit-test perspective that produced these results (ADR-078)."
    )


class IFRS17Request(BaseModel):
    """Request body for IFRS 17 measurement endpoints."""

    policies: list[PolicyInput] = Field(min_length=1)
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(
        ge=0.0, le=1.0, default=0.04, description="IFRS 17 risk-free rate."
    )
    ra_factor: float = Field(ge=0.0, le=0.50, default=0.05, description="RA as % of BEL.")
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001)
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05)


class IFRS17Response(BaseModel):
    """Response body for IFRS 17 measurement endpoints."""

    approach: str
    initial_bel: float
    initial_ra: float
    initial_csm: float
    loss_component: float
    total_initial_liability: float
    insurance_liability: list[float]
    bel: list[float]
    risk_adjustment: list[float]
    csm: list[float]
    csm_release: list[float]
    insurance_revenue: list[float]
    insurance_service_result: list[float]


class IFRS17MovementRequest(BaseModel):
    """Request body for the IFRS 17 analysis-of-change (movement) table.

    Policies are grouped into **annual issue-year cohorts** by their
    ``issue_date``; each cohort is measured BBA at its own locked-in discount
    rate and rolled forward into an opening→closing movement table. All policies
    must share a common ``valuation_date`` so the cohort schedules align on one
    calendar grid (the cohort manager raises otherwise).
    """

    policies: list[PolicyInput] = Field(min_length=1)
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(
        ge=0.0,
        le=1.0,
        default=0.04,
        description="Default IFRS 17 locked-in rate for any cohort not listed in "
        "`locked_in_rates`.",
    )
    ra_factor: float = Field(ge=0.0, le=0.50, default=0.05, description="RA as % of BEL.")
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001)
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05)
    months_per_period: int = Field(
        ge=1,
        le=120,
        default=12,
        description="Months aggregated into each reporting period (12 = annual).",
    )
    locked_in_rates: dict[int, float] | None = Field(
        default=None,
        description="Optional per-issue-year locked-in discount rate "
        "(issue year → rate). Cohorts without an entry use `discount_rate`.",
    )


class IFRS17MovementResponse(BaseModel):
    """Response body for the IFRS 17 movement table.

    ``aggregate`` and each entry of ``cohorts`` are the serialised
    :class:`~polaris_re.analytics.ifrs17.IFRS17MovementTable` (table metadata +
    per-period rows, each row carrying the BEL / RA / CSM / total analysis of
    change). ``max_footing_error`` is the worst footing residual across the whole
    response — a filer can assert the disclosure foots from this single number.
    """

    months_per_period: int
    n_cohorts: int
    max_footing_error: float
    aggregate: dict[str, object]
    cohorts: list[dict[str, object]]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_components(
    policies_in: list[PolicyInput],
    projection_horizon_years: int,
    discount_rate: float,
    flat_qx: float,
    flat_lapse: float,
    product_type_str: str = "TERM",
    acquisition_cost_per_policy: float = 0.0,
    maintenance_cost_per_policy_per_year: float = 0.0,
    reserve_basis: ReserveBasis = ReserveBasis.NET_PREMIUM,
    valuation_mortality: str | None = None,
) -> tuple[InforceBlock, AssumptionSet, ProjectionConfig]:
    """Convert API request data into core pipeline components (no treaty).

    Treaty construction is intentionally excluded. The YRT rate must be derived
    from the gross projection output before building the treaty (ADR-038).
    This ensures ceded premiums are always non-zero and calibrated to actual
    mortality experience in the projection.

    Args:
        policies_in: Validated policy inputs from the API request.
        projection_horizon_years: Projection term in years.
        discount_rate: Annual discount rate for present value calculations.
        flat_qx: Flat annual mortality rate for the synthetic demo table.
        flat_lapse: Flat annual lapse rate for all durations.
        acquisition_cost_per_policy: One-time acquisition expense per policy.
        maintenance_cost_per_policy_per_year: Annual per-policy maintenance expense.

    Returns:
        (InforceBlock, AssumptionSet, ProjectionConfig) ready for projection.
    """
    import os
    from pathlib import Path

    n_ages = 121 - 18  # ages 18-120 inclusive = 103 ages
    qx = np.full(n_ages, flat_qx, dtype=np.float64)
    rates_2d = qx.reshape(-1, 1)  # shape (103, 1) — ultimate-only

    # Build a synthetic flat-rate table array once, then register it under
    # all six sex/smoker key combinations so any policy mix resolves correctly.
    # The demo pipeline uses a uniform flat_qx regardless of sex/smoker status;
    # real production would use MortalityTable.load() with actual CSV files.
    all_keys: dict[str, MortalityTableArray] = {}
    for sex_val in (Sex.MALE, Sex.FEMALE):
        for smoker_val in (SmokerStatus.SMOKER, SmokerStatus.NON_SMOKER, SmokerStatus.UNKNOWN):
            key = f"{sex_val.value}_{smoker_val.value}"
            all_keys[key] = MortalityTableArray(
                rates=rates_2d.copy(),
                min_age=18,
                max_age=120,
                select_period=0,
                source_file=Path("synthetic"),
            )

    mortality = MortalityTable(
        source=MortalityTableSource.CSO_2001,
        table_name="Synthetic API (flat rate)",
        min_age=18,
        max_age=120,
        select_period_years=0,
        has_smoker_distinct_rates=False,
        tables=all_keys,
    )
    lapse = LapseAssumption.from_duration_table(
        {1: flat_lapse, 2: flat_lapse, 3: flat_lapse, "ultimate": flat_lapse}
    )

    # Prescribed statutory valuation table (Reserve-Basis Exactness epic,
    # ADR-125). ``None`` (default) leaves the statutory reserve on the
    # projection best-estimate table — byte-identical to prior responses. When
    # a named source id is supplied it is loaded server-side (static, no
    # improvement) from ``$POLARIS_DATA_DIR/mortality_tables``; an unknown id
    # raises ``PolarisValidationError``, which the endpoint maps to HTTP 422.
    valuation_table = None
    if valuation_mortality is not None:
        data_dir = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
        valuation_table = load_valuation_mortality(valuation_mortality, data_dir)

    assumptions = AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        valuation_mortality=valuation_table,
        version="api-v1",
        effective_date=date.today(),
    )

    resolved_product_type = ProductType(product_type_str)

    policies = [
        Policy(
            policy_id=p.policy_id,
            issue_age=p.issue_age,
            attained_age=p.attained_age,
            sex=Sex.MALE if p.sex.upper() == "M" else Sex.FEMALE,
            smoker_status=SmokerStatus.SMOKER if p.smoker else SmokerStatus.NON_SMOKER,
            underwriting_class=p.underwriting_class,
            face_amount=p.face_amount,
            annual_premium=p.annual_premium,
            policy_term=p.policy_term,
            duration_inforce=p.duration_inforce,
            reinsurance_cession_pct=None,
            issue_date=p.issue_date,
            valuation_date=p.valuation_date,
            product_type=resolved_product_type,
            account_value=p.account_value,
            credited_rate=p.credited_rate,
        )
        for p in policies_in
    ]
    inforce = InforceBlock(policies=policies)
    # ADR-074 ingestion guard: stored duration_inforce / attained_age must
    # agree with the issue/valuation dates. Raises PolarisValidationError,
    # which every endpoint's catch-all maps to HTTP 422 — the same status
    # FastAPI uses for schema-invalid payloads, since this is the semantic
    # half of request validation.
    inforce.validate_date_consistency()

    config = ProjectionConfig(
        valuation_date=policies_in[0].valuation_date,
        projection_horizon_years=projection_horizon_years,
        discount_rate=discount_rate,
        acquisition_cost_per_policy=acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
        reserve_basis=reserve_basis,
    )

    return inforce, assumptions, config


def _run_gross_projection(
    inforce: InforceBlock,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    seriatim: bool = False,
) -> CashFlowResult:
    """Run a GROSS projection. ``seriatim=True`` populates the (N, T)
    arrays required by tabular YRT consumption (ADR-051 / ADR-052)."""
    product = get_product_engine(inforce=inforce, assumptions=assumptions, config=config)
    return product.project(seriatim=seriatim)


def _derive_yrt_rate(
    gross: CashFlowResult,
    face_amount: float,
    loading: float = 0.10,
) -> float:
    """Derive a mortality-based YRT rate per $1,000 NAR from a gross projection.

    Uses first-year actual claims divided by total face amount to estimate the
    implied annual q_x, then applies the loading factor. Mirrors the dashboard's
    ``derive_yrt_rate()`` helper (ADR-038).

    Args:
        gross: GROSS basis CashFlowResult with at least 12 months of projections.
        face_amount: Total initial in-force face amount in dollars.
        loading: YRT loading over expected mortality (e.g. 0.10 = 10%).

    Returns:
        YRT rate per $1,000 NAR (annual).
    """
    first_year_claims = float(gross.death_claims[:12].sum())
    implied_qx = first_year_claims / face_amount if face_amount > 0 else 0.001
    return implied_qx * 1000.0 * (1.0 + loading)


def _ceded_to_reinsurer_view(ceded: CashFlowResult) -> CashFlowResult:
    """Re-label a CEDED CashFlowResult as NET for reinsurer profit testing.

    ProfitTester rejects CEDED basis by design (it is meaningless to profit-test
    the ceded portion from the cedant's perspective). However, the reinsurer's
    "net" position IS exactly the ceded cash flows. This helper creates a copy
    with ``basis="NET"`` so ProfitTester accepts it (ADR-039).
    """
    return CashFlowResult(
        run_id=ceded.run_id,
        valuation_date=ceded.valuation_date,
        basis="NET",
        assumption_set_version=ceded.assumption_set_version,
        product_type=ceded.product_type,
        block_id=ceded.block_id,
        projection_months=ceded.projection_months,
        time_index=ceded.time_index,
        gross_premiums=ceded.gross_premiums,
        death_claims=ceded.death_claims,
        lapse_surrenders=ceded.lapse_surrenders,
        expenses=ceded.expenses,
        reserve_balance=ceded.reserve_balance,
        reserve_increase=ceded.reserve_increase,
        net_cash_flow=ceded.net_cash_flow,
    )


def _build_treaty(
    treaty_type: str | None,
    gross: CashFlowResult,
    face_amount: float,
    cession_pct: float = 0.90,
    yrt_loading: float = 0.10,
    modco_interest_rate: float = 0.045,
    yrt_rate_table: object | None = None,
    expense_allowance: ExpenseAllowance | None = None,
    experience_refund: ExperienceRefund | None = None,
) -> BaseTreaty | None:
    """Build a treaty object based on treaty_type string.

    Returns None for gross-only (no treaty).

    When ``yrt_rate_table`` is supplied with ``treaty_type == "YRT"``,
    the treaty is constructed with the tabular schedule and the implied
    flat rate is suppressed (mutual exclusion enforced by
    ``YRTTreaty._validate_rate_source_exclusive``). The caller must pass
    an ``InforceBlock`` to ``apply()`` for the tabular path.

    ``expense_allowance`` / ``experience_refund`` (expense-allowance epic,
    ADR-119/ADR-121) are threaded onto the ``YRT`` / ``Coinsurance`` treaties —
    the only treaties that carry the fields. ``None`` (default) leaves the
    treaty byte-identical. Both are silently ignored for ``Modco`` / gross,
    which have no allowance/refund field.
    """
    if treaty_type is None:
        return None

    if treaty_type == "YRT":
        if yrt_rate_table is not None:
            from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

            if not isinstance(yrt_rate_table, YRTRateTable):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "yrt_rate_table must be a YRTRateTable instance, "
                        f"got {type(yrt_rate_table).__name__}."
                    ),
                )
            return YRTTreaty(
                treaty_name="YRT-API",
                cession_pct=cession_pct,
                total_face_amount=face_amount,
                yrt_rate_table=yrt_rate_table,
                expense_allowance=expense_allowance,
                experience_refund=experience_refund,
            )
        yrt_rate = _derive_yrt_rate(gross, face_amount, yrt_loading)
        return YRTTreaty(
            cession_pct=cession_pct,
            total_face_amount=face_amount,
            flat_yrt_rate_per_1000=yrt_rate,
            expense_allowance=expense_allowance,
            experience_refund=experience_refund,
        )
    elif treaty_type == "Coinsurance":
        from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

        return CoinsuranceTreaty(
            treaty_name="COINS-API",
            cession_pct=cession_pct,
            include_expense_allowance=True,
            expense_allowance=expense_allowance,
            experience_refund=experience_refund,
        )
    elif treaty_type == "Modco":
        from polaris_re.reinsurance.modco import ModcoTreaty

        return ModcoTreaty(
            treaty_name="MODCO-API",
            cession_pct=cession_pct,
            modco_interest_rate=modco_interest_rate,
        )

    raise HTTPException(
        status_code=400,
        detail=f"Unknown treaty_type '{treaty_type}'. Use 'YRT', 'Coinsurance', 'Modco', or null.",
    )


def _resolve_yrt_rate_table_path(rel_path: str) -> Path:
    """Resolve a server-side YRT rate-table path safely (ADR-052).

    The user-supplied ``yrt_rate_table_path`` is resolved relative to
    ``$POLARIS_DATA_DIR``. Path traversal (``..``, absolute paths
    escaping the data dir) is rejected with HTTP 400.
    """
    import os

    data_dir_env = os.environ.get("POLARIS_DATA_DIR")
    if data_dir_env is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "POLARIS_DATA_DIR environment variable must be set on the "
                "server to resolve yrt_rate_table_path."
            ),
        )
    data_root = Path(data_dir_env).resolve()
    candidate = (data_root / rel_path).resolve()
    try:
        candidate.relative_to(data_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=(f"yrt_rate_table_path must resolve inside POLARIS_DATA_DIR; got {rel_path!r}."),
        ) from exc
    if not candidate.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"yrt_rate_table_path directory not found: {rel_path}",
        )
    return candidate


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health() -> HealthResponse:
    """Liveness and readiness probe."""
    return HealthResponse(status="ok", version=polaris_re.__version__)


@app.get("/version", tags=["System"])
def version() -> dict[str, str]:
    """Return package version information."""
    import sys

    return {
        "polaris_re": polaris_re.__version__,
        "python": sys.version.split()[0],
    }


@app.get("/metrics", tags=["System"], include_in_schema=False)
def metrics() -> PlainTextResponse:
    """Expose request metrics in Prometheus text-exposition format (v0.0.4).

    Scraped by a Prometheus server (see ``deploy/prometheus/prometheus.yml``).
    Exempt from API-key auth and rate limiting (``EXEMPT_PATHS`` in
    ``api/auth.py``) so a scraper — which cannot present a key — can always
    reach it.
    """
    return PlainTextResponse(render_latest(), media_type=METRICS_CONTENT_TYPE)


@app.post("/api/v1/price", response_model=PriceResponse, tags=["Pricing"])
def price(request: PriceRequest) -> PriceResponse:
    """
    Run a full deal pricing pipeline.

    Projects the supplied inforce block through a treaty and returns profit
    metrics for both the cedant (NET basis) and the reinsurer perspectives.
    Supports TERM, WHOLE_LIFE, and UL product types via the product dispatcher.
    Supports YRT, Coinsurance, and Modco treaty types (or null for gross only).
    """
    try:
        inforce, assumptions, config = _build_components(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
            product_type_str=request.product_type,
            acquisition_cost_per_policy=request.acquisition_cost_per_policy,
            maintenance_cost_per_policy_per_year=request.maintenance_cost_per_policy_per_year,
            reserve_basis=request.reserve_basis,
            valuation_mortality=request.valuation_mortality,
        )

        # Tabular YRT rate table (ADR-052) — server-side load before the
        # gross projection so we know to enable seriatim.
        yrt_rate_table = None
        if request.yrt_rate_table_path is not None:
            from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

            table_dir = _resolve_yrt_rate_table_path(request.yrt_rate_table_path)
            yrt_rate_table = YRTRateTable.load(
                directory=table_dir,
                select_period=request.yrt_rate_table_select_period,
                table_name=request.yrt_rate_table_label or "yrt",
                label=request.yrt_rate_table_label,
                smoker_distinct=request.yrt_rate_table_smoker_distinct,
            )

        gross = _run_gross_projection(
            inforce, assumptions, config, seriatim=yrt_rate_table is not None
        )

        # Build treaty from request parameters
        total_face = sum(p.face_amount for p in request.policies)
        treaty = _build_treaty(
            treaty_type=request.treaty_type,
            gross=gross,
            face_amount=total_face,
            cession_pct=request.cession_pct,
            yrt_loading=request.yrt_loading,
            modco_interest_rate=request.modco_interest_rate,
            yrt_rate_table=yrt_rate_table,
            expense_allowance=request.expense_allowance,
            experience_refund=request.experience_refund,
        )

        if treaty is not None:
            # Tabular YRT requires inforce. The flat-rate path is
            # backward-compatible because YRTTreaty.apply() ignores
            # inforce when the tabular table is absent (cession is
            # resolved via face-weighted average — same scalar as
            # treaty.cession_pct when policies have no overrides).
            net, ceded = treaty.apply(
                gross, inforce=inforce if yrt_rate_table is not None else None
            )
        else:
            net, ceded = gross, None

        # Cedant + reinsurer profit tests, optionally with regulatory capital
        # (licat / rbc / solvency2; ADR-049/101). When capital is off the
        # original code path is taken so existing API consumers see
        # byte-identical responses.
        cedant_tester = ProfitTester(cashflows=net, hurdle_rate=request.hurdle_rate)
        reinsurer_tester: ProfitTester | None = None
        if ceded is not None:
            reinsurer_tester = ProfitTester(
                cashflows=_ceded_to_reinsurer_view(ceded),
                hurdle_rate=request.hurdle_rate,
            )

        cedant: ProfitTestResult
        reinsurer: ProfitTestResult
        if request.capital_model is None:
            cedant = cedant_tester.run()
            reinsurer = reinsurer_tester.run() if reinsurer_tester is not None else cedant
        else:
            product_type_enum = ProductType(request.product_type)
            capital_model = capital_model_for(request.capital_model, product_type_enum)
            cession_pct = request.cession_pct if treaty is not None else None
            cedant_nar = derive_capital_nar(
                gross=gross,
                reserve_balance=net.reserve_balance,
                face_amount_total=total_face,
                cession_pct=cession_pct,
                is_reinsurer=False,
            )
            cedant = cedant_tester.run_with_capital(
                capital_model, nar=cedant_nar, available_capital=request.available_capital
            )
            if reinsurer_tester is not None and ceded is not None and cession_pct is not None:
                reinsurer_nar = derive_capital_nar(
                    gross=gross,
                    reserve_balance=ceded.reserve_balance,
                    face_amount_total=total_face,
                    cession_pct=cession_pct,
                    is_reinsurer=True,
                )
                reinsurer = reinsurer_tester.run_with_capital(
                    capital_model, nar=reinsurer_nar, available_capital=request.available_capital
                )
            else:
                # Gross-only: reinsurer mirrors cedant view (existing behaviour)
                reinsurer = cedant

        # Premium sufficiency (ADR-083), computed at the valuation discount
        # rate (not the profit hurdle). Cedant on NET; reinsurer on the ceded
        # cash flows re-viewed as NET, mirroring cedant when no treaty.
        cedant_sufficiency = PremiumSufficiencyTester(
            cashflows=net,
            discount_rate=request.discount_rate,
            target_margin=request.sufficiency_target_margin,
        ).run()
        if ceded is not None:
            reinsurer_sufficiency = PremiumSufficiencyTester(
                cashflows=_ceded_to_reinsurer_view(ceded),
                discount_rate=request.discount_rate,
                target_margin=request.sufficiency_target_margin,
            ).run()
        else:
            reinsurer_sufficiency = cedant_sufficiency

        # Asset-liability duration gap (Asset/ALM epic, Slice 4b-2b). Purely
        # additive: computed only when an asset portfolio is supplied. Both sides
        # are measured at one common flat yield — the explicit
        # ``alm_valuation_yield`` when given, else the ``discount_rate`` — and the
        # reserve-backed liability streams are built at the reserve's own valuation
        # rate (``effective_valuation_rate``). The reinsurer-view (ceded reserve) is
        # the headline; for a YRT treaty the ceded reserve is ~0, so that side is
        # null and the cedant-view (net reserve) carries the gap. Mirrors the CLI
        # compute path (``dual_duration_gap``) so the two surfaces stay in parity.
        alm_gap: DualDurationGap | None = None
        if request.asset_portfolio is not None:
            gap_yield = (
                request.alm_valuation_yield
                if request.alm_valuation_yield is not None
                else request.discount_rate
            )
            dual = dual_duration_gap(
                request.asset_portfolio, net, ceded, gap_yield, config.effective_valuation_rate
            )
            alm_gap = None if dual.is_empty else dual
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cedant_capital = _capital_block(cedant)
    reinsurer_capital = _capital_block(reinsurer)

    return PriceResponse(
        hurdle_rate=cedant.hurdle_rate,
        pv_profits=cedant.pv_profits,
        pv_premiums=cedant.pv_premiums,
        profit_margin=cedant.profit_margin,
        irr=cedant.irr,
        breakeven_year=cedant.breakeven_year,
        total_undiscounted_profit=cedant.total_undiscounted_profit,
        profit_by_year=cedant.profit_by_year.tolist(),
        reinsurer_pv_profits=reinsurer.pv_profits,
        reinsurer_profit_margin=reinsurer.profit_margin,
        reinsurer_irr=reinsurer.irr,
        reinsurer_breakeven_year=reinsurer.breakeven_year,
        reinsurer_total_undiscounted_profit=reinsurer.total_undiscounted_profit,
        reinsurer_profit_by_year=reinsurer.profit_by_year.tolist(),
        peak_capital=cedant_capital["peak_capital"],
        pv_capital=cedant_capital["pv_capital"],
        pv_capital_strain=cedant_capital["pv_capital_strain"],
        return_on_capital=cedant_capital["return_on_capital"],
        capital_adjusted_irr=cedant_capital["capital_adjusted_irr"],
        available_capital=cedant_capital["available_capital"],
        capital_ratio=cedant_capital["capital_ratio"],
        reinsurer_peak_capital=reinsurer_capital["peak_capital"],
        reinsurer_pv_capital=reinsurer_capital["pv_capital"],
        reinsurer_pv_capital_strain=reinsurer_capital["pv_capital_strain"],
        reinsurer_return_on_capital=reinsurer_capital["return_on_capital"],
        reinsurer_capital_adjusted_irr=reinsurer_capital["capital_adjusted_irr"],
        reinsurer_capital_ratio=reinsurer_capital["capital_ratio"],
        premium_sufficiency=_sufficiency_block(cedant_sufficiency),
        reinsurer_premium_sufficiency=_sufficiency_block(reinsurer_sufficiency),
        n_policies=len(request.policies),
        projection_months=config.projection_months,
        reserve_basis=config.reserve_basis,
        alm_duration_gap=alm_gap,
    )


def _capital_block(result: ProfitTestResult) -> dict[str, float | None]:
    """Extract the regulatory-capital fields from a profit-test result.

    Returns all-None when ``result`` is a plain ``ProfitTestResult`` so
    the API response gracefully omits the block when the capital model
    was not requested (ADR-049).
    """
    if not isinstance(result, ProfitResultWithCapital):
        return {
            "peak_capital": None,
            "pv_capital": None,
            "pv_capital_strain": None,
            "return_on_capital": None,
            "capital_adjusted_irr": None,
            "available_capital": None,
            "capital_ratio": None,
        }
    return {
        "peak_capital": float(result.peak_capital),
        "pv_capital": float(result.pv_capital),
        "pv_capital_strain": float(result.pv_capital_strain),
        "return_on_capital": result.return_on_capital,
        "capital_adjusted_irr": result.capital_adjusted_irr,
        # ADR-104: None unless available_capital was supplied on the request.
        "available_capital": result.available_capital,
        "capital_ratio": result.capital_ratio,
    }


def _sufficiency_block(result: PremiumSufficiencyResult) -> dict[str, float | bool | None]:
    """Flatten a PremiumSufficiencyResult into a response dict (ADR-083)."""
    return {
        "discount_rate": result.discount_rate,
        "target_margin": result.target_margin,
        "pv_premiums": result.pv_premiums,
        "pv_claims": result.pv_claims,
        "pv_surrenders": result.pv_surrenders,
        "pv_benefits": result.pv_benefits,
        "pv_expenses": result.pv_expenses,
        "sufficiency_margin": result.sufficiency_margin,
        "sufficiency_ratio": result.sufficiency_ratio,
        "loss_ratio": result.loss_ratio,
        "expense_ratio": result.expense_ratio,
        "combined_ratio": result.combined_ratio,
        "is_sufficient": result.is_sufficient,
    }


def _resolve_api_perspective(
    perspective: Literal["reinsurer", "cedant"], *, has_treaty: bool
) -> Literal["reinsurer", "cedant"]:
    """Resolve the requested profit-test perspective for scenario / uq (ADR-078).

    When the deal carries no real treaty the reinsurer (ceded) view is
    undefined, so a requested ``"reinsurer"`` perspective is downgraded to
    ``"cedant"`` — mirroring ``polaris price`` ("reinsurer view not
    available") and the CLI ``scenario`` / ``uq`` commands (ADR-077). The
    effective perspective is returned so it can be surfaced in the response.
    """
    if perspective == "reinsurer" and not has_treaty:
        return "cedant"
    return perspective


@app.post("/api/v1/scenario", response_model=ScenarioResponse, tags=["Pricing"])
def scenario(request: ScenarioRequest) -> ScenarioResponse:
    """
    Run standard stress scenario analysis.

    Applies pre-defined stress scenarios (mortality shock, lapse stress,
    rate shock) to the base assumptions and returns comparative profit metrics.
    The YRT rate is derived from the base gross projection (ADR-038) so that
    the treaty is correctly calibrated before stress scenarios are applied.
    """
    try:
        inforce, assumptions, config = _build_components(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
            product_type_str=request.product_type,
            acquisition_cost_per_policy=request.acquisition_cost_per_policy,
            maintenance_cost_per_policy_per_year=request.maintenance_cost_per_policy_per_year,
        )
        gross = _run_gross_projection(inforce, assumptions, config)
        total_face = sum(p.face_amount for p in request.policies)
        treaty = _build_treaty(
            treaty_type=request.treaty_type,
            gross=gross,
            face_amount=total_face,
            cession_pct=request.cession_pct,
            yrt_loading=request.yrt_loading,
            modco_interest_rate=request.modco_interest_rate,
            expense_allowance=request.expense_allowance,
            experience_refund=request.experience_refund,
        )
        # Reinsurer view requires a real ceded position (ADR-078); resolve
        # before the zero-cession passthrough fallback below.
        effective_perspective = _resolve_api_perspective(
            request.perspective, has_treaty=treaty is not None
        )
        # ScenarioRunner requires a treaty; use zero-cession YRT as passthrough if None
        if treaty is None:
            yrt_rate = _derive_yrt_rate(gross, total_face)
            treaty = YRTTreaty(
                cession_pct=0.0,
                total_face_amount=total_face,
                flat_yrt_rate_per_1000=yrt_rate,
            )
        runner = ScenarioRunner(
            inforce=inforce,
            base_assumptions=assumptions,
            config=config,
            treaty=treaty,
            hurdle_rate=request.hurdle_rate,
            perspective=effective_perspective,
        )
        results = runner.run()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    summaries = [
        ScenarioSummary(
            scenario_name=name,
            pv_profits=res.pv_profits,
            profit_margin=res.profit_margin,
            irr=res.irr,
        )
        for name, res in results.scenarios
    ]
    return ScenarioResponse(
        scenarios=summaries,
        n_scenarios=len(summaries),
        perspective=effective_perspective,
    )


@app.post("/api/v1/uq", response_model=UQResponse, tags=["Pricing"])
def uq(request: UQRequest) -> UQResponse:
    """
    Run Monte Carlo uncertainty quantification.

    Samples assumption multipliers from LogNormal (mortality, lapse) and
    Normal (interest rate) distributions and returns the distribution of
    deal profitability metrics. The YRT rate is derived from the base gross
    projection (ADR-038) so that the treaty is calibrated before sampling.
    """
    try:
        inforce, assumptions, config = _build_components(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
            product_type_str=request.product_type,
            acquisition_cost_per_policy=request.acquisition_cost_per_policy,
            maintenance_cost_per_policy_per_year=request.maintenance_cost_per_policy_per_year,
        )
        gross = _run_gross_projection(inforce, assumptions, config)
        total_face = sum(p.face_amount for p in request.policies)
        treaty = _build_treaty(
            treaty_type=request.treaty_type,
            gross=gross,
            face_amount=total_face,
            cession_pct=request.cession_pct,
            yrt_loading=request.yrt_loading,
            modco_interest_rate=request.modco_interest_rate,
            expense_allowance=request.expense_allowance,
            experience_refund=request.experience_refund,
        )
        # Reinsurer view requires a real ceded position (ADR-078); MonteCarloUQ
        # accepts treaty=None directly, so resolve against treaty presence.
        effective_perspective = _resolve_api_perspective(
            request.perspective, has_treaty=treaty is not None
        )
        uq_runner = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumptions,
            base_config=config,
            treaty=treaty,
            hurdle_rate=request.hurdle_rate,
            n_scenarios=request.n_scenarios,
            seed=request.seed,
            params=UQParameters(
                mortality_log_sigma=request.mortality_log_sigma,
                lapse_log_sigma=request.lapse_log_sigma,
                interest_rate_sigma=request.interest_rate_sigma,
            ),
            perspective=effective_perspective,
        )
        result = uq_runner.run()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    p5 = result.percentile(5)
    p50 = result.percentile(50)
    p95 = result.percentile(95)

    return UQResponse(
        n_scenarios=result.n_scenarios,
        seed=result.seed,
        base_pv_profit=result.base_pv_profit,
        base_irr=result.base_irr,
        p5_pv_profit=p5["pv_profit"],
        p50_pv_profit=p50["pv_profit"],
        p95_pv_profit=p95["pv_profit"],
        var_95=result.var(0.95),
        cvar_95=result.cvar(0.95),
        p5_profit_margin=p5["profit_margin"],
        p50_profit_margin=p50["profit_margin"],
        p95_profit_margin=p95["profit_margin"],
        perspective=effective_perspective,
    )


@app.post("/api/v1/ifrs17/bba", response_model=IFRS17Response, tags=["IFRS 17"])
def ifrs17_bba(request: IFRS17Request) -> IFRS17Response:
    """
    Compute IFRS 17 Building Block Approach (BBA) measurement.

    Returns the full insurance liability roll-forward including BEL,
    Risk Adjustment, CSM schedule, and P&L components.
    """
    try:
        inforce, assumptions, config = _build_components(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
        )
        gross = _run_gross_projection(inforce, assumptions, config)
        measurement = IFRS17Measurement(
            cashflows=gross,
            discount_rate=request.discount_rate,
            ra_factor=request.ra_factor,
        )
        result = measurement.measure_bba()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return IFRS17Response(
        approach=result.approach,
        initial_bel=result.initial_bel,
        initial_ra=result.initial_ra,
        initial_csm=result.initial_csm,
        loss_component=result.loss_component,
        total_initial_liability=result.total_initial_liability(),
        insurance_liability=result.insurance_liability.tolist(),
        bel=result.bel.tolist(),
        risk_adjustment=result.risk_adjustment.tolist(),
        csm=result.csm.tolist(),
        csm_release=result.csm_release.tolist(),
        insurance_revenue=result.insurance_revenue.tolist(),
        insurance_service_result=result.insurance_service_result.tolist(),
    )


@app.post("/api/v1/ifrs17/paa", response_model=IFRS17Response, tags=["IFRS 17"])
def ifrs17_paa(request: IFRS17Request) -> IFRS17Response:
    """
    Compute IFRS 17 Premium Allocation Approach (PAA) measurement.

    Returns LRC (Liability for Remaining Coverage) and LIC (Liability
    for Incurred Claims) schedules for short-duration contracts.
    """
    try:
        inforce, assumptions, config = _build_components(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
        )
        gross = _run_gross_projection(inforce, assumptions, config)
        measurement = IFRS17Measurement(
            cashflows=gross,
            discount_rate=request.discount_rate,
            ra_factor=request.ra_factor,
        )
        result = measurement.measure_paa()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return IFRS17Response(
        approach=result.approach,
        initial_bel=result.initial_bel,
        initial_ra=result.initial_ra,
        initial_csm=result.initial_csm,
        loss_component=result.loss_component,
        total_initial_liability=result.total_initial_liability(),
        insurance_liability=result.insurance_liability.tolist(),
        bel=result.bel.tolist(),
        risk_adjustment=result.risk_adjustment.tolist(),
        csm=result.csm.tolist(),
        csm_release=result.csm_release.tolist(),
        insurance_revenue=result.insurance_revenue.tolist(),
        insurance_service_result=result.insurance_service_result.tolist(),
    )


@app.post(
    "/api/v1/ifrs17/movement",
    response_model=IFRS17MovementResponse,
    tags=["IFRS 17"],
)
def ifrs17_movement(request: IFRS17MovementRequest) -> IFRS17MovementResponse:
    """
    Compute the IFRS 17 analysis-of-change (movement) table.

    Policies are grouped into annual issue-year cohorts; each cohort is measured
    BBA at its own locked-in discount rate and rolled forward into an
    opening → new business → interest accretion → release → closing
    reconciliation for BEL, RA and CSM. Returns the per-cohort tables (ordered by
    issue year) and the aggregate, each foots by construction.
    """
    try:
        # Group the request's policies by issue-year cohort, project each group
        # on the shared calendar grid, and feed one aggregated contract per
        # cohort to the IFRS 17 cohort manager.
        cohort_groups: dict[int, list[PolicyInput]] = {}
        for policy in request.policies:
            cohort_groups.setdefault(policy.issue_date.year, []).append(policy)

        rate_overrides = request.locked_in_rates or {}
        contracts: list[IFRS17ContractInput] = []
        for issue_year in sorted(cohort_groups):
            members = cohort_groups[issue_year]
            locked_in_rate = rate_overrides.get(issue_year, request.discount_rate)
            inforce, assumptions, config = _build_components(
                policies_in=members,
                projection_horizon_years=request.projection_horizon_years,
                discount_rate=locked_in_rate,
                flat_qx=request.flat_qx,
                flat_lapse=request.flat_lapse,
            )
            gross = _run_gross_projection(inforce, assumptions, config)
            contracts.append(
                IFRS17ContractInput(
                    cashflows=gross,
                    issue_date=members[0].issue_date,
                    locked_in_rate=locked_in_rate,
                    ra_factor=request.ra_factor,
                )
            )

        manager = IFRS17CohortManager(contracts)
        aggregate = manager.aggregate_movement_table(months_per_period=request.months_per_period)
        cohort_tables = manager.cohort_movement_tables(months_per_period=request.months_per_period)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    max_footing_error = max(
        [aggregate.max_footing_error(), *(t.max_footing_error() for t in cohort_tables)]
    )

    return IFRS17MovementResponse(
        months_per_period=request.months_per_period,
        n_cohorts=manager.n_cohorts,
        max_footing_error=max_footing_error,
        aggregate=aggregate.to_dict(),
        cohorts=[t.to_dict() for t in cohort_tables],
    )


# =========================================================================
# POST /api/v1/ingest — Cedant inforce data ingestion
# =========================================================================


class IngestCurrency(BaseModel):
    """Static currency conversion applied to monetary columns during coercion."""

    code: str = Field(description="ISO code of the source currency, e.g. 'CAD'.")
    rate: float = Field(
        gt=0.0, description="Multiplicative rate converting source → reporting currency."
    )


class IngestColumnMapping(BaseModel):
    """Column mapping + value-coercion configuration from source to Polaris RE schema.

    The coercion fields (``unit_scale`` / ``premium_mode`` / ``currency`` /
    ``date_columns`` / ``date_formats``, A3' Slice 2-3) all default to a no-op, so
    a request that does not set them behaves exactly as before.
    """

    column_mapping: dict[str, str] = Field(description="Maps Polaris field → source column name.")
    code_translations: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Per-field code translations."
    )
    defaults: dict[str, str | float | int] = Field(
        default_factory=dict, description="Default values for missing fields."
    )
    unit_scale: dict[str, float] = Field(
        default_factory=dict,
        description="Per-column multiplicative scale (e.g. {'face_amount': 1000.0}).",
    )
    premium_mode: Literal["annual", "semiannual", "quarterly", "monthly"] = Field(
        default="annual",
        description="Reporting frequency of annual_premium; non-annual values are annualised.",
    )
    currency: IngestCurrency | None = Field(
        default=None, description="Optional static currency conversion of monetary columns."
    )
    date_columns: list[str] = Field(
        default_factory=list,
        description="Columns to coerce to canonical ISO dates. Empty = no coercion.",
    )
    date_formats: dict[str, str] = Field(
        default_factory=dict,
        description="Explicit source strftime format per date column (overrides inference).",
    )


class IngestRequest(BaseModel):
    """Request body for inforce data ingestion."""

    policies: list[dict[str, str | float | int]] = Field(
        description="Raw policy records as list of dicts."
    )
    mapping: IngestColumnMapping = Field(description="Column mapping configuration.")


class IngestResponse(BaseModel):
    """Response body for inforce data ingestion.

    Summary statistics describe the *clean* block (usable rows). The
    quarantine fields (``n_input`` / ``n_rejected`` / ``reject_reasons`` /
    ``rejects``) enumerate rows that could not be priced and why; for a fully
    clean block ``n_rejected`` is 0 and ``rejects`` is empty (back-compatible).
    """

    n_policies: int = Field(description="Number of clean policies ingested.")
    total_face_amount: float = Field(description="Total face amount (clean block).")
    mean_age: float = Field(description="Mean attained age (clean block).")
    sex_split: dict[str, int] = Field(description="Count by sex (clean block).")
    smoker_split: dict[str, int] = Field(description="Count by smoker status (clean block).")
    errors: list[str] = Field(description="Validation errors on the clean block.")
    warnings: list[str] = Field(description="Coercion + validation warnings.")
    policies: list[dict[str, str | float | int | None]] = Field(
        description="Normalised clean policy records."
    )
    n_input: int = Field(default=0, description="Total rows examined before quarantine.")
    n_rejected: int = Field(default=0, description="Rows quarantined as unusable.")
    reject_reasons: dict[str, int] = Field(
        default_factory=dict, description="Per-rule count of rejected rows."
    )
    rejects: list[dict[str, str | float | int | None]] = Field(
        default_factory=list,
        description="Quarantined rows, each carrying a '_reject_reason' column.",
    )


@app.post("/api/v1/ingest", response_model=IngestResponse)
def api_ingest(request: IngestRequest) -> IngestResponse:
    """Ingest raw cedant inforce data: apply column mapping and validate."""
    import polars as pl

    from polaris_re.utils.ingestion import (
        CurrencyConfig,
        IngestConfig,
        apply_value_coercion,
        partition_inforce_rows,
    )

    try:
        df = pl.DataFrame(request.policies)

        currency = (
            CurrencyConfig(code=request.mapping.currency.code, rate=request.mapping.currency.rate)
            if request.mapping.currency is not None
            else None
        )
        config = IngestConfig(
            column_mapping=request.mapping.column_mapping,
            code_translations=request.mapping.code_translations,
            defaults=request.mapping.defaults,
            unit_scale=request.mapping.unit_scale,
            premium_mode=request.mapping.premium_mode,
            currency=currency,
            date_columns=request.mapping.date_columns,
            date_formats=request.mapping.date_formats,
        )

        # Apply rename
        rename_map: dict[str, str] = {}
        for polaris_field, source_col in config.column_mapping.items():
            if source_col in df.columns:
                rename_map[source_col] = polaris_field
        df = df.rename(rename_map)

        # Apply code translations
        for field_name, translation in config.code_translations.items():
            if field_name in df.columns:
                df = df.with_columns(
                    pl.col(field_name).cast(pl.Utf8).replace(translation).alias(field_name)
                )

        # Apply defaults
        for field_name, default_value in config.defaults.items():
            if field_name not in df.columns:
                df = df.with_columns(pl.lit(default_value).alias(field_name))

        # Coerce messy values (mixed dates, unit/currency — config-gated), then
        # quarantine rows that still cannot be priced (A3' Slice 3, ADR-138).
        df, coercion_warnings = apply_value_coercion(df, config)
        clean_df, rejects_df, report = partition_inforce_rows(df)

        policies_out = clean_df.to_dicts()
        rejects_out = rejects_df.to_dicts()

    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return IngestResponse(
        n_policies=report.n_policies,
        total_face_amount=report.total_face_amount,
        mean_age=report.mean_age,
        sex_split=report.sex_split,
        smoker_split=report.smoker_split,
        errors=report.errors,
        warnings=coercion_warnings + report.warnings,
        policies=policies_out,
        n_input=report.n_input,
        n_rejected=report.n_rejected,
        reject_reasons=report.reject_reasons,
        rejects=rejects_out,
    )


# =========================================================================
# POST /api/v1/rate-schedule — YRT Rate Schedule Generator
# =========================================================================


class RateScheduleRequest(BaseModel):
    """Request body for YRT rate schedule generation."""

    target_irr: float = Field(default=0.10, ge=0.0, le=1.0, description="Target annual IRR.")
    ages: list[int] = Field(
        default=[25, 30, 35, 40, 45, 50, 55, 60],
        description="Issue ages to include in the schedule.",
    )
    policy_term: int = Field(default=20, ge=1, le=50, description="Policy term in years.")
    policies_in: int = Field(default=5, description="Demo: number of policies (ignored).")
    flat_qx: float = Field(default=0.004, description="Demo: flat annual mortality rate.")
    flat_lapse: float = Field(default=0.03, description="Demo: flat annual lapse rate.")
    discount_rate: float = Field(default=0.05, description="Annual discount rate.")


class RateScheduleResponse(BaseModel):
    """Response body for YRT rate schedule."""

    target_irr: float
    n_cells: int
    schedule: list[dict[str, float | str | int | None]]


@app.post("/api/v1/rate-schedule", response_model=RateScheduleResponse)
def api_rate_schedule(request: RateScheduleRequest) -> RateScheduleResponse:
    """Generate a YRT rate schedule solving for rates that achieve target IRR.

    Builds a synthetic flat-rate assumption set from the request parameters and
    solves for the per-$1,000 NAR YRT rate at each age/sex/smoker cell that
    achieves the requested target IRR.
    """
    from polaris_re.analytics.rate_schedule import YRTRateSchedule

    try:
        # Build synthetic assumptions using the shared helper.
        # A dummy single-policy request is not needed — _build_components() is
        # designed for inforce inputs, so we construct assumptions + config directly
        # here using the same pattern as _build_components() internally.
        from pathlib import Path

        n_ages = 121 - 18
        qx = np.full(n_ages, request.flat_qx, dtype=np.float64)
        rates_2d = qx.reshape(-1, 1)

        all_keys: dict[str, MortalityTableArray] = {}
        for sex_val in (Sex.MALE, Sex.FEMALE):
            for smoker_val in (SmokerStatus.SMOKER, SmokerStatus.NON_SMOKER, SmokerStatus.UNKNOWN):
                key = f"{sex_val.value}_{smoker_val.value}"
                all_keys[key] = MortalityTableArray(
                    rates=rates_2d.copy(),
                    min_age=18,
                    max_age=120,
                    select_period=0,
                    source_file=Path("synthetic"),
                )

        mortality = MortalityTable(
            source=MortalityTableSource.CSO_2001,
            table_name="Synthetic API (flat rate)",
            min_age=18,
            max_age=120,
            select_period_years=0,
            has_smoker_distinct_rates=False,
            tables=all_keys,
        )
        lapse = LapseAssumption.from_duration_table(
            {
                1: request.flat_lapse,
                2: request.flat_lapse,
                3: request.flat_lapse,
                "ultimate": request.flat_lapse,
            }
        )
        assumptions = AssumptionSet(
            mortality=mortality,
            lapse=lapse,
            version="api-v1",
        )
        config = ProjectionConfig(
            valuation_date=date.today(),
            projection_horizon_years=request.policy_term,
            discount_rate=request.discount_rate,
        )

        scheduler = YRTRateSchedule(
            assumptions=assumptions,
            config=config,
            target_irr=request.target_irr,
        )

        result_df = scheduler.generate(
            ages=request.ages,
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
            policy_term=request.policy_term,
        )

        schedule = result_df.to_dicts()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RateScheduleResponse(
        target_irr=request.target_irr,
        n_cells=len(schedule),
        schedule=schedule,
    )


# =========================================================================
# POST /api/v1/portfolio — Multi-deal portfolio aggregation (ADR-057 Slice 2)
# =========================================================================


class PortfolioDealRequest(BaseModel):
    """One deal entry in a portfolio request.

    Carries everything ``PriceRequest`` accepts (policies, treaty,
    assumptions) plus a ``deal_id`` and ``cedant`` label used for the
    portfolio's per-deal breakdown and concentration metrics. Stop-loss
    and other non-proportional structures are out of scope for Slice 2 —
    ``treaty_type`` must be one of ``YRT`` / ``Coinsurance`` / ``Modco``.
    """

    deal_id: str = Field(description="Unique identifier for the deal within the portfolio.")
    cedant: str = Field(description="Ceding company label — used as the concentration key.")
    policies: list[PolicyInput] = Field(
        min_length=1, description="List of policies covered by this deal."
    )
    product_type: str = Field(
        default="TERM", description="Product type: 'TERM', 'WHOLE_LIFE', or 'UL'."
    )
    treaty_type: str = Field(
        default="YRT",
        description=(
            "Treaty type — proportional only: 'YRT', 'Coinsurance', or 'Modco'. "
            "Stop-loss and 'None'/gross-only are rejected (a portfolio is a book "
            "of ceded positions)."
        ),
    )
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(ge=0.0, le=1.0, default=0.06)
    cession_pct: float = Field(ge=0.0, le=1.0, default=0.90)
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001)
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05)
    acquisition_cost_per_policy: float = Field(default=0.0, ge=0.0)
    maintenance_cost_per_policy_per_year: float = Field(default=0.0, ge=0.0)
    yrt_loading: float = Field(default=0.10, ge=0.0, le=1.0)
    modco_interest_rate: float = Field(default=0.045, ge=0.0, le=0.20)
    expense_allowance: ExpenseAllowance | None = Field(
        default=None,
        description=(
            "Optional sliding-scale expense allowance threaded onto this deal's "
            "YRT / Coinsurance treaty (expense-allowance epic, ADR-119). See "
            "/api/v1/price for the semantics. Ignored for Modco. None (default) "
            "is byte-identical."
        ),
    )
    experience_refund: ExperienceRefund | None = Field(
        default=None,
        description=(
            "Optional experience refund threaded onto this deal's YRT / "
            "Coinsurance treaty (expense-allowance epic, ADR-121). See "
            "/api/v1/price for the semantics. Ignored for Modco. None (default) "
            "is byte-identical."
        ),
    )


class PortfolioRequest(BaseModel):
    """Request body for ``POST /api/v1/portfolio``."""

    hurdle_rate: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Annual hurdle rate applied uniformly to every deal and to the aggregate.",
    )
    deals: list[PortfolioDealRequest] = Field(
        min_length=1, description="One entry per reinsurance deal in the portfolio."
    )
    name: str = Field(default="portfolio", description="Portfolio identifier (used in run id).")
    align: Literal["strict", "calendar"] = Field(
        default="strict",
        description=(
            "Time-alignment mode (ADR-061). 'strict' (default) sums cash flows by "
            "month index and requires every deal to share a valuation date. "
            "'calendar' places each deal on a common monthly grid keyed off the "
            "earliest valuation date so deals with different inception dates "
            "aggregate correctly; total_pv_profits then reports the portfolio "
            "NPV as of the common origin (NOT the naive sum of per-deal PVs)."
        ),
    )


def _portfolio_from_request_deals(
    name: str,
    deals: list[PortfolioDealRequest],
) -> "Portfolio":
    """Build a :class:`~polaris_re.analytics.portfolio.Portfolio` from a
    sequence of :class:`PortfolioDealRequest` payloads.

    Mirrors the per-deal build pipeline used by :func:`api_portfolio` so that
    both ``POST /api/v1/portfolio`` and the scenarios endpoint
    (:func:`api_portfolio_scenarios`) consume identical request shapes and
    produce identical book objects.

    Raises :class:`HTTPException` for any validation failure (bad treaty
    type, unbuildable treaty, etc.) so the FastAPI handler can re-raise
    without losing the 400 status code.
    """
    from polaris_re.analytics.portfolio import Portfolio

    portfolio = Portfolio(name=name)
    for deal_req in deals:
        inforce, assumptions, config = _build_components(
            policies_in=deal_req.policies,
            projection_horizon_years=deal_req.projection_horizon_years,
            discount_rate=deal_req.discount_rate,
            flat_qx=deal_req.flat_qx,
            flat_lapse=deal_req.flat_lapse,
            product_type_str=deal_req.product_type,
            acquisition_cost_per_policy=deal_req.acquisition_cost_per_policy,
            maintenance_cost_per_policy_per_year=deal_req.maintenance_cost_per_policy_per_year,
        )

        # Portfolio rejects non-proportional treaties via Portfolio.add_deal,
        # but reject empty/null treaties up front so the error is a clean 400.
        if deal_req.treaty_type not in ("YRT", "Coinsurance", "Modco"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Deal {deal_req.deal_id!r}: treaty_type must be 'YRT', "
                    f"'Coinsurance', or 'Modco'; got {deal_req.treaty_type!r}."
                ),
            )

        # YRT needs a rate — derive from the gross projection (mirrors /api/v1/price).
        gross_for_yrt_rate = None
        if deal_req.treaty_type == "YRT":
            gross_for_yrt_rate = _run_gross_projection(inforce, assumptions, config)

        total_face = sum(p.face_amount for p in deal_req.policies)
        treaty = _build_treaty(
            treaty_type=deal_req.treaty_type,
            gross=gross_for_yrt_rate,  # type: ignore[arg-type]
            face_amount=total_face,
            cession_pct=deal_req.cession_pct,
            yrt_loading=deal_req.yrt_loading,
            modco_interest_rate=deal_req.modco_interest_rate,
            expense_allowance=deal_req.expense_allowance,
            experience_refund=deal_req.experience_refund,
        )
        if treaty is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Deal {deal_req.deal_id!r}: could not build a treaty for "
                    f"treaty_type={deal_req.treaty_type!r}."
                ),
            )
        portfolio.add_deal(
            deal_id=deal_req.deal_id,
            cedant=deal_req.cedant,
            inforce=inforce,
            assumptions=assumptions,
            config=config,
            treaty=treaty,
        )
    return portfolio


@app.post("/api/v1/portfolio", tags=["Pricing"])
def api_portfolio(request: PortfolioRequest) -> dict:  # type: ignore[type-arg]
    """Run a multi-deal portfolio and return aggregate reinsurer-level metrics.

    Projects every deal, applies its proportional treaty, and aggregates
    the reinsurer-side cash flows into total PV profits, total IRR, and
    concentration metrics by cedant, product type, and treaty type. The
    response shape mirrors ``PortfolioResult.to_dict()`` — see ADR-057.
    """
    try:
        portfolio = _portfolio_from_request_deals(request.name, request.deals)
        result = portfolio.run(request.hurdle_rate, align=request.align)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result.to_dict()


# =========================================================================
# POST /api/v1/portfolio/scenarios — Multi-scenario portfolio stress (ADR-066)
# =========================================================================


class PortfolioScenariosRequest(BaseModel):
    """Request body for ``POST /api/v1/portfolio/scenarios``.

    Carries the same deal list as :class:`PortfolioRequest` plus an optional
    ``scenarios`` list of scenario names drawn from
    :meth:`polaris_re.analytics.scenario.ScenarioRunner.standard_stress_scenarios`.
    When omitted, the deal-committee six-scenario set is used.
    """

    hurdle_rate: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Annual hurdle rate applied uniformly to every scenario's aggregate.",
    )
    deals: list[PortfolioDealRequest] = Field(
        min_length=1, description="One entry per reinsurance deal in the portfolio."
    )
    name: str = Field(default="portfolio", description="Portfolio identifier (used in run id).")
    align: Literal["strict", "calendar"] = Field(
        default="strict",
        description=(
            "Time-alignment mode (ADR-061). 'strict' (default) requires every "
            "deal to share a valuation date. 'calendar' places each deal on a "
            "common monthly grid keyed off the earliest valuation date. The "
            "mode is forwarded unchanged to every scenario's aggregate run."
        ),
    )
    scenarios: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of scenario names drawn from the standard six-scenario "
            "set (BASE, MORT_110, MORT_90, LAPSE_80, LAPSE_120, MORT_110_LAPSE_80). "
            "Order is preserved in the response. Omit (or pass null) to run the "
            "full standard set. An empty list is rejected — pass null instead."
        ),
    )


@app.post("/api/v1/portfolio/scenarios", tags=["Pricing"])
def api_portfolio_scenarios(request: PortfolioScenariosRequest) -> dict:  # type: ignore[type-arg]
    """Run a multi-deal portfolio under a stress-scenario set (ADR-066).

    Wires :meth:`polaris_re.analytics.portfolio.Portfolio.run_scenarios`
    through to the API. The response shape mirrors
    :meth:`PortfolioScenarioResult.to_dict()` — a flat
    ``{"scenarios": [{"name", "result"}, ...]}`` mapping where every
    ``result`` is itself a :meth:`PortfolioResult.to_dict()` payload. The
    same correlated-stress semantics ADR-064 defines apply: each scenario's
    mortality / lapse multipliers are applied uniformly to every deal in
    the book.
    """
    from polaris_re.analytics.scenario import ScenarioRunner

    standard = ScenarioRunner.standard_stress_scenarios()
    by_name = {sc.name: sc for sc in standard}

    if request.scenarios is None:
        scenario_objs = list(standard)
    else:
        if len(request.scenarios) == 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    "scenarios: empty list. Omit the field (or pass null) to run "
                    "the standard six-scenario set; otherwise supply at least one "
                    "scenario name."
                ),
            )
        if len(request.scenarios) != len(set(request.scenarios)):
            counts: dict[str, int] = {}
            for n in request.scenarios:
                counts[n] = counts.get(n, 0) + 1
            duplicates = sorted(n for n, c in counts.items() if c > 1)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"scenarios: duplicate names {duplicates}. Each scenario must "
                    "appear at most once."
                ),
            )
        unknown = [n for n in request.scenarios if n not in by_name]
        if unknown:
            valid = ", ".join(sc.name for sc in standard)
            raise HTTPException(
                status_code=400,
                detail=f"scenarios: unknown name(s) {unknown}. Valid names: {valid}.",
            )
        scenario_objs = [by_name[n] for n in request.scenarios]

    try:
        portfolio = _portfolio_from_request_deals(request.name, request.deals)
        result = portfolio.run_scenarios(
            request.hurdle_rate,
            scenarios=scenario_objs,
            align=request.align,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result.to_dict()

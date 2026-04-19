"""
Polaris RE — REST API (FastAPI).

Exposes the core Polaris RE pricing engine over HTTP for integration
with downstream systems, dashboards, and workflow automation.

Endpoints:
    GET  /health                  — liveness / readiness probe
    GET  /version                 — package version information
    POST /api/v1/price            — run full pricing pipeline (cedant + reinsurer views)
    POST /api/v1/scenario         — run scenario analysis
    POST /api/v1/uq               — run Monte Carlo uncertainty quantification
    POST /api/v1/ifrs17/bba       — compute IFRS 17 BBA measurement
    POST /api/v1/ifrs17/paa       — compute IFRS 17 PAA measurement
    POST /api/v1/ingest           — ingest raw cedant inforce data
    POST /api/v1/rate-schedule    — generate YRT rate schedule for a target IRR

All request and response bodies are JSON, validated via Pydantic models.
NumPy arrays are serialised as lists. Dates are ISO-8601 strings.

Running locally:
    uvicorn polaris_re.api.main:app --reload --port 8000

Production:
    uvicorn polaris_re.api.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from datetime import date

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import polaris_re
from polaris_re.analytics.ifrs17 import IFRS17Measurement
from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.analytics.scenario import ScenarioRunner
from polaris_re.analytics.uq import MonteCarloUQ, UQParameters
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty
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
    # Metadata
    n_policies: int
    projection_months: int


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
    assumptions = AssumptionSet(
        mortality=mortality,
        lapse=lapse,
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
            reinsurance_cession_pct=0.0,
            issue_date=p.issue_date,
            valuation_date=p.valuation_date,
            product_type=resolved_product_type,
            account_value=p.account_value,
            credited_rate=p.credited_rate,
        )
        for p in policies_in
    ]
    inforce = InforceBlock(policies=policies)

    config = ProjectionConfig(
        valuation_date=policies_in[0].valuation_date,
        projection_horizon_years=projection_horizon_years,
        discount_rate=discount_rate,
        acquisition_cost_per_policy=acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=maintenance_cost_per_policy_per_year,
    )

    return inforce, assumptions, config


def _run_gross_projection(
    inforce: InforceBlock,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
) -> CashFlowResult:
    product = get_product_engine(inforce=inforce, assumptions=assumptions, config=config)
    return product.project()


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
) -> BaseTreaty | None:
    """Build a treaty object based on treaty_type string.

    Returns None for gross-only (no treaty).
    """
    if treaty_type is None:
        return None

    if treaty_type == "YRT":
        yrt_rate = _derive_yrt_rate(gross, face_amount, yrt_loading)
        return YRTTreaty(
            cession_pct=cession_pct,
            total_face_amount=face_amount,
            flat_yrt_rate_per_1000=yrt_rate,
        )
    elif treaty_type == "Coinsurance":
        from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

        return CoinsuranceTreaty(
            treaty_name="COINS-API",
            cession_pct=cession_pct,
            include_expense_allowance=True,
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
        )
        gross = _run_gross_projection(inforce, assumptions, config)

        # Build treaty from request parameters
        total_face = sum(p.face_amount for p in request.policies)
        treaty = _build_treaty(
            treaty_type=request.treaty_type,
            gross=gross,
            face_amount=total_face,
            cession_pct=request.cession_pct,
            yrt_loading=request.yrt_loading,
            modco_interest_rate=request.modco_interest_rate,
        )

        if treaty is not None:
            net, ceded = treaty.apply(gross)
        else:
            net, ceded = gross, None

        # Cedant view: profit test on NET cash flows
        cedant = ProfitTester(cashflows=net, hurdle_rate=request.hurdle_rate).run()

        # Reinsurer view: CEDED re-labelled as NET (ADR-039)
        if ceded is not None:
            reinsurer = ProfitTester(
                cashflows=_ceded_to_reinsurer_view(ceded),
                hurdle_rate=request.hurdle_rate,
            ).run()
        else:
            reinsurer = cedant  # Gross-only: cedant = full view
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        n_policies=len(request.policies),
        projection_months=config.projection_months,
    )


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
    return ScenarioResponse(scenarios=summaries, n_scenarios=len(summaries))


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


# =========================================================================
# POST /api/v1/ingest — Cedant inforce data ingestion
# =========================================================================


class IngestColumnMapping(BaseModel):
    """Column mapping from source to Polaris RE schema."""

    column_mapping: dict[str, str] = Field(description="Maps Polaris field → source column name.")
    code_translations: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Per-field code translations."
    )
    defaults: dict[str, str | float | int] = Field(
        default_factory=dict, description="Default values for missing fields."
    )


class IngestRequest(BaseModel):
    """Request body for inforce data ingestion."""

    policies: list[dict[str, str | float | int]] = Field(
        description="Raw policy records as list of dicts."
    )
    mapping: IngestColumnMapping = Field(description="Column mapping configuration.")


class IngestResponse(BaseModel):
    """Response body for inforce data ingestion."""

    n_policies: int = Field(description="Number of policies ingested.")
    total_face_amount: float = Field(description="Total face amount.")
    mean_age: float = Field(description="Mean attained age.")
    sex_split: dict[str, int] = Field(description="Count by sex.")
    smoker_split: dict[str, int] = Field(description="Count by smoker status.")
    errors: list[str] = Field(description="Validation errors.")
    warnings: list[str] = Field(description="Validation warnings.")
    policies: list[dict[str, str | float | int | None]] = Field(
        description="Normalised policy records."
    )


@app.post("/api/v1/ingest", response_model=IngestResponse)
def api_ingest(request: IngestRequest) -> IngestResponse:
    """Ingest raw cedant inforce data: apply column mapping and validate."""
    import polars as pl

    from polaris_re.utils.ingestion import (
        IngestConfig,
        validate_inforce_df,
    )

    try:
        df = pl.DataFrame(request.policies)

        config = IngestConfig(
            column_mapping=request.mapping.column_mapping,
            code_translations=request.mapping.code_translations,
            defaults=request.mapping.defaults,
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

        report = validate_inforce_df(df)

        policies_out = df.to_dicts()

    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return IngestResponse(
        n_policies=report.n_policies,
        total_face_amount=report.total_face_amount,
        mean_age=report.mean_age,
        sex_split=report.sex_split,
        smoker_split=report.smoker_split,
        errors=report.errors,
        warnings=report.warnings,
        policies=policies_out,
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

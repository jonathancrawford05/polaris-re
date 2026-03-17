"""
Polaris RE — REST API (FastAPI).

Exposes the core Polaris RE pricing engine over HTTP for integration
with downstream systems, dashboards, and workflow automation.

Endpoints:
    GET  /health               — liveness / readiness probe
    GET  /version              — package version information
    POST /api/v1/price         — run full pricing pipeline
    POST /api/v1/scenario      — run scenario analysis
    POST /api/v1/uq            — run Monte Carlo uncertainty quantification
    POST /api/v1/ifrs17/bba    — compute IFRS 17 BBA measurement
    POST /api/v1/ifrs17/paa    — compute IFRS 17 PAA measurement

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
from polaris_re.products.term_life import TermLife
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
    policy_term: int = Field(ge=1, le=40, description="Policy term in years.")
    duration_inforce: int = Field(default=0, ge=0, description="Months in force at valuation date.")
    issue_date: date = Field(description="Policy issue date (ISO 8601).")
    valuation_date: date = Field(description="Valuation date (ISO 8601).")


class PriceRequest(BaseModel):
    """Request body for /api/v1/price."""

    policies: list[PolicyInput] = Field(min_length=1, description="List of policies to price.")
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(ge=0.0, le=1.0, default=0.06)
    hurdle_rate: float = Field(ge=0.0, le=1.0, default=0.10)
    cession_pct: float = Field(ge=0.0, le=1.0, default=0.90, description="YRT cession percentage.")
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001, description="Flat mortality rate (demo).")
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05, description="Flat annual lapse rate.")


class PriceResponse(BaseModel):
    """Response body for /api/v1/price."""

    hurdle_rate: float
    pv_profits: float
    pv_premiums: float
    profit_margin: float
    irr: float | None
    breakeven_year: int | None
    total_undiscounted_profit: float
    profit_by_year: list[float]
    n_policies: int
    projection_months: int


class ScenarioRequest(BaseModel):
    """Request body for /api/v1/scenario."""

    policies: list[PolicyInput] = Field(min_length=1)
    projection_horizon_years: int = Field(ge=1, le=40, default=20)
    discount_rate: float = Field(ge=0.0, le=1.0, default=0.06)
    hurdle_rate: float = Field(ge=0.0, le=1.0, default=0.10)
    cession_pct: float = Field(ge=0.0, le=1.0, default=0.90)
    flat_qx: float = Field(ge=0.0, le=1.0, default=0.001)
    flat_lapse: float = Field(ge=0.0, le=1.0, default=0.05)


class ScenarioSummary(BaseModel):
    """Results for a single scenario."""

    scenario_name: str
    pv_profits: float
    profit_margin: float
    irr: float | None


class ScenarioResponse(BaseModel):
    """Response body for /api/v1/scenario."""

    scenarios: list[ScenarioSummary]
    n_scenarios: int


class UQRequest(BaseModel):
    """Request body for /api/v1/uq."""

    policies: list[PolicyInput] = Field(min_length=1)
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


def _build_pipeline(
    policies_in: list[PolicyInput],
    projection_horizon_years: int,
    discount_rate: float,
    cession_pct: float,
    flat_qx: float,
    flat_lapse: float,
) -> tuple[InforceBlock, AssumptionSet, ProjectionConfig, YRTTreaty]:
    """Convert API request data into pipeline components."""
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
            product_type=ProductType.TERM,
        )
        for p in policies_in
    ]
    inforce = InforceBlock(policies=policies)

    config = ProjectionConfig(
        valuation_date=policies_in[0].valuation_date,
        projection_horizon_years=projection_horizon_years,
        discount_rate=discount_rate,
    )

    total_face = sum(p.face_amount for p in policies_in)
    treaty = YRTTreaty(
        cession_pct=cession_pct,
        total_face_amount=total_face,
    )
    return inforce, assumptions, config, treaty


def _run_gross_projection(
    inforce: InforceBlock,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
) -> CashFlowResult:
    product = TermLife(inforce=inforce, assumptions=assumptions, config=config)
    return product.project()


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

    Projects the supplied inforce block through a YRT treaty and computes
    profit metrics: PV profits, IRR, break-even year, profit margin.
    """
    try:
        inforce, assumptions, config, treaty = _build_pipeline(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            cession_pct=request.cession_pct,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
        )
        gross = _run_gross_projection(inforce, assumptions, config)
        net, _ = treaty.apply(gross)
        result = ProfitTester(cashflows=net, hurdle_rate=request.hurdle_rate).run()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PriceResponse(
        hurdle_rate=result.hurdle_rate,
        pv_profits=result.pv_profits,
        pv_premiums=result.pv_premiums,
        profit_margin=result.profit_margin,
        irr=result.irr,
        breakeven_year=result.breakeven_year,
        total_undiscounted_profit=result.total_undiscounted_profit,
        profit_by_year=result.profit_by_year.tolist(),
        n_policies=len(request.policies),
        projection_months=config.projection_months,
    )


@app.post("/api/v1/scenario", response_model=ScenarioResponse, tags=["Pricing"])
def scenario(request: ScenarioRequest) -> ScenarioResponse:
    """
    Run standard stress scenario analysis.

    Applies pre-defined stress scenarios (mortality shock, lapse stress,
    rate shock) to the base assumptions and returns comparative profit metrics.
    """
    try:
        inforce, assumptions, config, treaty = _build_pipeline(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            cession_pct=request.cession_pct,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
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
    deal profitability metrics.
    """
    try:
        inforce, assumptions, config, treaty = _build_pipeline(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            cession_pct=request.cession_pct,
            flat_qx=request.flat_qx,
            flat_lapse=request.flat_lapse,
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
        inforce, assumptions, config, _ = _build_pipeline(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            cession_pct=0.0,  # Gross basis for IFRS 17
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
        inforce, assumptions, config, _ = _build_pipeline(
            policies_in=request.policies,
            projection_horizon_years=request.projection_horizon_years,
            discount_rate=request.discount_rate,
            cession_pct=0.0,
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

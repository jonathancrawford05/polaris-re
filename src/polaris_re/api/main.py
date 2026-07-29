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
from typing import TYPE_CHECKING, Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

import polaris_re

if TYPE_CHECKING:
    from polaris_re.analytics.portfolio import Portfolio
from polaris_re.analytics.ifrs17 import (
    IFRS17CohortManager,
    IFRS17ContractInput,
    IFRS17Measurement,
)
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
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.reinsurance.expense_allowance import ExpenseAllowance
from polaris_re.reinsurance.experience_refund import ExperienceRefund
from polaris_re.services.pricing import (
    PolicyInput,
    PriceRequest,
    PriceResponse,
    ScenarioRequest,
    ScenarioResponse,
    UQRequest,
    UQResponse,
    _build_components,
    _build_treaty,
    _run_gross_projection,
    run_price,
    run_scenario,
    run_uq,
)
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
    Supports YRT, Coinsurance, Modco, and FWCoinsurance treaty types (or null
    for gross only).

    Thin HTTP adapter over :func:`polaris_re.services.pricing.run_price` (the
    shared in-process engine path): delegate, and map any domain / validation
    failure to HTTP 422 exactly as the previous inline body did (every error
    raised while building or pricing the deal was already re-wrapped into 422).
    """
    try:
        return run_price(request)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/scenario", response_model=ScenarioResponse, tags=["Pricing"])
def scenario(request: ScenarioRequest) -> ScenarioResponse:
    """
    Run standard stress scenario analysis.

    Applies pre-defined stress scenarios (mortality shock, lapse stress,
    rate shock) to the base assumptions and returns comparative profit metrics.
    The YRT rate is derived from the base gross projection (ADR-038) so that
    the treaty is correctly calibrated before stress scenarios are applied.

    Thin HTTP adapter over :func:`polaris_re.services.pricing.run_scenario` (the
    shared in-process engine path, ADR-172): delegate, and map any domain /
    validation failure to HTTP 422 exactly as the previous inline body did.
    """
    try:
        return run_scenario(request)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/uq", response_model=UQResponse, tags=["Pricing"])
def uq(request: UQRequest) -> UQResponse:
    """
    Run Monte Carlo uncertainty quantification.

    Samples assumption multipliers from LogNormal (mortality, lapse) and
    Normal (interest rate) distributions and returns the distribution of
    deal profitability metrics. The YRT rate is derived from the base gross
    projection (ADR-038) so that the treaty is calibrated before sampling.

    Thin HTTP adapter over :func:`polaris_re.services.pricing.run_uq` (the shared
    in-process engine path, ADR-172): delegate, and map any domain / validation
    failure to HTTP 422 exactly as the previous inline body did.
    """
    try:
        return run_uq(request)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    ``treaty_type`` must be one of ``YRT`` / ``Coinsurance`` / ``Modco`` /
    ``FWCoinsurance``.
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

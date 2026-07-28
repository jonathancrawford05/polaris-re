"""
Polaris RE — pricing service layer.

The **engine-invocation composition root** for the deal-pricing workflow. This
module owns the typed request/response contracts (:class:`PriceRequest` /
:class:`PriceResponse` / :class:`PolicyInput`) and the single function that
drives the engine end-to-end:

    run_price(request: PriceRequest) -> PriceResponse

``run_price`` performs: build components → gross projection → apply treaty →
cedant + reinsurer profit tests (optionally with regulatory capital) → premium
sufficiency → optional ALM duration gap → assemble ``PriceResponse``. It is the
logic that previously lived inline in the FastAPI ``POST /api/v1/price`` route
body; the route now delegates to it.

Why a service layer (ADR-170; continues the ADR-156 composition-root cleanup):
the FastAPI route **and** any other host (an MCP server, a batch script, a
notebook) can call ``run_price`` in-process — one engine path, no second mapping
to drift, and no web-framework (``fastapi`` / ``uvicorn``) dependency to invoke
the engine. This module deliberately imports **no** ``fastapi``: validation
failures raise the domain :class:`PolarisValidationError`, which each host maps
to its own error surface (the API maps it to HTTP 422).

Byte-identical guarantee: this is an engine-neutral extraction. ``polaris price``
and every API pricing response are unchanged; no pricing number moves.

The scenario and Monte-Carlo-UQ workflows (``run_scenario`` / ``run_uq``) are the
natural next tenants of this layer; they are extracted in a later slice of the
MCP-server epic (see ``docs/PLAN_mcp_server.md`` Slice 3). Until then they remain
inline in :mod:`polaris_re.api.main`.
"""

from datetime import date
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field, model_validator

from polaris_re.analytics.alm import DualDurationGap, dual_duration_gap
from polaris_re.analytics.capital_base import CapitalModelId, capital_model_for
from polaris_re.analytics.premium_sufficiency import (
    PremiumSufficiencyResult,
    PremiumSufficiencyTester,
)
from polaris_re.analytics.profit_test import (
    ProfitResultWithCapital,
    ProfitTester,
    ProfitTestResult,
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
from polaris_re.pipeline import (
    derive_capital_nar,
    load_improvement_version,
    load_valuation_mortality,
)
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty
from polaris_re.reinsurance.expense_allowance import ExpenseAllowance
from polaris_re.reinsurance.experience_refund import ExperienceRefund
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import MortalityTableArray

__all__ = ["PolicyInput", "PriceRequest", "PriceResponse", "run_price"]


# ---------------------------------------------------------------------------
# Request / Response contracts
# ---------------------------------------------------------------------------


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
        description=(
            "Treaty type: 'YRT', 'Coinsurance', 'Modco', 'FWCoinsurance', or null for gross only."
        ),
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
    gaap_mortality_pad: float = Field(
        default=1.0,
        ge=1.0,
        description=(
            "GAAP (FAS 60) mortality provision for adverse deviation (PAD): a "
            "multiplicative margin (>= 1.0) on locked-in best-estimate mortality "
            "for the FAS 60 net-premium benefit reserve. Consumed only on the "
            "GAAP reserve basis (reserve_basis=GAAP); ignored on every other "
            "basis. 1.0 (default) is byte-identical to prior responses; a value "
            "> 1.0 raises the GAAP reserve so a reinsurer can reproduce the "
            "cedant's held FAS 60 reserve. A value < 1.0 yields HTTP 422."
        ),
    )
    gaap_interest_margin: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "GAAP (FAS 60) interest provision for adverse deviation (PAD): an "
            "absolute reduction (in [0, 1]) applied to the valuation interest "
            "rate when discounting the FAS 60 net-premium benefit reserve. "
            "Consumed only on the GAAP reserve basis (reserve_basis=GAAP); "
            "ignored on every other basis. 0.0 (default) is byte-identical to "
            "prior responses; a positive value lowers the GAAP discount rate, "
            "raising the reserve. An out-of-range value yields HTTP 422."
        ),
    )
    improvement_version: str | None = Field(
        default=None,
        description=(
            "Versioned experience-derived mortality-improvement scale "
            "(mi-dashboard epic, ADR-159 — API half of IMPORTANT #12). "
            "A ``version_id`` in the append-only assumption-version store, "
            "loaded server-side from "
            "``$POLARIS_DATA_DIR/assumption_versions`` (kind "
            "``mortality_improvement``). When set, the frozen "
            "``ImprovementScale.CUSTOM`` scale is threaded onto the priced run's "
            "``AssumptionSet.improvement`` — identical to the CLI "
            "``--improvement-version`` flag / ``mortality.improvement_version_id`` "
            "config key and the dashboard Deal-Pricing selector — so the run "
            "prices on the frozen experience basis instead of the default "
            "no-improvement projection table. The response echoes it back. None "
            "(default) is byte-identical to prior responses. An unknown "
            "version id yields HTTP 422."
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
    # GAAP (FAS 60) provisions for adverse deviation the run was priced on.
    # Echo the request's PADs so a client can confirm the adverse-deviation
    # basis the GAAP reserve was valued on (neutral 1.0 / 0.0 unless set, and
    # consumed only on the GAAP reserve basis).
    gaap_mortality_pad: float = 1.0
    gaap_interest_margin: float = 0.0
    # Versioned experience-derived improvement scale the run was priced on
    # (mi-dashboard epic, API half of IMPORTANT #12). Echoes the request's
    # ``improvement_version`` so a client can confirm which frozen basis drove
    # the mortality (and therefore the priced numbers). None when the run used
    # the default no-improvement projection table.
    improvement_version: str | None = None
    # Asset-liability duration gap (Asset/ALM epic, Slice 4b-2b). Populated only
    # when ``asset_portfolio`` was supplied; None otherwise (the block is purely
    # additive, so existing responses are unchanged except for this null field).
    # Carries the reinsurer-view (ceded reserve — headline) and cedant-view
    # (retained reserve) gaps; either side is null when its reserve is ~0 (e.g. the
    # ceded reserve of a YRT treaty).
    alm_duration_gap: DualDurationGap | None = None


# ---------------------------------------------------------------------------
# Internal helpers (engine composition — no web-framework dependency)
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
    improvement_version: str | None = None,
    gaap_mortality_pad: float = 1.0,
    gaap_interest_margin: float = 0.0,
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

    # Versioned experience-derived mortality improvement (mi-dashboard epic,
    # ADR-159 — API half of IMPORTANT #12). ``None`` (default) leaves
    # ``AssumptionSet.improvement`` unset → the projection applies no improvement
    # exactly as before (byte-identical). When a version id is supplied, the
    # frozen ``ImprovementScale.CUSTOM`` scale is loaded server-side from the
    # append-only store (``$POLARIS_DATA_DIR/assumption_versions``) and threaded
    # onto the assumption set — the same path the CLI ``--improvement-version``
    # flag and the dashboard selector use. An unknown id raises
    # ``PolarisValidationError``, which the endpoint maps to HTTP 422.
    improvement = None
    if improvement_version is not None:
        improvement = load_improvement_version(improvement_version)

    assumptions = AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        improvement=improvement,
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
        gaap_mortality_pad=gaap_mortality_pad,
        gaap_interest_margin=gaap_interest_margin,
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
    treaty byte-identical. Both are silently ignored for ``Modco`` /
    ``FWCoinsurance`` / gross, which have no allowance/refund field.

    ``FWCoinsurance`` (funds-withheld coinsurance, ADR-163/164) reuses the
    ``modco_interest_rate`` request field as its funds-withheld interest rate.

    Validation failures raise :class:`PolarisValidationError` (the API layer
    maps it to HTTP 422 — pre-existing behaviour, since the price / scenario /
    uq route bodies already re-wrap any error into 422).
    """
    if treaty_type is None:
        return None

    if treaty_type == "YRT":
        if yrt_rate_table is not None:
            from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

            if not isinstance(yrt_rate_table, YRTRateTable):
                raise PolarisValidationError(
                    "yrt_rate_table must be a YRTRateTable instance, "
                    f"got {type(yrt_rate_table).__name__}."
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
    elif treaty_type == "FWCoinsurance":
        from polaris_re.reinsurance.fw_coinsurance import FWCoinsuranceTreaty

        # Funds-withheld coinsurance reuses the ``modco_interest_rate`` request
        # field as its funds-withheld interest rate (ADR-164) — both credit
        # interest on reserve assets retained/withheld by the cedant.
        return FWCoinsuranceTreaty(
            treaty_name="FWCOINS-API",
            cession_pct=cession_pct,
            funds_withheld_rate=modco_interest_rate,
        )

    raise PolarisValidationError(
        f"Unknown treaty_type '{treaty_type}'. "
        "Use 'YRT', 'Coinsurance', 'Modco', 'FWCoinsurance', or null."
    )


def _resolve_yrt_rate_table_path(rel_path: str) -> Path:
    """Resolve a server-side YRT rate-table path safely (ADR-052).

    The user-supplied ``yrt_rate_table_path`` is resolved relative to
    ``$POLARIS_DATA_DIR``. Path traversal (``..``, absolute paths
    escaping the data dir) is rejected.

    Raises :class:`PolarisValidationError` for a missing ``POLARIS_DATA_DIR``,
    a traversal attempt, or a non-existent directory (the API layer maps it to
    HTTP 422 — pre-existing behaviour, since the price route body already
    re-wraps any error into 422).
    """
    import os

    data_dir_env = os.environ.get("POLARIS_DATA_DIR")
    if data_dir_env is None:
        raise PolarisValidationError(
            "POLARIS_DATA_DIR environment variable must be set on the "
            "server to resolve yrt_rate_table_path."
        )
    data_root = Path(data_dir_env).resolve()
    candidate = (data_root / rel_path).resolve()
    try:
        candidate.relative_to(data_root)
    except ValueError as exc:
        raise PolarisValidationError(
            f"yrt_rate_table_path must resolve inside POLARIS_DATA_DIR; got {rel_path!r}."
        ) from exc
    if not candidate.is_dir():
        raise PolarisValidationError(f"yrt_rate_table_path directory not found: {rel_path}")
    return candidate


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


# ---------------------------------------------------------------------------
# Public service entry point
# ---------------------------------------------------------------------------


def run_price(request: PriceRequest) -> PriceResponse:
    """Run the full deal-pricing pipeline for ``request`` and return the response.

    Projects the supplied inforce block through a treaty and returns profit
    metrics for both the cedant (NET basis) and the reinsurer perspectives.
    Supports TERM, WHOLE_LIFE, and UL product types via the product dispatcher
    and YRT, Coinsurance, Modco, and FWCoinsurance treaty types (or null for
    gross only).

    This is the shared engine-invocation path: the FastAPI ``POST /api/v1/price``
    route delegates to it, and any in-process host (an MCP tool, a batch script)
    can call it directly. It performs no HTTP concerns — validation failures
    propagate as :class:`PolarisValidationError` / ``ValueError`` for the caller
    to map to its own error surface (the API wraps them into HTTP 422).
    """
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
        improvement_version=request.improvement_version,
        gaap_mortality_pad=request.gaap_mortality_pad,
        gaap_interest_margin=request.gaap_interest_margin,
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

    gross = _run_gross_projection(inforce, assumptions, config, seriatim=yrt_rate_table is not None)

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
        # Pass ``inforce`` ALWAYS so a sliding-scale ``ExpenseAllowance`` is
        # mapped to each policy's actual duration (block-aware first-year
        # rate) — not just on the tabular-YRT path (ADR-166;
        # expense-allowance duration Slice 2). ``use_policy_cession`` is
        # threaded EXPLICITLY (not left to the default) so this call does not
        # silently change behaviour if ``apply``'s default ever flips, and so
        # the intent is legible alongside the CLI / dashboard callers that
        # thread it too. It is cession-neutral for existing responses:
        # ``PolicyInput`` carries no per-policy cession override (Policy is
        # built with ``reinsurance_cession_pct=None``), so the face-weighted
        # cession equals the flat ``treaty.cession_pct`` regardless of the
        # flag. Only an allowance on a mid-duration block moves — the fix.
        net, ceded = treaty.apply(gross, inforce=inforce, use_policy_cession=True)
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
        gaap_mortality_pad=config.gaap_mortality_pad,
        gaap_interest_margin=config.gaap_interest_margin,
        improvement_version=request.improvement_version,
        alm_duration_gap=alm_gap,
    )

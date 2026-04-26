"""Shared pipeline builder — single source of truth for CLI and dashboard.

Both the CLI and Streamlit dashboard construct identical
(InforceBlock, AssumptionSet, ProjectionConfig) tuples from this module.
No other code should instantiate MortalityTable, LapseAssumption,
AssumptionSet, or ProjectionConfig for a deal — use `build_pipeline`.
"""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.utils.table_io import MortalityTableArray

__all__ = [
    "DEFAULT_LAPSE_CURVE",
    "DealConfig",
    "LapseConfig",
    "MortalityConfig",
    "PipelineInputs",
    "build_assumption_set",
    "build_pipeline",
    "build_projection_config",
    "build_treaty",
    "ceded_to_reinsurer_view",
    "derive_capital_nar",
    "derive_yrt_rate",
    "dump_parity_debug",
    "iter_cohorts",
    "load_inforce",
]

# ------------------------------------------------------------------ #
# Default lapse curve — shared between CLI, dashboard, and tests     #
# ------------------------------------------------------------------ #

DEFAULT_LAPSE_CURVE: dict[int | str, float] = {
    1: 0.06,
    2: 0.05,
    3: 0.04,
    4: 0.035,
    5: 0.03,
    6: 0.025,
    7: 0.02,
    8: 0.02,
    9: 0.02,
    10: 0.02,
    "ultimate": 0.015,
}


# ------------------------------------------------------------------ #
# Configuration dataclasses                                           #
# ------------------------------------------------------------------ #


@dataclass
class MortalityConfig:
    """Configuration for mortality table loading."""

    source: str = "SOA_VBT_2015"  # "SOA_VBT_2015" | "CIA_2014" | "CSO_2001" | "flat"
    multiplier: float = 1.0
    flat_qx: float | None = None  # only used when source == "flat"
    data_dir: Path | None = None  # None → $POLARIS_DATA_DIR / mortality_tables
    # TODO: ml_mortality_path — future ML model loading


@dataclass
class LapseConfig:
    """Configuration for lapse assumption construction."""

    duration_table: dict[int | str, float] = field(
        default_factory=lambda: dict(DEFAULT_LAPSE_CURVE)
    )
    multiplier: float = 1.0


@dataclass
class DealConfig:
    """Deal configuration — mirrors dashboard state.DEFAULTS.

    Keep these defaults in lockstep with the dashboard.
    """

    product_type: str = "TERM"
    treaty_type: str = "YRT"
    cession_pct: float = 0.90
    yrt_loading: float = 0.10
    yrt_rate_per_1000: float | None = None
    yrt_rate_basis: str = "Mortality-based"  # or "Manual Rate"
    modco_rate: float = 0.045
    discount_rate: float = 0.06
    hurdle_rate: float = 0.10
    projection_years: int = 20
    acquisition_cost: float = 500.0
    maintenance_cost: float = 75.0
    use_policy_cession: bool = False
    valuation_date: date = field(default_factory=date.today)

    def to_dict(self) -> dict[str, object]:
        """Return a plain dict suitable for dashboard session state."""
        return {
            "product_type": self.product_type,
            "treaty_type": self.treaty_type,
            "cession_pct": self.cession_pct,
            "yrt_loading": self.yrt_loading,
            "yrt_rate_per_1000": self.yrt_rate_per_1000,
            "yrt_rate_basis": self.yrt_rate_basis,
            "modco_rate": self.modco_rate,
            "discount_rate": self.discount_rate,
            "hurdle_rate": self.hurdle_rate,
            "projection_years": self.projection_years,
            "acquisition_cost": self.acquisition_cost,
            "maintenance_cost": self.maintenance_cost,
            "valuation_date": self.valuation_date,
        }


@dataclass
class PipelineInputs:
    """All inputs needed to build a pricing pipeline."""

    mortality: MortalityConfig = field(default_factory=MortalityConfig)
    lapse: LapseConfig = field(default_factory=LapseConfig)
    deal: DealConfig = field(default_factory=DealConfig)


# ------------------------------------------------------------------ #
# Inforce loading                                                     #
# ------------------------------------------------------------------ #


def load_inforce(
    csv_path: Path | None = None,
    policies_dict: list[dict[str, object]] | None = None,
) -> InforceBlock:
    """Load an inforce block from either a CSV file or a list-of-dicts.

    Exactly one of csv_path / policies_dict must be provided.
    """
    if csv_path is not None and policies_dict is not None:
        raise PolarisValidationError("Provide either csv_path or policies_dict, not both.")
    if csv_path is None and policies_dict is None:
        raise PolarisValidationError("Provide either csv_path or policies_dict.")

    if csv_path is not None:
        return InforceBlock.from_csv(csv_path)

    # Build from list-of-dicts (legacy JSON config path)
    from polaris_re.core.policy import Policy, ProductType

    policies = []
    for p in policies_dict:  # type: ignore[union-attr]
        product_type_str = str(p.get("product_type", "TERM"))
        product_type = ProductType(product_type_str)

        sex = Sex.MALE if str(p.get("sex", "M")).upper() == "M" else Sex.FEMALE
        smoker_status = SmokerStatus.SMOKER if p.get("smoker", False) else SmokerStatus.NON_SMOKER

        policies.append(
            Policy(
                policy_id=str(p["policy_id"]),
                issue_age=int(p["issue_age"]),  # type: ignore[arg-type]
                attained_age=int(p["attained_age"]),  # type: ignore[arg-type]
                sex=sex,
                smoker_status=smoker_status,
                underwriting_class=str(p.get("underwriting_class", "STANDARD")),
                face_amount=float(p["face_amount"]),  # type: ignore[arg-type]
                annual_premium=float(p["annual_premium"]),  # type: ignore[arg-type]
                policy_term=p.get("policy_term"),  # type: ignore[arg-type]
                duration_inforce=int(p.get("duration_inforce", 0)),  # type: ignore[arg-type]
                reinsurance_cession_pct=float(p.get("reinsurance_cession_pct", 0.0)),  # type: ignore[arg-type]
                issue_date=date.fromisoformat(str(p["issue_date"])),
                valuation_date=date.fromisoformat(str(p["valuation_date"])),
                product_type=product_type,
                account_value=float(p.get("account_value", 0.0)),  # type: ignore[arg-type]
                credited_rate=float(p.get("credited_rate", 0.0)),  # type: ignore[arg-type]
            )
        )

    return InforceBlock(policies=policies)


# ------------------------------------------------------------------ #
# Mortality table building                                            #
# ------------------------------------------------------------------ #


def _resolve_data_dir(config: MortalityConfig) -> Path:
    """Resolve the mortality tables data directory."""
    if config.data_dir is not None:
        return config.data_dir
    env_dir = os.environ.get("POLARIS_DATA_DIR", "data")
    return Path(env_dir) / "mortality_tables"


def _build_flat_mortality(flat_qx: float) -> MortalityTable:
    """Build a synthetic flat-rate mortality table with all sex/smoker combos.

    Identical to the dashboard's ``_build_flat_mortality`` in
    ``views/assumptions.py`` — kept here as the single source of truth.
    """
    n_ages = 121 - 18
    qx = np.full(n_ages, flat_qx, dtype=np.float64)
    rates_2d = qx.reshape(-1, 1)

    tables: dict[str, MortalityTableArray] = {}
    for sex in Sex:
        for smoker in SmokerStatus:
            key = f"{sex.value}_{smoker.value}"
            tables[key] = MortalityTableArray(
                rates=rates_2d.copy(),
                min_age=18,
                max_age=120,
                select_period=0,
                source_file=Path("synthetic"),
            )

    return MortalityTable(
        source=MortalityTableSource.CSO_2001,
        table_name=f"Flat Rate ({flat_qx:.6f})",
        min_age=18,
        max_age=120,
        select_period_years=0,
        has_smoker_distinct_rates=False,
        tables=tables,
    )


def _load_mortality(config: MortalityConfig) -> MortalityTable:
    """Load or build a mortality table based on config."""
    if config.source == "flat":
        flat_qx = config.flat_qx if config.flat_qx is not None else 0.001
        return _build_flat_mortality(flat_qx)

    source_map = {
        "SOA_VBT_2015": MortalityTableSource.SOA_VBT_2015,
        "CIA_2014": MortalityTableSource.CIA_2014,
        "CSO_2001": MortalityTableSource.CSO_2001,
    }
    source = source_map.get(config.source)
    if source is None:
        raise PolarisValidationError(
            f"Unknown mortality source: {config.source!r}. "
            f"Valid: {[*list(source_map.keys()), 'flat']}"
        )

    data_dir = _resolve_data_dir(config)
    return MortalityTable.load(source=source, data_dir=data_dir)


def _apply_mortality_multiplier(
    mortality: MortalityTable,
    multiplier: float,
) -> MortalityTable:
    """Scale all mortality rates by a multiplier, clamped to [0, 1]."""
    if multiplier == 1.0:
        return mortality

    scaled_tables: dict[str, MortalityTableArray] = {}
    for key, table_array in mortality.tables.items():
        scaled_rates = np.clip(table_array.rates * multiplier, 0.0, 1.0)
        scaled_tables[key] = MortalityTableArray(
            rates=scaled_rates,
            min_age=table_array.min_age,
            max_age=table_array.max_age,
            select_period=table_array.select_period,
            source_file=table_array.source_file,
        )

    return MortalityTable(
        source=mortality.source,
        table_name=f"{mortality.table_name} (x{multiplier:.2f})",
        min_age=mortality.min_age,
        max_age=mortality.max_age,
        select_period_years=mortality.select_period_years,
        has_smoker_distinct_rates=mortality.has_smoker_distinct_rates,
        tables=scaled_tables,
    )


# ------------------------------------------------------------------ #
# Assumption set building                                             #
# ------------------------------------------------------------------ #


def build_assumption_set(inputs: PipelineInputs) -> AssumptionSet:
    """Build an AssumptionSet matching how the dashboard builds it."""
    # Mortality
    mortality = _load_mortality(inputs.mortality)
    mortality = _apply_mortality_multiplier(mortality, inputs.mortality.multiplier)

    # Lapse
    lapse = LapseAssumption.from_duration_table(inputs.lapse.duration_table)
    if inputs.lapse.multiplier != 1.0:
        scaled_select = tuple(min(r * inputs.lapse.multiplier, 1.0) for r in lapse.select_rates)
        scaled_ultimate = min(lapse.ultimate_rate * inputs.lapse.multiplier, 1.0)
        lapse = LapseAssumption(
            select_rates=scaled_select,
            ultimate_rate=scaled_ultimate,
            select_period_years=lapse.select_period_years,
        )

    return AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        version=f"pipeline-{inputs.mortality.source}-{date.today().isoformat()}",
        effective_date=date.today(),
    )


# ------------------------------------------------------------------ #
# Projection config building                                          #
# ------------------------------------------------------------------ #


def build_projection_config(
    inputs: PipelineInputs,
    valuation_date: date | None = None,
) -> ProjectionConfig:
    """Build a ProjectionConfig matching dashboard.components.projection.

    Resolution order for valuation_date:
    1. Explicit ``valuation_date`` argument (caller override).
    2. ``inputs.deal.valuation_date`` (from config JSON / dashboard).
    3. ``date.today()`` (fallback).
    """
    resolved_date = valuation_date or inputs.deal.valuation_date
    return ProjectionConfig(
        valuation_date=resolved_date,
        projection_horizon_years=inputs.deal.projection_years,
        discount_rate=inputs.deal.discount_rate,
        acquisition_cost_per_policy=inputs.deal.acquisition_cost,
        maintenance_cost_per_policy_per_year=inputs.deal.maintenance_cost,
    )


# ------------------------------------------------------------------ #
# Full pipeline builder                                               #
# ------------------------------------------------------------------ #


def build_pipeline(
    inforce: InforceBlock,
    inputs: PipelineInputs,
    valuation_date: date | None = None,
) -> tuple[InforceBlock, AssumptionSet, ProjectionConfig]:
    """One-shot builder that produces the full pipeline tuple.

    Resolution order for valuation_date:
    1. Explicit ``valuation_date`` argument.
    2. ``inputs.deal.valuation_date`` (from DealConfig).
    3. First policy's ``valuation_date`` in the inforce block.
    4. ``date.today()``.
    """
    assumptions = build_assumption_set(inputs)
    effective_date = (
        valuation_date
        or inputs.deal.valuation_date
        or (inforce.policies[0].valuation_date if inforce.policies else date.today())
    )
    config = build_projection_config(inputs, valuation_date=effective_date)
    return inforce, assumptions, config


# ------------------------------------------------------------------ #
# Cohort iteration — multi-product block partitioning                 #
# ------------------------------------------------------------------ #


def iter_cohorts(
    inforce: InforceBlock,
) -> list[tuple[ProductType, InforceBlock]]:
    """Partition an inforce block into single-product cohorts.

    Returns a deterministic list of ``(product_type, sub_block)`` tuples,
    ordered by ``ProductType`` enum value. A homogeneous block returns a
    single-element list containing the original block (no copy), so callers
    can use ``iter_cohorts()`` uniformly without paying any cost on the
    common single-product case.

    This is the path used by CLI ``price`` and the dashboard Pricing page
    to handle mixed product blocks as independent per-cohort pipelines
    (no cash-flow aggregation — each cohort is its own priced deal).

    Args:
        inforce: InforceBlock potentially containing multiple product types.

    Returns:
        List of (product_type, sub_block) tuples, one per distinct product
        type in the block. Sub-blocks are new InforceBlock instances when
        the input is heterogeneous, or the original block itself when it
        is already homogeneous.
    """
    distinct = sorted(inforce.product_types, key=lambda pt: pt.value)
    if len(distinct) <= 1:
        # Homogeneous: return the block as-is to avoid a redundant copy.
        if not distinct:
            return []
        return [(distinct[0], inforce)]
    return [(pt, inforce.filter_by_product(pt)) for pt in distinct]


# ------------------------------------------------------------------ #
# Treaty construction (consolidated from CLI + dashboard)             #
# ------------------------------------------------------------------ #


def derive_yrt_rate(
    gross: CashFlowResult,
    face_amount_total: float,
    loading: float = 0.10,
) -> float:
    """Derive a mortality-based YRT rate per $1,000 NAR from a gross projection.

    Uses the first year's actual claims divided by total face amount to
    estimate the implied annual q_x, then applies the loading factor.
    Canonical location per ADR-038.

    Args:
        gross: GROSS basis CashFlowResult with at least 12 months.
        face_amount_total: Total initial in-force face amount.
        loading: YRT loading over expected mortality (e.g. 0.10 = 10%).

    Returns:
        YRT rate per $1,000 NAR (annual).
    """
    first_year_claims = float(gross.death_claims[:12].sum())
    implied_annual_qx = first_year_claims / face_amount_total if face_amount_total > 0 else 0.001
    return implied_annual_qx * 1000.0 * (1.0 + loading)


def build_treaty(
    treaty_type: str,
    cession_pct: float,
    face_amount: float,
    modco_rate: float = 0.045,
    yrt_rate_per_1000: float | None = None,
    treaty_name: str | None = None,
) -> object | None:
    """Construct a treaty object from the given parameters.

    Consolidated from dashboard and CLI — single factory for all callers.

    Args:
        treaty_type: "YRT", "Coinsurance", "Modco", or "None (Gross)".
        cession_pct: Proportion ceded (e.g. 0.90).
        face_amount: Total in-force face amount.
        modco_rate: Modco interest rate (used only for Modco).
        yrt_rate_per_1000: YRT rate per $1,000 NAR. Required for YRT.
        treaty_name: Optional treaty name override.

    Returns:
        Treaty object or None for "None (Gross)".
    """
    if treaty_type in ("None (Gross)", "None", "none") or treaty_type is None:
        return None

    if treaty_type == "YRT":
        from polaris_re.reinsurance.yrt import YRTTreaty

        return YRTTreaty(
            treaty_name=treaty_name or "YRT",
            cession_pct=cession_pct,
            total_face_amount=face_amount,
            flat_yrt_rate_per_1000=yrt_rate_per_1000,
        )
    elif treaty_type == "Coinsurance":
        from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

        return CoinsuranceTreaty(
            treaty_name=treaty_name or "Coinsurance",
            cession_pct=cession_pct,
            include_expense_allowance=True,
        )
    elif treaty_type == "Modco":
        from polaris_re.reinsurance.modco import ModcoTreaty

        return ModcoTreaty(
            treaty_name=treaty_name or "Modco",
            cession_pct=cession_pct,
            modco_interest_rate=modco_rate,
        )

    return None


def derive_capital_nar(
    gross: CashFlowResult,
    reserve_balance: np.ndarray,
    face_amount_total: float,
    *,
    cession_pct: float | None = None,
    is_reinsurer: bool = False,
) -> np.ndarray:
    """Derive a NAR vector for `LICATCapital.required_capital` (ADR-049).

    Mirrors the inforce-ratio approximation that `YRTTreaty.apply` already
    uses to populate `cashflows.nar`, so capital NAR for non-YRT runs is
    consistent with the YRT path:

        inforce_ratio_t = gross.gross_premiums / gross.gross_premiums[0]
        face_in_force_t = face_amount_total * face_share * inforce_ratio_t
        nar_t           = max(face_in_force_t - reserve_balance_t, 0.0)

    `face_share` defaults to 1.0 (no treaty / GROSS basis). When
    `cession_pct` is provided, `face_share = cession_pct` for the reinsurer
    view and `(1 - cession_pct)` for the cedant. The same formula works
    for YRT (cedant retains face but only `(1-cession)` of mortality
    risk), coinsurance, and modco — pass the cashflows-being-capitalised
    `reserve_balance` to get a consistent NAR.

    Args:
        gross: GROSS-basis CashFlowResult — its `gross_premiums` runoff is
            the inforce-ratio reference. Using GROSS rather than NET keeps
            the inforce signal intact across treaty types (e.g. YRT NET
            premiums net out ceded YRT premiums and would distort the
            ratio).
        reserve_balance: Reserve balance vector of the cashflows being
            capitalised (NET for cedant, CEDED for reinsurer). Shape (T,).
        face_amount_total: Total initial in-force face amount.
        cession_pct: Treaty cession percentage. When None, `face_share` is
            1.0 (gross / no-treaty case).
        is_reinsurer: When True and `cession_pct is not None`, returns the
            reinsurer-share NAR (`face_share = cession_pct`); otherwise
            returns the cedant-share NAR (`face_share = 1 - cession_pct`).

    Returns:
        NAR vector of shape `(T,)`, dtype `float64`, floored at zero.
    """
    n = len(gross.gross_premiums)
    if n == 0:
        return np.array([], dtype=np.float64)

    initial = float(gross.gross_premiums[0])
    if initial > 0.0:
        inforce_ratio = gross.gross_premiums / initial
    else:
        inforce_ratio = np.ones(n, dtype=np.float64)

    if cession_pct is None:
        face_share = 1.0
    elif is_reinsurer:
        face_share = float(cession_pct)
    else:
        face_share = 1.0 - float(cession_pct)

    face_in_force = face_amount_total * face_share * inforce_ratio
    return np.maximum(face_in_force - reserve_balance, 0.0).astype(np.float64)


def ceded_to_reinsurer_view(ceded: CashFlowResult) -> CashFlowResult:
    """Re-label a CEDED CashFlowResult as NET for reinsurer profit testing.

    ProfitTester rejects CEDED basis by design (it's meaningless to
    profit-test the ceded portion from the cedant's perspective). However,
    the reinsurer's "net" position IS exactly the ceded cash flows. This
    helper creates a shallow copy with basis="NET" so ProfitTester accepts it.
    Canonical location per ADR-039.
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


# ------------------------------------------------------------------ #
# Parity diagnostic dump (set POLARIS_PARITY_DEBUG=1 to enable)       #
# ------------------------------------------------------------------ #


def dump_parity_debug(
    label: str,
    gross: CashFlowResult,
    net: CashFlowResult | None = None,
    ceded: CashFlowResult | None = None,
) -> None:
    """Write year-by-year cash flow CSV for parity debugging.

    Enabled only when the ``POLARIS_PARITY_DEBUG`` environment variable is
    set.  Writes to ``$POLARIS_PARITY_OUTPUT`` (default:
    ``data/outputs/parity``) as ``{label}_{basis}.csv``.

    Paths are resolved to absolute form so the location is always
    discoverable regardless of the caller's working directory.
    """
    import csv
    import sys

    if not os.environ.get("POLARIS_PARITY_DEBUG"):
        return

    out_dir = Path(os.environ.get("POLARIS_PARITY_OUTPUT", "data/outputs/parity")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Always announce the output directory so the user can find the files
    # even if the write step fails later.
    print(
        f"[parity-debug] label={label} cwd={Path.cwd()} out_dir={out_dir}",
        file=sys.stderr,
        flush=True,
    )

    for cf, basis in [(gross, "gross"), (net, "net"), (ceded, "ceded")]:
        if cf is None:
            continue
        months = cf.projection_months
        years = (np.arange(months) // 12) + 1
        rows: list[dict[str, object]] = []
        for yr in range(1, int(years.max()) + 1):
            mask = years == yr
            rows.append(
                {
                    "year": yr,
                    "gross_premiums": float(cf.gross_premiums[mask].sum()),
                    "death_claims": float(cf.death_claims[mask].sum()),
                    "lapse_surrenders": float(cf.lapse_surrenders[mask].sum()),
                    "expenses": float(cf.expenses[mask].sum()),
                    "reserve_increase": float(cf.reserve_increase[mask].sum()),
                    "net_cash_flow": float(cf.net_cash_flow[mask].sum()),
                    "reserve_balance_eoy": float(
                        cf.reserve_balance[min(int(mask.nonzero()[0][-1]) + 1, months - 1)]
                    ),
                }
            )

        path = out_dir / f"{label}_{basis}.csv"
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"[parity-debug] wrote {path}", file=sys.stderr, flush=True)

"""Shared projection helpers for all dashboard pages.

Provides consistent treaty construction, YRT rate derivation, and
projection execution so every page produces identical results for
the same inputs.

Core helpers (derive_yrt_rate, build_treaty, ceded_to_reinsurer_view)
are imported from ``polaris_re.core.pipeline`` — the single source of truth
shared with the CLI. Dashboard-specific UI glue lives here.
"""

from datetime import date

from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.pipeline import (
    build_treaty as _pipeline_build_treaty,
)
from polaris_re.core.pipeline import (
    ceded_to_reinsurer_view,
    derive_yrt_rate,
)
from polaris_re.core.projection import ProjectionConfig
from polaris_re.dashboard.components.state import get_deal_config

__all__ = [
    "build_projection_config",
    "build_treaty",
    "ceded_to_reinsurer_view",
    "derive_yrt_rate",
    "run_gross_projection",
    "run_treaty_projection",
]


def build_projection_config(
    overrides: dict[str, object] | None = None,
) -> ProjectionConfig:
    """Build a ProjectionConfig from the centralised deal config.

    The valuation date is derived from the inforce block in session state
    (using the first policy's valuation_date) so that CLI and dashboard
    produce identical results on the same CSV.  Falls back to date.today()
    only when no inforce block has been loaded yet.

    Args:
        overrides: Optional dict to override specific deal config values.
                   Supported keys: projection_years, discount_rate,
                   acquisition_cost, maintenance_cost.

    Returns:
        ProjectionConfig ready for projection.
    """
    import streamlit as st  # type: ignore[import-untyped]

    cfg = get_deal_config()
    if overrides:
        cfg = {**cfg, **overrides}

    # Resolution order: deal_config valuation_date → inforce block → today
    val_date = cfg.get("valuation_date")
    if isinstance(val_date, str):
        val_date = date.fromisoformat(val_date)
    if not isinstance(val_date, date):
        inforce_block = st.session_state.get("inforce_block")
        if (
            inforce_block is not None
            and hasattr(inforce_block, "policies")
            and inforce_block.policies
        ):
            val_date = inforce_block.policies[0].valuation_date
        else:
            val_date = date.today()

    return ProjectionConfig(
        valuation_date=val_date,
        projection_horizon_years=int(cfg.get("projection_years", 20)),
        discount_rate=float(cfg.get("discount_rate", 0.06)),
        acquisition_cost_per_policy=float(cfg.get("acquisition_cost", 500.0)),
        maintenance_cost_per_policy_per_year=float(cfg.get("maintenance_cost", 75.0)),
    )


def build_treaty(
    treaty_type: str,
    cession_pct: float,
    face_amount: float,
    modco_rate: float = 0.045,
    yrt_rate_per_1000: float | None = None,
    yrt_rate_table: object | None = None,
) -> object | None:
    """Construct a treaty object from the given parameters.

    Delegates to the shared ``core.pipeline.build_treaty`` with dashboard
    treaty name convention. When ``yrt_rate_table`` is supplied for a YRT
    treaty, it is wired directly onto the constructed ``YRTTreaty`` (the
    pipeline factory does not yet know about tabular rates — the dashboard
    constructs the treaty itself per ADR-052 / ADR-055).
    """
    if treaty_type == "YRT" and yrt_rate_table is not None:
        from polaris_re.reinsurance.yrt import YRTTreaty
        from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

        if not isinstance(yrt_rate_table, YRTRateTable):
            raise TypeError(
                f"yrt_rate_table must be a YRTRateTable, got {type(yrt_rate_table).__name__}."
            )
        return YRTTreaty(
            treaty_name="YRT",
            cession_pct=cession_pct,
            total_face_amount=face_amount,
            yrt_rate_table=yrt_rate_table,
        )

    return _pipeline_build_treaty(
        treaty_type=treaty_type,
        cession_pct=cession_pct,
        face_amount=face_amount,
        modco_rate=modco_rate,
        yrt_rate_per_1000=yrt_rate_per_1000,
    )


def run_gross_projection(
    inforce: object,
    assumptions: object,
    config: ProjectionConfig,
    seriatim: bool = False,
) -> CashFlowResult:
    """Run a gross projection using the appropriate product engine.

    Dispatches to TermLife, WholeLife, or UniversalLife based on the
    product type of the policies in the inforce block.

    Args:
        inforce: InforceBlock.
        assumptions: AssumptionSet.
        config: ProjectionConfig.
        seriatim: When True, request per-policy lx/reserves on the result
            (required when downstream tabular YRT consumption needs them —
            ADR-051 / ADR-052).

    Returns:
        GROSS basis CashFlowResult.
    """
    from polaris_re.products.dispatch import get_product_engine

    product = get_product_engine(
        inforce=inforce,  # type: ignore[arg-type]
        assumptions=assumptions,  # type: ignore[arg-type]
        config=config,
    )
    return product.project(seriatim=seriatim)


def run_treaty_projection(
    gross: CashFlowResult,
    inforce: object,
    treaty_type: str | None = None,
    cession_pct: float | None = None,
    yrt_rate_per_1000: float | None = None,
    yrt_loading: float | None = None,
    modco_rate: float | None = None,
    use_policy_cession: bool = False,
    yrt_rate_table: object | None = None,
) -> tuple[CashFlowResult, CashFlowResult | None]:
    """Apply a treaty to gross cash flows, deriving YRT rate if needed.

    Uses the centralised deal config for any parameters not explicitly
    overridden. For YRT with mortality-based pricing, derives the rate
    from the gross projection. When ``yrt_rate_table`` is supplied (or
    present in the deal config), the tabular path runs and the flat-rate
    derivation is skipped — the underlying ``YRTTreaty.apply()`` requires
    the inforce block (ADR-051), which is always passed here.

    Args:
        gross: GROSS basis CashFlowResult.
        inforce: InforceBlock (needed for face amount and policy-level cession).
        treaty_type: Override for treaty type.
        cession_pct: Override for cession percentage.
        yrt_rate_per_1000: Override for YRT rate. If None and YRT, derives from gross.
        yrt_loading: Override for YRT loading (used when deriving rate).
        modco_rate: Override for Modco interest rate.
        use_policy_cession: Whether to use policy-level cession overrides.
        yrt_rate_table: Optional pre-loaded ``YRTRateTable``. Takes precedence
            over flat-rate derivation when ``treaty_type == "YRT"``.

    Returns:
        (net, ceded) tuple. ceded is None for "None (Gross)".
    """
    cfg = get_deal_config()
    tt = treaty_type or str(cfg.get("treaty_type", "YRT"))
    cp = cession_pct if cession_pct is not None else float(cfg.get("cession_pct", 0.90))
    mr = modco_rate if modco_rate is not None else float(cfg.get("modco_rate", 0.045))

    if tt == "None (Gross)":
        return gross, None

    face_amount = float(inforce.total_face_amount())  # type: ignore[union-attr]

    # Tabular YRT path — wire the table directly onto the treaty and
    # bypass flat-rate derivation. Inforce is always passed because
    # tabular YRT requires per-policy (age, sex, smoker, duration) lookups.
    effective_table = yrt_rate_table if yrt_rate_table is not None else cfg.get("yrt_rate_table")
    if tt == "YRT" and effective_table is not None:
        treaty = build_treaty(tt, cp, face_amount, mr, yrt_rate_table=effective_table)
        if treaty is None:
            return gross, None
        net, ceded = treaty.apply(gross, inforce=inforce)  # type: ignore[union-attr]
        return net, ceded

    # Resolve YRT rate
    effective_yrt_rate = yrt_rate_per_1000
    if tt == "YRT" and effective_yrt_rate is None:
        rate_basis = str(cfg.get("yrt_rate_basis", "Mortality-based"))
        if rate_basis == "Manual Rate":
            effective_yrt_rate = cfg.get("yrt_rate_per_1000")  # type: ignore[assignment]
        if effective_yrt_rate is None:
            yl = yrt_loading if yrt_loading is not None else float(cfg.get("yrt_loading", 0.10))
            effective_yrt_rate = derive_yrt_rate(gross, face_amount, yl)

    treaty = build_treaty(tt, cp, face_amount, mr, effective_yrt_rate)
    if treaty is None:
        return gross, None

    inforce_arg = inforce if use_policy_cession else None
    net, ceded = treaty.apply(gross, inforce=inforce_arg)  # type: ignore[union-attr]
    return net, ceded

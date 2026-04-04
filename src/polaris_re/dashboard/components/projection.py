"""Shared projection helpers for all dashboard pages.

Provides consistent treaty construction, YRT rate derivation, and
projection execution so every page produces identical results for
the same inputs. This is the single source of truth for how the
dashboard executes projections and applies reinsurance treaties.
"""

from datetime import date

from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.projection import ProjectionConfig
from polaris_re.dashboard.components.state import get_deal_config

__all__ = [
    "build_projection_config",
    "build_treaty",
    "derive_yrt_rate",
    "run_gross_projection",
    "run_treaty_projection",
]


def build_projection_config(
    overrides: dict[str, object] | None = None,
) -> ProjectionConfig:
    """Build a ProjectionConfig from the centralised deal config.

    Args:
        overrides: Optional dict to override specific deal config values.
                   Supported keys: projection_years, discount_rate,
                   acquisition_cost, maintenance_cost.

    Returns:
        ProjectionConfig ready for projection.
    """
    cfg = get_deal_config()
    if overrides:
        cfg = {**cfg, **overrides}

    return ProjectionConfig(
        valuation_date=date.today(),
        projection_horizon_years=int(cfg.get("projection_years", 20)),
        discount_rate=float(cfg.get("discount_rate", 0.06)),
        acquisition_cost_per_policy=float(cfg.get("acquisition_cost", 500.0)),
        maintenance_cost_per_policy_per_year=float(cfg.get("maintenance_cost", 75.0)),
    )


def derive_yrt_rate(
    gross: CashFlowResult,
    face_amount_total: float,
    loading: float = 0.10,
) -> float:
    """Derive a mortality-based YRT rate per $1,000 NAR from a gross projection.

    Uses the first year's actual claims divided by total face amount to
    estimate the implied annual q_x, then applies the loading factor.

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
) -> object | None:
    """Construct a treaty object from the given parameters.

    Args:
        treaty_type: "YRT", "Coinsurance", "Modco", or "None (Gross)".
        cession_pct: Proportion ceded (e.g. 0.90).
        face_amount: Total in-force face amount.
        modco_rate: Modco interest rate (used only for Modco).
        yrt_rate_per_1000: YRT rate per $1,000 NAR. Required for YRT.

    Returns:
        Treaty object or None for "None (Gross)".
    """
    if treaty_type == "YRT":
        from polaris_re.reinsurance.yrt import YRTTreaty

        return YRTTreaty(
            treaty_name="YRT-DASH",
            cession_pct=cession_pct,
            total_face_amount=face_amount,
            flat_yrt_rate_per_1000=yrt_rate_per_1000,
        )
    elif treaty_type == "Coinsurance":
        from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

        return CoinsuranceTreaty(
            treaty_name="COINS-DASH",
            cession_pct=cession_pct,
            include_expense_allowance=True,
        )
    elif treaty_type == "Modco":
        from polaris_re.reinsurance.modco import ModcoTreaty

        return ModcoTreaty(
            treaty_name="MODCO-DASH",
            cession_pct=cession_pct,
            modco_interest_rate=modco_rate,
        )
    return None


def run_gross_projection(
    inforce: object,
    assumptions: object,
    config: ProjectionConfig,
) -> CashFlowResult:
    """Run a gross TermLife projection.

    Args:
        inforce: InforceBlock.
        assumptions: AssumptionSet.
        config: ProjectionConfig.

    Returns:
        GROSS basis CashFlowResult.
    """
    from polaris_re.products.term_life import TermLife

    product = TermLife(
        inforce=inforce,
        assumptions=assumptions,
        config=config,
    )  # type: ignore[arg-type]
    return product.project()


def run_treaty_projection(
    gross: CashFlowResult,
    inforce: object,
    treaty_type: str | None = None,
    cession_pct: float | None = None,
    yrt_rate_per_1000: float | None = None,
    yrt_loading: float | None = None,
    modco_rate: float | None = None,
    use_policy_cession: bool = False,
) -> tuple[CashFlowResult, CashFlowResult | None]:
    """Apply a treaty to gross cash flows, deriving YRT rate if needed.

    Uses the centralised deal config for any parameters not explicitly
    overridden. For YRT with mortality-based pricing, derives the rate
    from the gross projection.

    Args:
        gross: GROSS basis CashFlowResult.
        inforce: InforceBlock (needed for face amount and policy-level cession).
        treaty_type: Override for treaty type.
        cession_pct: Override for cession percentage.
        yrt_rate_per_1000: Override for YRT rate. If None and YRT, derives from gross.
        yrt_loading: Override for YRT loading (used when deriving rate).
        modco_rate: Override for Modco interest rate.
        use_policy_cession: Whether to use policy-level cession overrides.

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

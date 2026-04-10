"""Page 3: Deal Pricing — consumes session state from Pages 1-2.

Requires Inforce Block and Assumptions to be configured first. No fallback
mechanism — all inputs are centralised on the Assumptions page.

Provides separate Cedant and Reinsurer views of cash flows for clarity.
When the inforce block contains multiple product types, each distinct
``product_type`` is priced as its own independent cohort (separate gross
projection, treaty, and profit test) displayed in per-cohort tabs.
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.analytics.profit_test import ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import iter_cohorts
from polaris_re.core.projection import ProjectionConfig
from polaris_re.dashboard.components.charts import cashflow_waterfall
from polaris_re.dashboard.components.projection import (
    build_projection_config,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    run_gross_projection,
    run_treaty_projection,
)
from polaris_re.dashboard.components.state import get_deal_config

__all__ = ["page_pricing"]


@dataclass(frozen=True)
class CohortPricingData:
    """Typed per-cohort pricing artefacts used by the Deal Pricing page.

    Holds the raw projection and profit-test objects for rendering.
    Replaces an earlier ``dict[str, object]`` shape so downstream code
    (summary tables, tabs, session-state bridging) gets clean types.
    """

    cohort_id: str
    n_policies: int
    face_amount: float
    gross: CashFlowResult
    net: CashFlowResult
    ceded: CashFlowResult | None
    result: ProfitTestResult
    reinsurer_result: ProfitTestResult | None
    treaty_type: str
    loss_ratio_msg: tuple[str, str] | None


# Flat session-state keys preserved for single-cohort backward compatibility.
# Downstream pages (IFRS17, Treaty Compare) still read these directly. When a
# mixed-cohort run occurs, these are cleared so those pages show their
# mixed-block guard instead of stale single-cohort data.
_FLAT_PRICING_KEYS = (
    "pricing_result",
    "pricing_net_result",
    "pricing_ceded_result",
    "pricing_treaty_type",
    "reinsurer_result",
    "gross_result",
)


def _cash_flow_decomposition(
    cf_result: object,
    title_suffix: str = "",
    annotate_reserve_release: bool = False,
) -> plt.Figure:
    """Stacked area chart of premiums, claims, expenses, reserve increase, net cash flow."""
    from polaris_re.core.cashflow import CashFlowResult

    cf: CashFlowResult = cf_result  # type: ignore[assignment]
    n_years = cf.projection_months // 12

    annual_premiums = np.array(
        [cf.gross_premiums[i * 12 : (i + 1) * 12].sum() for i in range(n_years)]
    )
    annual_claims = np.array([cf.death_claims[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])
    annual_expenses = np.array([cf.expenses[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])
    annual_reserve_inc = np.array(
        [cf.reserve_increase[i * 12 : (i + 1) * 12].sum() for i in range(n_years)]
    )
    annual_ncf = np.array([cf.net_cash_flow[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])

    years = np.arange(1, n_years + 1)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(years, annual_premiums, label="Premiums", color="#2ecc71", linewidth=2)
    ax.plot(years, annual_claims, label="Claims", color="#e74c3c", linewidth=2)
    if annual_expenses.any():
        ax.plot(years, annual_expenses, label="Expenses", color="#f39c12", linewidth=2)
    ax.plot(
        years,
        annual_reserve_inc,
        label="Reserve Increase",
        color="#9b59b6",
        linewidth=1.5,
        linestyle="-.",
    )
    ax.plot(years, annual_ncf, label="Net Cash Flow", color="#3498db", linewidth=2, linestyle="--")
    ax.axhline(0, color="black", linewidth=0.5, linestyle=":")

    # Annotate reserve release when NCF > Premiums
    if annotate_reserve_release:
        release_years = np.where(annual_reserve_inc < 0)[0]
        if len(release_years) > 0:
            first_release = release_years[0]
            ax.annotate(
                "Reserve release\n(negative reserve inc.\nboosts NCF)",
                xy=(years[first_release], annual_ncf[first_release]),
                xytext=(years[first_release] + 2, annual_ncf[first_release] * 1.15),
                arrowprops={"arrowstyle": "->", "color": "#7f8c8d"},
                fontsize=8,
                color="#7f8c8d",
                ha="left",
            )

    ax.set_xlabel("Policy Year")
    ax.set_ylabel("Amount ($)")
    title = "Annual Cash Flow Decomposition"
    if title_suffix:
        title += f" \u2014 {title_suffix}"
    ax.set_title(title)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def _reserve_chart(gross: object) -> plt.Figure:
    """Reserve balance over time."""
    from polaris_re.core.cashflow import CashFlowResult

    cf: CashFlowResult = gross  # type: ignore[assignment]
    months = np.arange(cf.projection_months)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(
        months / 12, cf.reserve_balance, alpha=0.3, color="#9b59b6", label="Reserve Balance"
    )
    ax.plot(months / 12, cf.reserve_balance, color="#9b59b6", linewidth=1.5)
    ax.set_xlabel("Year")
    ax.set_ylabel("Reserve ($)")
    ax.set_title("Reserve Balance Over Time")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def _reinsurer_cash_flow_chart(ceded: object, treaty_type: str) -> plt.Figure:
    """Cash flow decomposition from the reinsurer's perspective (ceded basis).

    For the reinsurer:
        Income = ceded premiums received (YRT premiums for YRT, proportional for coinsurance)
        Outgo  = ceded claims paid
        NCF    = ceded net cash flow (ceded_premiums - ceded_claims - ceded_expenses - ...)
    """
    from polaris_re.core.cashflow import CashFlowResult

    cf: CashFlowResult = ceded  # type: ignore[assignment]
    n_years = cf.projection_months // 12

    annual_premiums = np.array(
        [cf.gross_premiums[i * 12 : (i + 1) * 12].sum() for i in range(n_years)]
    )
    annual_claims = np.array([cf.death_claims[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])
    annual_expenses = np.array([cf.expenses[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])
    annual_reserve_inc = np.array(
        [cf.reserve_increase[i * 12 : (i + 1) * 12].sum() for i in range(n_years)]
    )
    annual_ncf = np.array([cf.net_cash_flow[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])

    years = np.arange(1, n_years + 1)
    fig, ax = plt.subplots(figsize=(10, 5))

    prem_label = "YRT Premiums Received" if treaty_type == "YRT" else "Ceded Premiums Received"
    ax.plot(years, annual_premiums, label=prem_label, color="#2ecc71", linewidth=2)
    ax.plot(years, annual_claims, label="Claims Paid", color="#e74c3c", linewidth=2)
    if annual_expenses.any():
        ax.plot(years, annual_expenses, label="Expense Allowance", color="#f39c12", linewidth=2)
    if annual_reserve_inc.any():
        ax.plot(
            years,
            annual_reserve_inc,
            label="Reserve Increase",
            color="#9b59b6",
            linewidth=1.5,
            linestyle="-.",
        )
    ax.plot(
        years,
        annual_ncf,
        label="Reinsurer NCF",
        color="#3498db",
        linewidth=2,
        linestyle="--",
    )
    ax.axhline(0, color="black", linewidth=0.5, linestyle=":")
    ax.set_xlabel("Policy Year")
    ax.set_ylabel("Amount ($)")
    ax.set_title(f"Reinsurer Cash Flow \u2014 {treaty_type}")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def _table_vs_ml_comparison(assumption_set: object, ml_mort: object) -> None:
    """Show Table vs ML mortality q_x comparison chart."""
    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.core.policy import Sex, SmokerStatus

    a_set: AssumptionSet = assumption_set  # type: ignore[assignment]

    with st.expander("Table vs ML Mortality Comparison"):
        ages = np.arange(25, 71, dtype=np.int32)
        durations = np.full_like(ages, 12)

        try:
            table_rates = a_set.mortality.get_qx_vector(
                ages, Sex.MALE, SmokerStatus.NON_SMOKER, durations
            )
            ml_rates = ml_mort.get_qx_vector(  # type: ignore[union-attr]
                ages, Sex.MALE, SmokerStatus.NON_SMOKER, durations
            )

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(ages, table_rates * 12, label="Table (monthly\u00d712)", color="#3498db", lw=2)
            ax.plot(ages, ml_rates * 12, label="ML Model (monthly\u00d712)", color="#e74c3c", lw=2)
            ax.set_xlabel("Attained Age")
            ax.set_ylabel("Approx Annual q_x")
            ax.set_title("Table vs ML Mortality \u2014 Male Non-Smoker")
            ax.legend()
            ax.set_yscale("log")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

            ratio = ml_rates / np.maximum(table_rates, 1e-10)
            fig2, ax2 = plt.subplots(figsize=(10, 4))
            ax2.plot(ages, ratio, color="#9b59b6", linewidth=2)
            ax2.axhline(1.0, color="black", linestyle="--", alpha=0.5)
            ax2.set_xlabel("Attained Age")
            ax2.set_ylabel("ML / Table Ratio")
            ax2.set_title("ML-to-Table Mortality Ratio")
            ax2.grid(True, alpha=0.3)
            fig2.tight_layout()
            st.pyplot(fig2)
            plt.close(fig2)
        except Exception as exc:
            st.warning(f"Could not generate Table vs ML comparison: {exc}")


def _format_irr(irr: float | None, treaty_type: str) -> str:
    """Format IRR with explanation when N/A."""
    if irr is not None:
        return f"{irr:.2%}"
    return "N/A"


def _irr_explanation(irr: float | None, treaty_type: str) -> str | None:
    """Return an explanatory note when IRR is undefined."""
    if irr is not None:
        return None
    if treaty_type == "YRT":
        return (
            "IRR is undefined because the reinsurer's net cash flows are "
            "positive in all projection years (no sign change occurs). "
            "This is typical for YRT structures where the reinsurer has no "
            "upfront capital deployment. Consider the profit margin and "
            "PV Profit metrics instead."
        )
    return (
        "IRR is undefined because net cash flows have no sign change. "
        "This can occur when the deal is always profitable (or always "
        "unprofitable) throughout the projection."
    )


def _run_pricing_for_cohort(
    cohort_id: str,
    cohort_inforce: InforceBlock,
    assumption_set: AssumptionSet,
    config: ProjectionConfig,
    treaty_type: str,
    use_policy_cession: bool,
    hurdle_rate: float,
    parity_label: str,
    show_yrt_info: bool,
) -> CohortPricingData:
    """Run the full pricing pipeline for a single-product cohort.

    Returns a ``CohortPricingData`` carrying the raw projection and
    profit-test objects for later rendering. Does NOT touch session state.
    """
    from polaris_re.analytics.profit_test import ProfitTester
    from polaris_re.core.pipeline import dump_parity_debug

    cfg = get_deal_config()

    # 1. Gross projection via product dispatch
    gross = run_gross_projection(cohort_inforce, assumption_set, config)

    face_amount_total = float(cohort_inforce.total_face_amount())

    # 2. Show derived YRT rate info (only for the single-cohort case to
    #    avoid cluttering the screen when there are many cohorts; per-cohort
    #    rate info is still captured in the parity debug dump).
    if show_yrt_info and treaty_type == "YRT":
        yrt_loading = float(cfg.get("yrt_loading", 0.10))  # type: ignore[arg-type]
        yrt_manual_rate = cfg.get("yrt_rate_per_1000")
        rate_basis = str(cfg.get("yrt_rate_basis", "Mortality-based"))

        if rate_basis == "Mortality-based" or yrt_manual_rate is None:
            derived_rate = derive_yrt_rate(gross, face_amount_total, yrt_loading)
            implied_qx = derived_rate / (1000.0 * (1.0 + yrt_loading))
            st.info(
                f"Derived YRT rate ({cohort_id}): {derived_rate:.3f} per $1,000 NAR "
                f"(implied q_x = {implied_qx:.5f}, loading = {yrt_loading:.0%})"
            )

    # 3. Apply treaty
    net, ceded = run_treaty_projection(
        gross,
        cohort_inforce,
        use_policy_cession=use_policy_cession,
    )

    # 4. Parity diagnostic dump (disambiguated per cohort)
    dump_parity_debug(parity_label, gross, net, ceded)

    # 5. Cedant profit test
    result = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate).run()

    # 6. Reinsurer profit test on ceded re-labelled as net (ADR-039)
    reinsurer_result: ProfitTestResult | None = None
    if ceded is not None:
        reinsurer_result = ProfitTester(
            cashflows=ceded_to_reinsurer_view(ceded), hurdle_rate=hurdle_rate
        ).run()

    # 7. Sanity check: loss ratio warning
    total_claims = float(gross.death_claims.sum())
    total_premiums = float(gross.gross_premiums.sum())
    loss_ratio_msg: tuple[str, str] | None = None
    if total_premiums > 0:
        loss_ratio = total_claims / total_premiums
        if loss_ratio < 0.01:
            loss_ratio_msg = (
                "error",
                f"**Pricing Validation Warning ({cohort_id})**: "
                f"Aggregate loss ratio is {loss_ratio:.4%} "
                f"(claims ${total_claims:,.0f} vs premiums "
                f"${total_premiums:,.0f}). Expected 20-80%.",
            )
        elif loss_ratio > 2.0:
            loss_ratio_msg = (
                "warning",
                f"**Pricing Validation Warning ({cohort_id})**: "
                f"Loss ratio is {loss_ratio:.2%} \u2014 claims far exceed premiums.",
            )
        else:
            loss_ratio_msg = (
                "caption",
                f"Validation ({cohort_id}): gross loss ratio = {loss_ratio:.1%}, "
                f"total claims = ${total_claims:,.0f}, "
                f"total premiums = ${total_premiums:,.0f}",
            )

    return CohortPricingData(
        cohort_id=cohort_id,
        n_policies=cohort_inforce.n_policies,
        face_amount=face_amount_total,
        gross=gross,
        net=net,
        ceded=ceded,
        result=result,
        reinsurer_result=reinsurer_result,
        treaty_type=treaty_type,
        loss_ratio_msg=loss_ratio_msg,
    )


def _render_cohort_results(cohort_data: CohortPricingData, assumption_set: AssumptionSet) -> None:
    """Render cedant + reinsurer views for a single priced cohort."""
    gross = cohort_data.gross
    net = cohort_data.net
    ceded = cohort_data.ceded
    result = cohort_data.result
    reinsurer_result = cohort_data.reinsurer_result
    cached_treaty_type = cohort_data.treaty_type
    loss_ratio_msg = cohort_data.loss_ratio_msg

    if loss_ratio_msg is not None:
        level, msg = loss_ratio_msg
        if level == "error":
            st.error(msg)
        elif level == "warning":
            st.warning(msg)
        else:
            st.caption(msg)

    # ========== CEDANT VIEW ==========
    st.subheader("Cedant View (Retained)")
    basis_label = "Gross" if cached_treaty_type == "None (Gross)" else f"Net ({cached_treaty_type})"

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("PV Profits (Cedant)", f"${result.pv_profits:,.0f}")
    col_b.metric(
        "Profit Margin",
        f"{result.profit_margin:.2%}",
        help="PV(Net Cash Flow) / PV(Net Premiums) at the hurdle rate.",
    )
    col_c.metric("IRR", _format_irr(result.irr, cached_treaty_type))
    bey = str(result.breakeven_year) if result.breakeven_year else "N/A"
    col_d.metric("Break-even Year", bey)

    irr_note = _irr_explanation(result.irr, cached_treaty_type)
    if irr_note:
        st.caption(irr_note)

    st.pyplot(
        cashflow_waterfall(
            result.profit_by_year,
            title="Cedant Annual Profit Waterfall",
        )
    )
    st.pyplot(
        _cash_flow_decomposition(net, title_suffix=basis_label, annotate_reserve_release=True)
    )

    # ========== REINSURER VIEW ==========
    if ceded is not None and reinsurer_result is not None:
        st.subheader("Reinsurer View (Ceded)")

        rc_a, rc_b, rc_c, rc_d = st.columns(4)
        rc_a.metric(
            "PV Profits (Reinsurer)",
            f"${reinsurer_result.pv_profits:,.0f}",
        )

        ceded_total_claims = float(ceded.death_claims.sum())
        ceded_total_premiums = float(ceded.gross_premiums.sum())
        net_loss_ratio = (
            ceded_total_claims / ceded_total_premiums if ceded_total_premiums > 0 else 0.0
        )
        rc_b.metric(
            "Net Loss Ratio",
            f"{net_loss_ratio:.1%}",
            help=(
                "Ceded Claims / Ceded Premiums (undiscounted). "
                "For a profitable reinsurer, this should be < 100%."
            ),
        )
        rc_c.metric(
            "Reinsurer Margin",
            f"{reinsurer_result.profit_margin:.2%}",
            help="PV(Reinsurer NCF) / PV(Ceded Premiums) at the hurdle rate.",
        )
        rc_d.metric(
            "IRR",
            _format_irr(reinsurer_result.irr, cached_treaty_type),
        )

        irr_note_r = _irr_explanation(
            reinsurer_result.irr,
            cached_treaty_type,
        )
        if irr_note_r:
            st.caption(irr_note_r)

        st.pyplot(_reinsurer_cash_flow_chart(ceded, cached_treaty_type))

    # ========== GROSS RESERVE ==========
    st.subheader("Reserve Balance")
    st.pyplot(_reserve_chart(gross))

    # ========== NCF FORMULA EXPLANATION ==========
    st.caption(
        "**NCF formula**: Net Cash Flow = Premiums \u2212 Claims \u2212 Expenses "
        "\u2212 Reserve Increase. When reserves release (reserve increase turns "
        "negative in later years), NCF can exceed premiums. This is normal for "
        "term life as the in-force shrinks and reserves run off."
    )

    # ========== ANNUAL TABLE ==========
    n_years = net.projection_months // 12
    annual_data = []
    for yr in range(n_years):
        s, e = yr * 12, (yr + 1) * 12
        row: dict[str, str | int] = {"Year": yr + 1}
        if cached_treaty_type != "None (Gross)":
            row["Gross Premiums"] = f"${gross.gross_premiums[s:e].sum():,.0f}"
            row["Gross Claims"] = f"${gross.death_claims[s:e].sum():,.0f}"
        row["Net Premiums"] = f"${net.gross_premiums[s:e].sum():,.0f}"
        row["Net Claims"] = f"${net.death_claims[s:e].sum():,.0f}"
        row["Expenses"] = f"${net.expenses[s:e].sum():,.0f}"
        row["Reserve Inc."] = f"${net.reserve_increase[s:e].sum():,.0f}"
        row["Net Cash Flow"] = f"${net.net_cash_flow[s:e].sum():,.0f}"
        row["Cumul. NCF"] = f"${net.net_cash_flow[:e].sum():,.0f}"
        if ceded is not None:
            row["Ceded Premiums"] = f"${ceded.gross_premiums[s:e].sum():,.0f}"
            row["Ceded Claims"] = f"${ceded.death_claims[s:e].sum():,.0f}"
            row["Reinsurer NCF"] = f"${ceded.net_cash_flow[s:e].sum():,.0f}"
        if gross.lapse_count is not None:
            row["Lapse Exits"] = f"{gross.lapse_count[s:e].sum():,.1f}"
        annual_data.append(row)

    st.subheader(f"Annual Summary \u2014 {basis_label}")
    if cached_treaty_type == "YRT":
        st.caption(
            "**YRT mechanics**: Cedant retains gross premiums and pays separate "
            "YRT premiums to the reinsurer (shown as 'Ceded Premiums'). "
            "Claims are ceded proportionally. Reserves stay with the cedant."
        )
    elif cached_treaty_type == "Coinsurance":
        st.caption(
            "**Coinsurance mechanics**: Reinsurer takes a proportional share "
            "of ALL cash flows including reserves. Both mortality and lapse "
            "risk are transferred."
        )
    st.dataframe(annual_data, use_container_width=True)

    # Table vs ML comparison
    ml_mort = st.session_state.get("ml_mortality_model")
    if ml_mort is not None:
        _table_vs_ml_comparison(assumption_set, ml_mort)


def page_pricing() -> None:
    """Deal pricing page \u2014 requires session state from Pages 1-2.

    When the inforce contains multiple product types, each cohort is priced
    as an independent deal (separate gross projection, treaty, profit test)
    and shown in a dedicated tab. No cross-product aggregation is performed.
    """
    st.header("Deal Pricing")

    # Check prerequisites
    inforce_block = st.session_state.get("inforce_block")
    assumption_set = st.session_state.get("assumption_set")
    cfg = get_deal_config()

    if inforce_block is None or assumption_set is None:
        st.warning(
            "Configure **Inforce Block** (Page 1) and **Assumptions** (Page 2) first. "
            "All deal inputs \u2014 including treaty structure, expenses, and projection "
            "parameters \u2014 are set on the Assumptions page."
        )
        return

    # Partition the block into single-product cohorts. For homogeneous
    # blocks this is a zero-cost single-element list; for mixed blocks it
    # returns one sub-block per distinct product type.
    cohorts = iter_cohorts(inforce_block)
    n_cohorts = len(cohorts)

    if n_cohorts > 1:
        detected = ", ".join(pt.value for pt, _ in cohorts)
        st.info(
            f"Mixed product block detected ({n_cohorts} cohorts: {detected}). "
            f"Each cohort will be priced as an independent deal and shown in its own tab. "
            f"There is no cross-product aggregation \u2014 every cohort carries its own "
            f"PV profits, IRR, and break-even metrics."
        )
    else:
        st.success(
            f"Using session state: {inforce_block.n_policies:,} policies, "
            f"assumptions v{assumption_set.version}"
        )

    # Show current deal config summary
    treaty_type = str(cfg.get("treaty_type", "YRT"))
    cession_pct = float(cfg.get("cession_pct", 0.90))
    with st.expander("Current Deal Configuration (edit on Assumptions page)", expanded=False):
        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric("Treaty", treaty_type)
        dc2.metric("Cession", f"{cession_pct:.0%}")
        dc3.metric("Discount Rate", f"{float(cfg.get('discount_rate', 0.06)):.0%}")
        dc4.metric("Hurdle Rate", f"{float(cfg.get('hurdle_rate', 0.10)):.0%}")

        dc5, dc6, dc7, dc8 = st.columns(4)
        dc5.metric("Projection", f"{int(cfg.get('projection_years', 20))} years")
        dc6.metric("Acq. Cost", f"${float(cfg.get('acquisition_cost', 500)):,.0f}/policy")
        dc7.metric("Maint. Cost", f"${float(cfg.get('maintenance_cost', 75)):,.0f}/yr/policy")
        if treaty_type == "YRT":
            basis = str(cfg.get("yrt_rate_basis", "Mortality-based"))
            loading = float(cfg.get("yrt_loading", 0.10))
            dc8.metric(
                "YRT Basis",
                f"{basis} ({loading:.0%} loading)" if basis == "Mortality-based" else basis,
            )

    # Optional per-run overrides (minimal — most config is on Assumptions page)
    use_policy_cession = st.checkbox(
        "Use policy-level cession overrides",
        help="Uses per-policy reinsurance_cession_pct from inforce data (ADR-036).",
    )

    if st.button("Run Pricing", type="primary"):
        with st.spinner("Running projection..."):
            config = build_projection_config()
            hurdle_rate = float(cfg.get("hurdle_rate", 0.10))  # type: ignore[arg-type]

            cohort_data_map: dict[str, CohortPricingData] = {}
            for product_type, cohort_inforce in cohorts:
                cohort_id = product_type.value
                parity_label = f"dashboard_{cohort_id.lower()}" if n_cohorts > 1 else "dashboard"
                cohort_data_map[cohort_id] = _run_pricing_for_cohort(
                    cohort_id=cohort_id,
                    cohort_inforce=cohort_inforce,
                    assumption_set=assumption_set,
                    config=config,
                    treaty_type=treaty_type,
                    use_policy_cession=use_policy_cession,
                    hurdle_rate=hurdle_rate,
                    parity_label=parity_label,
                    show_yrt_info=(n_cohorts == 1),
                )

        # Store multi-cohort results
        st.session_state["pricing_cohorts"] = cohort_data_map

        # Backward-compat flat keys: preserved for single-cohort so that
        # IFRS17 and Treaty Compare pages keep working unchanged. Cleared
        # on multi-cohort runs so those pages trip their mixed-block guard.
        if n_cohorts == 1:
            only = next(iter(cohort_data_map.values()))
            st.session_state["gross_result"] = only.gross
            st.session_state["pricing_result"] = only.result
            st.session_state["pricing_net_result"] = only.net
            st.session_state["pricing_ceded_result"] = only.ceded
            st.session_state["pricing_treaty_type"] = treaty_type
            if only.reinsurer_result is not None:
                st.session_state["reinsurer_result"] = only.reinsurer_result
            elif "reinsurer_result" in st.session_state:
                del st.session_state["reinsurer_result"]
        else:
            for k in _FLAT_PRICING_KEYS:
                if k in st.session_state:
                    del st.session_state[k]

    # --- Display results from session state ---
    cohort_data_map = st.session_state.get("pricing_cohorts")  # type: ignore[assignment]
    if not cohort_data_map:
        return

    if len(cohort_data_map) == 1:
        only = next(iter(cohort_data_map.values()))
        _render_cohort_results(only, assumption_set)
        return

    # Mixed-cohort summary table above the tabs
    summary_rows = []
    total_cedant_pv = 0.0
    total_reinsurer_pv = 0.0
    for cohort_id, data in cohort_data_map.items():
        cedant_pv = float(data.result.pv_profits)
        total_cedant_pv += cedant_pv
        rei_pv: float | None = None
        if data.reinsurer_result is not None:
            rei_pv = float(data.reinsurer_result.pv_profits)
            total_reinsurer_pv += rei_pv
        summary_rows.append(
            {
                "Cohort": cohort_id,
                "Policies": f"{data.n_policies:,}",
                "Face Amount": f"${data.face_amount:,.0f}",
                "Cedant PV Profits": f"${cedant_pv:,.0f}",
                "Reinsurer PV Profits": (f"${rei_pv:,.0f}" if rei_pv is not None else "N/A"),
                "Cedant IRR": (f"{data.result.irr:.2%}" if data.result.irr is not None else "N/A"),
            }
        )

    st.subheader("Mixed-Cohort Summary")
    st.dataframe(summary_rows, use_container_width=True)
    ms_a, ms_b = st.columns(2)
    ms_a.metric("Total PV Profits (Cedant)", f"${total_cedant_pv:,.0f}")
    ms_b.metric("Total PV Profits (Reinsurer)", f"${total_reinsurer_pv:,.0f}")
    st.caption(
        "Per-cohort IRRs are not summed. Each cohort is an independent deal \u2014 "
        "cross-product aggregation (single blended IRR) is a separate feature. "
        "Note: **Treaty Comparison**, **Scenario Analysis**, **Monte Carlo UQ**, "
        "and **IFRS 17** pages do not yet support mixed blocks; they will show a "
        "guard message until you filter the inforce to a single product type."
    )

    # Per-cohort tabs
    tab_labels = list(cohort_data_map.keys())
    tabs = st.tabs(tab_labels)
    for tab, cohort_id in zip(tabs, tab_labels, strict=True):
        with tab:
            _render_cohort_results(cohort_data_map[cohort_id], assumption_set)

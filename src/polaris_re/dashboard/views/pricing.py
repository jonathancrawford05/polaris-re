"""Page 3: Deal Pricing — rebuilt to consume session state from Pages 1-2."""

from datetime import date

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import cashflow_waterfall

__all__ = ["page_pricing"]


def _build_fallback_assumptions(
    flat_qx: float,
    flat_lapse: float,
    valuation_date: date,
) -> object:
    """Build minimal AssumptionSet for dashboard with flat rates (fallback)."""
    from pathlib import Path

    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.policy import Sex, SmokerStatus
    from polaris_re.utils.table_io import MortalityTableArray

    n_ages = 121 - 18
    qx = np.full(n_ages, flat_qx, dtype=np.float64)
    rates_2d = qx.reshape(-1, 1)

    # Create table arrays for all sex/smoker combos so any policy can be priced
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

    mortality = MortalityTable(
        source=MortalityTableSource.CSO_2001,
        table_name="Synthetic Dashboard",
        min_age=18,
        max_age=120,
        select_period_years=0,
        has_smoker_distinct_rates=False,
        tables=tables,
    )
    lapse = LapseAssumption.from_duration_table(
        {1: flat_lapse, 2: flat_lapse, 3: flat_lapse, "ultimate": flat_lapse}
    )
    return AssumptionSet(
        mortality=mortality, lapse=lapse, version="dashboard-v1", effective_date=valuation_date
    )


def _build_fallback_block(
    n_policies: int,
    attained_age: int,
    face_amount: float,
    flat_qx: float,
    target_loss_ratio: float,
    term_years: int,
    valuation_date: date,
) -> object:
    """Build InforceBlock for dashboard (fallback when Page 1 not configured)."""
    from polaris_re.core.inforce import InforceBlock
    from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus

    # Calibrate premium to mortality and loss ratio
    # flat_qx is annual; premium = face * qx / loss_ratio
    annual_premium = (face_amount * flat_qx) / target_loss_ratio

    policies = [
        Policy(
            policy_id=f"P{i:05d}",
            issue_age=attained_age,
            attained_age=attained_age,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=face_amount,
            annual_premium=annual_premium,
            policy_term=term_years,
            duration_inforce=0,
            reinsurance_cession_pct=0.0,
            issue_date=valuation_date,
            valuation_date=valuation_date,
            product_type=ProductType.TERM,
        )
        for i in range(n_policies)
    ]
    return InforceBlock(policies=policies)


def _cash_flow_decomposition(cf_result: object, title_suffix: str = "") -> plt.Figure:
    """Stacked area chart of premiums, claims, expenses, net cash flow."""
    from polaris_re.core.cashflow import CashFlowResult

    cf: CashFlowResult = cf_result  # type: ignore[assignment]
    # Annualise: sum monthly values into yearly
    n_years = cf.projection_months // 12

    annual_premiums = np.array(
        [cf.gross_premiums[i * 12 : (i + 1) * 12].sum() for i in range(n_years)]
    )
    annual_claims = np.array([cf.death_claims[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])
    annual_expenses = np.array([cf.expenses[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])
    annual_ncf = np.array([cf.net_cash_flow[i * 12 : (i + 1) * 12].sum() for i in range(n_years)])

    years = np.arange(1, n_years + 1)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(years, annual_premiums, label="Premiums", color="#2ecc71", linewidth=2)
    ax.plot(years, annual_claims, label="Claims", color="#e74c3c", linewidth=2)
    if annual_expenses.any():
        ax.plot(years, annual_expenses, label="Expenses", color="#f39c12", linewidth=2)
    ax.plot(years, annual_ncf, label="Net Cash Flow", color="#3498db", linewidth=2, linestyle="--")
    ax.axhline(0, color="black", linewidth=0.5, linestyle=":")
    ax.set_xlabel("Policy Year")
    ax.set_ylabel("Amount ($)")
    title = "Annual Cash Flow Decomposition"
    if title_suffix:
        title += f" \u2014 {title_suffix}"
    ax.set_title(title)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.legend()
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


def _build_treaty(
    treaty_type: str,
    cession_pct: float,
    face_amount: float,
    modco_rate: float = 0.045,
    yrt_rate_per_1000: float | None = None,
) -> object:
    """Construct the selected treaty object."""
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
            treaty_name="COINS-DASH", cession_pct=cession_pct, include_expense_allowance=True
        )
    elif treaty_type == "Modco":
        from polaris_re.reinsurance.modco import ModcoTreaty

        return ModcoTreaty(
            treaty_name="MODCO-DASH",
            cession_pct=cession_pct,
            modco_interest_rate=modco_rate,
        )
    return None


def _table_vs_ml_comparison(assumption_set: object, ml_mort: object) -> None:
    """Show Table vs ML mortality q_x comparison chart."""
    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.core.policy import Sex, SmokerStatus

    a_set: AssumptionSet = assumption_set  # type: ignore[assignment]

    with st.expander("Table vs ML Mortality Comparison"):
        ages = np.arange(25, 71, dtype=np.int32)
        durations = np.full_like(ages, 12)  # 1 year into select

        try:
            # Table-based rates
            table_rates = a_set.mortality.get_qx_vector(
                ages, Sex.MALE, SmokerStatus.NON_SMOKER, durations
            )

            # ML-based rates
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

            # Ratio chart
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


def page_pricing() -> None:
    """Deal pricing page — rebuilt to use session state inforce + assumptions."""
    st.header("Deal Pricing")

    # Check for session state prerequisites
    inforce_block = st.session_state.get("inforce_block")
    assumption_set = st.session_state.get("assumption_set")

    if inforce_block is None or assumption_set is None:
        st.warning(
            "Configure **Inforce Block** (Page 1) and **Assumptions** (Page 2) first, "
            "or use the fallback sliders below."
        )
        use_session = False
    else:
        st.success(
            f"Using session state: {inforce_block.n_policies} policies, "
            f"assumptions v{assumption_set.version}"
        )
        use_session = True

    # Treaty configuration
    st.subheader("Treaty Configuration")
    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        treaty_type = st.selectbox("Treaty Type", ["YRT", "Coinsurance", "Modco", "None (Gross)"])
    with tc2:
        cession_pct = float(st.slider("Cession %", 50, 100, 90)) / 100.0
    with tc3:
        modco_rate = 0.045
        if treaty_type == "Modco":
            modco_rate = float(st.slider("Modco Interest Rate (%)", 1.0, 8.0, 4.5, step=0.5)) / 100
        use_policy_cession = st.checkbox(
            "Use policy-level cession overrides",
            help="Uses per-policy reinsurance_cession_pct from inforce data (ADR-036).",
        )

    # YRT rate configuration
    yrt_rate_per_1000: float | None = None
    if treaty_type == "YRT":
        yrt_basis = st.selectbox(
            "YRT Rate Basis",
            ["Mortality-based", "Manual Rate"],
            help=(
                "Mortality-based: derives YRT rate from the portfolio's average "
                "mortality rate with a configurable loading. "
                "Manual: enter a flat rate per $1,000 NAR directly."
            ),
        )
        if yrt_basis == "Mortality-based":
            yrt_loading = (
                float(
                    st.slider(
                        "YRT Loading over Expected Mortality (%)",
                        min_value=0,
                        max_value=50,
                        value=10,
                        step=5,
                        help=(
                            "Reinsurer margin above expected mortality. "
                            "10% means YRT rate = q_x * 1.10."
                        ),
                    )
                )
                / 100.0
            )
            st.session_state["yrt_loading"] = yrt_loading
        else:
            yrt_rate_per_1000 = float(
                st.number_input(
                    "Flat YRT Rate per $1,000 NAR",
                    min_value=0.01,
                    max_value=50.0,
                    value=2.0,
                    step=0.1,
                    format="%.2f",
                    help="Annual rate per $1,000 of Net Amount at Risk.",
                )
            )

    # Projection parameters
    st.subheader("Projection Parameters")
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        projection_years = int(st.slider("Projection Horizon (years)", 5, 30, 20))
    with pc2:
        discount_rate = float(st.slider("Discount Rate (%)", 2, 12, 6)) / 100.0
    with pc3:
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0

    # Expense loading
    st.subheader("Expense Loading")
    ec1, ec2 = st.columns(2)
    with ec1:
        acquisition_cost = float(
            st.number_input(
                "Acquisition Cost per Policy ($)",
                min_value=0,
                max_value=10_000,
                value=500,
                step=50,
                help="One-time cost at issue: underwriting, commission, setup.",
            )
        )
    with ec2:
        maintenance_cost = float(
            st.number_input(
                "Annual Maintenance Cost per Policy ($)",
                min_value=0,
                max_value=1_000,
                value=75,
                step=5,
                help="Ongoing admin cost per in-force policy per year.",
            )
        )

    # Fallback sliders when session state not populated
    if not use_session:
        st.subheader("Fallback: Manual Block & Assumptions")
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            n_policies = int(
                st.number_input(
                    "Number of Policies", min_value=1, max_value=10000, value=100, step=10
                )
            )
            attained_age = int(st.slider("Attained Age", 25, 65, 40))
        with fc2:
            face_amount = float(
                st.number_input(
                    "Face Amount ($)",
                    min_value=50_000,
                    max_value=5_000_000,
                    value=500_000,
                    step=50_000,
                )
            )
            target_loss_ratio = st.slider(
                "Target Loss Ratio",
                min_value=0.30,
                max_value=0.90,
                value=0.60,
                step=0.05,
                help="Ratio of expected claims to premiums. Lower = more profitable.",
            )
        with fc3:
            flat_qx = (
                float(st.slider("Mortality Rate (q_x \u2030)", 0.1, 10.0, 1.0, step=0.1)) / 1000.0
            )
            flat_lapse = float(st.slider("Lapse Rate (%)", 1, 20, 5)) / 100.0

    if st.button("Run Pricing", type="primary"):
        from polaris_re.analytics.profit_test import ProfitTester
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.products.term_life import TermLife

        with st.spinner("Running projection..."):
            valuation_date = date.today()
            config = ProjectionConfig(
                valuation_date=valuation_date,
                projection_horizon_years=projection_years,
                discount_rate=discount_rate,
                acquisition_cost_per_policy=acquisition_cost,
                maintenance_cost_per_policy_per_year=maintenance_cost,
            )

            if use_session:
                inforce = inforce_block
                assumptions = assumption_set
                face_amount_total = float(inforce.total_face_amount())
            else:
                inforce = _build_fallback_block(
                    n_policies,  # type: ignore[possibly-undefined]
                    attained_age,  # type: ignore[possibly-undefined]
                    face_amount,  # type: ignore[possibly-undefined]
                    flat_qx,  # type: ignore[possibly-undefined]
                    target_loss_ratio,  # type: ignore[possibly-undefined]
                    projection_years,
                    valuation_date,
                )
                assumptions = _build_fallback_assumptions(
                    flat_qx,
                    flat_lapse,
                    valuation_date,  # type: ignore[possibly-undefined]
                )
                face_amount_total = face_amount  # type: ignore[possibly-undefined]

            product = TermLife(inforce=inforce, assumptions=assumptions, config=config)  # type: ignore[arg-type]
            gross = product.project()
            st.session_state["gross_result"] = gross

            # Derive mortality-based YRT rate if applicable
            if treaty_type == "YRT" and yrt_rate_per_1000 is None:
                # Compute portfolio average annual q_x from gross cash flows:
                # avg_qx = total_claims / total_face_exposure
                # where face_exposure approximates sum of (lx * face) over time.
                total_claims = float(gross.death_claims.sum())
                # Annual face exposure: sum of monthly (premium / monthly_prem)
                # approximated as total_premiums / (claims_rate * face)
                # Simpler: derive from the first year's loss ratio
                first_year_claims = float(gross.death_claims[:12].sum())
                first_year_face_exposure = face_amount_total  # approximation for year 1
                if first_year_face_exposure > 0:
                    implied_annual_qx = first_year_claims / first_year_face_exposure
                else:
                    implied_annual_qx = 0.001  # fallback
                loading = st.session_state.get("yrt_loading", 0.10)
                yrt_rate_per_1000 = implied_annual_qx * 1000.0 * (1.0 + loading)
                st.info(
                    f"Derived YRT rate: {yrt_rate_per_1000:.3f} per $1,000 NAR "
                    f"(implied q_x = {implied_annual_qx:.5f}, "
                    f"loading = {loading:.0%})"
                )

            if treaty_type == "None (Gross)":
                net = gross
            else:
                treaty = _build_treaty(
                    treaty_type, cession_pct, face_amount_total, modco_rate, yrt_rate_per_1000
                )
                inforce_arg = inforce if use_policy_cession else None
                net, _ceded = treaty.apply(gross, inforce=inforce_arg)  # type: ignore[union-attr]

            result = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate).run()

            # Sanity check: loss ratio (claims / premiums)
            total_claims = float(gross.death_claims.sum())
            total_premiums = float(gross.gross_premiums.sum())
            if total_premiums > 0:
                loss_ratio = total_claims / total_premiums
                if loss_ratio < 0.01:
                    st.error(
                        f"**Pricing Validation Warning**: Aggregate loss ratio "
                        f"is {loss_ratio:.4%} (claims ${total_claims:,.0f} vs "
                        f"premiums ${total_premiums:,.0f}). "
                        f"Expected 20-80% for a correctly parameterised deal. "
                        f"Check that mortality rates are correctly scaled "
                        f"(decimal q_x, not per-mille or per-100,000)."
                    )
                elif loss_ratio > 2.0:
                    st.warning(
                        f"**Pricing Validation Warning**: Loss ratio is "
                        f"{loss_ratio:.2%} — claims far exceed premiums. "
                        f"Check premium calibration and mortality assumptions."
                    )
                else:
                    st.caption(
                        f"Validation: aggregate loss ratio = {loss_ratio:.1%}, "
                        f"total claims = ${total_claims:,.0f}, "
                        f"total premiums = ${total_premiums:,.0f}"
                    )

            # Cache results in session state so they survive page navigation
            st.session_state["pricing_result"] = result
            st.session_state["pricing_net_result"] = net
            st.session_state["pricing_treaty_type"] = treaty_type

    # Display results from session state (persists across navigation)
    result = st.session_state.get("pricing_result")
    net = st.session_state.get("pricing_net_result")
    gross = st.session_state.get("gross_result")
    cached_treaty_type = st.session_state.get("pricing_treaty_type", treaty_type)

    if result is not None and net is not None and gross is not None:
        # Metrics
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("PV Profits", f"${result.pv_profits:,.0f}")
        col_b.metric("Profit Margin", f"{result.profit_margin:.2%}")
        col_c.metric("IRR", f"{result.irr:.2%}" if result.irr else "N/A")
        bey = str(result.breakeven_year) if result.breakeven_year else "Never"
        col_d.metric("Break-even Year", bey)

        # Charts — use net (post-treaty) basis to match the table and KPIs
        basis_label = (
            "Gross" if cached_treaty_type == "None (Gross)" else f"Net ({cached_treaty_type})"
        )
        st.pyplot(cashflow_waterfall(result.profit_by_year))
        st.pyplot(_cash_flow_decomposition(net, title_suffix=basis_label))
        st.pyplot(_reserve_chart(gross))

        # Tabular summary — show both gross and net to make treaty effect visible.
        # For YRT without an explicit rate, ceded premiums may be zero (cedant
        # keeps all premiums but pays YRT premium separately), making net premiums
        # appear identical to gross while claims are heavily reduced.
        n_years = net.projection_months // 12
        annual_data = []
        for yr in range(n_years):
            s, e = yr * 12, (yr + 1) * 12
            row: dict[str, str | int] = {"Year": yr + 1}
            if cached_treaty_type != "None (Gross)":
                row["Gross Premiums"] = f"${gross.gross_premiums[s:e].sum():,.0f}"
                row["Gross Claims"] = f"${gross.death_claims[s:e].sum():,.0f}"
            row["Premiums"] = f"${net.gross_premiums[s:e].sum():,.0f}"
            row["Claims"] = f"${net.death_claims[s:e].sum():,.0f}"
            row["Expenses"] = f"${net.expenses[s:e].sum():,.0f}"
            row["Reserve Inc."] = f"${net.reserve_increase[s:e].sum():,.0f}"
            row["Net Cash Flow"] = f"${net.net_cash_flow[s:e].sum():,.0f}"
            row["Cumul. NCF"] = f"${net.net_cash_flow[:e].sum():,.0f}"
            # Lapse exits (informational — not a cash flow for term life,
            # but confirms assumptions are being applied)
            if gross.lapse_count is not None:
                row["Lapse Exits"] = f"{gross.lapse_count[s:e].sum():,.1f}"
            annual_data.append(row)
        st.subheader(f"Annual Summary \u2014 {basis_label}")
        if cached_treaty_type == "YRT":
            st.caption(
                "YRT: cedant retains gross premiums and pays separate YRT premium to reinsurer. "
                "Claims are ceded proportionally. Gross columns shown for reference."
            )
        st.caption(
            "NCF = Premiums \u2212 Claims \u2212 Expenses \u2212 Reserve Increase. "
            "Term life has no cash surrender value; lapse impact is reflected in "
            "declining premiums/claims and reserve release. "
            "Lapse Exits column confirms assumptions are applied."
        )
        st.dataframe(annual_data, use_container_width=True)

        # Table vs ML comparison (Phase E)
        ml_mort = st.session_state.get("ml_mortality_model")
        if ml_mort is not None and use_session:
            _table_vs_ml_comparison(assumption_set, ml_mort)

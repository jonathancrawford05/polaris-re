"""Page 3: Deal Pricing — rebuilt to consume session state from Pages 1-2."""

import os
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import cashflow_waterfall

__all__ = ["page_pricing"]

# Default select-and-ultimate lapse structure (realistic industry pattern)
_DEFAULT_LAPSE_TABLE: dict[int | str, float] = {
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

# Map UI labels to MortalityTableSource enum values
_TABLE_SOURCE_MAP: dict[str, str] = {
    "SOA VBT 2015": "SOA_VBT_2015",
    "CIA 2014": "CIA_2014",
    "2001 CSO": "CSO_2001",
}


def _resolve_data_dir() -> Path:
    """Resolve mortality table data directory using the same convention as the Assumptions page."""
    return Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"


def _load_mortality_table(source_label: str) -> object | None:
    """Attempt to load a standard mortality table. Returns MortalityTable or None."""
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource

    source_key = _TABLE_SOURCE_MAP[source_label]
    table_source = MortalityTableSource(source_key)
    data_dir = _resolve_data_dir()

    try:
        return MortalityTable.load(source=table_source, data_dir=data_dir)
    except (FileNotFoundError, Exception) as exc:
        st.error(
            f"**Cannot load {source_label}**: {exc}\n\n"
            f"Ensure mortality table CSVs are in `{data_dir}` or set the "
            f"`POLARIS_DATA_DIR` environment variable. "
            f"See `data/mortality_tables/` in the repository."
        )
        return None


def _build_fallback_assumptions(
    mortality_table: object,
    lapse_ultimate_rate: float,
    valuation_date: date,
    source_label: str,
) -> object:
    """Build AssumptionSet for dashboard using a real mortality table basis."""
    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.assumptions.lapse import LapseAssumption

    # Build select-and-ultimate lapse structure, scaling the ultimate rate
    # while preserving the select-period shape
    base_ultimate = _DEFAULT_LAPSE_TABLE["ultimate"]
    scale = lapse_ultimate_rate / base_ultimate if base_ultimate > 0 else 1.0
    scaled_lapse: dict[int | str, float] = {}
    for k, v in _DEFAULT_LAPSE_TABLE.items():
        scaled_lapse[k] = min(v * scale, 1.0)  # cap at 100%

    lapse = LapseAssumption.from_duration_table(scaled_lapse)

    return AssumptionSet(
        mortality=mortality_table,  # type: ignore[arg-type]
        lapse=lapse,
        version=f"dashboard-fallback-{source_label.replace(' ', '_').lower()}",
        effective_date=valuation_date,
    )


def _build_fallback_block(
    n_policies: int,
    attained_age: int,
    face_amount: float,
    target_loss_ratio: float,
    term_years: int,
    valuation_date: date,
    mortality_table: object,
    sex: object,
    smoker_status: object,
) -> object:
    """Build InforceBlock for dashboard, with premium calibrated from table mortality."""
    from polaris_re.core.inforce import InforceBlock
    from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus

    sex_val: Sex = sex  # type: ignore[assignment]
    smoker_val: SmokerStatus = smoker_status  # type: ignore[assignment]

    # Look up annual q_x at the specified attained age from the real table
    q_monthly = mortality_table.get_qx_scalar(  # type: ignore[union-attr]
        attained_age, sex_val, smoker_val, duration_months=0
    )
    q_annual = 1.0 - (1.0 - q_monthly) ** 12

    # Calibrate premium: premium = face * q_x / loss_ratio
    annual_premium = (face_amount * q_annual) / target_loss_ratio

    policies = [
        Policy(
            policy_id=f"P{i:05d}",
            issue_age=attained_age,
            attained_age=attained_age,
            sex=sex_val,
            smoker_status=smoker_val,
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
            "or use the quick-start parameters below to run a pricing scenario "
            "on a standard mortality basis."
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

    # Quick-start block & assumptions when session state not populated
    fallback_ready = True  # will be set to False if table loading fails
    if not use_session:
        st.subheader("Quick-Start: Block & Assumptions")
        st.caption(
            "Define a homogeneous policy block with standard mortality basis. "
            "For heterogeneous blocks, configure Pages 1-2 instead."
        )

        # Mortality basis selection
        fb_mort_col, fb_demo_col, fb_block_col = st.columns(3)
        with fb_mort_col:
            mort_table_label = st.selectbox(
                "Mortality Table",
                list(_TABLE_SOURCE_MAP.keys()),
                index=0,
                help="Standard industry mortality basis for the projection.",
            )
            mortality_multiplier = st.slider(
                "Mortality Multiplier",
                min_value=0.50,
                max_value=2.00,
                value=1.00,
                step=0.05,
                help=(
                    "Scale factor applied to base table rates. "
                    "1.0 = 100% of table. Use <1.0 for preferred lives, "
                    ">1.0 for substandard."
                ),
            )

        with fb_demo_col:
            from polaris_re.core.policy import Sex, SmokerStatus

            sex_label = st.selectbox("Sex", ["Male", "Female"])
            sex = Sex.MALE if sex_label == "Male" else Sex.FEMALE
            smoker_label = st.selectbox("Smoker Status", ["Non-Smoker", "Smoker"])
            smoker_status = (
                SmokerStatus.NON_SMOKER if smoker_label == "Non-Smoker" else SmokerStatus.SMOKER
            )

        with fb_block_col:
            n_policies = int(
                st.number_input(
                    "Number of Policies", min_value=1, max_value=10000, value=100, step=10
                )
            )
            attained_age = int(st.slider("Attained Age", 25, 65, 40))

        fb_fin_col1, fb_fin_col2 = st.columns(2)
        with fb_fin_col1:
            face_amount = float(
                st.number_input(
                    "Face Amount ($)",
                    min_value=50_000,
                    max_value=5_000_000,
                    value=500_000,
                    step=50_000,
                )
            )
        with fb_fin_col2:
            target_loss_ratio = st.slider(
                "Target Loss Ratio",
                min_value=0.30,
                max_value=0.90,
                value=0.60,
                step=0.05,
                help="Ratio of expected claims to premiums. Lower = more profitable.",
            )

        # Lapse assumption
        lapse_ultimate = float(
            st.slider(
                "Ultimate Lapse Rate (%)",
                min_value=0.5,
                max_value=10.0,
                value=1.5,
                step=0.5,
                help=(
                    "Ultimate annual lapse rate (after year 10). "
                    "Early-duration rates are scaled proportionally from a "
                    "standard select-and-ultimate structure."
                ),
            )
        ) / 100.0

        # Eagerly load the mortality table to validate and show calibration info
        mortality_table = _load_mortality_table(mort_table_label)
        if mortality_table is None:
            fallback_ready = False
        else:
            # Show the implied premium from the table-based calibration
            q_monthly = mortality_table.get_qx_scalar(  # type: ignore[union-attr]
                attained_age, sex, smoker_status, duration_months=0
            )
            q_annual = 1.0 - (1.0 - q_monthly) ** 12
            q_annual_adj = min(q_annual * mortality_multiplier, 1.0)
            implied_premium = (face_amount * q_annual_adj) / target_loss_ratio
            st.info(
                f"**{mort_table_label}** \u2014 "
                f"q_x at age {attained_age} ({sex_label}, {smoker_label}): "
                f"{q_annual:.5f}"
                f"{f' \u00d7 {mortality_multiplier:.2f} = {q_annual_adj:.5f}' if mortality_multiplier != 1.0 else ''}"
                f" \u2192 implied annual premium: **${implied_premium:,.0f}** "
                f"(at {target_loss_ratio:.0%} loss ratio)"
            )

    if st.button("Run Pricing", type="primary"):
        if not use_session and not fallback_ready:
            st.error("Cannot run pricing — mortality table failed to load. See error above.")
            st.stop()

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
                # Apply mortality multiplier by scaling the table rates if != 1.0
                effective_table = mortality_table  # type: ignore[possibly-undefined]
                if mortality_multiplier != 1.0:  # type: ignore[possibly-undefined]
                    effective_table = _apply_mortality_multiplier(
                        mortality_table,  # type: ignore[possibly-undefined]
                        mortality_multiplier,  # type: ignore[possibly-undefined]
                    )

                assumptions = _build_fallback_assumptions(
                    effective_table,
                    lapse_ultimate,  # type: ignore[possibly-undefined]
                    valuation_date,
                    mort_table_label,  # type: ignore[possibly-undefined]
                )
                inforce = _build_fallback_block(
                    n_policies,  # type: ignore[possibly-undefined]
                    attained_age,  # type: ignore[possibly-undefined]
                    face_amount,  # type: ignore[possibly-undefined]
                    target_loss_ratio,  # type: ignore[possibly-undefined]
                    projection_years,
                    valuation_date,
                    effective_table,
                    sex,  # type: ignore[possibly-undefined]
                    smoker_status,  # type: ignore[possibly-undefined]
                )
                face_amount_total = face_amount  # type: ignore[possibly-undefined]

            product = TermLife(inforce=inforce, assumptions=assumptions, config=config)  # type: ignore[arg-type]
            gross = product.project()
            st.session_state["gross_result"] = gross

            # Derive mortality-based YRT rate if applicable
            if treaty_type == "YRT" and yrt_rate_per_1000 is None:
                total_claims = float(gross.death_claims.sum())
                first_year_claims = float(gross.death_claims[:12].sum())
                first_year_face_exposure = face_amount_total
                if first_year_face_exposure > 0:
                    implied_annual_qx = first_year_claims / first_year_face_exposure
                else:
                    implied_annual_qx = 0.001
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


def _apply_mortality_multiplier(mortality_table: object, multiplier: float) -> object:
    """Create a new MortalityTable with rates scaled by the multiplier.

    Constructs new MortalityTableArray objects with adjusted rates,
    preserving the original table structure and metadata.
    """
    from polaris_re.assumptions.mortality import MortalityTable
    from polaris_re.utils.table_io import MortalityTableArray

    orig: MortalityTable = mortality_table  # type: ignore[assignment]
    scaled_tables: dict[str, MortalityTableArray] = {}

    for key, table_arr in orig.tables.items():
        scaled_rates = np.minimum(table_arr.rates * multiplier, 1.0)
        scaled_tables[key] = MortalityTableArray(
            rates=scaled_rates,
            min_age=table_arr.min_age,
            max_age=table_arr.max_age,
            select_period=table_arr.select_period,
            source_file=table_arr.source_file,
        )

    return MortalityTable(
        source=orig.source,
        table_name=f"{orig.table_name} (\u00d7{multiplier:.2f})",
        min_age=orig.min_age,
        max_age=orig.max_age,
        select_period_years=orig.select_period_years,
        has_smoker_distinct_rates=orig.has_smoker_distinct_rates,
        tables=scaled_tables,
    )

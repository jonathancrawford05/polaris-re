"""Page 3: Deal Pricing — migrated from original app.py."""

from datetime import date

import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import cashflow_waterfall

__all__ = ["page_pricing"]


def _build_assumptions(
    flat_qx: float,
    flat_lapse: float,
    valuation_date: date,
) -> object:
    """Build minimal AssumptionSet for dashboard with flat rates."""
    from pathlib import Path

    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.policy import Sex, SmokerStatus
    from polaris_re.utils.table_io import MortalityTableArray

    n_ages = 121 - 18
    qx = np.full(n_ages, flat_qx, dtype=np.float64)
    rates_2d = qx.reshape(-1, 1)
    table_array = MortalityTableArray(
        rates=rates_2d,
        min_age=18,
        max_age=120,
        select_period=0,
        source_file=Path("synthetic"),
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.CSO_2001,
        table_name="Synthetic Dashboard",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.UNKNOWN,
    )
    lapse = LapseAssumption.from_duration_table(
        {1: flat_lapse, 2: flat_lapse, 3: flat_lapse, "ultimate": flat_lapse}
    )
    return AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        version="dashboard-v1",
        effective_date=valuation_date,
    )


def _build_policy_block(
    n_policies: int,
    attained_age: int,
    face_amount: float,
    annual_premium: float,
    term_years: int,
    valuation_date: date,
) -> object:
    """Build InforceBlock for dashboard."""
    from polaris_re.core.inforce import InforceBlock
    from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus

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


def page_pricing() -> None:
    """Deal pricing page."""
    st.header("Deal Pricing")

    col1, col2, col3 = st.columns(3)
    with col1:
        n_policies = int(
            st.number_input("Number of Policies", min_value=1, max_value=10000, value=100, step=10)
        )
        attained_age = int(st.slider("Attained Age", 25, 65, 40))
        face_amount = float(
            st.number_input(
                "Face Amount ($)", min_value=50_000, max_value=5_000_000, value=500_000, step=50_000
            )
        )
    with col2:
        annual_premium = float(
            st.number_input(
                "Annual Premium ($)", min_value=100, max_value=50_000, value=1_200, step=100
            )
        )
        term_years = int(st.slider("Term (years)", 5, 30, 20))
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0
    with col3:
        flat_qx = float(st.slider("Mortality Rate (q_x \u2030)", 0.1, 10.0, 1.0, step=0.1)) / 1000.0
        flat_lapse = float(st.slider("Lapse Rate (%)", 1, 20, 5)) / 100.0
        cession_pct = float(st.slider("Cession % (YRT)", 50, 100, 90)) / 100.0
        discount_rate = float(st.slider("Discount Rate (%)", 2, 12, 6)) / 100.0

    if st.button("Run Pricing", type="primary"):
        from polaris_re.analytics.profit_test import ProfitTester
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.products.term_life import TermLife
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner("Running projection..."):
            valuation_date = date.today()
            inforce = _build_policy_block(
                n_policies, attained_age, face_amount, annual_premium, term_years, valuation_date
            )
            assumptions = _build_assumptions(flat_qx, flat_lapse, valuation_date)
            config = ProjectionConfig(
                valuation_date=valuation_date,
                projection_horizon_years=term_years,
                discount_rate=discount_rate,
            )
            treaty = YRTTreaty(
                treaty_name="YRT-DASH",
                cession_pct=cession_pct,
                total_face_amount=face_amount,
            )
            product = TermLife(inforce=inforce, assumptions=assumptions, config=config)  # type: ignore[arg-type]
            gross = product.project()
            net, _ceded = treaty.apply(gross)
            result = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate).run()

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("PV Profits", f"${result.pv_profits:,.0f}")
        col_b.metric("Profit Margin", f"{result.profit_margin:.2%}")
        col_c.metric("IRR", f"{result.irr:.2%}" if result.irr else "N/A")
        bey = str(result.breakeven_year) if result.breakeven_year else "Never"
        col_d.metric("Break-even Year", bey)

        st.pyplot(cashflow_waterfall(result.profit_by_year))

"""Page 5: Scenario Analysis — migrated from original app.py."""

from datetime import date

import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import scenario_tornado
from polaris_re.dashboard.pages.pricing import _build_assumptions, _build_policy_block

__all__ = ["page_scenario"]


def page_scenario() -> None:
    """Scenario analysis page."""
    st.header("Scenario Analysis")

    col1, col2 = st.columns(2)
    with col1:
        n_policies = int(
            st.number_input("Number of Policies", min_value=1, max_value=1000, value=50, step=10)
        )
        attained_age = int(st.slider("Attained Age", 25, 65, 40))
        face_amount = float(st.number_input("Face Amount ($)", value=500_000, step=50_000))
    with col2:
        annual_premium = float(st.number_input("Annual Premium ($)", value=1_200, step=100))
        term_years = int(st.slider("Term (years)", 5, 30, 20))
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0

    if st.button("Run Scenarios", type="primary"):
        from polaris_re.analytics.scenario import ScenarioRunner
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner("Running scenario analysis..."):
            valuation_date = date.today()
            inforce = _build_policy_block(
                n_policies, attained_age, face_amount, annual_premium, term_years, valuation_date
            )
            assumptions = _build_assumptions(0.001, 0.05, valuation_date)
            config = ProjectionConfig(
                valuation_date=valuation_date,
                projection_horizon_years=term_years,
                discount_rate=0.06,
            )
            treaty = YRTTreaty(
                treaty_name="YRT-SCENARIO", cession_pct=0.90, total_face_amount=face_amount
            )
            runner = ScenarioRunner(
                inforce=inforce,
                base_assumptions=assumptions,
                config=config,
                treaty=treaty,
                hurdle_rate=hurdle_rate,
            )
            results = runner.run()

        results_dict = {name: res for name, res in results.scenarios}
        base_case = results.base_case()
        base_pv = base_case.pv_profits if base_case else results.scenarios[0][1].pv_profits
        st.pyplot(scenario_tornado(results_dict, base_pv))

        irr_str = {k: f"{v.irr:.2%}" if v.irr else "N/A" for k, v in results_dict.items()}
        rows = [
            {"Scenario": k, "PV Profit": f"${v.pv_profits:,.0f}", "IRR": irr_str[k]}
            for k, v in results_dict.items()
        ]
        st.table(rows)

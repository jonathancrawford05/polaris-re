"""Page 6: Monte Carlo Uncertainty Quantification — migrated from original app.py."""

from datetime import date

import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import uq_histogram
from polaris_re.dashboard.pages.pricing import _build_assumptions, _build_policy_block

__all__ = ["page_uq"]


def page_uq() -> None:
    """Monte Carlo UQ page."""
    st.header("Monte Carlo Uncertainty Quantification")

    col1, col2, col3 = st.columns(3)
    with col1:
        n_scenarios = int(st.slider("Monte Carlo Scenarios", 50, 1000, 200, step=50))
        seed = int(st.number_input("Random Seed", value=42, min_value=0))
    with col2:
        mort_sigma = float(st.slider("Mortality vol (%)", 5, 30, 10)) / 100.0
        lapse_sigma = float(st.slider("Lapse vol (%)", 5, 30, 15)) / 100.0
    with col3:
        rate_sigma = float(st.slider("Rate vol (bps)", 10, 200, 50)) / 10_000.0
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0

    if st.button("Run Monte Carlo", type="primary"):
        from polaris_re.analytics.uq import MonteCarloUQ, UQParameters
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner(f"Running {n_scenarios} scenarios..."):
            valuation_date = date.today()
            inforce = _build_policy_block(50, 40, 500_000, 1_200, 20, valuation_date)
            assumptions = _build_assumptions(0.001, 0.05, valuation_date)
            config = ProjectionConfig(
                valuation_date=valuation_date, projection_horizon_years=20, discount_rate=0.06
            )
            treaty = YRTTreaty(treaty_name="YRT-UQ", cession_pct=0.90, total_face_amount=500_000)
            uq = MonteCarloUQ(
                inforce=inforce,
                base_assumptions=assumptions,
                base_config=config,
                treaty=treaty,
                hurdle_rate=hurdle_rate,
                n_scenarios=n_scenarios,
                seed=seed,
                params=UQParameters(
                    mortality_log_sigma=mort_sigma,
                    lapse_log_sigma=lapse_sigma,
                    interest_rate_sigma=rate_sigma,
                ),
            )
            result = uq.run()

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("VaR 95%", f"${result.var(0.95):,.0f}")
        col_b.metric("CVaR 95%", f"${result.cvar(0.95):,.0f}")
        col_c.metric("Base PV Profit", f"${result.base_pv_profit:,.0f}")

        st.pyplot(
            uq_histogram(
                result.pv_profits, result.var(0.95), result.cvar(0.95), result.base_pv_profit
            )
        )

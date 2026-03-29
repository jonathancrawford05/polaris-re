"""Page 6: Monte Carlo Uncertainty Quantification — rebuilt on session state."""

from datetime import date

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import uq_histogram
from polaris_re.dashboard.views.pricing import (
    _build_fallback_assumptions,
    _build_fallback_block,
)

__all__ = ["page_uq"]


def page_uq() -> None:
    """Monte Carlo UQ page — uses session state or fallback."""
    st.header("Monte Carlo Uncertainty Quantification")

    inforce_block = st.session_state.get("inforce_block")
    assumption_set = st.session_state.get("assumption_set")

    if inforce_block is not None and assumption_set is not None:
        use_session = True
        st.success(
            f"Using session state: {inforce_block.n_policies} policies, "
            f"assumptions v{assumption_set.version}"
        )
    else:
        use_session = False
        st.warning("No session state configured. Using fallback assumptions.")

    col1, col2, col3 = st.columns(3)
    with col1:
        n_scenarios = int(st.slider("Monte Carlo Scenarios", 100, 2000, 500, step=100))
        seed = int(st.number_input("Random Seed", value=42, min_value=0))
    with col2:
        mort_sigma = float(st.slider("Mortality vol (%)", 5, 30, 10)) / 100.0
        lapse_sigma = float(st.slider("Lapse vol (%)", 5, 30, 15)) / 100.0
    with col3:
        rate_sigma = float(st.slider("Rate vol (bps)", 10, 200, 50)) / 10_000.0
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0

    projection_years = int(st.slider("Projection Horizon (years)", 5, 30, 20))
    discount_rate = float(st.slider("Discount Rate (%)", 2, 12, 6)) / 100.0
    cession_pct = float(st.slider("Cession %", 50, 100, 90)) / 100.0

    if st.button("Run Monte Carlo", type="primary"):
        from polaris_re.analytics.uq import MonteCarloUQ, UQParameters
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner(f"Running {n_scenarios} scenarios..."):
            valuation_date = date.today()

            if use_session:
                inforce = inforce_block
                assumptions = assumption_set
                face_total = float(inforce.total_face_amount())
            else:
                inforce = _build_fallback_block(50, 40, 500_000, 1_200, 20, valuation_date)
                assumptions = _build_fallback_assumptions(0.001, 0.05, valuation_date)
                face_total = 500_000.0

            config = ProjectionConfig(
                valuation_date=valuation_date,
                projection_horizon_years=projection_years,
                discount_rate=discount_rate,
            )
            treaty = YRTTreaty(
                treaty_name="YRT-UQ",
                cession_pct=cession_pct,
                total_face_amount=face_total,
            )
            uq = MonteCarloUQ(
                inforce=inforce,  # type: ignore[arg-type]
                base_assumptions=assumptions,  # type: ignore[arg-type]
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

        # Metrics — VaR 95% is the 5th percentile of PV profits (same as P5),
        # so we show Prob(Loss) instead of the redundant P5 metric.
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric(
            "VaR 95%",
            f"${result.var(0.95):,.0f}",
            help="5th percentile of PV Profit distribution (worst-case at 95% confidence).",
        )
        col_b.metric("CVaR 95%", f"${result.cvar(0.95):,.0f}")
        col_c.metric("Base PV Profit", f"${result.base_pv_profit:,.0f}")
        prob_loss = float((result.pv_profits < 0).mean()) * 100.0
        col_d.metric("Prob(Loss)", f"{prob_loss:.1f}%")

        # Main histogram
        st.pyplot(
            uq_histogram(
                result.pv_profits,
                result.var(0.95),
                result.cvar(0.95),
                result.base_pv_profit,
            )
        )

        # Percentile distribution overlay
        st.subheader("Distribution Summary")
        percentiles = [5, 25, 50, 75, 95]
        pct_rows = []
        for p in percentiles:
            pct_data = result.percentile(p)
            pct_rows.append(
                {
                    "Percentile": f"P{p}",
                    "PV Profit": f"${pct_data['pv_profit']:,.0f}",
                    "IRR": f"{pct_data['irr']:.2%}" if not np.isnan(pct_data["irr"]) else "N/A",
                    "Margin": f"{pct_data['profit_margin']:.2%}",
                }
            )
        st.dataframe(pct_rows, use_container_width=True)

        # Convergence diagnostic: running mean
        st.subheader("Convergence Diagnostic")
        running_mean = np.cumsum(result.pv_profits) / np.arange(1, n_scenarios + 1)
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(np.arange(1, n_scenarios + 1), running_mean, color="#3498db", linewidth=1.5)
        ax.axhline(
            result.base_pv_profit,
            color="#2ecc71",
            linestyle="--",
            label=f"Base: ${result.base_pv_profit:,.0f}",
        )
        ax.set_xlabel("Scenario Count")
        ax.set_ylabel("Running Mean PV Profit ($)")
        ax.set_title("Monte Carlo Convergence")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

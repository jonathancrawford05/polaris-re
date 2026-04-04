"""Page 6: Monte Carlo Uncertainty Quantification — uses session state.

Requires Inforce Block and Assumptions to be configured. No fallback.
Uses the shared projection helpers for consistent YRT rate derivation.
"""

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import uq_histogram
from polaris_re.dashboard.components.projection import (
    build_projection_config,
    derive_yrt_rate,
    run_gross_projection,
)
from polaris_re.dashboard.components.state import get_deal_config

__all__ = ["page_uq"]


def page_uq() -> None:
    """Monte Carlo UQ page \u2014 uses session state assumptions."""
    st.header("Monte Carlo Uncertainty Quantification")

    inforce_block = st.session_state.get("inforce_block")
    assumption_set = st.session_state.get("assumption_set")

    if inforce_block is None or assumption_set is None:
        st.warning(
            "Configure **Inforce Block** (Page 1) and **Assumptions** (Page 2) first. "
            "All projection parameters are set on the Assumptions page."
        )
        return

    st.success(
        f"Using session state: {inforce_block.n_policies:,} policies, "
        f"assumptions v{assumption_set.version}"
    )

    cfg = get_deal_config()

    col1, col2, col3 = st.columns(3)
    with col1:
        n_scenarios = int(st.slider("Monte Carlo Scenarios", 100, 2000, 500, step=100))
        seed = int(st.number_input("Random Seed", value=42, min_value=0))
    with col2:
        mort_sigma = float(st.slider("Mortality vol (%)", 5, 30, 10)) / 100.0
        lapse_sigma = float(st.slider("Lapse vol (%)", 5, 30, 15)) / 100.0
    with col3:
        rate_sigma = float(st.slider("Rate vol (bps)", 10, 200, 50)) / 10_000.0
        cession_pct = (
            float(
                st.slider(
                    "Cession %",
                    50,
                    100,
                    int(float(cfg.get("cession_pct", 0.90)) * 100),
                    key="uq_cession",
                )
            )
            / 100.0
        )

    hurdle_rate = float(cfg.get("hurdle_rate", 0.10))

    st.caption(
        "Projection horizon, discount rate, expenses, and hurdle rate are inherited "
        "from the Assumptions page. Cession % can be adjusted above."
    )

    if st.button("Run Monte Carlo", type="primary"):
        from polaris_re.analytics.uq import MonteCarloUQ, UQParameters
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner(f"Running {n_scenarios} scenarios..."):
            config = build_projection_config()
            face_total = float(inforce_block.total_face_amount())

            # Derive YRT rate consistently with Deal Pricing
            yrt_loading = float(cfg.get("yrt_loading", 0.10))
            _base_gross = run_gross_projection(inforce_block, assumption_set, config)
            yrt_rate = derive_yrt_rate(_base_gross, face_total, yrt_loading)
            st.info(
                f"Derived YRT rate: {yrt_rate:.3f} per $1,000 NAR (loading = {yrt_loading:.0%})"
            )

            treaty = YRTTreaty(
                treaty_name="YRT-UQ",
                cession_pct=cession_pct,
                total_face_amount=face_total,
                flat_yrt_rate_per_1000=yrt_rate,
            )
            uq = MonteCarloUQ(
                inforce=inforce_block,
                base_assumptions=assumption_set,
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

        # Metrics
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

        if prob_loss == 0.0:
            st.caption(
                "Prob(Loss) = 0% across all scenarios. This typically indicates "
                "the YRT pricing margin is large enough that even adverse scenarios "
                "remain profitable. Consider testing with lower YRT loading or "
                "higher volatility parameters to explore tail risk."
            )

        # Main histogram
        st.pyplot(
            uq_histogram(
                result.pv_profits,
                result.var(0.95),
                result.cvar(0.95),
                result.base_pv_profit,
            )
        )

        # Percentile distribution table
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

        # Check if all IRRs are N/A
        valid_irrs = result.irrs[~np.isnan(result.irrs)]
        if len(valid_irrs) == 0:
            st.caption(
                "All IRRs are N/A across the distribution because no scenario "
                "produces a sign change in net cash flows. This is typical for "
                "YRT structures with no capital deployment."
            )

        # Spread analysis
        p5 = float(np.percentile(result.pv_profits, 5))
        p95 = float(np.percentile(result.pv_profits, 95))
        spread_pct = (
            (p95 - p5) / abs(result.base_pv_profit) * 100 if result.base_pv_profit != 0 else 0
        )
        st.caption(
            f"P5\u2013P95 spread: ${p5:,.0f} to ${p95:,.0f} "
            f"({spread_pct:.1f}% of base). "
            f"Mortality vol = {mort_sigma:.0%}, Lapse vol = {lapse_sigma:.0%}."
        )

        # Convergence diagnostic
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

"""Page 4: Treaty Comparison — side-by-side YRT vs Coinsurance vs Modco.

Uses the shared projection helpers to ensure consistent YRT rate derivation
and expense loading across all treaty structures.
"""

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.projection import (
    build_projection_config,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    run_gross_projection,
)
from polaris_re.dashboard.components.state import get_deal_config

__all__ = ["page_treaty_compare"]


def page_treaty_compare() -> None:
    """Treaty comparison page \u2014 compare metrics across treaty structures."""
    st.header("Treaty Comparison")

    inforce_block = st.session_state.get("inforce_block")
    assumption_set = st.session_state.get("assumption_set")

    if inforce_block is None or assumption_set is None:
        st.warning(
            "Configure **Inforce Block** (Page 1) and **Assumptions** (Page 2) first. "
            "All projection parameters (expenses, discount rate, etc.) are set on "
            "the Assumptions page."
        )
        return

    cfg = get_deal_config()

    # Treaty selection
    treaties_to_compare = st.multiselect(
        "Treaties to Compare",
        ["Gross (No Treaty)", "YRT", "Coinsurance", "Modco"],
        default=["YRT", "Coinsurance"],
    )

    # Allow cession and hurdle override for comparison purposes
    col1, col2, col3 = st.columns(3)
    with col1:
        cession_pct = (
            float(
                st.slider(
                    "Cession %",
                    50,
                    100,
                    int(float(cfg.get("cession_pct", 0.90)) * 100),
                    key="tc_cession",
                )
            )
            / 100.0
        )
    with col2:
        modco_rate = (
            float(st.slider("Modco Interest Rate (%)", 1.0, 8.0, 4.5, step=0.5, key="tc_modco"))
            / 100.0
        )
    with col3:
        hurdle_rate = (
            float(
                st.slider(
                    "Hurdle Rate (%)",
                    5,
                    20,
                    int(float(cfg.get("hurdle_rate", 0.10)) * 100),
                    key="tc_hurdle",
                )
            )
            / 100.0
        )

    st.caption(
        "Projection horizon, discount rate, and expense loading are inherited "
        "from the Assumptions page. Cession % and hurdle rate can be adjusted "
        "above for comparative purposes."
    )

    if st.button("Run Comparison", type="primary"):
        from polaris_re.analytics.profit_test import ProfitTester

        with st.spinner("Running treaty comparison..."):
            config = build_projection_config()

            # Run gross projection (consistent with Deal Pricing)
            gross = run_gross_projection(inforce_block, assumption_set, config)
            st.session_state["gross_result"] = gross

            face_amount = float(inforce_block.total_face_amount())

            # Derive YRT rate from the gross projection (critical fix!)
            yrt_loading = float(cfg.get("yrt_loading", 0.10))
            rate_basis = str(cfg.get("yrt_rate_basis", "Mortality-based"))
            yrt_rate = cfg.get("yrt_rate_per_1000")  # type: ignore[assignment]
            if rate_basis == "Mortality-based" or yrt_rate is None:
                yrt_rate = derive_yrt_rate(gross, face_amount, yrt_loading)
            st.info(
                f"YRT rate: {yrt_rate:.3f} per $1,000 NAR "  # type: ignore[union-attr]
                f"(loading = {yrt_loading:.0%})"
            )

            results: dict[str, object] = {}
            ncf_curves: dict[str, np.ndarray] = {}
            reserve_peaks: dict[str, float] = {}
            reserve_curves: dict[str, np.ndarray] = {}
            reinsurer_results: dict[str, object] = {}
            ceded_ncf_curves: dict[str, np.ndarray] = {}

            for treaty_name in treaties_to_compare:
                if treaty_name == "Gross (No Treaty)":
                    net = gross
                    ceded = None
                else:
                    # Build treaty with proper YRT rate
                    effective_yrt = yrt_rate if treaty_name == "YRT" else None
                    treaty = build_treaty(
                        treaty_name,
                        cession_pct,
                        face_amount,
                        modco_rate,
                        effective_yrt,  # type: ignore[arg-type]
                    )
                    if treaty is None:
                        continue
                    net, ceded = treaty.apply(gross)  # type: ignore[union-attr]
                    reserve_peaks[treaty_name] = float(ceded.reserve_balance.max())
                    reserve_curves[treaty_name] = ceded.reserve_balance

                    # Reinsurer profit test (on ceded cash flows)
                    reinsurer_profit = ProfitTester(
                        cashflows=ceded_to_reinsurer_view(ceded),
                        hurdle_rate=hurdle_rate,
                    ).run()
                    reinsurer_results[treaty_name] = reinsurer_profit
                    ceded_ncf_curves[treaty_name] = ceded.net_cash_flow

                # Cedant profit test (on net cash flows)
                profit_result = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate).run()
                results[treaty_name] = profit_result
                ncf_curves[treaty_name] = net.net_cash_flow

        # ========== CEDANT COMPARISON ==========
        st.subheader("Cedant Metrics Comparison")
        comparison_rows = []
        for name, res in results.items():
            comparison_rows.append(
                {
                    "Treaty": name,
                    "PV Profit (Cedant)": f"${res.pv_profits:,.0f}",  # type: ignore[union-attr]
                    "Profit Margin": f"{res.profit_margin:.2%}",  # type: ignore[union-attr]
                    "IRR": f"{res.irr:.2%}" if res.irr else "N/A",  # type: ignore[union-attr]
                    "Break-even": str(res.breakeven_year) if res.breakeven_year else "N/A",  # type: ignore[union-attr]
                }
            )
        st.dataframe(comparison_rows, use_container_width=True)

        # ========== REINSURER COMPARISON ==========
        if reinsurer_results:
            st.subheader("Reinsurer Metrics Comparison")
            reinsurer_rows = []
            for name, res in reinsurer_results.items():
                reinsurer_rows.append(
                    {
                        "Treaty": name,
                        "PV Profit (Reinsurer)": f"${res.pv_profits:,.0f}",  # type: ignore[union-attr]
                        "Reinsurer Margin": f"{res.profit_margin:.2%}",  # type: ignore[union-attr]
                        "IRR": f"{res.irr:.2%}" if res.irr else "N/A",  # type: ignore[union-attr]
                        "Break-even": str(res.breakeven_year) if res.breakeven_year else "N/A",  # type: ignore[union-attr]
                    }
                )
            st.dataframe(reinsurer_rows, use_container_width=True)

            # IRR explanation for treaties where all IRRs are N/A
            all_irrs_na = all(
                res.irr is None
                for res in reinsurer_results.values()  # type: ignore[union-attr]
            )
            if all_irrs_na:
                st.caption(
                    "All IRRs are N/A because no treaty structure produces a negative "
                    "initial cash flow (no sign change in the NCF series). For YRT, "
                    "the reinsurer has no capital deployment. For coinsurance, IRR "
                    "becomes meaningful when reserve funding creates early-year strain."
                )

        # Cedant NCF overlay chart
        st.subheader("Cedant Net Cash Flow Comparison")
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = ["#2ecc71", "#3498db", "#e74c3c", "#9b59b6"]
        for i, (name, ncf) in enumerate(ncf_curves.items()):
            n_years = len(ncf) // 12
            annual = np.array([ncf[y * 12 : (y + 1) * 12].sum() for y in range(n_years)])
            ax.plot(
                np.arange(1, n_years + 1),
                annual,
                label=name,
                color=colors[i % len(colors)],
                linewidth=2,
            )
        ax.axhline(0, color="black", linewidth=0.5, linestyle=":")
        ax.set_xlabel("Policy Year")
        ax.set_ylabel("Annual NCF ($)")
        ax.set_title("Annual Net Cash Flow by Treaty (Cedant View)")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        # Reinsurer NCF overlay chart
        if ceded_ncf_curves:
            st.subheader("Reinsurer Net Cash Flow Comparison")
            fig2, ax2 = plt.subplots(figsize=(10, 5))
            for i, (name, ncf) in enumerate(ceded_ncf_curves.items()):
                n_years = len(ncf) // 12
                annual = np.array([ncf[y * 12 : (y + 1) * 12].sum() for y in range(n_years)])
                ax2.plot(
                    np.arange(1, n_years + 1),
                    annual,
                    label=name,
                    color=colors[(i + 1) % len(colors)],
                    linewidth=2,
                )
            ax2.axhline(0, color="black", linewidth=0.5, linestyle=":")
            ax2.set_xlabel("Policy Year")
            ax2.set_ylabel("Annual NCF ($)")
            ax2.set_title("Annual Net Cash Flow by Treaty (Reinsurer View)")
            ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            fig2.tight_layout()
            st.pyplot(fig2)
            plt.close(fig2)

        # Reserve balance comparison
        if reserve_curves:
            st.subheader("Ceded Reserve Balance Over Time")
            colors_res = ["#3498db", "#e74c3c", "#9b59b6"]
            fig3, ax3 = plt.subplots(figsize=(10, 5))
            for i, (name, curve) in enumerate(reserve_curves.items()):
                n_months = len(curve)
                peak = reserve_peaks[name]
                ax3.plot(
                    np.arange(n_months) / 12,
                    curve,
                    label=f"{name} (peak ${peak:,.0f})",
                    color=colors_res[i % len(colors_res)],
                    linewidth=2,
                )
            ax3.set_xlabel("Year")
            ax3.set_ylabel("Ceded Reserve Balance ($)")
            ax3.set_title("Ceded Reserve Balance by Treaty Type")
            ax3.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
            ax3.legend()
            ax3.grid(True, alpha=0.3)
            fig3.tight_layout()
            st.pyplot(fig3)
            plt.close(fig3)

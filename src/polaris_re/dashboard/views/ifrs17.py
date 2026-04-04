"""Page 7: IFRS 17 Insurance Contract Measurement.

Provides BBA and PAA measurement with proper Risk Adjustment calculation,
annual ISR table, and clear metric definitions.
"""

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

__all__ = ["page_ifrs17"]


def page_ifrs17() -> None:
    """IFRS 17 measurement page \u2014 BBA or PAA from gross projection."""
    st.header("IFRS 17 Measurement")

    gross_result = st.session_state.get("gross_result")
    if gross_result is None:
        st.warning(
            "No gross projection available. Run **Deal Pricing** (Page 3) first "
            "to generate a gross cash flow projection."
        )
        return

    st.success(f"Using cached gross projection: {gross_result.projection_months} months")

    # Configuration
    col1, col2, col3 = st.columns(3)
    with col1:
        approach = st.selectbox("Measurement Approach", ["BBA", "PAA"])
    with col2:
        ifrs_discount_rate = (
            float(st.slider("Risk-Free Discount Rate (%)", 1.0, 8.0, 3.5, step=0.5)) / 100.0
        )
    with col3:
        ra_factor = float(st.slider("Risk Adjustment Factor (%)", 1.0, 10.0, 5.0, step=0.5)) / 100.0

    st.caption(
        f"**Risk Adjustment**: {ra_factor:.1%} of |BEL| at each period. "
        f"The RA compensates for non-financial risk uncertainty and is "
        f"always a positive liability (IFRS 17.37(b))."
    )

    if st.button("Run IFRS 17 Measurement", type="primary"):
        from polaris_re.analytics.ifrs17 import IFRS17Measurement

        with st.spinner("Computing IFRS 17 measurement..."):
            measurement = IFRS17Measurement(
                cashflows=gross_result,
                discount_rate=ifrs_discount_rate,
                ra_factor=ra_factor,
            )

            result = measurement.measure_bba() if approach == "BBA" else measurement.measure_paa()

        # Initial recognition metrics
        st.subheader("Initial Recognition")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Best Estimate Liability", f"${result.initial_bel:,.0f}")
        m2.metric("Risk Adjustment", f"${result.initial_ra:,.0f}")
        m3.metric("CSM", f"${result.initial_csm:,.0f}")
        total_liab = result.total_initial_liability()
        m4.metric("Total Liability", f"${total_liab:,.0f}")

        # Explain BEL sign
        if result.initial_bel < 0:
            st.info(
                f"BEL is negative (${result.initial_bel:,.0f}) because the contract group "
                f"is profitable: PV of expected premium inflows exceeds PV of expected "
                f"outflows (claims + expenses). The CSM captures this unearned profit."
            )

        if result.loss_component > 0:
            st.error(
                f"Onerous contract: Loss Component = ${result.loss_component:,.0f} "
                "(recognised in P&L at inception)"
            )
            st.info(
                "Under IFRS 17 B123, insurance revenue for onerous contracts "
                "excludes the portion of expected cash flows attributable to the "
                "loss component. The ISR chart below reflects this adjustment."
            )

        # Reconciliation note
        deal_pv = st.session_state.get("pricing_result")
        if deal_pv is not None:
            st.caption(
                f"**Reconciliation note**: The CSM (${result.initial_csm:,.0f}) represents "
                f"unearned profit at inception discounted at the IFRS 17 risk-free rate "
                f"({ifrs_discount_rate:.1%}), whereas Deal Pricing PV Profit "
                f"(${deal_pv.pv_profits:,.0f}) uses the hurdle rate "
                f"({deal_pv.hurdle_rate:.1%}). The difference in discount rates and the "
                f"inclusion of the Risk Adjustment (${result.initial_ra:,.0f}) in the "
                f"IFRS 17 liability explains the gap between CSM and PV Profit."
            )

        # CSM amortisation schedule (BBA only)
        if approach == "BBA":
            st.subheader("CSM Amortisation")
            months = np.arange(result.n_periods)

            fig, ax = plt.subplots(figsize=(10, 5))
            ax.fill_between(
                months / 12, result.csm, alpha=0.3, color="#2ecc71", label="CSM Balance"
            )
            ax.plot(months / 12, result.csm, color="#2ecc71", linewidth=1.5)
            ax.plot(
                months / 12,
                np.cumsum(result.csm_release),
                color="#e74c3c",
                linewidth=1.5,
                linestyle="--",
                label="Cumulative CSM Released",
            )
            ax.set_xlabel("Year")
            ax.set_ylabel("Amount ($)")
            ax.set_title("CSM Amortisation Schedule")
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
            ax.legend()
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

        # Insurance liability over time
        st.subheader("Insurance Liability Components")
        months = np.arange(result.n_periods)
        fig2, ax2 = plt.subplots(figsize=(10, 5))

        if approach == "BBA":
            ax2.stackplot(
                months / 12,
                np.maximum(result.bel, 0),
                result.risk_adjustment,
                result.csm,
                labels=["BEL (positive part)", "Risk Adjustment", "CSM"],
                colors=["#3498db", "#e74c3c", "#2ecc71"],
                alpha=0.6,
            )
            # Show negative BEL as a separate line for visibility
            if (result.bel < 0).any():
                ax2.plot(
                    months / 12,
                    result.bel,
                    color="#3498db",
                    linewidth=1.5,
                    linestyle="--",
                    label="BEL (incl. negative)",
                )
        else:
            if result.lrc is not None and result.lic is not None:
                ax2.stackplot(
                    months / 12,
                    result.lrc,
                    result.lic,
                    labels=["LRC", "LIC"],
                    colors=["#3498db", "#e74c3c"],
                    alpha=0.6,
                )

        ax2.plot(
            months / 12,
            result.insurance_liability,
            color="black",
            linewidth=2,
            label="Total Liability",
        )
        ax2.set_xlabel("Year")
        ax2.set_ylabel("Liability ($)")
        ax2.set_title(f"Insurance Liability \u2014 {approach}")
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        fig2.tight_layout()
        st.pyplot(fig2)
        plt.close(fig2)

        # P&L: Insurance service result
        st.subheader("Profit & Loss \u2014 Insurance Service Result")
        n_years = result.n_periods // 12
        annual_revenue = np.array(
            [result.insurance_revenue[y * 12 : (y + 1) * 12].sum() for y in range(n_years)]
        )
        annual_expenses = np.array(
            [result.insurance_service_expenses[y * 12 : (y + 1) * 12].sum() for y in range(n_years)]
        )
        annual_result = np.array(
            [result.insurance_service_result[y * 12 : (y + 1) * 12].sum() for y in range(n_years)]
        )
        years = np.arange(1, n_years + 1)

        fig3, ax3 = plt.subplots(figsize=(10, 5))
        ax3.bar(years - 0.2, annual_revenue, 0.35, label="Revenue", color="#2ecc71", alpha=0.8)
        ax3.bar(years + 0.2, annual_expenses, 0.35, label="Expenses", color="#e74c3c", alpha=0.8)
        ax3.plot(years, annual_result, color="#3498db", linewidth=2, marker="o", label="Net Result")
        ax3.axhline(0, color="black", linewidth=0.5, linestyle=":")
        ax3.set_xlabel("Policy Year")
        ax3.set_ylabel("Amount ($)")
        ax3.set_title(f"Insurance Service Result \u2014 {approach}")
        ax3.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        fig3.tight_layout()
        st.pyplot(fig3)
        plt.close(fig3)

        # Annual ISR table (Finding 7.3 — make verifiable)
        st.subheader("Annual Insurance Service Result Table")
        isr_rows = []
        for yr in range(n_years):
            isr_rows.append(
                {
                    "Year": yr + 1,
                    "Revenue": f"${annual_revenue[yr]:,.0f}",
                    "Expenses": f"${annual_expenses[yr]:,.0f}",
                    "Net ISR": f"${annual_result[yr]:,.0f}",
                    "CSM Release": f"${result.csm_release[yr * 12 : (yr + 1) * 12].sum():,.0f}",
                    "RA (start)": f"${result.risk_adjustment[yr * 12]:,.0f}",
                }
            )
        st.dataframe(isr_rows, use_container_width=True)

        # Check for negative ISR in final years
        if (annual_result < 0).any():
            neg_years = years[annual_result < 0]
            st.warning(
                f"Negative ISR in year(s) {list(neg_years)}. Under IFRS 17 BBA for "
                f"a profitable group (positive CSM), the ISR should generally be "
                f"non-negative. This may indicate CSM exhaustion before final "
                f"contracts run off, or experience variances not absorbed by CSM."
            )

        # PV summary
        st.metric("PV Insurance Revenue", f"${result.pv_insurance_revenue():,.0f}")
        st.caption(
            "IFRS 17 Insurance Revenue \u2260 cash premiums. Under the BBA it equals "
            "the release of expected claims, expenses, RA, and CSM to P&L over the "
            "coverage period (IFRS 17.B121). For onerous contracts, revenue is "
            "reduced by the loss component allocation (IFRS 17.B123)."
        )

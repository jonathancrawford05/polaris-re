"""Page 4: Treaty Comparison — side-by-side YRT vs Coinsurance vs Modco."""

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np
import streamlit as st  # type: ignore[import-untyped]

__all__ = ["page_treaty_compare"]


def page_treaty_compare() -> None:
    """Treaty comparison page — compare metrics across treaty structures."""
    st.header("Treaty Comparison")

    inforce_block = st.session_state.get("inforce_block")
    assumption_set = st.session_state.get("assumption_set")
    gross_result = st.session_state.get("gross_result")

    if inforce_block is None or assumption_set is None:
        st.warning(
            "Configure **Inforce Block** (Page 1) and **Assumptions** (Page 2) first. "
            "Then run **Deal Pricing** (Page 3) to generate a gross projection."
        )
        return

    # Treaty selection
    treaties_to_compare = st.multiselect(
        "Treaties to Compare",
        ["Gross (No Treaty)", "YRT", "Coinsurance", "Modco"],
        default=["YRT", "Coinsurance"],
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        cession_pct = float(st.slider("Cession %", 50, 100, 90)) / 100.0
    with col2:
        modco_rate = float(st.slider("Modco Interest Rate (%)", 1.0, 8.0, 4.5, step=0.5)) / 100.0
    with col3:
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0

    projection_years = int(st.slider("Projection Horizon (years)", 5, 30, 20))
    discount_rate = float(st.slider("Discount Rate (%)", 2, 12, 6)) / 100.0

    if st.button("Run Comparison", type="primary"):
        from datetime import date

        from polaris_re.analytics.profit_test import ProfitTester
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.products.term_life import TermLife
        from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
        from polaris_re.reinsurance.modco import ModcoTreaty
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner("Running treaty comparison..."):
            valuation_date = date.today()
            config = ProjectionConfig(
                valuation_date=valuation_date,
                projection_horizon_years=projection_years,
                discount_rate=discount_rate,
            )

            # Run gross projection if not cached
            if gross_result is None:
                product = TermLife(
                    inforce=inforce_block,
                    assumptions=assumption_set,
                    config=config,
                )  # type: ignore[arg-type]
                gross = product.project()
                st.session_state["gross_result"] = gross
            else:
                gross = gross_result

            face_amount = float(inforce_block.total_face_amount())

            results: dict[str, object] = {}
            ncf_curves: dict[str, np.ndarray] = {}
            reserve_totals: dict[str, float] = {}

            for treaty_name in treaties_to_compare:
                if treaty_name == "Gross (No Treaty)":
                    net = gross
                elif treaty_name == "YRT":
                    treaty = YRTTreaty(
                        treaty_name="YRT-CMP",
                        cession_pct=cession_pct,
                        total_face_amount=face_amount,
                    )
                    net, ceded = treaty.apply(gross)
                    reserve_totals[treaty_name] = float(ceded.reserve_balance.sum())
                elif treaty_name == "Coinsurance":
                    treaty = CoinsuranceTreaty(  # type: ignore[assignment]
                        treaty_name="COINS-CMP",
                        cession_pct=cession_pct,
                        include_expense_allowance=True,
                    )
                    net, ceded = treaty.apply(gross)  # type: ignore[union-attr]
                    reserve_totals[treaty_name] = float(ceded.reserve_balance.sum())
                elif treaty_name == "Modco":
                    treaty = ModcoTreaty(  # type: ignore[assignment]
                        treaty_name="MODCO-CMP",
                        cession_pct=cession_pct,
                        modco_interest_rate=modco_rate,
                    )
                    net, ceded = treaty.apply(gross)  # type: ignore[union-attr]
                    reserve_totals[treaty_name] = float(ceded.reserve_balance.sum())
                else:
                    continue

                profit_result = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate).run()
                results[treaty_name] = profit_result
                ncf_curves[treaty_name] = net.net_cash_flow

        # Comparison table
        st.subheader("Metrics Comparison")
        comparison_rows = []
        for name, res in results.items():
            comparison_rows.append(
                {
                    "Treaty": name,
                    "PV Profit": f"${res.pv_profits:,.0f}",  # type: ignore[union-attr]
                    "Profit Margin": f"{res.profit_margin:.2%}",  # type: ignore[union-attr]
                    "IRR": f"{res.irr:.2%}" if res.irr else "N/A",  # type: ignore[union-attr]
                    "Break-even": str(res.breakeven_year) if res.breakeven_year else "Never",  # type: ignore[union-attr]
                }
            )
        st.dataframe(comparison_rows, use_container_width=True)

        # NCF overlay chart
        st.subheader("Net Cash Flow Comparison")
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
        ax.set_title("Annual Net Cash Flow by Treaty")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        # Reserve transfer comparison
        if reserve_totals:
            st.subheader("Ceded Reserve Transfer (Cumulative)")
            fig2, ax2 = plt.subplots(figsize=(8, 4))
            names = list(reserve_totals.keys())
            vals = [reserve_totals[n] for n in names]
            ax2.bar(names, vals, color=["#3498db", "#e74c3c", "#9b59b6"][: len(names)])
            ax2.set_ylabel("Total Ceded Reserve ($)")
            ax2.set_title("Ceded Reserve by Treaty Type")
            ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
            fig2.tight_layout()
            st.pyplot(fig2)
            plt.close(fig2)

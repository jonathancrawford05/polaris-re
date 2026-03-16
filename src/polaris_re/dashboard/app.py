"""
Polaris RE Interactive Dashboard (Streamlit).

Provides interactive visualisation for:
1. Deal Pricing — PV profit, IRR, break-even vs assumption inputs
2. Treaty Comparison — YRT vs Coinsurance vs Modco side-by-side
3. Scenario Analysis — sensitivity tornado chart
4. Monte Carlo UQ — histogram of PV profits with VaR/CVaR markers
5. Cash Flow Waterfall — annual cash flow by component

Run with:
    streamlit run src/polaris_re/dashboard/app.py

Dependencies: streamlit>=1.35, matplotlib>=3.9
Install: pip install streamlit  (not in core deps — optional extra)
"""

from __future__ import annotations

import sys
from datetime import date

import numpy as np

# Streamlit is an optional dependency — check at runtime
try:
    import streamlit as st  # type: ignore[import-untyped]

    _STREAMLIT_AVAILABLE = True
except ImportError:
    _STREAMLIT_AVAILABLE = False

try:
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]
    import matplotlib.ticker as mticker  # type: ignore[import-untyped]

    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False


def _check_deps() -> None:
    if not _STREAMLIT_AVAILABLE:
        print(
            "Streamlit is required for the dashboard. Install with:\n"
            "    pip install streamlit\n"
            "or:\n"
            "    uv pip install streamlit",
            file=sys.stderr,
        )
        sys.exit(1)
    if not _MATPLOTLIB_AVAILABLE:
        print("matplotlib is required for charts. Install with: pip install matplotlib")
        sys.exit(1)


def _build_assumptions(
    flat_qx: float,
    flat_lapse: float,
    valuation_date: date,
) -> tuple:
    """Build minimal AssumptionSet for dashboard."""
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
) -> tuple:
    """Build InforceBlock and ProjectionConfig for dashboard."""
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


def _run_pricing_pipeline(
    inforce: object,
    assumptions: object,
    config: object,
    treaty: object,
    hurdle_rate: float,
) -> tuple:
    from polaris_re.analytics.profit_test import ProfitTester
    from polaris_re.products.term_life import TermLife

    product = TermLife(inforce=inforce, assumptions=assumptions, config=config)  # type: ignore[arg-type]
    gross = product.project()
    net, ceded = treaty.apply(gross)  # type: ignore[union-attr]
    result = ProfitTester(cashflows=net, hurdle_rate=hurdle_rate).run()
    return gross, net, ceded, result


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------


def _cashflow_waterfall(
    profit_by_year: np.ndarray,
    title: str = "Annual Profit Waterfall",
) -> plt.Figure:
    """Stacked waterfall chart of annual profits."""
    fig, ax = plt.subplots(figsize=(10, 5))
    years = np.arange(1, len(profit_by_year) + 1)
    colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in profit_by_year]
    ax.bar(years, profit_by_year, color=colors, edgecolor="white", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Policy Year")
    ax.set_ylabel("Profit ($)")
    ax.set_title(title)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    fig.tight_layout()
    return fig


def _uq_histogram(
    pv_profits: np.ndarray,
    var_95: float,
    cvar_95: float,
    base_pv_profit: float,
    title: str = "Monte Carlo PV Profit Distribution",
) -> plt.Figure:
    """Histogram of simulated PV profits with VaR/CVaR markers."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(pv_profits, bins=40, color="#3498db", edgecolor="white", linewidth=0.5, alpha=0.8)
    ax.axvline(var_95, color="#e74c3c", linestyle="--", linewidth=1.5,
               label=f"VaR 95%: ${var_95:,.0f}")
    ax.axvline(cvar_95, color="#c0392b", linestyle=":", linewidth=1.5,
               label=f"CVaR 95%: ${cvar_95:,.0f}")
    ax.axvline(base_pv_profit, color="#2ecc71", linestyle="-", linewidth=1.5,
               label=f"Base: ${base_pv_profit:,.0f}")
    ax.set_xlabel("PV Profit ($)")
    ax.set_ylabel("Frequency")
    ax.set_title(title)
    ax.legend()
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    fig.tight_layout()
    return fig


def _scenario_tornado(
    scenario_results: dict,
    base_pv: float,
    title: str = "Scenario Sensitivity (PV Profit)",
) -> plt.Figure:
    """Tornado chart showing PV profit deviation from base for each scenario."""
    names = list(scenario_results.keys())
    deviations = [scenario_results[n].pv_profits - base_pv for n in names]

    # Sort by absolute deviation
    pairs = sorted(zip(deviations, names, strict=False), key=lambda x: abs(x[0]))
    deviations_sorted = [p[0] for p in pairs]
    names_sorted = [p[1] for p in pairs]

    fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.6)))
    colors = ["#2ecc71" if d >= 0 else "#e74c3c" for d in deviations_sorted]
    y_pos = np.arange(len(names_sorted))
    ax.barh(y_pos, deviations_sorted, color=colors, edgecolor="white")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names_sorted)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("PV Profit Deviation from Base ($)")
    ax.set_title(title)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Dashboard pages
# ---------------------------------------------------------------------------


def _page_pricing() -> None:
    """Deal pricing page."""
    st.header("Deal Pricing")

    col1, col2, col3 = st.columns(3)
    with col1:
        n_policies = int(st.number_input(
            "Number of Policies", min_value=1, max_value=10000, value=100, step=10
        ))
        attained_age = int(st.slider("Attained Age", 25, 65, 40))
        face_amount = float(st.number_input(
            "Face Amount ($)", min_value=50_000, max_value=5_000_000, value=500_000, step=50_000
        ))
    with col2:
        annual_premium = float(st.number_input(
            "Annual Premium ($)", min_value=100, max_value=50_000, value=1_200, step=100
        ))
        term_years = int(st.slider("Term (years)", 5, 30, 20))
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0
    with col3:
        flat_qx = float(st.slider("Mortality Rate (q_x ‰)", 0.1, 10.0, 1.0, step=0.1)) / 1000.0
        flat_lapse = float(st.slider("Lapse Rate (%)", 1, 20, 5)) / 100.0
        cession_pct = float(st.slider("Cession % (YRT)", 50, 100, 90)) / 100.0
        discount_rate = float(st.slider("Discount Rate (%)", 2, 12, 6)) / 100.0

    if st.button("Run Pricing", type="primary"):
        from polaris_re.core.projection import ProjectionConfig
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
                treaty_id="YRT-DASH",
                cession_pct=cession_pct,
                total_face_amount=face_amount,
            )
            _gross, _net, _ceded, result = _run_pricing_pipeline(
                inforce, assumptions, config, treaty, hurdle_rate
            )

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("PV Profits", f"${result.pv_profits:,.0f}")
        col_b.metric("Profit Margin", f"{result.profit_margin:.2%}")
        col_c.metric("IRR", f"{result.irr:.2%}" if result.irr else "N/A")
        bey = str(result.breakeven_year) if result.breakeven_year else "Never"
        col_d.metric("Break-even Year", bey)

        st.pyplot(_cashflow_waterfall(result.profit_by_year))


def _page_scenario() -> None:
    """Scenario analysis page."""
    st.header("Scenario Analysis")

    col1, col2 = st.columns(2)
    with col1:
        n_policies = int(st.number_input(
            "Number of Policies", min_value=1, max_value=1000, value=50, step=10
        ))
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
                treaty_id="YRT-SCENARIO", cession_pct=0.90, total_face_amount=face_amount
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
        st.pyplot(_scenario_tornado(results_dict, base_pv))

        irr_str = {k: f"{v.irr:.2%}" if v.irr else "N/A" for k, v in results_dict.items()}
        rows = [
            {"Scenario": k, "PV Profit": f"${v.pv_profits:,.0f}", "IRR": irr_str[k]}
            for k, v in results_dict.items()
        ]
        st.table(rows)


def _page_uq() -> None:
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
            treaty = YRTTreaty(treaty_id="YRT-UQ", cession_pct=0.90, total_face_amount=500_000)
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

        st.pyplot(_uq_histogram(
            result.pv_profits, result.var(0.95), result.cvar(0.95), result.base_pv_profit
        ))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Launch the Polaris RE Streamlit dashboard."""
    _check_deps()

    st.set_page_config(
        page_title="Polaris RE Dashboard",
        page_icon="🏔",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.sidebar.title("Polaris RE")
    st.sidebar.caption("Life Reinsurance Pricing Engine")

    page = st.sidebar.radio(
        "Navigation",
        ["Deal Pricing", "Scenario Analysis", "Monte Carlo UQ"],
    )

    if page == "Deal Pricing":
        _page_pricing()
    elif page == "Scenario Analysis":
        _page_scenario()
    elif page == "Monte Carlo UQ":
        _page_uq()


if __name__ == "__main__":
    main()

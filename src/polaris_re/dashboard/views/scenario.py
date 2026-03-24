"""Page 5: Scenario Analysis — rebuilt to use session state assumptions."""

from datetime import date

import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import scenario_tornado
from polaris_re.dashboard.views.pricing import (
    _build_fallback_assumptions,
    _build_fallback_block,
)

__all__ = ["page_scenario"]


def page_scenario() -> None:
    """Scenario analysis page — uses session state or fallback sliders."""
    st.header("Scenario Analysis")

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
        st.warning(
            "No session state configured. Using fallback sliders. "
            "Configure Pages 1-2 for real assumptions."
        )

    # Common parameters
    col1, col2 = st.columns(2)
    with col1:
        projection_years = int(st.slider("Projection Horizon (years)", 5, 30, 20))
        discount_rate = float(st.slider("Discount Rate (%)", 2, 12, 6)) / 100.0
    with col2:
        hurdle_rate = float(st.slider("Hurdle Rate (%)", 5, 20, 10)) / 100.0
        cession_pct = float(st.slider("Cession % (YRT)", 50, 100, 90)) / 100.0

    # Fallback sliders
    if not use_session:
        st.subheader("Fallback Parameters")
        fc1, fc2 = st.columns(2)
        with fc1:
            n_policies = int(
                st.number_input(
                    "Number of Policies", min_value=1, max_value=1000, value=50, step=10
                )
            )
            attained_age = int(st.slider("Attained Age", 25, 65, 40))
            face_amount = float(st.number_input("Face Amount ($)", value=500_000, step=50_000))
        with fc2:
            annual_premium = float(st.number_input("Annual Premium ($)", value=1_200, step=100))

    # Custom scenario builder
    st.subheader("Custom Scenarios")
    st.caption("Add custom stress scenarios beyond the 6 standard ones.")

    if "custom_scenarios" not in st.session_state:
        st.session_state["custom_scenarios"] = []

    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        custom_name = st.text_input("Scenario Name", value="CUSTOM_1")
    with cs2:
        custom_mort = st.slider("Mortality Multiplier", 0.50, 2.00, 1.00, step=0.05, key="cs_m")
    with cs3:
        custom_lapse = st.slider("Lapse Multiplier", 0.50, 2.00, 1.00, step=0.05, key="cs_l")

    if st.button("Add Custom Scenario"):
        st.session_state["custom_scenarios"].append((custom_name, custom_mort, custom_lapse))
        st.success(
            f"Added scenario: {custom_name} (mort={custom_mort:.2f}, lapse={custom_lapse:.2f})"
        )

    if st.session_state["custom_scenarios"]:
        st.caption(f"Custom scenarios: {len(st.session_state['custom_scenarios'])}")
        for cs_name, cs_m, cs_l in st.session_state["custom_scenarios"]:
            st.text(f"  {cs_name}: mortality={cs_m:.2f}, lapse={cs_l:.2f}")

    if st.button("Run Scenarios", type="primary"):
        from polaris_re.analytics.scenario import ScenarioAdjustment, ScenarioRunner
        from polaris_re.core.projection import ProjectionConfig
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner("Running scenario analysis..."):
            valuation_date = date.today()

            if use_session:
                inforce = inforce_block
                assumptions = assumption_set
                face_total = float(inforce.total_face_amount())
            else:
                inforce = _build_fallback_block(
                    n_policies,  # type: ignore[possibly-undefined]
                    attained_age,  # type: ignore[possibly-undefined]
                    face_amount,  # type: ignore[possibly-undefined]
                    annual_premium,  # type: ignore[possibly-undefined]
                    projection_years,
                    valuation_date,
                )
                assumptions = _build_fallback_assumptions(0.001, 0.05, valuation_date)
                face_total = face_amount  # type: ignore[possibly-undefined]

            config = ProjectionConfig(
                valuation_date=valuation_date,
                projection_horizon_years=projection_years,
                discount_rate=discount_rate,
            )
            treaty = YRTTreaty(
                treaty_name="YRT-SCENARIO",
                cession_pct=cession_pct,
                total_face_amount=face_total,
            )

            # Build scenario list: standard + custom
            custom_adjustments = [
                ScenarioAdjustment(
                    name=cs_name,
                    mortality_multiplier=cs_m,
                    lapse_multiplier=cs_l,
                    description=f"Custom: mort={cs_m:.2f}, lapse={cs_l:.2f}",
                )
                for cs_name, cs_m, cs_l in st.session_state.get("custom_scenarios", [])
            ]

            runner = ScenarioRunner(
                inforce=inforce,  # type: ignore[arg-type]
                base_assumptions=assumptions,  # type: ignore[arg-type]
                config=config,
                treaty=treaty,
                hurdle_rate=hurdle_rate,
            )

            # Standard scenarios + any custom ones
            all_scenarios = ScenarioRunner.standard_stress_scenarios() + custom_adjustments
            results = runner.run(scenarios=all_scenarios)

        results_dict = {name: res for name, res in results.scenarios}
        base_case = results.base_case()
        base_pv = base_case.pv_profits if base_case else results.scenarios[0][1].pv_profits
        st.pyplot(scenario_tornado(results_dict, base_pv))

        # Scenario comparison table with IRR and margin
        rows = []
        for name, res in results_dict.items():
            rows.append(
                {
                    "Scenario": name,
                    "PV Profit": f"${res.pv_profits:,.0f}",
                    "Profit Margin": f"{res.profit_margin:.2%}",
                    "IRR": f"{res.irr:.2%}" if res.irr else "N/A",
                    "Break-even": str(res.breakeven_year) if res.breakeven_year else "Never",
                }
            )
        st.dataframe(rows, use_container_width=True)

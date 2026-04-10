"""Page 5: Scenario Analysis — uses session state assumptions and deal config.

Requires Inforce Block and Assumptions to be configured. No fallback.
Uses the shared projection helpers for consistent YRT rate derivation.
"""

import streamlit as st  # type: ignore[import-untyped]

from polaris_re.dashboard.components.charts import scenario_tornado
from polaris_re.dashboard.components.projection import (
    build_projection_config,
    derive_yrt_rate,
    run_gross_projection,
)
from polaris_re.dashboard.components.state import (
    get_deal_config,
    require_single_product_cohort,
)

__all__ = ["page_scenario"]


def page_scenario() -> None:
    """Scenario analysis page \u2014 uses session state assumptions."""
    st.header("Scenario Analysis")

    inforce_block = st.session_state.get("inforce_block")
    assumption_set = st.session_state.get("assumption_set")

    if inforce_block is None or assumption_set is None:
        st.warning(
            "Configure **Inforce Block** (Page 1) and **Assumptions** (Page 2) first. "
            "All projection parameters are set on the Assumptions page."
        )
        return

    if not require_single_product_cohort(inforce_block, "Scenario Analysis"):
        return

    st.success(
        f"Using session state: {inforce_block.n_policies:,} policies, "
        f"assumptions v{assumption_set.version}"
    )

    cfg = get_deal_config()

    # Show inherited config with option to override cession and YRT loading for sensitivity
    with st.expander("Scenario Configuration (overrides for sensitivity)", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            cession_pct = (
                float(
                    st.slider(
                        "Cession % (YRT)",
                        50,
                        100,
                        int(float(cfg.get("cession_pct", 0.90)) * 100),
                        key="sc_cession",
                    )
                )
                / 100.0
            )
            yrt_loading = (
                float(
                    st.slider(
                        "YRT Loading over Mortality (%)",
                        min_value=0,
                        max_value=50,
                        value=int(float(cfg.get("yrt_loading", 0.10)) * 100),
                        step=5,
                        key="sc_yrt_load",
                        help="Reinsurer margin above expected mortality for YRT rate.",
                    )
                )
                / 100.0
            )
        with col2:
            hurdle_rate = (
                float(
                    st.slider(
                        "Hurdle Rate (%)",
                        5,
                        20,
                        int(float(cfg.get("hurdle_rate", 0.10)) * 100),
                        key="sc_hurdle",
                    )
                )
                / 100.0
            )

    st.caption(
        "Projection horizon, discount rate, and expenses are inherited from the "
        "Assumptions page. Cession %, YRT loading, and hurdle rate can be adjusted "
        "for sensitivity testing."
    )

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
        if abs(custom_mort - 1.0) < 1e-6 and abs(custom_lapse - 1.0) < 1e-6:
            st.warning(
                "Mortality=1.00 and Lapse=1.00 is identical to the BASE scenario. "
                "Adjust at least one parameter."
            )
        else:
            st.session_state["custom_scenarios"].append((custom_name, custom_mort, custom_lapse))
            st.success(
                f"Added scenario: {custom_name} (mort={custom_mort:.2f}, lapse={custom_lapse:.2f})"
            )

    if st.session_state["custom_scenarios"]:
        st.caption(f"Custom scenarios: {len(st.session_state['custom_scenarios'])}")
        indices_to_remove: list[int] = []
        for idx, (cs_name, cs_m, cs_l) in enumerate(st.session_state["custom_scenarios"]):
            sc_col1, sc_col2 = st.columns([4, 1])
            with sc_col1:
                st.text(f"  {cs_name}: mortality={cs_m:.2f}, lapse={cs_l:.2f}")
            with sc_col2:
                if st.button("\u2715", key=f"del_scenario_{idx}", help=f"Remove {cs_name}"):
                    indices_to_remove.append(idx)
        if indices_to_remove:
            st.session_state["custom_scenarios"] = [
                s
                for i, s in enumerate(st.session_state["custom_scenarios"])
                if i not in indices_to_remove
            ]
            st.rerun()
        if st.button("Clear All Custom Scenarios"):
            st.session_state["custom_scenarios"] = []
            st.rerun()

    if st.button("Run Scenarios", type="primary"):
        from polaris_re.analytics.scenario import ScenarioAdjustment, ScenarioRunner
        from polaris_re.reinsurance.yrt import YRTTreaty

        with st.spinner("Running scenario analysis..."):
            config = build_projection_config()
            face_total = float(inforce_block.total_face_amount())

            # Derive YRT rate from a base gross projection (consistent with Deal Pricing)
            _base_gross = run_gross_projection(inforce_block, assumption_set, config)
            _yrt_rate = derive_yrt_rate(_base_gross, face_total, yrt_loading)
            st.info(
                f"Derived YRT rate: {_yrt_rate:.3f} per $1,000 NAR (loading = {yrt_loading:.0%})"
            )

            treaty = YRTTreaty(
                treaty_name="YRT-SCENARIO",
                cession_pct=cession_pct,
                total_face_amount=face_total,
                flat_yrt_rate_per_1000=_yrt_rate,
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
                inforce=inforce_block,
                base_assumptions=assumption_set,
                config=config,
                treaty=treaty,
                hurdle_rate=hurdle_rate,
            )

            all_scenarios = ScenarioRunner.standard_stress_scenarios() + custom_adjustments
            results = runner.run(scenarios=all_scenarios)

        results_dict = {name: res for name, res in results.scenarios}
        base_case = results.base_case()
        base_pv = base_case.pv_profits if base_case else results.scenarios[0][1].pv_profits
        st.pyplot(scenario_tornado(results_dict, base_pv))

        # Scenario comparison table
        rows = []
        for name, res in results_dict.items():
            delta = res.pv_profits - base_pv
            rows.append(
                {
                    "Scenario": name,
                    "PV Profit": f"${res.pv_profits:,.0f}",
                    "Delta vs Base": f"${delta:+,.0f}",
                    "Delta %": f"{delta / abs(base_pv) * 100:+.1f}%" if base_pv != 0 else "N/A",
                    "Profit Margin": f"{res.profit_margin:.2%}",
                    "IRR": f"{res.irr:.2%}" if res.irr else "N/A",
                    "Break-even": str(res.breakeven_year) if res.breakeven_year else "N/A",
                }
            )
        st.dataframe(rows, use_container_width=True)

        # Note about scenario mechanics
        st.caption(
            "**Scenario mechanics**: Each scenario re-projects the full inforce "
            "block with scaled mortality and/or lapse assumptions. The YRT rate "
            "is locked at the base-case derived rate \u2014 only claims and in-force "
            "runoff change. This reflects the contractual nature of YRT pricing "
            "where rates are set at treaty inception."
        )

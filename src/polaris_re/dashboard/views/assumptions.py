"""Page 2: Assumptions — single source of truth for all deal inputs.

Consolidates mortality, lapse, improvement, expense loading, treaty
configuration, and projection parameters so every downstream page
(Deal Pricing, Treaty Comparison, Scenario Analysis, Monte Carlo UQ,
IFRS 17) consumes the same saved configuration.
"""

import os
import tempfile
from pathlib import Path

import numpy as np
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.core.pipeline import DEFAULT_LAPSE_CURVE
from polaris_re.dashboard.components.state import get_deal_config

__all__ = ["page_assumptions"]

# Default lapse curve: derived from the shared DEFAULT_LAPSE_CURVE
# in core.pipeline (the single source of truth), re-keyed with display labels.
_DEFAULT_LAPSE_RATES: dict[str, float] = {
    **{f"Year {k}": v for k, v in DEFAULT_LAPSE_CURVE.items() if isinstance(k, int)},
    "Ultimate": DEFAULT_LAPSE_CURVE["ultimate"],
}


# ------------------------------------------------------------------ #
# Mortality section                                                    #
# ------------------------------------------------------------------ #


def _mortality_section() -> tuple[object, str] | None:
    """Mortality basis selection. Returns (MortalityTable, source_label) or None."""
    st.subheader("Mortality Basis")

    source_options = ["SOA VBT 2015", "CIA 2014", "2001 CSO", "Flat Rate"]
    selection = st.selectbox("Mortality Table", source_options)

    mortality_multiplier = st.slider(
        "Mortality Multiplier", min_value=0.50, max_value=2.00, value=1.00, step=0.05
    )
    st.session_state["mortality_multiplier"] = mortality_multiplier

    if selection == "Flat Rate":
        flat_qx = (
            float(
                st.slider("Flat q_x (\u2030)", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
            )
            / 1000.0
        )
        st.session_state["mortality_source"] = "flat_rate"
        mortality = _build_flat_mortality(flat_qx)
        st.info(f"Using flat mortality rate: {flat_qx * 1000:.1f}\u2030 per annum")
        return mortality, "Flat Rate"

    # Real table loading
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource

    source_map = {
        "SOA VBT 2015": MortalityTableSource.SOA_VBT_2015,
        "CIA 2014": MortalityTableSource.CIA_2014,
        "2001 CSO": MortalityTableSource.CSO_2001,
    }
    table_source = source_map[selection]  # type: ignore[index]
    data_dir = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"

    try:
        mortality = MortalityTable.load(source=table_source, data_dir=data_dir)
        st.session_state["mortality_source"] = selection
        st.success(f"Loaded {selection} (ages {mortality.min_age}-{mortality.max_age})")
        _plot_qx_curves(mortality)
        return mortality, selection  # type: ignore[return-value]
    except (FileNotFoundError, Exception) as exc:
        st.warning(f"Could not load {selection}: {exc}")
        st.info(
            "Falling back to flat rate. "
            "Set POLARIS_DATA_DIR or place tables in data/mortality_tables/."
        )
        flat_qx = (
            float(
                st.slider(
                    "Fallback Flat q_x (\u2030)",
                    min_value=0.1,
                    max_value=10.0,
                    value=1.0,
                    step=0.1,
                )
            )
            / 1000.0
        )
        mortality = _build_flat_mortality(flat_qx)
        st.session_state["mortality_source"] = "flat_rate"
        return mortality, "Flat Rate"


# ------------------------------------------------------------------ #
# ML model sections                                                    #
# ------------------------------------------------------------------ #


def _ml_mortality_section() -> None:
    """ML mortality model upload and feature importance display."""
    use_ml_mort = st.checkbox("Use ML Mortality Model")
    if not use_ml_mort:
        st.session_state["ml_mortality_model"] = None
        return

    uploaded = st.file_uploader("Upload ML Mortality Model (.joblib)", type=["joblib"])
    if uploaded is None:
        st.info("Upload a joblib file saved via `MLMortalityAssumption.save()`")
        return

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = Path(tmp.name)

    try:
        from polaris_re.assumptions.ml_mortality import MLMortalityAssumption

        ml_model = MLMortalityAssumption.load(tmp_path)
        st.session_state["ml_mortality_model"] = ml_model
        st.success(
            f"Loaded ML mortality model: {ml_model.model_type} "
            f"({len(ml_model.feature_names)} features)"
        )
        _plot_feature_importance(ml_model, "ML Mortality Model \u2014 Feature Importance")
    except Exception as exc:
        st.error(f"Failed to load ML mortality model: {exc}")


def _ml_lapse_section() -> None:
    """ML lapse model upload and feature importance display."""
    use_ml_lapse = st.checkbox("Use ML Lapse Model")
    if not use_ml_lapse:
        st.session_state["ml_lapse_model"] = None
        return

    uploaded = st.file_uploader(
        "Upload ML Lapse Model (.joblib)", type=["joblib"], key="ml_lapse_upload"
    )
    if uploaded is None:
        st.info("Upload a joblib file saved via `MLLapseAssumption.save()`")
        return

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = Path(tmp.name)

    try:
        from polaris_re.assumptions.ml_lapse import MLLapseAssumption

        ml_model = MLLapseAssumption.load(tmp_path)
        st.session_state["ml_lapse_model"] = ml_model
        st.success(
            f"Loaded ML lapse model: {ml_model.model_type} ({len(ml_model.feature_names)} features)"
        )
        _plot_feature_importance(ml_model, "ML Lapse Model \u2014 Feature Importance")
    except Exception as exc:
        st.error(f"Failed to load ML lapse model: {exc}")


def _plot_feature_importance(ml_model: object, title: str) -> None:
    """Display feature importance bar chart for an ML model."""
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]

    try:
        model = ml_model.model  # type: ignore[union-attr]
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            features = ml_model.feature_names  # type: ignore[union-attr]

            idx = np.argsort(importances)
            fig, ax = plt.subplots(figsize=(8, max(3, len(features) * 0.4)))
            ax.barh(np.array(features)[idx], importances[idx], color="#3498db")
            ax.set_xlabel("Importance")
            ax.set_title(title)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("Model does not expose feature_importances_.")
    except Exception:
        st.info("Could not extract feature importances from model.")


# ------------------------------------------------------------------ #
# Helper builders                                                      #
# ------------------------------------------------------------------ #


def _build_flat_mortality(flat_qx: float) -> object:
    """Build a synthetic flat-rate mortality table with all sex/smoker combos."""
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.policy import Sex, SmokerStatus
    from polaris_re.utils.table_io import MortalityTableArray

    n_ages = 121 - 18
    qx = np.full(n_ages, flat_qx, dtype=np.float64)
    rates_2d = qx.reshape(-1, 1)

    tables: dict[str, MortalityTableArray] = {}
    for sex in Sex:
        for smoker in SmokerStatus:
            key = f"{sex.value}_{smoker.value}"
            tables[key] = MortalityTableArray(
                rates=rates_2d.copy(),
                min_age=18,
                max_age=120,
                select_period=0,
                source_file=Path("synthetic"),
            )

    return MortalityTable(
        source=MortalityTableSource.CSO_2001,
        table_name="Flat Rate (Dashboard)",
        min_age=18,
        max_age=120,
        select_period_years=0,
        has_smoker_distinct_rates=False,
        tables=tables,
    )


def _plot_qx_curves(mortality: object) -> None:
    """Plot q_x curves for all loaded sex/smoker combos."""
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]

    from polaris_re.assumptions.mortality import MortalityTable

    mt: MortalityTable = mortality  # type: ignore[assignment]

    fig, ax = plt.subplots(figsize=(10, 5))
    ages = np.arange(mt.min_age, mt.max_age + 1, dtype=np.int32)

    key_labels: dict[str, str] = {
        "M_S": "Male Smoker",
        "M_NS": "Male Non-Smoker",
        "F_S": "Female Smoker",
        "F_NS": "Female Non-Smoker",
        "M_U": "Male Aggregate",
        "F_U": "Female Aggregate",
    }

    for key, table_array in mt.tables.items():
        ultimate_col = table_array.select_period
        q_annual = table_array.rates[:, ultimate_col]
        label = key_labels.get(key, key)
        ax.plot(ages[: len(q_annual)], q_annual, label=label, linewidth=1.5)

    ax.set_xlabel("Attained Age")
    ax.set_ylabel("Annual q_x")
    ax.set_title(f"Mortality Rates \u2014 {mt.table_name}")
    ax.legend()
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ------------------------------------------------------------------ #
# Lapse section                                                        #
# ------------------------------------------------------------------ #


def _lapse_section() -> object | None:
    """Lapse basis selection. Returns LapseAssumption or None."""
    st.subheader("Lapse Basis")

    lapse_mode = st.selectbox("Lapse Assumption", ["Manual Duration Table", "CSV Upload"])

    lapse_multiplier = st.slider(
        "Lapse Multiplier", min_value=0.50, max_value=2.00, value=1.00, step=0.05
    )
    st.session_state["lapse_multiplier"] = lapse_multiplier

    if lapse_mode == "Manual Duration Table":
        return _manual_lapse()
    return _csv_lapse()


def _manual_lapse() -> object:
    """Manual duration table with sliders for years 1-10 + ultimate."""
    from polaris_re.assumptions.lapse import LapseAssumption

    rates: dict[int | str, float] = {}
    cols = st.columns(4)
    for i, (label, default) in enumerate(_DEFAULT_LAPSE_RATES.items()):
        col_idx = i % 4
        with cols[col_idx]:
            if label == "Ultimate":
                val = st.slider(
                    label,
                    min_value=0.0,
                    max_value=0.30,
                    value=default,
                    step=0.005,
                    format="%.3f",
                )
                rates["ultimate"] = val
            else:
                val = st.slider(
                    label,
                    min_value=0.0,
                    max_value=0.30,
                    value=default,
                    step=0.005,
                    format="%.3f",
                )
                rates[i + 1] = val

    lapse = LapseAssumption.from_duration_table(rates)
    st.session_state["lapse_source"] = "manual"

    _plot_lapse_curve(lapse)
    return lapse


def _csv_lapse() -> object | None:
    """CSV upload for lapse table."""
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.utils.table_io import load_lapse_csv

    uploaded = st.file_uploader("Upload lapse CSV", type=["csv"])
    if uploaded is None:
        st.info("Upload a CSV with columns: policy_year, rate")
        return None

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = Path(tmp.name)

    try:
        lapse_array = load_lapse_csv(tmp_path)
        table_dict: dict[int | str, float] = {}
        for yr in range(1, lapse_array.max_policy_year + 1):
            table_dict[yr] = float(lapse_array.rates[yr - 1])
        table_dict["ultimate"] = float(lapse_array.rates[-1])

        lapse = LapseAssumption.from_duration_table(table_dict)
        st.session_state["lapse_source"] = "csv"
        st.success(f"Loaded lapse table: {lapse_array.max_policy_year} years")
        _plot_lapse_curve(lapse)
        return lapse
    except Exception as exc:
        st.error(f"Failed to load lapse CSV: {exc}")
        return None


def _plot_lapse_curve(lapse: object) -> None:
    """Plot lapse rate by policy year."""
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]

    from polaris_re.assumptions.lapse import LapseAssumption

    la: LapseAssumption = lapse  # type: ignore[assignment]

    max_yr = la.select_period_years + 5
    years = list(range(1, max_yr + 1))
    rates = [
        float(la.select_rates[yr - 1]) if yr <= la.select_period_years else la.ultimate_rate
        for yr in years
    ]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(years, rates, marker="o", linewidth=1.5, color="#2ecc71")
    ax.axhline(la.ultimate_rate, color="gray", linestyle="--", alpha=0.5, label="Ultimate")
    ax.set_xlabel("Policy Year")
    ax.set_ylabel("Annual Lapse Rate")
    ax.set_title("Lapse Rates by Policy Year")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ------------------------------------------------------------------ #
# Improvement section                                                  #
# ------------------------------------------------------------------ #


def _improvement_section() -> object | None:
    """Mortality improvement scale selection. Returns MortalityImprovement or None."""
    from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement

    with st.expander("Mortality Improvement Scale"):
        improvement = st.selectbox(
            "Mortality Improvement", ["None", "Scale AA", "MP-2020", "CPM-B"]
        )

        mort_source = st.session_state.get("mortality_source", "")
        base_year_map = {
            "SOA VBT 2015": 2015,
            "CIA 2014": 2014,
            "2001 CSO": 2001,
        }
        base_year = base_year_map.get(mort_source, 2015)

        scale_map: dict[str, ImprovementScale] = {
            "None": ImprovementScale.NONE,
            "Scale AA": ImprovementScale.SCALE_AA,
            "MP-2020": ImprovementScale.MP_2020,
            "CPM-B": ImprovementScale.CPM_B,
        }
        scale = scale_map[improvement]

        if scale == ImprovementScale.NONE:
            st.warning(
                "No mortality improvement applied. The industry standard for "
                "North American pricing is to apply an improvement scale "
                "(e.g. SOA MP-2020 or Scale AA). Static mortality tables will "
                "overstate YRT premium rates for long-duration blocks."
            )
            return None

        mi = MortalityImprovement(scale=scale, base_year=base_year)
        st.info(
            f"**{improvement}** selected (base year {base_year}). "
            f"Improvement will be applied during projection."
        )
        return mi


# ------------------------------------------------------------------ #
# Expense loading section (NEW — previously on Deal Pricing only)      #
# ------------------------------------------------------------------ #


def _expense_section() -> tuple[float, float]:
    """Expense loading inputs. Returns (acquisition_cost, maintenance_cost)."""
    st.subheader("Expense Loading")
    st.caption(
        "These expense assumptions apply to all projections across all pages "
        "(Deal Pricing, Treaty Comparison, Scenario Analysis, Monte Carlo UQ)."
    )
    cfg = get_deal_config()

    ec1, ec2 = st.columns(2)
    with ec1:
        acquisition_cost = float(
            st.number_input(
                "Acquisition Cost per Policy ($)",
                min_value=0,
                max_value=10_000,
                value=int(cfg.get("acquisition_cost", 500)),
                step=50,
                help="One-time cost at issue: underwriting, commission, setup.",
                key="assum_acq_cost",
            )
        )
    with ec2:
        maintenance_cost = float(
            st.number_input(
                "Annual Maintenance Cost per Policy ($)",
                min_value=0,
                max_value=1_000,
                value=int(cfg.get("maintenance_cost", 75)),
                step=5,
                help="Ongoing admin cost per in-force policy per year.",
                key="assum_maint_cost",
            )
        )
    return acquisition_cost, maintenance_cost


# ------------------------------------------------------------------ #
# Product type section                                                  #
# ------------------------------------------------------------------ #


def _product_type_section() -> str:
    """Product type selector. Returns product type string for deal config."""
    st.subheader("Product Type")
    cfg = get_deal_config()
    product_options = ["TERM", "WHOLE_LIFE", "UL"]
    product_labels = {
        "TERM": "Term Life",
        "WHOLE_LIFE": "Whole Life",
        "UL": "Universal Life",
    }
    current = str(cfg.get("product_type", "TERM"))
    idx = product_options.index(current) if current in product_options else 0
    selection = st.selectbox(
        "Product Type",
        product_options,
        index=idx,
        format_func=lambda x: product_labels.get(x, x),
        key="assum_product_type",
        help=(
            "Selects the projection engine. Term Life has a fixed expiry; "
            "Whole Life projects to max age 120; Universal Life models "
            "account value roll-forward with COI deductions."
        ),
    )
    if selection == "WHOLE_LIFE":
        st.info(
            "Whole Life: policies have no term expiry. Ensure your inforce "
            "block has `policy_term` set to null or omitted for permanent products."
        )
    elif selection == "UL":
        st.info(
            "Universal Life: requires `account_value` and `credited_rate` "
            "fields on each policy. The projection uses AV roll-forward with COI."
        )
    return selection  # type: ignore[return-value]


# ------------------------------------------------------------------ #
# Treaty configuration section (NEW — previously on Deal Pricing only) #
# ------------------------------------------------------------------ #


def _treaty_section() -> dict[str, object]:
    """Treaty and projection configuration. Returns a dict of treaty params."""
    st.subheader("Treaty & Projection Configuration")
    st.caption(
        "Reinsurance treaty parameters and projection settings used by all "
        "downstream pages. Individual pages may override specific parameters "
        "for comparative analysis (e.g. Treaty Comparison tests multiple structures)."
    )
    cfg = get_deal_config()

    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        treaty_type = st.selectbox(
            "Default Treaty Type",
            ["YRT", "Coinsurance", "Modco", "None (Gross)"],
            index=["YRT", "Coinsurance", "Modco", "None (Gross)"].index(
                str(cfg.get("treaty_type", "YRT"))
            ),
            key="assum_treaty_type",
        )
    with tc2:
        cession_pct = (
            float(
                st.slider(
                    "Cession %",
                    0,
                    100,
                    int(float(cfg.get("cession_pct", 0.90)) * 100),
                    key="assum_cession",
                )
            )
            / 100.0
        )
    with tc3:
        modco_rate = 0.045
        if treaty_type == "Modco":
            modco_rate = (
                float(
                    st.slider("Modco Interest Rate (%)", 1.0, 8.0, 4.5, step=0.5, key="assum_modco")
                )
                / 100.0
            )

    # YRT rate configuration
    yrt_rate_per_1000: float | None = None
    yrt_rate_basis = "Mortality-based"
    yrt_loading = 0.10
    if treaty_type == "YRT":
        yrt_rate_basis = st.selectbox(
            "YRT Rate Basis",
            ["Mortality-based", "Manual Rate"],
            key="assum_yrt_basis",
            help=(
                "Mortality-based: derives YRT rate from the portfolio's "
                "average mortality rate with a configurable loading. "
                "Manual: enter a flat rate per $1,000 NAR directly."
            ),
        )
        if yrt_rate_basis == "Mortality-based":
            yrt_loading = (
                float(
                    st.slider(
                        "YRT Loading over Expected Mortality (%)",
                        min_value=0,
                        max_value=50,
                        value=int(float(cfg.get("yrt_loading", 0.10)) * 100),
                        step=5,
                        help="Reinsurer margin above expected mortality. 10% = q_x * 1.10.",
                        key="assum_yrt_loading",
                    )
                )
                / 100.0
            )
        else:
            yrt_rate_per_1000 = float(
                st.number_input(
                    "Flat YRT Rate per $1,000 NAR",
                    min_value=0.01,
                    max_value=50.0,
                    value=2.0,
                    step=0.1,
                    format="%.2f",
                    help="Annual rate per $1,000 of Net Amount at Risk.",
                    key="assum_yrt_manual",
                )
            )

    # Projection parameters
    st.subheader("Projection Parameters")
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        projection_years = int(
            st.slider(
                "Projection Horizon (years)",
                5,
                30,
                int(cfg.get("projection_years", 20)),
                key="assum_proj_years",
            )
        )
    with pc2:
        discount_rate = (
            float(
                st.slider(
                    "Discount Rate (%)",
                    2,
                    12,
                    int(float(cfg.get("discount_rate", 0.06)) * 100),
                    key="assum_disc_rate",
                )
            )
            / 100.0
        )
    with pc3:
        hurdle_rate = (
            float(
                st.slider(
                    "Hurdle Rate (%)",
                    5,
                    20,
                    int(float(cfg.get("hurdle_rate", 0.10)) * 100),
                    key="assum_hurdle",
                )
            )
            / 100.0
        )

    return {
        "treaty_type": treaty_type,
        "cession_pct": cession_pct,
        "yrt_loading": yrt_loading,
        "yrt_rate_per_1000": yrt_rate_per_1000,
        "yrt_rate_basis": yrt_rate_basis,
        "modco_rate": modco_rate,
        "discount_rate": discount_rate,
        "hurdle_rate": hurdle_rate,
        "projection_years": projection_years,
    }


# ------------------------------------------------------------------ #
# Main page                                                            #
# ------------------------------------------------------------------ #


def page_assumptions() -> None:
    """Assumptions page \u2014 single source of truth for all deal inputs."""
    st.header("Assumptions")
    st.caption(
        "All assumption inputs are configured here and shared across every "
        "downstream page. Save assumptions before navigating to Deal Pricing, "
        "Treaty Comparison, Scenario Analysis, or Monte Carlo UQ."
    )

    # --- Actuarial assumptions ---
    mortality_result = _mortality_section()
    _ml_mortality_section()

    st.divider()
    lapse_result = _lapse_section()
    _ml_lapse_section()

    st.divider()
    improvement_result = _improvement_section()

    st.divider()
    # --- Expense loading ---
    acquisition_cost, maintenance_cost = _expense_section()

    st.divider()
    # --- Product type ---
    product_type = _product_type_section()

    st.divider()
    # --- Treaty & projection config ---
    treaty_params = _treaty_section()

    st.divider()
    if st.button("Save All Assumptions", type="primary"):
        if mortality_result is None:
            st.error("No mortality table selected.")
            return
        if lapse_result is None:
            st.error("No lapse assumption configured.")
            return

        from datetime import date

        from polaris_re.analytics.scenario import _scale_lapse, _scale_mortality
        from polaris_re.assumptions.assumption_set import AssumptionSet

        # Use ML model as mortality source if available
        ml_mort = st.session_state.get("ml_mortality_model")
        mortality, source_label = mortality_result
        effective_mortality = ml_mort if ml_mort is not None else mortality

        # Apply user-configured multipliers
        mort_mult = st.session_state.get("mortality_multiplier", 1.0)
        lapse_mult = st.session_state.get("lapse_multiplier", 1.0)

        if mort_mult != 1.0 and ml_mort is None:
            effective_mortality = _scale_mortality(effective_mortality, mort_mult)
        if lapse_mult != 1.0:
            lapse_result = _scale_lapse(lapse_result, lapse_mult)  # type: ignore[arg-type]

        assumption_set = AssumptionSet(
            mortality=effective_mortality,  # type: ignore[arg-type]
            lapse=lapse_result,  # type: ignore[arg-type]
            improvement=improvement_result,  # type: ignore[arg-type]
            version=f"dashboard-{source_label}-{date.today().isoformat()}",
            effective_date=date.today(),
        )
        st.session_state["assumption_set"] = assumption_set

        # Save deal config centrally
        deal_cfg = dict(treaty_params)
        deal_cfg["acquisition_cost"] = acquisition_cost
        deal_cfg["maintenance_cost"] = maintenance_cost
        deal_cfg["product_type"] = product_type
        st.session_state["deal_config"] = deal_cfg

        # Clear cached results so downstream pages re-compute
        st.session_state["gross_result"] = None
        st.session_state["pricing_result"] = None
        st.session_state["pricing_net_result"] = None
        st.session_state["pricing_ceded_result"] = None

        lapse_ult = assumption_set.lapse.ultimate_rate
        mult_info = ""
        if mort_mult != 1.0:
            mult_info += f" (mort x{mort_mult:.2f})"
        if lapse_mult != 1.0:
            mult_info += f" (lapse x{lapse_mult:.2f})"

        if ml_mort is not None:
            st.success(
                f"Assumptions saved \u2014 Mortality: ML model (overriding {source_label}), "
                f"Lapse ultimate: {lapse_ult:.1%}{mult_info}"
            )
        else:
            st.success(
                f"Assumptions saved \u2014 Mortality: {source_label}, "
                f"Lapse ultimate: {lapse_ult:.1%}{mult_info}"
            )
        st.success(
            f"Deal config saved \u2014 Treaty: {treaty_params['treaty_type']}, "
            f"Cession: {treaty_params['cession_pct']:.0%}, "
            f"Discount: {treaty_params['discount_rate']:.0%}, "
            f"Expenses: ${acquisition_cost:,.0f} acq + ${maintenance_cost:,.0f}/yr maint"
        )

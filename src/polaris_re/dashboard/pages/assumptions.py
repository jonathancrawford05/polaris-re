"""Page 2: Assumptions — mortality, lapse, and improvement scale selection."""

import os
from pathlib import Path

import numpy as np
import streamlit as st  # type: ignore[import-untyped]

__all__ = ["page_assumptions"]

# Default lapse curve: realistic duration-based select structure
_DEFAULT_LAPSE_RATES: dict[str, float] = {
    "Year 1": 0.06,
    "Year 2": 0.05,
    "Year 3": 0.04,
    "Year 4": 0.035,
    "Year 5": 0.03,
    "Year 6": 0.025,
    "Year 7": 0.02,
    "Year 8": 0.02,
    "Year 9": 0.02,
    "Year 10": 0.02,
    "Ultimate": 0.015,
}


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
        # Build a synthetic flat-rate table
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


def _build_flat_mortality(flat_qx: float) -> object:
    """Build a synthetic flat-rate mortality table."""
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
    return MortalityTable.from_table_array(
        source=MortalityTableSource.CSO_2001,
        table_name="Flat Rate (Dashboard)",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.UNKNOWN,
    )


def _plot_qx_curves(mortality: object) -> None:
    """Plot q_x curves for all loaded sex/smoker combos."""
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]

    from polaris_re.assumptions.mortality import MortalityTable

    mt: MortalityTable = mortality  # type: ignore[assignment]

    fig, ax = plt.subplots(figsize=(10, 5))
    ages = np.arange(mt.min_age, mt.max_age + 1, dtype=np.int32)

    for key, table_array in mt.tables.items():
        # Use ultimate column for display
        ultimate_col = table_array.select_period
        q_annual = table_array.rates[:, ultimate_col]
        label = key.replace("_", " ").title()
        ax.plot(ages[: len(q_annual)], q_annual, label=label, linewidth=1.5)

    ax.set_xlabel("Attained Age")
    ax.set_ylabel("Annual q_x")
    ax.set_title(f"Mortality Rates — {mt.table_name}")
    ax.legend()
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


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
                val = st.slider(label, min_value=0.0, max_value=0.30, value=default, step=0.005)
                rates["ultimate"] = val
            else:
                year_num = i + 1
                val = st.slider(label, min_value=0.0, max_value=0.30, value=default, step=0.005)
                rates[year_num] = val

    lapse = LapseAssumption.from_duration_table(rates)
    st.session_state["lapse_source"] = "manual"

    _plot_lapse_curve(lapse)
    return lapse


def _csv_lapse() -> object | None:
    """CSV upload for lapse table."""
    import tempfile

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
        # Build LapseAssumption from the loaded rates
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


def _improvement_section() -> None:
    """Mortality improvement scale selection (informational only)."""
    with st.expander("Mortality Improvement Scale"):
        improvement = st.selectbox(
            "Mortality Improvement", ["None", "Scale AA", "MP-2020", "CPM-B"]
        )
        if improvement == "None":
            st.info("No mortality improvement applied.")
        else:
            st.info(
                f"**{improvement}** selected. "
                "Improvement will be applied during projection (Phase C)."
            )


def page_assumptions() -> None:
    """Assumptions page — mortality, lapse, and improvement selection."""
    st.header("Assumptions")

    mortality_result = _mortality_section()
    st.divider()
    lapse_result = _lapse_section()
    st.divider()
    _improvement_section()

    st.divider()
    if st.button("Save Assumptions", type="primary"):
        if mortality_result is None:
            st.error("No mortality table selected.")
            return
        if lapse_result is None:
            st.error("No lapse assumption configured.")
            return

        from datetime import date

        from polaris_re.assumptions.assumption_set import AssumptionSet

        mortality, source_label = mortality_result
        assumption_set = AssumptionSet(
            mortality=mortality,  # type: ignore[arg-type]
            lapse=lapse_result,  # type: ignore[arg-type]
            version=f"dashboard-{source_label}-{date.today().isoformat()}",
            effective_date=date.today(),
        )
        st.session_state["assumption_set"] = assumption_set
        st.success(f"Assumptions saved: {assumption_set.summary}")

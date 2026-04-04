"""Page 1: Inforce Block — upload CSV or generate synthetic block."""

import tempfile
from pathlib import Path

import numpy as np
import streamlit as st  # type: ignore[import-untyped]

__all__ = ["page_inforce"]


def _age_band(age: int) -> str:
    """Assign an attained age to a 5-year band label."""
    if age >= 70:
        return "70+"
    lower = (age // 5) * 5
    return f"{lower}-{lower + 4}"


def _summary_panel(block: object) -> None:
    """Display summary metrics, demographic charts, face amount, and duration distributions."""
    from polaris_re.core.inforce import InforceBlock

    ib: InforceBlock = block  # type: ignore[assignment]

    face_amounts = ib.face_amount_vec
    mean_face = float(face_amounts.mean())
    median_face = float(np.median(face_amounts))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Policies", f"{ib.n_policies:,}")
    col2.metric("Total Face Amount", f"${ib.total_face_amount():,.0f}")
    col3.metric("Mean Attained Age", f"{float(ib.attained_age_vec.mean()):.1f}")
    col4.metric(
        "Mean / Median Face",
        f"${mean_face:,.0f}",
        delta=f"Median ${median_face:,.0f}",
        delta_color="off",
    )

    # Sex and smoker splits
    n_male = int(ib.is_male_vec.sum())
    n_female = ib.n_policies - n_male
    n_smoker = int(ib.is_smoker_vec.sum())
    n_nonsmoker = ib.n_policies - n_smoker

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Male", f"{n_male:,}")
    c2.metric("Female", f"{n_female:,}")
    c3.metric("Smoker", f"{n_smoker:,}")
    c4.metric("Non-Smoker", f"{n_nonsmoker:,}")

    _age_gender_chart(ib)
    _face_amount_chart(ib)
    _duration_chart(ib)


def _age_gender_chart(block: object) -> None:
    """Horizontal grouped bar chart: age band x gender distribution."""
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]

    from polaris_re.core.inforce import InforceBlock

    ib: InforceBlock = block  # type: ignore[assignment]

    ages = ib.attained_age_vec
    is_male = ib.is_male_vec

    # Build band labels in order
    band_order = [f"{lo}-{lo + 4}" for lo in range(20, 70, 5)] + ["70+"]
    bands = np.array([_age_band(int(a)) for a in ages])

    male_counts = {b: 0 for b in band_order}
    female_counts = {b: 0 for b in band_order}
    for band, male in zip(bands, is_male, strict=False):
        if male:
            male_counts[band] = male_counts.get(band, 0) + 1
        else:
            female_counts[band] = female_counts.get(band, 0) + 1

    y_pos = np.arange(len(band_order))
    bar_height = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    m_vals = [male_counts[b] for b in band_order]
    f_vals = [female_counts[b] for b in band_order]
    ax.barh(y_pos - bar_height / 2, m_vals, bar_height, label="Male", color="#3498db")
    ax.barh(y_pos + bar_height / 2, f_vals, bar_height, label="Female", color="#e74c3c")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(band_order)
    ax.set_xlabel("Policy Count")
    ax.set_title("Age x Gender Distribution")
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _face_amount_chart(block: object) -> None:
    """Histogram of face amounts showing concentration risk."""
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]

    from polaris_re.core.inforce import InforceBlock

    ib: InforceBlock = block  # type: ignore[assignment]
    face_amounts = ib.face_amount_vec

    # Define face bands
    bands = [0, 100_000, 250_000, 500_000, 750_000, 1_000_000, 2_000_000, float("inf")]
    band_labels = ["<$100K", "$100-250K", "$250-500K", "$500-750K", "$750K-1M", "$1-2M", ">$2M"]
    counts = np.histogram(face_amounts, bins=bands)[0]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(band_labels, counts, color="#3498db", edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Face Amount Band")
    ax.set_ylabel("Policy Count")
    ax.set_title("Face Amount Distribution")
    for i, (cnt, _lbl) in enumerate(zip(counts, band_labels, strict=False)):
        if cnt > 0:
            ax.text(i, cnt + max(counts) * 0.02, str(cnt), ha="center", va="bottom", fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _duration_chart(block: object) -> None:
    """Histogram of policy years in-force (attained age - issue age)."""
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]

    from polaris_re.core.inforce import InforceBlock

    ib: InforceBlock = block  # type: ignore[assignment]

    durations = ib.attained_age_vec - ib.issue_age_vec
    mean_dur = float(durations.mean())
    median_dur = float(np.median(durations))

    fig, ax = plt.subplots(figsize=(8, 4))
    max_dur = int(durations.max()) + 1
    bins = np.arange(0, max_dur + 1) - 0.5
    ax.hist(durations, bins=bins, color="#9b59b6", edgecolor="white", linewidth=0.5, alpha=0.8)
    ax.axvline(
        mean_dur, color="#e74c3c", linestyle="--", linewidth=1.5, label=f"Mean: {mean_dur:.1f} yrs"
    )
    ax.axvline(
        median_dur,
        color="#2ecc71",
        linestyle=":",
        linewidth=1.5,
        label=f"Median: {median_dur:.1f} yrs",
    )
    ax.set_xlabel("Policy Years In-Force")
    ax.set_ylabel("Policy Count")
    ax.set_title("Policy Duration Distribution")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _upload_tab() -> None:
    """Upload File tab content."""
    from polaris_re.core.inforce import InforceBlock

    uploaded = st.file_uploader("Upload inforce CSV", type=["csv"])
    if uploaded is not None:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)

        try:
            block = InforceBlock.from_csv(tmp_path)
            st.session_state["inforce_block"] = block
            st.success(f"Loaded {block.n_policies:,} policies from {uploaded.name}")
        except Exception as exc:
            st.error(f"Failed to load inforce CSV: {exc}")

    # Only show reset button when a block is loaded
    if st.session_state.get("inforce_block") is not None and st.button("Reset Inforce Block"):
        st.session_state["inforce_block"] = None
        st.rerun()


def _synthetic_tab() -> None:
    """Generate Synthetic tab content."""
    from polaris_re.core.inforce import InforceBlock

    col1, col2 = st.columns(2)
    with col1:
        n_policies = int(st.slider("Number of Policies", min_value=10, max_value=10000, value=1000))
        mean_age = int(
            st.slider(
                "Mean Issue Age",
                min_value=30,
                max_value=60,
                value=40,
                help=(
                    "Controls the mean issue age of generated policies. "
                    "Attained age will be higher due to random policy durations "
                    "(typically 5\u201315 years older depending on term mix)."
                ),
            )
        )
        age_std = int(st.slider("Age Std Dev", min_value=5, max_value=15, value=8))
        male_pct = int(st.slider("Male %", min_value=0, max_value=100, value=60))
    with col2:
        smoker_pct = int(st.slider("Smoker %", min_value=0, max_value=100, value=15))
        face_median = int(
            st.slider(
                "Face Amount Median ($)",
                min_value=100_000,
                max_value=2_000_000,
                value=500_000,
                step=50_000,
            )
        )
        term_10 = int(st.slider("10yr Term Mix %", 0, 100, 20))
        term_20 = int(st.slider("20yr Term Mix %", 0, 100, 60))
        term_30 = 100 - term_10 - term_20

    st.subheader("Premium Calibration")
    pc1, pc2 = st.columns(2)
    with pc1:
        mortality_source = st.selectbox(
            "Mortality Table for Pricing",
            ["SOA_VBT_2015", "CIA_2014", "CSO_2001"],
            index=0,
            help="Premiums are calibrated to expected mortality from this table.",
        )
    with pc2:
        target_loss_ratio = st.slider(
            "Target Loss Ratio",
            min_value=0.30,
            max_value=0.90,
            value=0.60,
            step=0.05,
            format="%.2f",
            help=(
                "Ratio of expected claims to premiums. "
                "Lower = more profitable. 0.60 means 60% of premium covers expected claims."
            ),
        )

    if term_30 < 0:
        st.warning("Term mix exceeds 100%. Adjust 10yr and 20yr sliders.")
        return

    st.slider(
        f"30yr Term Mix % (auto-calculated: {term_30}%)",
        min_value=0,
        max_value=100,
        value=term_30,
        disabled=True,
        help=(
            "This value is automatically calculated as 100% minus "
            "the 10yr and 20yr term mix percentages. Adjust those "
            "sliders to change the 30yr allocation."
        ),
    )

    if st.button("Generate", type="primary"):
        # Import the generation function from scripts
        import sys

        scripts_dir = str(Path(__file__).resolve().parents[4] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from generate_synthetic_block import (
            generate_synthetic_block,  # type: ignore[import-not-found]
        )

        with st.spinner("Generating synthetic block..."):
            df = generate_synthetic_block(
                n_policies=n_policies,
                mean_age=mean_age,
                age_std=age_std,
                male_pct=male_pct,
                smoker_pct=smoker_pct,
                face_median=face_median,
                term_10_pct=term_10,
                term_20_pct=term_20,
                mortality_table_source=mortality_source,
                target_loss_ratio=target_loss_ratio,
            )

            # Write to temp CSV and load via InforceBlock.from_csv
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                df.write_csv(tmp.name)
                tmp_path = Path(tmp.name)

            block = InforceBlock.from_csv(tmp_path)
            st.session_state["inforce_block"] = block

        st.success(f"Generated {block.n_policies:,} synthetic policies")


def page_inforce() -> None:
    """Inforce Block page with Upload and Synthetic tabs."""
    st.header("Inforce Block")

    tab_upload, tab_synthetic = st.tabs(["Upload File", "Generate Synthetic"])

    with tab_upload:
        _upload_tab()

    with tab_synthetic:
        _synthetic_tab()

    # Show single persistent summary from session state
    block = st.session_state.get("inforce_block")
    if block is not None:
        st.divider()
        st.subheader("Current Inforce Block")
        _summary_panel(block)

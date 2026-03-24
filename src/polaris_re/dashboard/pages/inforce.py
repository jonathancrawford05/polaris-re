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
    """Display summary metrics and demographic chart for an InforceBlock."""
    from polaris_re.core.inforce import InforceBlock

    ib: InforceBlock = block  # type: ignore[assignment]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Policies", f"{ib.n_policies:,}")
    col2.metric("Total Face Amount", f"${ib.total_face_amount():,.0f}")
    col3.metric("Mean Attained Age", f"{float(ib.attained_age_vec.mean()):.1f}")

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
            _summary_panel(block)
        except Exception as exc:
            st.error(f"Failed to load inforce CSV: {exc}")

    if st.button("Reset to File"):
        st.session_state["inforce_block"] = None
        st.rerun()


def _synthetic_tab() -> None:
    """Generate Synthetic tab content."""
    from polaris_re.core.inforce import InforceBlock

    col1, col2 = st.columns(2)
    with col1:
        n_policies = int(st.slider("Number of Policies", min_value=10, max_value=10000, value=1000))
        _mean_age = int(st.slider("Mean Age", min_value=30, max_value=60, value=40))
        _age_std = int(st.slider("Age Std Dev", min_value=5, max_value=15, value=8))
        _male_pct = int(st.slider("Male %", min_value=0, max_value=100, value=60))
    with col2:
        _smoker_pct = int(st.slider("Smoker %", min_value=0, max_value=100, value=15))
        _face_median = int(
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

    if term_30 < 0:
        st.warning("Term mix exceeds 100%. Adjust 10yr and 20yr sliders.")
        return

    st.caption(f"30yr Term Mix: {term_30}%")

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
            df = generate_synthetic_block(n_policies=n_policies)

            # Write to temp CSV and load via InforceBlock.from_csv
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                df.write_csv(tmp.name)
                tmp_path = Path(tmp.name)

            block = InforceBlock.from_csv(tmp_path)
            st.session_state["inforce_block"] = block

        st.success(f"Generated {block.n_policies:,} synthetic policies")
        _summary_panel(block)


def page_inforce() -> None:
    """Inforce Block page with Upload and Synthetic tabs."""
    st.header("Inforce Block")

    tab_upload, tab_synthetic = st.tabs(["Upload File", "Generate Synthetic"])

    with tab_upload:
        _upload_tab()

    with tab_synthetic:
        _synthetic_tab()

    # Show existing block from session state if present
    block = st.session_state.get("inforce_block")
    if block is not None:
        st.divider()
        st.subheader("Current Inforce Block")
        _summary_panel(block)

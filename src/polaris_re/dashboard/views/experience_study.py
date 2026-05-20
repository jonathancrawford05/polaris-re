"""Page 8: Experience Study — Actual-to-Expected (A/E) analysis.

Surfaces ``polaris_re.analytics.experience_study.ExperienceStudy`` in the
Streamlit dashboard. Users either upload a CSV of observed experience or
load a built-in sample, configure the credibility threshold and grouping
dimensions, and view A/E ratios with credibility-weighted multipliers.

CSV schema (required columns):
    - ``actual``    (float): observed events in the row's cell
    - ``expected``  (float): expected events from the assumption table
    - ``exposure``  (float): risk exposure (policy-years, person-months, …)

Optional dimension columns (any name) become available as group-by
selections — typical examples: ``age``, ``sex``, ``smoker_status``,
``duration_band``, ``calendar_year``, ``product_type``.

The page is purely a presentation layer; all calculations are delegated to
``ExperienceStudy`` so the engine and the UI cannot drift.
"""

import io
from typing import Protocol

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np
import polars as pl
import streamlit as st  # type: ignore[import-untyped]
from matplotlib.figure import Figure  # type: ignore[import-untyped]

from polaris_re.analytics.experience_study import ExperienceStudy

__all__ = ["page_experience_study"]


REQUIRED_COLUMNS: set[str] = {"actual", "expected", "exposure"}


class _BytesUpload(Protocol):
    """Structural type for any object exposing Streamlit's ``UploadedFile.getvalue()``."""

    def getvalue(self) -> bytes: ...


def _read_uploaded_csv(uploaded: _BytesUpload) -> pl.DataFrame:
    """Parse an uploaded CSV's bytes into a Polars DataFrame.

    ``uploaded`` is a Streamlit ``UploadedFile``-like object exposing
    ``getvalue() -> bytes`` (anything quack-equivalent works in tests).
    """
    return pl.read_csv(io.BytesIO(uploaded.getvalue()))


def _sample_data() -> pl.DataFrame:
    """Built-in sample mortality experience for the demo path."""
    return pl.DataFrame(
        {
            "age": [35, 40, 45, 50, 55, 60, 65, 70],
            "sex": ["M", "M", "M", "F", "F", "M", "M", "F"],
            "actual": [12.0, 18.0, 24.0, 8.0, 14.0, 30.0, 45.0, 22.0],
            "expected": [10.0, 20.0, 25.0, 10.0, 12.0, 28.0, 50.0, 25.0],
            "exposure": [5_000.0, 6_000.0, 5_500.0, 4_000.0, 3_500.0, 4_500.0, 3_000.0, 2_000.0],
        }
    )


def _composite_group_labels(summary: pl.DataFrame, group_cols: list[str]) -> list[str]:
    """Build one x-axis label per summary row across all grouping dimensions.

    With a single dimension the label is that column's value. With multiple
    dimensions the per-row values are joined with ' / ' so every
    (dim_1, dim_2, ...) combination gets a distinct bar — otherwise repeated
    first-dimension values (e.g. several ages within one sex) would collapse
    onto the same x tick and overplot.
    """
    rows = summary.select(group_cols).rows()
    return [" / ".join(str(v) for v in row) for row in rows]


def _ae_bar_chart(summary: pl.DataFrame, group_cols: list[str]) -> Figure:
    """Bar chart of A/E ratio by group with a reference line at 1.0."""
    fig, ax = plt.subplots(figsize=(10, 4))
    labels = _composite_group_labels(summary, group_cols)
    x = np.arange(len(labels))
    ae = summary["ae_ratio"].to_numpy()
    bar_colors = ["#e74c3c" if val > 1.0 else "#2ecc71" for val in ae]
    ax.bar(x, ae, color=bar_colors, alpha=0.75)
    ax.axhline(1.0, color="#34495e", linestyle="--", linewidth=1.0, label="Expected (A/E = 1.0)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    axis_label = " / ".join(group_cols)
    ax.set_ylabel("A/E Ratio")
    ax.set_xlabel(axis_label)
    ax.set_title(f"Actual-to-Expected Ratio by {axis_label}")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    if len(labels) > 6:
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    return fig


def _multiplier_chart(summary: pl.DataFrame, group_cols: list[str]) -> Figure:
    """Side-by-side raw A/E vs credibility-adjusted multiplier."""
    fig, ax = plt.subplots(figsize=(10, 4))
    labels = _composite_group_labels(summary, group_cols)
    x = np.arange(len(labels))
    ae = summary["ae_ratio"].to_numpy()
    mult = summary["multiplier"].to_numpy()
    width = 0.38
    ax.bar(x - width / 2, ae, width, label="Raw A/E", color="#3498db", alpha=0.7)
    ax.bar(x + width / 2, mult, width, label="Credibility-Adjusted", color="#9b59b6", alpha=0.7)
    ax.axhline(1.0, color="#34495e", linestyle="--", linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    axis_label = " / ".join(group_cols)
    ax.set_ylabel("Ratio")
    ax.set_xlabel(axis_label)
    ax.set_title(f"Raw vs Credibility-Adjusted by {axis_label}")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    if len(labels) > 6:
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    return fig


def _format_summary_for_display(multipliers: pl.DataFrame) -> pl.DataFrame:
    """Round numeric columns for readable st.dataframe output."""
    rounding = {
        "actual": 2,
        "expected": 2,
        "exposure": 2,
        "ae_ratio": 4,
        "actual_rate": 6,
        "expected_rate": 6,
        "blended_rate": 6,
        "credibility": 4,
        "multiplier": 4,
    }
    cols_present = [pl.col(c).round(d) for c, d in rounding.items() if c in multipliers.columns]
    return multipliers.with_columns(cols_present) if cols_present else multipliers


def page_experience_study() -> None:
    """Experience Study page — A/E with credibility weighting."""
    st.header("Experience Study (A/E Analysis)")
    st.caption(
        "Actual-to-Expected analysis with limited-fluctuation credibility weighting. "
        "Upload a CSV with `actual`, `expected`, `exposure` columns plus optional "
        "grouping dimensions, or use the built-in sample to explore the page."
    )

    source = st.radio("Data source", ["Upload CSV", "Sample data"], horizontal=True)

    df: pl.DataFrame | None = None
    if source == "Upload CSV":
        uploaded = st.file_uploader("Experience CSV", type=["csv"])
        if uploaded is not None:
            try:
                df = _read_uploaded_csv(uploaded)
                st.success(f"Loaded {len(df):,} rows from {uploaded.name}")
            except Exception as exc:
                st.error(f"Failed to read CSV: {exc}")
                return
    else:
        df = _sample_data()
        st.info("Using built-in sample mortality data (8 rows by age x sex).")

    if df is None:
        st.caption("Upload a CSV above to begin, or switch to **Sample data**.")
        return

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        st.error(
            f"CSV is missing required columns: {sorted(missing)}. "
            f"Required schema: actual, expected, exposure."
        )
        return

    with st.expander("Preview data", expanded=False):
        st.dataframe(df.head(20).to_pandas(), use_container_width=True)

    # --- Configuration ---
    col1, col2, col3 = st.columns(3)
    with col1:
        study_type = st.selectbox(
            "Study Type",
            ["mortality", "lapse"],
            help="Selects the limited-fluctuation default; both produce identical math.",
        )
    with col2:
        n_full = float(
            st.number_input(
                "Full Credibility Threshold",
                min_value=10.0,
                max_value=10_000.0,
                value=1082.0,
                step=10.0,
                help=(
                    "Events for full credibility. Standard limited-fluctuation: "
                    "1082 (90% probability within ±5% for mortality)."
                ),
            )
        )
    with col3:
        candidate_dims = [c for c in df.columns if c not in REQUIRED_COLUMNS]
        group_by = st.multiselect(
            "Group By",
            options=candidate_dims,
            default=[],
            help="Leave empty for an overall A/E. Add one or more dimensions to drill down.",
        )

    # --- Optional age banding ---
    if "age" in df.columns:
        with st.expander("Age banding (optional)"):
            add_bands = st.checkbox(
                "Bin `age` into bands",
                value=False,
                help="Adds an `age_band` column and uses it as a grouping dimension.",
            )
            if add_bands:
                band_width = int(st.slider("Band width (years)", 1, 10, 5))
                df = ExperienceStudy.add_age_bands(df, age_col="age", band_width=band_width)
                if "age_band" not in group_by:
                    group_by = [*list(group_by), "age_band"]

    # --- Run the study ---
    try:
        study = ExperienceStudy(df, study_type=study_type, n_full_credibility=n_full)
        result = study.run(group_by=list(group_by) or None)
    except ValueError as exc:
        st.error(f"Validation error: {exc}")
        return

    # --- Overall metrics ---
    st.subheader("Overall")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Actual", f"{result.total_actual:,.1f}")
    m2.metric("Total Expected", f"{result.total_expected:,.1f}")
    overall_ae_str = f"{result.overall_ae:.3f}" if not np.isnan(result.overall_ae) else "N/A"
    m3.metric("Overall A/E", overall_ae_str)
    m4.metric("Overall Credibility", f"{result.overall_credibility:.2%}")

    if not np.isnan(result.overall_ae):
        if result.overall_ae > 1.05:
            st.warning(
                f"A/E = {result.overall_ae:.3f} is meaningfully worse than expected "
                f"(>5% adverse). Review assumption calibration."
            )
        elif result.overall_ae < 0.95:
            st.info(
                f"A/E = {result.overall_ae:.3f} is meaningfully better than expected "
                f"(>5% favourable)."
            )
        else:
            st.success(f"A/E = {result.overall_ae:.3f} is within ±5% of expected.")

    # --- Summary table with credibility-adjusted multiplier ---
    st.subheader("Summary by Group" if group_by else "Summary")
    multipliers = result.credibility_adjusted_multipliers()
    display_df = _format_summary_for_display(multipliers)
    st.dataframe(display_df.to_pandas(), use_container_width=True)

    # --- Visualisations ---
    group_cols = list(group_by)
    if group_cols and 1 < len(result.summary) <= 50:
        st.subheader("A/E Ratio by Group")
        fig_ae = _ae_bar_chart(multipliers, group_cols)
        st.pyplot(fig_ae)
        plt.close(fig_ae)

        st.subheader("Raw vs Credibility-Adjusted")
        fig_mult = _multiplier_chart(multipliers, group_cols)
        st.pyplot(fig_mult)
        plt.close(fig_mult)
    elif group_by and len(result.summary) > 50:
        st.caption(
            f"Suppressing chart: {len(result.summary)} groups exceeds the 50-row "
            f"display threshold. Inspect the table above or download the CSV."
        )

    # --- Download CSV ---
    csv_buffer = io.StringIO()
    multipliers.write_csv(csv_buffer)
    st.download_button(
        "Download Results CSV",
        data=csv_buffer.getvalue(),
        file_name="experience_study_results.csv",
        mime="text/csv",
    )

    # --- Methodology footnote ---
    st.caption(
        f"**Credibility (Z)** = min(1, sqrt(actual / {int(n_full)})). "
        "**Multiplier** = Z * A/E + (1 - Z). "
        "**Blended rate** = Z * actual_rate + (1 - Z) * expected_rate. "
        "Limited-fluctuation method (Klugman, Panjer, Willmot, *Loss Models*)."
    )

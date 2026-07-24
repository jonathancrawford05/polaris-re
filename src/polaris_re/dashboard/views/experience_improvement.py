"""Page 10: Mortality Improvement — experience-GAM diagnostics.

Surfaces the shipped experience-GAM / mortality-improvement capability (A4'
epic, ADR-139..154) in the Streamlit dashboard so a non-CLI pricing actuary can
inspect a fitted improvement surface interactively. This is Slice 1 of the MI
dashboard page (``docs/PLAN_mi_dashboard.md``): the **diagnostics** half
(carried-forward experience-GAM #89 / ADR-153). It is a pure presentation layer
over the shipped analytics — ``ExperienceGAM`` / ``TensorMIModel`` /
``BayesianTensorMIModel`` and the ``[viz]`` helpers in
``polaris_re.viz.experience_plots`` — and drives no pricing/engine behaviour, so
goldens are byte-identical.

The user either loads the built-in sample grouped-cell experience or uploads a
CSV in the canonical contract, then sees three diagnostics rendered straight
from the shipped data structures:

* **Fitted effects** — per-feature A/E multiplier shapes from
  ``ExperienceGAM.all_effects()`` (``plot_effects``).
* **MI surface slices + band-width** — the ``MI_x(y)`` improvement surface from
  ``TensorMIModel.improvement_surface()`` (``plot_mi_surface`` /
  ``plot_mi_surface_bandwidth``).
* **Forward projection fan** — the CMI/MP-style mean-reverting projection from
  the Bayesian ``BayesianTensorMIModel.project_improvement()``
  (``plot_mi_projection``), behind an explicit "run Bayesian (slow)" toggle so
  the interactive default stays the fast frequentist fit.

CSV schema (canonical grouped-cell contract, count basis):
    - ``attained_age``    (int):   attained age of the cell
    - ``calendar_year``   (int):   experience calendar year (>1 distinct value)
    - ``q_base``          (float): static select-and-ultimate base rate in (0, 1]
    - ``central_exposure``(float): policy-year exposure (count basis)
    - ``death_count``     (float): observed deaths (count basis)

For the ``amount`` basis, supply ``amount_exposed`` / ``death_amount`` instead of
the count pair. Optional canonical dimension columns (``sex``, ``smoker``,
``duration_months``, …) become GAM factors/smooths when present and varying.

The versioned improvement-scale selector wired into Deal Pricing (IMPORTANT #12 /
ADR-148, the #12 dashboard half) is Slice 2 of this feature and is intentionally
not shipped here — see the CONTINUATION.
"""

import io
from typing import Protocol

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np
import polars as pl
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.analytics.experience_gam import (
    AMOUNT_MEASURES,
    COUNT_MEASURES,
    ExperienceGAM,
    GAMFitResult,
    MISurface,
    TensorMIModel,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.viz.experience_plots import (
    plot_effects,
    plot_mi_projection,
    plot_mi_surface,
    plot_mi_surface_bandwidth,
)

__all__ = ["page_experience_improvement"]


# --- Sample data (pinned; no wall-clock dependence, ADR-074) --------------------

# A compact grid keeps the interactive/AppTest fit sub-second while still
# spanning enough ages and years for the tensor surface to be identified.
_SAMPLE_AGES: tuple[int, int] = (40, 65)
_SAMPLE_YEARS: tuple[int, int] = (2012, 2020)
_SAMPLE_MI: float = 0.015
"""Flat 1.5%/yr improvement baked into the sample so a fit recovers a clean,
interpretable surface."""


def _sample_q_base(age: int) -> float:
    """A smooth, increasing static base rate ``q_base(age)`` in (0, 1)."""
    return 0.004 * float(np.exp(0.08 * (age - 45.0)))


def _sample_cells() -> pl.DataFrame:
    """Built-in grouped-cell experience: ``q_base(age)·(1-mi)^(year-base)``.

    Deaths are the expected count under a flat 1.5%/yr improvement, so the
    diagnostics render a clean, recoverable surface on the demo path. All ages
    and years are pinned literals (ADR-074 — no ``date.today()``).
    """
    base_year = _SAMPLE_YEARS[0]
    ages = range(_SAMPLE_AGES[0], _SAMPLE_AGES[1] + 1)
    years = range(_SAMPLE_YEARS[0], _SAMPLE_YEARS[1] + 1)
    rows: list[tuple[int, int, float, float, float]] = []
    for a in ages:
        q0 = _sample_q_base(a)
        for y in years:
            actual_q = q0 * (1.0 - _SAMPLE_MI) ** (y - base_year)
            rows.append((a, y, q0, 2.0e6, 2.0e6 * actual_q))
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


class _BytesUpload(Protocol):
    """Structural type for any object exposing Streamlit's ``UploadedFile.getvalue()``."""

    def getvalue(self) -> bytes: ...


def _read_uploaded_csv(uploaded: _BytesUpload) -> pl.DataFrame:
    """Parse an uploaded CSV's bytes into a Polars DataFrame."""
    return pl.read_csv(io.BytesIO(uploaded.getvalue()))


def _missing_basis_columns(df: pl.DataFrame, basis: str) -> set[str]:
    """Required columns for ``basis`` that are absent from ``df``.

    Slice 1 requires the CSV to already carry a static ``q_base`` offset (the
    table-attach path is Slice 2 scope). Returns the missing set, empty when the
    frame is complete for the chosen basis.
    """
    exposure_col, deaths_col = COUNT_MEASURES if basis == "count" else AMOUNT_MEASURES
    required = {"attained_age", "calendar_year", "q_base", exposure_col, deaths_col}
    return required - set(df.columns)


def _fit_diagnostics(
    cells: pl.DataFrame,
    *,
    basis: str,
    age_df: int,
    year_df: int,
    age_varying: bool,
    confidence_level: float,
) -> tuple[GAMFitResult, MISurface]:
    """Fit the additive A/E GAM and the tensor MI surface, returning both results.

    Returns ``(gam_result, mi_surface)`` where ``gam_result`` is a
    ``GAMFitResult`` (for the effects panel) and ``mi_surface`` is an
    ``MISurface`` (for the surface/band-width panels). Both fits share the same
    grouped cells; nothing here changes pricing behaviour.
    """
    gam_result = ExperienceGAM(cells, basis=basis, age_df=age_df).fit()
    mi_result = TensorMIModel(
        cells,
        basis=basis,
        age_df=age_df,
        year_df=year_df,
        age_varying=age_varying,
    ).fit()
    surface = mi_result.improvement_surface(confidence_level=confidence_level)
    return gam_result, surface


def page_experience_improvement() -> None:
    """Mortality Improvement page — experience-GAM diagnostics (Slice 1)."""
    st.header("Mortality Improvement (Experience-GAM Diagnostics)")
    st.caption(
        "Inspect a fitted data-driven mortality-improvement surface (A4' epic). "
        "Load the built-in sample or upload a grouped-cell experience CSV with "
        "`attained_age`, `calendar_year`, `q_base`, and the exposure/deaths pair, "
        "then view the fitted effects, the `MI_x(y)` surface, and (optionally) a "
        "forward projection fan. This page is diagnostics only — it does not "
        "change any pricing output."
    )

    # --- Data source ---
    source = st.radio("Data source", ["Sample data", "Upload CSV"], horizontal=True)

    basis = st.selectbox(
        "Experience basis",
        ["count", "amount"],
        help="'count' uses central_exposure/death_count; 'amount' uses "
        "amount_exposed/death_amount (overdispersed → wider bands).",
    )

    cells: pl.DataFrame | None = None
    if source == "Sample data":
        cells = _sample_cells()
        st.info(
            f"Using built-in sample: ages {_SAMPLE_AGES[0]}-{_SAMPLE_AGES[1]} x "
            f"years {_SAMPLE_YEARS[0]}-{_SAMPLE_YEARS[1]}, flat "
            f"{_SAMPLE_MI:.1%}/yr improvement (count basis)."
        )
        if basis == "amount":
            st.warning(
                "The built-in sample carries the count basis only. Switch to "
                "'count', or upload an amount-basis CSV."
            )
            return
    else:
        uploaded = st.file_uploader("Experience CSV", type=["csv"])
        if uploaded is not None:
            try:
                cells = _read_uploaded_csv(uploaded)
                st.success(f"Loaded {len(cells):,} rows from {uploaded.name}")
            except Exception as exc:  # broad — surface any parse error to the UI
                st.error(f"Failed to read CSV: {exc}")
                return

    if cells is None:
        st.caption("Upload a CSV above to begin, or switch to **Sample data**.")
        return

    missing = _missing_basis_columns(cells, basis)
    if missing:
        st.error(
            f"CSV is missing required columns for the '{basis}' basis: "
            f"{sorted(missing)}. Slice 1 requires a pre-built `q_base` offset "
            f"column; the versioned-table attach path is a later slice."
        )
        return

    with st.expander("Preview data", expanded=False):
        st.dataframe(cells.head(20).to_pandas(), use_container_width=True)

    # --- Configuration ---
    col1, col2, col3 = st.columns(3)
    with col1:
        age_df = int(
            st.number_input(
                "Attained-age spline df",
                min_value=3,
                max_value=12,
                value=6,
                step=1,
                help="Degrees of freedom for the attained-age smooth.",
            )
        )
    with col2:
        year_df = int(
            st.number_input(
                "Calendar-year spline df",
                min_value=3,
                max_value=10,
                value=4,
                step=1,
                help="Degrees of freedom for the calendar-year (trend) smooth.",
            )
        )
    with col3:
        confidence_level = float(
            st.slider(
                "Confidence level",
                min_value=0.50,
                max_value=0.99,
                value=0.95,
                step=0.01,
                help="Two-sided confidence level for the reported bands.",
            )
        )

    age_varying = st.checkbox(
        "Age-varying improvement (age x calendar tensor)",
        value=True,
        help="Include the tensor interaction so improvement varies by age. "
        "Unset fits a separable age + calendar model (improvement constant "
        "across age).",
    )

    # --- Fit the frequentist diagnostics ---
    try:
        gam_result, surface = _fit_diagnostics(
            cells,
            basis=basis,
            age_df=age_df,
            year_df=year_df,
            age_varying=age_varying,
            confidence_level=confidence_level,
        )
    except PolarisValidationError as exc:
        st.error(f"Validation error: {exc}")
        return
    except PolarisComputationError as exc:
        st.error(
            f"Fit failed: {exc}. The experience-GAM diagnostics require the "
            f"optional `[ml]` extra (statsmodels); install with `uv sync --extra ml`."
        )
        return

    # --- Overall fit metrics ---
    st.subheader("Fit Summary")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Overall A/E", f"{gam_result.overall_ae:.4f}")
    m2.metric("Dispersion φ", f"{gam_result.dispersion:.3f}")
    m3.metric("Grouped cells", f"{gam_result.n_cells:,}")
    m4.metric(
        "Observed ages",
        f"{int(surface.ages.min())}-{int(surface.ages.max())}",
    )

    # --- Diagnostic 1: fitted effects ---
    st.subheader("Fitted Effects")
    st.caption(
        "Per-feature A/E multiplier shapes with confidence bands (`ExperienceGAM.all_effects()`)."
    )
    effects = gam_result.all_effects(confidence_level=confidence_level)
    if effects.height == 0:
        st.info("No smooth or factor effects to plot for this data.")
    else:
        fig_effects = plot_effects(
            effects, band_kind="confidence", confidence_level=confidence_level
        )
        st.pyplot(fig_effects)
        plt.close(fig_effects)

    # --- Diagnostic 2: MI surface slices ---
    st.subheader("Mortality-Improvement Surface")
    st.caption(
        "Annual improvement `MI_x(y)` sliced by age and by year, each with a "
        "confidence band (`TensorMIModel.improvement_surface()`)."
    )
    fig_surface = plot_mi_surface(surface, band_kind="confidence")
    st.pyplot(fig_surface)
    plt.close(fig_surface)

    # --- Diagnostic 3: band-width heatmap ---
    st.subheader("Surface Identification (Band Width)")
    st.caption(
        "Where the surface is well-identified (narrow band, dark) vs poorly "
        "identified (wide band, bright — typically the edges)."
    )
    fig_bw = plot_mi_surface_bandwidth(surface)
    st.pyplot(fig_bw)
    plt.close(fig_bw)

    # --- MI grid download (reuses the shipped surface) ---
    grid = pl.DataFrame(
        {
            "attained_age": np.repeat(surface.ages, len(surface.years)),
            "calendar_year": np.tile(surface.years, len(surface.ages)),
            "mi": surface.mi_grid.reshape(-1),
            "mi_lower": surface.mi_lower.reshape(-1),
            "mi_upper": surface.mi_upper.reshape(-1),
        }
    )
    grid_buffer = io.StringIO()
    grid.write_csv(grid_buffer)
    st.download_button(
        "Download MI surface grid (CSV)",
        data=grid_buffer.getvalue(),
        file_name="mi_surface_grid.csv",
        mime="text/csv",
    )

    # --- Diagnostic 4: Bayesian forward projection (slow path) ---
    st.subheader("Forward Projection (Bayesian)")
    st.caption(
        "CMI/MP-style projection that mean-reverts a fitted age's improvement to "
        "a long-term rate. The Bayesian reduced-rank-GP fit is slower, so it runs "
        "only on request."
    )
    run_bayesian = st.checkbox("Run Bayesian projection (slow)", value=False)
    if run_bayesian:
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            horizon = int(
                st.number_input(
                    "Projection horizon (years)",
                    min_value=1,
                    max_value=60,
                    value=25,
                    step=1,
                )
            )
        with pcol2:
            long_term_rate = float(
                st.number_input(
                    "Long-term improvement rate",
                    min_value=-0.05,
                    max_value=0.05,
                    value=0.01,
                    step=0.001,
                    format="%.3f",
                )
            )
        try:
            from polaris_re.analytics.experience_gam import BayesianTensorMIModel

            with st.spinner("Fitting Bayesian surface and projecting…"):
                bayes = BayesianTensorMIModel(cells, basis=basis, age_varying=age_varying).fit()
                projection = bayes.project_improvement(
                    horizon,
                    long_term_rate,
                    credible_level=confidence_level,
                )
            fig_proj = plot_mi_projection(projection, band_kind="posterior-predictive")
            st.pyplot(fig_proj)
            plt.close(fig_proj)
        except (PolarisValidationError, PolarisComputationError) as exc:
            st.error(f"Bayesian projection failed: {exc}")

    st.caption(
        "Diagnostics only. Slice 2 wires a versioned improvement basis into the "
        "Deal Pricing page (IMPORTANT #12 / ADR-148). See "
        "`docs/CONTINUATION_mi_dashboard.md`."
    )

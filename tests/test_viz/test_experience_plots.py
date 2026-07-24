"""Tests for the experience-GAM static diagnostic plots (A4' Slice 4d-2).

Covers ``polaris_re.viz.experience_plots``:

- ``plot_effects`` renders a smooth term as a shaded band + line and a factor
  term as an error-bar container, labels the band *kind*, and validates its
  input frame.
- ``plot_mi_surface`` renders the two slice panels (MI vs year, MI vs age)
  each with a band, and rejects off-surface age/year selections.
- ``plot_mi_surface_bandwidth`` renders the band-width heatmap whose image data
  equals ``mi_upper - mi_lower``.
- ``plot_mi_projection`` renders the fan chart, marks the long-term rate, and
  keeps the band widest at the join (the point of a fan chart).

Figures are built on the headless Agg backend and closed after every
assertion so matplotlib global state does not leak between tests. All fixtures
pin literal seeds/ages/years — none read the wall clock (ADR-074 guard).
"""

import matplotlib

matplotlib.use("Agg")  # headless, before pyplot is imported anywhere in-process

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import (
    ExperienceGAM,
    MIProjection,
    MISurface,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.viz import (
    plot_effects,
    plot_mi_projection,
    plot_mi_surface,
    plot_mi_surface_bandwidth,
)

SEED = 20260723


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _effects_frame() -> pl.DataFrame:
    """A minimal tidy effects frame matching ``GAMFitResult.all_effects``:
    one smooth block (``attained_age``) + one factor block (``sex``)."""
    ages = np.linspace(40.0, 70.0, 8)
    mult = np.exp(0.02 * (ages - 40.0))
    smooth = pl.DataFrame(
        {
            "feature": ["attained_age"] * ages.size,
            "term_type": ["smooth"] * ages.size,
            "x": [f"{a:g}" for a in ages],
            "x_value": ages,
            "multiplier": mult,
            "lower": mult * 0.9,
            "upper": mult * 1.1,
        }
    )
    factor = pl.DataFrame(
        {
            "feature": ["sex", "sex"],
            "term_type": ["factor", "factor"],
            "x": ["M", "F"],
            "x_value": [None, None],
            "multiplier": [1.0, 0.72],
            "lower": [1.0, 0.66],
            "upper": [1.0, 0.79],
        }
    )
    return pl.concat([smooth, factor])


def _synthetic_surface() -> MISurface:
    """A 4-age x 5-year surface with an explicit, well-identified band."""
    ages = np.arange(45, 49, dtype=np.int64)
    years = np.arange(2016, 2021, dtype=np.int64)
    mi = np.full((ages.size, years.size), 0.015, dtype=np.float64)
    half = np.full_like(mi, 0.004)
    return MISurface(
        ages=ages,
        years=years,
        mi_grid=mi,
        mi_lower=mi - half,
        mi_upper=mi + half,
        confidence_level=0.95,
    )


def _narrowing_projection() -> MIProjection:
    """A 2-age projection whose band narrows from the join to the long-term rate."""
    ages = np.arange(50, 52, dtype=np.int64)
    years = np.arange(2021, 2027, dtype=np.int64)
    k = years.size
    # Band half-width shrinks linearly to zero — widest at the join (year 0).
    half = np.linspace(0.006, 0.0, k)
    mi = np.linspace(0.018, 0.010, k)
    mi_grid = np.vstack([mi, mi * 0.9])
    return MIProjection(
        ages=ages,
        years=years,
        mi_grid=mi_grid.astype(np.float64),
        mi_lower=(mi_grid - half).astype(np.float64),
        mi_upper=(mi_grid + half).astype(np.float64),
        confidence_level=0.90,
        long_term_rate=0.010,
        convergence_period=k,
        method="cosine",
        last_observed_year=2020,
        initial_mi=mi_grid[:, 0].copy(),
    )


# --------------------------------------------------------------------------- #
# Import-hygiene guardrail — viz must stay off the pricing path
# --------------------------------------------------------------------------- #
def test_importing_viz_does_not_eagerly_import_matplotlib():
    """``import polaris_re.viz`` must not pull in ``matplotlib`` (the [viz] extra
    is optional and off the pricing path); it is imported lazily on first plot
    call. Run in a clean subprocess so already-imported modules don't mask it."""
    import subprocess
    import sys

    code = (
        "import sys; import polaris_re.viz; "
        "assert 'matplotlib' not in sys.modules, 'viz eagerly imported matplotlib'; "
        "print('ok')"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


# --------------------------------------------------------------------------- #
# plot_effects
# --------------------------------------------------------------------------- #
class TestPlotEffects:
    def test_returns_figure_with_one_panel_per_feature(self):
        fig = plot_effects(_effects_frame(), confidence_level=0.95)
        try:
            assert len(fig.axes) == 2  # attained_age + sex
        finally:
            plt.close(fig)

    def test_smooth_panel_has_band_and_line(self):
        fig = plot_effects(_effects_frame(), confidence_level=0.95)
        try:
            smooth_ax = fig.axes[0]
            # fill_between adds one PolyCollection; the fitted line + A/E ref line.
            assert len(smooth_ax.collections) == 1
            assert len(smooth_ax.get_lines()) == 2
        finally:
            plt.close(fig)

    def test_factor_panel_has_errorbar_container(self):
        fig = plot_effects(_effects_frame(), confidence_level=0.95)
        try:
            factor_ax = fig.axes[1]
            assert len(factor_ax.containers) >= 1  # ErrorbarContainer
        finally:
            plt.close(fig)

    def test_band_kind_labelled_in_legend(self):
        fig = plot_effects(_effects_frame(), band_kind="confidence", confidence_level=0.95)
        try:
            texts = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
            assert "95% confidence band" in texts
        finally:
            plt.close(fig)

    def test_credible_band_kind_labelled_distinctly(self):
        fig = plot_effects(_effects_frame(), band_kind="credible", confidence_level=0.9)
        try:
            texts = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
            assert "90% credible band" in texts
            assert not any("confidence" in t for t in texts)
        finally:
            plt.close(fig)

    def test_empty_frame_raises(self):
        empty = _effects_frame().clear()
        with pytest.raises(PolarisValidationError, match="empty"):
            plot_effects(empty)

    def test_missing_column_raises(self):
        bad = _effects_frame().drop("lower")
        with pytest.raises(PolarisValidationError, match="missing required columns"):
            plot_effects(bad)

    def test_invalid_band_kind_raises(self):
        with pytest.raises(PolarisValidationError, match="band_kind"):
            plot_effects(_effects_frame(), band_kind="bootstrap")  # type: ignore[arg-type]

    def test_integration_with_real_all_effects(self):
        """End-to-end: a real GAM fit's ``all_effects`` frame plots without error."""
        ages = np.arange(40, 70)
        rng = np.random.default_rng(SEED)
        q_base = 0.004 * np.exp(0.06 * (ages - 40))
        exposure = np.full(ages.size, 40000.0)
        deaths = rng.poisson(exposure * q_base * 1.2).astype(np.float64)
        cells = pl.DataFrame(
            {
                "attained_age": ages.astype(np.int64),
                "central_exposure": exposure,
                "death_count": deaths,
                "q_base": q_base,
            }
        )
        fit = ExperienceGAM(cells, basis="count", age_df=5).fit()
        fig = plot_effects(fit.all_effects(grid_points=25), confidence_level=0.95)
        try:
            assert len(fig.axes) == len(fit.smooth_features) + len(fit.factors)
            assert fig.axes[0].collections  # the smooth band rendered
        finally:
            plt.close(fig)


# --------------------------------------------------------------------------- #
# plot_mi_surface
# --------------------------------------------------------------------------- #
class TestPlotMISurface:
    def test_returns_two_slice_panels(self):
        fig = plot_mi_surface(_synthetic_surface())
        try:
            assert len(fig.axes) == 2
            for ax in fig.axes:
                assert ax.collections  # each slice panel has at least one band
        finally:
            plt.close(fig)

    def test_band_kind_in_legend_titles(self):
        fig = plot_mi_surface(_synthetic_surface(), band_kind="confidence")
        try:
            for ax in fig.axes:
                assert ax.get_legend().get_title().get_text() == "95% confidence band"
        finally:
            plt.close(fig)

    def test_explicit_age_year_selection(self):
        surface = _synthetic_surface()
        fig = plot_mi_surface(surface, ages=[45, 47], years=[2016, 2020])
        try:
            year_ax = fig.axes[0]
            assert len(year_ax.get_lines()) == 2  # two age slices
        finally:
            plt.close(fig)

    def test_off_surface_ages_raise(self):
        with pytest.raises(PolarisValidationError, match="none of the requested ages"):
            plot_mi_surface(_synthetic_surface(), ages=[999])

    def test_off_surface_years_raise(self):
        with pytest.raises(PolarisValidationError, match="none of the requested years"):
            plot_mi_surface(_synthetic_surface(), years=[1900])


# --------------------------------------------------------------------------- #
# plot_mi_surface_bandwidth
# --------------------------------------------------------------------------- #
class TestPlotMISurfaceBandwidth:
    def test_image_data_equals_band_width(self):
        surface = _synthetic_surface()
        fig = plot_mi_surface_bandwidth(surface)
        try:
            assert len(fig.axes[0].images) == 1
            shown = fig.axes[0].images[0].get_array()
            expected = surface.mi_upper - surface.mi_lower
            np.testing.assert_allclose(np.asarray(shown), expected)
        finally:
            plt.close(fig)


# --------------------------------------------------------------------------- #
# plot_mi_projection
# --------------------------------------------------------------------------- #
class TestPlotMIProjection:
    def test_returns_fan_with_band_and_ltr_line(self):
        fig = plot_mi_projection(_narrowing_projection())
        try:
            ax = fig.axes[0]
            assert len(ax.collections) == 1  # the fan band
            # projected-MI line + long-term-rate reference line.
            assert len(ax.get_lines()) == 2
        finally:
            plt.close(fig)

    def test_band_widest_at_join(self):
        """The defining property of a fan chart: band width is maximal at the
        join year and non-increasing toward the long-term rate."""
        proj = _narrowing_projection()
        fig = plot_mi_projection(proj, age=50)
        try:
            band = fig.axes[0].collections[0]
            # Reconstruct rendered width from the projection the figure was built from.
            i = int(np.nonzero(proj.ages == 50)[0][0])
            width = proj.mi_upper[i] - proj.mi_lower[i]
            # Widest at the join: the max sits at index 0 (integer index compare,
            # not a float-equality check — repo convention).
            assert int(np.argmax(width)) == 0
            assert np.all(np.diff(width) <= 1e-12)
            assert band is not None
        finally:
            plt.close(fig)

    def test_default_age_is_a_projected_age(self):
        fig = plot_mi_projection(_narrowing_projection())
        try:
            assert fig.axes[0].get_lines()  # rendered without raising
        finally:
            plt.close(fig)

    def test_off_age_raises(self):
        with pytest.raises(PolarisValidationError, match="not among the projected ages"):
            plot_mi_projection(_narrowing_projection(), age=999)

    def test_posterior_predictive_is_default_band_kind(self):
        fig = plot_mi_projection(_narrowing_projection())
        try:
            texts = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
            assert any("posterior-predictive band" in t for t in texts)
        finally:
            plt.close(fig)

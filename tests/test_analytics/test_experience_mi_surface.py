"""
Tests for the Slice-2a tensor mortality-improvement (MI) surface.

Covers the Slice-2a acceptance criteria from docs/PLAN_experience_gam.md
(the frequentist, CI-lean de-risking of the HEADLINE tensor surface):
- recover a known constant age x year improvement from synthetic data (exact)
- recover an age-varying improvement gradient (young improves faster than old)
- no calendar trend => recovered MI is ~0
- Design-Anchor-3 identifiability: the separable (non-tensor) model attributes a
  single trend across age; the tensor model resolves the age gradient
- optional ``underwriting_era`` factor enters the model
- static-vs-generational base guard (Anchor 1) rejects a calendar-varying q_base,
  with an explicit override
- delta-method confidence band brackets the truth and widens as data thins
- contract validation (missing columns, single calendar year, no cell spanning
  multiple years) and the [ml]-absent import guard

The recovery tests use *deterministic* expected deaths (deaths == exposure * q),
so the GLM recovers the generating surface to machine precision — a closed-form
verification. Band tests use seeded Poisson draws. No test depends on the wall
clock (ADR-074 guard).
"""

import sys

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import (
    MISurface,
    MISurfaceResult,
    TensorMIModel,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

SEED = 20260722

# Deterministic recovery gives a perfect GLM fit; statsmodels flags that as
# perfect separation. It is expected here and does not indicate a problem.
pytestmark = pytest.mark.filterwarnings(
    "ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning"
)


# --------------------------------------------------------------------------- #
# Synthetic data helpers
# --------------------------------------------------------------------------- #


def _q_base(age: np.ndarray) -> np.ndarray:
    """A smooth, increasing static base rate q_base(age) in (0, 1)."""
    return 0.004 * np.exp(0.08 * (np.asarray(age, dtype=np.float64) - 45.0))


def _mi_cells(
    ages: np.ndarray,
    years: np.ndarray,
    mi_fn,
    *,
    exposure: float = 2.0e6,
    generational_drift: float | None = None,
) -> pl.DataFrame:
    """
    Build grouped cells over an age x calendar-year grid where the *actual*
    mortality is ``q_base(age) * (1 - mi_fn(age))^(year - base_year)`` — a constant
    (per-age) annual improvement. Deaths are set to the expected count so the fit
    recovers the surface exactly.

    If ``generational_drift`` is given, the ``q_base`` *offset column* is made to
    drift with calendar year (a generational base) to exercise Anchor-1's guard.
    """
    base = int(years.min())
    rows = []
    for a in ages:
        q0 = float(_q_base(np.array([a]))[0])
        mi = float(mi_fn(a))
        for y in years:
            actual_q = q0 * (1.0 - mi) ** (int(y) - base)
            expected_deaths = exposure * actual_q
            if generational_drift is not None:
                q_col = q0 * (1.0 + generational_drift) ** (int(y) - base)
            else:
                q_col = q0
            rows.append((int(a), int(y), q_col, exposure, expected_deaths))
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


def _mi_cells_poisson(
    ages: np.ndarray,
    years: np.ndarray,
    mi: float,
    *,
    exposure: float,
    seed: int,
) -> pl.DataFrame:
    """Grouped cells with Poisson-sampled deaths at a constant improvement ``mi``."""
    rng = np.random.default_rng(seed)
    base = int(years.min())
    rows = []
    for a in ages:
        q0 = float(_q_base(np.array([a]))[0])
        for y in years:
            lam = exposure * q0 * (1.0 - mi) ** (int(y) - base)
            rows.append((int(a), int(y), q0, exposure, float(rng.poisson(lam))))
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


_AGES = np.arange(40, 71)
_YEARS = np.arange(2005, 2021)
# Interior slices avoid B-spline boundary wiggle when asserting on recovered values.
_INT_AGE = slice(5, 25)
_INT_YEAR = slice(2, 12)


# --------------------------------------------------------------------------- #
# Surface recovery (closed-form verification)
# --------------------------------------------------------------------------- #


def test_constant_improvement_recovered_exactly():
    """A flat 1.5%/yr improvement is recovered to machine precision everywhere."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    surface = TensorMIModel(cells, age_df=6, year_df=4, age_varying=True).fit()
    mi = surface.improvement_surface()
    assert mi.mi_grid.shape == (len(_AGES), len(_YEARS) - 1)
    np.testing.assert_allclose(mi.mi_grid[_INT_AGE, _INT_YEAR], 0.015, atol=1e-6)


def test_age_varying_improvement_gradient_recovered():
    """Young ages improve faster than old — the tensor recovers the gradient."""

    def mi_fn(a: float) -> float:
        return 0.020 - 0.0003 * (a - 45.0)

    cells = _mi_cells(_AGES, _YEARS, mi_fn)
    surface = TensorMIModel(cells, age_df=6, year_df=4, age_varying=True).fit()
    mi = surface.improvement_surface()
    frame = mi.to_frame()

    for age in (48, 56, 64):
        row_mask = frame["attained_age"] == age
        recovered = frame.filter(row_mask)["mi"].to_numpy()
        # Interior years only.
        np.testing.assert_allclose(recovered[2:12].mean(), mi_fn(age), atol=5e-4)

    ai_young = list(_AGES).index(48)
    ai_old = list(_AGES).index(64)
    assert mi.mi_grid[ai_young, _INT_YEAR].mean() > mi.mi_grid[ai_old, _INT_YEAR].mean()


def test_no_calendar_trend_gives_zero_improvement():
    """With no secular trend the recovered MI surface is ~0."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.0)
    surface = TensorMIModel(cells, age_df=6, year_df=4, age_varying=True).fit()
    mi = surface.improvement_surface()
    assert np.abs(mi.mi_grid[_INT_AGE, _INT_YEAR]).max() < 1e-7


def test_separable_model_flattens_age_gradient():
    """
    Design-Anchor-3 attribution check: the separable (non-tensor) model carries a
    single calendar trend shared across age, so it cannot resolve an age-varying
    improvement — its recovered MI is flat across age. The tensor model does.
    """

    def mi_fn(a: float) -> float:
        return 0.020 - 0.0003 * (a - 45.0)

    cells = _mi_cells(_AGES, _YEARS, mi_fn)
    separable = TensorMIModel(cells, age_df=6, year_df=4, age_varying=False).fit()
    tensor = TensorMIModel(cells, age_df=6, year_df=4, age_varying=True).fit()
    sep = separable.improvement_surface().mi_grid
    ten = tensor.improvement_surface().mi_grid

    ai_young = list(_AGES).index(48)
    ai_old = list(_AGES).index(64)
    sep_spread = sep[ai_young, _INT_YEAR].mean() - sep[ai_old, _INT_YEAR].mean()
    ten_spread = ten[ai_young, _INT_YEAR].mean() - ten[ai_old, _INT_YEAR].mean()
    assert abs(sep_spread) < 1e-4  # separable => no age gradient
    np.testing.assert_allclose(ten_spread, mi_fn(48) - mi_fn(64), atol=5e-4)


def test_underwriting_era_enters_as_factor():
    """The Anchor-3 escape hatch: an optional underwriting_era column enters the
    model as an ordinary factor (a cohort shift attributed off the trend)."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    era = np.where(cells["calendar_year"].to_numpy() < 2013, "pre2013", "post2013")
    cells = cells.with_columns(pl.Series("underwriting_era", era))
    result = TensorMIModel(cells, age_df=6, year_df=4).fit()
    assert "underwriting_era" in result.factors


# --------------------------------------------------------------------------- #
# Anchor-1 static-base guard
# --------------------------------------------------------------------------- #


def test_generational_base_offset_rejected():
    """A calendar-drifting q_base offset is rejected (Anchor 1)."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015, generational_drift=-0.01)
    with pytest.raises(PolarisValidationError, match="generational"):
        TensorMIModel(cells)


def test_generational_base_override_allows_fit():
    """allow_generational_base=True bypasses the static guard."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015, generational_drift=-0.01)
    result = TensorMIModel(cells, allow_generational_base=True).fit()
    assert isinstance(result, MISurfaceResult)


def test_no_cell_spans_multiple_years_rejected():
    """Diagonal cohort data (each covariate cell at one calendar year) cannot
    identify the trend and is rejected with an actionable message."""
    cells = pl.DataFrame(
        {
            "attained_age": [50, 51, 52, 53],
            "calendar_year": [2010, 2011, 2012, 2013],
            "duration_months": [120, 120, 120, 120],
            "q_base": [0.010, 0.011, 0.012, 0.013],
            "central_exposure": [1e5, 1e5, 1e5, 1e5],
            "death_count": [1000.0, 1000.0, 1000.0, 1000.0],
        }
    )
    with pytest.raises(PolarisValidationError, match="multiple calendar years"):
        TensorMIModel(cells)


# --------------------------------------------------------------------------- #
# Uncertainty band (delta method)
# --------------------------------------------------------------------------- #


def test_band_brackets_truth_and_widens_as_data_thins():
    """The 95% delta-method band covers the true MI and widens with less exposure."""
    big = _mi_cells_poisson(_AGES, _YEARS, 0.015, exposure=5e5, seed=SEED)
    small = _mi_cells_poisson(_AGES, _YEARS, 0.015, exposure=5e4, seed=SEED)
    surf_big = TensorMIModel(big, age_df=6, year_df=4).fit().improvement_surface()
    surf_small = TensorMIModel(small, age_df=6, year_df=4).fit().improvement_surface()

    covered = (surf_big.mi_lower <= 0.015) & (surf_big.mi_upper >= 0.015)
    assert covered[_INT_AGE, _INT_YEAR].mean() >= 0.9

    width_big = (surf_big.mi_upper - surf_big.mi_lower)[_INT_AGE, _INT_YEAR].mean()
    width_small = (surf_small.mi_upper - surf_small.mi_lower)[_INT_AGE, _INT_YEAR].mean()
    assert width_small > width_big
    # Lower confidence widens the band monotonically.
    surf_80 = (
        TensorMIModel(big, age_df=6, year_df=4).fit().improvement_surface(confidence_level=0.80)
    )
    width_80 = (surf_80.mi_upper - surf_80.mi_lower)[_INT_AGE, _INT_YEAR].mean()
    assert width_80 < width_big


def test_to_frame_shape_and_columns():
    """MISurface.to_frame yields one long-format row per (age, step-end-year)."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    surface = TensorMIModel(cells, age_df=6, year_df=4).fit().improvement_surface()
    frame = surface.to_frame()
    assert frame.height == len(surface.ages) * len(surface.years)
    assert set(frame.columns) == {"attained_age", "calendar_year", "mi", "mi_lower", "mi_upper"}
    assert isinstance(surface, MISurface)


# --------------------------------------------------------------------------- #
# Contract validation
# --------------------------------------------------------------------------- #


def test_requires_multiple_calendar_years():
    cells = _mi_cells(_AGES, np.array([2010]), lambda a: 0.015)
    with pytest.raises(PolarisValidationError, match="distinct calendar_year"):
        TensorMIModel(cells)


def test_missing_required_columns_raise():
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015).drop("q_base")
    with pytest.raises(PolarisValidationError, match="missing required columns"):
        TensorMIModel(cells)


def test_improvement_surface_needs_two_years():
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    result = TensorMIModel(cells, age_df=6, year_df=4).fit()
    with pytest.raises(PolarisValidationError, match="two calendar years"):
        result.improvement_surface(years=np.array([2010]))


def test_bad_basis_rejected():
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    with pytest.raises(PolarisValidationError, match="basis must be"):
        TensorMIModel(cells, basis="face")


def test_import_guard_when_statsmodels_absent(monkeypatch):
    """With statsmodels unavailable, fit raises an actionable PolarisComputationError."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    model = TensorMIModel(cells)
    monkeypatch.setitem(sys.modules, "statsmodels", None)
    monkeypatch.setitem(sys.modules, "statsmodels.api", None)
    with pytest.raises(PolarisComputationError, match="statsmodels"):
        model.fit()

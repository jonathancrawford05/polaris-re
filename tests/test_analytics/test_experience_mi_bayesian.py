"""
Tests for the Slice-2b Bayesian reduced-rank-GP mortality-improvement surface.

Covers the Slice-2b (surface sub-slice) acceptance criteria from
docs/PLAN_experience_gam.md and docs/CONTINUATION_experience_gam.md — the honest
posterior-credible-interval upgrade of the Slice-2a frequentist tensor surface:

- recover a known constant age x year improvement from synthetic data (closed form)
- recover an age-varying improvement gradient (young improves faster than old)
- no calendar trend => recovered MI is ~0
- separable model attributes one trend across age; the tensor resolves the gradient
  (Design-Anchor-3 identifiability, mirroring the frequentist model)
- optional ``underwriting_era`` factor enters the model
- Anchor-1 static-vs-generational base guard (reject + explicit override)
- posterior credible band brackets the truth, widens as exposure thins, and widens
  with a higher credible level
- the fit is deterministic (bit-identical on re-run) and matches the Slice-2a
  frequentist grid within tolerance on the same data
- by-amount overdispersion widens the band
- contract validation (missing columns, single calendar year, no cell spanning
  multiple years, invalid config) and a valid :class:`MISurface` is returned

The recovery tests use *deterministic* expected deaths (deaths == exposure * q),
so the penalised-GLM fit recovers the generating surface closely — a closed-form
verification. Band tests use seeded Poisson draws. No test depends on the wall
clock (ADR-074 guard). Unlike the Slice-2a suite this model is pure NumPy/SciPy —
no statsmodels / [ml] extra — so there is no import guard to exercise here.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import (
    BayesianMISurfaceResult,
    BayesianTensorMIModel,
    MISurface,
    TensorMIModel,
)
from polaris_re.core.exceptions import PolarisValidationError

SEED = 20260722

# The frequentist cross-check fits a TensorMIModel on deterministic (noiseless)
# deaths, which statsmodels flags as perfect separation. It is expected here.
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
    extra: dict | None = None,
) -> pl.DataFrame:
    """
    Grouped cells over an age x calendar-year grid where the *actual* mortality is
    ``q_base(age) * (1 - mi_fn(age))^(year - base_year)``. Deaths are set to the
    expected count so the fit recovers the surface (closed-form verification).

    ``generational_drift`` makes the ``q_base`` offset column drift with calendar
    year (a generational base) to exercise Anchor-1's guard.
    """
    base = int(years.min())
    rows = []
    for a in ages:
        q0 = float(_q_base(np.array([a]))[0])
        mi = float(mi_fn(a))
        for y in years:
            actual_q = q0 * (1.0 - mi) ** (int(y) - base)
            expected_deaths = exposure * actual_q
            q_col = q0 * (1.0 + generational_drift) ** (int(y) - base) if generational_drift else q0
            row = {
                "attained_age": int(a),
                "calendar_year": int(y),
                "q_base": q_col,
                "central_exposure": exposure,
                "death_count": expected_deaths,
            }
            if extra:
                row.update(extra)
            rows.append(row)
    return pl.DataFrame(rows)


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
            rows.append(
                {
                    "attained_age": int(a),
                    "calendar_year": int(y),
                    "q_base": q0,
                    "central_exposure": exposure,
                    "death_count": float(rng.poisson(lam)),
                }
            )
    return pl.DataFrame(rows)


_AGES = np.arange(40, 71)
_YEARS = np.arange(2005, 2021)
# Interior slices avoid GP boundary effects when asserting on recovered values.
_INT_AGE = slice(5, 25)
_INT_YEAR = slice(2, 12)


# --------------------------------------------------------------------------- #
# Surface recovery (closed-form verification)
# --------------------------------------------------------------------------- #


def test_constant_improvement_recovered():
    """A flat 1.5%/yr improvement is recovered across the interior grid."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    result = BayesianTensorMIModel(cells).fit()
    assert isinstance(result, BayesianMISurfaceResult)
    surface = result.improvement_surface()
    assert isinstance(surface, MISurface)
    assert surface.mi_grid.shape == (len(_AGES), len(_YEARS) - 1)
    np.testing.assert_allclose(surface.mi_grid[_INT_AGE, _INT_YEAR], 0.015, atol=1.5e-3)


def test_age_varying_improvement_gradient_recovered():
    """Young ages improve faster than old — the tensor recovers the gradient."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.03 - 0.0006 * (a - 40))
    surface = BayesianTensorMIModel(cells, age_varying=True).fit().improvement_surface()
    ages = surface.ages.tolist()
    mi_young = surface.mi_grid[ages.index(48), _INT_YEAR].mean()
    mi_old = surface.mi_grid[ages.index(62), _INT_YEAR].mean()
    assert mi_young > mi_old
    # true improvement at 48 is 0.0252, at 62 is 0.0168
    assert abs(mi_young - 0.0252) < 3e-3
    assert abs(mi_old - 0.0168) < 3e-3


def test_no_trend_gives_zero_improvement():
    """Flat mortality (no calendar trend) => recovered MI ~ 0 on the interior."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.0)
    surface = BayesianTensorMIModel(cells).fit().improvement_surface()
    np.testing.assert_allclose(surface.mi_grid[_INT_AGE, _INT_YEAR], 0.0, atol=1.5e-3)


def test_separable_model_flattens_age_gradient():
    """
    The separable (age_varying=False) model attributes a single trend across age,
    so its MI is (near) constant across age; the tensor model resolves the
    age gradient. This mirrors the Slice-2a Design-Anchor-3 attribution test.
    """
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.03 - 0.0006 * (a - 40))
    sep = BayesianTensorMIModel(cells, age_varying=False).fit().improvement_surface()
    ten = BayesianTensorMIModel(cells, age_varying=True).fit().improvement_surface()
    ages = sep.ages.tolist()

    def spread(surface):
        young = surface.mi_grid[ages.index(48), _INT_YEAR].mean()
        old = surface.mi_grid[ages.index(62), _INT_YEAR].mean()
        return young - old

    # Separable: no age x year term => MI identical across age (to machine eps).
    assert abs(spread(sep)) < 1e-9
    # Tensor: resolves a real, positive young-minus-old gradient.
    assert spread(ten) > 5e-3


def test_underwriting_era_factor_enters():
    """A varying ``underwriting_era`` column is picked up as a model factor."""
    cells_a = _mi_cells(_AGES, _YEARS, lambda a: 0.015, extra={"underwriting_era": "pre2010"})
    cells_b = _mi_cells(_AGES, _YEARS, lambda a: 0.015, extra={"underwriting_era": "post2010"})
    cells = pl.concat([cells_a, cells_b])
    result = BayesianTensorMIModel(cells).fit()
    assert "underwriting_era" in result.factors


# --------------------------------------------------------------------------- #
# Posterior credible band
# --------------------------------------------------------------------------- #


def test_credible_band_brackets_truth():
    """The 95% posterior credible band covers the true improvement on most steps."""
    cells = _mi_cells_poisson(_AGES, _YEARS, 0.015, exposure=5.0e4, seed=SEED)
    surface = BayesianTensorMIModel(cells).fit().improvement_surface(credible_level=0.95)
    inside = (surface.mi_lower <= 0.015) & (surface.mi_upper >= 0.015)
    # A calibrated 95% band should cover the truth on the large majority of cells.
    assert inside.mean() > 0.9
    assert np.all(surface.mi_upper >= surface.mi_lower)


def test_credible_band_widens_as_exposure_thins():
    """Thinner experience => a wider posterior credible band (more uncertainty)."""
    thick = _mi_cells_poisson(_AGES, _YEARS, 0.015, exposure=5.0e5, seed=SEED)
    thin = _mi_cells_poisson(_AGES, _YEARS, 0.015, exposure=2.0e4, seed=SEED)
    w_thick = BayesianTensorMIModel(thick).fit().improvement_surface()
    w_thin = BayesianTensorMIModel(thin).fit().improvement_surface()
    width_thick = (w_thick.mi_upper - w_thick.mi_lower)[_INT_AGE, _INT_YEAR].mean()
    width_thin = (w_thin.mi_upper - w_thin.mi_lower)[_INT_AGE, _INT_YEAR].mean()
    assert width_thin > width_thick


def test_credible_band_widens_with_confidence_level():
    """A 99% band is strictly wider than a 90% band from the same fit."""
    cells = _mi_cells_poisson(_AGES, _YEARS, 0.015, exposure=5.0e4, seed=SEED)
    result = BayesianTensorMIModel(cells).fit()
    band90 = result.improvement_surface(credible_level=0.90)
    band99 = result.improvement_surface(credible_level=0.99)
    w90 = (band90.mi_upper - band90.mi_lower)[_INT_AGE, _INT_YEAR]
    w99 = (band99.mi_upper - band99.mi_lower)[_INT_AGE, _INT_YEAR]
    assert np.all(w99 > w90)


@pytest.mark.parametrize("exposure", [3.0e4, 1.0e5, 4.0e5])
def test_by_amount_overdispersion_widens_band(exposure):
    """
    The by-amount basis (overdispersed) applies quasi-Poisson dispersion, so its
    posterior band is at least as wide as the by-count band on the same cells.
    """
    rng = np.random.default_rng(SEED)
    base = int(_YEARS.min())
    rows = []
    for a in _AGES:
        q0 = float(_q_base(np.array([a]))[0])
        for y in _YEARS:
            lam = exposure * q0 * (1.0 - 0.015) ** (int(y) - base)
            n = float(rng.poisson(lam))
            # amounts: a few large claims inflate the by-amount variance
            amt = n * float(rng.uniform(5.0e4, 2.0e5))
            rows.append(
                {
                    "attained_age": int(a),
                    "calendar_year": int(y),
                    "q_base": q0,
                    "central_exposure": exposure,
                    "death_count": n,
                    "amount_exposed": exposure * 1.0e5,
                    "death_amount": amt,
                }
            )
    cells = pl.DataFrame(rows)
    count_res = BayesianTensorMIModel(cells, basis="count").fit()
    amount_res = BayesianTensorMIModel(cells, basis="amount").fit()
    assert count_res.overdispersion_applied is False
    assert amount_res.overdispersion_applied is True
    assert amount_res.dispersion > 1.0
    w_count = count_res.improvement_surface().mi_upper - count_res.improvement_surface().mi_lower
    w_amount = amount_res.improvement_surface().mi_upper - amount_res.improvement_surface().mi_lower
    assert w_amount[_INT_AGE, _INT_YEAR].mean() > w_count[_INT_AGE, _INT_YEAR].mean()


# --------------------------------------------------------------------------- #
# Determinism & consistency with the frequentist grid
# --------------------------------------------------------------------------- #


def test_fit_is_deterministic():
    """Two independent fits of the same data give bit-identical surfaces."""
    cells = _mi_cells_poisson(_AGES, _YEARS, 0.015, exposure=5.0e4, seed=SEED)
    a = BayesianTensorMIModel(cells).fit().improvement_surface()
    b = BayesianTensorMIModel(cells).fit().improvement_surface()
    assert np.array_equal(a.mi_grid, b.mi_grid)
    assert np.array_equal(a.mi_lower, b.mi_lower)
    assert np.array_equal(a.mi_upper, b.mi_upper)


def test_agrees_with_frequentist_grid():
    """
    On the same closed-form data the Bayesian HSGP surface recovers the same
    improvement as the Slice-2a frequentist tensor grid within tolerance — the
    two backends agree on the point estimate; only the band interpretation differs
    (credible interval vs delta-method CI).
    """
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.02)
    bayes = BayesianTensorMIModel(cells).fit().improvement_surface()
    freq = TensorMIModel(cells, age_df=6, year_df=4).fit().improvement_surface()
    np.testing.assert_allclose(
        bayes.mi_grid[_INT_AGE, _INT_YEAR], freq.mi_grid[_INT_AGE, _INT_YEAR], atol=3e-3
    )


def test_effective_df_is_bounded():
    """Effective df is positive and below the raw GP parameter count (shrinkage)."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    result = BayesianTensorMIModel(cells, age_basis=8, year_basis=8).fit()
    n_gp_params = 8 + 8 + 8 * 8  # age + year + interaction
    assert 0.0 < result.effective_df < n_gp_params + 5


def test_to_frame_has_expected_shape():
    """The returned MISurface flattens to a tidy per-(age, step-year) frame."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    surface = BayesianTensorMIModel(cells).fit().improvement_surface()
    frame = surface.to_frame()
    assert frame.columns == ["attained_age", "calendar_year", "mi", "mi_lower", "mi_upper"]
    assert frame.height == len(surface.ages) * len(surface.years)


# --------------------------------------------------------------------------- #
# Anchor-1 static-base guard
# --------------------------------------------------------------------------- #


def test_generational_base_rejected():
    """A calendar-drifting q_base offset (generational) is rejected by Anchor 1."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015, generational_drift=0.01)
    with pytest.raises(PolarisValidationError, match="generational"):
        BayesianTensorMIModel(cells)


def test_generational_base_override():
    """``allow_generational_base=True`` bypasses the static-base guard."""
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015, generational_drift=0.01)
    result = BayesianTensorMIModel(cells, allow_generational_base=True).fit()
    assert isinstance(result, BayesianMISurfaceResult)


def test_single_calendar_year_cells_rejected():
    """No cell spanning >1 calendar year => the trend is unidentifiable (Anchor 1)."""
    rows = [
        {
            "attained_age": int(a),
            "calendar_year": 2005 + (int(a) % 3),  # each age has exactly one year
            "q_base": 0.01,
            "central_exposure": 1.0e5,
            "death_count": 1.0e3,
        }
        for a in _AGES
    ]
    cells = pl.DataFrame(rows)
    with pytest.raises(PolarisValidationError):
        BayesianTensorMIModel(cells)


# --------------------------------------------------------------------------- #
# Contract & config validation
# --------------------------------------------------------------------------- #


def test_missing_required_column_rejected():
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015).drop("q_base")
    with pytest.raises(PolarisValidationError, match="missing required"):
        BayesianTensorMIModel(cells)


def test_single_year_rejected():
    cells = _mi_cells(_AGES, np.array([2010]), lambda a: 0.015)
    with pytest.raises(PolarisValidationError, match="distinct calendar_year"):
        BayesianTensorMIModel(cells)


def test_invalid_basis_rejected():
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    with pytest.raises(PolarisValidationError, match="basis must be"):
        BayesianTensorMIModel(cells, basis="face")


def test_invalid_boundary_factor_rejected():
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    with pytest.raises(PolarisValidationError, match="boundary_factor"):
        BayesianTensorMIModel(cells, boundary_factor=1.0)


def test_too_few_surface_years_rejected():
    cells = _mi_cells(_AGES, _YEARS, lambda a: 0.015)
    result = BayesianTensorMIModel(cells).fit()
    with pytest.raises(PolarisValidationError, match="two calendar years"):
        result.improvement_surface(years=np.array([2010]))

"""
Tests for the Slice-2c ``MortalityImprovement``-compatible custom-scale emission.

Slice 2c closes the experience-GAM loop: an experience-fitted ``MI_x(y)`` surface
(:class:`MISurface`) or forward projection (:class:`MIProjection`) is emitted as a
``MortalityImprovement`` (``ImprovementScale.CUSTOM``) via
``to_mortality_improvement``, so a data-driven improvement basis plugs straight into
the same ``apply_improvement`` path the built-in scales use.

The headline acceptance criterion is the **round-trip identity**: the emitted CUSTOM
scale reproduces the dataclass's own ``cumulative_factor()`` exactly, i.e.

    apply_improvement(q, ages, years[k]) == q * cumulative_factor()[:, k].

Both a fast direct-construction path (exact, no fitting) and an end-to-end
fit -> project -> emit integration test are covered. No test depends on the wall
clock (ADR-074 guard).
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import (
    BayesianTensorMIModel,
    MIProjection,
    MISurface,
)
from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement

SEED = 20260722


def _projection(mi_grid: np.ndarray, *, long_term_rate: float = 0.01) -> MIProjection:
    """Build an MIProjection directly from a known grid (no fitting)."""
    a, k = mi_grid.shape
    ages = np.arange(50, 50 + a, dtype=np.int64)
    years = np.arange(2026, 2026 + k, dtype=np.int64)
    return MIProjection(
        ages=ages,
        years=years,
        mi_grid=mi_grid.astype(np.float64),
        mi_lower=(mi_grid - 0.005).astype(np.float64),
        mi_upper=(mi_grid + 0.005).astype(np.float64),
        confidence_level=0.95,
        long_term_rate=long_term_rate,
        convergence_period=20,
        method="cosine",
        last_observed_year=2025,
        initial_mi=mi_grid[:, 0].astype(np.float64),
    )


def _surface(mi_grid: np.ndarray) -> MISurface:
    """Build an MISurface directly from a known grid (no fitting)."""
    a, k = mi_grid.shape
    ages = np.arange(50, 50 + a, dtype=np.int64)
    years = np.arange(2011, 2011 + k, dtype=np.int64)
    return MISurface(
        ages=ages,
        years=years,
        mi_grid=mi_grid.astype(np.float64),
        mi_lower=(mi_grid - 0.005).astype(np.float64),
        mi_upper=(mi_grid + 0.005).astype(np.float64),
        confidence_level=0.95,
    )


# --------------------------------------------------------------------------- #
# Round-trip identity: emitted scale reproduces cumulative_factor exactly
# --------------------------------------------------------------------------- #


def test_projection_emits_custom_scale():
    """to_mortality_improvement yields a CUSTOM scale anchored at last_observed_year."""
    proj = _projection(np.full((3, 4), 0.02))
    imp = proj.to_mortality_improvement()
    assert isinstance(imp, MortalityImprovement)
    assert imp.scale == ImprovementScale.CUSTOM
    assert imp.base_year == 2025  # last_observed_year == years[0] - 1


def test_projection_round_trip_matches_cumulative_factor():
    """
    ACCEPTANCE: apply_improvement(q, ages, years[k]) == q * cumulative_factor[:, k]
    for every projected year k, on the projected ages.
    """
    rng = np.random.default_rng(SEED)
    mi_grid = rng.uniform(0.005, 0.03, size=(4, 5))
    proj = _projection(mi_grid)
    imp = proj.to_mortality_improvement(ultimate_rate=0.0)

    factor = proj.cumulative_factor()  # (A, K)
    q_base = np.array([0.01, 0.02, 0.03, 0.05], dtype=np.float64)
    ages = proj.ages.astype(np.int32)
    for k, year in enumerate(proj.years):
        result = imp.apply_improvement(q_base, ages, target_year=int(year))
        np.testing.assert_allclose(result, q_base * factor[:, k], rtol=1e-12)


def test_surface_round_trip_matches_cumulative_product():
    """MISurface emission reproduces the in-window Π(1 - MI) cumulative product."""
    rng = np.random.default_rng(SEED + 1)
    mi_grid = rng.uniform(0.005, 0.03, size=(3, 6))
    surf = _surface(mi_grid)
    imp = surf.to_mortality_improvement()

    factor = np.cumprod(1.0 - mi_grid, axis=1)
    q_base = np.array([0.01, 0.02, 0.03], dtype=np.float64)
    ages = surf.ages.astype(np.int32)
    for k, year in enumerate(surf.years):
        result = imp.apply_improvement(q_base, ages, target_year=int(year))
        np.testing.assert_allclose(result, q_base * factor[:, k], rtol=1e-12)


# --------------------------------------------------------------------------- #
# Ultimate-rate behaviour past the horizon
# --------------------------------------------------------------------------- #


def test_projection_default_ultimate_is_long_term_rate():
    """Default ultimate rate continues the projection's long-term assumption."""
    proj = _projection(np.full((2, 3), 0.02), long_term_rate=0.012)
    imp = proj.to_mortality_improvement()
    assert imp.custom_ultimate_rate == pytest.approx(0.012)

    # One year past the horizon uses the long-term rate.
    q_base = np.array([0.01, 0.01], dtype=np.float64)
    ages = proj.ages.astype(np.int32)
    beyond = imp.apply_improvement(q_base, ages, target_year=int(proj.years[-1]) + 1)
    at_horizon = imp.apply_improvement(q_base, ages, target_year=int(proj.years[-1]))
    np.testing.assert_allclose(beyond, at_horizon * (1.0 - 0.012), rtol=1e-12)


def test_projection_ultimate_zero_stops_improvement():
    """ultimate_rate=0.0 freezes mortality past the projection horizon."""
    proj = _projection(np.full((2, 3), 0.02))
    imp = proj.to_mortality_improvement(ultimate_rate=0.0)
    q_base = np.array([0.01, 0.01], dtype=np.float64)
    ages = proj.ages.astype(np.int32)
    at_horizon = imp.apply_improvement(q_base, ages, target_year=int(proj.years[-1]))
    beyond = imp.apply_improvement(q_base, ages, target_year=int(proj.years[-1]) + 5)
    np.testing.assert_allclose(beyond, at_horizon, rtol=1e-12)


# --------------------------------------------------------------------------- #
# End-to-end: fit -> project -> emit
# --------------------------------------------------------------------------- #


def _q_base(age: np.ndarray) -> np.ndarray:
    return 0.004 * np.exp(0.08 * (np.asarray(age, dtype=np.float64) - 45.0))


def _constant_mi_cells(mi: float, *, exposure: float = 2.0e6) -> pl.DataFrame:
    """Grouped cells with a constant improvement rate (deterministic deaths)."""
    ages = np.arange(40, 71)
    years = np.arange(2005, 2021)
    base = int(years.min())
    rows = []
    for a in ages:
        q0 = float(_q_base(np.array([a]))[0])
        for y in years:
            actual_q = q0 * (1.0 - mi) ** (int(y) - base)
            rows.append(
                {
                    "attained_age": int(a),
                    "calendar_year": int(y),
                    "q_base": q0,
                    "central_exposure": exposure,
                    "death_count": exposure * actual_q,
                }
            )
    return pl.DataFrame(rows)


@pytest.mark.filterwarnings("ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning")
def test_end_to_end_fit_project_emit_round_trip():
    """
    A fitted Bayesian surface, projected forward and emitted as a CUSTOM scale,
    reproduces the projection's cumulative_factor through apply_improvement.
    """
    cells = _constant_mi_cells(0.015)
    result = BayesianTensorMIModel(cells).fit()
    proj = result.project_improvement(horizon_years=10, long_term_rate=0.01)
    imp = proj.to_mortality_improvement()

    assert imp.scale == ImprovementScale.CUSTOM
    factor = proj.cumulative_factor()
    q_base = _q_base(proj.ages)
    ages = proj.ages.astype(np.int32)
    for k, year in enumerate(proj.years):
        result_q = imp.apply_improvement(q_base, ages, target_year=int(year))
        np.testing.assert_allclose(result_q, q_base * factor[:, k], rtol=1e-10)


@pytest.mark.filterwarnings("ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning")
def test_end_to_end_recovers_constant_improvement():
    """
    A ~1.5%/yr experience trend, once emitted as a CUSTOM scale, projects mortality
    forward at approximately that rate (sanity, closed-form-ish).
    """
    cells = _constant_mi_cells(0.015)
    proj = (
        BayesianTensorMIModel(cells)
        .fit()
        .project_improvement(horizon_years=5, long_term_rate=0.015)
    )
    imp = proj.to_mortality_improvement()
    # Interior age avoids GP boundary effects.
    age = np.array([55], dtype=np.int32)
    q_base = _q_base(age)
    one_year = imp.apply_improvement(q_base, age, target_year=int(proj.years[0]))
    realised_mi = 1.0 - float(one_year[0] / q_base[0])
    assert realised_mi == pytest.approx(0.015, abs=3e-3)

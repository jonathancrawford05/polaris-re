"""Partial effects and the improvement surface (D2, ADR-263): shapes, closed forms, refusals.
Every check here is a MEASUREMENT of the fitted model (own criterion) unless it compares to a
closed form stated in the test."""

import numpy as np
import polars as pl
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam import gam
from polaris_re.gam.effects import improvement_surface, partial_effects


def _frame(seed: int = 3, n: int = 600) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.uniform(0.0, 6.0, n)
    f = rng.choice(["a", "b", "c"], n)
    shift = {"a": 0.0, "b": 0.5, "c": -0.3}
    y = np.sin(x) + np.array([shift[v] for v in f]) + rng.normal(0.0, 0.1, n)
    return pl.DataFrame({"x": x, "f": f, "y": y})


def test_partial_effect_curve_recovers_centred_sine_and_factor_levels() -> None:
    d = _frame()
    fit = gam('y ~ f + s(x, bs="cr", k=10)', d, "gaussian")
    eff = {e.label: e for e in partial_effects(fit, d)}
    curve = eff["s(x)"]
    grid = curve.axes[0]
    truth = np.sin(grid)
    # the smooth is centred over the training rows, so compare after centring the truth the same way
    truth_c = truth - np.mean(np.sin(d.get_column("x").to_numpy()))
    assert curve.kind == "curve" and curve.se.shape == grid.shape and np.all(curve.se > 0.0)
    np.testing.assert_allclose(curve.effect, truth_c, atol=0.1)
    lv = next(e for e in eff.values() if e.kind == "levels")
    got = dict(zip(lv.level_names, lv.effect, strict=True))
    np.testing.assert_allclose([got["a"], got["b"], got["c"]], [0.0, 0.5, -0.3], atol=0.05)


def test_partial_effects_sum_with_intercept_to_the_link_prediction() -> None:
    d = _frame()
    fit = gam('y ~ f + s(x, bs="cr", k=10)', d, "gaussian")
    # at the training rows: intercept + sum of term blocks == predict (closed identity)
    from polaris_re.analytics.gam_predict import predict_design

    cols = fit.encode(d)
    x = predict_design(fit.model, fit.term_states, cols)
    np.testing.assert_allclose(x @ fit.coef_full, fit.predict(d, "link"), rtol=1e-12, atol=1e-12)


def _cells(slope: float = 0.02) -> pl.DataFrame:
    ages = np.arange(40, 61, dtype=float)
    years = np.arange(2010, 2020, dtype=float)
    a = np.repeat(ages, years.size)
    y = np.tile(years, ages.size)
    mu = 2.0e5 * 0.004 * np.exp(0.07 * (a - 45.0)) * (1.0 - slope) ** (y - 2010.0)
    return pl.DataFrame(
        {
            "attained_age": a,
            "calendar_year": y,
            "death_count": mu,
            "log_exposure": np.full(a.size, np.log(2.0e5)),
        }
    )


FORM = (
    'death_count ~ s(attained_age, bs="cr", k=6) + s(calendar_year, bs="cr", k=5) '
    "+ offset(log_exposure)"
)


def test_surface_matches_the_public_predict_contrast_and_band_contains_estimate() -> None:
    d = _cells()
    fit = gam(FORM, d, "poisson")
    s = improvement_surface(fit, d)
    hi = d.filter(pl.col("calendar_year") == 2015.0)
    lo = hi.with_columns((pl.col("calendar_year") - 1.0).alias("calendar_year"))
    mi = 1.0 - np.exp(fit.predict(hi, "link") - fit.predict(lo, "link"))
    col = int(np.where(s.years == 2015.0)[0][0])
    np.testing.assert_allclose(s.mi[:, col], mi, rtol=1e-10)
    assert np.all(s.mi_lower <= s.mi) and np.all(s.mi <= s.mi_upper)
    assert s.mi.shape == (s.ages.size, s.years.size) and s.years[0] == 2011.0


def test_surface_width_grows_with_level() -> None:
    d = _cells()
    fit = gam(FORM, d, "poisson")
    w90 = improvement_surface(fit, d, level=0.90)
    w99 = improvement_surface(fit, d, level=0.99)
    assert np.all(w99.mi_upper - w99.mi_lower > w90.mi_upper - w90.mi_lower)


def test_surface_refused_without_a_calendar_year_smooth() -> None:
    d = _cells()
    fit = gam('death_count ~ s(attained_age, bs="cr", k=6) + offset(log_exposure)', d, "poisson")
    with pytest.raises(PolarisValidationError, match="no smooth term of 'calendar_year'"):
        improvement_surface(fit, d)


def test_surface_with_ti_runs_and_reports_references() -> None:
    d = _cells()
    fit = gam(
        FORM.replace("+ offset", '+ ti(attained_age, calendar_year, bs="cr") + offset'),
        d,
        "poisson",
    )
    s = improvement_surface(fit, d)
    np.testing.assert_allclose(s.mi, 0.02, atol=1e-6)
    surf = [e for e in partial_effects(fit, d, points=12) if e.kind == "surface"]
    assert len(surf) == 1 and surf[0].effect.shape == (12, 12)

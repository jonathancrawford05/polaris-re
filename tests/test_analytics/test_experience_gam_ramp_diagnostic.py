"""Slice 1 of ``docs/PLAN_gam_spline_diagnostics.md`` — what actually produces the
age-45 ramp.

``MEASUREMENT_experience_gam_ilec.md`` §3 reports that age 45's fitted MI runs
0.05% (2013) to 3.59% (2019) and calls it boundary contamination that "needs a
longer vintage, not a different setting". That sentence blocks every age-45
insured-improvement claim, and until now nothing tested it.

**Why synthetic is the stronger evidence here, not the weaker.** On real ILEC the
true surface is unknown, so a ramp is only ever *suspicious*. On a fixture with a
known constant injected surface, a swing is **proof of artifact** — there is
nothing else it could be. This is the one question where a fixture beats the real
data outright, which is why slice 4 is a single confirmation run rather than the
experiment.

What these tests establish, in order:

1. The shipped configuration recovers a constant surface **exactly** with no
   sampling noise. The cubic year basis is not biased and does not bend on its
   own — so "the ramp is what an unpenalized cubic does" is **wrong as stated**.
2. Sampling noise alone, on a truth that is exactly constant, manufactures a
   multi-point swing at the young end. That is the artifact, reproduced.
3. It is graded by **information**, not by knot position: the swing peaks at the
   youngest fitted age and is several times larger there than at the first
   interior knot, in every age range tried.

Tests 4 and 5 are the two-sided companions. Without them a smoother that simply
reported constant MI for everything would satisfy 1-3 and be applauded for it —
the failure mode ADR-182 caught in the slowdown verdict, one level down.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import TensorMIModel

# Large aggregated cells drive the Poisson IRLS to near-perfect prediction on the
# noiseless fixtures; statsmodels flags that as possible separation. Expected here.
pytestmark = pytest.mark.filterwarnings(
    "ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning"
)

# --------------------------------------------------------------------------- #
# The ILEC-shaped fixture
# --------------------------------------------------------------------------- #

_AGES = np.arange(25, 96)
_YEARS = np.arange(2012, 2020)
"""Eight calendar years and ages 25-95 — the shape of the committed ILEC runs."""

_REFERENCE_AGES = (45, 55, 65, 75, 85)
_MI_TRUE = 0.015
_EXPOSURE = 6.0e4
"""Per-cell exposure. Chosen so total deaths land within an order of magnitude of
ILEC's 4.35M, which is the regime where the artifact is the size ILEC reported."""

_SHIPPED_FIT = {"age_df": 6, "year_df": 3, "basis": "count"}
"""The configuration both committed ILEC reports used. Not a guess — read back
from ``docs/measurements/experience_gam_ilec*.json``."""


def _q_base(age: np.ndarray | float) -> np.ndarray:
    """Smooth increasing base rate. Deaths at 45 are ~24x scarcer than at 85 under
    this curve, which is the information asymmetry the whole finding turns on."""
    return 0.004 * np.exp(0.08 * (np.asarray(age, dtype=np.float64) - 45.0))


def _cells(
    mi_fn,
    *,
    ages: np.ndarray = _AGES,
    exposure: float = _EXPOSURE,
    noisy: bool,
    seed: int = 7,
) -> pl.DataFrame:
    """Grouped cells whose *actual* mortality follows a known improvement path.

    ``mi_fn(age, year)`` returns the improvement applied moving into ``year``, so a
    year-varying truth is expressible and the two-sided tests can inject a genuine
    ramp. ``q_base`` stays static (Anchor 1), so every calendar-varying effect is
    improvement by construction.
    """
    rng = np.random.default_rng(seed)
    base = int(_YEARS.min())
    rows: list[tuple[int, int, float, float, float]] = []
    for age in ages:
        q0 = float(_q_base(age))
        actual = q0
        for year in _YEARS:
            if int(year) > base:
                actual *= 1.0 - float(mi_fn(float(age), int(year)))
            expected = exposure * actual
            deaths = float(rng.poisson(expected)) if noisy else expected
            rows.append((int(age), int(year), q0, exposure, deaths))
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


def _surface(cells: pl.DataFrame, **overrides: object):
    kwargs = {**_SHIPPED_FIT, **overrides}
    return TensorMIModel(cells, **kwargs).fit().improvement_surface()  # type: ignore[arg-type]


def _row(surface, age: int) -> np.ndarray:
    return np.asarray(surface.mi_grid[int(np.where(surface.ages == age)[0][0])], dtype=np.float64)


def _span_pp(surface, age: int) -> float:
    """Peak-to-trough of fitted MI across the window, in percentage points."""
    row = _row(surface, age)
    return float(row.max() - row.min()) * 100.0


_CONSTANT = lambda age, year: _MI_TRUE  # noqa: E731 - a one-line truth, read inline
_BROAD_RAMP = lambda age, year: 0.035 * (year - 2013) / 6.0  # noqa: E731


# --------------------------------------------------------------------------- #
# 1. The cubic basis is not biased — it recovers the truth exactly
# --------------------------------------------------------------------------- #


def test_the_shipped_configuration_recovers_a_constant_surface_exactly() -> None:
    """No noise, no ramp — anywhere, including at the boundary ages.

    This is the falsification. The stated reading of age 45 was that an unpenalized
    cubic over eight years "must place its curvature somewhere" and ramps at the
    ends. If that were the mechanism it would show here, where there is nothing but
    the basis and the truth. It does not: a cubic year margin represents a
    linear-in-year eta exactly, so the constant surface comes back to machine
    precision. Whatever produces the real ramp, it is not basis bias.
    """
    surface = _surface(_cells(_CONSTANT, noisy=False))
    for age in _REFERENCE_AGES:
        np.testing.assert_allclose(_row(surface, age), _MI_TRUE, atol=1e-6)


# --------------------------------------------------------------------------- #
# 2. Sampling noise alone manufactures the swing
# --------------------------------------------------------------------------- #


def test_sampling_noise_alone_manufactures_a_multi_point_swing_at_age_45() -> None:
    """Truth is exactly 1.5%/yr at every age. The fit says otherwise at 45.

    Same fixture as the test above, with Poisson-sampled deaths and nothing else
    changed. Age 45's fitted MI swings by multiple percentage points across seven
    years while the injected surface is flat — so the swing is manufactured, and
    its size is comparable to the 0.05% -> 3.59% the real ILEC run reported.
    """
    surface = _surface(_cells(_CONSTANT, noisy=True, seed=7))
    assert _span_pp(surface, 45) > 1.0, "the artifact did not reproduce"
    # ...and the old end, with ~24x the deaths, stays close to the truth.
    assert _span_pp(surface, 85) < 1.0


# --------------------------------------------------------------------------- #
# 3. Graded by information, not by knot position
# --------------------------------------------------------------------------- #


def test_the_swing_is_graded_by_information_not_uniform_across_age() -> None:
    """Averaged over seeds, so the claim is about the distribution, not a draw.

    A single seed is a coin flip — age 45's span ranges 0.17 to 3.83 across ten of
    them, which is itself the signature of a variance phenomenon. The *mean* is
    stable, and it is several times larger at the death-poor young end.
    """
    seeds = range(1, 9)
    surfaces = [_surface(_cells(_CONSTANT, noisy=True, seed=s)) for s in seeds]
    young = float(np.mean([_span_pp(s, 45) for s in surfaces]))
    old = float(np.mean([_span_pp(s, 85) for s in surfaces]))
    assert young > 3.0 * old, f"expected a strong young/old gradient, got {young:.2f} vs {old:.2f}"


@pytest.mark.parametrize(("low", "high"), [(25, 96), (30, 101), (20, 91)])
def test_the_swing_does_not_track_the_age_knot_position(low: int, high: int) -> None:
    """Hypothesis B, falsified: move the knots and the anomaly stays put.

    ``bs(attained_age, df=6)`` places interior knots at quantiles, so shifting the
    fitted age range moves the first knot across 42 / 47 / 37. If age 45 were
    contaminated by sitting next to a knot, the worst-affected age would follow it.
    It does not — in every range the swing peaks at the *youngest fitted age* and
    is multiples of its value at the first knot. The driver is scarce deaths at the
    young edge, which is a different problem with a different fix.
    """
    ages = np.arange(low, high)
    surface = _surface(_cells(_CONSTANT, ages=ages, noisy=True, seed=7))
    span = (surface.mi_grid.max(axis=1) - surface.mi_grid.min(axis=1)) * 100.0

    first_knot = float(np.quantile(np.repeat(ages, len(_YEARS)).astype(np.float64), 0.25))
    at_knot = float(span[int(np.argmin(np.abs(surface.ages - first_knot)))])
    at_youngest = float(span[0])

    assert surface.ages[int(np.argmax(span))] < np.quantile(surface.ages, 0.2), (
        "the swing should peak at the young edge of the fitted range"
    )
    assert at_youngest > 2.0 * at_knot, (
        f"knot at ~{first_knot:.0f} shows {at_knot:.2f}pp against {at_youngest:.2f}pp "
        f"at the youngest age — the anomaly is not knot-driven"
    )


# --------------------------------------------------------------------------- #
# 4-5. Two-sided: a real ramp must still be visible
# --------------------------------------------------------------------------- #


def test_a_genuine_ramp_is_recovered_exactly_without_noise() -> None:
    """The guard against 'fixing' the artifact with a smoother that sees nothing.

    A truth whose MI genuinely climbs 0% -> 3.5% across the window, at every age,
    comes back exactly. The shipped basis is *capable*; tests 1-3 are about
    variance, not about the basis being unable to represent real structure.
    """
    surface = _surface(_cells(_BROAD_RAMP, noisy=False))
    expected = 0.035 * (np.asarray(surface.years, dtype=np.float64) - 2013.0) / 6.0
    for age in _REFERENCE_AGES:
        np.testing.assert_allclose(_row(surface, age), expected, atol=1e-6)


def test_a_genuine_ramp_survives_sampling_noise() -> None:
    """The same real ramp, with Poisson deaths, is still resolvable where there is
    information to resolve it.

    Age 45 is deliberately excluded: tests 2 and 3 establish it is the one place
    the noise wins, and asserting it here would contradict them. That exclusion is
    the finding, not an accommodation.
    """
    surface = _surface(_cells(_BROAD_RAMP, noisy=True, seed=7))
    for age in (55, 65, 75, 85):
        row = _row(surface, age)
        climb = float(row[-1] - row[0]) * 100.0
        assert climb > 2.0, f"age {age}: genuine ramp not recovered, climb {climb:.2f}pp"


# --------------------------------------------------------------------------- #
# 6-9. Slice 3 — the degree knob, and what it costs
# --------------------------------------------------------------------------- #


def test_degree_defaults_leave_the_shipped_design_untouched() -> None:
    """Every committed report predates this parameter and must stay reproducible.

    The formula string is emitted in its legacy form at the cubic default, so both
    the design columns *and* the ``design_info`` term names are identical to a fit
    taken before ``*_degree`` existed.
    """
    cells = _cells(_CONSTANT, noisy=True, seed=7)
    default = _surface(cells)
    explicit = _surface(cells, age_degree=3, year_degree=3, duration_degree=3)
    np.testing.assert_array_equal(default.mi_grid, explicit.mi_grid)

    fitted = TensorMIModel(cells, **_SHIPPED_FIT).fit()  # type: ignore[arg-type]
    assert "degree" not in "".join(fitted.knots), "cubic default must emit the legacy term name"
    # ...and the knots really are where slice 1 said, not at even fractions of the range.
    np.testing.assert_allclose(fitted.knots["bs(attained_age, df=6)"], [42.0, 60.0, 78.0])
    assert fitted.knots["bs(calendar_year, df=3)"] == [], "df == degree carries no interior knots"


def test_a_linear_year_margin_cannot_ramp_and_is_unbiased() -> None:
    """The fix, measured: the swing goes to zero *and* the level comes back.

    At ``df == degree == 1`` the year margin is a global straight line, so the
    year-to-year contrast is identical at every step and fitted MI is constant by
    construction. The level matters as much as the flatness — the shipped cubic
    pulls age 45's mean fitted MI to ~1.19% on a 1.50% truth, and this restores it.
    """
    cells = _cells(_CONSTANT, noisy=True, seed=7)
    linear = _surface(cells, year_df=1, year_degree=1)
    for age in _REFERENCE_AGES:
        row = _row(linear, age)
        assert _span_pp(linear, age) < 1e-9, f"age {age} is not flat"
        np.testing.assert_allclose(row.mean(), _MI_TRUE, atol=2e-3)

    cubic_bias = abs(float(_row(_surface(cells), 45).mean()) - _MI_TRUE)
    linear_bias = abs(float(_row(linear, 45).mean()) - _MI_TRUE)
    assert linear_bias < cubic_bias / 2.0, (
        f"expected the linear margin to de-bias age 45: cubic off by "
        f"{cubic_bias * 100:.2f}pp, linear by {linear_bias * 100:.2f}pp"
    )


def test_lowering_degree_without_df_still_permits_a_ramp() -> None:
    """The trap the plan itself fell into, pinned in code.

    ``year_degree=1`` with ``year_df=3`` keeps two interior knots, so MI becomes a
    *step function* in year and swings as freely as the cubic. Degree alone is not
    the knob; ``df == degree`` is.
    """
    cells = _cells(_CONSTANT, noisy=True, seed=7)
    kinked = _surface(cells, year_df=3, year_degree=1)
    assert _span_pp(kinked, 45) > 0.5, (
        "degree=1 with df=3 should still swing — if this ever passes at ~0, the "
        "two knobs have been conflated somewhere and the ladder is wrong"
    )


@pytest.mark.parametrize(
    ("year_df", "year_degree", "sees_the_ramp"),
    [(1, 1, False), (2, 2, True), (3, 3, True)],
)
def test_the_price_of_a_lower_order_is_blindness_to_real_curvature(
    year_df: int, year_degree: int, sees_the_ramp: bool
) -> None:
    """Slice 3's whole point: what a lower order costs, not what it buys.

    The truth here genuinely accelerates — MI climbs 0% to 3.5% across the window
    at every age. A global linear margin **cannot represent that**: it is forced to
    report one constant rate, and the climb vanishes. Quadratic and cubic both see
    it.

    So degree-lowering is not a free fix. It trades the ability to manufacture a
    false trend for the ability to detect a true one, uniformly across age, which
    is exactly the trade a *penalty* avoids having to make — the argument for the
    P-spline rebuild rather than a substitute for it.
    """
    surface = _surface(_cells(_BROAD_RAMP, noisy=False), year_df=year_df, year_degree=year_degree)
    climb = float(_row(surface, 65)[-1] - _row(surface, 65)[0]) * 100.0
    if sees_the_ramp:
        assert climb > 3.0, f"a genuine 3.5pp climb should be visible, got {climb:.2f}pp"
    else:
        assert abs(climb) < 1e-9, f"a linear margin cannot see a climb, yet reported {climb:.2f}pp"

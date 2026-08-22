"""Slices 1-4 of ``docs/PLAN_penalized_mi_surface.md`` — the penalized fitter.

The two limits are where correctness is decidable without trusting anything new:

- **λ = 0 must reproduce ``TensorMIModel`` exactly** (Anchor 1). The oracle already
  exists and is already tested, so this is the cheapest strong test available. It is
  asserted on the *fitted surface*, never on coefficients: the two models use
  different bases for the same column space, so their coefficients are not
  comparable while their fitted values must be identical.
- **λ → ∞ must shrink to the penalty's null space.** A second-difference penalty
  cannot see linear functions, so an enormous calendar penalty leaves η linear in
  year and fitted MI **constant in time** — which is the same quantity ADR-184
  amendment 1 measured at ``df == degree == 1``. Two independent implementations,
  one closed form.

Between the limits, ``edf`` must move monotonically — the whole behavioural
contract of slice 1.

Slice 2 adds λ **selection** and the Anchor-4 reporting fix. Its tests are grouped
below and turn on two things: the selection is a *grid*, so reproducibility is
exact rather than tolerance-bounded, and the graded-smoothness ladder must be
**representable in the basis** or the test measures the basis instead of the
selector (ADR-186).

Slice 3 adds the Bayesian band and the coverage study. Its fixtures encode the
distinction the study turns on: a truth can be **inside the penalty null space**
(constant MI — where shrinkage is free and coverage flatters), **outside it but
representable** (quadratic — where coverage measures the *band*), or
**unrepresentable** (a sine cycle — where coverage measures *bias*). Conflating the
three is what made a first probe read as a calibration disaster.

Slice 4 makes the selector survive a grid point that will not converge, and adds an
interval that stops conditioning on λ. Its tests turn on a distinction slice 3 could
not make: a band's coverage *given* λ and its coverage *under the procedure that
chose λ* are different quantities, and only the second is what a user gets.

(This docstring has now been stale twice: it said "selection is slice 2 and is
deliberately absent here" for one commit after six selection tests landed beside it,
and said "Slices 1-2" through all of slice 3. A docstring written for slice N is
stale by slice N+1 by default — see ADR-186 amendment 2 on claim sets.)
"""

import functools
import itertools
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import TensorMIModel, mi_surface_from_design
from polaris_re.analytics.experience_gam_penalized import (
    COARSE_STEP,
    KS_LOG_STEP,
    LAMBDA_LOG10_BOUNDS,
    REFINE_STEP,
    PenalizedTensorMIModel,
    difference_penalty,
    fit_reml,
    lambda_is_at_bound,
    reml_score,
    select_lambdas_reml,
    smoothing_uncertainty,
    tensor_penalties,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

pytestmark = pytest.mark.filterwarnings(
    "ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning"
)

_AGES = np.arange(25, 96)
_YEARS = np.arange(2012, 2020)
_MI_TRUE = 0.015


def _q_base(age: float) -> float:
    return 0.004 * float(np.exp(0.08 * (age - 45.0)))


def _cells(*, noisy: bool, seed: int = 7, mi: float = _MI_TRUE) -> pl.DataFrame:
    """The ILEC-shaped fixture from the diagnostics epic, reused rather than rebuilt."""
    rng = np.random.default_rng(seed)
    rows: list[tuple[int, int, float, float, float]] = []
    for age in _AGES:
        q0 = _q_base(float(age))
        actual = q0
        for year in _YEARS:
            if int(year) > int(_YEARS.min()):
                actual *= 1.0 - mi
            expected = 6.0e4 * actual
            rows.append(
                (
                    int(age),
                    int(year),
                    q0,
                    6.0e4,
                    float(rng.poisson(expected)) if noisy else expected,
                )
            )
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


def _cells_from(mi_fn, *, seed: int = 7) -> pl.DataFrame:
    """`_cells` with a year-varying truth — the graded ladder needs a callable."""
    rng = np.random.default_rng(seed)
    rows: list[tuple[int, int, float, float, float]] = []
    for age in _AGES:
        q0 = _q_base(float(age))
        actual = q0
        for year in _YEARS:
            if int(year) > int(_YEARS.min()):
                actual *= 1.0 - float(mi_fn(float(age), int(year)))
            rows.append((int(age), int(year), q0, 6.0e4, float(rng.poisson(6.0e4 * actual))))
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


def _penalized_mi(cells: pl.DataFrame, **kwargs: object) -> np.ndarray:
    """Fitted MI grid, **via the shipped extractor** rather than re-derived here.

    This used to rebuild the grid design and difference η itself, which meant every
    slice-1 and slice-2 limit test was asserting on arithmetic the test file owned
    rather than on what a caller receives. Slice 3 routes it through
    `improvement_surface`, so eleven existing tests now also pin the extraction path.
    """
    fit = PenalizedTensorMIModel(cells, **kwargs).fit()  # type: ignore[arg-type]
    return fit.improvement_surface(ages=_AGES, years=_YEARS).mi_grid


# --------------------------------------------------------------------------- #
# The penalty itself
# --------------------------------------------------------------------------- #


def test_the_second_difference_penalty_annihilates_linear_sequences() -> None:
    """The defining property, and the reason MI can never be shrunk to zero.

    ``order=2`` leaves linear functions in the null space, so a straight-line trend
    survives any λ. A penalty that could shrink improvement to nothing would be
    manufacturing a modelling artifact rather than smoothing one away.
    """
    s = difference_penalty(8, order=2)
    for null_vector in (np.ones(8), np.arange(8, dtype=np.float64)):
        np.testing.assert_allclose(s @ null_vector, 0.0, atol=1e-12)
    curved = np.arange(8, dtype=np.float64) ** 2
    assert float(curved @ s @ curved) > 0.0


def test_the_penalty_refuses_a_basis_too_small_to_penalise() -> None:
    with pytest.raises(PolarisValidationError, match="needs more than 2 coefficients"):
        difference_penalty(2, order=2)


def test_the_tensor_penalties_act_on_the_margin_they_name() -> None:
    """Age-major ordering, asserted — swapping the Kronecker factors still runs.

    A coefficient surface that is constant down the age axis carries no age
    roughness, so the age penalty must annihilate it while the year penalty need
    not, and vice versa. That is the check that catches a transposed penalty, which
    is otherwise silent and wrong.
    """
    k_age, k_year = 5, 4
    s_age, s_year = tensor_penalties(k_age, k_year)

    flat_in_age = np.tile(np.arange(k_year, dtype=np.float64) ** 2, k_age)
    np.testing.assert_allclose(s_age @ flat_in_age, 0.0, atol=1e-12)
    assert float(flat_in_age @ s_year @ flat_in_age) > 0.0

    flat_in_year = np.repeat(np.arange(k_age, dtype=np.float64) ** 2, k_year)
    np.testing.assert_allclose(s_year @ flat_in_year, 0.0, atol=1e-12)
    assert float(flat_in_year @ s_age @ flat_in_year) > 0.0


# --------------------------------------------------------------------------- #
# Anchor 1 — the λ = 0 oracle
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("noisy", [False, True])
def test_zero_penalty_reproduces_the_unpenalized_fit(noisy: bool) -> None:
    """Anchor 1, on the fitted surface rather than on coefficients.

    ``TensorMIModel`` and this model use different bases — patsy's main-effects
    parameterisation against the full Kronecker product — for the **same column
    space**. Least-squares projection is basis-independent, so at λ=0 the fitted
    values must agree to floating point even though the coefficient vectors are
    unrelated and of different length.

    This is the strongest correctness statement available for the new fitter and it
    costs nothing, because the oracle is already tested.
    """
    cells = _cells(noisy=noisy)
    reference = TensorMIModel(cells, age_df=6, year_df=3, basis="count").fit()
    mi_ref = reference.improvement_surface().mi_grid
    mi_pen = _penalized_mi(
        cells, k_age=7, k_year=4, lambda_age=0.0, lambda_year=0.0, knots="clamped"
    )
    np.testing.assert_allclose(mi_pen, mi_ref, atol=1e-10)


def test_zero_penalty_reproduces_the_unpenalized_dispersion() -> None:
    """The variance side of Anchor 1 — φ is what scales every band."""
    cells = _cells(noisy=True)
    reference = TensorMIModel(cells, age_df=6, year_df=3, basis="count").fit()
    fit = PenalizedTensorMIModel(cells, k_age=7, k_year=4, knots="clamped").fit()
    assert fit.edf_total == pytest.approx(fit.n_coef, abs=1e-8), (
        "at zero penalty every parameter is fully spent, so edf must equal n_coef"
    )
    assert fit.dispersion == pytest.approx(reference.dispersion, rel=1e-8)


# --------------------------------------------------------------------------- #
# The λ → ∞ limit, against a closed form from a different implementation
# --------------------------------------------------------------------------- #


def test_an_enormous_calendar_penalty_makes_improvement_constant_in_time() -> None:
    """The null-space limit, and it is checkable against ADR-184's linear margin.

    A second-difference penalty cannot see linear functions, so as λ_year grows η
    becomes linear in calendar year and fitted MI becomes **constant across the
    window** — the same surface ``TensorMIModel(year_df=1, year_degree=1)``
    produces. Two implementations, one closed form, and the agreement is what says
    the penalty acts on the margin it claims to.
    """
    cells = _cells(noisy=True)
    mi_pen = _penalized_mi(cells, k_age=7, k_year=6, lambda_age=0.0, lambda_year=1e12)
    span = mi_pen.max(axis=1) - mi_pen.min(axis=1)
    assert span.max() < 1e-6, f"MI is not constant in time: max span {span.max():.2e}"

    linear = TensorMIModel(cells, age_df=6, year_df=1, year_degree=1, basis="count").fit()
    mi_linear = linear.improvement_surface().mi_grid
    # Same limiting model, different route to it: agree to well inside a basis point.
    np.testing.assert_allclose(mi_pen.mean(axis=1), mi_linear.mean(axis=1), atol=2e-4)


def test_effective_df_falls_monotonically_in_the_penalty() -> None:
    """Between the two limits, and bounded by both.

    ``edf`` starts at the parameter count and decreases toward the null-space
    dimension. Monotonicity is the behavioural contract; the bounds are what make a
    reported ``edf`` interpretable at all (Anchor 4).
    """
    cells = _cells(noisy=True)
    edfs = [
        PenalizedTensorMIModel(cells, k_age=7, k_year=6, lambda_year=lam).fit().edf_total
        for lam in (0.0, 1e0, 1e3, 1e6, 1e12)
    ]
    assert all(a >= b - 1e-6 for a, b in itertools.pairwise(edfs)), (
        f"edf must not increase with the penalty: {[round(e, 3) for e in edfs]}"
    )
    assert edfs[0] > edfs[-1] + 1.0, "the penalty is doing nothing at all"
    assert edfs[-1] >= 2.0, "an order-2 penalty must leave at least the linear null space"


def test_a_penalty_on_one_margin_leaves_the_other_alone() -> None:
    """Penalising age must not flatten the calendar trend, which is the whole point
    of separate marginal penalties rather than one isotropic ridge."""
    cells = _cells(noisy=True)
    mi = _penalized_mi(cells, k_age=7, k_year=6, lambda_age=1e12, lambda_year=0.0)
    # The injected truth improves 1.5%/yr at every age; heavy AGE smoothing should
    # leave that intact rather than removing it.
    assert 0.005 < float(np.mean(mi)) < 0.030


# --------------------------------------------------------------------------- #
# Contract guards
# --------------------------------------------------------------------------- #


def test_a_negative_penalty_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="non-negative"):
        PenalizedTensorMIModel(_cells(noisy=False), lambda_year=-1.0)


def test_a_basis_too_small_for_the_degree_is_refused() -> None:
    """The Kronecker form uses FULL marginal bases, so the floor is degree + 1 --
    one higher than ``TensorMIModel``'s, and the message must say which it means."""
    with pytest.raises(PolarisValidationError, match="k_year=3 is below the full-basis minimum"):
        PenalizedTensorMIModel(_cells(noisy=False), k_year=3)


# --------------------------------------------------------------------------- #
# Per-margin edf — the two-sided guard the first implementation failed
# --------------------------------------------------------------------------- #


# NOTE: slice 1's `test_saturating_one_margin_drives_only_its_own_edf_to_zero` and
# `test_per_margin_edf_is_not_the_same_number_twice` were removed here, not dropped.
# The fields they guarded (`edf_age` / `edf_year`) were replaced in slice 2 by
# `shrinkage_age` / `shrinkage_year` under the amended Anchor 4, and both guards are
# carried onto the new names below —
# `test_shrinkage_reports_only_the_margin_that_was_penalised` (both directions) and
# `test_the_two_shrinkages_are_not_the_same_number_twice`. Recorded because a
# vanishing test is exactly what the PLAN/CONTINUATION contract exists to catch.


def test_the_two_shrinkages_are_not_the_same_number_twice() -> None:
    """The slice-1 defect, pinned against on the renamed quantity.

    The original per-margin split was inert — both fields returned the same number
    whichever axis was summed first — and eleven tests passed over it because all
    asserted on the total. Cheap insurance that the replacement has not collapsed
    the same way.
    """
    fit = PenalizedTensorMIModel(_cells(noisy=True), k_age=7, k_year=6, lambda_year=1e3).fit()
    assert abs(fit.shrinkage_age - fit.shrinkage_year) > 1.0, (
        "the two shrinkages are indistinguishable — the split has collapsed again"
    )


# --------------------------------------------------------------------------- #
# Isotropy — specified by PLAN slice 1 and missing from the first submission
# --------------------------------------------------------------------------- #


def test_the_fit_is_invariant_to_the_calendar_origin() -> None:
    """Difference penalties are scale-dependent, so this is where that would bite.

    Shifting `calendar_year` by a constant must not move the fitted surface: the
    knot sequence is built from the observed bounds, so it shifts with the data and
    the penalty sees the same coefficient geometry. The plan named this test and the
    first submission shipped without it or a line explaining its absence — which is
    the failure mode the PLAN/CONTINUATION contract exists to catch (PR #187 review
    [P1]).

    Asserted at a *penalised* λ as well as at zero, because at λ=0 the penalty is
    absent and the test would say nothing about the thing it is named for.
    """
    cells = _cells(noisy=True)
    shifted = cells.with_columns(pl.col("calendar_year") - 2012)

    for lam in (0.0, 1e3):
        base = PenalizedTensorMIModel(cells, k_age=7, k_year=6, lambda_year=lam).fit()
        moved = PenalizedTensorMIModel(shifted, k_age=7, k_year=6, lambda_year=lam).fit()
        np.testing.assert_allclose(moved.edf_total, base.edf_total, rtol=1e-8)

        # η itself, which is the strong form. Slice 3 briefly replaced this with the
        # MI comparison below on the stated grounds that "the origin shift moves η by
        # a constant the annual contrast differences out" — and that was **measured
        # false**: η is invariant to ~3e-15 and the difference has no constant
        # component at all, it is rounding noise. MI differences out any constant, so
        # the MI form cannot detect an η offset this one would (PR #189 review [P0]).
        eta_base = base._grid_design(_AGES, _YEARS) @ base.coef
        eta_moved = moved._grid_design(_AGES, _YEARS - 2012) @ moved.coef
        np.testing.assert_allclose(eta_moved, eta_base, atol=1e-9)

        # Kept alongside, not instead of: this is the caller-level statement.
        mi_base = base.improvement_surface(ages=_AGES, years=_YEARS).mi_grid
        mi_moved = moved.improvement_surface(ages=_AGES, years=_YEARS - 2012).mi_grid
        np.testing.assert_allclose(mi_moved, mi_base, atol=1e-9)


# --------------------------------------------------------------------------- #
# Slice 2 — the Anchor-4 reporting fix
# --------------------------------------------------------------------------- #


def _cells_with_factors(*, seed: int = 7) -> pl.DataFrame:
    """The fixture with a `sex` factor, so the additivity identity is non-trivial.

    Without factor columns `edf_factors` is 0 and `edf_tensor == edf_total`
    holds for free — the test would pass while asserting nothing.
    """
    rng = np.random.default_rng(seed)
    rows: list[tuple[int, int, str, float, float, float]] = []
    for age in _AGES:
        q0 = _q_base(float(age))
        for sex, multiplier in (("M", 1.15), ("F", 0.85)):
            actual = q0 * multiplier
            for year in _YEARS:
                if int(year) > int(_YEARS.min()):
                    actual *= 1.0 - _MI_TRUE
                rows.append(
                    (int(age), int(year), sex, q0, 6.0e4, float(rng.poisson(6.0e4 * actual)))
                )
    return pl.DataFrame(
        rows,
        schema=[
            "attained_age",
            "calendar_year",
            "sex",
            "q_base",
            "central_exposure",
            "death_count",
        ],
        orient="row",
    )


def test_the_per_term_edf_closes_against_the_factor_block() -> None:
    """The identity slice 1's split could not satisfy, on a fixture where it bites.

    `tr(F)` over the tensor block plus `tr(F)` over the factor block is `tr(F)` over
    everything, exactly. That is the whole reason this replaced the overlapping
    per-margin quantities: a reader can add the published numbers and get the right
    answer (amended Anchor 4).
    """
    fit = PenalizedTensorMIModel(_cells_with_factors(), k_age=7, k_year=6, lambda_year=1e3).fit()
    assert fit.factors == ("sex",), "the fixture must actually carry a factor"
    assert fit.edf_factors > 0.5, "a real factor must consume real degrees of freedom"
    assert fit.edf_tensor + fit.edf_factors == pytest.approx(fit.edf_total, abs=1e-9)


@pytest.mark.parametrize(
    ("penalised", "spared"),
    [("lambda_year", "lambda_age"), ("lambda_age", "lambda_year")],
)
def test_shrinkage_reports_only_the_margin_that_was_penalised(penalised: str, spared: str) -> None:
    """Slice 1's two-sided guard, carried onto the renamed quantity.

    A shrinkage is "dimensions this penalty removed", so the unpenalised margin must
    report ~0 and the penalised one must report real removal. Parametrised both ways
    because a quantity that responds correctly to one margin can still be reading
    the other.
    """
    cells = _cells(noisy=True)
    fit = PenalizedTensorMIModel(cells, k_age=7, k_year=6, **{penalised: 1e8, spared: 0.0}).fit()
    shrinkage = {"lambda_age": fit.shrinkage_age, "lambda_year": fit.shrinkage_year}
    assert shrinkage[spared] < 1e-6, (
        f"{spared} carries no penalty and must remove nothing, got {shrinkage[spared]:.4f}"
    )
    assert shrinkage[penalised] > 1.0, (
        f"a saturated {penalised} must remove real dimensions, got {shrinkage[penalised]:.4f}"
    )


# --------------------------------------------------------------------------- #
# Slice 2 — REML selection
# --------------------------------------------------------------------------- #


def _graded(kind: str):
    """Truths of increasing calendar complexity, all *representable in the basis*.

    The wiggle is scaled to the window rather than given a fixed period. A fixed
    period the basis cannot resolve makes REML correctly smooth it away, and the
    test would then be measuring the basis rather than the selector — which is what
    a 5.7-year sine over a 30-year window did during development.
    """
    span = float(_YEARS.max() - _YEARS.min())
    base = float(_YEARS.min())
    return {
        "const": lambda age, year: _MI_TRUE,
        "linear": lambda age, year: _MI_TRUE + 0.03 * (year - base) / span,
        "curved": lambda age, year: (
            _MI_TRUE + 0.020 * float(np.sin(2.0 * np.pi * (year - base) / span))
        ),
    }[kind]


def test_reml_selects_less_smoothing_as_the_truth_gets_wigglier() -> None:
    """The selector's whole job, and it is two-sided by construction.

    A selector that always chose maximum smoothing would satisfy the constant case
    and fail here; one that always chose minimum would do the reverse. Requiring the
    ladder to be **monotone** rules out both, which is the ADR-182 discipline this
    project applies to every verdict.

    Asserted on `edf_tensor` and `shrinkage_year` rather than `edf_total`: the total
    is dominated by the age margin and is a poor probe of calendar structure —
    measured during development, where a 30-year constant and a 30-year curved truth
    both landed at edf_total 36.4 while their calendar behaviour differed.
    """
    fits = {}
    for kind in ("const", "linear", "curved"):
        cells = _cells_from(_graded(kind))
        selected = select_lambdas_reml(cells, k_age=10, k_year=6)
        lam_age, lam_year = selected.lambda_age, selected.lambda_year
        fits[kind] = PenalizedTensorMIModel(
            cells, k_age=10, k_year=6, lambda_age=lam_age, lambda_year=lam_year
        ).fit()

    edf = [fits[k].edf_tensor for k in ("const", "linear", "curved")]
    assert edf[0] < edf[1] < edf[2], f"edf_tensor must rise with wiggliness, got {edf}"

    shrink = [fits[k].shrinkage_year for k in ("const", "linear", "curved")]
    assert shrink[0] > shrink[1] > shrink[2], (
        f"the calendar penalty must remove LESS as the truth gets wigglier, got {shrink}"
    )


def test_a_constant_truth_pins_lambda_to_the_search_bound_and_says_so() -> None:
    """A legitimate boundary hit, reported rather than hidden.

    Constant MI means η is linear in year, which lives in the penalty's null space
    and wants a λ larger than any grid expresses. The selector returns the bound and
    `lambda_is_at_bound` is how a caller learns the number means "at least this".
    """
    cells = _cells_from(_graded("const"))
    lam_year = select_lambdas_reml(cells, k_age=10, k_year=6).lambda_year
    assert lambda_is_at_bound(lam_year), (
        f"a null-space truth should saturate the search range, got {lam_year:.3g}"
    )
    assert not lambda_is_at_bound(10.0**3.5)


def test_selection_is_reproducible_within_the_process() -> None:
    """A grid has no optimiser state, so repeated selection is bit-identical.

    This is the cheap half of Anchor 3; the cross-process half is
    ``test_selection_is_reproducible_across_processes``, which is the one that
    matters — comparing two calls in one interpreter is exactly the weak check that
    let a false determinism claim ship in ADR-182.
    """
    cells = _cells(noisy=True)
    first = select_lambdas_reml(cells, k_age=7, k_year=6)
    second = select_lambdas_reml(cells, k_age=7, k_year=6)
    assert first == second


def test_selection_is_reproducible_across_processes() -> None:
    """Anchor 3, checked the only way that counts.

    ADR-182 shipped a determinism claim verified by comparing two renderings inside
    one interpreter; writing the real cross-process test falsified it. So this
    spawns fresh interpreters, which is also where BLAS threading decisions and
    library import order can differ.

    A grid search has no optimiser state to drift, so the expectation is *exact*
    equality of the repr — not a tolerance. If this ever needs a tolerance, the
    selection stopped being a grid and Anchor 3 needs revisiting rather than the
    test loosening.
    """
    script = textwrap.dedent(
        """
        import warnings
        warnings.filterwarnings("ignore")
        import numpy as np, polars as pl
        from polaris_re.analytics.experience_gam_penalized import select_lambdas_reml

        ages = np.arange(25, 96)
        years = np.arange(2012, 2020)
        rng = np.random.default_rng(7)
        rows = []
        for age in ages:
            q0 = 0.004 * float(np.exp(0.08 * (age - 45.0)))
            actual = q0
            for year in years:
                if int(year) > 2012:
                    actual *= 1.0 - 0.015
                rows.append((int(age), int(year), q0, 6.0e4, float(rng.poisson(6.0e4 * actual))))
        cells = pl.DataFrame(
            rows,
            schema=["attained_age", "calendar_year", "q_base",
                    "central_exposure", "death_count"],
            orient="row",
        )
        print(repr(select_lambdas_reml(cells, k_age=7, k_year=6)))
        """
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        ).stdout.strip()
        for _ in range(3)
    }
    assert len(outputs) == 1, f"selection differed across processes: {outputs}"


def test_the_grid_resolution_is_recorded_rather_than_implicit() -> None:
    """A grid buys determinism by giving up resolution; the price must be visible.

    `COARSE_STEP` / `REFINE_STEP` are module constants a caller can read, and the
    refinement is finer than the sweep — if that ever inverts, the refine pass is
    doing nothing and the selector silently has decade-level resolution.
    """
    assert REFINE_STEP < COARSE_STEP
    lo, hi = LAMBDA_LOG10_BOUNDS
    assert hi - lo >= 8.0, "the search range must span enough decades to find a null-space λ"


@pytest.mark.parametrize("kind", ["const", "curved"])
def test_reml_selection_beats_the_hand_tuned_configurations(kind: str) -> None:
    """The epic's thesis, at fixture scale — and it is allowed to fail here.

    PLAN §1: two hand adjustments (`year_df` 4->3, then `df == degree` 3->2) each
    moved a published ILEC finding, with nothing in the fit selecting them. The claim
    is that REML finds in one fit what took two epics and a maintainer run to find by
    hand.

    On real data the arbiter is SOA's own expected deaths; on a fixture it is the
    injected truth, which is a *stronger* arbiter because it carries no error of its
    own.

    **Parametrised over both regimes, and that is not decoration.** A constant truth
    lies *inside* the second-difference penalty's null space, so heavy smoothing is
    exactly right and the penalized fit gets a nearly free win — measured at 40x,
    which would be a dishonest number to quote as a general gain. The curved truth
    sits *outside* the null space and is the representative case, at ~2.3x. Testing
    only the first would let a selector that always smooths hard pass.

    If REML loses, that is data about the selector and belongs in the record — PLAN
    §6 row 1 already names the failure branch and says the independent check wins.
    """
    mi_fn = _graded(kind)
    cells = _cells_from(mi_fn)
    truth = np.array(
        [[float(mi_fn(float(age), int(year))) for year in _YEARS[1:]] for age in _AGES]
    )

    def rmse(grid: np.ndarray) -> float:
        return float(np.sqrt(np.mean((grid - truth) ** 2)))

    chosen = select_lambdas_reml(cells, k_age=10, k_year=6)
    lam_age, lam_year = chosen.lambda_age, chosen.lambda_year
    model = PenalizedTensorMIModel(
        cells, k_age=10, k_year=6, lambda_age=lam_age, lambda_year=lam_year
    )
    fit = model.fit()
    penalized = rmse(fit.improvement_surface(ages=_AGES, years=_YEARS).mi_grid)

    shipped = rmse(TensorMIModel(cells, age_df=6, year_df=3).fit().improvement_surface().mi_grid)
    hand_tuned = rmse(
        TensorMIModel(cells, age_df=6, year_df=2, year_degree=2).fit().improvement_surface().mi_grid
    )

    assert penalized < shipped, (
        f"[{kind}] REML ({penalized:.5f}) must beat the shipped cubic ({shipped:.5f})"
    )
    assert penalized < hand_tuned, (
        f"[{kind}] REML ({penalized:.5f}) must beat the hand-tuned quadratic ({hand_tuned:.5f})"
    )


def test_a_selected_fit_records_its_provenance_and_a_hand_set_one_does_not() -> None:
    """The distinction five docstrings claimed and no code provided.

    `reml_score` and `lambda_grid_step` were never written: `select_lambdas_reml`
    returned a bare tuple (slice 4 widened it to `LambdaSelection`, which does not
    change this), and a caller rebuilding the model got the field defaults —
    so both were always `None` and a selected surface was indistinguishable from a
    hand-set one, which is precisely what the docstrings said they were for
    (PR #188 review [P1]). Same class as #187's inert `edf` split: a field whose
    docstring describes behaviour the code does not have.
    """
    cells = _cells(noisy=True)
    selected = fit_reml(cells, k_age=7, k_year=6)
    hand_set = PenalizedTensorMIModel(cells, k_age=7, k_year=6, lambda_year=1.0).fit()

    assert selected.reml_score is not None
    assert selected.lambda_grid_step == REFINE_STEP
    assert hand_set.reml_score is None
    assert hand_set.lambda_grid_step is None


def test_the_recorded_grid_step_is_the_step_actually_swept() -> None:
    """Asserting against the module default cannot catch a hardcoded report.

    `fit_reml` previously passed `lambda_grid_step=REFINE_STEP` — the constant, not
    the resolution used — and forwarded `**model_kwargs` to the model constructor as
    well as the selector, so `refine_step=0.5` raised `TypeError` before reaching the
    grid. That made the report unfalsifiable rather than correct: the only input that
    could expose it crashed first, and the test above passes either way because it
    compares against the same constant the code hardcoded (PR #188 review round 2).

    So this sweeps a **non-default** resolution. It is the assertion that would have
    failed on the old code, which is the only kind worth adding here.
    """
    coarser = 0.5
    assert coarser != REFINE_STEP, "the override must differ from the default to test anything"

    fit = fit_reml(_cells(noisy=True), k_age=7, k_year=6, refine_step=coarser)

    assert fit.lambda_grid_step == coarser
    # λ is a grid point of the sweep that produced it, so a coarser step must leave
    # log10 λ on the coarser lattice. This is what makes the recorded step meaningful
    # rather than a label: it describes the lattice the answer actually came from.
    for lam in (fit.lambda_age, fit.lambda_year):
        residual = np.log10(lam) / coarser
        np.testing.assert_allclose(residual, np.round(residual), atol=1e-9)


def test_the_grid_resolution_is_fine_enough_that_edf_does_not_visibly_step() -> None:
    """PLAN slice 2's fourth test, restored — and it measures rather than asserts.

    The grid retired the *jitter-absorption* half of the plan's quantisation test
    (there is no optimiser to jitter), and ADR-186 explains that. It did **not**
    retire the other half: is 0.25 decade fine enough that `edf` moves smoothly
    rather than in visible steps? That question applies to a grid exactly as much,
    and it is the price ADR-186 says the grid paid. The test was dropped without a
    line recording it — the same silent-omission failure #187's review caught with
    the isotropy test (PR #188 review [P1]).

    Measured: the largest `edf_tensor` step between adjacent grid points, as a
    fraction of the total range swept. A coarse grid would show one or two large
    jumps; a fine one shows many small ones.
    """
    cells = _cells(noisy=True)
    log_lambdas = np.arange(0.0, 6.0 + REFINE_STEP / 2.0, REFINE_STEP)
    edfs = np.array(
        [
            PenalizedTensorMIModel(cells, k_age=7, k_year=6, lambda_year=float(10.0**log_lambda))
            .fit()
            .edf_tensor
            for log_lambda in log_lambdas
        ]
    )
    total_range = float(edfs.max() - edfs.min())
    largest_step = float(np.abs(np.diff(edfs)).max())
    assert total_range > 1.0, "the sweep must actually move edf, or it measures nothing"
    assert largest_step / total_range < 0.15, (
        f"edf steps visibly at {REFINE_STEP} decade resolution: largest single step "
        f"{largest_step:.3f} is {largest_step / total_range:.1%} of the {total_range:.3f} "
        f"range swept. The grid is too coarse and ADR-186's resolution trade needs revisiting."
    )


# --------------------------------------------------------------------------- #
# Slice 3 — Anchor 2, and the first coverage study this project has run
# --------------------------------------------------------------------------- #


def test_the_penalized_surface_is_built_by_the_shared_band_layer() -> None:
    """Anchor 2, asserted as an identity rather than as a resemblance.

    The claim is not "the penalized bands look like the others" but "they are
    produced by the same function". So the test rebuilds the expected surface by
    calling `mi_surface_from_design` directly on the fit's own design and
    covariance and requires **exact equality** — a reimplementation that happened
    to agree to 1e-12 would still be a second band layer, which is the thing
    Anchor 2 forbids.
    """
    fit = PenalizedTensorMIModel(_cells(noisy=True), k_age=7, k_year=6, lambda_year=1e3).fit()
    surface = fit.improvement_surface(ages=_AGES, years=_YEARS)

    tensor = fit._grid_design(_AGES, _YEARS)
    pad = fit.n_coef - fit.n_tensor
    design = (
        np.hstack([tensor, np.zeros((tensor.shape[0], pad), dtype=np.float64)]) if pad else tensor
    )
    expected = mi_surface_from_design(design, fit.coef, fit.cov, _AGES, _YEARS, 0.95)

    for attr in ("mi_grid", "mi_lower", "mi_upper"):
        assert np.array_equal(getattr(surface, attr), getattr(expected, attr)), (
            f"{attr} is not bit-identical to the shared layer's output"
        )


def test_the_window_contrast_telescopes_through_the_penalized_bands() -> None:
    """A multi-year window must equal the compounded annual steps, exactly.

    η is linear in the coefficients, so the contrast for a 2012->2019 window is the
    **sum** of the annual contrasts, and improvement compounds:
    ``1 - MI_window == prod(1 - MI_annual)``. This is the identity Anchor 2 names,
    and it holds for any covariance because it is a property of the contrast, not of
    ``V`` — which is precisely why the layer can be shared.
    """
    fit = PenalizedTensorMIModel(_cells(noisy=True), k_age=7, k_year=6, lambda_year=1e3).fit()
    annual = fit.improvement_surface(ages=_AGES, years=_YEARS).mi_grid
    window = fit.improvement_surface(
        ages=_AGES, years=np.array([_YEARS.min(), _YEARS.max()], dtype=np.int64)
    ).mi_grid

    np.testing.assert_allclose(1.0 - window[:, 0], np.prod(1.0 - annual, axis=1), rtol=1e-10)


def test_the_band_scales_with_the_square_root_of_the_dispersion() -> None:
    """φ enters only through ``V``, so scaling φ scales the band's half-width in log
    space by ``√φ`` — the quasi-Poisson correction the reports rely on.

    Asserted on the log contrast rather than on MI, because ``1 - exp(d ± z·se)`` is
    non-linear and the clean proportionality lives one step up.
    """
    fit = PenalizedTensorMIModel(_cells(noisy=True), k_age=7, k_year=6, lambda_year=1e3).fit()
    tensor = fit._grid_design(_AGES, _YEARS)
    pad = fit.n_coef - fit.n_tensor
    design = (
        np.hstack([tensor, np.zeros((tensor.shape[0], pad), dtype=np.float64)]) if pad else tensor
    )

    base = mi_surface_from_design(design, fit.coef, fit.cov, _AGES, _YEARS, 0.95)
    quadrupled = mi_surface_from_design(design, fit.coef, 4.0 * fit.cov, _AGES, _YEARS, 0.95)

    # half-width in log space: log(1 - mi_lower) - d, and d is common to both.
    half_base = np.log(1.0 - base.mi_lower) - np.log(1.0 - base.mi_grid)
    half_quad = np.log(1.0 - quadrupled.mi_lower) - np.log(1.0 - quadrupled.mi_grid)
    np.testing.assert_allclose(half_quad, 2.0 * half_base, rtol=1e-9)


_COVERAGE_REPLICATES = 200
"""The plan's figure. Monte-Carlo SE on a single cell at p=0.95 is
``√(0.95·0.05/200) ≈ 1.5pp``, which is small against the effects below (the
smallest gap reported is 2.4pp) and large enough that the assertions are banded
rather than pinned to the fourth decimal."""


def _quadratic_mi(age: float, year: int) -> float:
    """MI quadratic in year — **outside** the penalty null space, **inside** both bases.

    This distinction is the whole design of the coverage study. A second-difference
    penalty cannot see linear functions, so a constant MI sits in its null space
    where shrinkage is free and coverage flatters the penalized estimator. A
    quadratic MI accumulates to a cubic η, which a cubic P-spline at ``k_year=6``
    and patsy's ``bs(df=3)`` (a global cubic) each represent **exactly** — so any
    coverage shortfall here is the band's, not the basis's.
    """
    return 0.015 + 0.006 * ((year - 2015.5) / 3.5) ** 2


def _sine_mi(age: float, year: int) -> float:
    """A full sine cycle over eight years — neither basis can resolve it.

    Kept deliberately, and reported separately, because it measures **bias** rather
    than band calibration. Slice 2 lost a day to exactly this confusion: a fixture
    whose truth the basis could not represent looked like a broken selector.
    """
    return 0.015 + 0.010 * np.sin(2.0 * np.pi * (year - 2012) / 8.0)


_TRUTHS = {"nullspace": None, "curved": _quadratic_mi, "unrepresentable": _sine_mi}


@functools.cache
def _coverage(kind: str, estimator: str) -> tuple[float, float, float, float]:
    """(overall, young<=50, old>=80, mean band width) over seeded replicates.

    λ is selected **once**, on a held-out replicate, and every replicate is then fit
    at that λ. This is coverage *conditional on λ*, which is what
    ``Vb = (XᵀWX + S)⁻¹φ`` actually claims — it carries no smoothing-parameter
    uncertainty. Re-selecting per replicate would measure a different and more
    favourable-sounding quantity while the band being tested stayed the same one.
    """
    fn = _TRUTHS[kind]

    def cells_at(seed: int) -> pl.DataFrame:
        return _cells(noisy=True, seed=seed) if fn is None else _cells_from(fn, seed=seed)

    if fn is None:
        truth = np.full((len(_AGES), len(_YEARS) - 1), _MI_TRUE, dtype=np.float64)
    else:
        truth = np.array(
            [[fn(float(a), int(y)) for y in _YEARS[1:]] for a in _AGES], dtype=np.float64
        )

    # Seed 999 is OUTSIDE the 1000..1199 evaluation range. An earlier revision
    # selected on 1000 while the loop started at 1000, so replicate 0 shared the
    # selection data and "held-out" was false in a published ADR — one replicate in
    # 200, immaterial to the number and material to the claim (PR #189 review [P1]).
    chosen = select_lambdas_reml(cells_at(999), k_age=7, k_year=6)
    lam_age, lam_year = chosen.lambda_age, chosen.lambda_year
    hits = np.zeros_like(truth)
    widths = []
    for r in range(_COVERAGE_REPLICATES):
        cells = cells_at(1000 + r)
        if estimator == "penalized":
            surface = (
                PenalizedTensorMIModel(
                    cells, k_age=7, k_year=6, lambda_age=lam_age, lambda_year=lam_year
                )
                .fit()
                .improvement_surface(ages=_AGES, years=_YEARS)
            )
        else:
            surface = (
                TensorMIModel(cells, age_df=6, year_df=3)
                .fit()
                .improvement_surface(ages=_AGES, years=_YEARS)
            )
        hits += ((surface.mi_lower <= truth) & (truth <= surface.mi_upper)).astype(float)
        widths.append(float(np.mean(surface.mi_upper - surface.mi_lower)))
    cov = hits / _COVERAGE_REPLICATES
    return (
        float(cov.mean()),
        float(cov[_AGES <= 50].mean()),
        float(cov[_AGES >= 80].mean()),
        float(np.mean(widths)),
    )


def test_the_delta_method_bands_are_calibrated_after_all() -> None:
    """**The pre-registered hypothesis was that these under-cover. They do not.**

    PLAN slice 3 wrote: *"If the existing bands under-cover at the death-poor young
    end, that is a finding about every committed report, and it should be published
    whichever way it comes out."* It comes out the other way. Measured at 200
    replicates against nominal 95%:

    | truth | overall | young <= 50 | old >= 80 |
    |---|---|---|---|
    | constant MI (null space) | **0.9567** | 0.9589 | 0.9475 |
    | quadratic MI (representable) | **0.9586** | 0.9574 | 0.9533 |

    Young ages are the *best*-covered region, not the worst — so the ADR-184
    variance artifact at age 45 is a story about the **point estimate's** sampling
    spread, and the band was honest about it all along. The committed reports'
    bands stand.

    These two rows are the most trustworthy numbers in the study, because the
    unpenalized fit has no λ and so cannot inherit the selection instability that
    `test_reml_lambda_selection_is_unstable_across_replicates` measures.
    """
    for kind in ("nullspace", "curved"):
        overall, young, old, _ = _coverage(kind, "delta")
        assert 0.93 <= overall <= 0.98, f"[{kind}] delta-method coverage {overall:.4f}"
        assert young >= 0.93, (
            f"[{kind}] young-age coverage {young:.4f} — the pre-registered "
            "under-coverage hypothesis would be back in play"
        )
        assert old >= 0.93, f"[{kind}] old-age coverage {old:.4f}"


def test_reml_lambda_selection_is_unstable_across_replicates() -> None:
    """**The finding that reframes every penalized number below.**

    λ is chosen by REML from one realisation of an eight-year window, and across
    replicates of the *same truth* the choice moves enormously — measured on the
    quadratic fixture, log10 λ_age ranges over roughly five decades (2.50 to 8.00 on
    seeds 995-1002). The selected λ is one draw from a wide distribution, not a
    property of the truth.

    This is asserted rather than merely noted because it is the mechanism behind a
    correction: slice 3 first reported penalized coverage of 0.9260 on the quadratic
    truth, measured at a λ selected on seed 1000. Fixing an unrelated defect (the
    selection replicate was not actually held out, PR #189 review [P1]) moved the
    selection seed to 999 and the same measurement to **0.8710** — a 5.5-point swing
    caused by nothing but which replicate λ was read off.

    A characterisation test: if a future slice stabilises selection (averaging over
    replicates, or a proper marginal-likelihood treatment), this assertion is
    *supposed* to fail, and that failure is the signal the caveat can be lifted.
    """
    # All eight seeds the docstring and ADR-187 finding 2 cite. An earlier revision
    # swept only 995-1000 while claiming 995-1002 — the assertion held on the six, so
    # nothing was wrong, but a docstring describing seeds the test does not visit is
    # the claim-set defect this module keeps catching in itself (PR #189 review [P2]).
    spread = []
    for seed in (995, 996, 997, 998, 999, 1000, 1001, 1002):
        lam_age = select_lambdas_reml(
            _cells_from(_quadratic_mi, seed=seed), k_age=7, k_year=6
        ).lambda_age
        spread.append(float(np.log10(lam_age)))

    assert max(spread) - min(spread) > 1.0, (
        f"log10 lambda_age spread across replicates is only {max(spread) - min(spread):.2f} "
        "decades. If selection has been stabilised, ADR-187's instability caveat and "
        "the conditional-coverage framing both need revisiting rather than deleting."
    )


def test_the_penalized_bands_buy_width_and_pay_coverage() -> None:
    """The trade, measured — and quoted with the instability that bounds it.

    | truth | estimator | coverage | mean width |
    |---|---|---|---|
    | constant MI (null space) | penalized | 0.9733 | 0.00369 |
    | constant MI | delta | 0.9567 | 0.03045 |
    | quadratic MI | penalized | **0.8710** | 0.00688 |
    | quadratic MI | delta | 0.9586 | 0.03044 |

    In the null space the penalized band **over**-covers at an eighth of the width:
    the truth is what the penalty shrinks toward, so shrinkage costs no bias there.
    That is the flattering regime and it is not the headline, for the same reason
    slice 2 refused to quote its 40x.

    **The headline is the quadratic row: 87.1% against a nominal 95%, at 4.4x
    narrower.** An earlier revision reported 92.6% here and framed the cost as "2.4
    points"; that number came from a different selection seed and does not survive
    one. What survives is the *direction* — narrower, and under-covering — so the
    assertions below pin the direction and a generous band, not the decimals.
    """
    p_null, _, _, w_null = _coverage("nullspace", "penalized")
    d_null, _, _, wd_null = _coverage("nullspace", "delta")
    p_curve, _, _, w_curve = _coverage("curved", "penalized")
    d_curve, _, _, wd_curve = _coverage("curved", "delta")

    assert p_null > d_null, f"null-space: penalized {p_null:.4f} should over-cover vs {d_null:.4f}"
    assert p_curve < d_curve, (
        f"curved: the trade only exists if the penalized band ({p_curve:.4f}) covers "
        f"LESS than the delta band ({d_curve:.4f}) while being narrower"
    )
    assert 0.82 <= p_curve <= 0.95, (
        f"curved: penalized coverage {p_curve:.4f} is outside the range this study "
        "reports. Below 0.82 the band is not usable as a 95% interval at all; above "
        "0.95 the trade described here is gone. The band is wide because the selected "
        "lambda is itself a wide-variance draw."
    )
    assert wd_null / w_null > 5.0, f"null-space width ratio {wd_null / w_null:.1f}x"
    assert wd_curve / w_curve > 3.5, f"curved width ratio {wd_curve / w_curve:.1f}x"


def test_the_unpenalized_band_collapses_while_the_penalized_band_does_not_quite() -> None:
    """Neither interval covers a truth its basis cannot reach — and that is bias.

    | estimator | overall | young <= 50 | old >= 80 |
    |---|---|---|---|
    | penalized | 0.8995 | 0.9447 | **0.8282** |
    | delta | 0.8461 | 0.9436 | **0.6687** |

    Reported because it bounds what the two calibration results above mean. They say
    the arithmetic is right when the model is; they do not say a real book is inside
    either basis.

    **A withdrawn claim lives here.** An earlier revision reported 0.7597 vs 0.8461
    and concluded that the penalized estimator "degrades further — shrinkage adds
    bias on top of approximation error". At the corrected selection seed the two are
    level (0.8505 vs 0.8461, inside the ~1.5pp Monte-Carlo SE). The ordering was an
    artifact of which replicate λ was read off, and it is withdrawn rather than
    re-argued in the other direction: what is robust is that **both** collapse.

    **Updated 2026-08-19 (ADR-197 resolution, maintainer-authorized).** The
    penalized column above moved when ``experience_gam_penalized.reml_score``'s
    missing penalized-deviance term was fixed (`select_lambdas_reml`'s seed-999
    selection legitimately changed, which is what `_coverage` fits every replicate
    at) — 0.8505/0.9073/0.7598 -> 0.8995/0.9447/0.8282, a real, derived, measured
    consequence of the corrected λ selection, not a tuned number. The delta column
    is unaffected (`TensorMIModel` has no λ, so it never calls `reml_score`) and is
    reproduced unchanged as the control that shows so. **The "shared failure ~67-76%
    for both" framing is retired**: the fix closed roughly a third of the penalized
    estimator's old-age coverage gap to nominal (95%) while the delta method's did
    not move, so old age is no longer a *shared* failure of similar magnitude — it
    is now primarily the delta method's. Both estimators still fall short of nominal
    coverage at old ages (basis-representability bias, the point of this fixture),
    which is what the assertions below continue to check.
    """
    p_overall, _, p_old, _ = _coverage("unrepresentable", "penalized")
    d_overall, _, d_old, _ = _coverage("unrepresentable", "delta")

    assert p_overall < 0.90 and d_overall < 0.90, (
        f"misspecification no longer costs coverage (penalized {p_overall:.4f}, "
        f"delta {d_overall:.4f}) — the fixture may have become representable"
    )
    assert d_old < 0.80, f"delta-method old-age collapse: {d_old:.4f}"
    # The corrected λ selection lifted the penalized estimator's old-age coverage
    # above the old 0.80 bound (now ~0.8282) — a real, measured improvement, not a
    # tuned threshold. It still falls short of nominal (0.95), which is the
    # continuing claim this assertion checks.
    assert 0.80 <= p_old < 0.90, f"penalized old-age coverage moved outside 0.80-0.90: {p_old:.4f}"


def test_the_factor_block_is_padded_with_zeros_and_the_fill_does_not_matter() -> None:
    """The `pad > 0` branch of `improvement_surface`, which no other test reaches.

    Every other fixture that reaches the extractor is factor-free, so `n_coef ==
    n_tensor` and the branch is dead in the suite — while the `n_tensor` docstring
    argues at length for exactly its correctness (PR #189 review [P1]). A docstring
    defending an untested branch is the shape this epic has now hit three times.

    The claim under test is **fill-invariance**: factor columns are calendar-invariant
    at the reference, so they cancel in the annual contrast and the surface must not
    move if they are filled with ones instead of zeros. That is what makes zeros a
    correct choice rather than a convenient one — and it holds for the variance too,
    since the contrast rows are zero in those positions either way.
    """
    fit = PenalizedTensorMIModel(_cells_with_factors(), k_age=7, k_year=6, lambda_year=1e3).fit()
    assert fit.n_coef > fit.n_tensor, "the fixture must actually exercise the padding branch"

    surface = fit.improvement_surface(ages=_AGES, years=_YEARS)
    np.testing.assert_allclose(surface.mi_grid.mean(), _MI_TRUE, atol=2e-3)

    tensor = fit._grid_design(_AGES, _YEARS)
    pad = fit.n_coef - fit.n_tensor
    ones_filled = mi_surface_from_design(
        np.hstack([tensor, np.ones((tensor.shape[0], pad), dtype=np.float64)]),
        fit.coef,
        fit.cov,
        _AGES,
        _YEARS,
        0.95,
    )
    for attr in ("mi_grid", "mi_lower", "mi_upper"):
        np.testing.assert_allclose(getattr(ones_filled, attr), getattr(surface, attr), atol=1e-14)


# --------------------------------------------------------------------------- #
# Slice 4 — selector robustness, and an interval that does not condition on λ
# --------------------------------------------------------------------------- #

_ABORT_SEED = 1098
"""The replicate ADR-187 finding 5 names, and the fixture these tests still use.

**The non-convergence at this seed is NOT portable, and the tests below no longer
depend on it.** The first version of them asserted that
`log10 λ = (-1, 8)` genuinely fails to converge here, which it does on the container
the study ran in — and does *not* on CI's Python 3.13 runner, where the same corner
converges and three tests failed on a premise rather than on a contract (PR #190 CI
round 1). Everything else about that selection was bit-for-bit portable: same λ, same
166 grid points evaluated, REML score agreeing to the 11th digit. Only whether one
badly-conditioned IRLS crosses a deviance tolerance in 100 iterations moved, which is
BLAS accumulation order — the same mechanism ADR-184 amendment 2 recorded when it
falsified this project's byte-for-byte reproducibility claim.

So the failure is **forced** at exactly the corner ADR-187 names (see
`_raise_at_corner`) instead of being fished for. That is strictly stronger: the
contract under test is "a non-converging point is rejected and the search survives",
and forcing the failure asserts it on every platform, where the seed asserted it on
one and silently asserted nothing on the others."""

_ABORT_CORNER = (-1.0, 8.0)
"""`log10 (λ_age, λ_year)` — essentially unpenalized in age, saturated in year. The
coarse sweep visits it on every call, which is what made ADR-187 finding 5 fatal
rather than rare."""


def _raise_at_corner(
    monkeypatch: pytest.MonkeyPatch, corner: tuple[float, float] = _ABORT_CORNER
) -> None:
    """Make the penalized fit fail at one grid point, exactly as the real one did.

    Patched at `PenalizedTensorMIModel.fit`, so the exception travels the identical
    path a real IRLS failure takes — out of the fit, through `_fit_and_score`, into the
    selector's `except`. Targeted by λ rather than by call count so it is independent of
    sweep order, and it fires in the refinement pass too if the corner is revisited.
    """
    real_fit = PenalizedTensorMIModel.fit

    def fit_or_fail(self: PenalizedTensorMIModel, **kwargs: object) -> object:
        at = (
            round(float(np.log10(self.lambda_age)), 6),
            round(float(np.log10(self.lambda_year)), 6),
        )
        if at == corner:
            raise PolarisComputationError(
                "Penalized IRLS did not converge in 100 iterations (forced by test)."
            )
        return real_fit(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(PenalizedTensorMIModel, "fit", fit_or_fail)


def test_a_non_converging_grid_point_is_rejected_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-187 finding 5 — and the search must now complete over it.

    `select_lambdas_reml` used to let `PolarisComputationError` out of its inner
    scoring call, so the corner `log10 λ = (-1, 8)` took the entire search down with
    it. The coarse sweep visits that corner on **every** call, so on the ~1-in-100
    replicates where it failed, the whole selection failed. Slice 6 runs this on a
    125k-cell book, where that is a failed production run rather than a failed test.

    Two-sided by construction: **exactly one** point must be rejected, so a change that
    swallowed failures wholesale, or that stopped visiting the corner at all, fails here
    rather than quietly retiring the guard. See `_ABORT_SEED` on why the failure is
    forced rather than fished for.
    """
    cells = _cells_from(_quadratic_mi, seed=_ABORT_SEED)
    # Not necessarily rejection-free — on some platforms the corner genuinely fails
    # here too. It is the reference for the winner and the grid size, not for the count.
    unforced = select_lambdas_reml(cells, k_age=7, k_year=6)

    _raise_at_corner(monkeypatch)
    selection = select_lambdas_reml(cells, k_age=7, k_year=6)

    assert selection.n_rejected == 1, (
        f"expected exactly the one forced corner to be rejected, got "
        f"{selection.n_rejected} of {selection.n_evaluated}"
    )
    assert selection.n_evaluated == unforced.n_evaluated, (
        "rejecting a point must not change how much of the grid is searched"
    )
    assert np.isfinite(selection.reml_score)
    # The corner is a bad λ, so discarding it must not move the winner. This is the
    # assertion that says the rejection is *harmless*, not merely survivable.
    assert (selection.lambda_age, selection.lambda_year) == (
        unforced.lambda_age,
        unforced.lambda_year,
    )


def test_the_rejected_count_reaches_the_fit_and_a_hand_set_fit_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A search that discarded points must say so where a reader will look.

    The count is useless on the selection object alone: `fit_reml` is the entry point
    (ADR-186 amendment 2), so a caller who never touches `LambdaSelection` would get a
    surface with a silently-truncated grid behind it. Both the count and its
    denominator are carried onto the fit, and both are `None` for a hand-set λ, which
    is the same provenance distinction `reml_score` and `lambda_grid_step` draw.
    """
    hand_set = PenalizedTensorMIModel(_cells(noisy=True), k_age=7, k_year=6, lambda_year=1.0).fit()

    _raise_at_corner(monkeypatch)
    fit = fit_reml(_cells_from(_quadratic_mi, seed=_ABORT_SEED), k_age=7, k_year=6)

    assert fit.n_rejected_points == 1
    assert fit.n_evaluated_points is not None
    assert fit.n_evaluated_points > fit.n_rejected_points
    assert hand_set.n_rejected_points is None
    assert hand_set.n_evaluated_points is None


def test_a_grid_with_no_converging_point_raises_rather_than_inventing_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejecting every point must not return the grid centre wearing the right type.

    The rejection branch scores a failure `+inf` and keeps the running best, and the
    running best is seeded at the grid centre. If nothing ever beats `+inf` that
    centre is returned as though it had been selected — a fabricated λ, with a
    `reml_score` of `inf`, indistinguishable by type from a real selection. This is
    the failure mode the fix could have introduced while removing the one it targeted.
    """
    import polaris_re.analytics.experience_gam_penalized as module

    def never_converges(*_args: object, **_kwargs: object) -> object:
        raise PolarisComputationError("Penalized IRLS did not converge (forced).")

    monkeypatch.setattr(module.PenalizedTensorMIModel, "fit", never_converges)

    with pytest.raises(PolarisComputationError, match="rejected every one of"):
        select_lambdas_reml(_cells(noisy=True), k_age=7, k_year=6)


@pytest.mark.parametrize("gamma", [1.0, 1.4, 2.0])
def test_gamma_is_recorded_on_the_fit_it_selected(gamma: float) -> None:
    """A λ chosen under gamma != 1 is not comparable with one chosen under gamma=1.

    So the fit carries the gamma that produced it. A report showing the λ without the gamma
    invites exactly the comparison the two numbers do not support.
    """
    fit = fit_reml(_cells_from(_quadratic_mi), k_age=7, k_year=6, gamma=gamma)
    assert fit.gamma == gamma


def test_gamma_of_one_leaves_the_criterion_bit_identical() -> None:
    """gamma enters as the scale parameter, and at gamma=1 every gamma term must vanish exactly.

    Not approximately: `0.5·D/gamma` and the `-(p-r)·log(gamma)/2` offset both collapse to the
    pre-gamma expression at gamma=1, so slice 2's selected λ and REML scores are unmoved. This
    is what lets the eleven slice-2 selection tests stand as a regression guard on
    slice 4 rather than being re-baselined.
    """
    cells = _cells(noisy=True)
    model = PenalizedTensorMIModel(cells, k_age=7, k_year=6, lambda_age=1e2, lambda_year=1e3)
    fit = model.fit()
    context = model.design_context
    assert context is not None

    penalty = np.zeros((context.design.shape[1],) * 2, dtype=np.float64)
    penalty[: context.n_tensor, : context.n_tensor] = 1e2 * context.s_age + 1e3 * context.s_year

    default = reml_score(context.deaths, context.design, context.offset, fit.coef, penalty)
    explicit = reml_score(
        context.deaths, context.design, context.offset, fit.coef, penalty, gamma=1.0
    )
    assert default == explicit


def test_gamma_above_one_selects_a_smoother_fit() -> None:
    """Wood's gamma inflates the cost of complexity, so `edf` must fall monotonically.

    Two-sided by construction: an implementation that ignored gamma, or applied it to the
    wrong term, would leave `edf` flat or move it the other way. The ladder runs well
    past mgcv's recommended 1.4 so the direction is legible against grid resolution —
    at 0.25 decades a small gamma change can leave λ on the same grid point, which is a
    property of the grid rather than a failure of gamma.

    **Direction only, and deliberately.** ADR-187 amendment 2 measured the "REML
    undersmooths" claim on an age-flat fixture and found it does *not* reproduce on an
    age-varying one, so gamma is carried here for mgcv parity (PLAN Anchor 8), **not** as
    a remedy for a bias this project has demonstrated.
    """
    cells = _cells_from(_quadratic_mi)
    edfs = [fit_reml(cells, k_age=7, k_year=6, gamma=g).edf_tensor for g in (1.0, 1.4, 2.0, 5.0)]

    assert all(later <= earlier + 1e-9 for earlier, later in itertools.pairwise(edfs)), (
        f"edf must not rise with gamma: {edfs}"
    )
    assert edfs[-1] < edfs[0] - 0.5, (
        f"gamma has essentially no effect on complexity: {edfs[0]:.3f} -> {edfs[-1]:.3f}. "
        "Either it is not reaching the criterion or it is applied to a term that does "
        "not trade off against the deviance."
    )


def test_a_non_positive_gamma_is_refused() -> None:
    """gamma is a scale parameter; zero divides and negative inverts the criterion."""
    cells = _cells(noisy=True)
    model = PenalizedTensorMIModel(cells, k_age=7, k_year=6, lambda_year=1.0)
    fit = model.fit()
    context = model.design_context
    assert context is not None
    penalty = np.zeros((context.design.shape[1],) * 2, dtype=np.float64)

    for bad in (0.0, -1.0):
        with pytest.raises(PolarisValidationError, match="gamma must be positive"):
            reml_score(context.deaths, context.design, context.offset, fit.coef, penalty, gamma=bad)


def test_the_unconditional_correction_is_positive_semidefinite() -> None:
    """`J V_rho Jᵀ` cannot have a negative eigenvalue, and that is what makes it safe.

    PSD is not a stylistic preference — it is the property that guarantees the
    unconditional band is never *narrower* than the conditional one along any
    contrast, including contrasts no test enumerates. `V_rho` is built by eigen-flooring
    a symmetrised Hessian precisely so this holds even when the Hessian itself is
    indefinite, which it can be: λ comes from a grid point, not a stationary point.
    """
    cells = _cells_from(_quadratic_mi)
    selection = select_lambdas_reml(cells, k_age=7, k_year=6)
    extra = smoothing_uncertainty(
        cells,
        lambda_age=selection.lambda_age,
        lambda_year=selection.lambda_year,
        k_age=7,
        k_year=6,
    )

    correction = extra.correction
    np.testing.assert_allclose(correction, correction.T, atol=1e-18)
    smallest = float(np.linalg.eigvalsh(correction).min())
    scale = float(np.abs(correction).max())
    assert smallest > -1e-10 * max(scale, 1.0), f"correction has eigenvalue {smallest:.3e}"

    np.testing.assert_allclose(extra.v_rho, extra.v_rho.T, atol=1e-12)
    assert float(np.linalg.eigvalsh(extra.v_rho).min()) > 0.0
    assert extra.log_step == KS_LOG_STEP
    assert extra.jacobian.shape[1] == 2


def test_the_unconditional_band_is_wider_than_the_conditional_one() -> None:
    """The one-line direction check that a sign error breaks.

    The Kass-Steffey term is **added** to `Vb`, so every band half-width must grow —
    at every age, at every transition, not merely on average. A subtraction, or a
    Jacobian with a flipped finite difference, would still produce a plausible-looking
    surface and a plausible-looking mean width; it would not survive a cell-wise
    comparison.

    The point estimate must not move at all: the correction touches only the
    covariance, so `mi_grid` is the same surface either way.
    """
    cells = _cells_from(_quadratic_mi)
    conditional = fit_reml(cells, k_age=7, k_year=6)
    unconditional = fit_reml(cells, k_age=7, k_year=6, unconditional=True)

    assert conditional.band_is_unconditional is False
    assert unconditional.band_is_unconditional is True
    assert unconditional.lambda_age == conditional.lambda_age
    assert unconditional.lambda_year == conditional.lambda_year

    band_c = conditional.improvement_surface(ages=_AGES, years=_YEARS)
    band_u = unconditional.improvement_surface(ages=_AGES, years=_YEARS)

    np.testing.assert_allclose(band_u.mi_grid, band_c.mi_grid, rtol=1e-12)
    width_c = band_c.mi_upper - band_c.mi_lower
    width_u = band_u.mi_upper - band_u.mi_lower
    assert np.all(width_u >= width_c - 1e-15), (
        f"the correction narrowed {int(np.sum(width_u < width_c - 1e-15))} cells — "
        "an additive PSD term cannot do that, so the sign or the Jacobian is wrong"
    )
    assert float(np.mean(width_u) / np.mean(width_c)) > 1.0


def test_the_smoothing_variance_matches_the_measured_lambda_spread() -> None:
    """An independent check on `V_rho`, against a number measured a different way.

    ADR-187 amendment 1 measured λ's across-replicate spread empirically — 0.75
    decades in log10 λ_age on the age-varying truth, 5.50 on the age-flat one. `V_rho`
    claims the same quantity from a *single* dataset, via the curvature of the REML
    criterion. The two have no implementation in common, so agreement to an order of
    magnitude is real evidence and disagreement by orders would mean one of them is
    not measuring λ's sampling variance at all.

    Banded loosely on purpose: a Hessian-based standard error and an eight-seed
    empirical range are different estimators of a wide distribution, and pinning them
    together tightly would be asserting a coincidence.

    **Updated 2026-08-19 (ADR-197 resolution, maintainer-authorized).** Fixing
    ``experience_gam_penalized.reml_score``'s missing penalized-deviance term moved
    this fixture's own selection: ``select_lambdas_reml`` now picks ``lambda_age`` at
    the search bound (``10**8``, `LAMBDA_LOG10_BOUNDS`'s own upper edge —
    ``n_evaluated`` drops from 202 to 166, `select_lambdas_reml`'s own documented
    signature for "winner clips at a bound"), where ``lambda_age = 31622.78`` was
    interior before the fix. A boundary optimum has zero-or-negative curvature in
    that direction by construction (moving further would only smooth more, which the
    search bound alone stops), so the age-axis eigenvalue of the REML Hessian now
    legitimately floors — `n_floored` is `1`, not `0`, and the age-axis entry of
    `V_rho` is the search bound's own width cap, not a measured curvature (see
    `smoothing_uncertainty`'s own docstring on the cap). This is a real, derived
    consequence of the fix on this exact synthetic fixture, not a bug in it and not a
    reason to touch `LAMBDA_LOG10_BOUNDS` (out of scope — PLAN Anchor 7 authorized
    only the one-line score fix this session). The year axis remains an interior
    optimum and stays directly comparable to ADR-187's empirical spread; the age
    axis's comparison is retired here rather than silently accepted as if it were a
    measurement.
    """
    cells = _cells_from(_quadratic_mi)
    selection = select_lambdas_reml(cells, k_age=7, k_year=6)
    extra = smoothing_uncertainty(
        cells,
        lambda_age=selection.lambda_age,
        lambda_year=selection.lambda_year,
        k_age=7,
        k_year=6,
    )

    decades = np.sqrt(np.diag(extra.v_rho)) / np.log(10.0)
    assert extra.n_floored == 1, (
        f"expected exactly the age axis to floor at this fixture's post-fix, "
        f"at-bound selection (lambda_age={selection.lambda_age:.3e}); got "
        f"n_floored={extra.n_floored}. If 0, the selection likely moved back to an "
        "interior optimum and the retired age-axis comparison above should be "
        "revisited; if 2, the year axis floored too and needs its own investigation."
    )
    # Age axis (index 0): capped by the search bound's own width, not measured post
    # ADR-197's fix on this fixture — see the docstring above. Not compared here.
    year_sd = decades[1]
    assert 0.1 <= year_sd <= 10.0, (
        f"log10 lambda_year standard deviation is {year_sd:.3f} decades, outside the "
        "0.1-10 range ADR-187's empirical spreads (0.75-5.50 decades) make "
        "plausible. Vrho is in NATURAL log units; a missing ln(10) lands here."
    )


def test_the_unconditional_covariance_refuses_a_corner_it_cannot_reach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing derivative is not a smaller Hessian — it is no Hessian.

    Unlike the selector, `smoothing_uncertainty` does **not** reject and continue. The
    selector is choosing among points and can afford to discard one; a central
    difference needs *both* of its points, and assembling the matrix from whichever
    corners happened to converge would report a different quantity under the same name.

    Centred on the corner ADR-187 names, with that corner forced to fail — so the very
    first evaluation is the one that cannot be had. The message must name the offset,
    because "a fit did not converge" is not actionable when nine of them were attempted.
    """
    _raise_at_corner(monkeypatch)
    with pytest.raises(PolarisComputationError, match="did not converge") as excinfo:
        smoothing_uncertainty(
            _cells_from(_quadratic_mi, seed=_ABORT_SEED),
            lambda_age=10.0 ** _ABORT_CORNER[0],
            lambda_year=10.0 ** _ABORT_CORNER[1],
            k_age=7,
            k_year=6,
        )
    assert "offset" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, PolarisComputationError)


@pytest.mark.parametrize(("lambda_age", "lambda_year"), [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test_the_unconditional_covariance_refuses_a_non_positive_lambda(
    lambda_age: float, lambda_year: float
) -> None:
    """It differentiates in `log λ`, so λ=0 has no neighbourhood to difference over."""
    with pytest.raises(PolarisValidationError, match="strictly positive"):
        smoothing_uncertainty(
            _cells(noisy=True),
            lambda_age=lambda_age,
            lambda_year=lambda_year,
            k_age=7,
            k_year=6,
        )


def test_a_non_positive_log_step_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="log_step must be positive"):
        smoothing_uncertainty(
            _cells(noisy=True), lambda_age=1e2, lambda_year=1e2, log_step=0.0, k_age=7, k_year=6
        )


# ---------------------------------------------------------------------------------
# The level-4 refutation, localised (ADR-190)
#
# ADR-189 amendment 1 refuted this correction against `mgcv` and named three places to
# look: the difference step, the eigenvalue floor, and an `ln(10)²` conversion. All
# three are now refuted in turn — the gap is in the FORMULA, not this arithmetic. These
# two tests exist so a later session cannot "fix" correct arithmetic while chasing it.
# ---------------------------------------------------------------------------------


def test_the_correction_is_exactly_j_vrho_jt() -> None:
    """The implementation computes what ADR-188 decision 2 says it computes.

    Recomputed independently from the returned `hessian` and `jacobian` rather than
    trusting the internals. This pins the arithmetic so the open BLOCKER cannot be
    misread as a coding error: measured against `mgcv`'s own coefficients, own `V_rho`
    and own λ, `J V_rho Jᵀ` reproduces OUR inflation (1.18 / 1.15 / 1.24) and not
    `mgcv`'s (1.74 / 1.49 / 1.87). `vcov(unconditional = TRUE)` is a different and
    larger quantity — see ADR-190.
    """
    cells = _cells_from(_quadratic_mi)
    selection = select_lambdas_reml(cells, k_age=7, k_year=6)
    extra = smoothing_uncertainty(
        cells,
        lambda_age=selection.lambda_age,
        lambda_year=selection.lambda_year,
        k_age=7,
        k_year=6,
    )

    half_width = float(np.log(10.0) * (LAMBDA_LOG10_BOUNDS[1] - LAMBDA_LOG10_BOUNDS[0])) / 2.0
    eigenvalues, vectors = np.linalg.eigh(0.5 * (extra.hessian + extra.hessian.T))
    expected_v_rho = (
        vectors * (1.0 / np.maximum(eigenvalues, 1.0 / (half_width * half_width)))
    ) @ vectors.T

    np.testing.assert_allclose(extra.v_rho, expected_v_rho, rtol=1e-12, atol=0.0)
    np.testing.assert_allclose(
        extra.correction, extra.jacobian @ expected_v_rho @ extra.jacobian.T, rtol=1e-10
    )


def test_the_correction_is_converged_in_the_difference_step() -> None:
    """Halving the step barely moves the correction, so the step is not the gap.

    ADR-189 amendment 1 listed `log_step` first among the places to look. Halving it
    doubles the resolution of both central differences; if the default step were
    differencing structure it cannot resolve, the correction would move materially.
    The bound is 10% — an order of magnitude above the ~1.7% measured across an 8x
    step sweep on the conformance cells (ADR-190), and chosen to be loose enough that
    it fails only on a real change in behaviour rather than on fixture noise.
    """
    cells = _cells_from(_quadratic_mi)
    selection = select_lambdas_reml(cells, k_age=7, k_year=6)
    corrections = [
        smoothing_uncertainty(
            cells,
            lambda_age=selection.lambda_age,
            lambda_year=selection.lambda_year,
            log_step=step,
            k_age=7,
            k_year=6,
        ).correction
        for step in (KS_LOG_STEP, KS_LOG_STEP / 2.0)
    ]

    coarse, fine = (float(np.mean(np.diag(c))) for c in corrections)
    assert coarse > 0.0, "the correction must be non-degenerate for this test to mean anything"
    assert abs(fine / coarse - 1.0) < 0.10, (
        f"the correction moved {abs(fine / coarse - 1.0):.1%} when the difference step was "
        f"halved ({coarse:.6e} -> {fine:.6e}). ADR-190 established the step is converged; "
        f"if this fails, that finding no longer holds and the level-4 diagnosis needs redoing."
    )

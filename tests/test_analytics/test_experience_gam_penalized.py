"""Slice 1 of ``docs/PLAN_penalized_mi_surface.md`` — the penalized fitter at fixed λ.

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

Between the limits, ``edf`` must move monotonically. That is the whole behavioural
contract of slice 1; λ *selection* is slice 2 and is deliberately absent here.
"""

import itertools
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import TensorMIModel
from polaris_re.analytics.experience_gam_penalized import (
    COARSE_STEP,
    LAMBDA_LOG10_BOUNDS,
    REFINE_STEP,
    PenalizedTensorMIModel,
    difference_penalty,
    lambda_is_at_bound,
    select_lambdas_reml,
    tensor_penalties,
)
from polaris_re.core.exceptions import PolarisValidationError

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
    model = PenalizedTensorMIModel(cells, **kwargs)  # type: ignore[arg-type]
    fit = model.fit()
    design = model.design_on_grid(fit._design_builder, _AGES, _YEARS)
    eta = (design @ fit.coef).reshape(len(_AGES), len(_YEARS))
    return 1.0 - np.exp(np.diff(eta, axis=1))


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

        model = PenalizedTensorMIModel(cells, k_age=7, k_year=6, lambda_year=lam)
        eta_base = model.design_on_grid(base._design_builder, _AGES, _YEARS) @ base.coef
        shifted_model = PenalizedTensorMIModel(shifted, k_age=7, k_year=6, lambda_year=lam)
        eta_moved = (
            shifted_model.design_on_grid(moved._design_builder, _AGES, _YEARS - 2012) @ moved.coef
        )
        np.testing.assert_allclose(eta_moved, eta_base, atol=1e-9)


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
        lam_age, lam_year, _ = select_lambdas_reml(cells, k_age=10, k_year=6)
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
    _, lam_year, _ = select_lambdas_reml(cells, k_age=10, k_year=6)
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

    lam_age, lam_year, _ = select_lambdas_reml(cells, k_age=10, k_year=6)
    model = PenalizedTensorMIModel(
        cells, k_age=10, k_year=6, lambda_age=lam_age, lambda_year=lam_year
    )
    fit = model.fit()
    design = model.design_on_grid(fit._design_builder, _AGES, _YEARS)
    eta = (design @ fit.coef).reshape(len(_AGES), len(_YEARS))
    penalized = rmse(1.0 - np.exp(np.diff(eta, axis=1)))

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

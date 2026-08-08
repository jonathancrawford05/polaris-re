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

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import TensorMIModel
from polaris_re.analytics.experience_gam_penalized import (
    PenalizedTensorMIModel,
    difference_penalty,
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

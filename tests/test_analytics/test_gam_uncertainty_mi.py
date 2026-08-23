"""Tests for the WPS-2016 correction assembled on a penalized MI fit.

R-free, so they run in the gating pytest job — PR #206's review made zero
R-free coverage a [P1] on the last module that arrived without it.

**What these pin, and what they deliberately do not.** They pin the *adapter*:
that the design is rebuilt identically to the one the fit came from, that the
eigenvalue floor is production's rather than a new one, that the two correction
terms are separable and the second is not silently zero, and that nothing here
mutates the production fit. They do **not** assert agreement with ``mgcv`` —
that comparison lives in the digest-pinned conformance workflow (ADR-202), and a
unit test asserting it would be asserting something this file cannot establish.

They also do not assert a coverage rate. Coverage is a 200-replicate study
(``scripts/unconditional_coverage_study.py``); what a test can hold is the
*direction*, and :func:`test_the_second_order_term_widens_rather_than_narrows`
holds exactly that much.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam_penalized import (
    LAMBDA_LOG10_BOUNDS,
    PenalizedTensorMIModel,
    smoothing_uncertainty,
)
from polaris_re.analytics.gam_uncertainty_mi import _floored_hessian, wps_correction
from polaris_re.core.exceptions import PolarisComputationError

_AGES = np.arange(25, 96)
_YEARS = np.arange(2012, 2020)
_LAMBDA_AGE = 1.0e3
_LAMBDA_YEAR = 1.0e4
_K_AGE = 7
_K_YEAR = 6


def _q_base(age: float) -> float:
    return 0.004 * float(np.exp(0.08 * (age - 45.0)))


def _cells(*, seed: int = 7, mi: float = 0.015) -> pl.DataFrame:
    """The ILEC-shaped fixture the penalized tests already use, reused not rebuilt."""
    rng = np.random.default_rng(seed)
    rows: list[tuple[int, int, float, float, float]] = []
    for age in _AGES:
        q0 = _q_base(float(age))
        actual = q0
        for year in _YEARS:
            if int(year) > int(_YEARS.min()):
                actual *= 1.0 - mi
            rows.append((int(age), int(year), q0, 6.0e4, float(rng.poisson(6.0e4 * actual))))
    return pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )


@pytest.fixture(scope="module")
def fixture() -> tuple[pl.DataFrame, object, object]:
    """A fixed-lambda fit and its REML Hessian.

    Fixed lambda rather than :func:`fit_reml` on purpose: the grid search costs ~180
    penalized fits and selects nothing this file asserts about. The nine fits
    ``smoothing_uncertainty`` needs are the whole budget here.
    """
    cells = _cells()
    model = PenalizedTensorMIModel(
        cells,
        lambda_age=_LAMBDA_AGE,
        lambda_year=_LAMBDA_YEAR,
        k_age=_K_AGE,
        k_year=_K_YEAR,
    )
    fit = model.fit()
    extra = smoothing_uncertainty(
        cells,
        lambda_age=_LAMBDA_AGE,
        lambda_year=_LAMBDA_YEAR,
        k_age=_K_AGE,
        k_year=_K_YEAR,
    )
    return cells, fit, extra


def test_the_correction_is_the_sum_of_its_two_reported_terms(fixture) -> None:
    """``correction`` is exactly ``first_order + second_order``, not a third quantity."""
    cells, fit, extra = fixture
    result = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    np.testing.assert_allclose(
        result.correction, result.first_order + result.second_order, rtol=0.0, atol=0.0
    )


def test_the_second_order_term_is_not_zero(fixture) -> None:
    """The ``V''`` term carries real mass.

    **This is the mutation guard.** ``V''`` is precisely what plain Kass-Steffey
    omits, so a :func:`wps_correction` that returned only the first-order term — the
    single most plausible way for this module to be silently wrong — would leave the
    band identical to the shipped one and every other test here would still pass.
    """
    cells, fit, extra = fixture
    result = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    first = float(np.mean(np.abs(np.diag(result.first_order))))
    second = float(np.mean(np.abs(np.diag(result.second_order))))
    assert second > 0.1 * first, (
        f"V'' contributes {second:.3e} against V' at {first:.3e}. ADR-190 measured the "
        f"eq. (7) correction as 3.2-4.1x the Kass-Steffey one against mgcv, so a V'' "
        f"this small means it is not being assembled."
    )


def test_the_second_order_term_widens_rather_than_narrows(fixture) -> None:
    """Every coefficient variance goes up, never down.

    The direction is the part a unit test can hold; the magnitude is the coverage
    study's job. A correction that *narrowed* some variance would be a sign error in
    the ``V''`` assembly, and would push coverage the wrong way — the exact outcome
    ADR-190 decision 4 registered as falsifying.
    """
    cells, fit, extra = fixture
    result = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    assert np.all(np.diag(result.correction) >= 0.0)
    assert np.all(np.diag(result.second_order) >= 0.0)


def test_both_terms_are_symmetric(fixture) -> None:
    """A covariance correction that is not symmetric is not a covariance correction."""
    cells, fit, extra = fixture
    result = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    np.testing.assert_allclose(result.first_order, result.first_order.T, rtol=1e-12, atol=1e-18)
    np.testing.assert_allclose(result.second_order, result.second_order.T, rtol=1e-12, atol=1e-18)


def test_the_first_order_term_reproduces_productions_finite_difference_one(fixture) -> None:
    """Mechanism 2, measured: analytic ``J`` against production's central-difference ``J``.

    Same formula, two ways of getting ``J``. They should agree to something much
    tighter than the effect being studied, and this test is what licenses the
    coverage study's claim that any movement it sees belongs to the *formula* rather
    than to the derivative method.

    The tolerance is on the **aggregate** inflation rather than element-wise: the
    correction has near-zero entries where a relative comparison is meaningless, and
    the epic has already been bitten once by reading a scalar summary as if it were an
    element-wise one (ADR-202). Stated as an aggregate, and read as an aggregate.
    """
    cells, fit, extra = fixture
    result = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    analytic = float(np.mean(np.diag(result.first_order)))
    finite_difference = float(np.mean(np.diag(extra.correction)))
    relative = abs(analytic - finite_difference) / abs(finite_difference)
    assert relative < 0.05, (
        f"analytic first-order term {analytic:.6e} against production's "
        f"finite-difference {finite_difference:.6e} — {relative:.2%} apart. These are "
        f"the same formula; a gap this size means the derivative method is not the "
        f"negligible mechanism the coverage study reports it as."
    )


def test_the_eigenvalue_floor_is_productions_own(fixture) -> None:
    """``_floored_hessian`` reproduces ``smoothing_uncertainty``'s floor exactly.

    Not a restatement of the implementation: production floors the eigenvalues and
    *then* inverts, while this module has to floor and reassemble the Hessian,
    because ``unconditional_covariance`` takes two different inverses of it. The two
    routes are different code, so that they floor the same directions is a fact worth
    pinning — and it is what makes "no new constant was introduced" (PLAN Anchor 8)
    checkable rather than asserted in a docstring.
    """
    _cells_unused, _fit_unused, extra = fixture
    _, n_floored = _floored_hessian(extra.hessian, LAMBDA_LOG10_BOUNDS)
    assert n_floored == extra.n_floored


def test_a_floored_hessian_inverts_to_productions_v_rho(fixture) -> None:
    """The reassembled Hessian's inverse *is* production's ``v_rho``.

    The stronger form of the test above: identical floored directions could still
    mean a different matrix. This pins the matrix.
    """
    _cells_unused, _fit_unused, extra = fixture
    floored, _ = _floored_hessian(extra.hessian, LAMBDA_LOG10_BOUNDS)
    np.testing.assert_allclose(np.linalg.inv(floored), extra.v_rho, rtol=1e-10, atol=1e-14)


def test_mismatched_model_kwargs_raise_rather_than_silently_correcting_the_wrong_band(
    fixture,
) -> None:
    """A correction assembled on a different design than the band it corrects is not one.

    ``wps_correction`` cannot see the arguments the fit was produced under — it is
    given the fit, not the call — so the only defence is to rebuild and check. Without
    it, passing the wrong ``k_age`` would return a plausible, wrong covariance.
    """
    cells, fit, extra = fixture
    with pytest.raises(PolarisComputationError, match="model_kwargs do not match"):
        wps_correction(cells, fit, extra, k_age=_K_AGE + 2, k_year=_K_YEAR)


def test_it_does_not_mutate_the_fit_it_is_given(fixture) -> None:
    """The adapter reads the fit; it must not write to it.

    PLAN Anchor 7 protects the production module's *behaviour*, and a correction that
    quietly rewrote ``fit.cov`` would defeat that protection without editing a line of
    ``experience_gam_penalized``.
    """
    cells, fit, extra = fixture
    before_cov = fit.cov.copy()
    before_coef = fit.coef.copy()
    wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    np.testing.assert_array_equal(fit.cov, before_cov)
    np.testing.assert_array_equal(fit.coef, before_coef)


def test_it_is_deterministic(fixture) -> None:
    """Two calls on the same fit give bit-identical corrections (ADR-074).

    The grid selector is deterministic by construction and this must not be the thing
    that reintroduces drift.
    """
    cells, fit, extra = fixture
    first = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    second = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    np.testing.assert_array_equal(first.correction, second.correction)
    np.testing.assert_array_equal(first.first_order, second.first_order)
    np.testing.assert_array_equal(first.second_order, second.second_order)


def test_the_raw_hessian_eigenvalues_are_reported(fixture) -> None:
    """The unfloored eigenvalues come back, so a reader can see how close to singular.

    Reported rather than swallowed because the floor's whole justification is that it
    caps a *flat* direction at what the search could have produced; a reader who
    cannot see the raw eigenvalue cannot check that claim.
    """
    cells, fit, extra = fixture
    result = wps_correction(cells, fit, extra, k_age=_K_AGE, k_year=_K_YEAR)
    expected = np.linalg.eigvalsh(0.5 * (extra.hessian + extra.hessian.T))
    np.testing.assert_allclose(result.hessian_eigenvalues, expected, rtol=1e-12, atol=1e-18)

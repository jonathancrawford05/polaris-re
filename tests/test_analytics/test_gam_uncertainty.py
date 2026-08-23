"""Tests for Wood, Pya and Saefken (2016) eq. (7).

R-free, so they run in the gating pytest job. They pin the *machinery* — the
Cholesky-factor derivative, the V'' assembly, the first-order term's identity
with plain Kass-Steffey. They deliberately do NOT assert agreement with mgcv:
that comparison is characterised but NOT closed (see
docs/WORK_ORDER_level4_wps2016.md), and a test asserting it would be asserting
something this session did not establish.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_uncertainty import (
    MGCV_RHO_RIDGE,
    cholesky_factor_derivative,
    d_vbeta_d_rho,
    regularized_v_rho,
    second_order_correction,
    unconditional_covariance,
    wood_factor_and_derivative,
)
from polaris_re.core.exceptions import PolarisValidationError


def _spd(p: int, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(p, p))
    return a @ a.T + p * np.eye(p)


def test_cholesky_factor_derivative_matches_a_difference_of_a_real_factorisation() -> None:
    """dR/dt against a central difference of an actual Cholesky factorisation."""
    p = 5
    v0 = _spd(p)
    rng = np.random.default_rng(11)
    b = rng.normal(size=(p, p))
    dv = (b + b.T) / 2
    h = 1e-6

    def chol_upper(v: np.ndarray) -> np.ndarray:
        return np.linalg.cholesky(v).T

    fd = (chol_upper(v0 + h * dv) - chol_upper(v0 - h * dv)) / (2 * h)
    analytic = cholesky_factor_derivative(chol_upper(v0), dv)
    np.testing.assert_allclose(analytic, fd, atol=1e-8)


def test_cholesky_factor_derivative_returns_an_upper_triangular_factor() -> None:
    p = 4
    v0 = _spd(p)
    rng = np.random.default_rng(5)
    b = rng.normal(size=(p, p))
    d_r = cholesky_factor_derivative(np.linalg.cholesky(v0).T, (b + b.T) / 2)
    np.testing.assert_allclose(d_r, np.triu(d_r), atol=0.0)


def test_cholesky_factor_derivative_refuses_a_shape_mismatch() -> None:
    with pytest.raises(PolarisValidationError, match="both must be"):
        cholesky_factor_derivative(np.eye(3), np.eye(4))


def test_second_order_correction_is_symmetric_and_psd_for_a_psd_vrho() -> None:
    """V'' is a covariance, so it must come out symmetric — and positive
    semi-definite whenever Vrho is, since it is a sum of Vrho-weighted Gram
    matrices."""
    rng = np.random.default_rng(7)
    p, m = 5, 2
    d_r = tuple(np.triu(rng.normal(size=(p, p))) for _ in range(m))
    a = rng.normal(size=(m, m))
    v_rho = a @ a.T + m * np.eye(m)
    out = second_order_correction(d_r, v_rho)
    np.testing.assert_allclose(out, out.T, atol=1e-12)
    assert np.min(np.linalg.eigvalsh(out)) > -1e-10


def test_second_order_correction_is_zero_when_vrho_is_zero() -> None:
    """No smoothing-parameter uncertainty means no correction of either order —
    the control that catches a stray additive term."""
    rng = np.random.default_rng(9)
    p, m = 4, 2
    d_r = tuple(np.triu(rng.normal(size=(p, p))) for _ in range(m))
    out = second_order_correction(d_r, np.zeros((m, m)))
    assert np.count_nonzero(out) == 0


def test_second_order_correction_refuses_a_vrho_of_the_wrong_size() -> None:
    d_r = (np.eye(3), np.eye(3))
    with pytest.raises(PolarisValidationError, match="expected"):
        second_order_correction(d_r, np.eye(3))


def test_d_vbeta_d_rho_is_symmetric() -> None:
    rng = np.random.default_rng(13)
    n, p = 40, 5
    x = rng.normal(size=(n, p))
    v_beta = np.linalg.inv(_spd(p))
    out = d_vbeta_d_rho(v_beta, x, rng.normal(size=n), _spd(p, seed=4), 2.0)
    np.testing.assert_allclose(out, out.T, atol=1e-12)


def test_first_order_term_is_exactly_plain_kass_steffey() -> None:
    """`kass_steffey` must be `Vb + J Vrho J'` and nothing else — it is the
    thing this engine already computed, and the point of keeping the two terms
    separable is that adding V'' cannot silently perturb it."""
    rng = np.random.default_rng(17)
    n, p, m = 60, 5, 2
    x = rng.normal(size=(n, p))
    v_beta = np.linalg.inv(_spd(p))
    j = rng.normal(size=(m, p))
    dw = rng.normal(size=(m, n)) * 0.01
    pen = (_spd(p, seed=2) * 0.1, _spd(p, seed=6) * 0.1)
    a = rng.normal(size=(m, m))
    v_rho = a @ a.T + m * np.eye(m)
    h_rho = np.linalg.inv(v_rho)
    corr = unconditional_covariance(v_beta, x, j, dw, pen, np.array([0.5, -0.2]), h_rho)
    # V' uses the UNREGULARISED inverse Hessian — the measured asymmetry.
    np.testing.assert_allclose(corr.kass_steffey, v_beta + j.T @ v_rho @ j, rtol=1e-10)
    np.testing.assert_allclose(corr.full, corr.kass_steffey + corr.second_order, rtol=1e-12)


def test_unconditional_covariance_refuses_a_mismatched_j() -> None:
    rng = np.random.default_rng(19)
    n, p, m = 30, 4, 2
    x = rng.normal(size=(n, p))
    v_beta = np.linalg.inv(_spd(p))
    pen = (np.eye(p), np.eye(p))
    with pytest.raises(PolarisValidationError, match="dbeta_drho"):
        unconditional_covariance(
            v_beta,
            x,
            rng.normal(size=(m, p + 1)),
            rng.normal(size=(m, n)),
            pen,
            np.array([0.1, 0.2]),
            np.eye(m),
        )


# --- the two pieces identified by measurement against mgcv ------------------------


def test_wood_factor_satisfies_the_identity_eq7_is_written_in() -> None:
    """``G`` must satisfy ``Gᵀ G = V_beta`` — the defining property, checked rather
    than assumed, since a factor that failed it would still produce a plausible
    (and wrong) V''."""
    p = 6
    a = _spd(p, seed=21)
    g, _ = wood_factor_and_derivative(a, ())
    np.testing.assert_allclose(g.T @ g, np.linalg.inv(a), rtol=1e-10)


def test_wood_factor_is_lower_triangular_and_differs_from_the_cholesky_of_vbeta() -> None:
    """The finding this module turns on: eq. (7)'s factor is Wood (2011) 3.3's
    ``L⁻¹`` — lower triangular — and is a *different* square root from the upper
    Cholesky factor of ``V_beta``. Both satisfy ``GᵀG = V_beta``; they give
    different ``V''``. If these ever coincided, the distinction this module
    documents would be vacuous.
    """
    p = 6
    a = _spd(p, seed=23)
    g, _ = wood_factor_and_derivative(a, ())
    np.testing.assert_allclose(g, np.tril(g), atol=0.0)
    chol_of_vbeta = np.linalg.cholesky(np.linalg.inv(a)).T
    assert np.max(np.abs(g - chol_of_vbeta)) > 1e-6


def test_wood_factor_derivative_matches_a_difference_of_the_factor() -> None:
    p = 5
    a0 = _spd(p, seed=27)
    rng = np.random.default_rng(29)
    b = rng.normal(size=(p, p))
    da = (b + b.T) / 2
    h = 1e-6

    def factor(a: np.ndarray) -> np.ndarray:
        return np.linalg.inv(np.linalg.cholesky(a))

    fd = (factor(a0 + h * da) - factor(a0 - h * da)) / (2 * h)
    _, (analytic,) = wood_factor_and_derivative(a0, (da,))
    np.testing.assert_allclose(analytic, fd, atol=1e-8)


def test_regularized_v_rho_reproduces_the_measured_mgcv_ridge() -> None:
    """Pins :data:`MGCV_RHO_RIDGE` to what was measured against ``mgcv``'s own
    ``m$V.sp``, using that fit's actual outer Hessian and the ``V.sp`` it
    published. Residual there was 1.78e-15; this asserts far looser, because the
    point is that the *value* is 0.1 and not that this reproduces float noise.
    """
    hessian = np.array([[1.5789399638, -0.0001229184], [-0.0001229184, 0.0001351796]])
    mgcv_v_sp = np.array([[0.5956139656, 0.0007311309], [0.0007311309, 9.9865011842]])
    np.testing.assert_allclose(regularized_v_rho(hessian), mgcv_v_sp, rtol=1e-6)
    assert MGCV_RHO_RIDGE == 0.1


def test_an_unregularized_v_rho_blows_up_on_a_saturated_smoothing_parameter() -> None:
    """Why the ridge is load-bearing rather than cosmetic: without it, the
    saturated direction carries ~7400 of variance and V'' inherits it."""
    hessian = np.array([[1.5789399638, -0.0001229184], [-0.0001229184, 0.0001351796]])
    assert np.max(np.linalg.inv(hessian)) > 1000.0
    assert np.max(regularized_v_rho(hessian)) < 100.0


def test_the_two_terms_use_different_inverses_of_the_rho_hessian() -> None:
    """The measured asymmetry, pinned: `V'` takes the UNREGULARISED `H^-1` and
    `V''` the ridged one.

    This is the single fact that took `binomial-logit` from a 31.8% element-wise
    residual against mgcv to 0.023%. If a later change made both terms use the
    same inverse, the correction would silently regress to something that misses
    mgcv by ~30% on one family and ~2% on another — so it is asserted directly
    rather than left implicit in the assembly.
    """
    rng = np.random.default_rng(31)
    n, p, m = 80, 5, 2
    x = rng.normal(size=(n, p))
    v_beta = np.linalg.inv(_spd(p, seed=33))
    j = rng.normal(size=(m, p))
    dw = rng.normal(size=(m, n)) * 0.01
    pen = (_spd(p, seed=35) * 0.1, _spd(p, seed=37) * 0.1)
    # A Hessian with one near-null direction, as a saturated smoothing parameter gives.
    h_rho = np.diag([1.5, 1e-4])
    corr = unconditional_covariance(v_beta, x, j, dw, pen, np.array([0.3, 0.1]), h_rho)

    unreg = j.T @ np.linalg.inv(h_rho) @ j
    ridged = j.T @ regularized_v_rho(h_rho) @ j
    np.testing.assert_allclose(corr.first_order, unreg, rtol=1e-10)
    # ...and emphatically NOT the ridged one, on a Hessian like this.
    assert np.max(np.abs(corr.first_order - ridged)) > 0.5 * np.max(np.abs(unreg))


def test_the_finite_difference_rho_hessian_is_symmetric_and_step_converged() -> None:
    """PR #207 review [P1]: the "our own Hessian reproduces mgcv's" claim, pinned.

    R-free, so it cannot compare against ``mgcv`` — that comparison is now a
    reported column in the digest-pinned probe. What a unit test *can* hold is that
    the finite-difference Hessian is a converged second derivative rather than
    noise: symmetric, and stable across a 2x change of step.

    Step convergence is the substantive half. A central-difference Hessian sits
    between a truncation regime and a round-off regime, and this epic has already
    published a ratio from the wrong one once (ADR-202's Richardson diagnostic read
    ~0.6 under a header saying "want ~4"). Two steps agreeing to well under a
    percent is what says the reported number is the derivative.
    """
    import numpy as np

    from polaris_re.analytics.gam_family import poisson_log
    from polaris_re.analytics.gam_uncertainty_conformance import (
        finite_difference_rho_hessian,
    )

    rng = np.random.default_rng(20260823)
    n, k = 120, 6
    x = np.column_stack([np.ones(n), rng.normal(size=(n, k - 1))])
    penalty = np.zeros((k, k))
    penalty[1:, 1:] = np.eye(k - 1)
    penalties = (penalty,)
    coef_true = np.array([0.5, 0.3, -0.2, 0.1, 0.0, 0.15])
    y = rng.poisson(np.exp(x @ coef_true)).astype(np.float64)
    weights = np.ones(n)
    rho = np.array([np.log(2.0)])

    coarse = finite_difference_rho_hessian(x, y, penalties, poisson_log(), weights, rho, step=0.08)
    fine = finite_difference_rho_hessian(x, y, penalties, poisson_log(), weights, rho, step=0.04)

    np.testing.assert_allclose(coarse, coarse.T, rtol=1e-12, atol=1e-14)
    relative = float(np.max(np.abs(coarse - fine)) / np.max(np.abs(fine)))
    assert relative < 0.01, (
        f"the Hessian moved {relative:.3%} across a 2x step change, so the reported "
        "value is not a converged second derivative"
    )

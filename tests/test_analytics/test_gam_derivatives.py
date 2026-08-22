"""Tests for Wood (2011)'s ``dβ̂/drho``, ``dη/drho`` and ``dw/drho``.

R-free throughout, so they run in the **gating** pytest job. The parity
comparison against ``mgcv`` lives in ``scripts/gam_deriv_compare.py`` and runs in
the conformance workflow, which is `continue-on-error` and cannot fail a PR — the
lesson PR #206's review established, applied here from the start rather than
after the fact.

The finite-difference checks below are **internal self-consistency**, not parity
evidence: they difference this engine's own functions. They are what catches a
sign or transcription slip before an R round trip is spent, which is the role
Anchor 1 gives cheap checks.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_derivatives import (
    d_beta_d_rho,
    d_eta_d_rho,
    dw_deta,
    dw_drho,
    newton_alpha,
    newton_working_weights,
    second_deriv_mu_eta,
    variance_deriv,
)
from polaris_re.analytics.gam_family import (
    binomial_cloglog,
    binomial_logit,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.core.exceptions import PolarisValidationError

_FD = 1e-6


def _design(n: int = 120, p: int = 6, seed: int = 20260822) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x1 = np.sort(rng.uniform(-2.0, 2.0, n))
    return np.column_stack([np.ones(n), x1, x1**2, np.sin(x1), np.cos(x1), x1**3])


def _penalties(p: int = 6) -> tuple[np.ndarray, np.ndarray]:
    d = np.diff(np.eye(p), n=2, axis=0)
    s1 = d.T @ d
    s2 = np.zeros((p, p))
    s2[1, 1] = 1.0
    return s1, s2


# --- the analytic pieces Link/Family do not expose --------------------------------


@pytest.mark.parametrize(
    "family", [poisson_log(), binomial_logit(), binomial_cloglog()], ids=lambda f: f.link.name
)
def test_second_deriv_mu_eta_matches_a_difference_of_the_verified_mu_eta(family) -> None:
    """``d²μ/dη²`` against a central difference of the already-verified ``mu_eta``."""
    eta = np.linspace(-2.0, 1.0, 9)
    fd = (family.link.mu_eta(eta + _FD) - family.link.mu_eta(eta - _FD)) / (2 * _FD)
    analytic = second_deriv_mu_eta(family.link.name, eta, family.link.linkinv(eta))
    np.testing.assert_allclose(analytic, fd, atol=1e-8)


def test_variance_deriv_matches_a_difference_of_the_verified_variance() -> None:
    poisson = poisson_log()
    mu = np.linspace(0.5, 3.0, 9)
    fd = (poisson.variance(mu + _FD) - poisson.variance(mu - _FD)) / (2 * _FD)
    np.testing.assert_allclose(variance_deriv(poisson.name, mu), fd, atol=1e-7)

    binom = binomial_logit()
    mu = np.linspace(0.15, 0.8, 9)
    fd = (binom.variance(mu + _FD) - binom.variance(mu - _FD)) / (2 * _FD)
    np.testing.assert_allclose(variance_deriv(binom.name, mu), fd, atol=1e-7)


def test_second_deriv_mu_eta_refuses_an_underived_link() -> None:
    with pytest.raises(PolarisValidationError, match="no derivation recorded"):
        second_deriv_mu_eta("probit", np.zeros(3), np.zeros(3))


def test_variance_deriv_refuses_an_underived_family() -> None:
    with pytest.raises(PolarisValidationError, match="no derivation recorded"):
        variance_deriv("gaussian", np.zeros(3))


# --- alpha: the Fisher/Newton factor ----------------------------------------------


@pytest.mark.parametrize(
    "family",
    [poisson_log(), binomial_logit(), quasipoisson_log()],
    ids=lambda f: f.name + "-" + f.link.name,
)
def test_alpha_is_exactly_one_for_a_canonical_link(family) -> None:
    """Wood §3.2: *"If a canonical link function is used then alphaᵢ = 1 ∀ i."*

    Nothing in :func:`newton_alpha` special-cases canonical links — it evaluates
    ``V'/V - m'/m²`` generically — so this passing is an independent confirmation
    of that algebra rather than a tautology.
    """
    rng = np.random.default_rng(5)
    eta = rng.normal(size=40) * 0.5
    mu = family.link.linkinv(eta)
    y = mu + rng.normal(size=40) * 0.05
    np.testing.assert_allclose(newton_alpha(family, y, eta, mu), 1.0, atol=1e-12)


def test_alpha_departs_from_one_for_a_non_canonical_link() -> None:
    """cloglog is the cell where Fisher and Newton genuinely differ — if this ever
    became 1, the canonical test above would be vacuous."""
    family = binomial_cloglog()
    rng = np.random.default_rng(5)
    eta = rng.normal(size=40) * 0.5
    mu = family.link.linkinv(eta)
    y = np.clip(mu + rng.normal(size=40) * 0.1, 0.01, 0.99)
    assert np.max(np.abs(newton_alpha(family, y, eta, mu) - 1.0)) > 1e-3


def test_newton_weights_reduce_to_fisher_weights_on_a_canonical_link() -> None:
    family = binomial_logit()
    rng = np.random.default_rng(7)
    eta = rng.normal(size=30) * 0.4
    mu = family.link.linkinv(eta)
    y = np.clip(mu + rng.normal(size=30) * 0.05, 0.01, 0.99)
    omega = np.full(30, 12.0)
    fisher = omega * family.link.mu_eta(eta) ** 2 / family.variance(mu)
    np.testing.assert_allclose(
        newton_working_weights(family, y, eta, mu, omega), fisher, rtol=1e-12
    )


# --- dw/deta ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "family",
    [poisson_log(), binomial_logit(), binomial_cloglog(), quasipoisson_log()],
    ids=lambda f: f.name + "-" + f.link.name,
)
def test_dw_deta_matches_a_difference_of_the_working_weight_itself(family) -> None:
    eta = np.linspace(-1.5, 0.8, 9)
    omega = np.linspace(0.5, 2.0, 9)

    def w_of(e: np.ndarray) -> np.ndarray:
        return omega * family.link.mu_eta(e) ** 2 / family.variance(family.link.linkinv(e))

    fd = (w_of(eta + _FD) - w_of(eta - _FD)) / (2 * _FD)
    analytic = dw_deta(family, eta, family.link.linkinv(eta), omega)
    np.testing.assert_allclose(analytic, fd, atol=1e-7)


# --- dbeta/drho and deta/drho -----------------------------------------------------


def test_dbeta_drho_is_exactly_zero_at_a_zero_penalty() -> None:
    """``dβ̂/drhoⱼ`` carries ``Sⱼβ̂``, so a zero penalty block makes it identically
    zero — an exact closed-form control that catches a sign or scaling slip
    without any reference at all."""
    x = _design()
    p = x.shape[1]
    zeros = (np.zeros((p, p)), np.zeros((p, p)))
    rng = np.random.default_rng(11)
    result = d_beta_d_rho(x, zeros, np.ones(x.shape[0]), rng.normal(size=p), np.array([0.3, -0.7]))
    assert np.count_nonzero(result) == 0


def test_deta_drho_is_the_design_image_of_dbeta_drho() -> None:
    x = _design()
    pen = _penalties()
    rng = np.random.default_rng(13)
    w = rng.uniform(0.5, 2.0, x.shape[0])
    coef = rng.normal(size=x.shape[1])
    rho = np.array([1.0, 0.5])
    np.testing.assert_allclose(
        d_eta_d_rho(x, pen, w, coef, rho), d_beta_d_rho(x, pen, w, coef, rho) @ x.T, rtol=1e-12
    )


@pytest.mark.parametrize(
    ("family", "canonical"),
    [(poisson_log(), True), (binomial_logit(), True), (binomial_cloglog(), False)],
    ids=lambda v: str(v),
)
def test_analytic_deta_drho_matches_a_difference_of_our_own_refits(family, canonical) -> None:
    """The self-consistency check that localises the Fisher/Newton distinction.

    Internal, not parity — both sides are this engine. Its job is to establish,
    before any R runs, that the analytic derivative is the ``h → 0`` limit of our
    own fitter, and that this holds on the non-canonical link **only** once the
    observed-Hessian weights are used.
    """
    x = _design()
    pen = _penalties()
    rng = np.random.default_rng(17)
    eta_true = 0.4 * x[:, 1] - 0.2 * x[:, 2]
    omega = None
    if family.name == "binomial":
        omega = np.full(x.shape[0], 25.0)
        y = np.clip(family.link.linkinv(eta_true), 0.02, 0.98)
    else:
        y = rng.poisson(np.exp(eta_true)).astype(float)
    rho = np.array([1.0, 0.5])
    h = 1e-4

    def fit_at(r: np.ndarray):
        s = sum(np.exp(rj) * b for rj, b in zip(r, pen, strict=True))
        return penalized_irls_general(x, y, family=family, penalty=s, weights=omega)

    fit = fit_at(rho)
    w_newton = newton_working_weights(family, y, fit.eta, fit.mu, omega)
    analytic = d_eta_d_rho(x, pen, w_newton, fit.coef, rho)

    for j in range(2):
        up, down = rho.copy(), rho.copy()
        up[j] += h
        down[j] -= h
        fd = (fit_at(up).eta - fit_at(down).eta) / (2 * h)
        np.testing.assert_allclose(analytic[j], fd, atol=1e-8)


def test_fisher_weights_are_wrong_for_the_derivative_on_a_non_canonical_link() -> None:
    """Pins the reason :func:`newton_working_weights` exists.

    Passing Fisher weights to :func:`d_beta_d_rho` is silently correct on a
    canonical link and materially wrong on cloglog. If a future change made the
    two agree here, this slice's central finding would have evaporated and the
    test above would no longer be testing anything.
    """
    family = binomial_cloglog()
    x = _design()
    pen = _penalties()
    eta_true = 0.4 * x[:, 1] - 0.2 * x[:, 2]
    omega = np.full(x.shape[0], 25.0)
    y = np.clip(family.link.linkinv(eta_true), 0.02, 0.98)
    rho = np.array([1.0, 0.5])
    h = 1e-4

    def fit_at(r: np.ndarray):
        s = sum(np.exp(rj) * b for rj, b in zip(r, pen, strict=True))
        return penalized_irls_general(x, y, family=family, penalty=s, weights=omega)

    fit = fit_at(rho)
    fisher = omega * family.link.mu_eta(fit.eta) ** 2 / family.variance(fit.mu)
    newton = newton_working_weights(family, y, fit.eta, fit.mu, omega)
    with_fisher = d_eta_d_rho(x, pen, fisher, fit.coef, rho)
    with_newton = d_eta_d_rho(x, pen, newton, fit.coef, rho)

    up = rho.copy()
    up[0] += h
    down = rho.copy()
    down[0] -= h
    fd = (fit_at(up).eta - fit_at(down).eta) / (2 * h)

    err_fisher = np.max(np.abs(with_fisher[0] - fd))
    err_newton = np.max(np.abs(with_newton[0] - fd))
    assert err_newton < 1e-8
    assert err_fisher > 100 * err_newton


# --- dw/drho ----------------------------------------------------------------------


def test_dw_drho_is_the_chain_rule_of_its_two_factors() -> None:
    family = binomial_logit()
    x = _design()
    rng = np.random.default_rng(19)
    eta = rng.normal(size=x.shape[0]) * 0.3
    mu = family.link.linkinv(eta)
    omega = np.full(x.shape[0], 10.0)
    deta = rng.normal(size=(2, x.shape[0]))
    expected = dw_deta(family, eta, mu, omega)[None, :] * deta
    np.testing.assert_allclose(dw_drho(family, eta, mu, deta, omega), expected, rtol=1e-12)


def test_dw_drho_refuses_a_mismatched_deta_shape() -> None:
    family = poisson_log()
    eta = np.zeros(10)
    with pytest.raises(PolarisValidationError, match="expected"):
        dw_drho(family, eta, family.link.linkinv(eta), np.zeros((2, 9)))


# --- input validation -------------------------------------------------------------


def test_d_beta_d_rho_refuses_a_block_count_mismatch() -> None:
    x = _design()
    with pytest.raises(PolarisValidationError, match="one per block"):
        d_beta_d_rho(x, _penalties(), np.ones(x.shape[0]), np.zeros(x.shape[1]), np.array([1.0]))


def test_d_beta_d_rho_refuses_a_wrong_shaped_penalty() -> None:
    x = _design()
    with pytest.raises(PolarisValidationError, match=r"must be \(p, p\)"):
        d_beta_d_rho(
            x, (np.zeros((3, 3)),), np.ones(x.shape[0]), np.zeros(x.shape[1]), np.array([1.0])
        )


def test_d_beta_d_rho_refuses_mismatched_weights_or_coef() -> None:
    x = _design()
    pen = _penalties()
    rho = np.array([1.0, 0.5])
    with pytest.raises(PolarisValidationError, match="irls_weights"):
        d_beta_d_rho(x, pen, np.ones(3), np.zeros(x.shape[1]), rho)
    with pytest.raises(PolarisValidationError, match="coef"):
        d_beta_d_rho(x, pen, np.ones(x.shape[0]), np.zeros(3), rho)

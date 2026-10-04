"""Outer-solver epic Slice 2 — the exact REML Hessian (``gam_reml_hessian``).

Internal derivation checks, NOT an ``mgcv`` comparison: every analytic quantity
is checked against a central difference of the function one order below it
(``w''`` against ``dw_deta_observed``, ``d²log|S|+`` against
``dlogdet_s_plus_drho``, the Hessian against ``reml_score_gradient[_profiled]``),
on all five family/link combinations the engine defines, BEFORE composition
into the Newton loop. The ``mgcv`` comparison lives in
``gam_hessian_conformance``.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_derivatives import dw_deta_observed
from polaris_re.analytics.gam_family import (
    Family,
    binomial_cloglog,
    binomial_logit,
    gaussian_identity,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_reml_appendix_b import dlogdet_s_plus_drho
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient, reml_score_gradient_profiled
from polaris_re.analytics.gam_reml_hessian import (
    d2log_det_s_plus_drho2,
    d2w_deta2_observed,
    reml_score_hessian,
    reml_score_hessian_profiled,
)
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score
from polaris_re.core.exceptions import PolarisValidationError

_LN10 = float(np.log(10.0))
_FAMILIES = {
    "gaussian": gaussian_identity,
    "quasipoisson": quasipoisson_log,
    "poisson": poisson_log,
    "binomial_logit": binomial_logit,
    "binomial_cloglog": binomial_cloglog,
}


def _problem(name: str, n: int = 240, seed: int = 20261004):
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, 1.0, n)
    p = 10
    x = np.column_stack([np.ones(n)] + [np.cos(k * np.pi * t) for k in range(1, p)])
    block_a = np.zeros((p, p))
    block_b = np.zeros((p, p))
    for k in range(1, 6):
        block_a[k, k] = float(k) ** 4
    for k in range(6, p):
        block_b[k, k] = float(k) ** 4
    signal = 1.0 + 0.8 * np.cos(np.pi * t) + 0.3 * np.cos(3 * np.pi * t)
    weights = np.ones(n)
    if name == "gaussian":
        y = signal + rng.normal(scale=0.4, size=n)
    elif name in ("quasipoisson", "poisson"):
        y = rng.poisson(np.exp(0.5 + 0.5 * signal) * 3.0).astype(np.float64)
    elif name == "binomial_logit":
        weights = np.full(n, 30.0)
        y = rng.binomial(30, 1.0 / (1.0 + np.exp(-(signal - 1.0)))) / 30.0
    else:
        weights = np.full(n, 20.0)
        y = rng.binomial(20, 1.0 - np.exp(-np.exp(0.6 * signal - 1.5))) / 20.0
    return y, x, _FAMILIES[name](), (block_a, block_b), weights


@pytest.mark.parametrize("name", list(_FAMILIES))
def test_w_series_first_derivative_equals_the_closed_form_and_second_matches_its_difference(
    name: str,
) -> None:
    rng = np.random.default_rng(7)
    family: Family = _FAMILIES[name]()
    n = 50
    eta = rng.uniform(-1.2, 0.8, size=n)
    mu = family.link.linkinv(eta)
    if name == "gaussian":
        y = rng.normal(size=n)
    elif name in ("quasipoisson", "poisson"):
        y = rng.poisson(mu * 3.0).astype(np.float64)
    else:
        y = rng.uniform(0.05, 0.95, size=n)
    omega = rng.uniform(0.5, 3.0, size=n)
    _w, w1, w2 = d2w_deta2_observed(family, y, eta, omega)
    closed_w1 = dw_deta_observed(family, y, eta, mu, omega)
    np.testing.assert_allclose(w1, closed_w1, rtol=1e-11, atol=1e-12)
    h = 1e-5
    fd = (
        dw_deta_observed(family, y, eta + h, family.link.linkinv(eta + h), omega)
        - dw_deta_observed(family, y, eta - h, family.link.linkinv(eta - h), omega)
    ) / (2.0 * h)
    np.testing.assert_allclose(w2, fd, rtol=1e-6, atol=1e-8)


def test_second_derivative_of_logdet_s_plus_matches_a_difference_of_its_gradient() -> None:
    _y, _x, _f, blocks, _w = _problem("gaussian")
    for rho in (np.array([1.0, 2.0]), np.array([4.0, -1.0]), np.array([25.0, 3.0])):
        analytic = d2log_det_s_plus_drho2(blocks, np.exp(rho))
        h = 1e-4
        fd = np.zeros((2, 2))
        for k in range(2):
            up, dn = rho.copy(), rho.copy()
            up[k] += h
            dn[k] -= h
            fd[:, k] = (
                dlogdet_s_plus_drho(blocks, np.exp(up)) - dlogdet_s_plus_drho(blocks, np.exp(dn))
            ) / (2.0 * h)
        np.testing.assert_allclose(analytic, fd, rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize("name", list(_FAMILIES))
@pytest.mark.parametrize(
    "log10_lambda",
    [np.array([1.0, 2.0]), np.array([3.5, -0.5]), np.array([11.0, 2.0])],
    ids=["interior", "mixed", "block_at_1e11"],
)
def test_hessian_matches_a_central_difference_of_the_analytic_gradient(
    name: str, log10_lambda: np.ndarray
) -> None:
    y, x, family, blocks, weights = _problem(name)
    coef, _ = penalized_fit_and_score(y, x, family, blocks, log10_lambda, weights=weights)
    lam = 10.0**log10_lambda
    rho = np.log(lam)

    def gradient(r: np.ndarray) -> np.ndarray:
        c, _ = penalized_fit_and_score(y, x, family, blocks, r / _LN10, weights=weights)
        fn = reml_score_gradient if family.dispersion_fixed else reml_score_gradient_profiled
        return fn(y, x, family, c, blocks, np.exp(r), weights=weights)

    if family.dispersion_fixed:
        analytic = reml_score_hessian(y, x, family, coef, blocks, lam, weights=weights)
    else:
        analytic = reml_score_hessian_profiled(y, x, family, coef, blocks, lam, weights=weights)
    h = 1e-3
    fd = np.zeros_like(analytic)
    for k in range(2):
        up, dn = rho.copy(), rho.copy()
        up[k] += h
        dn[k] -= h
        fd[:, k] = (gradient(up) - gradient(dn)) / (2.0 * h)
    np.testing.assert_allclose(analytic, analytic.T, rtol=0, atol=1e-12)
    scale = max(float(np.max(np.abs(fd))), 1e-12)
    assert float(np.max(np.abs(analytic - 0.5 * (fd + fd.T)))) / scale < 5e-5


def test_hessian_rejects_the_wrong_scale_regime() -> None:
    y, x, family, blocks, _weights = _problem("gaussian")
    coef = np.zeros(x.shape[1])
    with pytest.raises(PolarisValidationError):
        reml_score_hessian(y, x, family, coef, blocks, np.ones(2))
    y, x, family, blocks, _weights = _problem("poisson")
    with pytest.raises(PolarisValidationError):
        reml_score_hessian_profiled(y, x, family, np.zeros(x.shape[1]), blocks, np.ones(2))

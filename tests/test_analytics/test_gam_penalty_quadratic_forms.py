"""Outer-solver epic Slice 3 (ADR-244) — the derivative path's penalty quadratic
forms are sums of squares, so a rounding-level change in ``beta`` cannot move them.

ADR-223 moved the SCORE's ``beta' S beta`` to a sum of squares over each block's
own root (ADR-222 amendment 2: formed, it carries ~1e-5 of absolute error at an
11-decade ``lambda`` spread). The analytic gradient's term 1 and the Hessian's
``A_j beta`` / ``beta' A_j beta`` still contracted the formed matrix, so the
gradient was noisy at exactly the spread the score had been fixed for: a 5e-15
change in ``beta`` moved term 1 by 3e-5.

These are own-criterion checks (no ``mgcv`` operand). The problem is built so
that every block's null space is DENSE in the coordinates (a random orthogonal
mix), because a diagonal block has exact zeros and cannot show the cancellation.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_family import quasipoisson_log
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient_profiled
from polaris_re.analytics.gam_reml_hessian import reml_score_hessian_profiled
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

_LN10 = float(np.log(10.0))
_EPS = float(np.finfo(np.float64).eps)


def _dense_null_problem():
    rng = np.random.default_rng(20261004)
    n, p = 400, 24
    t = np.linspace(0.0, 1.0, n)
    x = np.column_stack([np.ones(n)] + [np.cos(k * np.pi * t) for k in range(1, p)])
    q, _ = np.linalg.qr(rng.standard_normal((p, p)))
    blocks = []
    for lo, hi in ((2, 12), (12, 24)):
        spectrum = np.zeros(p)
        spectrum[lo:hi] = np.arange(1, hi - lo + 1, dtype=np.float64) ** 2
        block = q @ np.diag(spectrum) @ q.T
        blocks.append(0.5 * (block + block.T))
    # Both blocks share the first two coordinates as a dense null space.
    signal = 1.0 + 0.8 * np.cos(np.pi * t)
    y = rng.poisson(np.exp(0.5 + 0.5 * signal) * 3.0).astype(np.float64)
    return y, x, tuple(blocks)


@pytest.mark.parametrize(
    ("log10_lambda", "grad_limit", "hess_limit"),
    [
        # measured, fixed vs the formed-contraction code this replaced:
        #   (10, 10): dgrad 2.8e-08 vs 2.1e-06, dhess 4.2e-09 vs 3.1e-01
        #   (11, 11): dgrad 2.5e-07 vs 2.6e-05, dhess 7.0e-08 vs 1.9e+00
        ((10.0, 10.0), 2e-7, 1e-4),
        ((11.0, 11.0), 2e-6, 1e-4),
    ],
    ids=["both_1e10", "both_1e11"],
)
def test_gradient_and_hessian_are_smooth_in_beta_at_an_extreme_lambda(
    log10_lambda: tuple[float, float], grad_limit: float, hess_limit: float
) -> None:
    """A ``1e-15``-relative change in ``beta`` moves the analytic gradient and
    the Hessian by far less than the formed contraction did (limits sit between
    the two measured readings above; the real N=7 fixture is the same effect,
    gradient 6.5e-5 -> 4.7e-8 and scaled Hessian 3.9e-1 -> 4.8e-4 at an
    11-decade spread, ADR-244)."""
    y, x, blocks = _dense_null_problem()
    family = quasipoisson_log()
    point = np.asarray(log10_lambda, dtype=np.float64)
    coef, _score = penalized_fit_and_score(y, x, family, blocks, point)
    lambdas = 10.0**point
    g0 = reml_score_gradient_profiled(y, x, family, coef, blocks, lambdas)
    h0 = reml_score_hessian_profiled(y, x, family, coef, blocks, lambdas)
    scale = np.sqrt(np.outer(np.abs(np.diag(h0)), np.abs(np.diag(h0))))
    worst_g, worst_h = 0.0, 0.0
    for seed in range(8):
        noise = np.random.default_rng(seed).standard_normal(coef.shape)
        c1 = coef * (1.0 + _EPS * noise)
        g1 = reml_score_gradient_profiled(y, x, family, c1, blocks, lambdas)
        h1 = reml_score_hessian_profiled(y, x, family, c1, blocks, lambdas)
        worst_g = max(worst_g, float(np.max(np.abs(g1 - g0))))
        worst_h = max(worst_h, float(np.max(np.abs(h1 - h0) / scale)))
    assert worst_g < grad_limit, worst_g
    assert worst_h < hess_limit, worst_h


def test_the_sum_of_squares_gradient_still_matches_a_central_difference_of_the_score() -> None:
    """The change is arithmetic only — the derived gradient is unchanged."""
    y, x, blocks = _dense_null_problem()
    family = quasipoisson_log()
    point = np.array([4.0, 2.0])
    coef, _ = penalized_fit_and_score(y, x, family, blocks, point)
    analytic = reml_score_gradient_profiled(y, x, family, coef, blocks, 10.0**point)

    def score(rho: np.ndarray) -> float:
        _c, s = penalized_fit_and_score(y, x, family, blocks, rho / _LN10)
        return float(s)

    rho0 = point * _LN10
    h = 1e-4
    fd = np.array(
        [
            (score(rho0 + h * np.eye(2)[k]) - score(rho0 - h * np.eye(2)[k])) / (2 * h)
            for k in range(2)
        ]
    )
    np.testing.assert_allclose(analytic, fd, rtol=1e-5, atol=1e-6)

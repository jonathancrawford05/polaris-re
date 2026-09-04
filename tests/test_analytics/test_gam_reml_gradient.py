"""``docs/PLAN_mgcv_parity_engine.md`` slice 7d — the analytic REML gradient.

Every check here is internal self-consistency (does the analytic gradient
match a central difference of the already-verified
``gam_reml.reml_score_general``, does it reject what it must reject), the
same framing ``test_gam_reml.py`` and ``test_gam_derivatives.py`` use — cheap
to run before an R round trip is spent, and this module makes no `mgcv`
comparison at all: its entire job is to reproduce THIS engine's own score's
derivative, exactly.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_family import (
    binomial_cloglog,
    binomial_logit,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient
from polaris_re.core.exceptions import PolarisValidationError


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260903)


def _design(rng: np.random.Generator, n: int, p: int) -> np.ndarray:
    return np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])


def _second_difference_penalty(p: int) -> np.ndarray:
    d = np.diff(np.eye(p), n=2, axis=0)
    return d.T @ d


def _fit_coef(
    rng: np.random.Generator, family, x: np.ndarray, penalty: np.ndarray, weights=None
) -> tuple[np.ndarray, np.ndarray]:
    """A converged-enough coefficient vector to evaluate the score/gradient
    at — the gradient's own module docstring is explicit that ``coef`` is a
    caller-supplied argument, not something this function fits, so any
    coefficient vector exercises the formula; a genuinely fitted one keeps
    the fixture realistic."""
    from polaris_re.analytics.gam_fit import penalized_irls_general

    n, p = x.shape
    beta_true = rng.normal(scale=0.3, size=p)
    eta_true = x @ beta_true
    mu_true = family.link.linkinv(eta_true)
    if family.name == "binomial":
        y = np.clip(mu_true + rng.normal(scale=0.02, size=n), 0.01, 0.99)
    else:
        y = rng.poisson(np.maximum(mu_true, 0.1)).astype(np.float64)
    fit = penalized_irls_general(x, y, family=family, penalty=penalty, weights=weights)
    return y, fit.coef


def _central_difference_gradient(
    y: np.ndarray,
    x: np.ndarray,
    family,
    coef: np.ndarray,
    blocks: tuple[np.ndarray, ...],
    lambdas: np.ndarray,
    *,
    offset=None,
    weights=None,
    gamma: float = 1.0,
    h: float = 1e-5,
) -> np.ndarray:
    """A central difference of the PROFILE score ``V(rho) = score(coef_hat(rho),
    rho)`` in natural-log ``rho`` — the ground truth Wood's gradient (and
    :func:`reml_score_gradient`) actually computes, via the envelope theorem
    (the module docstring: "the indirect dβ̂ term vanishes" ONLY for the
    penalized-deviance term; the ``log|H|`` terms' dependence on ``β̂`` through
    ``W`` does NOT vanish and is exactly what the ``dW/drho`` term captures).

    **REFITS at every perturbed point** — holding ``coef`` fixed while
    perturbing ``rho`` (differencing ``reml_score_general`` directly at one
    fixed ``coef``) computes a DIFFERENT, partial quantity that omits the
    ``dW/drho`` term entirely (``W`` depends only on ``eta = X @ coef``, so a
    fixed ``coef`` makes ``dW/drho`` trivially 0) — this was tried first and
    the mismatch (up to ``0.08``, an order above this fixture's fit residual)
    is exactly the size of the omitted term, not a bug in the analytic
    gradient. Mirrors :func:`~polaris_re.analytics.gam_reml_optimize.penalized_fit_and_score`'s
    own refit-then-score pattern, which is what
    :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`'s
    own finite-difference gradient (pre-slice-7d default) actually differences.
    """
    from polaris_re.analytics.gam_fit import penalized_irls_general

    rho = np.log(lambdas)
    grad = np.zeros(len(blocks))

    def score_at(rho_point: np.ndarray) -> float:
        lam = np.exp(rho_point)
        penalty = sum(lam_j * block for lam_j, block in zip(lam, blocks, strict=True))
        fit = penalized_irls_general(
            x, y, family=family, penalty=penalty, offset=offset, weights=weights
        )
        return reml_score_general(
            y, x, family, fit.coef, blocks, lam, offset=offset, weights=weights, gamma=gamma
        )

    for j in range(len(blocks)):
        up, down = rho.copy(), rho.copy()
        up[j] += h
        down[j] -= h
        grad[j] = (score_at(up) - score_at(down)) / (2 * h)
    return grad


class TestMatchesACentralDifference:
    """The decisive check: does the analytic gradient equal the true
    derivative of :func:`~polaris_re.analytics.gam_reml.reml_score_general`
    — including the exact, alpha-aware ``dW/drho`` term (PLAN slice 7d's own
    "cheap check" found the omission leaves a residual an order of magnitude
    above a trustworthy central difference; the Fisher-only approximation
    closes most but not all of it)."""

    @pytest.mark.parametrize(
        "family",
        [poisson_log(), binomial_logit(), binomial_cloglog()],
        ids=lambda f: f.name + "-" + f.link.name,
    )
    def test_two_block_disjoint_support(self, rng: np.random.Generator, family) -> None:
        n, p = 150, 8
        x = _design(rng, n, p)
        s1 = np.zeros((p, p))
        s1[:4, :4] = _second_difference_penalty(4)
        s2 = np.zeros((p, p))
        s2[4:, 4:] = _second_difference_penalty(4)
        blocks = (s1, s2)
        lambdas = np.array([2.0, 15.0])
        penalty = lambdas[0] * s1 + lambdas[1] * s2
        weights = rng.uniform(0.5, 2.0, size=n) if family.name == "binomial" else None

        y, coef = _fit_coef(rng, family, x, penalty, weights=weights)

        analytic = reml_score_gradient(y, x, family, coef, blocks, lambdas, weights=weights)
        fd = _central_difference_gradient(y, x, family, coef, blocks, lambdas, weights=weights)
        np.testing.assert_allclose(analytic, fd, atol=1e-4)

    def test_three_blocks_badly_scaled_lambda(self, rng: np.random.Generator) -> None:
        """Appendix B's own reason for existing: lambdas spanning several
        decades, so the fourth (log|S|+) gradient term must use the
        structural rank decision, not a naive eigen-cut."""
        family = binomial_cloglog()
        n, p = 200, 9
        x = _design(rng, n, p)
        # Three disjoint 3x3 second-difference blocks embedded in the (p, p) design.
        blocks = []
        for i in range(3):
            block = np.zeros((p, p))
            small = _second_difference_penalty(3)
            block[i * 3 : (i + 1) * 3, i * 3 : (i + 1) * 3] = small
            blocks.append(block)
        blocks = tuple(blocks)
        lambdas = np.array([1.0e5, 1.0, 1.0e-3])
        penalty = sum(lam * block for lam, block in zip(lambdas, blocks, strict=True))
        weights = rng.uniform(0.5, 2.0, size=n)

        y, coef = _fit_coef(rng, family, x, penalty, weights=weights)

        analytic = reml_score_gradient(y, x, family, coef, blocks, lambdas, weights=weights)
        fd = _central_difference_gradient(
            y, x, family, coef, blocks, lambdas, weights=weights, h=1e-4
        )
        np.testing.assert_allclose(analytic, fd, atol=2e-3)

    def test_with_offset_and_gamma(self, rng: np.random.Generator) -> None:
        family = poisson_log()
        n, p = 120, 6
        x = _design(rng, n, p)
        offset = rng.normal(scale=0.1, size=n)
        block = _second_difference_penalty(p)
        blocks = (block,)
        lambdas = np.array([4.0])
        penalty = lambdas[0] * block
        beta_true = rng.normal(scale=0.2, size=p)
        y = rng.poisson(np.exp(offset + x @ beta_true)).astype(np.float64)

        from polaris_re.analytics.gam_fit import penalized_irls_general

        fit = penalized_irls_general(x, y, family=family, penalty=penalty, offset=offset)
        coef = fit.coef
        gamma = 1.3

        analytic = reml_score_gradient(
            y, x, family, coef, blocks, lambdas, offset=offset, gamma=gamma
        )
        fd = _central_difference_gradient(
            y, x, family, coef, blocks, lambdas, offset=offset, gamma=gamma
        )
        np.testing.assert_allclose(analytic, fd, atol=1e-4)


class TestRejectsWhatItMustReject:
    """Mirrors ``reml_score_general``'s own validation — this function
    forms the identical ``H`` and needs the identical preconditions."""

    def test_rejects_a_family_with_estimated_dispersion(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 4)
        block = _second_difference_penalty(4)
        with pytest.raises(PolarisValidationError, match="estimates its own dispersion"):
            reml_score_gradient(
                rng.poisson(3.0, size=30).astype(float),
                x,
                quasipoisson_log(),
                np.zeros(4),
                (block,),
                np.array([1.0]),
            )

    def test_rejects_nonpositive_gamma(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 4)
        block = _second_difference_penalty(4)
        with pytest.raises(PolarisValidationError, match="gamma must be positive"):
            reml_score_gradient(
                rng.poisson(3.0, size=30).astype(float),
                x,
                poisson_log(),
                np.zeros(4),
                (block,),
                np.array([1.0]),
                gamma=0.0,
            )

    def test_rejects_empty_penalty_blocks(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 4)
        with pytest.raises(PolarisValidationError, match="non-empty"):
            reml_score_gradient(
                rng.poisson(3.0, size=30).astype(float),
                x,
                poisson_log(),
                np.zeros(4),
                (),
                np.array([]),
            )

    def test_rejects_a_lambdas_block_count_mismatch(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 4)
        block = _second_difference_penalty(4)
        with pytest.raises(PolarisValidationError, match="one lambda"):
            reml_score_gradient(
                rng.poisson(3.0, size=30).astype(float),
                x,
                poisson_log(),
                np.zeros(4),
                (block,),
                np.array([1.0, 2.0]),
            )

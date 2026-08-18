"""Generalized REML score — mgcv-parity engine, slice 4, part A: the criterion itself.

``docs/PLAN_mgcv_parity_engine.md`` slice 4 is the outer N-dimensional (f)REML
optimiser — "the largest single piece of work in the epic." Before any optimiser
can search over smoothing parameters it needs a criterion that (a) works for the
target formula's actual families (binomial ``logit``/``cloglog``, PLAN §1) and
(b) accepts however many independently-scaled penalty blocks a model has, not
just the tensor MI surface's fixed two. This module builds that criterion —
generalized from ``experience_gam_penalized.reml_score`` (Poisson log-link,
exactly two hardcoded blocks) onto ``gam_fit``'s general IRLS core — and stops
there. **The search over log(lambda) itself is not attempted in this module**;
see ``docs/CONTINUATION_mgcv_parity_engine.md`` for why slice 4 was split this
way and what is left.

**Known-scale families only, and that is the target's own scope, not an
arbitrary cut.** ``experience_gam_penalized.reml_score``'s formula holds the
dispersion at ``gamma`` (Wood's smoothness multiplier, default 1) rather than
treating it as an estimated scale. Generalizing to an ESTIMATED dispersion
(quasi-Poisson) needs a materially different criterion — ``mgcv`` profiles
``phi`` out of the marginal likelihood rather than holding it fixed — that PLAN
slice 3 never had to solve at fixed ``sp`` and this module does not attempt.
The target formula's own family, binomial with a fixed dispersion of 1
(PLAN Anchor 5), never needs it, so the cut does not block slice 4's actual
target. :func:`reml_score_general` raises rather than silently reusing the
known-scale formula against a family it was not derived for.
"""

import numpy as np

from polaris_re.analytics.gam_family import Family
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["reml_score_general"]


def reml_score_general(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    coef: np.ndarray,
    penalty: np.ndarray,
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
) -> float:
    """Laplace-approximate REML for a penalized known-scale GLM (lower is better).

    Identical mathematical form to ``experience_gam_penalized.reml_score``:

        ``V = D/(2*gamma) + log|XᵀWX + S|/2 - log|S|₊/2 - (p - r)*log(gamma)/2``

    generalized only in *which* deviance ``D`` and *which* IRLS working weight
    ``W`` feed it — both now come from ``family`` (:mod:`gam_family`) rather
    than being hardcoded to the Poisson log-link, matching the same working
    weight :func:`gam_fit.penalized_irls_general` converges under
    (``w_i = weights_i * (dmu/deta)_i^2 / V(mu_i)``, Wood §3.1.2/§6.6).

    ``penalty`` is the CALLER-SUMMED ``S_λ = Σⱼ λⱼ Sⱼ`` across however many
    independently-scaled penalty blocks the model has. The score's own formula
    depends on that sum and its rank alone, not on how many blocks produced it
    — so no further generalization is needed to go from the tensor MI surface's
    two blocks to the target formula's thirteen. Evaluated at the supplied
    ``coef``, so callers own convergence: this function does not fit anything.

    Args:
        y: response, ``(n,)`` — counts, or a proportion for binomial.
        x: design matrix, ``(n, p)``.
        family: the distribution/link pair (:mod:`gam_family`). Must have
            ``dispersion_fixed=True`` — see the module docstring.
        coef: the converged penalized-IRLS coefficients at this ``penalty``.
        penalty: ``S_λ``, ``(p, p)``, positive semi-definite.
        offset: fixed addition to the linear predictor, ``(n,)``. Defaults to
            all-zero.
        weights: prior weights, ``(n,)``. Defaults to all-one.
        gamma: Wood's smoothness multiplier — see
            ``experience_gam_penalized.reml_score``'s docstring for the full
            derivation of what it does to the criterion. Same default (1.0,
            a no-op) and same status (adopted from ``mgcv``, unsettled —
            ADR-189 amendment 1).

    Returns:
        The REML score, lower is better.

    Raises:
        PolarisValidationError: if ``family.dispersion_fixed`` is ``False``, or
            ``gamma`` is not positive.
    """
    if not family.dispersion_fixed:
        raise PolarisValidationError(
            f"reml_score_general: family {family.name!r} estimates its own "
            "dispersion (dispersion_fixed=False). The known-scale REML formula "
            "this function implements does not apply to it — see the module "
            "docstring for why quasi-Poisson's REML criterion is out of scope."
        )
    if gamma <= 0.0:
        raise PolarisValidationError(f"gamma must be positive, got {gamma}.")

    n = y.shape[0]
    offset = np.zeros(n, dtype=np.float64) if offset is None else np.asarray(offset)
    weights = np.ones(n, dtype=np.float64) if weights is None else np.asarray(weights)

    eta = offset + x @ coef
    mu = family.link.linkinv(eta)
    deviance = family.deviance(y, mu, weights)

    deta_dmu = family.link.mu_eta(eta)
    irls_weights = weights * deta_dmu**2 / family.variance(mu)
    _, logdet_h = np.linalg.slogdet(x.T @ (irls_weights[:, None] * x) + penalty)

    eigenvalues = np.linalg.eigvalsh(penalty)
    largest = float(eigenvalues.max()) if eigenvalues.size else 0.0
    positive = eigenvalues[eigenvalues > max(largest, 1e-300) * 1e-10]
    logdet_s = float(np.sum(np.log(positive))) if positive.size else 0.0

    # No `gamma == 1.0` short-circuit, matching `experience_gam_penalized.reml_score`
    # (PR #190 review [P2]): `np.log(1.0)` is exactly `0.0`, so the criterion is
    # bit-identical at the default without a float-equality guard.
    scale = float(x.shape[1] - positive.size) * float(np.log(gamma))
    return float(0.5 * deviance / gamma + 0.5 * float(logdet_h) - 0.5 * logdet_s - 0.5 * scale)

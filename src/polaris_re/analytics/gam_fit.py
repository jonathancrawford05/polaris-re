"""General penalized IRLS — Stage B of the ``mgcv``-parity GAM engine.

``docs/PLAN_mgcv_parity_engine.md`` slice 3. :func:`penalized_irls_general`
generalizes ``experience_gam_penalized._penalized_irls`` (Poisson log-link only,
offset only) to any :class:`~polaris_re.analytics.gam_family.Family` / prior-weight
combination, at a caller-supplied (fixed) penalty — the outer smoothing-parameter
optimiser is slice 4's scope, not this one. The old module is untouched (PLAN
Anchor 7); this is new code the tensor MI surface does not depend on.

**Fixed sp only.** PLAN slice 3's acceptance criterion is "at fixed sp on a shared
design, eta matches for each family/link/weight combination" — REML selection for
non-Poisson families is explicitly slice 4's scope (N-dimensional (f)REML), not
generalised here.

**Anchor 2, applied to this module specifically.** ``mgcv`` reparameterises and a
fitted GLM's coefficients are convention-dependent (which parametrisation of the
binomial deviance, which QR pivoting) in ways the fitted surface is not. So the
Stage-B comparison this module feeds is on ``eta``, never on ``beta`` — the same
rule Stage A's own acceptance criteria state explicitly, restated here because this
is the module where it would be easiest to reach for the more familiar "compare
the coefficients" and be wrong.
"""

import numpy as np
from scipy.linalg import LinAlgError as SciPyLinAlgError
from scipy.linalg import cho_factor, cho_solve

from polaris_re.analytics.gam_family import Family, validate_family_inputs
from polaris_re.core.exceptions import PolarisComputationError

__all__ = [
    "GeneralIRLSFit",
    "effective_degrees_of_freedom",
    "pearson_dispersion",
    "penalized_irls_general",
]

_MAX_IRLS_ITER = 100
_IRLS_TOL = 1e-10
"""Matches ``experience_gam_penalized``'s own constants — same convergence
regime, no reason for this generalisation to be looser or tighter."""


class GeneralIRLSFit:
    """The result of :func:`penalized_irls_general`."""

    __slots__ = ("coef", "eta", "mu", "n_iter")

    def __init__(self, coef: np.ndarray, eta: np.ndarray, mu: np.ndarray, n_iter: int) -> None:
        self.coef = coef
        self.eta = eta
        self.mu = mu
        self.n_iter = n_iter


def penalized_irls_general(
    x: np.ndarray,
    y: np.ndarray,
    *,
    family: Family,
    penalty: np.ndarray,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
) -> GeneralIRLSFit:
    """Penalized IRLS at a fixed penalty, for an arbitrary :class:`Family`.

    Solves ``(XᵀWX + S)β = XᵀWz`` to convergence on the deviance (not the
    coefficient shift — see ``experience_gam_penalized._penalized_irls``'s
    docstring for why: in penalty-dominated directions the coefficients rattle
    at round-off long after the deviance has settled).

    Args:
        x: design matrix, ``(n, p)``.
        y: response — counts for Poisson/quasi-Poisson, a proportion in
            ``[0, 1]`` for binomial.
        family: the distribution/link pair (:mod:`polaris_re.analytics.gam_family`).
        penalty: the (fixed) penalty matrix ``S``, ``(p, p)``, positive
            semi-definite. Pass ``np.zeros((p, p))`` for an unpenalized fit.
        offset: a fixed addition to the linear predictor, ``(n,)``. Defaults to
            all-zero. Orthogonal to ``weights`` (PLAN Anchor 5) — both may be
            supplied at once.
        weights: prior weights, ``(n,)``, non-negative. Defaults to all-one.

    Returns:
        :class:`GeneralIRLSFit` with the converged coefficients, linear
        predictor and mean.
    """
    n, p = x.shape
    offset = (
        np.zeros(n, dtype=np.float64) if offset is None else np.asarray(offset, dtype=np.float64)
    )
    weights = (
        np.ones(n, dtype=np.float64) if weights is None else np.asarray(weights, dtype=np.float64)
    )
    y = np.asarray(y, dtype=np.float64)
    validate_family_inputs(x, y, weights, offset)

    link = family.link
    coef = np.zeros(p, dtype=np.float64)
    previous_deviance = np.inf
    eta = offset.copy()
    mu = link.linkinv(eta)
    for iteration in range(1, _MAX_IRLS_ITER + 1):
        eta = offset + x @ coef
        mu = link.linkinv(eta)
        deta_dmu = link.mu_eta(eta)
        irls_weights = weights * deta_dmu**2 / family.variance(mu)
        z = (eta - offset) + (y - mu) / deta_dmu

        lhs = x.T @ (irls_weights[:, None] * x) + penalty
        rhs = x.T @ (irls_weights * z)
        try:
            coef = cho_solve(cho_factor(lhs, lower=True), rhs)
        except (SciPyLinAlgError, np.linalg.LinAlgError):
            coef, *_ = np.linalg.lstsq(lhs, rhs, rcond=None)

        eta = offset + x @ coef
        mu = link.linkinv(eta)
        deviance = family.deviance(y, mu)
        if abs(deviance - previous_deviance) < _IRLS_TOL * (abs(deviance) + 0.1):
            return GeneralIRLSFit(coef=coef, eta=eta, mu=mu, n_iter=iteration)
        previous_deviance = deviance
    raise PolarisComputationError(
        f"Penalized IRLS ({family.name}/{link.name}) did not converge in "
        f"{_MAX_IRLS_ITER} iterations (deviance {previous_deviance:.6g})."
    )


def effective_degrees_of_freedom(
    x: np.ndarray,
    family: Family,
    eta: np.ndarray,
    mu: np.ndarray,
    penalty: np.ndarray,
    weights: np.ndarray | None = None,
) -> float:
    """``tr(F)`` at the converged fit — Anchor 4's EDF definition
    (``experience_gam_penalized.fit``'s own ``edf_total = trace(hat)``,
    verified against ``mgcv``'s ``sum(m$edf)`` to 7.2e-13, ADR-189 amendment 1),
    generalized from the Poisson-only IRLS weight to an arbitrary
    :class:`Family`.

    ``F = (XᵀWX + S)⁻¹XᵀWX`` at the final IRLS working weights ``W``. At
    ``penalty = 0`` with full column rank ``X``, ``F`` is the identity and
    ``tr(F) == p`` exactly — the closed-form check
    ``tests.test_analytics.test_gam_fit`` uses before trusting this on a
    penalized case.
    """
    n = mu.shape[0]
    weights = np.ones(n, dtype=np.float64) if weights is None else weights
    deta_dmu = family.link.mu_eta(eta)
    irls_weights = weights * deta_dmu**2 / family.variance(mu)
    xtwx = x.T @ (irls_weights[:, None] * x)
    try:
        inv = np.linalg.inv(xtwx + penalty)
    except np.linalg.LinAlgError as exc:  # pragma: no cover - singular design
        raise PolarisComputationError("Normal equations are singular at edf time.") from exc
    hat = inv @ xtwx
    return float(np.trace(hat))


def pearson_dispersion(
    y: np.ndarray, mu: np.ndarray, weights: np.ndarray, family: Family, edf: float
) -> float:
    """The Pearson-residual dispersion estimate ``mgcv`` uses for
    ``family$dispersion_estimated`` families (quasi-Poisson here): ``phi = sum(w
    * (y - mu)^2 / V(mu)) / (n - edf)``.

    For a fixed-dispersion family (Poisson, binomial) this is diagnostic only —
    ``mgcv`` holds the scale at 1 regardless of what this returns, matching
    ``m$scale.estimated == FALSE`` — so callers should read
    :attr:`~polaris_re.analytics.gam_family.Family.dispersion_fixed` to decide
    whether the fitted scale is ``1.0`` or this value.
    """
    n = y.shape[0]
    dof_resid = max(n - edf, 1.0)
    pearson_sq = weights * (y - mu) ** 2 / family.variance(mu)
    return float(np.sum(pearson_sq) / dof_resid)

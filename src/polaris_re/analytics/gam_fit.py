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

_MAX_STEP_HALVINGS = 30
"""PLAN slice 7g direction 1 (ADR-222's own registered follow-up): ``mgcv``'s
``gam.control(mgcv.half=...)`` exists for the identical failure mode — a
Newton/IRLS step that makes the PENALIZED OBJECTIVE (deviance + coef'Scoef,
not deviance alone — see :func:`penalized_irls_general`'s ``step_halving``
docstring) worse or non-finite — and this is this module's analogue."""


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
    step_halving: bool = False,
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
        step_halving: PLAN slice 7g direction 1 (ADR-222's own registered
            follow-up). When ``True``, a Newton step that would otherwise
            leave the PENALIZED OBJECTIVE (``deviance + coef'Scoef`` — what
            this solver actually descends on, not deviance alone) worse or
            non-finite is halved (mirrors ``mgcv``'s own
            ``gam.control(mgcv.half=...)``), up to :data:`_MAX_STEP_HALVINGS`
            times, before being accepted. Measured on the ACTUAL
            ``select=TRUE`` N=7 structure ADR-222 found non-convergent
            neighbours on: closes the KKT residual at the search's own
            restart plateau ``0.049335 -> 0.001125`` (~44x) and removes the
            non-convergent neighbourhood entirely — every point a central-
            difference probe found raising :class:`PolarisComputationError`
            before this option converges after (`docs/DEV_SESSION_LOG_
            2026-09-07_mgcv_parity_slice7g_step_halving.md`).

            **Default `False` — every existing caller's behaviour is
            unchanged, and this is deliberate, not merely cautious (PLAN
            Anchor 7).** Gating the halving on the penalized OBJECTIVE
            rather than raw deviance is itself load-bearing (an earlier
            version gated on deviance alone and landed a well-conditioned
            closed-form fixture, `TestPoissonReducesToTheVerifiedRecursion`,
            on a DIFFERENT stationary point 0.0089 away from the true
            minimum — confirmed off the true optimum independently via
            `scipy.optimize.minimize` on `deviance + coef'Scoef`) — but even
            with that fixed, enabling this unconditionally still perturbs
            several already-verified closed-form/finite-difference tests at
            the ``1e-6`` to ``1e-8`` level (`test_gam_derivatives.py`,
            `TestFiniteDiffStep`): whenever a plain Newton step transiently
            increases the objective — a normal, self-correcting property of
            full-step Newton/IRLS near a well-conditioned optimum, not a
            defect — halving takes a different (still correct) path to the
            same fixed point, and that changes exactly how many iterations
            it takes to get there. A handful of this repo's own tests
            resolve the fitted surface finely enough (comparing an analytic
            derivative against a central difference at `h=1e-4`, expecting
            agreement to `1e-8`) to be sensitive to that path, not just the
            destination. So this stays opt-in: :mod:`gam_reml_optimize`'s
            own search functions thread it through as their own
            ``step_halving`` parameter, defaulting to ``False`` there too.

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
    previous_objective = np.inf
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
            candidate = cho_solve(cho_factor(lhs, lower=True), rhs)
        except (SciPyLinAlgError, np.linalg.LinAlgError):
            candidate, *_ = np.linalg.lstsq(lhs, rhs, rcond=None)

        new_coef = candidate
        new_eta = offset + x @ new_coef
        new_mu = link.linkinv(new_eta)
        new_deviance = family.deviance(y, new_mu, weights)

        if step_halving:
            # Halve the distance from `coef` (the previous accepted point)
            # towards `candidate` (the full Newton step) until the PENALIZED
            # OBJECTIVE — not deviance alone, see this function's own
            # ``step_halving`` docstring for why — stops getting worse.
            step = candidate - coef
            new_objective = new_deviance + float(new_coef @ penalty @ new_coef)
            halvings = 0
            while (
                not np.isfinite(new_objective) or new_objective > previous_objective
            ) and halvings < _MAX_STEP_HALVINGS:
                halvings += 1
                step = step * 0.5
                new_coef = coef + step
                new_eta = offset + x @ new_coef
                new_mu = link.linkinv(new_eta)
                new_deviance = family.deviance(y, new_mu, weights)
                new_objective = new_deviance + float(new_coef @ penalty @ new_coef)
            previous_objective = new_objective

        coef = new_coef
        eta = new_eta
        mu = new_mu
        deviance = new_deviance
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

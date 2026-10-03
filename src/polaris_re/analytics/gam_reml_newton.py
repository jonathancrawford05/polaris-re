"""Safeguarded Newton outer search for the REML smoothing parameters —
outer-solver epic (``docs/PLAN_wood_outer_solver.md``), Slice 1.

**Why this exists (ADR-241).** The REML criterion is right; the L-BFGS-B search
over it is not reliable. Slice 0 measured two defects, neither of them the
start: an UNCAPPED first quasi-Newton step that was accepted 11.8 decades onto
the ``lambda -> infinity`` plateau (gaussian L1), and a termination test
(``factr``, relative function reduction) that is not a stationarity test and
declared ``converged=True`` with the gradient still ~2 per decade (quasipoisson
3c). This module replaces the search, not the start and not the criterion:
every start strategy that existed is one more sample for a search whose defect
is what it does *after* the start.

**What it does.** Works in natural-log ``rho = log(lambda)`` (the units
``mgcv``'s controls are stated in) and, per iteration:

1. evaluates the score and its ANALYTIC gradient
   (:func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient`, or
   :func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient_profiled`
   for a free-scale family);
2. stops if the projected gradient is below ``conv_tol`` times the score's own
   scale — a STATIONARITY test, never a function-reduction test;
3. drops already-converged directions (``|g_j|`` below that same tolerance, or
   pinned at a bound with the gradient pushing outward) from the step;
4. forms the Hessian of the remaining directions — EXACT by default
   (:func:`~polaris_re.analytics.gam_reml_hessian.reml_score_hessian`, Slice 2,
   ADR-243), or ``hessian="difference"``: Slice 1's central difference of the
   analytic gradient, kept so the two can be compared — forces it positive definite by
   eigendecomposition (negative eigenvalues flipped, tiny ones floored), and
   takes the Newton step;
5. caps the step at ``max_step`` natural-log units, clips it to the bounds, and
   halves it until the score decreases (``max_half`` times);
6. if no halving improves the score, retries along the steepest-descent
   direction capped at ``max_sd_step``; if that also fails the search ends
   ``converged=False`` and says so.

**Constants.** ``max_step = 5``, ``max_sd_step = 2``, ``max_half = 30`` and
``conv_tol = 1e-6`` are ``mgcv``'s documented ``gam.control()$newton`` defaults
(``maxNstep``, ``maxSstep``, ``maxHalf``, ``conv.tol``; read from
``mgcv:::newton`` 1.9.1 on tier 1 — behaviour and constants, not transcribed
code, ``mgcv`` being GPL and this project MIT). They are the method's own
numbers, named as such, and not tuned to any cell. The Hessian floor
``sqrt(machine epsilon) * max|eigenvalue|`` is the standard relative cut for
"numerically zero curvature". The central-difference step ``hessian_step`` is
this module's own (a stable-step measurement, see its docstring).
"""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_fit import effective_degrees_of_freedom
from polaris_re.analytics.gam_reml import penalty_block_square_roots
from polaris_re.analytics.gam_reml_gradient import (
    reml_score_gradient,
    reml_score_gradient_profiled,
)
from polaris_re.analytics.gam_reml_hessian import (
    reml_score_hessian,
    reml_score_hessian_profiled,
)
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import ComparedQuantity, VerificationClaim

__all__ = [
    "MGCV_NEWTON_CONV_TOL",
    "MGCV_NEWTON_MAX_HALF",
    "MGCV_NEWTON_MAX_NSTEP",
    "MGCV_NEWTON_MAX_SSTEP",
    "NewtonLambdaSelection",
    "newton_select_lambdas",
    "newton_variant",
]

MGCV_NEWTON_MAX_NSTEP = 5.0
"""``gam.control()$newton$maxNstep`` — the cap on any Newton step, in
natural-log ``lambda`` units (about 2.17 decades)."""

MGCV_NEWTON_MAX_SSTEP = 2.0
"""``gam.control()$newton$maxSstep`` — the cap on a steepest-descent step."""

MGCV_NEWTON_MAX_HALF = 30
"""``gam.control()$newton$maxHalf`` — step halvings before a direction is
declared exhausted."""

MGCV_NEWTON_CONV_TOL = 1.0e-6
"""``gam.control()$newton$conv.tol`` — gradient tolerance relative to the
score's own scale."""

_HESSIAN_STEP = 1.0e-3
"""Central-difference step (natural-log units) for the Hessian of the analytic
gradient. The gradient is a smooth function of ``rho`` evaluated at a
converged inner fit, so unlike a difference of the SCORE (ADR-212's noise
floor) a difference of the gradient at ``1e-3`` has truncation error
``O(h^2) ~ 1e-6`` relative and noise ``~ 1e-10 / h`` — both far below the
curvature being estimated. Verified against the Hessian at a doubled step in
the tests."""

_LN10 = float(np.log(10.0))


@dataclass(frozen=True)
class NewtonLambdaSelection:
    """What :func:`newton_select_lambdas` returns. Field names match
    :class:`~polaris_re.analytics.gam_reml_optimize.ContinuousLambdaSelection`
    so ``fit_polaris_gam`` consumes either; the rest is what the search did."""

    log_lambda: np.ndarray
    """``log10(lambda)`` at the stop, one entry per penalty block."""
    lambda_: np.ndarray
    coef: np.ndarray
    reml_score: float
    edf_total: float
    n_function_evals: int
    """Penalized fits spent: score+gradient evaluations at trial points, plus
    (``hessian="difference"`` only) the Hessian's central-difference gradient
    evaluations. The exact Hessian costs no extra fit."""
    n_rejected: int
    """Trial points whose inner fit did not converge (treated as a failed step)."""
    converged: bool
    """``True`` ONLY when the projected gradient met the score-scaled
    tolerance — the stationarity test. A stall (no step improves) is
    ``False``, whatever the gradient."""
    at_bound: bool
    message: str
    n_iterations: int = 0
    max_abs_projected_gradient: float | None = None
    """``max |g^P|`` at the stop, natural-log units."""
    gradient_tolerance: float | None = None
    """The score-scaled tolerance ``max |g^P|`` was tested against."""
    accepted_log10: list[np.ndarray] = field(default_factory=list)
    """The start, then every ACCEPTED iterate, in ``log10(lambda)``."""
    max_accepted_step_decades: float = 0.0
    """Largest single-coordinate move of any accepted iterate, in decades."""
    hessian_condition: float = float("nan")
    """``cond(X'WX + S)`` at the stop. DIAGNOSTIC ONLY — never gates anything."""
    gradient_precision_floor: float = float("nan")
    """``eps * hessian_condition``: the order of the analytic gradient's own
    rounding error at the stop (the ``tr(H^-1 lambda S_j)`` terms are computed
    through ``H``). Reported beside :attr:`max_abs_projected_gradient` so a
    stall can be read as "gradient above tolerance but within what this
    arithmetic can resolve" (Wood 2011 §3.1's motivation, Slice 3) or not.
    It is NOT a tolerance and no constant multiplies it."""


def _project(g: np.ndarray, rho: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out = g.copy()
    out[(rho <= lo) & (g > 0.0)] = 0.0  # at lower bound, descent would go below it
    out[(rho >= hi) & (g < 0.0)] = 0.0  # at upper bound, descent would go above it
    return out


def newton_select_lambdas(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    *,
    x0: np.ndarray,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
    bounds: tuple[float, float] = (-2.0, 12.0),
    maxiter: int = 200,
    conv_tol: float = MGCV_NEWTON_CONV_TOL,
    max_step: float = MGCV_NEWTON_MAX_NSTEP,
    max_sd_step: float = MGCV_NEWTON_MAX_SSTEP,
    max_half: int = MGCV_NEWTON_MAX_HALF,
    hessian_step: float = _HESSIAN_STEP,
    step_halving: bool = False,
    hessian: Literal["exact", "difference"] = "exact",
) -> NewtonLambdaSelection:
    """Select ``log10(lambda)`` for every block by safeguarded Newton from ``x0``.

    ``x0`` is REQUIRED (``log10(lambda)``): this module has no start strategy
    and must not grow one (ADR-241). ``bounds`` are in ``log10(lambda)`` like
    every other search in this package; the search itself runs in natural-log.

    Raises:
        PolarisValidationError: shape mismatch, ``gamma`` with a free-scale
            family, or ``lo >= hi``.
        PolarisComputationError: if the start point itself cannot be fitted.
    """
    m = len(penalty_blocks)
    x0 = np.asarray(x0, dtype=np.float64)
    if x0.shape != (m,):
        raise PolarisValidationError(
            f"newton_select_lambdas: x0 has shape {x0.shape}, expected ({m},)."
        )
    if bounds[0] >= bounds[1]:
        raise PolarisValidationError(f"newton_select_lambdas: bounds {bounds} are not lo < hi.")
    if hessian not in ("exact", "difference"):
        raise PolarisValidationError(
            f"newton_select_lambdas: hessian must be 'exact' or 'difference', got {hessian!r}."
        )
    if not family.dispersion_fixed and gamma != 1.0:
        raise PolarisValidationError("newton_select_lambdas: gamma is undefined for free scale.")
    lo, hi = bounds[0] * _LN10, bounds[1] * _LN10
    sqrt_blocks = penalty_block_square_roots(penalty_blocks)
    tally = {"fits": 0, "rejected": 0}

    def evaluate(rho: np.ndarray) -> tuple[np.ndarray, float, np.ndarray] | None:
        """``(coef, score, gradient)`` at ``rho``, or ``None`` if the inner fit fails."""
        tally["fits"] += 1
        log10 = rho / _LN10
        try:
            coef, score = penalized_fit_and_score(
                y,
                x,
                family,
                penalty_blocks,
                log10,
                offset=offset,
                weights=weights,
                gamma=gamma,
                penalty_sqrt_blocks=sqrt_blocks,
                step_halving=step_halving,
            )
            lambdas = np.exp(rho)
            if family.dispersion_fixed:
                grad = reml_score_gradient(
                    y,
                    x,
                    family,
                    coef,
                    penalty_blocks,
                    lambdas,
                    offset=offset,
                    weights=weights,
                    gamma=gamma,
                )
            else:
                grad = reml_score_gradient_profiled(
                    y, x, family, coef, penalty_blocks, lambdas, offset=offset, weights=weights
                )
        except (PolarisComputationError, np.linalg.LinAlgError):
            tally["rejected"] += 1
            return None
        if not (np.isfinite(score) and np.all(np.isfinite(grad))):
            tally["rejected"] += 1
            return None
        return coef, float(score), grad

    def exact_hessian(rho: np.ndarray, coef: np.ndarray, free: np.ndarray) -> np.ndarray | None:
        """The analytic Hessian restricted to the ``free`` coordinates, from the
        fit already in hand (no extra penalized fit). ``None`` if it cannot be
        formed (a singular ``H``)."""
        lambdas = np.exp(rho)
        try:
            if family.dispersion_fixed:
                full = reml_score_hessian(
                    y,
                    x,
                    family,
                    coef,
                    penalty_blocks,
                    lambdas,
                    offset=offset,
                    weights=weights,
                    gamma=gamma,
                )
            else:
                full = reml_score_hessian_profiled(
                    y, x, family, coef, penalty_blocks, lambdas, offset=offset, weights=weights
                )
        except (PolarisComputationError, np.linalg.LinAlgError):
            return None
        if not np.all(np.isfinite(full)):
            return None
        return np.asarray(full[np.ix_(free, free)], dtype=np.float64)

    def difference_hessian(rho: np.ndarray, free: np.ndarray) -> np.ndarray | None:
        """Central difference of the analytic gradient over the ``free``
        coordinates (one-sided at a bound). ``None`` if any probe fails."""
        idx = np.flatnonzero(free)
        h_mat = np.zeros((idx.size, idx.size), dtype=np.float64)
        for col, j in enumerate(idx):
            up = rho.copy()
            dn = rho.copy()
            up[j] = min(rho[j] + hessian_step, hi)
            dn[j] = max(rho[j] - hessian_step, lo)
            ev_up, ev_dn = evaluate(up), evaluate(dn)
            if ev_up is None or ev_dn is None:
                return None
            h_mat[:, col] = (ev_up[2][idx] - ev_dn[2][idx]) / (up[j] - dn[j])
        return 0.5 * (h_mat + h_mat.T)

    rho = np.clip(x0 * _LN10, lo, hi)
    current = evaluate(rho)
    if current is None:
        raise PolarisComputationError(
            "newton_select_lambdas: the penalized fit at the starting point did not converge."
        )
    coef, score, grad = current
    accepted = [rho / _LN10]
    max_move = 0.0
    converged = False
    message = f"maxiter={maxiter} reached"
    n_iter = 0
    tol = conv_tol * (1.0 + abs(score))
    for n_iter in range(1, maxiter + 1):
        tol = conv_tol * (1.0 + abs(score))
        g_proj = _project(grad, rho, lo, hi)
        if float(np.max(np.abs(g_proj))) <= tol:
            converged = True
            message = "gradient test: max abs projected gradient <= conv_tol * (1 + abs(score))"
            n_iter -= 1
            break
        free = np.abs(g_proj) > tol  # converged directions are dropped from the step
        h_free = (
            exact_hessian(rho, coef, free) if hessian == "exact" else difference_hessian(rho, free)
        )
        step = np.zeros(m, dtype=np.float64)
        if h_free is not None:
            evals, evecs = np.linalg.eigh(h_free)
            floor = float(np.sqrt(np.finfo(np.float64).eps)) * float(np.max(np.abs(evals)))
            mag = np.maximum(np.abs(evals), max(floor, np.finfo(np.float64).tiny))
            step[free] = -(evecs @ ((evecs.T @ g_proj[free]) / mag))
        sd = np.zeros(m, dtype=np.float64)
        sd[free] = -g_proj[free]
        directions = [(step, max_step)] if h_free is not None else []
        directions.append((sd, max_sd_step))

        moved = None
        for direction, cap in directions:
            size = float(np.max(np.abs(direction)))
            if size == 0.0:
                continue
            trial_step = direction * min(1.0, cap / size)
            for _ in range(max_half + 1):
                trial = np.clip(rho + trial_step, lo, hi)
                result = evaluate(trial)
                if result is not None and result[1] < score:
                    moved = (trial, result)
                    break
                trial_step = 0.5 * trial_step
            if moved is not None:
                break
        if moved is None:
            message = "stalled: no Newton or steepest-descent step improved the score"
            break
        move = float(np.max(np.abs(moved[0] - rho))) / _LN10
        max_move = max(max_move, move)
        rho = moved[0]
        coef, score, grad = moved[1]
        accepted.append(rho / _LN10)

    log_lambda = rho / _LN10
    penalty = np.zeros_like(penalty_blocks[0])
    for lam, block in zip(np.exp(rho), penalty_blocks, strict=True):
        penalty = penalty + lam * block
    eta = (np.zeros_like(y) if offset is None else np.asarray(offset)) + x @ coef
    mu = family.link.linkinv(eta)
    edf_total = effective_degrees_of_freedom(x, family, eta, mu, penalty, weights)
    w_obs = family.observed_information_weight(
        y, eta, np.ones_like(y) if weights is None else np.asarray(weights)
    )
    kappa = float(np.linalg.cond(x.T @ (w_obs[:, None] * x) + penalty))
    return NewtonLambdaSelection(
        log_lambda=log_lambda,
        lambda_=10.0**log_lambda,
        coef=coef,
        reml_score=score,
        edf_total=edf_total,
        n_function_evals=tally["fits"],
        n_rejected=tally["rejected"],
        converged=converged,
        at_bound=bool(
            np.any(np.isclose(log_lambda, bounds[0])) or np.any(np.isclose(log_lambda, bounds[1]))
        ),
        message=message,
        n_iterations=n_iter,
        max_abs_projected_gradient=float(np.max(np.abs(_project(grad, rho, lo, hi)))),
        gradient_tolerance=conv_tol * (1.0 + abs(score)),
        accepted_log10=accepted,
        max_accepted_step_decades=max_move,
        hessian_condition=kappa,
        gradient_precision_floor=float(np.finfo(np.float64).eps) * kappa,
    )


_LBFGSB_SEARCH = "gam_reml_optimize.select_lambdas_continuous"
_NEWTON_SEARCH = "gam_reml_newton.newton_select_lambdas (outer='newton', initial.spg start)"


def newton_variant(claim: VerificationClaim) -> VerificationClaim:
    """The same declared claim with the smoothing-parameter search named as the
    Newton one — derived from the existing claim, never re-written, so the
    published table's producers name the code under test (PR #251 review P1-b).
    Provenance per quantity is unchanged: the search is part of the Polaris
    producer either way, and the recipe still excludes ``mgcv``'s outputs."""
    return VerificationClaim(
        claim=claim.claim.replace(_LBFGSB_SEARCH, _NEWTON_SEARCH),
        quantities=tuple(
            ComparedQuantity(
                quantity=q.quantity,
                left_producer=q.left_producer.replace(_LBFGSB_SEARCH, _NEWTON_SEARCH),
                right_producer=q.right_producer,
                provenance=q.provenance,
            )
            for q in claim.quantities
        ),
    )

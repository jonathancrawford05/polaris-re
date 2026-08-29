"""Continuous outer optimiser over log10(lambda) — mgcv-parity engine, slice 4 part B.

``docs/PLAN_mgcv_parity_engine.md`` slice 4 splits into two parts. Part A (DONE,
ADR-196) built and verified the REML criterion itself
(:func:`~polaris_re.analytics.gam_reml.reml_score_general`) against ``mgcv`` —
generalized to an arbitrary known-scale family and any number of
independently-scaled penalty blocks, agreeing to float round-trip precision.
Part A deliberately stopped there: "The search over log(lambda) itself is not
attempted in this module." This module is that search.

**Newton/quasi-Newton, per PLAN §3.** The target formula needs 13-21 smoothing
parameters; a three-point grid in that many dimensions is 4.8 million fits —
"the grid is not slow there, it is impossible." This module uses
``scipy.optimize.minimize`` (L-BFGS-B, a quasi-Newton method) with a
finite-difference gradient of the already-verified
:func:`~polaris_re.analytics.gam_reml.reml_score_general`, refitting
:func:`~polaris_re.analytics.gam_fit.penalized_irls_general` at every trial
point. Nothing here re-derives the score or the fit — both are the same
functions slice 3 and slice 4 part A already built and verified independently
against ``mgcv``; this module only adds the search loop around them.

**Two searches over lambda, and only this one is continuous — deliberately.**
``experience_gam_penalized.select_lambdas_reml`` (the SHIPPED, production
tensor-MI-surface selector) keeps its 2-D grid. ADR-186 chose the grid
*deliberately*, for reproducibility: no optimiser state, no convergence path,
no last-digit drift across platforms or SciPy versions (Anchor 3). That
argument does not disappear here — it is simply out of scope, because a grid
in 13-21 dimensions is not an option for the target formula the way it is at
two. Re-pointing the *production* selector at a continuous search is
explicitly a separate decision reserved for the maintainer
(``docs/CONTINUATION_mgcv_parity_engine.md``, "Two searches, not one") — this
module is new code for the new N-dimensional engine PLAN slice 4 targets, and
does not touch ``experience_gam_penalized.py`` (PLAN Anchor 7).

**ADR-198's registered prediction is what this module exists to test.** Every
free-``sp`` conformance cell disagrees with ``mgcv``'s own continuous REML
selection by *less than half the production grid's own refinement step*
(0.0645 / 0.0791 / 0.1048 / 0.0776 decades against a half-step of 0.125).
ADR-198 hypothesises that this residual **is** the grid's own quantisation —
that a continuous optimiser on the identical criterion should drive the
disagreement toward its own convergence tolerance rather than leaving it near
0.1. Measuring that, either way, is this module's decisive comparison; see
``docs/CONFORMANCE_LEDGER.md`` for the result.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_fit import effective_degrees_of_freedom, penalized_irls_general
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "ContinuousLambdaSelection",
    "penalized_fit_and_score",
    "select_lambdas_continuous",
]

DEFAULT_LOG10_BOUNDS = (-2.0, 8.0)
"""Same search range as ``experience_gam_penalized.LAMBDA_LOG10_BOUNDS`` — not
imported from there, because that constant belongs to the grid selector this
module deliberately does not touch (PLAN Anchor 7), and a shared default
value is not the same thing as a shared owner. Both happen to be right for
the identical reason (Wood's own discussion of representable smoothing
regimes), which is why they agree."""

_REJECTED_SCORE = 1.0e10
"""Score assigned to a trial ``log10(lambda)`` whose own penalized IRLS does
not converge — mirrors ``select_lambdas_reml``'s ``+inf`` grid rejection, but
FINITE. A finite-difference gradient straddling an infinite objective value
returns ``nan`` and stalls L-BFGS-B's line search rather than steering it
away from the bad region, so the rejection has to stay differentiable-adjacent:
large enough that no converged point could ever compete with it, finite
enough that SciPy's numerical gradient stays finite too."""


def penalized_fit_and_score(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    log_lambda: np.ndarray,
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
) -> tuple[np.ndarray, float]:
    """One penalized fit and its REML score at ``log10(lambda) = log_lambda``.

    ``penalty_blocks`` is one ``(p, p)`` matrix per independently-scaled
    smoothing parameter — already padded to the full design width, the same
    convention ``DesignExport.s_age``/``s_year`` and
    ``gam_reml_production_check._padded_penalty`` use.
    ``S_lambda = sum_j 10**log_lambda[j] * penalty_blocks[j]`` is assembled
    here and handed to :func:`~polaris_re.analytics.gam_fit.penalized_irls_general`
    and :func:`~polaris_re.analytics.gam_reml.reml_score_general` — the two
    functions PLAN slice 3 and slice 4 part A already built and verified
    independently against ``mgcv``. This function adds no new fitting or
    scoring formula; it only assembles the caller-summed penalty a
    multi-block search needs at each trial point.

    Args:
        y: response, ``(n,)``.
        x: design matrix, ``(n, p)``.
        family: the distribution/link pair. Must have ``dispersion_fixed=True``
            (``reml_score_general``'s own requirement).
        penalty_blocks: one ``(p, p)`` matrix per smoothing parameter.
        log_lambda: ``log10(lambda)`` for each block, ``(len(penalty_blocks),)``.
        offset: fixed addition to the linear predictor, ``(n,)``. Defaults to
            all-zero.
        weights: prior weights, ``(n,)``. Defaults to all-one.
        gamma: Wood's smoothness multiplier — passed through to
            ``reml_score_general`` unchanged.

    Returns:
        ``(coef, score)`` — the converged coefficients and the REML score at
        them, lower is better.

    Raises:
        PolarisComputationError: propagated from a non-converging penalized fit.
    """
    log_lambda = np.asarray(log_lambda, dtype=np.float64)
    if log_lambda.shape != (len(penalty_blocks),):
        raise PolarisValidationError(
            f"log_lambda has shape {log_lambda.shape}, but {len(penalty_blocks)} "
            "penalty_blocks were supplied — one log10(lambda) entry per block."
        )
    lambdas = 10.0**log_lambda
    penalty = np.zeros_like(penalty_blocks[0])
    for lam, block in zip(lambdas, penalty_blocks, strict=True):
        penalty = penalty + lam * block
    fit = penalized_irls_general(
        x, y, family=family, penalty=penalty, offset=offset, weights=weights
    )
    score = reml_score_general(
        y,
        x,
        family,
        fit.coef,
        penalty_blocks,
        lambdas,
        offset=offset,
        weights=weights,
        gamma=gamma,
    )
    return fit.coef, score


@dataclass(frozen=True)
class ContinuousLambdaSelection:
    """What :func:`select_lambdas_continuous` returns.

    Mirrors the shape of ``experience_gam_penalized.LambdaSelection`` and
    ``gam_reml_production_check.CorrectedLambdaSelection`` (log10 lambda,
    fitted coefficients, the score, and enough diagnostics to tell a genuine
    optimum from a rejected search) but is not a subtype of either — this is
    a different search strategy (continuous, not grid) over a different
    criterion signature (N blocks, any known-scale family), not a variant of
    the production selector.
    """

    log_lambda: np.ndarray
    """``log10(lambda)`` at the optimiser's reported minimum, one entry per
    penalty block, in the order ``penalty_blocks`` was supplied."""
    lambda_: np.ndarray
    """``10 ** log_lambda`` — the natural-units smoothing parameters."""
    coef: np.ndarray
    """The penalized-IRLS coefficients at ``log_lambda``."""
    reml_score: float
    """The REML score at ``log_lambda`` — lower is better."""
    edf_total: float
    """``tr(F)`` at ``log_lambda`` — Anchor 4's EDF definition, via
    :func:`~polaris_re.analytics.gam_fit.effective_degrees_of_freedom`."""
    n_function_evals: int
    """SciPy's own ``nfev`` — how many ``(fit, score)`` evaluations the
    search cost, the continuous-search analogue of ``LambdaSelection``'s
    ``n_evaluated``."""
    n_rejected: int
    """Trial points whose own penalized IRLS did not converge and were
    scored :data:`_REJECTED_SCORE` — mirrors ``LambdaSelection.n_rejected``,
    the grid selector's identical bookkeeping for the identical situation."""
    converged: bool
    """SciPy's own convergence flag (``OptimizeResult.success``)."""
    at_bound: bool
    """Whether any entry of ``log_lambda`` sits on ``bounds`` — the same
    caveat ``select_lambdas_reml``'s callers already read off
    ``lambda_is_at_bound``: a selection at a bound is "at least this",
    since ``mgcv``'s own optimiser is unbounded."""
    message: str
    """SciPy's own human-readable termination message."""


def select_lambdas_continuous(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
    x0: np.ndarray | None = None,
    bounds: tuple[float, float] = DEFAULT_LOG10_BOUNDS,
    gtol: float = 1.0e-8,
    maxiter: int = 200,
) -> ContinuousLambdaSelection:
    """Choose ``log10(lambda)`` for every penalty block by continuous REML
    minimisation (``scipy.optimize.minimize``, L-BFGS-B).

    Starts at the centre of ``bounds`` for every block by default — the same
    starting point ``select_lambdas_reml``'s coarse sweep centres on — and
    refits :func:`penalized_fit_and_score` at every trial point SciPy's line
    search proposes. A trial whose own IRLS does not converge, or whose score
    is non-finite, is scored :data:`_REJECTED_SCORE` rather than raised
    (mirrors the grid selector's rejection rule): a bad point should steer
    the search away, not crash it.

    Args:
        y, x, family, penalty_blocks, offset, weights, gamma: as
            :func:`penalized_fit_and_score`.
        x0: starting ``log10(lambda)`` for every block. Defaults to the
            centre of ``bounds`` for each — an uninformative start, matching
            the grid search's own coarse-sweep centre.
        bounds: ``(lo, hi)`` on ``log10(lambda)``, applied to every block.
            Same default range as the production grid's own
            ``LAMBDA_LOG10_BOUNDS`` (see the module docstring for why it is
            not imported from there).
        gtol: SciPy's projected-gradient convergence tolerance.
        maxiter: SciPy's iteration cap.

    Returns:
        :class:`ContinuousLambdaSelection`.

    Raises:
        PolarisValidationError: if ``penalty_blocks`` is empty, or ``x0``'s
            shape does not match ``penalty_blocks``.
        PolarisComputationError: if every trial point SciPy visited was
            rejected — the search found nothing to report, mirroring
            ``select_lambdas_reml``'s identical refusal to fabricate a
            selection from a fully-rejected grid. Can also propagate,
            unguarded, from the single re-fit at SciPy's reported minimum
            (below) — narrow in practice, since that point was reached
            through a converging search path, but not impossible.
    """
    n_blocks = len(penalty_blocks)
    if n_blocks == 0:
        raise PolarisValidationError("select_lambdas_continuous needs at least one penalty block.")
    lo, hi = bounds
    start = (
        np.full(n_blocks, (lo + hi) / 2.0, dtype=np.float64)
        if x0 is None
        else np.asarray(x0, dtype=np.float64)
    )
    if start.shape != (n_blocks,):
        raise PolarisValidationError(
            f"x0 has shape {start.shape}, but {n_blocks} penalty_blocks were supplied."
        )

    tally = {"rejected": 0, "evaluated": 0}
    any_converged = {"flag": False}

    def objective(log_lambda: np.ndarray) -> float:
        tally["evaluated"] += 1
        try:
            _, score = penalized_fit_and_score(
                y,
                x,
                family,
                penalty_blocks,
                log_lambda,
                offset=offset,
                weights=weights,
                gamma=gamma,
            )
        except PolarisComputationError:
            tally["rejected"] += 1
            return _REJECTED_SCORE
        if not np.isfinite(score):
            tally["rejected"] += 1
            return _REJECTED_SCORE
        any_converged["flag"] = True
        return score

    result = minimize(
        objective,
        start,
        method="L-BFGS-B",
        bounds=[bounds] * n_blocks,
        options={"gtol": gtol, "maxiter": maxiter},
    )
    if not any_converged["flag"]:
        raise PolarisComputationError(
            f"Continuous REML selection rejected every one of {tally['evaluated']} trial "
            f"points — no penalized fit converged anywhere in log10 lambda {bounds}. The "
            "starting point is not an answer, so this raises rather than returning one."
        )

    log_lambda = np.asarray(result.x, dtype=np.float64)
    coef, score = penalized_fit_and_score(
        y, x, family, penalty_blocks, log_lambda, offset=offset, weights=weights, gamma=gamma
    )
    penalty = np.zeros_like(penalty_blocks[0])
    for log_lam, block in zip(log_lambda, penalty_blocks, strict=True):
        penalty = penalty + (10.0**log_lam) * block
    eta = (np.zeros_like(y) if offset is None else np.asarray(offset)) + x @ coef
    mu = family.link.linkinv(eta)
    edf_total = effective_degrees_of_freedom(x, family, eta, mu, penalty, weights)

    return ContinuousLambdaSelection(
        log_lambda=log_lambda,
        lambda_=10.0**log_lambda,
        coef=coef,
        reml_score=float(score),
        edf_total=edf_total,
        n_function_evals=int(result.nfev),
        n_rejected=tally["rejected"],
        converged=bool(result.success),
        at_bound=bool(np.any(np.isclose(log_lambda, lo)) or np.any(np.isclose(log_lambda, hi))),
        message=str(result.message),
    )

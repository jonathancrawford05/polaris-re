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
from scipy.optimize import OptimizeResult, minimize

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_fit import effective_degrees_of_freedom, penalized_irls_general
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "ContinuousLambdaSelection",
    "MultiStartLambdaSelection",
    "penalized_fit_and_score",
    "penalized_fit_score_and_gradient",
    "projected_gradient",
    "select_lambdas_continuous",
    "select_lambdas_continuous_multistart",
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

_BOUND_ATOL = 1.0e-8
"""How close to a bound counts as pinned TO it, in
:func:`projected_gradient`. SciPy returns a bound-active component as the
bound value to within its own rounding rather than exactly, so an equality
test would misread a pinned component as interior and then treat the bound's
own restoring gradient as an unconverged residual — the exact false positive
PLAN slice 7f's fix must not manufacture. Absolute, because the bounds this
module is called with (``PRODUCTION_LOG10_BOUNDS = (-2.0, 12.0)``) are O(1)
to O(10) in ``log10(lambda)``."""

_FINITE_DIFF_STEP = 1.0e-5
"""``scipy.optimize.minimize(method="L-BFGS-B")``'s own default forward-
difference step (``eps=1.4901161193847656e-08``, absolute) sits INSIDE this
objective's own noise floor, not below it — PLAN slice 5d's own measurement
(``docs/DECISIONS.md`` ADR-212), not a value chosen to move any comparison
against ``mgcv``.

``penalized_fit_and_score`` refits :func:`~polaris_re.analytics.gam_fit.penalized_irls_general`
at every trial point, and that fit only converges to its own ``_IRLS_TOL``
(``gam_fit.py``, ``1e-10`` relative on deviance) — so two trial points closer
together than that residual differ by numerical noise, not signal. Measured
directly (forward differences of the SAME objective at a fixed point, varying
only the step): the derivative estimate is stable to four significant figures
for every ``h`` from ``1e-1`` down to ``1e-6`` (matching an independent
central-difference cross-check at each ``h``), then breaks down catastrophically
at ``h <= 1e-9`` — including a WRONG-SIGN estimate at ``h = 1e-9``. SciPy's own
default step falls inside that broken region (``1.49e-8`` is between the last
stable reading at ``1e-6`` and the sign-flip at ``1e-9``), which is why
:func:`select_lambdas_continuous` was reporting spurious convergence: its
gradient norm at a reported "minimum" measures ``~0.55`` under an independent
central-difference check with a stable step, not the near-zero SciPy's own
noise-corrupted internal estimate implied.

``1e-5`` is two orders of magnitude above the measured stable/unstable
boundary — a safety margin on OUR OWN measured noise floor, not a tuned
constant (Anchor 8 / ``ROUTINE_MGCV_PARITY.md``'s "never widen a tolerance to
close a gap": this step was derived from this module's own IRLS tolerance and
verified against an independent central-difference estimate, both entirely
without reference to ``mgcv``, before it was ever checked against ``mgcv`` at
all).

**This default is a trade-off, not a universal improvement, and PR #216's own
review caught it** ([P1-2]): an independent probe on a SEPARATE, well-
conditioned single-block design (unrelated to the N=4 structure this value
was measured on) found SciPy's default step accurate to ``~6e-6`` there,
while ``1e-5`` was ~10x LESS accurate — exactly what forward-difference
truncation error predicts on a problem with no noise-floor problem to begin
with. So this module trades a digit of gradient accuracy on easy problems
for robustness against the specific spurious-convergence failure mode
measured above. :func:`select_lambdas_continuous` exposes ``finite_diff_step``
so a caller who knows their own problem is well-conditioned (no near-flat
block, no badly-scaled lambda spread) may pass a smaller value; this module's
default stays conservative because the target multi-term formula's own N=4
structure is exactly the badly-conditioned case, not the easy one."""


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


def penalized_fit_score_and_gradient(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    log_lambda: np.ndarray,
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
) -> tuple[np.ndarray, float, np.ndarray]:
    """:func:`penalized_fit_and_score`, plus the analytic gradient of the
    score in ``log10(lambda)`` units — PLAN slice 7d.

    One penalized fit produces everything both the value and the gradient
    need (:func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient`
    reuses the SAME converged ``coef``), so this costs one IRLS solve —
    against the ``2 * len(penalty_blocks)`` extra solves SciPy's own
    forward-difference gradient needs per trial point when no ``jac=`` is
    supplied (``select_lambdas_continuous``'s own module docstring: "8 nested
    penalized-IRLS solves per gradient" at ``select=True``'s 7 blocks).

    Returns:
        ``(coef, score, gradient)`` — ``gradient`` is ``(len(penalty_blocks),)``,
        ``d(score)/d(log10(lambda)ⱼ)`` (scaled from
        :func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient`'s
        own natural-log convention by ``ln(10)``, matching
        ``select_lambdas_continuous``'s own search variable).

    Raises:
        PolarisComputationError: propagated from a non-converging penalized fit.
    """
    coef, score = penalized_fit_and_score(
        y, x, family, penalty_blocks, log_lambda, offset=offset, weights=weights, gamma=gamma
    )
    lambdas = 10.0 ** np.asarray(log_lambda, dtype=np.float64)
    gradient_natural = reml_score_gradient(
        y, x, family, coef, penalty_blocks, lambdas, offset=offset, weights=weights, gamma=gamma
    )
    gradient = gradient_natural * float(np.log(10.0))
    return coef, score, gradient


def projected_gradient(
    gradient: np.ndarray, point: np.ndarray, bounds: tuple[float, float]
) -> np.ndarray:
    """The KKT residual of ``gradient`` at ``point`` under box ``bounds`` —
    PLAN slice 7f (ADR-222).

    For a MINIMISATION under ``lo <= x <= hi``, a component pinned at a bound
    is stationary when the objective can only be *increased* by the one
    feasible direction left to it. So the residual is the raw gradient in the
    interior, and clipped at a bound:

    - interior (``lo < x < hi``):  ``g``
    - at ``lo`` (only ``dx >= 0`` is feasible):  ``min(g, 0)``
    - at ``hi`` (only ``dx <= 0`` is feasible):  ``max(g, 0)``

    **Why this and not the raw norm.** A large raw gradient at a bound-pinned
    component is not evidence of an unconverged search — the bound is holding
    it there legitimately, and reporting ``||g||`` would flag a correct answer
    as a defect. Only the projected residual distinguishes "the optimiser
    stopped early" from "the optimiser stopped at a corner it should stop at".
    On PLAN slice 7f's own fixture the two happen to be nearly equal
    (``3.067232`` against ``3.067233``, because the residual sits on the FREE
    blocks and the two bound-pinned ones contribute ~0) — but that is a fact
    about that fixture, established by measuring, not a licence to use the raw
    norm in general.

    This is the same quantity L-BFGS-B tests internally against its own
    ``pgtol``; recomputing it here is what lets a caller check whether SciPy's
    reported exit actually satisfied the tolerance it was given.

    Args:
        gradient: ``(M,)`` gradient in the SAME units as ``point`` (for
            :func:`select_lambdas_continuous` that is ``log10(lambda)``, not
            natural-log rho).
        point: ``(M,)`` the point the gradient was evaluated at.
        bounds: ``(lo, hi)``, applied to every component.

    Returns:
        ``(M,)`` projected gradient. Its ``max(abs(...))`` is ``0`` exactly at
        a KKT point.

    Raises:
        PolarisValidationError: on a shape mismatch, or ``lo >= hi``.
    """
    gradient = np.asarray(gradient, dtype=np.float64)
    point = np.asarray(point, dtype=np.float64)
    if gradient.shape != point.shape or gradient.ndim != 1:
        raise PolarisValidationError(
            f"projected_gradient: gradient has shape {gradient.shape} and point "
            f"{point.shape}; both must be the same 1-D shape."
        )
    lo, hi = float(bounds[0]), float(bounds[1])
    if lo >= hi:
        raise PolarisValidationError(f"projected_gradient: bounds {bounds} are not lo < hi.")
    # Tolerance, not equality: SciPy returns a bound-pinned component as the
    # bound to within rounding, and a float == comparison would silently treat
    # a pinned component as interior.
    at_lo = point <= lo + _BOUND_ATOL
    at_hi = point >= hi - _BOUND_ATOL
    out = gradient.copy()
    out[at_lo] = np.minimum(gradient[at_lo], 0.0)
    out[at_hi] = np.maximum(gradient[at_hi], 0.0)
    return out


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
    """SciPy's own ``nfev``, summed across the initial search and any restarts
    — how many ``(fit, score)`` evaluations the search cost, the
    continuous-search analogue of ``LambdaSelection``'s ``n_evaluated``.

    **Excludes the restart loop's own residual probes** (PR #228 review
    [P2-2]): when ``max_gtol_restarts > 0``, each iteration also runs one
    :func:`penalized_fit_score_and_gradient` to test the criterion, and those
    are not SciPy evaluations so they are not counted here. Budget it as one
    extra fit per restart plus one, and read this field as "what the optimiser
    spent", not "what the call cost"."""
    n_rejected: int
    """Trial points whose own penalized IRLS did not converge and were
    scored :data:`_REJECTED_SCORE` — mirrors ``LambdaSelection.n_rejected``,
    the grid selector's identical bookkeeping for the identical situation."""
    converged: bool
    """SciPy's own convergence flag (``OptimizeResult.success``), on every
    path. **Read it with :attr:`max_abs_projected_gradient` beside it, not
    alone:** PLAN slice 7f (ADR-222) measured L-BFGS-B reporting ``True`` here
    at a point whose true KKT residual is ``4.9e-01``. This field was
    deliberately NOT redefined to fold in that residual — see ADR-222 and
    :func:`select_lambdas_continuous`'s ``max_gtol_restarts``, which records
    why choosing the threshold that would make it meaningful is a maintainer
    decision rather than this slice's."""
    at_bound: bool
    """Whether any entry of ``log_lambda`` sits on ``bounds`` — the same
    caveat ``select_lambdas_reml``'s callers already read off
    ``lambda_is_at_bound``: a selection at a bound is "at least this",
    since ``mgcv``'s own optimiser is unbounded."""
    message: str
    """SciPy's own human-readable termination message."""
    n_gtol_restarts: int = 0
    """How many times the search was re-entered because SciPy exited with the
    caller's ``gtol`` unmet (PLAN slice 7f). Always ``0`` on the default path
    (``max_gtol_restarts=0``), which is byte-identical to the pre-7f
    behaviour."""
    max_abs_projected_gradient: float | None = None
    """``max |g^P|`` at :attr:`log_lambda` — the KKT residual
    (:func:`projected_gradient`) of the TRUE analytic gradient, the quantity
    :attr:`converged` is tested against when ``max_gtol_restarts > 0``.
    ``None`` when it was never computed (the finite-difference path, or
    ``max_gtol_restarts=0``): a finite-differenced gradient carries its own
    noise floor and testing it against a small ``gtol`` would be testing
    noise — ADR-212's own finding."""


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
    finite_diff_step: float = _FINITE_DIFF_STEP,
    analytic_gradient: bool = False,
    max_gtol_restarts: int = 0,
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
        finite_diff_step: SciPy's forward-difference step for L-BFGS-B's
            internal gradient estimate — used only when ``analytic_gradient``
            is ``False`` (the default). Defaults to :data:`_FINITE_DIFF_STEP`
            — see that constant's docstring for the trade-off (robust on this
            module's own badly-conditioned target structure, less accurate
            than SciPy's own default on an easy, well-conditioned problem).
            Achievable ``gtol`` is bounded below by this value on a noisy
            objective, so a caller both wanting a tighter ``gtol`` AND
            knowing their design has no near-flat block may pass a smaller
            step.
        analytic_gradient: when ``True``, use
            :func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient`
            (PLAN slice 7d) via SciPy's ``jac=True`` combined-objective
            protocol, instead of SciPy's own forward-difference estimate.
            One penalized-IRLS solve per trial point rather than
            ``1 + 2 * len(penalty_blocks)`` (the module docstring's own "8
            nested solves" at ``select=True``'s 7 blocks), and ``gtol``
            becomes a test of the TRUE gradient rather than a
            finite-difference estimate that can sit inside this objective's
            own noise floor (ADR-212's own finding, which motivated
            :data:`_FINITE_DIFF_STEP` in the first place). Default ``False``:
            every existing caller's behaviour is unchanged — this is new,
            opt-in code, not a re-point of the finite-difference path (the
            same discipline :func:`select_lambdas_continuous_multistart`'s
            own ``multistart``/``n_starts`` parameters use for ADR-213).
            ``finite_diff_step`` is ignored when this is ``True``.
        max_gtol_restarts: how many times to re-enter ``minimize`` from the
            point SciPy reported when it exited with ``gtol`` **unmet** on the
            true projected gradient (PLAN slice 7f, ADR-222). Default ``0`` —
            off, and the default path is byte-identical to the pre-7f
            behaviour. **Requires ``analytic_gradient=True``**; ignored
            otherwise, because the test compares a gradient against a small
            ``gtol`` and a finite-differenced gradient's own noise floor sits
            far above it (ADR-212), so the loop would spin on noise. Raises if
            negative.

            **This is a measured PARTIAL mitigation, not a closure, and
            ADR-222 says so.** On slice 7f's own N=7 fixture it takes the score
            from ``524.788031`` to ``523.677681`` and the KKT residual from
            ``2.09`` to ``4.9e-01`` — a real improvement, and still far from
            ``gtol``. The remaining residual is not a stopping-rule problem:
            the inner penalized IRLS stops converging at neighbouring points,
            so the line search runs into :data:`_REJECTED_SCORE` and cannot
            descend a direction the objective genuinely does decrease along.
            :attr:`ContinuousLambdaSelection.max_abs_projected_gradient`
            reports the residual actually reached, and
            :attr:`ContinuousLambdaSelection.converged` is deliberately left as
            SciPy's own flag.

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
    if max_gtol_restarts < 0:
        raise PolarisValidationError(
            f"select_lambdas_continuous: max_gtol_restarts={max_gtol_restarts} is negative. "
            "Use 0 to disable the PLAN slice 7f restart, or a positive budget."
        )
    if max_gtol_restarts > 0 and not analytic_gradient:
        raise PolarisValidationError(
            f"select_lambdas_continuous: max_gtol_restarts={max_gtol_restarts} needs "
            "analytic_gradient=True. The restart tests a gradient against gtol, and a "
            "finite-differenced gradient's own noise floor sits far above any sensible "
            "gtol (ADR-212), so the loop would spin on noise. Raising rather than "
            "silently ignoring the budget: a negative one already raises, and a caller "
            "who sets an inapplicable one deserves the same signal (PR #228 review "
            "[P2-3])."
        )

    tally = {"rejected": 0, "evaluated": 0}
    any_converged = {"flag": False}
    _rejected_gradient = np.zeros(n_blocks, dtype=np.float64)

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

    def objective_and_gradient(log_lambda: np.ndarray) -> tuple[float, np.ndarray]:
        tally["evaluated"] += 1
        try:
            _, score, gradient = penalized_fit_score_and_gradient(
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
            return _REJECTED_SCORE, _rejected_gradient
        if not np.isfinite(score):
            tally["rejected"] += 1
            return _REJECTED_SCORE, _rejected_gradient
        any_converged["flag"] = True
        return score, gradient

    def _run(x_start: np.ndarray) -> OptimizeResult:
        return minimize(
            objective_and_gradient if analytic_gradient else objective,
            x_start,
            method="L-BFGS-B",
            jac=True if analytic_gradient else None,
            bounds=[bounds] * n_blocks,
            options=(
                {"gtol": gtol, "maxiter": maxiter}
                if analytic_gradient
                else {"gtol": gtol, "maxiter": maxiter, "eps": finite_diff_step}
            ),
        )

    result = _run(start)
    total_nfev = int(result.nfev)
    n_gtol_restarts = 0
    max_abs_proj: float | None = None

    # PLAN slice 7f (ADR-222). L-BFGS-B can exit via its own function-reduction
    # rule ("RELATIVE REDUCTION OF F <= FACTR*EPSMCH") with the caller's `gtol`
    # nowhere near met — measured on the select=True 7-block structure at a KKT
    # residual of 2.09 against a gtol of 1e-8. Re-entering `minimize` from the
    # reported point resets the limited-memory Hessian approximation and the
    # line-search state, which is what lets it make progress again.
    #
    # Gated on `analytic_gradient` deliberately: the test compares a gradient
    # against a small `gtol`, and a finite-differenced gradient carries its own
    # noise floor well above it (ADR-212), so on that path the loop would spin
    # on noise rather than on a real residual.
    #
    # TWO stopping conditions, and the second is what keeps this from burning
    # the budget on an already-good answer: the residual test (`gtol` met), and
    # a strict-improvement test. ADR-222 measured `gtol = 1e-8` to be BELOW this
    # objective's own computability floor — the inner penalized IRLS stops
    # converging at neighbouring points well before a KKT residual that small is
    # reachable — so the residual test alone would essentially never fire and
    # every run would spend its whole budget. Stopping as soon as a restart
    # stops strictly improving the score needs no tolerance of its own.
    if max_gtol_restarts > 0 and analytic_gradient:

        def _residual_at(pt: np.ndarray) -> tuple[float, float] | None:
            """``(score, max|g^P|)`` at ``pt``, or ``None`` if unevaluable."""
            try:
                _, sc, grad = penalized_fit_score_and_gradient(
                    y,
                    x,
                    family,
                    penalty_blocks,
                    pt,
                    offset=offset,
                    weights=weights,
                    gamma=gamma,
                )
            except PolarisComputationError:
                return None
            return sc, float(np.max(np.abs(projected_gradient(grad, pt, bounds))))

        # Carries the previous iteration's own measurement forward, so an
        # improving restart does not pay for `_residual_at` twice at the same
        # point (PR #228 review [P2-2]). Each such call is a full IRLS fit plus
        # a gradient, and none are counted in `n_function_evals` — see that
        # field's docstring.
        measured: tuple[float, float] | None = None
        while True:
            point = np.asarray(result.x, dtype=np.float64)
            if measured is None:
                measured = _residual_at(point)
            if measured is None:
                # Cannot test the criterion here. Keep the point we have, and
                # leave the residual unreported rather than publishing one that
                # was never measured.
                max_abs_proj = None
                break
            score_here, max_abs_proj = measured
            if max_abs_proj <= gtol or n_gtol_restarts >= max_gtol_restarts:
                break
            restarted = _run(point)
            total_nfev += int(restarted.nfev)
            n_gtol_restarts += 1
            new_point = np.asarray(restarted.x, dtype=np.float64)
            new_measured = _residual_at(new_point)
            measured = new_measured
            if new_measured is None or not new_measured[0] < score_here:
                # No strict improvement — L-BFGS-B has nothing further to
                # extract from this point, so the remaining budget would only
                # repeat this. Keep the BETTER of the two, which is the one we
                # already had.
                break
            result = restarted

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
        n_function_evals=total_nfev,
        n_rejected=tally["rejected"],
        # Deliberately still SciPy's own flag, on every path. ADR-222 measured
        # that redefining it as "gtol met on the true projected gradient" would
        # report a perfectly good fit as unconverged: on the well-conditioned
        # N=4 control the restarted search reaches a residual of 2.0e-04 — three
        # orders better than the N=7 case's 4.9e-01, and still four orders
        # above `gtol = 1e-8`, because that gtol is below what this objective
        # can resolve at all. Picking some threshold in between to make both
        # cases read "converged" would be tuning a number to make a check pass.
        # So the flag keeps its existing meaning and
        # `max_abs_projected_gradient` carries the measurement; what the flag
        # SHOULD test is a maintainer decision ADR-222 registers, not one this
        # slice takes.
        converged=bool(result.success),
        at_bound=bool(np.any(np.isclose(log_lambda, lo)) or np.any(np.isclose(log_lambda, hi))),
        message=str(result.message),
        n_gtol_restarts=n_gtol_restarts,
        max_abs_projected_gradient=max_abs_proj,
    )


_MULTISTART_SEED = 20260830
"""Pinned per ADR-074 (never the wall clock), not tuned against any ``mgcv``
reading — the starting points below are read off this seed alone, before any
fit runs. Fixed so a re-run of :func:`select_lambdas_continuous_multistart`
on identical ``(y, x, penalty_blocks)`` draws the identical set of starts
regardless of platform or `NumPy` version: `numpy.random.default_rng`'s
PCG64 stream is a pure integer/bit algorithm, independent of BLAS, OpenMP or
thread count — the axis PLAN slice 5e/ADR-211 found the SEARCH itself
sensitive to. Only the *starting points* are pinned this way; each start's
own converged score can still move with thread count, for the identical
reason a single-start search does (ADR-211) — multi-start does not remove
that per-fit noise, it gives the search several independent attempts to
escape whichever near-flat direction the noise happens to stall on."""


@dataclass(frozen=True)
class MultiStartLambdaSelection:
    """What :func:`select_lambdas_continuous_multistart` returns — the
    best-scoring converged result of ``n_starts`` independent
    :func:`select_lambdas_continuous` calls, plus enough bookkeeping to state
    the search's own cost and how much the starts actually disagreed."""

    best: ContinuousLambdaSelection
    """The lowest-score CONVERGED run (or, if none converged, the
    lowest-score run overall — see :attr:`any_converged`)."""
    starts: tuple[np.ndarray, ...]
    """Every ``x0`` tried, in the order evaluated. ``starts[0]`` is always
    the bounds-centre — the same point :func:`select_lambdas_continuous`
    itself defaults to — so a caller can read index 0 as "what the
    single-start search alone would have returned"."""
    scores: tuple[float, ...]
    """Each start's own converged (or best-effort) REML score, same order as
    :attr:`starts` — ``_REJECTED_SCORE`` for a start whose own search
    rejected every trial point it tried."""
    converged: tuple[bool, ...]
    """Each start's own :attr:`ContinuousLambdaSelection.converged`, same
    order as :attr:`starts`."""
    best_start_index: int
    """Index into :attr:`starts`/:attr:`scores` of the run :attr:`best` came
    from."""
    any_converged: bool
    """Whether at least one start converged. ``False`` means :attr:`best` is
    the least-bad non-converged run, reported rather than raised — mirrors
    :func:`select_lambdas_continuous`'s own per-start rejection handling,
    but at the level of whole runs instead of trial points."""
    total_function_evals: int
    """Sum of every start's own ``n_function_evals`` — the search's real
    cost: ``n_starts`` times a single search's own evaluation count, give or
    take each start's own path length."""


def select_lambdas_continuous_multistart(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
    bounds: tuple[float, float] = DEFAULT_LOG10_BOUNDS,
    gtol: float = 1.0e-8,
    maxiter: int = 200,
    finite_diff_step: float = _FINITE_DIFF_STEP,
    n_starts: int = 9,
    seed: int = _MULTISTART_SEED,
    analytic_gradient: bool = False,
    max_gtol_restarts: int = 0,
) -> MultiStartLambdaSelection:
    """Best-of-``n_starts`` :func:`select_lambdas_continuous`, candidate (1)
    of PLAN slice 5e (``docs/PLAN_mgcv_parity_engine.md``).

    ADR-211's own blind multi-start check (9 starts: bounds-centre plus 8
    uniform-random draws) found the single bounds-centre start alone can
    land measurably short of a reachable, better-scoring point on a
    near-flat, weakly-identified block — this function is that check turned
    into a reusable, deterministic building block rather than a one-off
    diagnostic script. It adds no new fitting or scoring formula: every
    start is an ordinary :func:`select_lambdas_continuous` call, and this
    function only picks the best of their results.

    The first start is always the bounds-centre (matching
    :func:`select_lambdas_continuous`'s own default ``x0``); the remaining
    ``n_starts - 1`` are drawn uniformly from ``bounds`` by
    ``numpy.random.default_rng(seed)`` — deterministic across platforms
    regardless of BLAS thread count (see :data:`_MULTISTART_SEED`).

    A start whose own search raises :class:`~polaris_re.core.exceptions.PolarisComputationError`
    (every trial point it tried was rejected) is recorded with score
    :data:`_REJECTED_SCORE` and ``converged=False`` rather than aborting the
    whole multi-start run — one bad start should not hide the other starts'
    results, the same reasoning a single search's own per-trial-point
    rejection already uses.

    Args:
        y, x, family, penalty_blocks, offset, weights, gamma, bounds, gtol,
            maxiter, finite_diff_step: passed to every
            :func:`select_lambdas_continuous` call unchanged.
        n_starts: total number of starts, bounds-centre included. ADR-211's
            own diagnostic used 9; kept as the default here since it is the
            one value this module has actual evidence about, not because 9
            is derived from anything.
        seed: seeds the ``n_starts - 1`` random starts. Change only to
            explore a different draw — the default is pinned, not tuned.
        analytic_gradient: passed through to every
            :func:`select_lambdas_continuous` call unchanged (PLAN slice 7d).
            Default ``False`` — existing callers are unaffected.
        max_gtol_restarts: passed through to every
            :func:`select_lambdas_continuous` call unchanged (PLAN slice 7f).
            Default ``0`` — existing callers are unaffected. Applies per
            start, so each start independently gets up to this many restarts.

    Returns:
        :class:`MultiStartLambdaSelection`.

    Raises:
        PolarisValidationError: if ``penalty_blocks`` is empty, or
            ``n_starts < 1``.
    """
    n_blocks = len(penalty_blocks)
    if n_blocks == 0:
        raise PolarisValidationError(
            "select_lambdas_continuous_multistart needs at least one penalty block."
        )
    if n_starts < 1:
        raise PolarisValidationError(
            f"select_lambdas_continuous_multistart needs n_starts >= 1; got {n_starts}."
        )
    lo, hi = bounds
    centre = np.full(n_blocks, (lo + hi) / 2.0, dtype=np.float64)
    rng = np.random.default_rng(seed)
    starts = [centre] + [
        rng.uniform(lo, hi, size=n_blocks).astype(np.float64) for _ in range(n_starts - 1)
    ]

    runs: list[ContinuousLambdaSelection | None] = []
    for start in starts:
        try:
            runs.append(
                select_lambdas_continuous(
                    y,
                    x,
                    family,
                    penalty_blocks,
                    offset=offset,
                    weights=weights,
                    gamma=gamma,
                    x0=start,
                    bounds=bounds,
                    gtol=gtol,
                    maxiter=maxiter,
                    finite_diff_step=finite_diff_step,
                    analytic_gradient=analytic_gradient,
                    max_gtol_restarts=max_gtol_restarts,
                )
            )
        except PolarisComputationError:
            runs.append(None)

    scores = tuple(_REJECTED_SCORE if run is None else run.reml_score for run in runs)
    converged = tuple(False if run is None else run.converged for run in runs)
    total_evals = sum(0 if run is None else run.n_function_evals for run in runs)

    converged_indices = [i for i, ok in enumerate(converged) if ok]
    any_conv = bool(converged_indices)
    candidate_indices = converged_indices if any_conv else list(range(len(runs)))
    best_idx = min(candidate_indices, key=lambda i: scores[i])
    best_run = runs[best_idx]
    if best_run is None:
        raise PolarisComputationError(
            f"select_lambdas_continuous_multistart: every one of {n_starts} starts "
            f"raised PolarisComputationError (its own search rejected every trial "
            f"point it tried) — no penalized fit converged anywhere in log10 lambda "
            f"{bounds}."
        )

    return MultiStartLambdaSelection(
        best=best_run,
        starts=tuple(starts),
        scores=scores,
        converged=converged,
        best_start_index=best_idx,
        any_converged=any_conv,
        total_function_evals=total_evals,
    )

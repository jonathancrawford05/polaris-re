"""Measuring a smoothing-parameter disagreement in units the criterion can
actually resolve -- mgcv-parity engine, PLAN slice 7c Part 2 (ADR-219).

**Why this module exists.** ``SELECT_FREE_SP_MODEL_CLAIM`` and
``FREE_SP_MODEL_CLAIM`` both gate on ``max |Δ log10(sp)|``, which implicitly
assumes every smoothing-parameter direction is equally well determined. PLAN
slice 7c Part 0 measured that assumption directly on the ``select = TRUE``
7-block structure and found it false: two of the seven blocks carry REML
curvature indistinguishable from zero (moving one of them a full DECADE costs
under ``2e-3`` of score, against ``~1.0`` for half a decade on an identified
block). On such a direction ``max |Δ log10(sp)|`` measures the optimiser's
arbitrary stopping place, not a modelling disagreement.

This module provides the alternative this epic can compute from quantities it
already has, and it is **reported, never gated** by anything in this module
itself: nothing here edits ``SELECT_FREE_SP_MODEL_CLAIM``'s or
``FREE_SP_MODEL_CLAIM``'s own acceptance criterion. Choosing to re-gate on it
is a maintainer decision (``docs/ROUTINE_MGCV_PARITY.md``, "May not decide" --
"whether to relax an acceptance criterion"), which ADR-219 records as
recommended-and-not-taken.

**Provenance (ADR-193) -- corrected, PLAN slice 7e / ADR-221 amendment 3.**
The TWO functions here have DIFFERENT provenance, and an earlier revision of
this module's own docstring conflated them:

- :func:`identified_direction_count` reads the curvature of OUR OWN criterion
  at a SINGLE point. Remove the reference entirely and the eigenvalues are
  unchanged -- the point of evaluation is an argument, not an operand. This
  one is genuinely ``MEASUREMENT (own criterion)``
  (``docs/VERIFICATION_STANDARD.md`` §2.1) and carries no
  ``VerificationClaim``.
- :func:`hessian_weighted_distance` is a norm on ``delta_rho``, and
  ``delta_rho`` is a DISPLACEMENT BETWEEN TWO INDEPENDENTLY-PRODUCED POINTS
  (our own selected ``rho`` and ``mgcv``'s own selected ``rho``). Remove the
  reference and there is no displacement, hence no number -- by
  §2.1's own mechanical test ("remove the reference entirely, is there still
  a number?") this is a COMPARISON, not a bare measurement, and its
  provenance is **INDEPENDENT**: both operands are independently produced,
  from the same recipe (each side's own free-``sp`` REML selection). ADR-219
  said so in prose ("the H-weighted column is labelled INDEPENDENT
  correctly, but only in prose") and named the one caveat that qualifies
  it, not its category: the WEIGHTING Hessian must be evaluated at OUR OWN
  selected point, never at ``mgcv``'s -- weighting at ``mgcv``'s point lets
  its payload re-enter the metric a second time, through the norm, even
  though it is absent from both operands (a real seam, closed by using our
  own point). A caller wiring this into a declared ``ComparedQuantity`` MUST
  supply a Hessian built at ITS OWN selected point to keep that guarantee;
  this module has no way to enforce it and does not try to.
"""

from collections.abc import Callable

import numpy as np

from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "derive_floor_from_step_stability",
    "hessian_weighted_distance",
    "identified_direction_count",
]

_DEFAULT_STEP_SCAN = (0.2, 0.1, 0.05, 0.025)
"""Spans a factor of 8, enough to separate a stable curvature from a
``1/h^2`` noise signature (PLAN slice 7c Part 0). **In whatever units
``point``/``score_at`` use.** This epic's own convention sizes a step scan
in natural-log-rho units (matching
``gam_uncertainty_conformance.finite_difference_rho_hessian``'s own
Hessian); a caller whose ``score_at`` takes ``log10(lambda)`` instead
converts EVERY step by dividing by ``ln(10)`` before passing ``steps`` in
-- the same conversion it must already apply to build ``point`` and
``hessian`` in consistent units. This module does not perform that
conversion itself, so a caller passing raw natural-log-rho steps alongside
a ``log10(lambda)``-valued ``score_at`` will silently scan the wrong
distances; the diagnostic script and the production comparator both
convert before calling, and a new caller must do the same."""


def derive_floor_from_step_stability(
    score_at: Callable[[np.ndarray], float],
    base_score: float,
    point: np.ndarray,
    hessian: np.ndarray,
    *,
    steps: tuple[float, ...] = _DEFAULT_STEP_SCAN,
    unstable_ratio: float = 4.0,
) -> float:
    """Derive :func:`hessian_weighted_distance`'s ``floor`` from the
    criterion's OWN measured noise, rather than choosing a constant
    (Anchor 8).

    For each direction ``j``, the diagonal second difference
    ``(score(point + h*e_j) - 2*score(point) + score(point - h*e_j)) / h^2``
    is computed at each ``h`` in ``steps``. A REAL curvature is stable as
    ``h`` shrinks; a value driven by a fixed absolute noise floor grows like
    ``1/h^2`` (PLAN slice 7c / ADR-219's own discriminator, the same
    discipline ADR-212 used to find a finite-difference-step defect
    elsewhere in this epic). ``unstable_ratio`` is a deliberately generous
    cut: the coarsest-to-finest ratio expected from noise alone is ``~64x``
    over this module's own default 8x step range; flagging anything above
    4x is conservative in the "call it flat" direction.

    Args:
        score_at: the criterion, as a function of ``point``'s own units
            (e.g. ``log10(lambda)``).
        base_score: ``score_at(point)``, passed in rather than recomputed.
        point: the ``(M,)`` point to scan around, in ``score_at``'s units.
        hessian: the ``(M, M)`` Hessian already computed at ``point``, in
            the SAME units ``steps`` is given in (this epic's own
            convention: natural-log-rho) -- used only to size the
            flat-direction count against; not recomputed here.
        steps: the step sizes to scan, in ``point``'s own units, coarsest
            first -- see :data:`_DEFAULT_STEP_SCAN` for the unit-conversion
            responsibility this places on the caller.
        unstable_ratio: a direction is FLAT if its finest-step reading
            exceeds ``unstable_ratio`` times its coarsest-step reading (or
            ``1e-12``, whichever is larger, to avoid a division artefact
            near an exact zero).

    Returns:
        The floor: the smallest RESOLVED eigenvalue of ``hessian`` (0.0 if
        every direction is flat), i.e. exactly as many of the smallest
        eigenvalues are clipped as the step-stability scan found flat --
        never a chosen constant.
    """
    n = point.shape[0]
    flat_count = 0
    for j in range(n):
        row = []
        for h in steps:
            up, dn = point.copy(), point.copy()
            up[j] += h
            dn[j] -= h
            row.append((score_at(up) - 2.0 * base_score + score_at(dn)) / (h * h))
        coarse, fine = abs(row[0]), abs(row[-1])
        if fine > unstable_ratio * max(coarse, 1e-12):
            flat_count += 1
    if flat_count == 0:
        return 0.0
    sorted_evals = np.sort(np.linalg.eigvalsh(np.asarray(hessian, dtype=np.float64)))
    return float(sorted_evals[flat_count])


def _psd_part(hessian: np.ndarray, floor: float) -> tuple[np.ndarray, np.ndarray]:
    """Eigendecompose ``hessian`` and clip eigenvalues below ``floor`` to zero.

    A finite-difference Hessian on a criterion with a noise floor returns
    small NEGATIVE eigenvalues along genuinely flat directions (PLAN slice 7c
    Part 0 measured exactly two, at ``-8.7e-3`` and ``-3.5e-3``, on directions
    whose second difference grows like ``1/h^2`` -- the signature of noise, not
    of a saddle). Clipping is therefore the physically correct reading of a
    flat direction, not a numerical convenience: a direction the criterion
    does not resolve should contribute nothing to a distance measured in units
    of what the criterion resolves.
    """
    if hessian.ndim != 2 or hessian.shape[0] != hessian.shape[1]:
        raise PolarisValidationError(
            f"gam_sp_identifiability: hessian must be square, got shape {hessian.shape}."
        )
    if not np.allclose(hessian, hessian.T, rtol=0.0, atol=1e-8):
        raise PolarisValidationError(
            "gam_sp_identifiability: hessian must be symmetric — a REML score's "
            "own second-derivative matrix is, and an asymmetric one signals the "
            "caller assembled it wrongly."
        )
    evals, evecs = np.linalg.eigh(np.asarray(hessian, dtype=np.float64))
    return np.where(evals < floor, 0.0, evals), evecs


def hessian_weighted_distance(
    delta_rho: np.ndarray,
    hessian: np.ndarray,
    *,
    floor: float,
) -> float:
    """``sqrt(Δᵀ H₊ Δ)`` — a displacement in ``rho`` measured in the units the
    REML criterion actually resolves.

    Twice this quantity squared is the second-order change in the REML score
    the displacement causes, so it answers "how far apart are these two
    selections, in score?" rather than "how far apart are the raw logs?". On a
    direction the criterion cannot resolve it contributes ~0, which is the
    point: two selections that differ by decades along a flat direction ARE the
    same selection as far as the fitted model is concerned, and slice 7b's
    ``eta``/``edf`` agreement (``0.0027``/``0.11``) is what that looks like from
    the other side.

    Args:
        delta_rho: ``(M,)`` displacement in NATURAL-log lambda. Note the units
            — :func:`finite_difference_rho_hessian`
            (:mod:`~polaris_re.analytics.gam_uncertainty_conformance`)
            works in natural log, while the conformance modules report
            ``log10``; multiply a ``log10`` difference by ``ln(10)`` first.
        hessian: ``(M, M)`` symmetric REML Hessian w.r.t. natural-log lambda,
            evaluated at one of the two points.
        floor: eigenvalues strictly below this are clipped to zero. **Required,
            for the same reason it is required on
            :func:`identified_direction_count` — an earlier revision defaulted
            it to ``0.0`` and that default is a trap.** Clipping only the
            NEGATIVES is asymmetric: noise that lands negative is discarded
            while noise that lands positive is kept and contributes. Measured
            across four readings of the slice 7c fixture (ADR-219 amendment 4),
            with the selection identical in three of them:

            ==========  ==========================  ============  ==============
            reading     two noise eigenvalues       ``floor=0``   ``floor=0.1``
            ==========  ==========================  ============  ==============
            tier 1      ``-0.008687``, ``-0.003479``  0.0976        0.0973
            t3 run 1    ``+0.005624``, ``+0.012057``  **0.4625**    0.0973
            t3 run 2    ``-0.003605``, ``+0.001244``  **0.1546**    0.0973
            t3 run 3    ``-0.004976``, ``-0.002473``  0.0976        0.0973
            ==========  ==========================  ============  ==============

            At ``floor=0`` the metric moves 4.7x on nothing but the sign of
            noise; above the noise floor it is identical everywhere. Derive the
            value from the criterion's own measured noise floor (Anchor 8) —
            never from what makes a number look good.

    Returns:
        The non-negative distance. ``0.0`` exactly when ``delta_rho`` lies
        entirely in the clipped (unresolved) subspace.

    Raises:
        PolarisValidationError: if ``hessian`` is not square and symmetric, or
            its size does not match ``delta_rho``.
    """
    delta_rho = np.asarray(delta_rho, dtype=np.float64)
    evals, evecs = _psd_part(np.asarray(hessian, dtype=np.float64), floor)
    if delta_rho.ndim != 1 or delta_rho.shape[0] != evals.shape[0]:
        raise PolarisValidationError(
            f"gam_sp_identifiability: delta_rho has shape {delta_rho.shape}, "
            f"expected ({evals.shape[0]},) to match the hessian."
        )
    projected = evecs.T @ delta_rho
    return float(np.sqrt(max(float(np.sum(evals * projected**2)), 0.0)))


def identified_direction_count(hessian: np.ndarray, *, floor: float) -> int:
    """How many of ``hessian``'s directions carry curvature above ``floor``.

    **``floor`` is REQUIRED, and that is a correctness guard, not pedantry.**
    An earlier revision defaulted it to ``0.0``, which counts eigenvalues by
    SIGN — and on a criterion with a noise floor the sign of an unresolved
    direction is not a property of the model at all. Measured, on the *same*
    slice 7c fixture (ADR-219 amendment 2):

    ===========================  ==========================  =============
    tier                         two smallest eigenvalues    count at 0.0
    ===========================  ==========================  =============
    1 (R 4.3.3 / mgcv 1.9-1)     ``-0.008687``, ``-0.003479``  **5 of 7**
    3 (R 4.6.1 / mgcv 1.9.4)     ``+0.005624``, ``+0.012057``  **7 of 7**
    ===========================  ==========================  =============

    Same fixture, same `mgcv` selection to four decimal places, same profile to
    three — and a headline that moves from 5 to 7 purely on which side of zero
    the noise landed. Requiring an explicit ``floor`` makes that mistake
    impossible to make by accident.

    **This is the secondary reading, never the headline.** The robust
    discriminator is the step-stability scan in
    ``scripts/gam_select_free_sp_identifiability_diagnostic.py``: a real
    curvature holds steady as the finite-difference step shrinks, while a noise
    floor divided by ``h^2`` grows. That scan called `b1`/`b3` FLAT at BOTH
    tiers, which is the finding — the eigenvalue count did not survive
    re-measurement and must not be quoted as though it had.

    Args:
        hessian: ``(M, M)`` symmetric REML Hessian w.r.t. natural-log lambda.
        floor: curvature at or below which a direction counts as unresolved.
            There is no universally right value — derive it from the criterion's
            own measured noise floor for the case at hand (Anchor 8), never from
            what makes a number look good.
    """
    evals, _ = _psd_part(np.asarray(hessian, dtype=np.float64), floor)
    return int(np.count_nonzero(evals > 0.0))

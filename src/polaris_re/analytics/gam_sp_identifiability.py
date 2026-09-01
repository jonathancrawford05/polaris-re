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
already has, and it is **reported, never gated**: nothing here edits
``SELECT_FREE_SP_MODEL_CLAIM``'s or ``FREE_SP_MODEL_CLAIM``'s own acceptance
criterion. Choosing to re-gate on it is a maintainer decision
(``docs/ROUTINE_MGCV_PARITY.md``, "May not decide" -- "whether to relax an
acceptance criterion"), which ADR-219 records as recommended-and-not-taken.

**Provenance (ADR-193).** Nothing here is a comparison between two producers.
:func:`hessian_weighted_distance` is a norm on a displacement, and the
Hessian it weights by is our OWN criterion's curvature. It carries no
``VerificationClaim`` because there is no second producer to name -- see
``scripts/gam_select_free_sp_identifiability_diagnostic.py``'s own docstring.
"""

import numpy as np

from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "hessian_weighted_distance",
    "identified_direction_count",
]


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
    floor: float = 0.0,
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
        floor: eigenvalues strictly below this are clipped to zero. Default
            ``0.0`` — clip only the negatives a noise floor produces. Pass a
            small positive value to also discard directions that are
            technically positive but below the criterion's own resolution.

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


def identified_direction_count(hessian: np.ndarray, *, floor: float = 0.0) -> int:
    """How many of ``hessian``'s directions the criterion actually resolves.

    The companion reading to :func:`hessian_weighted_distance`: a gate on raw
    ``log10(sp)`` is only meaningful when this equals the block count. On the
    slice 7c fixture it is 5 of 7 (ADR-219).
    """
    evals, _ = _psd_part(np.asarray(hessian, dtype=np.float64), floor)
    return int(np.count_nonzero(evals > 0.0))

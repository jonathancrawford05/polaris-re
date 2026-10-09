"""Rank pivoting for structurally rank-deficient GAM designs (parity-engine Slice 9).

A smooth ``s(x)`` and a factor-``by`` smooth ``s(x, by=f)`` of the same covariate
share their linear null space: the sum over levels of the per-level linear terms equals
the main-effect linear term, and no penalty or datum identifies the split. The design
then has a direction ``v`` with ``S_lambda v = 0`` for every ``lambda`` and ``X v = 0``
(``rank(X) < p``, ADR-250). ``mgcv`` pivots the unidentified coefficient out of its
criterion, its edf and ``Vp``; before this module this engine inverted
``X'WX + S_lambda`` and took ``log|X'WX + S_lambda|`` through that direction.

**The construction.** Find the orthonormal directions ``V`` (``p x r``) with ``S V = 0``
and ``X V = 0``; choose ``r`` coefficients ``D`` such that ``V[D, :]`` is invertible
(column-pivoted QR of ``V'``); fit on the remaining columns ``X[:, kept]`` and
``S_j[kept, kept]``.

**Why that is the same model.** Any ``beta`` can be moved along ``V`` until
``beta[D] = 0`` (``V[D, :]`` invertible), and the move changes neither ``X beta``
(``X V = 0``) nor ``beta' S_j beta`` (``S_j V = 0`` — ``V`` is in the null space of the
SUM of the normalised penalties, which are positive semi-definite, hence of each).
So the fitted function space, ``eta``, the penalty values and ``log|S|_+`` are
unchanged; only ``log|X'WX + S_lambda|`` becomes the determinant on the identified
subspace, which is what ``mgcv`` uses. ``eta``, ``edf_total`` and the ``Vp``-based
``se`` are pivot-invariant (measured: dropping each of eight different columns moved
``Vp`` se by < 1e-4 between choices); per-term edf is reported but depends on the
column dropped. The unconditional ``Vc`` is NOT pivot-invariant (eq. (7)'s ``V''``
term depends on the square root of ``V_beta``), so it is refused for a pivoted fit.
mgcv's own ``Vp`` has no zero row for the redundant coefficient; the zero row in
``vcov()`` is this engine's convention.

**Scope.** Structural rank loss only — a function of ``X`` and the penalties, never of
the weights. A weight-dependent loss (zero prior weights) is not handled here and still
trips the covariance guard in :mod:`~polaris_re.analytics.gam_vcov`.

**Threshold.** The cut ``1e-10`` (relative to the largest singular value / eigenvalue)
is the one ADR-251 uses for the refusal this module replaces: deficient designs read
~1e-15 and identified ones >= 1e-3, so the cut sits in a gap of twelve orders and is
not tuned against any ``mgcv`` output.
"""

from collections.abc import Sequence

import numpy as np
from scipy.linalg import qr as scipy_qr

from polaris_re.core.exceptions import PolarisComputationError

__all__ = [
    "RANK_TOLERANCE",
    "choose_pivot_columns",
    "pivot_out",
    "unidentified_directions",
]

RANK_TOLERANCE = 1.0e-10
"""Relative singular-value / eigenvalue cut (see module docstring)."""


def unidentified_directions(x: np.ndarray, penalty_blocks: Sequence[np.ndarray]) -> np.ndarray:
    """Orthonormal ``(p, r)`` basis of ``{v : S_j v = 0 for all j, X v = 0}``.

    ``r = 0`` (a ``(p, 0)`` array) for an identified design. Depends on ``X`` and the
    penalty structure only — not on ``y``, the weights or the smoothing parameters.
    """
    p = x.shape[1]
    s_total = np.zeros((p, p), dtype=np.float64)
    for block in penalty_blocks:
        s_total += block / max(float(np.linalg.norm(block, ord=2)), 1.0e-300)
    eigvals, eigvecs = np.linalg.eigh((s_total + s_total.T) / 2.0)
    scale = max(float(eigvals[-1]), 1.0e-300)
    null_basis = eigvecs[:, eigvals <= RANK_TOLERANCE * scale]
    q = null_basis.shape[1]
    if q == 0:
        return np.zeros((p, 0), dtype=np.float64)
    # X N = Q R: the SVD of the small q-column triangle R has the singular values of X N
    # without squaring its condition number (X'X would put a deficient direction at the
    # eps floor, where no relative cut can separate it).
    r_factor = np.linalg.qr(x @ null_basis, mode="r")
    _, sv, vt = np.linalg.svd(r_factor, full_matrices=True)
    sv_max = max(float(sv[0]) if sv.size else 0.0, 1.0e-300)
    rank = int(np.count_nonzero(sv > RANK_TOLERANCE * sv_max))
    return np.asarray(null_basis @ vt[rank:].T, dtype=np.float64)


def choose_pivot_columns(directions: np.ndarray) -> tuple[int, ...]:
    """The ``r`` coefficient indices to eliminate: column-pivoted QR of ``V'``
    selects ``r`` rows of ``V`` that are as well conditioned as a greedy rule can
    make them, so ``V[D, :]`` is invertible. Returned sorted."""
    r = directions.shape[1]
    if r == 0:
        return ()
    _, _, piv = scipy_qr(directions.T, mode="economic", pivoting=True)
    return tuple(sorted(int(i) for i in piv[:r]))


def pivot_out(
    x: np.ndarray, penalty_blocks: Sequence[np.ndarray]
) -> tuple[np.ndarray, tuple[np.ndarray, ...], tuple[int, ...]]:
    """Eliminate the unidentified coefficients.

    Returns ``(x_kept, penalty_blocks_kept, kept)`` where ``kept`` are the retained
    column indices (all of them when the design is identified, in which case the inputs
    are returned unchanged).

    Raises:
        PolarisComputationError: if the reduced design is still rank deficient — the
            selected rows did not span the null directions, which would mean the
            construction's invariant failed.
    """
    p = x.shape[1]
    v = unidentified_directions(x, penalty_blocks)
    if v.shape[1] == 0:
        return x, tuple(penalty_blocks), tuple(range(p))
    dropped = set(choose_pivot_columns(v))
    kept = tuple(j for j in range(p) if j not in dropped)
    idx = np.asarray(kept, dtype=np.intp)
    x_kept = np.ascontiguousarray(x[:, idx])
    blocks_kept = tuple(np.ascontiguousarray(b[np.ix_(idx, idx)]) for b in penalty_blocks)
    remaining = unidentified_directions(x_kept, blocks_kept).shape[1]
    if remaining:
        raise PolarisComputationError(
            f"pivot_out: {remaining} unidentified direction(s) remain after eliminating "
            f"columns {sorted(dropped)}; the pivot selection did not span the null space."
        )
    return x_kept, blocks_kept, kept

"""Wood's thin-plate regression spline basis, one covariate (``bs="tp"``) — R4 / ladder L7.

``docs/PLAN_gam_real_data_readiness.md`` Slice R4, ADR-261. ``mgcv``'s default smooth:
a bare ``s(x)`` is ``bs="tp"``, ``k = 10`` (``M + 8`` with the null-space dimension
``M = 2``).

**Parity claim (ADR-193, written before the code):** this module computes the
thin-plate regression spline ``design_X`` and ``penalty_S`` from the covariate and
``k`` alone (the eigen-truncation recipe below); ``mgcv`` computes them via
``smoothCon(s(x, bs="tp", k=k), absorb.cons=TRUE)`` (its ``construct_tprs`` C routine);
compared on the **column space of the design** and on **the penalty in a common basis**
(:func:`compare_tp_basis`), not element-wise — see "The gauge" below.

The recipe, pinned by reading ``mgcv:::smooth.construct.tp.smooth.spec`` and then
measuring ``smoothCon`` output against it (tier 1, ADR-261 amendment log — hypotheses
that the tier-3 probe re-measures), not guessed:

1. ``shift = mean(x)``; work with ``x - shift``. The distinct shifted values ``xu``
   (``nu`` of them) carry the basis; the data rows only evaluate it.
2. ``E[i, j] = c · |xu_i - xu_j|³`` with ``c = Γ(-3/2) / (2⁴ √π) = 1/12`` (the
   ``m = 2``, ``d = 1`` thin-plate kernel, ``η(r) ∝ r^(2m-d)``). The null space is
   ``T = [1, xu]`` (``M = 2``).
3. **Truncate first, constrain second** (Wood 2003, §2.2; the name ``UZ`` is "U times Z"):
   eigendecompose the full ``E``, keep the ``k`` eigenpairs of largest ``|λ|``, then
   impose ``Tᵀδ = 0`` on ``δ = U_k δ_k`` by ``Z`` = the null space of ``T'U_k`` (full
   Householder QR of its transpose). The range basis is ``U_k Z`` and its penalty is
   ``Zᵀ diag(λ_k) Z`` (NOT diagonal). Truncating ``Z'EZ`` instead gives a different
   subspace (measured sine of the principal angle 0.10-0.17, not rounding).
4. Every column of the design ``[E(x, xu), T(x)] · UZ`` is rescaled to Euclidean norm
   ``√n`` (``n`` = number of data rows, not ``nu``), the penalty by the same factors.
5. ``smoothCon``'s ``scale.penalty`` (the same rescaling as :func:`cr_basis`), then the
   sum-to-zero identifiability constraint (:func:`absorb_sum_to_zero_constraint`).

The gauge. The range-space coordinates are determined only up to an invertible ``(k-2)²``
matrix: the sign and the order of the eigenvectors come out of ``mgcv``'s Lanczos routine
and of LAPACK differently, and the null space ``Z`` of ``T'U_k`` depends on both. Any
two such parameterisations give the same penalised fit (``η``, ``edf``, REML score), so
they are one model, but their ``X`` and ``S`` do not agree element by element. The
comparison is therefore gauge-invariant: the sine of the largest principal angle
between the two column spaces, and ``S`` in the basis that maps one design to the other.
``mgcv``'s truncated eigenvectors are themselves a Lanczos result, accurate to about
``1e-8`` on some cases (measured); the tolerance is derived from that, not chosen
(:func:`derived_tolerance`).

**Refused, by name:** ``mgcv`` randomly subsamples ``max.knots = 2000`` of the distinct
covariate values when there are more than 2000 data rows *and* more than 2000 distinct
values (``temp.seed(1)`` and ``sample()``); that stream is not ported, so
:func:`tp_basis` raises rather than return a different basis.
"""

from dataclasses import dataclass
from math import gamma, pi, sqrt

import numpy as np

from polaris_re.analytics.gam_basis_cr import _r_norm_inf, _r_norm_one
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "TP_BASIS_CLAIM",
    "TP_MAX_KNOTS",
    "TP_NULL_DIM",
    "TpBasisComparison",
    "TprsState",
    "compare_tp_basis",
    "derived_tolerance",
    "eigenspace_rounding_bound",
    "subspace_distance",
    "tp_basis",
    "tp_predict",
]

TP_NULL_DIM = 2
"""Null-space dimension ``M`` of the default ``m = 2``, ``d = 1`` thin-plate penalty
(constants and linear functions are unpenalised)."""

TP_MAX_KNOTS = 2000
"""``mgcv``'s ``max.knots`` default: above it (rows AND distinct values) it subsamples."""

_ETA_CONST = gamma(-1.5) / (2.0**4 * sqrt(pi))
"""``Γ(d/2 - m) / (2^{2m} π^{d/2} (m-1)!)`` at ``m = 2, d = 1`` (``mgcv``'s ``eta.const``
for odd ``d``); equals ``1/12``."""

_EVAL_CHUNK = 2048


@dataclass(frozen=True)
class TprsState:
    """What a ``tp`` term must remember to be evaluated at new covariate values — the
    analogue of ``smooth$shift``, ``$Xu`` and ``$UZ``."""

    shift: float
    xu: np.ndarray
    uz: np.ndarray


def _kernel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.asarray(_ETA_CONST * np.abs(a[:, None] - b[None, :]) ** 3, dtype=np.float64)


def _eval_unique(xs: np.ndarray, state: TprsState) -> np.ndarray:
    """``[E(xs, xu), 1, xs] · UZ`` for distinct shifted values ``xs``."""
    out = np.empty((xs.shape[0], state.uz.shape[1]), dtype=np.float64)
    for start in range(0, xs.shape[0], _EVAL_CHUNK):
        chunk = xs[start : start + _EVAL_CHUNK]
        full = np.hstack([_kernel(chunk, state.xu), np.ones((chunk.shape[0], 1)), chunk[:, None]])
        out[start : start + _EVAL_CHUNK] = full @ state.uz
    return out


def tp_predict(x: np.ndarray, state: TprsState) -> np.ndarray:
    """The **unconstrained** ``tp`` design at ``x`` (``mgcv``'s ``Predict.matrix``): the
    caller applies the training sum-to-zero ``Z``. Evaluating at the training rows
    reproduces the training design exactly (same arithmetic)."""
    xs = np.asarray(x, dtype=np.float64) - state.shift
    xs_u, inverse = np.unique(xs, return_inverse=True)
    return _eval_unique(xs_u, state)[inverse.reshape(-1)]


def _eigen_truncation(
    xu: np.ndarray, k: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(E, λ_k, U_k, order-info)`` — the ``k`` eigenpairs of the full kernel matrix
    ``E`` with the largest ``|λ|``, negatives (ascending) first then positives
    (descending), each eigenvector's largest-magnitude entry made positive."""
    e = _kernel(xu, xu)
    values, vectors = np.linalg.eigh(e)
    keep = np.argsort(-np.abs(values), kind="stable")[:k]
    lam = values[keep]
    neg = sorted((i for i in range(k) if lam[i] < 0), key=lambda i: lam[i])
    pos = sorted((i for i in range(k) if lam[i] >= 0), key=lambda i: -lam[i])
    order = np.asarray(neg + pos, dtype=np.int64)
    u = vectors[:, keep[order]]
    lam = lam[order]
    lead = np.argmax(np.abs(u), axis=0)
    u = u * np.sign(u[lead, np.arange(k)])
    return e, lam, u, values


def _check_inputs(x: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1 or x.shape[0] == 0 or not np.all(np.isfinite(x)):
        raise PolarisValidationError("tp_basis: x must be a non-empty finite 1-D array.")
    if k < TP_NULL_DIM + 1:
        raise PolarisValidationError(
            f"tp_basis: k={k} is below the minimum {TP_NULL_DIM + 1} (null space {TP_NULL_DIM} "
            "plus one wiggly column); mgcv would silently raise it, so it is refused instead."
        )
    xs = x - float(np.mean(x))
    xu, inverse, counts = np.unique(xs, return_inverse=True, return_counts=True)
    if x.shape[0] > TP_MAX_KNOTS and xu.shape[0] > TP_MAX_KNOTS:
        raise PolarisValidationError(
            f"tp_basis: {x.shape[0]} rows and {xu.shape[0]} distinct values both exceed mgcv's "
            f"max.knots={TP_MAX_KNOTS}, where mgcv draws a RANDOM subsample of the distinct "
            "values (set.seed(1) then sample()); that stream is not reproduced, so a different "
            "basis would be returned silently. Aggregate the covariate to <= 2000 distinct "
            "values (e.g. a banded or integer age) or use bs='cr'."
        )
    if xu.shape[0] < k:
        raise PolarisValidationError(
            f"tp_basis: only {xu.shape[0]} distinct covariate value(s) for k={k}; mgcv refuses "
            "this too ('a term has fewer unique covariate combinations than specified maximum "
            "degrees of freedom')."
        )
    return xs, xu, inverse.reshape(-1), counts


def tp_basis(x: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray, TprsState]:
    """The **unconstrained** ``tp`` design ``(n, k)``, the (``scale.penalty``-rescaled)
    penalty ``(k, k)`` and the :class:`TprsState` — ``smoothCon(..., absorb.cons=FALSE)``.

    Raises:
        PolarisValidationError: ``k < 3``; fewer than ``k`` distinct values; or the
            subsampling regime described in the module docstring.
        PolarisComputationError: a degenerate (zero) column or penalty.
    """
    xs, xu, inverse, counts = _check_inputs(x, k)
    n = xs.shape[0]
    nu = xu.shape[0]
    m = TP_NULL_DIM
    _, lam, u, _ = _eigen_truncation(xu, k)
    t = np.column_stack([np.ones(nu), xu])
    q, _ = np.linalg.qr((t.T @ u).T, mode="complete")
    z = q[:, m:]
    uz = np.zeros((nu + m, k), dtype=np.float64)
    uz[:nu, : k - m] = u @ z
    uz[nu:, k - m :] = np.eye(m)
    s_raw = np.zeros((k, k), dtype=np.float64)
    s_raw[: k - m, : k - m] = z.T @ (lam[:, None] * z)
    state = TprsState(shift=float(np.mean(np.asarray(x, dtype=np.float64))), xu=xu, uz=uz)

    design_u = _eval_unique(xu, state)
    column_norm = np.sqrt(counts @ design_u**2)
    if np.any(column_norm == 0.0):
        raise PolarisComputationError("tp_basis: a design column is identically zero.")
    col_scale = sqrt(n) / column_norm
    design_u = design_u * col_scale
    uz = uz * col_scale
    s_scaled = s_raw * np.outer(col_scale, col_scale)
    s_scaled = (s_scaled + s_scaled.T) / 2.0
    x_inf_sq = _r_norm_inf(design_u) ** 2
    scale = _r_norm_one(s_scaled) / x_inf_sq
    if scale == 0.0:
        raise PolarisComputationError("tp_basis: the unscaled penalty is identically zero.")
    return (
        design_u[inverse],
        s_scaled / scale,
        TprsState(shift=state.shift, xu=xu, uz=uz),
    )


def subspace_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Sine of the largest principal angle between ``col(a)`` and ``col(b)`` (a metric on
    subspaces, so it satisfies the triangle inequality)."""
    qa = np.linalg.qr(a)[0]
    qb = np.linalg.qr(b)[0]
    resid = qb - qa @ (qa.T @ qb)
    return float(np.linalg.svd(resid, compute_uv=False)[0])


def eigenspace_rounding_bound(x: np.ndarray, k: int) -> float:
    """A-priori bound on how far a floating-point eigensolver can move the kept ``k``-dimensional
    eigenspace of the kernel matrix ``E``: ``nu · eps · ‖E‖₂ / gap`` (Davis-Kahan, with the LAPACK
    backward-error constant ``nu``), ``gap`` the smallest distance between a kept and a dropped
    eigenvalue. Computed from Polaris's own spectrum; it reads no ``mgcv`` output."""
    _, xu, _, _ = _check_inputs(x, k)
    values = np.linalg.eigvalsh(_kernel(xu, xu))
    keep = np.zeros(values.shape[0], dtype=bool)
    keep[np.argsort(-np.abs(values), kind="stable")[:k]] = True
    if keep.all():
        return float(xu.shape[0] * np.finfo(np.float64).eps)
    gap = float(np.min(np.abs(values[keep][:, None] - values[~keep][None, :])))
    return float(xu.shape[0] * np.finfo(np.float64).eps * np.max(np.abs(values)) / gap)


TP_BASIS_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_basis_tp builds the thin-plate regression spline "
        "(design_X, penalty_S) from the covariate values and k alone (eigen-truncation "
        "recipe, module docstring); mgcv computes them via smoothCon(s(x, bs='tp', k), "
        "absorb.cons=TRUE). Compared on the column space of design_X (sine of the largest "
        "principal angle) and on penalty_S in the basis mapping one design to the other (up to "
        "scale.penalty's gauge-dependent scalar), because the coefficient gauge is not unique; "
        "rank is compared directly."
    ),
    quantities=(
        ComparedQuantity(
            quantity="design_X column space",
            left_producer="gam_basis_tp.tp_basis + absorb_sum_to_zero_constraint",
            right_producer="mgcv smoothCon(s(x, bs='tp', k), absorb.cons=TRUE)$X",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="penalty_S in a common basis",
            left_producer="gam_basis_tp.tp_basis (Z'diag(lambda)Z, scale.penalty rescaled)",
            right_producer="mgcv smoothCon(...)$S after its own scale.penalty",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="rank",
            left_producer="numpy.linalg.matrix_rank on the constrained penalty",
            right_producer="mgcv smoothCon(...)$rank",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Provenance of the ``tp`` Stage-A comparison (ADR-193). ``x`` and ``k`` are the shared
recipe (not compared quantities); neither producer reads the other's output."""


@dataclass(frozen=True)
class TpBasisComparison:
    """One Stage-A verdict for a ``tp`` term. ``agrees`` is the gate; the rest explains it."""

    subspace_distance: float
    penalty_rel_diff: float
    penalty_scale: float
    rank_diff: int
    rounding_bound: float
    mgcv_vs_exact: float
    tolerance: float
    agrees: bool
    evidence: VerificationClaim


def derived_tolerance(rounding_bound: float, mgcv_vs_exact: float) -> float:
    """Acceptance tolerance for the gauge-invariant comparison, derived and not chosen.

    ``d(.,.)`` is the sine of the largest principal angle between two column spaces (a metric).
    Three constructions of the SAME recipe exist: Polaris's, ``mgcv``'s, and an exact reference
    the probe builds in R with ``eigen()`` from ``mgcv``'s own ``Xu``. ``mgcv``'s truncation is a
    Lanczos result, so ``d(mgcv, exact_R)`` is not zero (measured up to ~3e-8); the probe reads
    it. Polaris and the exact reference are both full eigensolvers and differ by rounding, at
    most :func:`eigenspace_rounding_bound` (``1e3`` times it absorbs the amplification of an
    eigenvector error through the kernel when the design is formed, and the second
    eigensolver). So ``d(polaris, mgcv) <= d(mgcv, exact_R) + 1e3 · rounding_bound`` for a
    correct recipe. A recipe error (wrong kernel, truncating ``Z'EZ``, wrong ``M``) moves the
    subspace by 1e-3 to 1 and is not covered. The penalty is a quadratic form in ``k`` columns each
    perturbed by at most that much, so its relative Frobenius error is bounded by ``k`` times it
    (:func:`compare_tp_basis`).
    """
    return mgcv_vs_exact + 1.0e3 * rounding_bound


def compare_tp_basis(
    x: np.ndarray,
    k: int,
    mgcv_design: np.ndarray,
    mgcv_penalty: np.ndarray,
    mgcv_rank: int,
    mgcv_vs_exact: float,
) -> TpBasisComparison:
    """Compare Polaris's constrained ``tp`` design/penalty with ``mgcv``'s, gauge-free.

    ``x`` and ``k`` are the shared recipe; the ``mgcv_*`` arguments are the reference's
    output and are passed by the caller, so :func:`tp_basis` (the producer) sees
    neither (ADR-193's mechanical test applies to ``tp_basis``, not to this comparator).

    ``penalty_S`` is compared up to a positive scalar: ``smoothCon``'s ``scale.penalty``
    divides ``S`` by ``norm1(S) / norminf(X)²``, which depends on the coefficient gauge, so two
    correct constructions can differ by that scalar (measured: 164.55 on a ``k = nu`` case where
    the designs and the quadratic form agree exactly). The scalar only rescales ``sp``
    (``λS`` is what is fitted), so it is reported as :attr:`TpBasisComparison.penalty_scale`
    and not gated.
    """
    from polaris_re.analytics.gam_basis_cr import absorb_sum_to_zero_constraint

    design_u, s_u, _ = tp_basis(x, k)
    design, s = absorb_sum_to_zero_constraint(design_u, s_u)
    d_x = subspace_distance(design, mgcv_design)
    transform, *_ = np.linalg.lstsq(design, mgcv_design, rcond=None)
    s_in_mgcv_basis = transform.T @ s @ transform
    scale = float(np.sum(mgcv_penalty * s_in_mgcv_basis) / np.sum(s_in_mgcv_basis**2))
    penalty_rel = float(
        np.linalg.norm(scale * s_in_mgcv_basis - mgcv_penalty) / np.linalg.norm(mgcv_penalty)
    )
    rank_diff = int(mgcv_rank - np.linalg.matrix_rank(s))
    bound = eigenspace_rounding_bound(x, k)
    tol = derived_tolerance(bound, mgcv_vs_exact)
    return TpBasisComparison(
        subspace_distance=d_x,
        penalty_rel_diff=penalty_rel,
        penalty_scale=scale,
        rank_diff=rank_diff,
        rounding_bound=bound,
        mgcv_vs_exact=mgcv_vs_exact,
        tolerance=tol,
        agrees=bool(d_x <= tol and penalty_rel <= k * tol and rank_diff == 0),
        evidence=TP_BASIS_CLAIM,
    )

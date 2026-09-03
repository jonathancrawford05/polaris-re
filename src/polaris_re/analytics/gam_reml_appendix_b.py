"""Wood (2011) Appendix B — the rank-robust generalized determinant `|S|+`.

``docs/PLAN_mgcv_parity_engine.md`` slice 5c localised the `sp`-dependent REML
criterion discrepancy found on slice 5b's N=4 structure (ADR-208's amendment)
to `gam_reml.reml_score_general`'s `log|S|+` term: it forms `S = sum_j
lambda_j S_j`, eigendecomposes the SUM, and cuts the null space at a fixed
relative tolerance of ``1e-10``. When the `lambda`'s span many decades that
cut misreads the true (lambda-independent) null space of the model, and the
score moves discretely as eigenvalues are misclassified — Wood's own
"numerical zero leakage" (Section 3.1).

This module builds Wood's Appendix B similarity-transform algorithm, which
determines the rank of ``S = sum_j lambda_j S_j`` from the STRUCTURE of the
individual blocks rather than from a single eigenvalue cut on their weighted
sum, and is provably invariant to how the ``lambda_j`` are scaled relative to
one another. It replaces the null-space cut ONLY — the fitter
(:mod:`gam_fit`), the penalized deviance and the `log|X'WX+S|` term are
untouched (measured separately, ``docs/RECALIBRATION_mgcv_parity_2026-08-25.md``
Section 1.2: naive `slogdet` tracks a diagonally-preconditioned Cholesky
closely even at the worst conditioning reached, because `X'WX+S` is full rank
and positive definite — unlike the generalised determinant, it has no
null-space decision to get wrong).

**Scope, per the PLAN.** Build the whole of Appendix B — the similarity
transform, the accumulated orthogonal transform, the pivoted-QR determinant
AND the stable square root ``E`` (``E^T E = S``) — but wire only the
determinant into the REML score. ``E`` and the accumulated transform are
built and tested on their own terms (never through the score) so that a
later adoption of the reparameterisation through the fitter (needed if PIRLS
ever moves to Newton's method for a non-canonical link, Wood Section 3.3)
starts from a component already known correct, rather than from an
orientation bug hiding behind an invariant (`log|S|+` is insensitive to a
transposed similarity transform — see the ``EtE`` test below and mutation 6
in the ADR).

**Implemented from the paper, not from mgcv's source** — the same footing as
ADR-196 (Wood 2011 eq. 4) and ADR-202 (Wood, Pya & Sadfken 2016 eq. 7);
transcribing mgcv's own C/R implementation would cross its GPL licence
(Anchor 8's companion rule, this project is MIT).

Wood, S.N. (2011), *JRSS-B* 73(1), 3-36, "Fast stable restricted maximum
likelihood and marginal likelihood estimation of semiparametric generalized
linear models", Section 3.1 and Appendix B.
"""

from dataclasses import dataclass

import numpy as np
import scipy.linalg

from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "AppendixBResult",
    "appendix_b_transform",
    "dlogdet_s_plus_drho",
    "logdet_s_plus",
]

_TINY = 1e-300
"""Floor to avoid a zero-Frobenius-norm block dividing by zero — the same
role as the existing `max(largest, 1e-300)` floor in `gam_reml.py`, not a
rank-decision tolerance."""


def _pivoted_qr_logdet(matrix: np.ndarray) -> float:
    """``log|matrix|`` by pivoted QR — Wood's stated choice for this step,
    because "alternative methods (Choleski or symmetric eigen) would require
    an additional pre-conditioning step" (Appendix B) — QR "operates on
    columns without mixing them", which preserves the separation the
    similarity-transform iteration built. Assumes ``matrix`` is the
    already-resolved, genuinely full-rank block the iteration hands this
    function; a singular or near-singular input here would be an algorithm
    defect upstream, not something for this helper to guard against."""
    if matrix.shape[0] == 0:
        return 0.0
    _q, r, _piv = scipy.linalg.qr(matrix, pivoting=True)
    return float(np.sum(np.log(np.abs(np.diag(r)))))


@dataclass(frozen=True)
class AppendixBResult:
    """Everything Appendix B produces, so ``E`` and the accumulated
    transform can be tested independently of the score that (for now) uses
    only :attr:`logdet_s_plus`.

    Attributes:
        logdet_s_plus: ``log|S|+`` — the generalized determinant over the
            structurally-determined positive eigenspace of
            ``S = sum_j lambda_j S_j``.
        rank: the dimension of that positive eigenspace (``r`` accumulated
            across every iteration of the algorithm).
        e: the stable square root, shape ``(rank, q)`` where ``q`` is the
            common dimension of the supplied blocks, satisfying
            ``E^T @ E == S`` restricted to its positive eigenspace (to
            floating-point precision) — built per Appendix B's similarity
            transform, **not adopted by the fitter in this slice** (PLAN
            5c scope: "wire only the determinant").
    """

    logdet_s_plus: float
    rank: int
    e: np.ndarray


def _dominant_split(
    active: list[int],
    s_bar: dict[int, np.ndarray],
    lambdas: np.ndarray,
) -> tuple[list[int], list[int]]:
    """Wood Appendix B step 2: split ``active`` into the dominant set
    ``alpha`` and the subordinate set ``gamma_prime`` by comparing each
    block's own scale ``Omega_i = ||S_bar_i||_F * lambda_i`` against
    ``epsilon * max(Omega)``, ``epsilon`` the CUBE ROOT of machine
    precision — Wood's own stated choice, not a fitted constant (mutation 3
    in the ADR's protocol tests using plain machine epsilon instead)."""
    eps_cube_root = np.finfo(np.float64).eps ** (1.0 / 3.0)
    omega = {i: float(np.linalg.norm(s_bar[i], "fro")) * lambdas[i] for i in active}
    max_omega = max(omega.values())
    alpha = [i for i in active if omega[i] >= eps_cube_root * max_omega]
    gamma_prime = [i for i in active if omega[i] < eps_cube_root * max_omega]
    return alpha, gamma_prime


def _formal_rank(
    alpha: list[int],
    s_bar: dict[int, np.ndarray],
    dim: int,
    rank_eps_power: float,
) -> int:
    """Wood Appendix B step 3: the eigenvalues of the alpha-dominant blocks'
    OWN Frobenius-normalized sum give the formal rank ``r`` of the currently
    active subspace — count eigenvalues exceeding ``eps_tilde`` times the
    dominant one, ``eps_tilde = eps**rank_eps_power`` with
    ``rank_eps_power`` in Wood's stated ``[0.7, 0.9]`` (mutation 4 in the
    ADR's protocol tests a fixed ``1e-10`` here instead — the shipped
    defect this whole module exists to replace)."""
    normalized_sum = np.zeros((dim, dim), dtype=np.float64)
    for i in alpha:
        normalized_sum = normalized_sum + s_bar[i] / max(
            float(np.linalg.norm(s_bar[i], "fro")), _TINY
        )
    eigenvalues = np.linalg.eigvalsh(normalized_sum)
    largest = float(eigenvalues.max()) if eigenvalues.size else 0.0
    eps_tilde = np.finfo(np.float64).eps ** rank_eps_power
    return int(np.sum(eigenvalues > max(largest, _TINY) * eps_tilde))


def appendix_b_transform(
    blocks: tuple[np.ndarray, ...],
    lambdas: np.ndarray,
    *,
    prestep_eps_power: float = 0.8,
    rank_eps_power: float = 0.8,
) -> AppendixBResult:
    """Wood (2011) Appendix B: the similarity-transform determinant of
    ``S = sum_j lambda_j blocks[j]``, robust to badly-scaled ``lambda``.

    Args:
        blocks: one ``(q, q)`` symmetric PSD penalty block per smoothing
            parameter, all in the same ``q``-dimensional coordinate system
            (``gam_reml_optimize``'s own convention — already padded to the
            full design width).
        lambdas: one positive smoothing parameter per block, ``(len(blocks),)``.
        prestep_eps_power: the machine-epsilon power used to separate
            genuinely-zero eigenvalues of the AVERAGE normalized block from
            positive ones in the pre-step (Appendix B: "S not formally full
            rank"). Not tuned to any measured case — a value in the same
            ``[0.7, 0.9]`` family Wood names for the in-loop rank cut
            (:func:`_formal_rank`), because both are the same kind of
            decision: is this eigenvalue numerically indistinguishable from
            zero relative to the largest one.
        rank_eps_power: passed to :func:`_formal_rank` each iteration.

    Returns:
        :class:`AppendixBResult`.

    Raises:
        PolarisValidationError: if ``blocks`` is empty, blocks are not all
            square of the same size, or ``lambdas`` has the wrong length or
            a non-positive entry.
    """
    if not blocks:
        raise PolarisValidationError("appendix_b_transform: blocks must be non-empty.")
    q = blocks[0].shape[0]
    for b in blocks:
        if b.shape != (q, q):
            raise PolarisValidationError(
                f"appendix_b_transform: all blocks must be square and equal-sized; "
                f"got shapes {[b.shape for b in blocks]}."
            )
    lambdas = np.asarray(lambdas, dtype=np.float64)
    if lambdas.shape != (len(blocks),):
        raise PolarisValidationError(
            f"appendix_b_transform: lambdas has shape {lambdas.shape}, expected "
            f"({len(blocks)},) to match blocks."
        )
    if np.any(lambdas <= 0.0):
        raise PolarisValidationError("appendix_b_transform: every lambda must be positive.")

    m = len(blocks)

    # Pre-step: S may not be formally full rank even at the model level (a
    # null space shared by every block, independent of lambda). Symmetric
    # eigendecomposition of the UNWEIGHTED, Frobenius-normalized average
    # isolates it; U_plus spans the complement.
    average = np.zeros((q, q), dtype=np.float64)
    for b in blocks:
        average = average + b / max(float(np.linalg.norm(b, "fro")), _TINY)
    avg_eigenvalues, avg_eigenvectors = np.linalg.eigh(average)
    prestep_tol = float(avg_eigenvalues.max()) * np.finfo(np.float64).eps ** prestep_eps_power
    u_plus = avg_eigenvectors[:, avg_eigenvalues > max(prestep_tol, _TINY)]
    q0 = u_plus.shape[1]

    s_bar: dict[int, np.ndarray] = {i: u_plus.T @ blocks[i] @ u_plus for i in range(m)}
    active = list(range(m))

    logdet = 0.0
    rank = 0
    # q_accum: the running (q0, q0) orthogonal similarity transform mapping
    # the pre-step coordinates to the fully block-resolved ones. Columns
    # [0:K) are already finalized (each iteration's own eigenbasis, in
    # order); columns [K:q0) are still "active" and get rotated in place
    # each iteration — contiguous, since resolved dimensions are always
    # peeled from the front.
    q_accum = np.eye(q0, dtype=np.float64)
    # e_blocks[k] is the Cholesky-transpose factor for the k-th finalized
    # block, in order — concatenated block-diagonally at the end to build E.
    e_blocks: list[np.ndarray] = []
    k = 0
    dim = q0

    while True:
        alpha, gamma_prime = _dominant_split(active, s_bar, lambdas)
        r = _formal_rank(alpha, s_bar, dim, rank_eps_power)

        if r == dim:
            # Terminate: the currently active subspace is genuinely full
            # rank under every remaining block combined.
            s_total = np.zeros((dim, dim), dtype=np.float64)
            for i in active:
                s_total = s_total + lambdas[i] * s_bar[i]
            logdet += _pivoted_qr_logdet(s_total)
            rank += dim
            e_blocks.append(np.linalg.cholesky(s_total).T)
            break

        # Step 5: eigendecompose the DOMINANT terms' own (unnormalized,
        # lambda-weighted) sum — descending order, so the first r columns
        # are the r "confidently nonzero" directions.
        s_dominant = np.zeros((dim, dim), dtype=np.float64)
        for i in alpha:
            s_dominant = s_dominant + lambdas[i] * s_bar[i]
        dom_eigenvalues, dom_eigenvectors = np.linalg.eigh(s_dominant)
        order = np.argsort(dom_eigenvalues)[::-1]
        dom_eigenvalues = dom_eigenvalues[order]
        dom_eigenvectors = dom_eigenvectors[:, order]
        u_r = dom_eigenvectors[:, :r]
        u_n = dom_eigenvectors[:, r:]
        d_r = np.diag(dom_eigenvalues[:r])

        # Steps 6-7: the subordinate terms leak a little into the r
        # dominant directions too — correct for it before finalizing them,
        # then re-express every subordinate block in the U_n (still-null)
        # basis for the next iteration.
        s_subordinate = np.zeros((dim, dim), dtype=np.float64)
        for i in gamma_prime:
            s_subordinate = s_subordinate + lambdas[i] * s_bar[i]
        c_resolved = d_r + u_r.T @ s_subordinate @ u_r

        logdet += _pivoted_qr_logdet(c_resolved)
        rank += r
        e_blocks.append(np.linalg.cholesky(c_resolved).T)

        u_full = np.concatenate([u_r, u_n], axis=1)
        q_accum[:, k : k + dim] = q_accum[:, k : k + dim] @ u_full
        k += r
        dim -= r

        if not gamma_prime or dim == 0:
            # Nothing left to process: the remaining `dim` dimensions are
            # the model's TRUE null space (no active block has any weight
            # there), contributing 0 to log|S|+ — discard rather than force
            # a spurious final full-rank block.
            break

        s_bar = {i: u_n.T @ s_bar[i] @ u_n for i in gamma_prime}
        active = gamma_prime

    # e_blocks concatenates to a (rank, rank) block-diagonal factor of the
    # RESOLVED part only; pad with zero columns for any discarded true
    # null-space directions (q_accum's trailing q0-rank columns) so the
    # shapes line up with q_accum's full q0 columns.
    e_square = (
        scipy.linalg.block_diag(*e_blocks) if e_blocks else np.zeros((0, 0), dtype=np.float64)
    )
    e_reduced = np.hstack([e_square, np.zeros((rank, q0 - rank), dtype=np.float64)])
    # Map back: q_accum @ (block-diagonal S in the resolved basis) @
    # q_accum^T equals the original (U_plus-projected) sum
    # `sum_i lambda_i * s_bar_i`, restricted to its positive eigenspace —
    # so e_full = e_reduced @ q_accum^T satisfies e_full^T @ e_full equal
    # to that restriction, and e = e_full @ u_plus^T maps it back through
    # the pre-step projection to the original q-dimensional coordinates.
    e_full = e_reduced @ q_accum.T
    e = e_full @ u_plus.T

    return AppendixBResult(logdet_s_plus=logdet, rank=rank, e=e)


def logdet_s_plus(blocks: tuple[np.ndarray, ...], lambdas: np.ndarray) -> float:
    """``log|S|+`` alone — the one quantity :mod:`gam_reml` wires in.

    A thin wrapper over :func:`appendix_b_transform` for call sites that
    don't need ``E`` or the rank.
    """
    return appendix_b_transform(blocks, lambdas).logdet_s_plus


def dlogdet_s_plus_drho(blocks: tuple[np.ndarray, ...], lambdas: np.ndarray) -> np.ndarray:
    """``d(log|S|+)/drhoⱼ = λⱼ tr(S⁺Sⱼ)`` — PLAN slice 7d, the fourth term of
    the analytic REML gradient (``docs/PLAN_mgcv_parity_engine.md``, "Part 1").

    The standard generalized-determinant derivative identity (Wood 2011's own
    statement, quoted in the PLAN slice), with ``S⁺`` the Moore-Penrose
    pseudoinverse of ``S = Σⱼ λⱼblocks[j]`` restricted to its positive
    eigenspace. **``S⁺`` is built from :func:`appendix_b_transform`'s own
    ``e`` (``eᵀe = S``, already resolved by the structural rank decision),
    never by eigendecomposing the raw summed ``S`` at a fixed tolerance** —
    that eigen-cut is exactly Defect A (this module's own docstring), and
    reintroducing it here for the derivative would carry the identical
    numerical-zero-leakage failure into the gradient that Appendix B exists
    to keep out of the score.

    Economy SVD of ``e`` (``(rank, q)``, full row rank by construction):
    ``e = UΣVᵀ`` gives ``S⁺ = VΣ⁻²Vᵀ`` directly (``V``'s columns are an
    orthonormal basis of ``S``'s row/column space, ``Σ`` its nonzero
    singular values) — so ``tr(S⁺Sⱼ) = Σᵢ σᵢ⁻² vᵢᵀSⱼvᵢ``, computed per block
    without ever forming the ``(q, q)`` pseudoinverse explicitly.

    Args:
        blocks: as :func:`appendix_b_transform`.
        lambdas: as :func:`appendix_b_transform`.

    Returns:
        ``(len(blocks),)`` — one ``d(log|S|+)/drhoⱼ`` per block, natural-log
        ``rho`` (matching :mod:`~polaris_re.analytics.gam_derivatives`'s own
        convention, ``rhoⱼ = log(λⱼ)``).
    """
    result = appendix_b_transform(blocks, lambdas)
    e = result.e
    n_blocks = len(blocks)
    if e.shape[0] == 0:
        # The model's positive eigenspace is empty (every block is exactly
        # zero) — log|S|+ is identically 0 regardless of rho, so every
        # derivative is 0.
        return np.zeros(n_blocks, dtype=np.float64)

    _u, sigma, vt = np.linalg.svd(e, full_matrices=False)
    v = vt.T  # (q, rank), orthonormal columns spanning S's row/column space
    inv_sigma_sq = 1.0 / (sigma**2)

    grad = np.empty(n_blocks, dtype=np.float64)
    for j, block in enumerate(blocks):
        block_v = block @ v  # (q, rank)
        diag_vals = np.einsum("qi,qi->i", v, block_v)  # v_i^T @ block @ v_i, one per column
        trace_s_plus_block = float(np.sum(inv_sigma_sq * diag_vals))
        grad[j] = lambdas[j] * trace_s_plus_block
    return grad

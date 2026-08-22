"""Wood, Pya and Saefken (2016) eq. (7) — the full smoothing-parameter-uncertainty
covariance, of which plain Kass-Steffey is the first-order part.

**What this closes, and what ADR-190 already established.** ADR-190 measured that
``mgcv``'s ``vcov(unconditional = TRUE)`` is *not* ``Vb + J Vrho Jᵀ``: built
entirely from ``mgcv``'s own coefficients, ``Vrho`` and lambda, that expression
reproduces *our* number (inflation 1.11-1.21x), not ``mgcv``'s (1.49-1.87x), with
a non-constant ratio of 3.2-4.1x. It re-scoped the level-4 blocker from "find the
bug in our arithmetic" to "implement the fuller correction", and named the missing
ingredient as ``dw/drho``.

**Wood, Pya and Saefken (2016) section 4 states the same thing from the other
side.** Their eq. (7) is::

    V'_beta = V_beta + V' + V''      with   V' = J Vrho Jᵀ

and the paper then says, verbatim: *"Dropping V'' we have the Kass and Steffey
(1989) approximation beta|y ~ N(beta_hat, V*_beta) where V*_beta = V_beta +
J Vrho Jᵀ."* So **V'' is precisely and entirely what this engine was missing**, and
ADR-190's measurement and the paper's own framing agree on that without either
having been derived from the other.

The V'' term
-------------
With ``R_rho`` the factor satisfying ``R_rhoᵀ R_rho = V_beta`` (so ``R`` is the
upper-triangular Cholesky factor), eq. (7) reads::

    V''_jm = sum_i sum_k sum_l  (dR_ij/drho_k) Vrho_kl (dR_im/drho_l)

The ``i`` sum is an inner product of two columns, so this collapses to a form with
no explicit element loops::

    V'' = sum_k sum_l  Vrho_kl  (dR/drho_k)ᵀ (dR/drho_l)

which is what :func:`second_order_correction` computes.

Why this needs ``dw/drho`` — the ADR-190 link, concretely
-----------------------------------------------------------
``V_beta = (I_hat + S_lambda)⁻¹``, and ``I_hat = XᵀWX`` depends on ``rho`` through
the working weights ``W``. So::

    dV_beta/drho_k = -V_beta (Xᵀ (dW/drho_k) X + lambda_k S_k) V_beta

and ``dW/drho_k`` is exactly
:func:`~polaris_re.analytics.gam_derivatives.dw_drho` (ADR-201, Wood 2011
Appendix D). That is the whole reason ADR-190 named ``dw/drho`` as the blocking
ingredient: **without it there is no ``dR/drho``, and without ``dR/drho`` there is
no V''.** Plain Kass-Steffey needs only ``J``, which is why the engine could
compute the first-order term all along.

``dR/drho`` — differentiating a Cholesky factor
-------------------------------------------------
Standard, and derived here rather than quoted: differentiating ``RᵀR = V`` gives
``(dR)ᵀR + Rᵀ(dR) = dV``. Writing ``A = R⁻ᵀ (dV) R⁻¹`` and ``B = (dR) R⁻¹`` turns
this into ``B + Bᵀ = A`` with ``B`` upper triangular, whose unique solution is
``B = Phi(A)`` — the upper triangle of ``A`` with the diagonal halved. Then
``dR = B R``. :func:`cholesky_factor_derivative` implements exactly that, and
:mod:`tests.test_analytics.test_gam_uncertainty` checks it against a central
difference of an actual Cholesky factorisation.

Scope
------
This module computes the correction; it does **not** re-point any production path.
:func:`~polaris_re.analytics.experience_gam_penalized.smoothing_uncertainty` and
every shipped entry point are untouched (PLAN Anchor 7). Whether the corrected
covariance should replace the shipped one is a separate decision with its own
sign-off, and labelling any resulting interval a 95% band remains
maintainer-reserved regardless.
"""

import numpy as np

from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "UncertaintyCorrection",
    "cholesky_factor_derivative",
    "d_vbeta_d_rho",
    "second_order_correction",
    "unconditional_covariance",
]


class UncertaintyCorrection:
    """The three terms of Wood, Pya and Saefken (2016) eq. (7), kept separable.

    Separable on purpose: ``first_order`` alone is the Kass-Steffey approximation
    this engine already had, so carrying both terms lets a report state the
    before and after from one computation rather than two code paths, and lets a
    test assert that the first-order part is unchanged by the addition of the
    second.
    """

    def __init__(
        self,
        v_beta: np.ndarray,
        first_order: np.ndarray,
        second_order: np.ndarray,
    ) -> None:
        self.v_beta = v_beta
        self.first_order = first_order
        self.second_order = second_order

    @property
    def kass_steffey(self) -> np.ndarray:
        """``V*_beta = V_beta + J Vrho Jᵀ`` — the first-order approximation, i.e.
        what this engine computed before this module existed."""
        return self.v_beta + self.first_order

    @property
    def full(self) -> np.ndarray:
        """``V'_beta = V_beta + V' + V''`` — eq. (7) in full."""
        return self.v_beta + self.first_order + self.second_order

    def inflation(self, corrected: np.ndarray) -> float:
        """``mean(diag(corrected)) / mean(diag(V_beta))``.

        The scale-free summary the conformance suite compares, chosen there
        because the two sides select different lambda at free ``sp`` and a
        ratio survives that where an element-wise comparison would not
        (RUNBOOK level 4, metric 2).
        """
        return float(np.mean(np.diag(corrected)) / np.mean(np.diag(self.v_beta)))


def cholesky_factor_derivative(r_factor: np.ndarray, d_v: np.ndarray) -> np.ndarray:
    """``dR/drho_k`` given ``R`` (upper, ``RᵀR = V``) and ``dV/drho_k``.

    Solves ``(dR)ᵀR + Rᵀ(dR) = dV`` for upper-triangular ``dR`` — see the module
    docstring for the derivation. ``dV`` must be symmetric; it is symmetrised
    here rather than trusted, because it arrives from a product of matrices that
    are only symmetric up to round-off.
    """
    p = r_factor.shape[0]
    if r_factor.shape != (p, p) or d_v.shape != (p, p):
        raise PolarisValidationError(
            f"cholesky_factor_derivative: R is {r_factor.shape} and dV is "
            f"{d_v.shape}; both must be ({p}, {p})."
        )
    d_v = (d_v + d_v.T) / 2.0
    r_inv = np.linalg.inv(r_factor)
    a = r_inv.T @ d_v @ r_inv
    # Phi(A): upper triangle, diagonal halved.
    b = np.triu(a)
    np.fill_diagonal(b, np.diag(a) / 2.0)
    return b @ r_factor


def d_vbeta_d_rho(
    v_beta: np.ndarray,
    design: np.ndarray,
    dw_drho_k: np.ndarray,
    penalty_block: np.ndarray,
    lambda_k: float,
) -> np.ndarray:
    """``dV_beta/drho_k = -V_beta (Xᵀ diag(dw/drho_k) X + lambda_k S_k) V_beta``.

    The chain that makes ``dw/drho`` (ADR-201) load-bearing for level 4: ``V_beta``
    depends on ``rho`` both through the explicit penalty ``lambda_k S_k`` and
    through the working weights, and dropping the weight term is what leaves only
    the first-order correction.

    Args:
        v_beta: ``(p, p)``, the conditional covariance ``(XᵀWX + S_lambda)⁻¹``.
        design: ``(n, p)``.
        dw_drho_k: ``(n,)`` — one row of
            :func:`~polaris_re.analytics.gam_derivatives.dw_drho`.
        penalty_block: ``(p, p)``, ``S_k``.
        lambda_k: ``exp(rho_k)``.
    """
    inner = design.T @ (dw_drho_k[:, None] * design) + lambda_k * penalty_block
    out = -v_beta @ inner @ v_beta
    return (out + out.T) / 2.0


def second_order_correction(d_r_d_rho: tuple[np.ndarray, ...], v_rho: np.ndarray) -> np.ndarray:
    """``V'' = sum_k sum_l Vrho_kl (dR/drho_k)ᵀ (dR/drho_l)`` — eq. (7)'s second term.

    Args:
        d_r_d_rho: one ``(p, p)`` ``dR/drho_k`` per smoothing parameter.
        v_rho: ``(M, M)``, the covariance of ``rho``.
    """
    m = len(d_r_d_rho)
    if v_rho.shape != (m, m):
        raise PolarisValidationError(
            f"second_order_correction: {m} dR/drho block(s) but Vrho is "
            f"{v_rho.shape}; expected ({m}, {m})."
        )
    p = d_r_d_rho[0].shape[0]
    out = np.zeros((p, p), dtype=np.float64)
    for k in range(m):
        for lidx in range(m):
            out = out + v_rho[k, lidx] * (d_r_d_rho[k].T @ d_r_d_rho[lidx])
    return (out + out.T) / 2.0


def unconditional_covariance(
    v_beta: np.ndarray,
    design: np.ndarray,
    dbeta_drho: np.ndarray,
    dw_drho_all: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    log_lambda: np.ndarray,
    v_rho: np.ndarray,
) -> UncertaintyCorrection:
    """Wood, Pya and Saefken (2016) eq. (7), assembled.

    Args:
        v_beta: ``(p, p)`` conditional covariance.
        design: ``(n, p)``.
        dbeta_drho: ``(M, p)`` — ``J``, from
            :func:`~polaris_re.analytics.gam_derivatives.d_beta_d_rho`. **This is
            the one place in the epic where ``dbeta/drho`` is used rather than
            compared** — PLAN Anchor 2 forbids comparing coefficients against
            ``mgcv``, not using them internally, and eq. (7) is written in terms
            of ``J``.
        dw_drho_all: ``(M, n)`` from
            :func:`~polaris_re.analytics.gam_derivatives.dw_drho`.
        penalties: the ``S_k``, each ``(p, p)``.
        log_lambda: ``(M,)``.
        v_rho: ``(M, M)``.
    """
    p = v_beta.shape[0]
    m = log_lambda.shape[0]
    if dbeta_drho.shape != (m, p):
        raise PolarisValidationError(
            f"unconditional_covariance: dbeta_drho is {dbeta_drho.shape}, expected {(m, p)}."
        )
    if dw_drho_all.shape[0] != m:
        raise PolarisValidationError(
            f"unconditional_covariance: dw_drho_all has {dw_drho_all.shape[0]} "
            f"row(s), expected {m}."
        )

    first_order = dbeta_drho.T @ v_rho @ dbeta_drho

    try:
        r_factor = np.linalg.cholesky(v_beta).T  # upper, RᵀR = V_beta
    except np.linalg.LinAlgError as exc:
        raise PolarisComputationError(
            "unconditional_covariance: V_beta is not positive definite, so the "
            "Cholesky factor eq. (7) is written in terms of does not exist. The "
            "paper's own remedy for a degenerate case is regularisation of the "
            "rho Hessian (section 4), not of V_beta; this path is not derived."
        ) from exc

    lam = np.exp(log_lambda)
    d_r = tuple(
        cholesky_factor_derivative(
            r_factor,
            d_vbeta_d_rho(v_beta, design, dw_drho_all[k], penalties[k], float(lam[k])),
        )
        for k in range(m)
    )
    return UncertaintyCorrection(
        v_beta=v_beta,
        first_order=(first_order + first_order.T) / 2.0,
        second_order=second_order_correction(d_r, v_rho),
    )

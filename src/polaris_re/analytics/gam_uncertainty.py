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

The asymmetry between the two terms — measured, not assumed
-------------------------------------------------------------
``mgcv`` does **not** use the same ``Vrho`` in both terms, and this is the last
thing that stood between this module and parity:

* ``V'`` (first order) uses the **unregularised** ``H^-1``.
* ``V''`` (second order) uses the **ridged** ``(H + 0.1 I)^-1``.

Found by localisation, not by trying combinations blindly: with a single ridged
``Vrho`` the residual against ``mgcv``'s own ``Vc - Vp`` was 31.8% on
``binomial-logit``, and that residual was **essentially rank-1** (relative
singular values 1.000, 0.084, 0.0006). Its dominant direction had ``|cos| =
0.9994`` with ``J[1]``, and the best-fitting multiple of ``J[1] J[1]^T`` was
**3210** — against an unregularised ``H^-1[1,1]`` of **3184**, a ~1% match. That
named the term and the treatment together.

Validated on **five held-out cases** that played no part in identifying it —
different seeds, sizes and dimensions, including a ``cloglog`` (non-canonical)
case:

==============  ==================  ====================  =================
case            family/link         element-wise residual  inflation rel err
==============  ==================  ====================  =================
``v-pois-a``    poisson/log         0.730%                0.071%
``v-pois-b``    poisson/log         0.334%                0.010%
``v-binom-a``   binomial/logit      0.075%                0.000%
``v-binom-b``   binomial/logit      0.076%                0.007%
``v-cloglog-a`` binomial/cloglog    0.219%                0.002%
==============  ==================  ====================  =================

**The residual is small but not float noise** (0.07-0.73% element-wise). The
likeliest source is the remainder ``r`` the paper's own first-order Taylor
expansion drops — eq. (7) is an approximation, not an identity — so exact
agreement was never the target. It is recorded rather than explained away.

Scope — what is and is not closed
-----------------------------------
**The level-4 FORMULA gap is closed**: this module reproduces ``mgcv``'s
``vcov(unconditional = TRUE)`` to <1% element-wise and <0.1% on the inflation
ratio, where ADR-190 measured the old first-order-only correction inflating
1.11-1.21x against ``mgcv``'s 1.49-1.87x.

**The conformance suite's level 4 will still DISAGREE**, and that is correct
rather than a contradiction: it exercises
:func:`~polaris_re.analytics.experience_gam_penalized.smoothing_uncertainty`,
the shipped path, which this module does not touch. **Re-pointing production at
this is a separate decision requiring PLAN Anchor 7 sign-off**, and it carries
its own question about determinism (ADR-186). Labelling any resulting interval a
95% band remains maintainer-reserved (ADR-188) regardless.
"""

import numpy as np

from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "MGCV_RHO_RIDGE",
    "UncertaintyCorrection",
    "cholesky_factor_derivative",
    "d_vbeta_d_rho",
    "regularized_v_rho",
    "second_order_correction",
    "unconditional_covariance",
    "wood_factor_and_derivative",
]

MGCV_RHO_RIDGE = 0.1
"""The ridge ``mgcv`` adds to the rho Hessian before inverting it for ``Vrho``.

**Identified by measurement, not chosen.** Wood, Pya and Saefken (2016) section 4
states the mechanism but not the value: *"it is necessary to substitute a
Moore-Penrose pseudoinverse of the Hessian if a smoothing parameter is
effectively infinite, or otherwise to regularize the inversion (which is
equivalent to placing a Gaussian prior on rho)."* ``mgcv`` exposes the result as
``m$V.sp``, and::

    m$V.sp == solve(m$outer.info$hess + 0.1 * I)

to a residual of **1.78e-15** on two independent fits (poisson-log and
binomial-logit), with a one-dimensional search over the ridge returning
``0.1000000000``. So this is a Gaussian prior on rho with variance 10, read off
``mgcv``'s own published quantity — not a constant tuned until a comparison went
green, which this project forbids (PLAN Anchor 8).

Why it matters so much: on a saturated smoothing parameter the unregularized
inverse is enormous (``lambda_2 ~ 1.06e+05`` gives a Hessian eigenvalue of
~1.35e-4, hence ~7400 of variance), and ``V''`` inherits it — the unregularized
correction overshoots ``mgcv`` by 3-4x."""


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
        return np.asarray(self.v_beta + self.first_order, dtype=np.float64)

    @property
    def full(self) -> np.ndarray:
        """``V'_beta = V_beta + V' + V''`` — eq. (7) in full."""
        return np.asarray(self.v_beta + self.first_order + self.second_order, dtype=np.float64)

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
    return np.asarray(b @ r_factor, dtype=np.float64)


def regularized_v_rho(hessian: np.ndarray, ridge: float = MGCV_RHO_RIDGE) -> np.ndarray:
    """``Vrho = (H + ridge * I)^-1`` — see :data:`MGCV_RHO_RIDGE`."""
    m = hessian.shape[0]
    return np.asarray(np.linalg.inv(hessian + ridge * np.eye(m)), dtype=np.float64)


def wood_factor_and_derivative(
    information: np.ndarray, d_information: tuple[np.ndarray, ...]
) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    """The factor eq. (7) is actually written in, and its derivatives.

    **``V''`` is NOT invariant to the choice of square root, which the paper's
    ``R_rho^T R_rho = V_beta`` alone does not pin down.** Measured: swapping a
    plain Cholesky of ``V_beta`` for the symmetric square root moves ``V''`` by
    ~17% and the element-wise residual against ``mgcv`` from 26.7% to 21.2%. So
    the factor has to be the *specific* one ``mgcv`` builds, not any valid one.

    That factor comes from Wood (2011) section 3.3, which the 2016 paper
    explicitly reuses: it forms ``A = X^T W X + S_lambda`` and works with
    ``P = R^-1`` such that ``V_beta = P P^T``. A factor with ``G^T G = V_beta`` is
    therefore ``G = P^T = L^-1`` where ``A = L L^T`` — **lower** triangular, and a
    genuinely different square root from the upper-triangular Cholesky factor of
    ``V_beta`` itself.

    Measured, on ``poisson-log``: using this factor drops the element-wise
    residual against ``mgcv``'s own ``Vc - Vp`` from **26.7% to 1.87%**.

    Args:
        information: ``A = X^T W X + S_lambda``, ``(p, p)``.
        d_information: ``dA/drho_k`` per smoothing parameter.

    Returns:
        ``(G, (dG/drho_k, ...))``.
    """
    lower = np.linalg.cholesky(information)
    g = np.linalg.inv(lower)
    l_inv = g

    def d_lower(d_a: np.ndarray) -> np.ndarray:
        phi = l_inv @ ((d_a + d_a.T) / 2.0) @ l_inv.T
        phi = np.tril(phi)
        np.fill_diagonal(phi, np.diag(phi) / 2.0)
        return np.asarray(lower @ phi, dtype=np.float64)

    return g, tuple(-g @ d_lower(d_a) @ g for d_a in d_information)


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
    return np.asarray((out + out.T) / 2.0, dtype=np.float64)


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
    return np.asarray((out + out.T) / 2.0, dtype=np.float64)


def unconditional_covariance(
    v_beta: np.ndarray,
    design: np.ndarray,
    dbeta_drho: np.ndarray,
    dw_drho_all: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    log_lambda: np.ndarray,
    rho_hessian: np.ndarray,
    ridge: float = MGCV_RHO_RIDGE,
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
        rho_hessian: ``(M, M)`` — the Hessian of the REML criterion in ``rho``.
            Taken raw rather than pre-inverted **because the two terms need
            different inverses of it** (see the module docstring).
        ridge: the regularisation applied before inverting for the second-order
            term only. Defaults to :data:`MGCV_RHO_RIDGE`.
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
    if rho_hessian.shape != (m, m):
        raise PolarisValidationError(
            f"unconditional_covariance: rho_hessian is {rho_hessian.shape}, expected {(m, m)}."
        )

    # THE ASYMMETRY, measured (see the module docstring): the first-order term
    # uses the UNREGULARISED inverse Hessian, the second-order term the ridged
    # one. Identified on two cases and then held on five independent held-out
    # ones, worst element-wise residual 0.730%.
    v_rho_first = np.linalg.inv(rho_hessian)
    v_rho_second = regularized_v_rho(rho_hessian, ridge)

    first_order = dbeta_drho.T @ v_rho_first @ dbeta_drho

    lam = np.exp(log_lambda)
    information = np.linalg.inv(v_beta)
    d_information = tuple(
        design.T @ (dw_drho_all[k][:, None] * design) + lam[k] * penalties[k] for k in range(m)
    )
    try:
        _, d_factor = wood_factor_and_derivative(information, d_information)
    except np.linalg.LinAlgError as exc:
        raise PolarisComputationError(
            "unconditional_covariance: X^T W X + S_lambda is not positive "
            "definite, so Wood (2011) 3.3's factor does not exist. The paper's "
            "own remedy is the negative-weight machinery of that section, which "
            "is not derived here."
        ) from exc

    return UncertaintyCorrection(
        v_beta=v_beta,
        first_order=(first_order + first_order.T) / 2.0,
        second_order=second_order_correction(d_factor, v_rho_second),
    )

"""Exact Hessian of the REML score in natural-log ``rho`` — outer-solver epic,
Slice 2 (``docs/PLAN_wood_outer_solver.md``).

Slice 1's Newton search differenced the analytic gradient (``2 x free`` extra
penalized fits per iteration). This module differentiates the gradient
analytically instead, from Wood (2011) §3.4-3.5 / Appendix C-D, never
transcribed from ``mgcv`` (GPL; this project is MIT).

**The derivation.** Write ``A_j = lambda_j S_j`` (so ``dA_j/drho_k = delta_jk A_j``),
``H = X'WX + sum_j A_j`` with ``W`` the OBSERVED weight (``alpha * w_Fisher``),
and ``b_j = d beta_hat/d rho_j``. The gradient this module differentiates is
(``gam_reml_gradient``)::

    g_j = beta'A_j beta / (2 s) + 1/2 tr(H^-1 H_j) - 1/2 d log|S|+ / d rho_j,
    H_j = dH/drho_j = A_j + X' diag(w' * u_j) X,   u_j = X b_j

with ``w' = dw/deta`` (observed weight,
:func:`~polaris_re.analytics.gam_derivatives.dw_deta_observed`) and ``s`` the scale.
Implicit differentiation of the penalized stationarity
condition at ``beta_hat`` (Wood Appendix C — the matrix that appears is the
OBSERVED Hessian ``H``) gives ``b_j = -H^-1 A_j beta`` and, differentiating
``H b_j = -A_j beta`` once more,::

    b_jk = -H^-1 [ H_k b_j + A_j b_k + delta_jk A_j beta ].

Differentiating ``g_j`` in ``rho_k``, term by term::

    d/drho_k [beta'A_j beta/(2 s)] = delta_jk beta'A_j beta/(2 s) - beta'A_j H^-1 A_k beta / s
    d/drho_k [1/2 tr(H^-1 H_j)]    = 1/2 [ tr(H^-1 H_jk) - tr(H^-1 H_j H^-1 H_k) ]
    H_jk = delta_jk A_j + X' diag( w'' u_j u_k + w' u_jk ) X,   u_jk = X b_jk
    d²log|S|+ / drho_j drho_k      = delta_jk lambda_j tr(S+ S_j)
                                      - lambda_j lambda_k tr(S+ S_j S+ S_k)

so the new ingredient over the gradient is ``w'' = d²w/deta²`` of the observed
weight. It is built by truncated Taylor-series arithmetic in ``t`` (``eta =
eta_0 + t``) on the link's inverse and the family's variance polynomial
(:func:`d2w_deta2_observed`): ``alpha`` needs ``d²mu/deta²`` and so ``mu`` to
fourth order, and the series recursions are the links' own ODEs
(``mu' = mu(1-mu)`` for logit, ``mu' = e^eta (1-mu)`` for cloglog). Verified
against a central difference of the independently-derived
:func:`~polaris_re.analytics.gam_derivatives.dw_deta_observed` — a different
derivation of the same quantity, one order down.

**Free scale.** The free-scale criterion is the known-scale one profiled over
``phi``: ``V(rho) = min_phi V(rho, phi)`` with ``V_phi = 0`` at ``phi_hat``.
The profile Hessian is the Schur complement
``V_rr - V_rp V_pp^-1 V_pr`` with ``V_pp = (n - Mp)/(2 phi^2)`` and
``V_{rho_j, phi} = -beta'A_j beta/(2 phi^2)``, i.e. the known-scale Hessian at
``s = phi_hat`` minus ``(beta'A_j beta)(beta'A_k beta) / (2 phi^2 (n - Mp))``.
Slice 1's gradient was verified, not assumed, by central difference; this is
verified the same way (``tests/test_analytics/test_gam_reml_hessian.py``).
"""

import numpy as np
import scipy.linalg

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_reml import penalty_block_square_roots
from polaris_re.analytics.gam_reml_appendix_b import appendix_b_transform
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "d2log_det_s_plus_drho2",
    "d2w_deta2_observed",
    "reml_score_hessian",
    "reml_score_hessian_profiled",
]

_ORDER = 4
"""Taylor order carried for ``mu(eta_0 + t)``: ``alpha`` contains ``d²mu/deta²``
and ``w''`` differentiates it twice more."""


def _mul(a: np.ndarray, b: np.ndarray, order: int) -> np.ndarray:
    """Truncated-series product, coefficient arrays ``(order + 1, n)``."""
    out = np.zeros((order + 1, a.shape[1]), dtype=np.float64)
    for i in range(order + 1):
        for j in range(order + 1 - i):
            out[i + j] += a[i] * b[j]
    return out


def _inv(a: np.ndarray, order: int) -> np.ndarray:
    """Truncated-series reciprocal ``1/a`` (``a[0] != 0``)."""
    out = np.zeros_like(a[: order + 1], dtype=np.float64)
    out[0] = 1.0 / a[0]
    for k in range(1, order + 1):
        acc = np.zeros(a.shape[1], dtype=np.float64)
        for j in range(1, k + 1):
            acc += a[j] * out[k - j]
        out[k] = -acc * out[0]
    return out


def _deriv(a: np.ndarray) -> np.ndarray:
    """``d/dt`` of a series: one order shorter."""
    return np.asarray(a[1:] * np.arange(1, a.shape[0], dtype=np.float64)[:, None], dtype=np.float64)


def _mu_series(family: Family, eta: np.ndarray) -> np.ndarray:
    """``mu(eta_0 + t)`` as a series to ``_ORDER`` from the link's own ODE."""
    n = eta.shape[0]
    mu0 = family.link.linkinv(eta)
    c = np.zeros((_ORDER + 1, n), dtype=np.float64)
    c[0] = mu0
    name = family.link.name
    if name == "identity":
        c[0] = eta
        c[1] = 1.0
        return c
    if name == "log":
        fact = 1.0
        for k in range(1, _ORDER + 1):
            fact *= k
            c[k] = mu0 / fact
        return c
    if name == "logit":
        for k in range(_ORDER):
            mu_sq_k = sum(c[i] * c[k - i] for i in range(k + 1))
            c[k + 1] = (c[k] - mu_sq_k) / (k + 1)
        return c
    if name == "cloglog":
        g = np.zeros((_ORDER + 1, n), dtype=np.float64)
        fact = 1.0
        g[0] = np.exp(eta)
        for k in range(1, _ORDER + 1):
            fact *= k
            g[k] = g[0] / fact
        for k in range(_ORDER):
            # [g (1 - mu)]_k = g_k - sum_i g_i mu_{k-i}
            prod_k = sum(g[i] * c[k - i] for i in range(k + 1))
            c[k + 1] = (g[k] - prod_k) / (k + 1)
        return c
    raise PolarisValidationError(
        f"gam_reml_hessian: no series recorded for link {name!r}. Add its ODE rather "
        "than differencing numerically (CLAUDE.md: do not guess at a derivation)."
    )


def _variance_series(family: Family, mu: np.ndarray, order: int) -> tuple[np.ndarray, np.ndarray]:
    """``V(mu(t))`` and ``V'(mu(t))`` as series; ``V`` is at most quadratic here."""
    n = mu.shape[1]
    ones = np.zeros((order + 1, n), dtype=np.float64)
    ones[0] = 1.0
    m = mu[: order + 1]
    if family.name == "gaussian":
        return ones, np.zeros_like(ones)
    if family.name in ("poisson", "quasipoisson"):
        return m.copy(), ones
    if family.name == "binomial":
        return m - _mul(m, m, order), ones - 2.0 * m
    raise PolarisValidationError(
        f"gam_reml_hessian: no variance series recorded for family {family.name!r}."
    )


def d2w_deta2_observed(
    family: Family,
    y: np.ndarray,
    eta: np.ndarray,
    prior_weights: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(w, dw/deta, d²w/deta²)`` of the OBSERVED weight ``w = alpha * omega m²/V``.

    Series arithmetic in ``t`` (``eta = eta_0 + t``): ``w(t) = alpha(t) F(t)``,
    ``alpha = 1 + (y - mu)(V'/V - m'/m²)``, ``F = omega m²/V``, ``m = dmu/deta``;
    the Taylor coefficients give ``w' = c_1`` and ``w'' = 2 c_2``. ``dw/deta``
    returned here is a by-product that must equal
    :func:`~polaris_re.analytics.gam_derivatives.dw_deta_observed` (a separate
    closed-form derivation) — the tests pin that.
    """
    y = np.asarray(y, dtype=np.float64)
    eta = np.asarray(eta, dtype=np.float64)
    n = eta.shape[0]
    omega = (
        np.ones(n, dtype=np.float64)
        if prior_weights is None
        else np.asarray(prior_weights, dtype=np.float64)
    )
    mu = _mu_series(family, eta)  # order 4
    m = _deriv(mu)  # order 3
    m_prime = _deriv(m)  # order 2
    order = 2
    v, v_prime = _variance_series(family, mu, order)
    m2 = m[: order + 1]
    m_sq = _mul(m2, m2, order)
    inv_v = _inv(v, order)
    fisher = omega[None, :] * _mul(m_sq, inv_v, order)
    b = _mul(v_prime, inv_v, order) - _mul(m_prime[: order + 1], _inv(m_sq, order), order)
    resid = -mu[: order + 1].copy()
    resid[0] += y
    alpha = _mul(resid, b, order)
    alpha[0] += 1.0
    w = _mul(alpha, fisher, order)
    return w[0], w[1], 2.0 * w[2]


def d2log_det_s_plus_drho2(blocks: tuple[np.ndarray, ...], lambdas: np.ndarray) -> np.ndarray:
    """``d²log|S|+/drho_j drho_k``, i.e.
    ``delta_jk lambda_j tr(S+ S_j) - lambda_j lambda_k tr(S+ S_j S+ S_k)``.

    Same stable route as
    :func:`~polaris_re.analytics.gam_reml_appendix_b.dlogdet_s_plus_drho`:
    ``S+ = V Sigma^-2 V'`` from Appendix B's own ``e`` (never an eigen-cut of the
    raw ``S``), so with ``B_j = Sigma^-1 V' S_j V Sigma^-1`` the trace of the
    product is ``tr(B_j B_k)``. Valid while the rank of ``S`` is constant in
    ``rho`` (the structural null space), which is what Appendix B's rank
    decision assumes.
    """
    m = len(blocks)
    e = appendix_b_transform(blocks, lambdas).e
    if e.shape[0] == 0:
        return np.zeros((m, m), dtype=np.float64)
    _u, sigma, vt = np.linalg.svd(e, full_matrices=False)
    v = vt.T
    inv_sigma = 1.0 / sigma
    b_mats = [inv_sigma[:, None] * (v.T @ block @ v) * inv_sigma[None, :] for block in blocks]
    out = np.zeros((m, m), dtype=np.float64)
    for j in range(m):
        for k in range(m):
            out[j, k] = -lambdas[j] * lambdas[k] * float(np.sum(b_mats[j] * b_mats[k].T))
        out[j, j] += lambdas[j] * float(np.trace(b_mats[j]))
    return out


def _hessian_at_scale(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    coef: np.ndarray,
    penalty_blocks: tuple[np.ndarray, ...],
    lambdas: np.ndarray,
    *,
    offset: np.ndarray | None,
    weights: np.ndarray | None,
    scale: float,
    profile_df: float | None,
    penalty_sqrt_blocks: tuple[np.ndarray, ...] | None = None,
) -> np.ndarray:
    """The Hessian with the penalized deviance divided by ``scale``; when
    ``profile_df`` (``n - Mp``) is given, the free-scale Schur correction."""
    n = y.shape[0]
    offset = np.zeros(n, dtype=np.float64) if offset is None else np.asarray(offset)
    weights = np.ones(n, dtype=np.float64) if weights is None else np.asarray(weights)
    coef = np.asarray(coef, dtype=np.float64)
    lambdas = np.asarray(lambdas, dtype=np.float64)
    m = len(penalty_blocks)

    a_mats = [lam * block for lam, block in zip(lambdas, penalty_blocks, strict=True)]
    penalty = np.zeros_like(a_mats[0])
    for a_j in a_mats:
        penalty = penalty + a_j

    eta = offset + x @ coef
    w_obs = family.observed_information_weight(y, eta, weights)
    hessian = x.T @ (w_obs[:, None] * x) + penalty
    h_inv = scipy.linalg.cho_solve(
        scipy.linalg.cho_factor(hessian, lower=True), np.eye(hessian.shape[0])
    )
    _w0, w1, w2 = d2w_deta2_observed(family, y, eta, weights)

    sqrt_blocks = (
        penalty_sqrt_blocks
        if penalty_sqrt_blocks is not None
        else penalty_block_square_roots(penalty_blocks)
    )
    # Outer-solver Slice 3 (ADR-244): A_j beta and beta' A_j beta through each
    # block's own root — L_j (L_j' beta) and ||L_j' beta||^2 — never by
    # contracting the formed matrix with `coef`, for the reason the gradient's
    # term 1 and the score's penalty term (ADR-223) already give: at a 1e11
    # `lambda_j` the formed contraction carries ~1e-5 of absolute error.
    a_beta = np.stack(
        [lam * (root @ (root.T @ coef)) for lam, root in zip(lambdas, sqrt_blocks, strict=True)],
        axis=1,
    )  # (p, M)
    b_first = -(h_inv @ a_beta)  # (p, M): b_j = -H^-1 A_j beta
    u_first = x @ b_first  # (n, M)
    # H_j = A_j + X' diag(w' u_j) X
    h_first = [a_mats[j] + x.T @ ((w1 * u_first[:, j])[:, None] * x) for j in range(m)]
    hat_diag = np.einsum("np,pq,nq->n", x, h_inv, x)
    p_mats = [h_inv @ h_first[j] for j in range(m)]

    d2_logdet_s = d2log_det_s_plus_drho2(penalty_blocks, lambdas)
    q = np.array(
        [
            lam * float(np.sum((root.T @ coef) ** 2))
            for lam, root in zip(lambdas, sqrt_blocks, strict=True)
        ],
        dtype=np.float64,
    )

    out = np.zeros((m, m), dtype=np.float64)
    for j in range(m):
        for k in range(j, m):
            # Term 1: d/drho_k [beta'A_j beta / (2 s)]
            t1 = -float(a_beta[:, j] @ h_inv @ a_beta[:, k]) / scale
            if j == k:
                t1 += q[j] / (2.0 * scale)
            # b_jk = -H^-1 [ H_k b_j + A_j b_k + delta_jk A_j beta ]
            rhs = h_first[k] @ b_first[:, j] + a_mats[j] @ b_first[:, k]
            if j == k:
                rhs = rhs + a_beta[:, j]
            u_second = x @ (-(h_inv @ rhs))
            # tr(H^-1 H_jk), H_jk = delta_jk A_j + X' diag(w'' u_j u_k + w' u_jk) X
            wd = w2 * u_first[:, j] * u_first[:, k] + w1 * u_second
            tr_hjk = float(np.sum(hat_diag * wd))
            if j == k:
                tr_hjk += float(np.sum(h_inv * a_mats[j]))
            tr_prod = float(np.sum(p_mats[j] * p_mats[k].T))
            t2 = 0.5 * (tr_hjk - tr_prod)
            t4 = -0.5 * d2_logdet_s[j, k]
            val = t1 + t2 + t4
            if profile_df is not None:
                val -= q[j] * q[k] / (2.0 * scale**2 * profile_df)
            out[j, k] = val
            out[k, j] = val
    return out


def reml_score_hessian(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    coef: np.ndarray,
    penalty_blocks: tuple[np.ndarray, ...],
    lambdas: np.ndarray,
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
    penalty_sqrt_blocks: tuple[np.ndarray, ...] | None = None,
) -> np.ndarray:
    """``d²V/drho_j drho_k`` of the KNOWN-scale criterion
    (:func:`~polaris_re.analytics.gam_reml.reml_score_general`), natural-log
    ``rho``, ``(M, M)`` symmetric. Arguments are exactly
    :func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient`'s.

    Raises:
        PolarisValidationError: free-scale family, non-positive ``gamma``,
            empty/mismatched ``penalty_blocks``.
    """
    if not family.dispersion_fixed:
        raise PolarisValidationError(
            f"reml_score_hessian: family {family.name!r} estimates its dispersion — "
            "use reml_score_hessian_profiled."
        )
    if gamma <= 0.0:
        raise PolarisValidationError(f"gamma must be positive, got {gamma}.")
    _validate_blocks("reml_score_hessian", penalty_blocks, lambdas)
    return _hessian_at_scale(
        y,
        x,
        family,
        coef,
        penalty_blocks,
        lambdas,
        offset=offset,
        weights=weights,
        scale=gamma,
        profile_df=None,
        penalty_sqrt_blocks=penalty_sqrt_blocks,
    )


def reml_score_hessian_profiled(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    coef: np.ndarray,
    penalty_blocks: tuple[np.ndarray, ...],
    lambdas: np.ndarray,
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    penalty_sqrt_blocks: tuple[np.ndarray, ...] | None = None,
) -> np.ndarray:
    """Hessian of the FREE-SCALE criterion (``phi`` profiled out) in natural-log
    ``rho``: the known-scale Hessian at ``s = phi_hat`` less the Schur term
    ``(beta'A_j beta)(beta'A_k beta) / (2 phi_hat² (n - Mp))`` (module docstring).
    """
    if family.dispersion_fixed:
        raise PolarisValidationError(
            f"reml_score_hessian_profiled: family {family.name!r} has a fixed "
            "dispersion — use reml_score_hessian."
        )
    _validate_blocks("reml_score_hessian_profiled", penalty_blocks, lambdas)
    n = y.shape[0]
    offset_vec = np.zeros(n, dtype=np.float64) if offset is None else np.asarray(offset)
    weights_vec = np.ones(n, dtype=np.float64) if weights is None else np.asarray(weights)
    coef = np.asarray(coef, dtype=np.float64)
    lambdas = np.asarray(lambdas, dtype=np.float64)
    mu = family.link.linkinv(offset_vec + x @ coef)
    deviance = family.deviance(y, mu, weights_vec)
    sqrt_blocks = (
        penalty_sqrt_blocks
        if penalty_sqrt_blocks is not None
        else penalty_block_square_roots(penalty_blocks)
    )
    penalized_deviance = deviance + sum(
        lam * float(np.sum((root.T @ coef) ** 2))
        for lam, root in zip(lambdas, sqrt_blocks, strict=True)
    )
    null_space_dim = float(x.shape[1] - appendix_b_transform(penalty_blocks, lambdas).rank)
    residual_df = float(n) - null_space_dim
    if residual_df <= 0.0:
        raise PolarisValidationError(
            f"reml_score_hessian_profiled: n={n} does not exceed Mp={null_space_dim:.1f}."
        )
    return _hessian_at_scale(
        y,
        x,
        family,
        coef,
        penalty_blocks,
        lambdas,
        offset=offset,
        weights=weights,
        scale=penalized_deviance / residual_df,
        profile_df=residual_df,
        penalty_sqrt_blocks=sqrt_blocks,
    )


def _validate_blocks(
    name: str, penalty_blocks: tuple[np.ndarray, ...], lambdas: np.ndarray
) -> None:
    if not penalty_blocks:
        raise PolarisValidationError(f"{name}: penalty_blocks must be non-empty.")
    if len(lambdas) != len(penalty_blocks):
        raise PolarisValidationError(
            f"{name}: lambdas has {len(lambdas)} entries, but {len(penalty_blocks)} "
            "penalty_blocks were supplied — one lambda per block."
        )

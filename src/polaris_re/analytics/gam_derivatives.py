"""Derivatives of the penalized fit w.r.t. the log smoothing parameters.

Wood (2011) §3.4 and Appendix D — ``docs/WORK_ORDER_dw_drho_wood2011.md``.

**Why this module exists.** ADR-190 re-scoped the level-4 Kass-Steffey blocker from
"find the bug in our arithmetic" (there is none — two tests pin that arithmetic) to
"implement Wood, Pya & Säfken (2016)'s correction", and named the blocking
ingredient exactly:

    "it needs ``dw/drho``, which nothing in the fitter currently computes."

This module computes it. **It does not close level 4** and nothing here may be
reported as doing so: Wood (2011) derives ``dw/drho`` because the REML *Newton
iteration* needs it, and contains no unconditional-covariance formula at all
(searched: zero occurrences of "unconditional"). How ``dw/drho`` assembles into
``Vc`` is the 2016 paper's own contribution and is still outstanding.

The construction, and where each piece comes from
--------------------------------------------------
Given a converged penalized fit with working weights ``W``, coefficients ``β̂``,
and penalty blocks ``Sⱼ`` scaled by ``λⱼ = e^rhoⱼ``:

1. **``dβ̂/drhoⱼ = -λⱼ (XᵀWX + S)⁻¹ Sⱼ β̂``** — Wood (2011) §3.4, which writes it as
   ``-e^rhoⱼ PPᵀ Sⱼ β̂`` where ``PPᵀ = (XᵀWX + S)⁻¹`` (§3.3). **The paper's ``PPᵀ``
   factorisation is numerical-stability machinery for the ill-conditioned /
   negative-weight case, not extra mathematical content**, so a direct solve is
   mathematically identical. Recorded so a later reader does not mistake the
   simplification for a deviation from the source.

2. **``dηᵢ/drhoⱼ = Xᵢ dβ̂/drhoⱼ``** — §3.4. This is the quantity compared against
   ``mgcv``, because it is basis-invariant where ``β̂`` is not (PLAN Anchor 2).

3. **``dwᵢ/dηᵢ = (wᵢ/gᵢ')(alphaᵢ'/alphaᵢ - Vᵢ'/Vᵢ - 2gᵢ''/gᵢ')``** — Appendix D, primes
   denoting ``d/dμᵢ``. See :func:`dw_deta` for the ``alpha ≡ 1`` specialisation this
   engine's Fisher-weighted IRLS requires, and why.

4. **``dwᵢ/drhoⱼ = (dwᵢ/dηᵢ)(dηᵢ/drhoⱼ)``** — Appendix D's closing line.

Fisher versus Newton — measured, then resolved
-----------------------------------------------
Wood derives ``dβ̂/drho`` by implicit differentiation of the penalized-deviance
stationarity condition (Appendix C); the inverse appearing there is
``[∂²Dp/∂β∂βᵀ]⁻¹``, the **observed (Newton)** Hessian. That is why the paper's
weights carry the ``alphaᵢ`` factor.

:func:`~polaris_re.analytics.gam_fit.penalized_irls_general` uses **Fisher**
weights (``ω·(dμ/dη)²/V(μ)``, no ``alpha``). That is correct for the *fit* — Fisher
scoring and Newton converge to the same ``β̂``, differing in the step, not the
fixed point — but it is **not** the matrix the derivative needs.

Measured before the fix, against a central difference of this engine's own refits:

===================  ==============  =========================  ==========================
cell                 ``max|alpha - 1|``  ``dη/drho`` w/ Fisher ``W``   ``dη/drho`` w/ Newton ``W``
===================  ==============  =========================  ==========================
``poisson-log``      6.7e-16         6.6e-12                    6.6e-12
``binomial-logit``   0.0 (exact)     2.7e-11                    2.7e-11
``binomial-cloglog`` 4.3e-03         **6.9e-06**                **1.1e-11**
===================  ==============  =========================  ==========================

So: ``alpha`` is identically 1 on the canonical links (an independent confirmation of
:func:`newton_alpha`'s algebra, since nothing forced that), the two Hessians
coincide there, and the whole discrepancy on the non-canonical cell is the missing
``alpha``. Supplying :func:`newton_working_weights` to :func:`d_beta_d_rho` closes it
to the same finite-difference floor as the canonical cells.

**The fitter is untouched** (Anchor 7; its Fisher choice is verified behaviour,
ADR-195). Only the derivative's Hessian changed, which is what the paper's own
derivation calls for. Callers must pass Newton weights — see
:func:`d_beta_d_rho`'s ``irls_weights`` argument.
"""

import numpy as np

from polaris_re.analytics.gam_family import Family
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "d_beta_d_rho",
    "d_eta_d_rho",
    "dw_deta",
    "dw_drho",
    "newton_alpha",
    "newton_working_weights",
    "second_deriv_mu_eta",
    "variance_deriv",
]


def _as_2d_blocks(penalties: tuple[np.ndarray, ...], p: int) -> tuple[np.ndarray, ...]:
    for j, block in enumerate(penalties):
        if block.shape != (p, p):
            raise PolarisValidationError(
                f"gam_derivatives: penalty block {j} is {block.shape} but the design "
                f"has {p} column(s); every Sⱼ must be (p, p)."
            )
    return penalties


def d_beta_d_rho(
    x: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    irls_weights: np.ndarray,
    coef: np.ndarray,
    log_lambda: np.ndarray,
) -> np.ndarray:
    """``dβ̂/drhoⱼ`` — Wood (2011) §3.4, one row per penalty block.

    ``dβ̂/drhoⱼ = -λⱼ (XᵀWX + S)⁻¹ Sⱼ β̂`` with ``S = Σⱼ λⱼ Sⱼ``.

    **Not a compared quantity** (PLAN Anchor 2 — coefficients are basis-dependent
    and ``mgcv`` reparameterises). :func:`d_eta_d_rho` is the comparable image of
    this and is what the conformance claim declares.

    Args:
        x: design matrix, ``(n, p)``.
        penalties: the penalty blocks ``Sⱼ``, each ``(p, p)``, in the same order
            as ``log_lambda``.
        irls_weights: the converged working weights ``w``, ``(n,)``. **Must be the
            observed-Hessian (Newton) weights** from
            :func:`newton_working_weights`, not the fitter's Fisher weights — see
            that function and the module docstring. Passing Fisher weights is
            silently correct on a canonical link (the two coincide, ``alpha ≡ 1``) and
            wrong by ~5 orders of magnitude on a non-canonical one, which is the
            worst failure mode available and the reason this is stated here rather
            than left to the caller to infer.
        coef: the converged coefficients ``β̂``, ``(p,)``.
        log_lambda: ``rho = log(λ)`` per block, ``(M,)`` — natural log, matching the
            paper's ``rhoⱼ = log(λⱼ)``.

    Returns:
        ``(M, p)`` — row ``j`` is ``dβ̂/drhoⱼ``.
    """
    x = np.asarray(x, dtype=np.float64)
    coef = np.asarray(coef, dtype=np.float64)
    irls_weights = np.asarray(irls_weights, dtype=np.float64)
    log_lambda = np.atleast_1d(np.asarray(log_lambda, dtype=np.float64))
    n, p = x.shape
    if len(penalties) != log_lambda.shape[0]:
        raise PolarisValidationError(
            f"gam_derivatives: {len(penalties)} penalty block(s) but "
            f"{log_lambda.shape[0]} log-lambda value(s); one per block is required."
        )
    if irls_weights.shape != (n,):
        raise PolarisValidationError(
            f"gam_derivatives: irls_weights has shape {irls_weights.shape}, expected {(n,)}."
        )
    if coef.shape != (p,):
        raise PolarisValidationError(
            f"gam_derivatives: coef has shape {coef.shape}, expected {(p,)}."
        )
    _as_2d_blocks(penalties, p)

    lam = np.exp(log_lambda)
    s_total = np.zeros((p, p), dtype=np.float64)
    for lam_j, block in zip(lam, penalties, strict=True):
        s_total = s_total + lam_j * block

    hessian = x.T @ (irls_weights[:, None] * x) + s_total
    out = np.empty((log_lambda.shape[0], p), dtype=np.float64)
    for j, (lam_j, block) in enumerate(zip(lam, penalties, strict=True)):
        rhs = -lam_j * (block @ coef)
        try:
            out[j] = np.linalg.solve(hessian, rhs)
        except np.linalg.LinAlgError as exc:  # pragma: no cover - guarded, not expected
            raise PolarisComputationError(
                "gam_derivatives: (XᵀWX + S) is singular, so dβ̂/drho is not defined. "
                "Wood (2011) §3.3 handles this with a pseudoinverse; this engine's "
                "fixtures are full rank and this path is not derived."
            ) from exc
    return out


def d_eta_d_rho(
    x: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    irls_weights: np.ndarray,
    coef: np.ndarray,
    log_lambda: np.ndarray,
) -> np.ndarray:
    """``dη/drhoⱼ = X dβ̂/drhoⱼ`` — Wood (2011) §3.4.

    **The compared quantity** of this module's parity claim: basis-invariant where
    ``β̂`` is not, so it survives ``mgcv``'s internal reparameterisation (PLAN
    Anchor 2). Arguments are :func:`d_beta_d_rho`'s.

    Returns:
        ``(M, n)`` — row ``j`` is ``dη/drhoⱼ`` over the data.
    """
    return (
        d_beta_d_rho(x, penalties, irls_weights, coef, log_lambda)
        @ np.asarray(x, dtype=np.float64).T
    )


def second_deriv_mu_eta(link_name: str, eta: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """``d²μ/dη²`` — the analytic second derivative of the inverse link.

    :class:`~polaris_re.analytics.gam_family.Link` carries ``linkinv`` and
    ``mu_eta`` only, so this lives here rather than being bolted onto that
    already-verified class (PLAN Anchor 7). Derived per link rather than
    differenced, so :func:`dw_deta` is analytic throughout — the finite-difference
    check in the tests is then an independent check *of* this, not its definition.

    - ``log``: ``μ = e^η`` so ``dμ/dη = d²μ/dη² = μ``.
    - ``logit``: ``dμ/dη = μ(1-μ)`` so ``d²μ/dη² = μ(1-μ)(1-2μ)``.
    - ``cloglog``: ``μ = 1 - exp(-e^η)``, ``dμ/dη = e^(η-e^η)``, so
      ``d²μ/dη² = e^(η-e^η)(1 - e^η) = (dμ/dη)(1 - e^η)``.
    """
    eta = np.asarray(eta, dtype=np.float64)
    mu = np.asarray(mu, dtype=np.float64)
    if link_name == "log":
        return mu
    if link_name == "logit":
        return mu * (1.0 - mu) * (1.0 - 2.0 * mu)
    if link_name == "cloglog":
        exp_eta = np.exp(eta)
        return np.asarray(np.exp(eta - exp_eta) * (1.0 - exp_eta), dtype=np.float64)
    raise PolarisValidationError(
        f"gam_derivatives.second_deriv_mu_eta: no derivation recorded for link "
        f"{link_name!r}. Add it from the link definition rather than differencing "
        "numerically (CLAUDE.md: do not guess at a derivation)."
    )


def variance_deriv(family_name: str, mu: np.ndarray) -> np.ndarray:
    """``dV/dμ`` — the analytic derivative of the family variance function.

    - ``poisson`` / ``quasipoisson``: ``V = μ`` so ``V' = 1``.
    - ``binomial``: ``V = μ(1-μ)`` so ``V' = 1 - 2μ``.

    Quasi-Poisson shares Poisson's variance *function*; the dispersion ``φ`` scales
    ``V`` by a constant and so cancels out of Appendix D's ``V'/V`` ratio, which is
    why no ``φ`` appears here.
    """
    mu = np.asarray(mu, dtype=np.float64)
    if family_name in ("poisson", "quasipoisson"):
        return np.ones_like(mu)
    if family_name == "binomial":
        return 1.0 - 2.0 * mu
    raise PolarisValidationError(
        f"gam_derivatives.variance_deriv: no derivation recorded for family {family_name!r}."
    )


def newton_alpha(family: Family, y: np.ndarray, eta: np.ndarray, mu: np.ndarray) -> np.ndarray:
    """Wood (2011) §3.2's ``alphaᵢ`` — the factor turning a Fisher weight into a Newton one.

    The paper writes it in the ``μ``-parameterisation::

        alphaᵢ = 1 + (yᵢ - μᵢ)(Vᵢ'/Vᵢ + gᵢ''/gᵢ')

    with primes ``d/dμ``. This codebase carries ``m ≡ dμ/dη`` (:meth:`Link.mu_eta`)
    rather than ``gᵢ' = dη/dμ``, so the change of variable is done once, here, rather
    than reconstructing ``g`` from reciprocals. Since ``gᵢ' = 1/m``::

        gᵢ'' = d/dμ (1/m) = -(1/m²)(dm/dμ) = -(1/m²)(m'/m) = -m'/m³
        gᵢ''/gᵢ' = (-m'/m³)·m = -m'/m²

    giving ``alphaᵢ = 1 + (yᵢ - μᵢ)(V'/V - m'/m²)``, with ``m' = d²μ/dη²``.

    **This is identically 1 for a canonical link** — the paper says so, and the
    algebra shows it: for Poisson-log, ``V'/V = 1/μ`` and ``m'/m² = μ/μ² = 1/μ``;
    for binomial-logit both equal ``(1-2μ)/(μ(1-μ))``. It departs from 1 only for
    non-canonical links (binomial-cloglog here), which is exactly where Fisher and
    Newton part company.
    """
    y = np.asarray(y, dtype=np.float64)
    eta = np.asarray(eta, dtype=np.float64)
    mu = np.asarray(mu, dtype=np.float64)
    m = family.link.mu_eta(eta)
    m_prime = second_deriv_mu_eta(family.link.name, eta, mu)
    variance = family.variance(mu)
    v_prime = variance_deriv(family.name, mu)
    return np.asarray(1.0 + (y - mu) * (v_prime / variance - m_prime / m**2), dtype=np.float64)


def newton_working_weights(
    family: Family,
    y: np.ndarray,
    eta: np.ndarray,
    mu: np.ndarray,
    prior_weights: np.ndarray | None = None,
) -> np.ndarray:
    """The **observed-Hessian** working weights, ``wᵢ = ωᵢalphaᵢ/(Vᵢgᵢ'²) = alphaᵢ · wᵢ^Fisher``.

    **Why the derivative needs these even though the fit does not.** Fisher scoring
    and Newton converge to the *same* ``β̂`` — both solve ``∇βDp = 0``; they differ
    in the Hessian used to *step*, not in the fixed point. But ``dβ̂/drho`` comes from
    implicit differentiation *at* that fixed point (Wood Appendix C), and the matrix
    appearing there is the true ``∂²Dp/∂β∂βᵀ`` — the **observed** Hessian. So the
    correct ``dβ̂/drho`` uses ``XᵀW_Newton X + S`` even when the fit that produced
    ``β̂`` used Fisher weights throughout.

    Measured, before this function existed: passing Fisher weights to
    :func:`d_beta_d_rho` reproduces a finite-difference ``dη/drho`` to ~1e-11 on both
    canonical cells and to only **1.5e-05** on binomial-cloglog — six orders worse,
    and entirely explained by ``alpha ≠ 1`` there. The fitter is untouched (Anchor 7,
    ADR-195); only the derivative's Hessian changes.
    """
    n = np.asarray(eta, dtype=np.float64).shape[0]
    prior_weights = (
        np.ones(n, dtype=np.float64)
        if prior_weights is None
        else np.asarray(prior_weights, dtype=np.float64)
    )
    m = family.link.mu_eta(np.asarray(eta, dtype=np.float64))
    variance = family.variance(np.asarray(mu, dtype=np.float64))
    fisher = prior_weights * m**2 / variance
    return np.asarray(newton_alpha(family, y, eta, mu) * fisher, dtype=np.float64)


def dw_deta(
    family: Family,
    eta: np.ndarray,
    mu: np.ndarray,
    prior_weights: np.ndarray | None = None,
) -> np.ndarray:
    """``dwᵢ/dηᵢ`` for the **Fisher** working weight — Wood (2011) Appendix D at ``alpha ≡ 1``.

    Appendix D gives, with primes denoting ``d/dμ``::

        dwᵢ/dηᵢ = (wᵢ/gᵢ')(alphaᵢ'/alphaᵢ - Vᵢ'/Vᵢ - 2gᵢ''/gᵢ')

    and notes *"setting ``alphaᵢ ≡ 1``, and its derivatives to zero, recovers Fisher
    scoring"* — which is this engine's IRLS (module docstring). Dropping the ``alpha``
    term and writing it in the ``η``-parameterisation this codebase already uses
    (``m ≡ dμ/dη = 1/gᵢ'``, which :meth:`Link.mu_eta` supplies directly)::

        w  = ω m² / V(μ)
        dw/dη = w (2 m'/m - V'(μ) m / V)

    where ``m' = d²μ/dη²``. The two forms are the same expression — ``gᵢ''/gᵢ'`` and
    ``m'/m`` differ by the sign and factor that the change of variable introduces —
    and this one avoids reconstructing ``gᵢ''`` from a reciprocal. Both were checked
    against a numerical derivative of ``w(η)`` before this was written.

    Args:
        family: the fitted :class:`~polaris_re.analytics.gam_family.Family`.
        eta: linear predictor at the fit, ``(n,)``.
        mu: fitted mean, ``(n,)``.
        prior_weights: ``ω``, ``(n,)``. Defaults to all-one.

    Returns:
        ``(n,)`` — ``dwᵢ/dηᵢ``.
    """
    eta = np.asarray(eta, dtype=np.float64)
    mu = np.asarray(mu, dtype=np.float64)
    n = eta.shape[0]
    prior_weights = (
        np.ones(n, dtype=np.float64)
        if prior_weights is None
        else np.asarray(prior_weights, dtype=np.float64)
    )
    m = family.link.mu_eta(eta)
    m_prime = second_deriv_mu_eta(family.link.name, eta, mu)
    variance = family.variance(mu)
    v_prime = variance_deriv(family.name, mu)
    w = prior_weights * m**2 / variance
    return np.asarray(w * (2.0 * m_prime / m - v_prime * m / variance), dtype=np.float64)


def dw_drho(
    family: Family,
    eta: np.ndarray,
    mu: np.ndarray,
    deta_drho: np.ndarray,
    prior_weights: np.ndarray | None = None,
) -> np.ndarray:
    """``dwᵢ/drhoⱼ = (dwᵢ/dηᵢ)(dηᵢ/drhoⱼ)`` — Wood (2011) Appendix D's closing line.

    The quantity ADR-190 named as the missing ingredient for the level-4
    correction. **On its own it does not close level 4** — see the module
    docstring.

    Args:
        family: the fitted family.
        eta: linear predictor at the fit, ``(n,)``.
        mu: fitted mean, ``(n,)``.
        deta_drho: ``(M, n)`` from :func:`d_eta_d_rho`.
        prior_weights: ``ω``, ``(n,)``. Defaults to all-one.

    Returns:
        ``(M, n)`` — row ``j`` is ``dw/drhoⱼ``.
    """
    deta_drho = np.asarray(deta_drho, dtype=np.float64)
    if deta_drho.ndim != 2 or deta_drho.shape[1] != eta.shape[0]:
        raise PolarisValidationError(
            f"gam_derivatives.dw_drho: deta_drho has shape {deta_drho.shape}, "
            f"expected (M, {eta.shape[0]})."
        )
    return np.asarray(
        dw_deta(family, eta, mu, prior_weights)[None, :] * deta_drho, dtype=np.float64
    )

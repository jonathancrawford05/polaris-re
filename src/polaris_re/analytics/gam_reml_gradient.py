"""Analytic gradient of the REML score — mgcv-parity engine, PLAN slice 7d.

``docs/PLAN_mgcv_parity_engine.md`` slice 7c Part 0 found that
:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`'s
own ``max_abs_log10_sp_diff = 1.48`` residual on the ``select=True`` 7-block
structure is **not reachable by any optimiser**: 2 of the 7 ``rho``
directions carry curvature indistinguishable from zero under
``reml_score_general`` at ``mgcv``'s own point. What remains real and
closable is narrower (ADR-219, carried into slice 7d): the search's own
``0.0141`` score gap on the **5 identified** directions, where blind
multistart does not reach the point our own criterion prefers, and a
``converged=False``-at-near-zero-gradient contradiction traced to SciPy's
finite-difference gradient sitting inside this objective's own noise floor
(ADR-212). Both are symptoms of the SAME cause: ``select_lambdas_continuous``
supplies no ``jac=``, so SciPy differences an 8-nested-penalized-IRLS-solve
objective at ``h = 1e-5`` and calls the result a gradient. This module is
that gradient, computed analytically instead.

**The formula, Wood (2011) §2 eq. (4) differentiated w.r.t. natural-log
``rhoⱼ = log(λⱼ)``, term by term:**

    dV/drhoⱼ =  λⱼ β̂ᵀSⱼβ̂ / (2·gamma)              # envelope theorem: the
                                                     # indirect dβ̂ term
                                                     # vanishes at the fit's
                                                     # own stationary point
             +  0.5 · tr(H⁻¹ λⱼSⱼ)
             +  0.5 · tr(H⁻¹ Xᵀ(dW/drhoⱼ)X)          # the OBSERVED weight's
                                                     # own derivative — see
                                                     # below, this is the term
                                                     # PLAN slice 7c Part 1
                                                     # left as an open question
             -  0.5 · λⱼ · tr(S⁺Sⱼ)                  # Appendix B, never a
                                                     # naive eigen-cut on the
                                                     # raw summed S

with ``H = XᵀWX + S`` the SAME observed-Hessian matrix
:func:`~polaris_re.analytics.gam_reml.reml_score_general` already forms
(``W`` from :meth:`~polaris_re.analytics.gam_family.Family.observed_information_weight`,
PLAN slice 5c Defect B) and ``S⁺`` from
:func:`~polaris_re.analytics.gam_reml_appendix_b.dlogdet_s_plus_drho`.

**Term 3, and why it could not be dropped.** PLAN slice 7c named a "cheap
check" before deriving anything: compare the gradient WITHOUT this term
against a high-quality central difference of ``reml_score_general`` itself
(which carries the true, un-approximated dependence of ``W`` on ``rho``,
since it refits at every perturbed point rather than differentiating
anything) at a point where finite differences are trustworthy. **Run on the
N=4 ``tests/fixtures/gam_reml_optimize_near_flat_direction.json`` fixture at
its own production-converged point** (``select_lambdas_continuous`` with the
default, ADR-212-derived step): omitting term 3 entirely leaves a residual
up to ``0.02`` in ``log10(lambda)`` units. Including the exact term
collapses that residual to ``~1.3e-5``-``1.9e-5`` — a factor of ~1,500 — so
the omitted term is three orders of magnitude larger than the residual that
remains once it is included, refuting the "``alphaᵢ - 1``'s mean-0 property
makes this negligible" hypothesis outright, not merely leaving it untested.
Approximating term 3 with the FISHER weight's own derivative
(:func:`~polaris_re.analytics.gam_derivatives.dw_drho`, ``alpha ≡ 1``) closes
most of the gap (residual ``~0.001``) but not all of it — the remainder is
exactly the missing ``d(alpha)/d(eta)`` chain PLAN slice 7c flagged as new
math. **Built and verified before being wired in here**
(:func:`~polaris_re.analytics.gam_derivatives.third_deriv_mu_eta`,
:func:`~polaris_re.analytics.gam_derivatives.variance_second_deriv`,
:func:`~polaris_re.analytics.gam_derivatives.dalpha_deta`, each checked
against a central difference of the function one order below it on all
three link/family combinations this codebase defines, before either was
composed into :func:`~polaris_re.analytics.gam_derivatives.dw_deta_observed`/
:func:`~polaris_re.analytics.gam_derivatives.dw_drho_observed`) — this module
wires the EXACT term in, not the Fisher approximation. See the slice 7d ADR
for the full before/after numbers on the N=4 fixture.

Implemented from Wood (2011) directly (§2 eq. 4, differentiated; the
pseudo-determinant identity Appendix C states; Appendix D for ``dW/drho``),
not transcribed from ``mgcv``'s source — same footing as every other module
in this epic that touches Wood's formulas (Anchor 8's companion licensing
rule: ``mgcv`` is GPL(>=2), this project is MIT).
"""

import numpy as np
import scipy.linalg

from polaris_re.analytics.gam_derivatives import d_eta_d_rho, dw_drho_observed
from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_reml_appendix_b import dlogdet_s_plus_drho
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["reml_score_gradient"]


def reml_score_gradient(
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
) -> np.ndarray:
    """``dV/drhoⱼ`` for :func:`~polaris_re.analytics.gam_reml.reml_score_general`,
    natural-log ``rho`` — all four terms of the module docstring's formula,
    including the exact (not Fisher-approximated) ``dW/drho`` term.

    Args:
        y, x, family, coef, penalty_blocks, lambdas, offset, weights, gamma:
            exactly :func:`~polaris_re.analytics.gam_reml.reml_score_general`'s
            own arguments — this function evaluates the SAME criterion's
            gradient at the SAME point, so accepting a different signature
            would let the two silently drift apart.

    Returns:
        ``(len(penalty_blocks),)`` — ``dV/drhoⱼ``, one entry per block, in
        the same order as ``penalty_blocks``/``lambdas``. Natural-log
        ``rho``: a caller optimizing in ``log10(lambda)`` (e.g.
        :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`)
        must scale by ``ln(10)`` — ``drho/d(log10 lambda) = ln(10)``.

    Raises:
        PolarisValidationError: same conditions as ``reml_score_general``
            (``family.dispersion_fixed`` false, non-positive ``gamma``,
            empty ``penalty_blocks``, or a ``lambdas``/``penalty_blocks``
            length mismatch) — this function forms the identical ``H`` and
            needs the identical preconditions to be well-defined.
    """
    if not family.dispersion_fixed:
        raise PolarisValidationError(
            f"reml_score_gradient: family {family.name!r} estimates its own "
            "dispersion (dispersion_fixed=False) — the known-scale REML "
            "criterion this gradient differentiates does not apply to it."
        )
    if gamma <= 0.0:
        raise PolarisValidationError(f"gamma must be positive, got {gamma}.")
    if not penalty_blocks:
        raise PolarisValidationError("reml_score_gradient: penalty_blocks must be non-empty.")
    if len(lambdas) != len(penalty_blocks):
        raise PolarisValidationError(
            f"reml_score_gradient: lambdas has {len(lambdas)} entries, but "
            f"{len(penalty_blocks)} penalty_blocks were supplied — one lambda "
            "per block."
        )

    n = y.shape[0]
    offset = np.zeros(n, dtype=np.float64) if offset is None else np.asarray(offset)
    weights = np.ones(n, dtype=np.float64) if weights is None else np.asarray(weights)
    coef = np.asarray(coef, dtype=np.float64)
    lambdas = np.asarray(lambdas, dtype=np.float64)

    penalty = np.zeros_like(penalty_blocks[0], dtype=np.float64)
    for lam, block in zip(lambdas, penalty_blocks, strict=True):
        penalty = penalty + lam * block

    eta = offset + x @ coef
    mu = family.link.linkinv(eta)
    # The OBSERVED Hessian (Defect B), matching the SAME H `reml_score_general`
    # forms — the gradient must differentiate the identical function, not a
    # Fisher-weighted stand-in.
    observed_weights = family.observed_information_weight(y, eta, weights)
    hessian = x.T @ (observed_weights[:, None] * x) + penalty
    h_inv = scipy.linalg.cho_solve(
        scipy.linalg.cho_factor(hessian, lower=True), np.eye(hessian.shape[0])
    )

    dlogdet_s = dlogdet_s_plus_drho(penalty_blocks, lambdas)

    # Term 3 — dW/drho, exact (not the alpha=1 Fisher approximation):
    # d_eta_d_rho needs the SAME observed weights as H itself (Wood Appendix C
    # is an implicit-function-theorem result at the Newton/observed Hessian,
    # gam_derivatives.d_beta_d_rho's own docstring).
    log_lambda_natural = np.log(lambdas)
    deta_drho = d_eta_d_rho(x, penalty_blocks, observed_weights, coef, log_lambda_natural)
    dw_drho_all = dw_drho_observed(family, y, eta, mu, deta_drho, weights)  # (M, n)
    hat_diag = np.einsum("np,pq,nq->n", x, h_inv, x)  # diag(X H^-1 X^T)

    n_blocks = len(penalty_blocks)
    grad = np.empty(n_blocks, dtype=np.float64)
    for j, block in enumerate(penalty_blocks):
        lam_j = lambdas[j]
        # Term 1 — envelope theorem: at beta_hat, d(Dp)/dbeta = 0, so the
        # indirect term through d(beta_hat)/drho vanishes and only the
        # direct dependence of beta_hat^T @ S @ beta_hat on rho_j survives.
        term1 = lam_j * float(coef @ block @ coef) / (2.0 * gamma)
        # Term 2 — the direct-penalty part of d(log|H|)/drho_j.
        term2 = 0.5 * lam_j * float(np.sum(h_inv * block))
        # Term 3 — the weight-matrix part of d(log|H|)/drho_j.
        term3 = 0.5 * float(np.sum(dw_drho_all[j] * hat_diag))
        # Term 4 — d(-0.5 log|S|+)/drho_j, Appendix B's own pseudoinverse.
        term4 = -0.5 * dlogdet_s[j]
        grad[j] = term1 + term2 + term3 + term4
    return grad

"""Coefficient covariance and pointwise standard errors for ``PolarisGAMFit`` —
preview epic Slice P2 (``docs/PLAN_gam_parity_preview.md``, ADR-250).

**Nothing here is a new numeric formula.** This module composes pieces already
verified against ``mgcv`` at tier 3 and assembles what ``mgcv`` calls ``Vp`` and
``Vc``:

* ``Vp = phi (XᵀWX + S_lambda)⁻¹`` — the Bayesian posterior covariance of the
  coefficients (``m$Vp``, ``vcov(m)``), with ``W`` the observed-Hessian (Newton)
  working weights (:func:`~polaris_re.analytics.gam_derivatives.newton_working_weights`)
  and ``phi`` the fit's scale;
* ``Vc = Vp + J Vrho Jᵀ + phi V''`` — the Wood-Pya-Säfken (2016) eq. (7)
  smoothing-parameter-uncertainty correction
  (:func:`~polaris_re.analytics.gam_uncertainty.unconditional_covariance`,
  ADR-202), fed by the EXACT REML Hessian in ``rho = log(lambda)`` that the Newton
  search already computes
  (:func:`~polaris_re.analytics.gam_reml_hessian.reml_score_hessian` /
  :func:`~polaris_re.analytics.gam_reml_hessian.reml_score_hessian_profiled`,
  ADR-243/244) — not ``mgcv``'s Hessian, which is what ADR-202's own comparison
  had to borrow.

**Where the scale is applied (PLAN P2's third bullet).**
``unconditional_covariance`` works on the unit-dispersion basis: its
``first_order`` is scale-free and its ``second_order`` is linear in ``phi``
(its docstring, PR #207 review). So here ``Vp = phi * V_unit``,
``Vc = Vp + first_order + phi * second_order``. ``phi`` is ``1`` for a
fixed-dispersion family (Poisson, binomial) and the Fletcher estimate
(:attr:`~polaris_re.analytics.gam_dispersion.DispersionEstimates.fletcher`) for a
free-scale one — the estimate ADR-248's dispersion work established as
``mgcv``'s ``m$scale`` under REML.

**Standard errors** are ``sqrt(rowSums((X_new @ V) * X_new))`` on the link scale
(``mgcv``'s ``predict.gam(se.fit=TRUE)``); on the response scale the delta
method multiplies by ``|dmu/deta|``, exactly as ``predict.gam`` does. An offset
is a known constant and contributes no variance.

Plateau blocks: on a ``select=TRUE`` fit a block at large ``lambda`` makes the
``rho`` Hessian near-singular. ``Vp`` is unaffected (it does not use the
Hessian); ``Vc`` inverts it — unregularised for the first-order term and with
``mgcv``'s own ``0.1`` ridge for the second, as ``mgcv`` does
(``MGCV_RHO_RIDGE``). This module does not floor it further; a Hessian that is
not positive definite raises :class:`~polaris_re.core.exceptions.PolarisComputationError`
rather than returning a covariance that is not one.
"""

from dataclasses import dataclass

import numpy as np

from polaris_re.analytics.gam_derivatives import (
    d_beta_d_rho,
    d_eta_d_rho,
    dw_drho,
    newton_working_weights,
)
from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_reml_hessian import reml_score_hessian, reml_score_hessian_profiled
from polaris_re.analytics.gam_uncertainty import unconditional_covariance
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = ["CoefficientCovariance", "coefficient_covariance", "linear_predictor_se"]


@dataclass(frozen=True)
class CoefficientCovariance:
    """``Vp`` and the pieces of ``Vc``, kept separable."""

    vp: np.ndarray
    """``phi (XᵀWX + S_lambda)⁻¹`` — ``mgcv``'s ``m$Vp`` / ``vcov(m)``."""
    first_order: np.ndarray | None
    """``J Vrho Jᵀ`` (scale-free); ``None`` unless ``unconditional=True``."""
    second_order: np.ndarray | None
    """``phi V''``, already scaled; ``None`` unless ``unconditional=True``."""
    scale: float

    @property
    def vc(self) -> np.ndarray:
        """``Vp + J Vrho Jᵀ + phi V''`` — ``mgcv``'s ``vcov(m, unconditional=TRUE)``."""
        if self.first_order is None or self.second_order is None:
            raise PolarisValidationError(
                "CoefficientCovariance.vc: the unconditional correction was not computed "
                "(coefficient_covariance was called with unconditional=False)."
            )
        return np.asarray(self.vp + self.first_order + self.second_order, dtype=np.float64)


def coefficient_covariance(
    *,
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    log10_lambda: np.ndarray,
    coef: np.ndarray,
    offset: np.ndarray | None,
    weights: np.ndarray | None,
    scale: float,
    unconditional: bool,
) -> CoefficientCovariance:
    """``Vp`` and, when asked, the eq. (7) correction, at a converged fit.

    Args:
        y, x, family, penalty_blocks, coef, offset, weights: the fit's own data.
        log10_lambda: ``log10(lambda)`` per block (the fit's ``log_lambda``).
        scale: ``phi`` — ``1.0`` for a fixed-dispersion family.
        unconditional: also build the Wood-Pya-Säfken correction.

    Raises:
        PolarisValidationError: non-finite or non-positive ``scale``.
        PolarisComputationError: ``XᵀWX + S_lambda`` not positive definite, or
            the ``rho`` Hessian not invertible.
    """
    if not np.isfinite(scale) or scale <= 0.0:
        raise PolarisValidationError(
            f"coefficient_covariance: the scale must be finite and positive, got {scale!r} "
            "(a free-scale fit with no residual degrees of freedom has no covariance)."
        )
    n, p = x.shape
    lambdas = 10.0 ** np.asarray(log10_lambda, dtype=np.float64)
    off = np.zeros(n, dtype=np.float64) if offset is None else np.asarray(offset, dtype=np.float64)
    eta = off + x @ coef
    mu = family.link.linkinv(eta)
    w_newton = newton_working_weights(family, y, eta, mu, weights)
    s_total = np.zeros((p, p), dtype=np.float64)
    for lam, block in zip(lambdas, penalty_blocks, strict=True):
        s_total = s_total + lam * block
    information = x.T @ (w_newton[:, None] * x) + s_total
    eigenvalues = np.linalg.eigvalsh((information + information.T) / 2.0)
    if eigenvalues[0] <= p * np.finfo(np.float64).eps * eigenvalues[-1]:
        raise PolarisComputationError(
            "coefficient_covariance: XᵀWX + S_lambda is numerically singular "
            f"(smallest eigenvalue {eigenvalues[0]:.3e} against largest "
            f"{eigenvalues[-1]:.3e}): a direction no term's penalty or data identifies. "
            "The usual cause is a smooth and a factor-`by` smooth of the same covariate "
            "(their linear null spaces coincide). mgcv fits such a model by pivoting the "
            "unidentified coefficient out; this engine does not, and a covariance "
            "inverted through that direction would be arbitrary, so none is returned "
            "(ADR-250; MGCV_FEATURE_COVERAGE.md)."
        )
    v_unit = np.linalg.inv(information)
    v_unit = (v_unit + v_unit.T) / 2.0
    vp = scale * v_unit
    if not unconditional:
        return CoefficientCovariance(vp=vp, first_order=None, second_order=None, scale=scale)

    rho = np.log(lambdas)
    j = d_beta_d_rho(x, penalty_blocks, w_newton, coef, rho)
    deta = d_eta_d_rho(x, penalty_blocks, w_newton, coef, rho)
    dw = dw_drho(family, eta, mu, deta, weights)
    if family.dispersion_fixed:
        hessian = reml_score_hessian(
            y, x, family, coef, penalty_blocks, lambdas, offset=offset, weights=weights
        )
    else:
        hessian = reml_score_hessian_profiled(
            y, x, family, coef, penalty_blocks, lambdas, offset=offset, weights=weights
        )
    try:
        corr = unconditional_covariance(
            v_beta=v_unit,
            design=x,
            dbeta_drho=j,
            dw_drho_all=dw,
            penalties=penalty_blocks,
            log_lambda=rho,
            rho_hessian=0.5 * (hessian + hessian.T),
        )
    except np.linalg.LinAlgError as exc:
        raise PolarisComputationError(
            "coefficient_covariance: the REML Hessian in rho is singular, so the "
            "unconditional correction is undefined (a plateau block on a select=TRUE fit)."
        ) from exc
    return CoefficientCovariance(
        vp=vp,
        first_order=corr.first_order,
        second_order=corr.second_order * scale,
        scale=scale,
    )


def linear_predictor_se(x_new: np.ndarray, v: np.ndarray) -> np.ndarray:
    """``sqrt(diag(X_new V X_newᵀ))`` without forming the ``n x n`` matrix."""
    var = np.einsum("ij,jk,ik->i", x_new, v, x_new)
    floor = -1.0e-10 * max(1.0, float(np.max(np.abs(var))))
    if np.any(var < floor):
        raise PolarisComputationError(
            f"linear_predictor_se: a variance of {float(var.min()):.3e} is materially negative, "
            "so V is not positive semi-definite; clipping it would hide that."
        )
    return np.asarray(np.sqrt(np.maximum(var, 0.0)), dtype=np.float64)

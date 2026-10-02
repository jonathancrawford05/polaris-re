"""Dispersion (scale) estimators for a fitted GAM — capability ladder slice **3c**.

``gam_reml.reml_score_general`` profiles a free scale out of the REML score as
``phi_hat = penalized_deviance / (n - Mp)`` and then discards it: that quantity
is internal to the criterion and is **not** what ``mgcv`` reports. This module
exposes the estimator ``mgcv`` actually reports as ``m$scale`` for a
quasi-family fit, computed from a fit's own ``mu`` and EDF.

**Which estimator (measured, not assumed).** ``mgcv``'s ``gam.control`` default
is ``scale.est = "fletcher"``; ``gam.fit3`` computes, for ``dev.extra = 0``,

    pearson   = sum(w * (y - mu)^2 / V(mu))
    scale.est = pearson / (n - trA)
    s.bar     = max(-0.9, mean(V'(mu) * (y - mu) / V(mu)))
    scale.est = scale.est / (1 + s.bar)            # Fletcher (2012)

with ``trA`` the trace of the influence matrix (``PolarisGAMFit.edf_total``).
Plain Pearson (``scale.est = "pearson"``) and deviance (``"deviance"``)
estimators are *different numbers* and are exposed separately so a caller is
never handed one under the other's name. Both ``mean`` in ``s.bar`` and ``n``
are over ALL observations, unweighted, as in ``gam.fit3`` (``n.true``); prior
weights enter only the Pearson sum.

Nothing here is a threshold or a gate: whether a given dispersion is severe
enough to justify a different family, or a two-stage fit, is the caller's
decision (maintainer, 2026-09-30).
"""

from dataclasses import dataclass

import numpy as np

from polaris_re.analytics.gam_family import Family
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["DispersionEstimates", "dispersion_estimates"]

_FLETCHER_S_BAR_FLOOR = -0.9
"""``mgcv``'s own floor on ``s.bar`` (``max(-0.9, ...)``) — keeps ``1 + s.bar``
away from zero. A constant of ``gam.fit3``, not a tuned one."""


@dataclass(frozen=True)
class DispersionEstimates:
    """The three classical dispersion estimators for one fit.

    For a family with ``dispersion_fixed=True`` (Poisson, binomial) these are
    *overdispersion diagnostics* of the fit, not the model's own scale (which is
    held at 1, or at ``gamma``).
    """

    pearson: float
    """``sum(w (y-mu)^2 / V(mu)) / (n - edf_total)`` — ``scale.est="pearson"``."""
    fletcher: float
    """``pearson / (1 + s_bar)`` — ``mgcv``'s default ``scale.est`` and what it
    reports as ``m$scale`` for a free-scale quasi-family under REML."""
    deviance: float
    """``deviance / (n - edf_total)`` — ``scale.est="deviance"``."""
    s_bar: float
    """Fletcher's correction term, after ``mgcv``'s ``-0.9`` floor."""
    residual_df: float
    """``n - edf_total``."""


def dispersion_estimates(
    y: np.ndarray,
    mu: np.ndarray,
    family: Family,
    edf_total: float,
    *,
    weights: np.ndarray | None = None,
) -> DispersionEstimates:
    """Pearson, Fletcher and deviance dispersion estimates for a fitted ``mu``.

    Args:
        y: the response, ``(n,)``.
        mu: fitted means on the response scale, ``(n,)``.
        family: the fit's :class:`~polaris_re.analytics.gam_family.Family`.
        edf_total: ``tr(F)`` of the fit — ``PolarisGAMFit.edf_total``.
        weights: prior weights, ``(n,)``; ``None`` means all ones.

    Raises:
        PolarisValidationError: shapes disagree, or ``n - edf_total <= 0`` (no
            residual degrees of freedom — every estimator is undefined).
    """
    y = np.asarray(y, dtype=np.float64)
    mu = np.asarray(mu, dtype=np.float64)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=np.float64)
    if not (y.shape == mu.shape == w.shape) or y.ndim != 1:
        raise PolarisValidationError(
            f"dispersion_estimates: y {y.shape}, mu {mu.shape}, weights {w.shape} "
            "must be equal-length 1-D arrays."
        )
    n = float(y.size)
    residual_df = n - float(edf_total)
    if residual_df <= 0.0:
        raise PolarisValidationError(
            f"dispersion_estimates: n - edf_total = {residual_df:.6g} <= 0; "
            "no residual degrees of freedom."
        )
    variance = family.variance(mu)
    pearson_stat = float(np.sum(w * (y - mu) ** 2 / variance))
    pearson = pearson_stat / residual_df
    s_bar = float(np.mean(family.variance_prime(mu) * (y - mu) / variance))
    s_bar = max(_FLETCHER_S_BAR_FLOOR, s_bar)
    return DispersionEstimates(
        pearson=pearson,
        fletcher=pearson / (1.0 + s_bar),
        deviance=family.deviance(y, mu, w) / residual_df,
        s_bar=s_bar,
        residual_df=residual_df,
    )

"""``mgcv``'s data-based starting smoothing parameters — capability ladder slice **3d**.

``gam(..., method="REML")`` does not start its outer search from a fixed point.
``estimate.gam`` calls ``initial.spg``, which evaluates the IRLS working weights
at the family's initial ``mu`` and passes ``sqrt(w) X`` to ``initial.sp``. That
function sets each penalty block's ``lambda_i = mean(diag(X'WX)) / mean(diag(S_i))``
(over the block's own penalized columns), then rescales ALL ``lambda`` together by
factors of 10 until ``mean(ldxx / (ldxx + ldss)) ≈ 0.4``. The ``0.4`` is ``mgcv``'s
own constant, reproduced here and not tuned.

:func:`initial_log10_lambda` is that recipe on Polaris's own penalty blocks
(Stage-A-verified equal to ``mgcv``'s ``S``). It reads no ``mgcv`` output: its
inputs are the data, the design and the penalty blocks.

Family initialisation (``family$initialize``) is dispatched by family name:
Poisson/quasi-Poisson ``mu = y + 0.1``, Gaussian ``mu = y``, binomial
``mu = (w y + 0.5)/(w + 1)``.
"""

import numpy as np

from polaris_re.analytics.gam_family import Family
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["initial_log10_lambda"]

_BALANCE_TARGET = 0.4
"""``mgcv``'s own ``initial.sp`` data/penalty balance target."""


def _initial_mu(family: Family, y: np.ndarray, weights: np.ndarray) -> np.ndarray:
    if family.name in ("poisson", "quasipoisson"):
        return np.asarray(y + 0.1, dtype=np.float64)
    if family.name == "gaussian":
        return y.copy()
    if family.name == "binomial":
        return np.asarray((weights * y + 0.5) / (weights + 1.0), dtype=np.float64)
    raise PolarisValidationError(
        f"initial_log10_lambda: no mgcv family$initialize rule for family {family.name!r}."
    )


def _linkfun(family: Family, mu: np.ndarray) -> np.ndarray:
    name = family.link.name
    if name == "log":
        return np.asarray(np.log(mu), dtype=np.float64)
    if name == "identity":
        return mu.copy()
    if name == "logit":
        return np.asarray(np.log(mu / (1.0 - mu)), dtype=np.float64)
    if name == "cloglog":
        return np.asarray(np.log(-np.log1p(-mu)), dtype=np.float64)
    raise PolarisValidationError(f"initial_log10_lambda: no linkfun for link {name!r}.")


def initial_log10_lambda(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    penalty_blocks: tuple[np.ndarray, ...],
    *,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    """``log10`` of ``mgcv``'s ``initial.spg`` starting ``lambda``, one per block."""
    y = np.asarray(y, dtype=np.float64)
    w_prior = np.ones_like(y) if weights is None else np.asarray(weights, dtype=np.float64)
    mu = _initial_mu(family, y, w_prior)
    eta = _linkfun(family, mu)
    w = np.sqrt(w_prior * family.link.mu_eta(eta) ** 2 / family.variance(mu))
    ldxx = np.sum((w[:, None] * x) ** 2, axis=0)
    eps = np.finfo(np.float64).eps
    ldss = np.zeros_like(ldxx)
    pen = np.zeros(ldxx.shape, dtype=bool)
    def_sp = np.zeros(len(penalty_blocks), dtype=np.float64)
    for i, block in enumerate(penalty_blocks):
        nz = np.flatnonzero(np.any(block != 0.0, axis=0))
        if nz.size == 0:
            raise PolarisValidationError(f"initial_log10_lambda: penalty block {i} is all zero.")
        sl = slice(int(nz[0]), int(nz[-1]) + 1)
        s = block[sl, sl]
        a = np.abs(s)
        thresh = eps**0.8 * a.max()
        keep = (a.mean(axis=1) > thresh) & (a.mean(axis=0) > thresh) & (np.diag(a) > thresh)
        size_s = float(np.mean(np.diag(s)[keep]))
        size_xx = float(np.mean(ldxx[sl][keep]))
        if size_s <= 0.0:
            raise PolarisValidationError(f"initial_log10_lambda: block {i} diagonal is not > 0.")
        def_sp[i] = size_xx / size_s
        ldss[sl] += def_sp[i] * np.diag(s)
        pen[sl] |= keep
    ind = (ldss > 0.0) & pen & (ldxx > 0.0)
    ldxx_i, ldss_i = ldxx[ind], ldss[ind]
    while np.mean(ldxx_i / (ldxx_i + ldss_i)) > _BALANCE_TARGET:
        def_sp *= 10.0
        ldss_i = ldss_i * 10.0
    while np.mean(ldxx_i / (ldxx_i + ldss_i)) < _BALANCE_TARGET:
        def_sp /= 10.0
        ldss_i = ldss_i / 10.0
    return np.log10(def_sp)

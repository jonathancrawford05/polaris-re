"""Wood, Pya and Saefken (2016) eq. (7) assembled for a penalized MI fit.

**This module changes nothing that ships.** `experience_gam_penalized` is
untouched (PLAN Anchor 7); this reads a fit that module produced and returns a
covariance correction beside it. It exists so ADR-190 decision 4's registered
prediction can be *measured* before anyone decides whether to re-point
production at it.

## Why a seam rather than an edit

ADR-202 closed level 4: :func:`~polaris_re.analytics.gam_uncertainty.unconditional_covariance`
reproduces ``mgcv``'s ``vcov(unconditional = TRUE)`` to 0.023-0.904% element-wise
on the tier-3 oracle. What it does not do is tell us whether the larger
correction *fixes the thing it was supposed to fix* — ADR-188's coverage gate,
which fails at 0.8516 / 0.8581 against a 0.9192 floor. Those are different
claims, and ADR-190 decision 4 wrote the second one down in advance:

    "Registered in advance: implementing Wood (2016) should move coverage toward
    or past that floor. If it does not, the coverage gap has a second cause and
    this ADR's decision 1 will need re-examining."

Measuring it requires the correction on the *production* fit, not on the
conformance fixtures. This module is that adapter, and it is deliberately the
only new seam: if the maintainer later signs off under Anchor 7, production
calls :func:`wps_correction` and nothing else moves.

## Two mechanisms, kept separable

Re-pointing production would change the shipped band **twice over**, and only one
of the two changes is what ADR-202 verified against ``mgcv``:

1. the **formula** — eq. (7)'s ``V''`` term, which plain Kass-Steffey omits;
2. the **derivative method** — ``J = dbeta/drho`` analytically (Wood 2011 section 3.4)
   rather than by the central differences
   :func:`~polaris_re.analytics.experience_gam_penalized.smoothing_uncertainty`
   takes.

:class:`MIUncertainty` therefore reports ``first_order`` and ``second_order``
separately, so a study can attribute any coverage movement to one or the other
instead of to their sum. On the age-varying truth at seed 1000 the analytic and
finite-difference first-order terms inflate the mean coefficient variance
1.1386x and 1.1418x respectively — the same quantity to 0.3% — which is the
evidence that mechanism 2 is small and mechanism 1 is the story.

## The Hessian, and the one place this floors it

``smoothing_uncertainty`` evaluates the REML Hessian at a **grid point**, not a
stationary point, so it can carry a near-zero or negative eigenvalue; production
raises those to ``1/(half bound width)**2``, a cap derived from the selector's own
contract rather than tuned (see that function's docstring). ``unconditional_covariance``
takes a Hessian, not an inverse, so this module reconstructs the floored Hessian
from production's own eigen-decomposition and reports how often it bound. No new
constant is introduced (PLAN Anchor 8): the floor is production's, reused.
"""

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam_penalized import (
    LAMBDA_LOG10_BOUNDS,
    PenalizedMIFit,
    PenalizedTensorMIModel,
    SmoothingUncertainty,
)
from polaris_re.analytics.gam_derivatives import (
    d_beta_d_rho,
    d_eta_d_rho,
    dw_drho,
    newton_working_weights,
)
from polaris_re.analytics.gam_family import poisson_log
from polaris_re.analytics.gam_uncertainty import unconditional_covariance
from polaris_re.core.exceptions import PolarisComputationError

__all__ = ["MIUncertainty", "wps_correction"]


class MIUncertainty:
    """Eq. (7)'s two correction terms for a penalized MI fit, kept separable.

    Args:
        first_order: ``V' = J Vrho Jᵀ`` with ``J`` taken analytically. The
            Kass-Steffey term, i.e. what production already approximates by
            central differences.
        second_order: ``V''``, eq. (7)'s addition. Zero in the Kass-Steffey
            approximation by construction, so this is exactly what re-pointing
            production would add.
        n_floored: Hessian directions raised to production's eigenvalue floor.
            Nonzero means the reported correction is capped rather than measured
            in that direction.
        hessian_eigenvalues: the raw REML Hessian's eigenvalues, before flooring,
            so a reader can see how close to singular the profile was.
    """

    def __init__(
        self,
        first_order: np.ndarray,
        second_order: np.ndarray,
        n_floored: int,
        hessian_eigenvalues: np.ndarray,
    ) -> None:
        self.first_order = first_order
        self.second_order = second_order
        self.n_floored = n_floored
        self.hessian_eigenvalues = hessian_eigenvalues

    @property
    def correction(self) -> np.ndarray:
        """``V' + V''`` — the full eq. (7) correction, to be added to ``Vb``."""
        return np.asarray(self.first_order + self.second_order, dtype=np.float64)


def _floored_hessian(hessian: np.ndarray, bounds: tuple[float, float]) -> tuple[np.ndarray, int]:
    """Production's eigenvalue floor, applied to the Hessian rather than its inverse.

    :func:`~polaris_re.analytics.experience_gam_penalized.smoothing_uncertainty`
    floors the eigenvalues and then inverts;
    :func:`~polaris_re.analytics.gam_uncertainty.unconditional_covariance` needs
    the Hessian itself, because its two terms take *different* inverses of it. So
    the same clip is applied and the matrix reassembled. Identical device,
    identical constant, one step earlier.
    """
    half_width = float(np.log(10.0) * (bounds[1] - bounds[0])) / 2.0
    floor = 1.0 / (half_width * half_width)
    symmetric = 0.5 * (hessian + hessian.T)
    eigenvalues, vectors = np.linalg.eigh(symmetric)
    clipped = np.maximum(eigenvalues, floor)
    n_floored = int(np.sum(eigenvalues <= floor))
    reassembled = (vectors * clipped) @ vectors.T
    return np.asarray(reassembled, dtype=np.float64), n_floored


def wps_correction(
    cells: pl.DataFrame,
    fit: PenalizedMIFit,
    extra: SmoothingUncertainty,
    *,
    bounds: tuple[float, float] = LAMBDA_LOG10_BOUNDS,
    **model_kwargs: object,
) -> MIUncertainty:
    """Eq. (7)'s correction for an already-fitted penalized MI surface.

    Args:
        cells: the grouped-cell frame the fit was produced from.
        fit: the fit, from
            :func:`~polaris_re.analytics.experience_gam_penalized.fit_reml`.
        extra: production's
            :func:`~polaris_re.analytics.experience_gam_penalized.smoothing_uncertainty`
            at the same lambda, used **only** for its REML Hessian. Taken as an
            argument rather than recomputed because it costs nine penalized fits
            and every caller already has one.
        bounds: the selector's log10 lambda search range, which is where the
            eigenvalue floor comes from.
        **model_kwargs: the model arguments the fit used (``k_age``, ``k_year``,
            ...), needed to rebuild the identical design.

    Returns:
        The two correction terms, separable.

    Raises:
        PolarisComputationError: if the rebuilt fit does not reproduce the
            supplied one. That would mean ``model_kwargs`` did not match the
            arguments ``fit`` was produced under, and a correction assembled on a
            different design than the band it corrects is not a correction.
    """
    model = PenalizedTensorMIModel(
        cells,
        lambda_age=fit.lambda_age,
        lambda_year=fit.lambda_year,
        **model_kwargs,  # type: ignore[arg-type]
    )
    rebuilt = model.fit()
    context = model.design_context
    if context is None:  # pragma: no cover - fit() always sets it
        raise PolarisComputationError("fit() did not record its design context.")
    # Shape first: a different `k` gives a different column count, and comparing
    # those with np.allclose raises a broadcast ValueError from numpy instead of
    # this function's own error. Caught by
    # test_mismatched_model_kwargs_raise_rather_than_silently_correcting_the_wrong_band.
    if rebuilt.coef.shape != fit.coef.shape or not np.allclose(
        rebuilt.coef, fit.coef, rtol=1e-10, atol=1e-12
    ):
        raise PolarisComputationError(
            "gam_uncertainty_mi: rebuilding the design at the fitted lambda gave "
            "different coefficients, so model_kwargs do not match the arguments "
            "the supplied fit was produced under. Correcting a band with a "
            "covariance assembled on a different design is not a correction."
        )

    design = np.asarray(context.design, dtype=np.float64)
    n_coef = design.shape[1]
    n_tensor = context.n_tensor

    eta = np.asarray(context.offset + design @ fit.coef, dtype=np.float64)
    mu = np.exp(eta)
    family = poisson_log()
    # The log link is canonical for the Poisson, so Wood (2011) Appendix C's
    # alpha is identically 1 and these coincide with the fitter's Fisher weights.
    # Taken through newton_working_weights anyway: that identity is a derived
    # result (ADR-201), not something this call should assume on its own.
    weights = newton_working_weights(family, context.deaths, eta, mu)

    penalties = []
    for block in (context.s_age, context.s_year):
        padded = np.zeros((n_coef, n_coef), dtype=np.float64)
        padded[:n_tensor, :n_tensor] = block
        penalties.append(padded)
    penalty_blocks = tuple(penalties)
    log_lambda = np.log(np.array([fit.lambda_age, fit.lambda_year], dtype=np.float64))

    dbeta = d_beta_d_rho(design, penalty_blocks, weights, fit.coef, log_lambda)
    deta = d_eta_d_rho(design, penalty_blocks, weights, fit.coef, log_lambda)
    dw_all = dw_drho(family, eta, mu, deta)

    hessian, n_floored = _floored_hessian(extra.hessian, bounds)
    raw_eigenvalues = np.linalg.eigvalsh(0.5 * (extra.hessian + extra.hessian.T))

    correction = unconditional_covariance(
        v_beta=fit.cov / fit.dispersion,
        design=design,
        dbeta_drho=dbeta,
        dw_drho_all=dw_all,
        penalties=penalty_blocks,
        log_lambda=log_lambda,
        rho_hessian=hessian,
    )
    return MIUncertainty(
        first_order=correction.first_order,
        second_order=correction.second_order,
        n_floored=n_floored,
        hessian_eigenvalues=raw_eigenvalues,
    )

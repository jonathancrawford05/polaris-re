"""
Offline ``mgcv``-via-``rpy2`` oracle for the tensor mortality-improvement GAM (A4').

Design Anchor 5 of the experience-GAM epic (docs/PLAN_experience_gam.md) commits to
validating the Python GAM against an independent, authoritative GAM implementation —
R's ``mgcv`` — **without ever shipping the R dependency at runtime or in CI** (it
would break the Python-native thesis and the Docker/CI image). This module is that
oracle: a dev-only, opt-in cross-check that the Python tensor-MI coefficients match
R ``mgcv`` on a shared synthetic dataset.

Why the cross-check is trustworthy — *correct by construction*
--------------------------------------------------------------
:class:`~polaris_re.analytics.experience_gam.TensorMIModel` fits a Poisson GLM with a
log link over a **fixed, unpenalized** tensor B-spline design ``X`` and a
log-exposure offset. That log-likelihood is strictly concave in the coefficients, so
its maximiser is **unique**: any correct Poisson-GLM solver applied to the identical
``(deaths, X, offset)`` returns the same coefficients to solver tolerance. The oracle
therefore ships the *exact* design the Python model fit — extracted from the fitted
``statsmodels`` result, never re-derived — to
``mgcv::gam(deaths ~ 0 + X, family = poisson(), offset = offset)`` (a pure-parametric
``gam`` reduces to exactly that GLM) and asserts the coefficients agree.

This construction lets the numerical claim be *verified without R present*:

- :func:`poisson_score_infinity_norm` proves the shipped design sits at the unique
  Poisson MLE (``||Xᵀ(y - μ)||∞ ≈ 0``). Because the problem is strictly concave, that
  single property pins what any conformant R solver must return — the mgcv comparison
  cannot disagree beyond solver tolerance. The runnable tests assert this property, so
  the session's coverage does not depend on R being installed.
- :func:`mgcv_available` gates the R path. Without ``rpy2`` + R + the ``mgcv``
  package it returns ``False`` and the opt-in cross-check test skips, so CI and the
  Docker runtime never import ``rpy2`` or spawn R (Anchor 5).

The synthetic dataset is grouped-cell experience with a Makeham static base and a
known age-declining improvement, with Poisson-sampled deaths under a **pinned** RNG
seed (never the wall clock — ADR-074). Poisson noise makes the fit an ordinary
interior MLE (rather than the noiseless exact fit of the Slice-4c-2 recovery deck),
which is the more representative thing to cross-check against ``mgcv``.

ADR-151.
"""

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam import TensorMIModel

__all__ = [
    "OracleCase",
    "build_oracle_case",
    "fit_mgcv_coefficients",
    "mgcv_available",
    "poisson_score_infinity_norm",
]

# --- Deterministic synthetic grid + parametric base (all literals — ADR-074 clean) ---

_BASE_YEAR = 2005
_AGES: np.ndarray = np.arange(45, 76, dtype=np.int64)
_YEARS: np.ndarray = np.arange(2008, 2021, dtype=np.int64)
_EXPOSURE = 50_000.0

# SOA Illustrative Life Table Makeham law (A + B·c^x) as the static base q0(x).
# The oracle cross-checks the *fit*, so the base only needs to be a plausible,
# strictly-positive q0(x); the improvement recovery/identity is not the point here.
_MAKEHAM_A = 0.0007
_MAKEHAM_B = 0.00005
_MAKEHAM_C = 10.0**0.04

# Age-declining injected improvement (MIM-2021 / CIA-style shape): 2.0%/yr at the
# youngest modelled age tapering linearly to 0.5%/yr at the oldest.
_MI_YOUNG = 0.020
_MI_OLD = 0.005

# Pinned RNG seed for the Poisson death draw — deterministic, wall-clock-free.
_DEFAULT_SEED = 20050101


def _q0(ages: np.ndarray) -> np.ndarray:
    """Parametric static base rate ``q0(x)`` (Makeham law), one per age."""
    return (_MAKEHAM_A + _MAKEHAM_B * _MAKEHAM_C ** ages.astype(np.float64)).astype(np.float64)


def _mi(ages: np.ndarray) -> np.ndarray:
    """Injected age-declining annual improvement over the modelled age span."""
    a = ages.astype(np.float64)
    lo, hi = float(_AGES[0]), float(_AGES[-1])
    frac = (a - lo) / (hi - lo)
    return (_MI_YOUNG + (_MI_OLD - _MI_YOUNG) * frac).astype(np.float64)


@dataclass(frozen=True)
class OracleCase:
    """A shared synthetic Poisson-GLM fit ready for the R ``mgcv`` cross-check.

    Carries the *exact* design, offset, and response the Python model fit, plus the
    Python coefficient vector. R ``mgcv`` fit on ``(deaths, design, offset)`` must
    reproduce :attr:`python_coef` because the Poisson log-likelihood is strictly
    concave (see the module docstring).
    """

    age_varying: bool
    """Whether the tensor age-by-year interaction (age-varying improvement) is fit."""

    deaths: np.ndarray
    """Poisson-sampled death counts per grouped cell, shape ``(n_cells,)``."""

    design: np.ndarray
    """The fixed unpenalized tensor B-spline design ``X``, shape ``(n_cells, n_params)``."""

    offset: np.ndarray
    """Log-exposure offset ``log(exposure · q_base)`` per cell, shape ``(n_cells,)``."""

    python_coef: np.ndarray
    """Python (``statsmodels``) MLE coefficients, shape ``(n_params,)``."""

    seed: int = field(default=_DEFAULT_SEED)
    """RNG seed used for the Poisson death draw (pinned — ADR-074)."""

    @property
    def n_cells(self) -> int:
        """Number of grouped experience cells (design rows)."""
        return int(self.design.shape[0])

    @property
    def n_params(self) -> int:
        """Number of design columns / coefficients."""
        return int(self.design.shape[1])


def _synthetic_cells(seed: int) -> pl.DataFrame:
    """Grouped count-basis experience cells with Poisson-sampled deaths.

    Uses the canonical grouped contract (``attained_age``, ``calendar_year``,
    ``central_exposure``, ``death_count``, ``q_base``, ``duration_months``) directly —
    the oracle cross-checks the *fit*, so it does not need the ILEC loader path that
    Slice 4c-2 already exercises. Death counts are drawn from
    ``Poisson(exposure · q0(x) · (1 - MI(x))**(y - base_year))`` under the pinned seed.
    """
    rng = np.random.default_rng(seed)
    n_age, n_year = len(_AGES), len(_YEARS)
    n_cell = n_age * n_year

    # Age-major grid (attained age slowest, calendar year fastest) over _AGES x _YEARS.
    ages = np.repeat(_AGES, n_year).astype(np.int64)
    years = np.tile(_YEARS, n_age).astype(np.int64)
    q_base = np.repeat(_q0(_AGES), n_year).astype(np.float64)
    mi = np.repeat(_mi(_AGES), n_year).astype(np.float64)

    # Expected deaths under the injected improvement, then a single Poisson draw.
    q = q_base * (1.0 - mi) ** (years - _BASE_YEAR).astype(np.float64)
    deaths = rng.poisson(_EXPOSURE * q).astype(np.float64)

    return pl.DataFrame(
        {
            "attained_age": ages,
            "calendar_year": years,
            "central_exposure": np.full(n_cell, _EXPOSURE, dtype=np.float64),
            "death_count": deaths,
            "q_base": q_base,
            "duration_months": np.full(n_cell, 120, dtype=np.int64),
        }
    )


def build_oracle_case(*, age_varying: bool = True, seed: int = _DEFAULT_SEED) -> OracleCase:
    """Fit the tensor-MI model on the shared synthetic dataset and package the fit.

    The returned :class:`OracleCase` carries the *exact* design, offset, response, and
    coefficients of the Python fit — the artefacts the R ``mgcv`` cross-check consumes.
    Extraction is via the public :meth:`MISurfaceResult.fitted_glm_arrays` accessor, so
    the design is byte-identical to what the model fit; nothing is re-derived and the
    oracle does not reach into the result's private fit state.

    Args:
        age_varying: Fit the age-by-year tensor interaction (age-varying improvement).
        seed:        RNG seed for the Poisson death draw (pinned — ADR-074).

    Returns:
        An :class:`OracleCase` ready for :func:`poisson_score_infinity_norm` and
        :func:`fit_mgcv_coefficients`.
    """
    cells = _synthetic_cells(seed)
    result = TensorMIModel(
        cells,
        basis="count",
        age_df=5,
        year_df=4,
        age_varying=age_varying,
    ).fit()

    arrays = result.fitted_glm_arrays()
    return OracleCase(
        age_varying=age_varying,
        deaths=arrays.response,
        design=arrays.design,
        offset=arrays.offset,
        python_coef=arrays.coefficients,
        seed=seed,
    )


def poisson_score_infinity_norm(case: OracleCase) -> float:
    """Infinity-norm of the Poisson score ``Xᵀ(y - μ)`` at the Python coefficients.

    For a Poisson GLM with a log link and offset, ``μ = exp(Xβ + offset)`` and the
    score is ``Xᵀ(y - μ)``; it is zero at the (unique) MLE. A value near zero proves
    the shipped design sits at that maximiser — which, by strict concavity, is exactly
    what any conformant R ``mgcv``/``glm`` solve must return. This is the runnable
    guarantee that the R cross-check cannot disagree beyond solver tolerance.
    """
    eta = case.design @ case.python_coef + case.offset
    mu = np.exp(eta)
    return float(np.max(np.abs(case.design.T @ (case.deaths - mu))))


def mgcv_available() -> bool:
    """Return ``True`` iff ``rpy2`` + R + the ``mgcv`` package are importable here.

    Used to gate the opt-in cross-check test so that CI and the Docker runtime — which
    ship neither ``rpy2`` nor R (Anchor 5) — skip it rather than fail. Any import or
    R-startup failure is treated as "unavailable".
    """
    try:  # pragma: no cover - exercised only on a dev machine with R installed
        from rpy2.robjects.packages import importr

        importr("mgcv")
        return True
    except Exception:
        return False


def fit_mgcv_coefficients(case: OracleCase) -> np.ndarray:  # pragma: no cover - dev-only
    """Fit R ``mgcv::gam`` on the shared design and return its coefficient vector.

    Fits ``mgcv::gam(deaths ~ 0 + X, family = poisson(), offset = offset)`` — a
    pure-parametric ``gam``, which is exactly the Poisson GLM the Python model fit over
    the identical design ``X``. The returned coefficients are ordered to match
    :attr:`OracleCase.python_coef` (design column order), so the caller can compare the
    two vectors element-wise.

    This path is **dev-only** and never imported by the runtime or CI: it requires
    ``rpy2`` + R + ``mgcv`` (guard with :func:`mgcv_available`). It is marked
    ``no cover`` because the coverage-measured test environment does not ship R.

    Raises:
        ImportError / R errors: if ``rpy2`` or ``mgcv`` are unavailable (call
            :func:`mgcv_available` first).
    """
    from rpy2.robjects import globalenv, numpy2ri, r
    from rpy2.robjects.packages import importr

    importr("mgcv")
    numpy2ri.activate()
    try:
        globalenv["X"] = case.design
        globalenv["y"] = np.asarray(case.deaths, dtype=np.float64)
        globalenv["off"] = np.asarray(case.offset, dtype=np.float64)
        # Pure-parametric gam == the Poisson GLM the Python model fit. Column order of
        # X is preserved, so coef() aligns element-wise with python_coef.
        coef = r("as.numeric(coef(mgcv::gam(y ~ 0 + X, family = poisson(), offset = off)))")
        return np.asarray(coef, dtype=np.float64)
    finally:
        numpy2ri.deactivate()

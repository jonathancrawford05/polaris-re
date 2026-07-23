"""
Experience-analysis validation deck (A4') — recover a known mortality-improvement
surface from grouped, ILEC-shaped experience.

The closed-form / statutory-deck packs in :mod:`polaris_re.analytics.validation`
prove the *pricing* engine reproduces authoritative references. This module is
the analogue for the **data-driven experience-analysis** capability (the A4'
epic): a diligence-grade, network-free demonstration that the tensor
mortality-improvement GAM (:class:`~polaris_re.analytics.experience_gam.TensorMIModel`)
recovers a *known* improvement surface from grouped experience.

It is a **recovery identity**, the experience-analysis analogue of the whole-life
deck's parametric Makeham reference (which reproduces the SOA Illustrative Life
Table from its *published law* rather than a hand-copied column). The deck:

1. Injects a known improvement surface ``MI(x)`` into a synthetic, ILEC-source-schema
   experience extract whose ``Death Count`` is the *expected* deaths under that
   surface: ``d(x, y) = E · q0(x) · (1 - MI(x))**(y - base_year)`` with ``q0(x)``
   a cited parametric static base. Because the improvement is constant across
   calendar years, ``log d(x, y)`` is linear in ``y`` with an age-varying slope —
   a function the tensor-product B-spline basis spans exactly.
2. Feeds that extract through the real
   :func:`~polaris_re.analytics.experience_loaders.load_ilec` loader (the
   *loaders-not-data* discipline — no proprietary ILEC or MIM-2021 table is
   vendored; the synthetic extract is generated in a temp file at run time).
3. Fits the tensor MI surface and checks the recovered ``MI_x(y)`` against the
   injected target within a tight, documented tolerance.

Two sub-decks: a **flat** improvement recovered by a separable age+calendar fit,
and an **age-declining** improvement (the general shape of the SOA MIM-2021 / CIA
aggregate scales — higher improvement at younger attained ages, tapering toward
the oldest) recovered by the age-varying tensor fit. Both recover the injected
surface to numerical precision (observed residual < 3e-12).

The reference values are the *injected* parametric targets, not vendored
proprietary MIM-2021/CIA numbers — the deck's claim is "the GAM recovers a known
improvement surface", which is exactly the credibility question for an
experience-derived assumption basis. Everything is deterministic and pinned to
literal calendar years (no wall-clock read — ADR-074). ADR-150.
"""

import tempfile
import warnings
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam import MISurface
from polaris_re.analytics.validation import (
    ValidationCase,
    ValidationCategory,
    ValidationReport,
    ValidationResult,
)

__all__ = [
    "run_experience_improvement_benchmarks",
]

# --- Deterministic grid + parametric assumptions (all literals — ADR-074 clean) ---

_BASE_YEAR = 2005
_AGES: np.ndarray = np.arange(40, 86, dtype=np.int64)
_YEARS: np.ndarray = np.arange(2005, 2021, dtype=np.int64)
_EXPOSURE = 100_000.0

# SOA Illustrative Life Table Makeham law (A + B·c^x) — the same parametric base
# the whole-life deck uses — as the static q0(x). The improvement recovery is
# invariant to the base shape (it cancels in the year-to-year contrast), so a
# cited parametric base keeps the deck fully data-free.
_MAKEHAM_A = 0.0007
_MAKEHAM_B = 0.00005
_MAKEHAM_C = 10.0**0.04

# Flat improvement: 1.5% per year at every attained age.
_FLAT_MI = 0.015

# Age-declining improvement in the general shape of the SOA MIM-2021 / CIA
# aggregate scales: 2.0% per year at age 40 tapering linearly to 0.5% at age 85.
_MI_YOUNG = 0.020
_MI_OLD = 0.005
_MI_AGE_LO = 40.0
_MI_AGE_HI = 85.0

# Recovery tolerance. The injected improvement is constant across calendar years,
# so the target is spanned exactly by the tensor B-spline basis; the residual is
# purely numerical (observed < 3e-12). 1e-6 guards platform BLAS variation while
# staying ~1e-4 of a 1.5% improvement.
_ATOL = 1e-6

_SOURCE = (
    "Recovery identity — tensor MI GAM refit of a known injected improvement "
    "surface (MIM-2021 / CIA-style age-declining shape) fed through load_ilec; "
    "reference is the injected parametric target, not vendored MIM-2021 tables."
)
_RATIONALE = (
    "Improvement constant across calendar years => log q(x,y) linear in y with an "
    "age-varying slope, spanned exactly by the tensor B-spline basis; recovery is "
    "numerical (observed residual < 3e-12). atol=1e-6 guards platform BLAS variation."
)


def _q0(ages: np.ndarray) -> np.ndarray:
    """Parametric static base rate ``q0(x)`` (Makeham law), one per age."""
    return (_MAKEHAM_A + _MAKEHAM_B * _MAKEHAM_C ** ages.astype(np.float64)).astype(np.float64)


def _flat_mi(ages: np.ndarray) -> np.ndarray:
    """Injected flat annual improvement — constant across age."""
    return np.full(len(ages), _FLAT_MI, dtype=np.float64)


def _agevarying_mi(ages: np.ndarray) -> np.ndarray:
    """Injected age-declining annual improvement (MIM-2021/CIA-style shape)."""
    a = ages.astype(np.float64)
    frac = (a - _MI_AGE_LO) / (_MI_AGE_HI - _MI_AGE_LO)
    return (_MI_YOUNG + (_MI_OLD - _MI_YOUNG) * frac).astype(np.float64)


def _synthetic_ilec_frame(mi_fn: Callable[[np.ndarray], np.ndarray]) -> pl.DataFrame:
    """Build an ILEC-*source*-schema experience frame whose ``Death Count`` is the
    *expected* deaths under the injected improvement surface ``mi_fn``.

    Column names are the SOA-ILEC source spellings (``Observation Year``,
    ``Attained Age``, ``Gender``, ``Policies Exposed``, ``Death Count``) so the
    frame exercises the real :func:`load_ilec` rename / canonicalisation path.
    """
    mi_by_age = {int(a): float(m) for a, m in zip(_AGES, mi_fn(_AGES), strict=True)}
    q0_by_age = {int(a): float(q) for a, q in zip(_AGES, _q0(_AGES), strict=True)}

    ages_col: list[int] = []
    years_col: list[int] = []
    exposed_col: list[float] = []
    deaths_col: list[float] = []
    for a in _AGES:
        base = q0_by_age[int(a)]
        mi = mi_by_age[int(a)]
        for y in _YEARS:
            q = base * (1.0 - mi) ** (int(y) - _BASE_YEAR)
            ages_col.append(int(a))
            years_col.append(int(y))
            exposed_col.append(_EXPOSURE)
            deaths_col.append(_EXPOSURE * q)

    return pl.DataFrame(
        {
            "Observation Year": years_col,
            "Attained Age": ages_col,
            "Gender": ["M"] * len(ages_col),
            "Policies Exposed": exposed_col,
            "Death Count": deaths_col,
        }
    )


def _recover_surface(mi_fn: Callable[[np.ndarray], np.ndarray], *, age_varying: bool) -> MISurface:
    """Refit the tensor MI surface from a synthetic ILEC extract and return the
    recovered :class:`MISurface` over the full ``(_AGES, _YEARS)`` grid."""
    from statsmodels.tools.sm_exceptions import (
        ConvergenceWarning,
        PerfectSeparationWarning,
    )

    from polaris_re.analytics.experience_gam import TensorMIModel
    from polaris_re.analytics.experience_loaders import load_ilec

    frame = _synthetic_ilec_frame(mi_fn)
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "synthetic_ilec.csv"
        frame.write_csv(csv_path)
        cells = load_ilec(csv_path, basis="count")

    # Attach the same parametric static base the deaths were generated from.
    ages = cells["attained_age"].to_numpy()
    cells = cells.with_columns(pl.Series("q_base", _q0(ages), dtype=pl.Float64))

    with warnings.catch_warnings():
        # Noiseless expected-death data fits the Poisson mean exactly, which
        # statsmodels flags as perfect separation / no residual to converge on.
        # Both are benign here — an *exact* fit is precisely the point of a
        # recovery identity — so filter only these two, nothing else.
        warnings.simplefilter("ignore", PerfectSeparationWarning)
        warnings.simplefilter("ignore", ConvergenceWarning)
        model = TensorMIModel(cells, basis="count", age_varying=age_varying)
        result = model.fit()

    return result.improvement_surface(ages=_AGES, years=_YEARS)


def _mi_at(surface: MISurface, age: int, year: int) -> float:
    """Look up the recovered ``MI`` at an ``(attained_age, step-end calendar year)``."""
    ai = int(np.flatnonzero(surface.ages == age)[0])
    yi = int(np.flatnonzero(surface.years == year)[0])
    return float(surface.mi_grid[ai, yi])


def run_experience_improvement_benchmarks() -> ValidationReport:
    """Recover the injected improvement surfaces and score the fit as a report.

    Two sub-decks — a flat improvement recovered by a separable fit and an
    age-declining improvement recovered by the age-varying tensor fit — each
    sampled at representative interior grid points and compared to the injected
    parametric target within :data:`_ATOL`.
    """
    flat = _recover_surface(_flat_mi, age_varying=False)
    agevar = _recover_surface(_agevarying_mi, age_varying=True)

    # (case_id, name, expected, computed) tuples — expected is the injected target,
    # computed the value the refit surface recovers at that grid point.
    specs: list[tuple[str, str, float, float]] = [
        (
            "EXP-MI-FLAT-A60-Y2010",
            "Flat 1.5% improvement recovered (age 60, 2010)",
            float(_flat_mi(np.array([60]))[0]),
            _mi_at(flat, 60, 2010),
        ),
        (
            "EXP-MI-FLAT-A70-Y2018",
            "Flat 1.5% improvement recovered (age 70, 2018)",
            float(_flat_mi(np.array([70]))[0]),
            _mi_at(flat, 70, 2018),
        ),
        (
            "EXP-MI-VARY-A45-Y2015",
            "Age-declining improvement recovered (age 45, 2015)",
            float(_agevarying_mi(np.array([45]))[0]),
            _mi_at(agevar, 45, 2015),
        ),
        (
            "EXP-MI-VARY-A60-Y2015",
            "Age-declining improvement recovered (age 60, 2015)",
            float(_agevarying_mi(np.array([60]))[0]),
            _mi_at(agevar, 60, 2015),
        ),
        (
            "EXP-MI-VARY-A75-Y2015",
            "Age-declining improvement recovered (age 75, 2015)",
            float(_agevarying_mi(np.array([75]))[0]),
            _mi_at(agevar, 75, 2015),
        ),
    ]

    results: list[ValidationResult] = []
    for case_id, name, expected, computed in specs:
        case = ValidationCase(
            case_id=case_id,
            name=name,
            category=ValidationCategory.EXPERIENCE_IMPROVEMENT,
            source=_SOURCE,
            description=(
                "Inject a known annual improvement surface into an ILEC-shaped "
                "experience extract (expected deaths), refit the tensor MI GAM via "
                "load_ilec, and recover MI at this (age, year)."
            ),
            expected=expected,
            unit="annual improvement rate",
            tolerance_rtol=0.0,
            tolerance_atol=_ATOL,
            tolerance_rationale=_RATIONALE,
        )
        results.append(case.evaluate(computed))

    return ValidationReport(
        title="Polaris RE — Experience-Analysis Improvement Recovery Deck",
        results=tuple(results),
    )

"""Capability ladder slice 3e — does mgcv's ``initial.spg``-style start meet
ADR-221 on EVERY existing free-scale conformance cell? (ADR-240.)

ADR-239 shipped ``fit_polaris_gam(initial_sp_start=True)`` as an opt-in because
flipping the default would move every other free-scale reading. This module is
the measurement that decision needed: it fits each existing free-scale
conformance cell twice — default bounds-centre start, and the seeded start —
and compares each against ``mgcv``'s own free-``sp`` REML fit under ADR-221's
imported criterion (the per-family ``compare_*_free_sp_case`` functions; no
tolerance is declared here).

Provenance (ADR-193): INDEPENDENT on every compared quantity. Each fit
function takes only the shared recipe (never ``mgcv`` output); the search start
is the only thing varied between the two Polaris producers. This module adds no
new comparison of its own — it re-runs the existing comparisons with one change.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from polaris_re.analytics.gam_by_factor_conformance import (
    compare_by_factor_free_sp_case,
    fit_by_factor_free_sp_case,
)
from polaris_re.analytics.gam_cr_re_ti_conformance import (
    compare_cr_re_ti_free_sp_case,
    fit_cr_re_ti_free_sp_case,
)
from polaris_re.analytics.gam_gaussian_conformance import (
    compare_gaussian_free_sp_case,
    fit_gaussian_free_sp_case,
)
from polaris_re.analytics.gam_model import PolarisGAMFit
from polaris_re.analytics.gam_parametric_conformance import (
    compare_parametric_free_sp_case,
    fit_parametric_free_sp_case,
)
from polaris_re.analytics.gam_quasipoisson_conformance import (
    compare_quasipoisson_free_sp_case,
    fit_quasipoisson_free_sp_case,
)
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "DEFAULT_START_STUDY_CLAIM",
    "StartComparison",
    "best_of_two",
    "cr_re_ti_payload",
    "dispersion_draw_payload",
    "measure_start",
]

DEFAULT_START_STUDY_CLAIM = VerificationClaim(
    claim=(
        "fit_polaris_gam computes the free-scale REML selection from a recipe-only "
        "design with either the bounds-centre start or mgcv's initial.spg recipe "
        "evaluated on Polaris's own data/penalties; mgcv computes it via "
        "gam(method='REML'); compared on eta and edf_total (ADR-221, imported "
        "through each cell's own compare_*_free_sp_case)."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris free-scale search, start varied, vs mgcv free sp)",
            left_producer="gam_model.fit_polaris_gam, centre or initial.spg-seeded start",
            right_producer="mgcv gam(method='REML') free-sp fit, m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris free-scale search, start varied, vs mgcv free sp)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 3e's provenance declaration. Every quantity INDEPENDENT."""


@dataclass(frozen=True)
class StartComparison:
    """One (cell, start) reading, as the cell's own comparator reported it."""

    cell: str
    start: str
    max_abs_eta_diff: float
    edf_total_diff: float
    max_abs_log10_sp_diff: float
    agrees: bool
    own_reml_score: float
    at_bound: bool


def _read(c: Any, name: str) -> Any:
    return c[name] if isinstance(c, dict) else getattr(c, name)


def cr_re_ti_payload(probe: dict[str, Any], case: str) -> dict[str, Any]:
    """One named case of ``gam_cr_re_ti_probe.json`` (its ``cases`` map)."""
    return dict(probe["cases"][case])


def dispersion_draw_payload(probe: dict[str, Any]) -> dict[str, Any]:
    """Slice 3c's draw as a quasipoisson free-``sp`` payload: the recipe columns
    plus mgcv's own joint free-scale fit (``probe['joint']``)."""
    return {**probe, **probe["joint"]}


def best_of_two(a: StartComparison, b: StartComparison) -> StartComparison:
    """The reading of the two-start strategy "run both, keep the lower
    own-criterion REML score" (ADR-237's selection rule, never reading mgcv):
    returns whichever of ``a``/``b`` Polaris's OWN criterion scores lower."""
    best = a if a.own_reml_score <= b.own_reml_score else b
    return StartComparison(
        cell=a.cell,
        start=f"best of both by own score ({best.start})",
        max_abs_eta_diff=best.max_abs_eta_diff,
        edf_total_diff=best.edf_total_diff,
        max_abs_log10_sp_diff=best.max_abs_log10_sp_diff,
        agrees=best.agrees,
        own_reml_score=best.own_reml_score,
        at_bound=best.at_bound,
    )


type _Fit = Callable[..., PolarisGAMFit]
type _Compare = Callable[[PolarisGAMFit, Any], Any]


def measure_start(
    cell: str,
    payload: dict[str, Any],
    fit: _Fit,
    compare: _Compare,
    *,
    initial_sp_start: bool,
) -> StartComparison:
    """Fit ``payload``'s recipe with the chosen start and compare to mgcv."""
    polaris_fit = fit(payload, initial_sp_start=initial_sp_start)
    c = compare(polaris_fit, payload)
    return StartComparison(
        cell=cell,
        start="initial.spg-seeded" if initial_sp_start else "centre (default)",
        max_abs_eta_diff=float(_read(c, "max_abs_eta_diff")),
        edf_total_diff=float(_read(c, "edf_total_diff")),
        max_abs_log10_sp_diff=float(_read(c, "max_abs_log10_sp_diff")),
        agrees=bool(_read(c, "agrees")),
        own_reml_score=float(polaris_fit.reml_score),
        at_bound=bool(polaris_fit.at_bound),
    )


CELLS: dict[str, tuple[_Fit, _Compare]] = {
    "gaussian L1 (cr+by+ti)": (fit_gaussian_free_sp_case, compare_gaussian_free_sp_case),
    "gaussian factor-by L3": (fit_by_factor_free_sp_case, compare_by_factor_free_sp_case),
    "gaussian parametric L4": (fit_parametric_free_sp_case, compare_parametric_free_sp_case),
    "gaussian cr+re+ti L6": (fit_cr_re_ti_free_sp_case, compare_cr_re_ti_free_sp_case),
    "quasipoisson 3b draw": (fit_quasipoisson_free_sp_case, compare_quasipoisson_free_sp_case),
    "quasipoisson 3c draw": (fit_quasipoisson_free_sp_case, compare_quasipoisson_free_sp_case),
}
"""Every existing FREE-SCALE free-``sp`` conformance cell. Fixed-scale cells
(poisson re/cr+re+ti, fixed-phi quasipoisson, select=TRUE) are out of scope:
``dispersion_fixed=True`` is a different criterion branch."""

__all__ += ["CELLS"]

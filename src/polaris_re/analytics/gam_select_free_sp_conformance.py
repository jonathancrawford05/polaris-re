"""Free-``sp`` conformance for ``select = TRUE`` — mgcv-parity engine, PLAN
slice 7b.

ADR-217 (PLAN slice 7) verified two things about ``select = TRUE``'s double
penalty: the null-space penalty rule itself (Stage A), and a multi-term fit
at a FIXED, externally-supplied ``sp`` for all 7 blocks (Stage B,
:mod:`~polaris_re.analytics.gam_select_multiterm_conformance`). Neither
exercised ``fit_polaris_gam``'s own free-``sp`` search on the doubled
(7-block) structure ``select = True`` produces — this module is that
measurement, PLAN slice 7b (ADR-218).

``scripts/gam_select_multiterm_free_sp_probe.R`` builds the same shared
recipe (three-term formula, target-formula knots) as
``gam_select_multiterm_probe.R``/``gam_multiterm_free_sp_probe.R``, a
distinct RNG seed, and fits natively via ``gam(..., select = TRUE,
method = "REML")`` with free ``sp``. :func:`fit_select_free_sp_case` reads
back **only that recipe** (:class:`RSelectFreeSpRecipe` structurally has no
``eta``/``coef``/``sp``/``edf`` key) and fits with
:func:`~polaris_re.analytics.gam_model.fit_polaris_gam` on a
``ModelSpec(..., select=True)`` — selecting all 7 smoothing parameters via
:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`
(single-start, ADR-199) or
:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous_multistart`
(best-of-N, ADR-213, via ``fit_polaris_gam``'s ``multistart=`` parameter,
ADR-218) — never reading the R script's own fit.

Same asymmetry as
:mod:`~polaris_re.analytics.gam_model_conformance` (ADR-208 §3): ``sp`` is a
COMPARED quantity here, not a shared input.
"""

from dataclasses import dataclass, replace
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_model import PRODUCTION_LOG10_BOUNDS, PolarisGAMFit, fit_polaris_gam
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "SELECT_FREE_SP_MODEL_CLAIM",
    "RSelectFreeSpPayload",
    "RSelectFreeSpRecipe",
    "SelectFreeSpCaseComparison",
    "compare_select_free_sp_case",
    "fit_select_free_sp_case",
]

_N_BLOCKS = 7
"""Same count as :mod:`~polaris_re.analytics.gam_select_multiterm_conformance`
-- 2 (``s(AttdAge)``: existing + null) + 2 (``s(AttdAge,by=StudyYear_C)``:
existing + null) + 3 (``ti(...)``: its own existing 2 plus one null-space
block, dimension 1). ``select=True`` changes nothing about how many EXISTING
blocks a term carries."""

_AGREEMENT_TOLERANCE_EDF = 1.0
"""Same diagnostic tolerance :mod:`~polaris_re.analytics.gam_model_conformance`
uses for its own ``edf_total`` reading — reported, not gated on its own (see
that module's own note: a residual here is the finding, not a bar to tune,
Anchor 8)."""


class RSelectFreeSpRecipe(TypedDict):
    """The shared-recipe fields of
    ``scripts/gam_select_multiterm_free_sp_probe.R``'s output. Deliberately
    narrower than
    :class:`~polaris_re.analytics.gam_select_multiterm_conformance.RSelectMultiTermRecipe`:
    no ``"sp"`` key at all, because free ``sp`` is what this comparison is
    measuring, not a value either side is handed."""

    n: int
    AttdAge: list[float]
    PolYear: list[float]
    StudyYear_C: list[float]
    ExposCnt: list[float]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]


class RSelectFreeSpPayload(RSelectFreeSpRecipe):
    """The recipe plus ``mgcv``'s own free-``sp`` fit under ``select=TRUE``.
    Read by :func:`compare_select_free_sp_case` only;
    :func:`fit_select_free_sp_case` cannot see any of these keys through its
    narrower parameter type."""

    eta: list[float]
    coef: list[float]
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    converged: bool


SELECT_FREE_SP_MODEL_CLAIM = VerificationClaim(
    claim=(
        "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) assembles the "
        "three-term design under ModelSpec(select=True) from the shared "
        "recipe (AttdAge, PolYear, StudyYear_C, ExposCnt, y, the target "
        "formula's own knot vectors) via the already-independently-verified "
        "cr/by/ti basis producers plus gam_select_penalty.null_space_penalty "
        "(ADR-217), then selects all 7 log10(lambda) by minimizing "
        "gam_reml.reml_score_general via "
        "gam_reml_optimize.select_lambdas_continuous — never reading mgcv's "
        "own eta, coef, sp or edf; mgcv computes the identical three-term "
        "formula via gam(family=binomial(link='cloglog'), weights=ExposCnt, "
        "select=TRUE, method='REML') with free sp, selecting its own 7 "
        "smoothing parameters independently "
        "(scripts/gam_select_multiterm_free_sp_probe.R); compared on eta at "
        "the training design, log10(sp) per block, edf_total and per-term "
        "edf."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda (select=True)",
            right_producer=(
                "mgcv gam(select=TRUE, method='REML') free-sp fit, predict(m, type='link')"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per block",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda (7 blocks)",
            right_producer="mgcv's own log10(m$sp) at its free-sp select=TRUE REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp select=TRUE REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-term edf",
            left_producer="PolarisGAMFit.edf_per_term (hat-matrix diagonal sum per term span)",
            right_producer=(
                "mgcv's own summary(m)$s.table[, 'edf'], read positionally in formula order"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""PLAN slice 7b's provenance declaration (ADR-193). Every quantity is
INDEPENDENT: :func:`fit_select_free_sp_case`'s signature takes only
:class:`RSelectFreeSpRecipe`, which structurally excludes ``eta``/``coef``/
``sp``/``edf_total``/``term_edf`` (the ADR-193 mechanical test by type, same
discipline :data:`~polaris_re.analytics.gam_model_conformance.FREE_SP_MODEL_CLAIM`
uses). **The asymmetry** (ADR-208 §3, restated for ``select=TRUE``): ``sp``
is a compared quantity, not a shared input — both sides choose all 7 values
independently from the same criterion, already INDEPENDENT-verified at fixed
``sp`` under ``select=TRUE`` (ADR-217) and at free ``sp`` on the non-``select``
N=4 structure (ADR-208/210/211/212), so a disagreement here localises to
lambda selection on the 7-block structure specifically — not to the bases,
the null-space-penalty rule, the fitter or the criterion, all unchanged from
ADR-217's fixed-``sp`` measurement (this slice's own registered
prediction)."""


def fit_select_free_sp_case(
    r_case: RSelectFreeSpRecipe,
    *,
    multistart: bool = False,
    n_starts: int = 9,
    analytic_gradient: bool = False,
) -> PolarisGAMFit:
    """The independent Python producer: assemble the ``select=True`` design,
    select its own 7 lambdas, and fit — never reading ``mgcv``'s ``eta``/
    ``coef``/``sp``/``edf`` (:class:`RSelectFreeSpRecipe` has none of these
    keys; a caller passing a wider payload still cannot make this function
    see them, the ADR-193 mechanical test enforced structurally).

    Args:
        r_case: the shared recipe.
        multistart: when ``True``, uses
            :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous_multistart`
            (best-of-``n_starts``, ADR-213), passed through to
            :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`'s own
            ``multistart`` parameter (ADR-218), instead of its default single
            bounds-centre start — PLAN slice 7b's own registered prediction
            is that this structure needs it, the same way the N=4
            non-``select`` structure did (ADR-213/214). Default ``False`` so
            a caller can read both readings side by side;
            :func:`fit_polaris_gam`'s own default behaviour for every other
            caller is unchanged.
        n_starts: passed through when ``multistart=True``.
        analytic_gradient: passed through to
            :func:`~polaris_re.analytics.gam_model.fit_polaris_gam` (PLAN
            slice 7d). Default ``False`` — every existing caller unaffected.
    """
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    year_knots = tuple(float(v) for v in r_case["year_knots"])
    model = replace(_multiterm_model_spec(age_knots, year_knots), select=True)
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "StudyYear_C": np.asarray(r_case["StudyYear_C"], dtype=np.float64),
        "ExposCnt": np.asarray(r_case["ExposCnt"], dtype=np.float64),
    }
    y = np.asarray(r_case["y"], dtype=np.float64)
    fit = fit_polaris_gam(
        model,
        data,
        y,
        bounds=PRODUCTION_LOG10_BOUNDS,
        multistart=multistart,
        n_starts=n_starts,
        analytic_gradient=analytic_gradient,
    )
    if len(fit.design["penalty_blocks"]) != _N_BLOCKS:
        raise PolarisValidationError(
            f"fit_select_free_sp_case: assembled {len(fit.design['penalty_blocks'])} "
            f"penalty block(s) under select=True, expected {_N_BLOCKS}."
        )
    return fit


@dataclass(frozen=True)
class SelectFreeSpCaseComparison:
    """One free-``sp`` ``select=True`` case's verdict, every quantity
    :data:`SELECT_FREE_SP_MODEL_CLAIM` declares."""

    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_select_free_sp_case(
    python_fit: PolarisGAMFit, r_case: RSelectFreeSpPayload, *, tolerance: float = 1.0e-2
) -> SelectFreeSpCaseComparison:
    """Compare the independent Python free-``sp`` ``select=True`` fit against
    the R payload's own, on every quantity :data:`SELECT_FREE_SP_MODEL_CLAIM`
    declares.

    ``tolerance`` gates ``max_abs_log10_sp_diff`` — same convention as
    :func:`~polaris_re.analytics.gam_model_conformance.compare_free_sp_case`
    (Anchor 8: never silently widen a tolerance to call a gap closed; kept a
    parameter, not a baked-in module constant)."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_select_free_sp_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    r_log_sp = np.log10(np.asarray(r_case["sp"], dtype=np.float64))
    if r_log_sp.shape != python_fit.log_lambda.shape:
        raise PolarisValidationError(
            f"compare_select_free_sp_case: R sp has {r_log_sp.shape[0]} entries, "
            f"Python log_lambda has {python_fit.log_lambda.shape[0]} — both "
            f"sides must select the same number of smoothing parameters "
            f"({_N_BLOCKS} expected)."
        )
    r_term_edf = np.asarray(r_case["term_edf"], dtype=np.float64)
    python_term_edf = np.asarray(list(python_fit.edf_per_term.values()), dtype=np.float64)
    if r_term_edf.shape != python_term_edf.shape:
        raise PolarisValidationError(
            f"compare_select_free_sp_case: R term_edf has {r_term_edf.shape[0]} "
            f"entries, Python edf_per_term has {python_term_edf.shape[0]} — "
            "both must name the same number of smooth terms, in the same "
            "formula order."
        )

    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.eta)))
    max_abs_log10_sp_diff = float(np.max(np.abs(python_fit.log_lambda - r_log_sp)))
    edf_total_diff = float(python_fit.edf_total - r_case["edf_total"])
    max_abs_term_edf_diff = float(np.max(np.abs(python_term_edf - r_term_edf)))

    agrees = (
        python_fit.converged and bool(r_case["converged"]) and max_abs_log10_sp_diff < tolerance
    )
    return SelectFreeSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=max_abs_log10_sp_diff,
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=max_abs_term_edf_diff,
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        evidence=SELECT_FREE_SP_MODEL_CLAIM,
    )

"""Free-``sp`` conformance for ``PolarisGAM`` — mgcv-parity engine, PLAN slice
5b (``docs/WORK_ORDER_multi_term_assembly.md``).

ADR-206's ``MULTITERM_CLAIM`` compared ``eta`` at a FIXED, externally-supplied
``sp`` — a shared input to both sides. This module is the work order's own
"genuinely new measurement" (§2): the SAME three-term formula, but with each
side choosing its own smoothing parameters independently from the same
criterion. ``mgcv``'s own selection was a **shared input** to ADR-206; here it
is a **compared quantity** — the work order's own asymmetry (§3), restated in
the type via :data:`FREE_SP_MODEL_CLAIM`.

``scripts/gam_multiterm_free_sp_probe.R`` builds the shared recipe (the same
covariates and target-formula knot vectors as ``gam_multiterm_probe.R``, a
distinct RNG seed) and fits it natively via ``gam(..., method="REML")`` with
free ``sp``. :func:`fit_free_sp_case` reads back **only that recipe**
(:class:`RFreeSpRecipe` structurally has no ``eta``/``coef``/``sp``/``edf``
key) and fits with :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`,
which selects its own smoothing parameters via
:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`
(ADR-199) — never reading the R script's own fit.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_model import PolarisGAMFit, fit_polaris_gam
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "FREE_SP_MODEL_CLAIM",
    "FreeSpCaseComparison",
    "RFreeSpPayload",
    "RFreeSpRecipe",
    "compare_free_sp_case",
    "fit_free_sp_case",
]

_AGREEMENT_TOLERANCE_EDF = 1.0
"""Same order as slice 4 part B's own `edf_total` diagnostic tolerance
(`ADR-199`/`ADR-198` context: their `edf` diffs were already an order of
magnitude smaller than this after the continuous search) — reported
alongside `max_abs_log10_sp_diff`, which is the primary registered metric
(work order §4). Not gated on its own: `agrees` below is driven by whether
the search converged and by-eta agreement, per the work order's own framing
that a residual here IS the finding, not a pass/fail bar to tune (Anchor 8)."""

_SEARCH_BOUNDS = (-2.0, 11.0)
"""Wider than :data:`~polaris_re.analytics.gam_reml_optimize.DEFAULT_LOG10_BOUNDS`
(``(-2, 8)``). Measured, not guessed: this module's own tier-1 run found
``mgcv``'s own free-sp selection for this formula reaches
``log10(sp) ~ 9.87`` on the by-term's block — outside the default range
entirely. Widening the SEARCH DOMAIN so the optimiser can reach the region
``mgcv`` itself selects in is not the tolerance-tuning Anchor 8 forbids (no
comparison threshold changes here, and
:attr:`~polaris_re.analytics.gam_reml_optimize.ContinuousLambdaSelection.at_bound`
is still reported so a selection still pinned at either edge is visible,
not hidden)."""


class RFreeSpRecipe(TypedDict):
    """The shared-recipe fields of ``scripts/gam_multiterm_free_sp_probe.R``'s
    output. Deliberately narrower than
    :class:`~polaris_re.analytics.gam_multiterm_conformance.RMultiTermRecipe`:
    no ``"sp"`` key at all, because free ``sp`` is what this comparison is
    measuring, not a value either side is handed (see the module docstring's
    note on the asymmetry, work order §3)."""

    n: int
    AttdAge: list[float]
    PolYear: list[float]
    StudyYear_C: list[float]
    ExposCnt: list[float]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]


class RFreeSpPayload(RFreeSpRecipe):
    """The recipe plus ``mgcv``'s own free-sp fit. Read by
    :func:`compare_free_sp_case` only; :func:`fit_free_sp_case` cannot see any
    of these keys through its narrower parameter type."""

    eta: list[float]
    coef: list[float]
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    converged: bool


FREE_SP_MODEL_CLAIM = VerificationClaim(
    claim=(
        "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) assembles the "
        "three-term design from the shared recipe (AttdAge, PolYear, "
        "StudyYear_C, ExposCnt, y, the target formula's own knot vectors) via "
        "the already-independently-verified cr/by/ti basis producers, then "
        "selects its own log10(lambda) per block by minimizing "
        "gam_reml.reml_score_general via "
        "gam_reml_optimize.select_lambdas_continuous, and fits with "
        "gam_fit.penalized_irls_general — never reading mgcv's own eta, coef, "
        "sp or edf; mgcv computes the identical three-term formula via "
        "gam(family=binomial(link='cloglog'), weights=ExposCnt, "
        "method='REML') with free sp, selecting its own smoothing parameters "
        "independently (scripts/gam_multiterm_free_sp_probe.R); compared on "
        "eta at the training design, log10(sp) per block, edf_total and "
        "per-term edf."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda",
            right_producer="mgcv gam(method='REML') free-sp fit, predict(m, type='link')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per block",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda",
            right_producer="mgcv's own log10(m$sp) at its free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit",
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
"""ADR-208's provenance declaration for PLAN slice 5b. Every quantity is
INDEPENDENT: :func:`fit_free_sp_case`'s signature takes only
:class:`RFreeSpRecipe`, which structurally excludes ``eta``/``coef``/``sp``/
``edf_total``/``term_edf`` (the ADR-193 mechanical test by type, the same
discipline PR #202 established for ``gam_family_conformance`` and PR #210 for
``gam_multiterm_conformance``). **The asymmetry the work order names (§3):**
unlike ADR-206's ``MULTITERM_CLAIM``, where ``sp`` was a shared input supplied
to both sides, here ``sp`` is itself a compared quantity — both sides choose
it independently from the same criterion (Wood 2011's REML score, already
INDEPENDENT-verified at fixed sp by ADR-196/ADR-197 and at free sp on 2-block
designs by ADR-199), so a disagreement localises to lambda selection on a
multi-term (N=4-block) design specifically — not to the bases, the fitter or
the criterion, all of which are unchanged from ADR-206's fixed-sp
measurement (the work order's registered prediction, §4)."""


def fit_free_sp_case(r_case: RFreeSpRecipe) -> PolarisGAMFit:
    """The independent Python producer: assemble the design, select its own
    lambda, and fit — never reading ``mgcv``'s ``eta``/``coef``/``sp``/``edf``
    (:class:`RFreeSpRecipe` has none of these keys; a caller passing a wider
    payload still cannot make this function see them, the ADR-193 mechanical
    test enforced structurally)."""
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    year_knots = tuple(float(v) for v in r_case["year_knots"])
    model = _multiterm_model_spec(age_knots, year_knots)
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "StudyYear_C": np.asarray(r_case["StudyYear_C"], dtype=np.float64),
        "ExposCnt": np.asarray(r_case["ExposCnt"], dtype=np.float64),
    }
    y = np.asarray(r_case["y"], dtype=np.float64)
    return fit_polaris_gam(model, data, y, bounds=_SEARCH_BOUNDS)


@dataclass(frozen=True)
class FreeSpCaseComparison:
    """One free-``sp`` case's verdict, every quantity :data:`FREE_SP_MODEL_CLAIM`
    declares."""

    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_free_sp_case(
    python_fit: PolarisGAMFit, r_case: RFreeSpPayload, *, tolerance: float = 1.0e-2
) -> FreeSpCaseComparison:
    """Compare the independent Python free-``sp`` fit against the R payload's
    own free-``sp`` fit, on every quantity :data:`FREE_SP_MODEL_CLAIM` declares.

    ``tolerance`` gates ``max_abs_log10_sp_diff`` — the work order's own
    primary metric (§4's registered prediction: it should land in the same
    6.9e-04-to-9.8e-04 range ADR-199 measured at N=2). Kept as a parameter
    rather than a module constant with a single value baked in, so a caller
    reporting this comparison states explicitly what bar it was read against
    (Anchor 8: never silently widen a tolerance to call a gap closed).
    """
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_free_sp_case: R eta has shape {r_eta.shape}, Python eta "
            f"has shape {python_fit.eta.shape}."
        )
    r_log_sp = np.log10(np.asarray(r_case["sp"], dtype=np.float64))
    if r_log_sp.shape != python_fit.log_lambda.shape:
        raise PolarisValidationError(
            f"compare_free_sp_case: R sp has {r_log_sp.shape[0]} entries, "
            f"Python log_lambda has {python_fit.log_lambda.shape[0]} — both "
            "sides must select the same number of smoothing parameters."
        )
    r_term_edf = np.asarray(r_case["term_edf"], dtype=np.float64)
    python_term_edf = np.asarray(list(python_fit.edf_per_term.values()), dtype=np.float64)
    if r_term_edf.shape != python_term_edf.shape:
        raise PolarisValidationError(
            f"compare_free_sp_case: R term_edf has {r_term_edf.shape[0]} "
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
    return FreeSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=max_abs_log10_sp_diff,
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=max_abs_term_edf_diff,
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        evidence=FREE_SP_MODEL_CLAIM,
    )

"""``quasipoisson(log)`` at FREE ``sp`` against ``mgcv`` — capability ladder
slice **3b** (``docs/PLAN_mgcv_capability_ladder.md``).

Slice 3 (ADR-231) measured ``quasipoisson(log)``'s free-scale REML criterion at
the SCORE level only. This is the FIT-level companion: both sides select their
own four smoothing parameters AND their own dispersion, on the identical
three-term design ladder rung L1 verified, so the family is the only new thing.

**Claim, before the code (VERIFICATION_STANDARD §3.2)** —
:data:`QUASIPOISSON_FREE_SP_CLAIM_SENTENCE`. Every quantity is ``INDEPENDENT``:
:func:`fit_quasipoisson_free_sp_case` takes :class:`RQuasiPoissonFreeSpRecipe`,
which structurally excludes every ``mgcv``-produced key (the ADR-193 mechanical
test), and ``mgcv`` is handed no ``sp`` and no scale.

The response is an overdispersed count (negative binomial), so the estimated
dispersion is well above 1: a criterion that silently treated the family as
Poisson (scale fixed at 1) would select visibly different ``sp``.

The gate is ADR-221's committed criterion, imported and never redeclared
(Anchor W5). ``log10(sp)`` and the dispersion are reported, not gated.
"""

from dataclasses import replace
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_gaussian_conformance import gaussian_model_spec
from polaris_re.analytics.gam_model import PolarisGAMFit, fit_polaris_gam
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.analytics.gam_term_spec import ModelSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "QUASIPOISSON_FREE_SP_CLAIM",
    "QUASIPOISSON_FREE_SP_CLAIM_SENTENCE",
    "QuasiPoissonFreeSpCaseComparison",
    "RQuasiPoissonFreeSpPayload",
    "RQuasiPoissonFreeSpRecipe",
    "compare_quasipoisson_free_sp_case",
    "fit_quasipoisson_free_sp_case",
    "quasipoisson_model_spec",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's ``eta`` gate (``2e-2``), imported, not redeclared (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's ``edf_total`` gate (``1.0``), imported, not redeclared."""


class RQuasiPoissonFreeSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**. No ``sp`` and no
    scale key: both are what this comparison measures."""

    n: int
    AttdAge: list[float]
    PolYear: list[float]
    StudyYear_C: list[float]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]


class RQuasiPoissonFreeSpPayload(RQuasiPoissonFreeSpRecipe):
    """The recipe plus ``scripts/gam_quasipoisson_free_sp_probe.R``'s OWN fit.
    Read by :func:`compare_quasipoisson_free_sp_case` only."""

    eta: list[float]
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    term_labels: list[str]
    offset_gap: float
    coef: list[float]
    scale: float
    converged: bool


QUASIPOISSON_FREE_SP_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) assembles the "
    "three-term cr / cr-by / ti design ladder slice 1 verified, from the "
    "shared recipe (AttdAge, PolYear, StudyYear_C, an overdispersed count y, "
    "the target formula's own knot vectors), and selects its own log10(lambda) "
    "for all four penalty blocks under quasipoisson(log) by minimizing "
    "gam_reml.reml_score_general's free-scale branch via "
    "gam_reml_optimize.select_lambdas_continuous, then fits with "
    "gam_fit.penalized_irls_general — never reading mgcv's own eta, coef, sp, "
    "edf or scale; mgcv computes it via "
    "gam(family=quasipoisson(link='log'), method='REML') with free sp and its "
    "own estimated dispersion (scripts/gam_quasipoisson_free_sp_probe.R). "
    "Compared on eta at the training design, edf_total and per-term edf, gated "
    "on ADR-221's committed criterion (max_abs_eta_diff < 2e-2 and "
    "abs(edf_total_diff) < 1.0), IMPORTED and not redeclared; log10(sp) per "
    "block and per-term edf are reported, not gated. Coefficients are never "
    "compared (PLAN Anchor 2)."
)


QUASIPOISSON_FREE_SP_CLAIM = VerificationClaim(
    claim=QUASIPOISSON_FREE_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris quasipoisson free sp vs mgcv, free sp)",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda",
            right_producer="mgcv gam(method='REML') free-sp fit, m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per block (Polaris quasipoisson free sp vs mgcv, free sp)",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda",
            right_producer="mgcv's own log10(m$sp) at its free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris quasipoisson free sp vs mgcv, free sp)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-term edf (Polaris quasipoisson free sp vs mgcv, free sp)",
            left_producer="PolarisGAMFit.edf_per_term (hat-matrix diagonal sum per term span)",
            right_producer=(
                "mgcv's own summary(m)$s.table[, 'edf'], read positionally in formula order"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 3b's provenance declaration. Every quantity INDEPENDENT."""


def quasipoisson_model_spec(
    age_knots: tuple[float, ...], year_knots: tuple[float, ...]
) -> ModelSpec:
    """The three-term ``ModelSpec`` of ladder L1, under ``quasipoisson(log)``."""
    return replace(gaussian_model_spec(age_knots, year_knots), family="quasipoisson", link="log")


def fit_quasipoisson_free_sp_case(
    r_case: RQuasiPoissonFreeSpRecipe, *, multistart: bool = False, initial_sp_start: bool = False
) -> PolarisGAMFit:
    """The independent Python producer: assemble, select own lambda under the
    free-scale REML criterion, fit. Never reads ``mgcv``'s
    ``eta``/``coef``/``sp``/``edf``/``scale`` (the recipe type has none)."""
    model = quasipoisson_model_spec(
        tuple(float(v) for v in r_case["age_knots"]),
        tuple(float(v) for v in r_case["year_knots"]),
    )
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "StudyYear_C": np.asarray(r_case["StudyYear_C"], dtype=np.float64),
    }
    y = np.asarray(r_case["y"], dtype=np.float64)
    return fit_polaris_gam(model, data, y, multistart=multistart, initial_sp_start=initial_sp_start)


class QuasiPoissonFreeSpCaseComparison(TypedDict):
    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    offset_gap: float
    r_scale: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_quasipoisson_free_sp_case(
    python_fit: PolarisGAMFit, r_case: RQuasiPoissonFreeSpPayload
) -> QuasiPoissonFreeSpCaseComparison:
    """Compare on every quantity :data:`QUASIPOISSON_FREE_SP_CLAIM` declares.
    ``agrees`` is ADR-221's imported ``eta``/``edf_total`` criterion."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_quasipoisson_free_sp_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    r_log_sp = np.log10(np.atleast_1d(np.asarray(r_case["sp"], dtype=np.float64)))
    if r_log_sp.shape != python_fit.log_lambda.shape:
        raise PolarisValidationError(
            f"compare_quasipoisson_free_sp_case: R sp has {r_log_sp.size} "
            f"entries, Python log_lambda has {python_fit.log_lambda.size}."
        )
    r_term_edf = np.atleast_1d(np.asarray(r_case["term_edf"], dtype=np.float64))
    python_term_edf = np.asarray(list(python_fit.edf_per_term.values()), dtype=np.float64)
    if r_term_edf.shape != python_term_edf.shape:
        raise PolarisValidationError(
            f"compare_quasipoisson_free_sp_case: R term_edf has {r_term_edf.size} "
            f"entries, Python edf_per_term has {python_term_edf.size}."
        )
    # Positional pairing is only valid if both sides list the terms in the same
    # order: check mgcv's own s.table row names against Polaris's term labels
    # (the guard ladder slice 6 added, `_check_labels`), so a reordered spec or
    # s.table cannot silently compare the by-term against the ti-term.
    r_labels = tuple(np.atleast_1d(np.asarray(r_case["term_labels"], dtype=str)).tolist())
    python_labels = tuple(python_fit.edf_per_term)
    if r_labels != python_labels:
        raise PolarisValidationError(
            f"compare_quasipoisson_free_sp_case: mgcv's s.table rows are {r_labels}, "
            f"Polaris's edf_per_term keys are {python_labels}; per-term edf would be "
            "compared out of alignment."
        )

    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.eta)))
    max_abs_log10_sp_diff = float(np.max(np.abs(python_fit.log_lambda - r_log_sp)))
    edf_total_diff = float(python_fit.edf_total - r_case["edf_total"])
    max_abs_term_edf_diff = float(np.max(np.abs(python_term_edf - r_term_edf)))

    agrees = (
        python_fit.converged
        and bool(r_case["converged"])
        and max_abs_eta_diff < _ETA_TOLERANCE
        and abs(edf_total_diff) < _EDF_TOLERANCE
    )
    return QuasiPoissonFreeSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=max_abs_log10_sp_diff,
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=max_abs_term_edf_diff,
        offset_gap=float(r_case["offset_gap"]),
        r_scale=float(r_case["scale"]),
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        evidence=QUASIPOISSON_FREE_SP_CLAIM,
    )

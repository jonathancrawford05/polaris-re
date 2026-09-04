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

**PLAN slice 7e (ADR-221) re-gates ``agrees``** from a bare ``log10(sp)``
threshold to ``eta``/``edf`` (ADR-219 amendment 1 decision 4) — see
:data:`SELECT_FREE_SP_REGATE_CLAIM_SENTENCE` and
:class:`SelectFreeSpCaseComparison`.
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
    "SELECT_FREE_SP_REGATE_CLAIM_SENTENCE",
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
"""Reused verbatim from
:data:`~polaris_re.analytics.gam_model_conformance._AGREEMENT_TOLERANCE_EDF`
(same order as slice 4 part B's own ``edf_total`` diagnostic tolerance) —
**PLAN slice 7e (ADR-221) promotes this from reported-only to the ``edf``
half of the primary gate**, per ADR-219 amendment 1 decision 4. Not
re-derived for this slice: reusing an existing, already-precedented project
constant is the opposite of tuning a fresh number to make a fresh check pass
(Anchor 8). The best CONFIRMED-at-both-tiers reading this epic has produced
on this exact fixture (ADR-220, ``multistart=True, analytic_gradient=True``)
is ``edf_total_diff≈-0.258`` (tier 1) / ``-0.259`` (tier 3) — inside this
bound with room, not tuned to sit just under it."""

_AGREEMENT_TOLERANCE_ETA = 2.0e-2
"""**New in PLAN slice 7e (ADR-221)** — the ``eta`` half of the primary
acceptance gate ADR-219 amendment 1 decision 4 authorized
(``eta``/``edf`` primary, H-weighted distance a reported companion never a
gate). Derived the same way
:func:`~polaris_re.analytics.gam_uncertainty_conformance.compare_vc_case`
derives its own 2% element-wise tolerance: **headroom over a measured floor,
not a number chosen to make today's reading pass.** The floor is the best
CONFIRMED-at-both-tiers reading this epic has produced on this exact 7-block
structure — ``multistart=True, analytic_gradient=True`` (ADR-220,
:func:`~polaris_re.analytics.gam_model.fit_polaris_gam`'s own opt-in, best
combination measured, not this module's default) — ``max_abs_eta_diff``
``5.46e-03`` (tier 1) / ``5.46e-03`` (tier 3, `docs/CONFORMANCE_LEDGER.md`
slice 7d rows). ``0.02`` is ~3.7x that floor, the same order of headroom
:func:`~polaris_re.analytics.gam_uncertainty_conformance.compare_vc_case`'s
own docstring uses ("worst residual 0.730%, so 2% leaves under a factor of
three"). **This does not pass every search configuration** — a plain
single-start call (the module default) reads ``max_abs_eta_diff=0.4456``,
over 20x this bound, and still fails the new gate exactly as it failed the
old one. The gate discriminates a real production choice
(``multistart=True`` is required to pass it); it was not loosened until
everything passed."""


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


SELECT_FREE_SP_REGATE_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam, multistart=True) "
    "and mgcv's gam(select=TRUE, method='REML') independently select all 7 "
    "log10(lambda) for the identical three-term select=TRUE formula from "
    "the same shared recipe (ADR-217/ADR-218 asymmetry: sp is a compared "
    "quantity here, not a shared input); agreement is declared on whether "
    "the two selections produce the SAME FITTED SURFACE — max_abs_eta_diff "
    "< 2e-2 and abs(edf_total_diff) < 1.0 — not on whether they land at the "
    "same log10(lambda), which is reported as a diagnostic alongside a "
    "companion H-weighted rho-distance (MEASUREMENT (own criterion), never "
    "a gate) rather than compared directly."
)
"""**PLAN slice 7e (ADR-221), written before the code per
``docs/VERIFICATION_STANDARD.md`` §3.2.** Deliberately narrower than
:data:`SELECT_FREE_SP_MODEL_CLAIM`'s own claim sentence in exactly the way
ADR-219 amendment 1's marketing-constraint decision 1 requires: it names one
structure (this three-term ``select=True`` formula), one search
configuration (``multistart=True`` — the plain single-start default still
fails this gate, see :data:`_AGREEMENT_TOLERANCE_ETA`), and states the two
tolerances explicitly rather than leaving "agrees" undefined. It replaces
the OLD implicit claim (bare ``max_abs_log10_sp_diff < 1e-2``, the
:data:`SELECT_FREE_SP_MODEL_CLAIM` module's original ``agrees``) rather than
adding to it — :func:`compare_select_free_sp_case`'s ``agrees`` now means
this sentence, and the old criterion is reported under
:attr:`SelectFreeSpCaseComparison.agrees_log10_sp` so every historical
reading stays legible under both gates side by side
(``docs/CONFORMANCE_LEDGER.md``). **No unqualified "mgcv parity" claim is
made anywhere by this sentence or by the code below** — it names the
quantity, the tolerance and the structure, per ADR-219 amendment 1's second
consequence; conformance level 4 (ADR-190) still genuinely disagrees and
this slice does nothing to it."""


@dataclass(frozen=True)
class SelectFreeSpCaseComparison:
    """One free-``sp`` ``select=True`` case's verdict, every quantity
    :data:`SELECT_FREE_SP_MODEL_CLAIM` declares.

    **PLAN slice 7e (ADR-221):** :attr:`agrees` is now driven by ``eta``/
    ``edf`` (:data:`SELECT_FREE_SP_REGATE_CLAIM_SENTENCE`), replacing the
    prior ``log10(sp)``-only gate. :attr:`agrees_log10_sp` preserves that
    prior criterion, reported and never re-used to drive :attr:`agrees`, so
    a caller (or the ledger) can read a result under both gates at once."""

    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    at_bound: bool
    converged: bool
    agrees: bool
    """The PRIMARY gate as of ADR-221: ``converged and max_abs_eta_diff <
    eta_tolerance and abs(edf_total_diff) < edf_tolerance``. Never driven by
    ``log10(sp)`` — see :attr:`agrees_log10_sp` for that reading."""
    agrees_log10_sp: bool
    """The gate :attr:`agrees` replaced (``converged and
    max_abs_log10_sp_diff < log10_sp_tolerance``) — kept, not deleted, so
    every historical row can be read under both criteria (ADR-221 DoD)."""
    eta_tolerance: float
    edf_tolerance: float
    log10_sp_tolerance: float
    evidence: VerificationClaim


def compare_select_free_sp_case(
    python_fit: PolarisGAMFit,
    r_case: RSelectFreeSpPayload,
    *,
    tolerance: float = 1.0e-2,
    eta_tolerance: float = _AGREEMENT_TOLERANCE_ETA,
    edf_tolerance: float = _AGREEMENT_TOLERANCE_EDF,
) -> SelectFreeSpCaseComparison:
    """Compare the independent Python free-``sp`` ``select=True`` fit against
    the R payload's own, on every quantity :data:`SELECT_FREE_SP_MODEL_CLAIM`
    declares.

    **PLAN slice 7e (ADR-221) re-gate.** ``agrees`` is now primary on
    ``eta``/``edf`` (:data:`SELECT_FREE_SP_REGATE_CLAIM_SENTENCE`) — the
    fitted surface, not the smoothing-parameter vector. ``tolerance`` (kept,
    unrenamed, for backward compatibility with existing callers) still gates
    the reported-only :attr:`SelectFreeSpCaseComparison.agrees_log10_sp`;
    Anchor 8 forbids silently widening it, so it is kept a parameter rather
    than folded away. ``eta_tolerance``/``edf_tolerance`` default to the
    module's own derived constants
    (:data:`_AGREEMENT_TOLERANCE_ETA`/:data:`_AGREEMENT_TOLERANCE_EDF`) and
    are exposed the same way, for the same reason."""
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

    both_converged = python_fit.converged and bool(r_case["converged"])
    agrees_log10_sp = both_converged and max_abs_log10_sp_diff < tolerance
    agrees = (
        both_converged and max_abs_eta_diff < eta_tolerance and abs(edf_total_diff) < edf_tolerance
    )
    return SelectFreeSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=max_abs_log10_sp_diff,
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=max_abs_term_edf_diff,
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        agrees_log10_sp=agrees_log10_sp,
        eta_tolerance=eta_tolerance,
        edf_tolerance=edf_tolerance,
        log10_sp_tolerance=tolerance,
        evidence=SELECT_FREE_SP_MODEL_CLAIM,
    )

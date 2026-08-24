"""Stage-B, multi-term conformance -- mgcv-parity engine, slice 5's remaining scope.

``docs/CONTINUATION_mgcv_parity_engine.md``, what remains of slice 5: "Nothing has
run Stage B / Anchor 2's own criteria (the MI contrast, ``eta``) on either
[``ti(AttdAge, PolYear)``] or the ``by`` term -- that is what unblocks both slice 4
part B's N>2 extension and Anchor 5's absolute/relative demonstration, and it is
what remains of slice 5." This module is that multi-term model.

Three of the target formula's eight terms (``docs/PLAN_mgcv_parity_engine.md``
Section 1), fit TOGETHER, at a FIXED, externally-supplied ``sp`` for every block --
the epic's first multi-term mgcv-native model::

    y ~ s(AttdAge, k=13, bs="cr")                       # reference age
      + s(AttdAge, by=StudyYear_C, k=13, bs="cr")        # the MI term (ADR-200)
      + ti(AttdAge, PolYear, k=(13,6), bs="cr")          # age x duration (ADR-205)
    family = binomial(link="cloglog"), weights = ExposCnt  # Anchor 5, absolute idiom

``scripts/gam_multiterm_probe.R`` builds the shared recipe (``AttdAge``,
``PolYear``, ``StudyYear_C``, ``ExposCnt``, ``y``, the target formula's own knot
vectors, and the fixed ``sp`` for all four blocks) deterministically and fits it
natively. :func:`fit_multiterm_case` reads back **only that recipe** and assembles
its own design from the three ALREADY-INDEPENDENTLY-VERIFIED basis producers
(:func:`~polaris_re.analytics.gam_stage_a.build_python_cr_term`,
:func:`~polaris_re.analytics.gam_stage_a.build_python_ti_term` -- ADR-194,
ADR-200, ADR-205) and fits with
:func:`~polaris_re.analytics.gam_fit.penalized_irls_general` at the SAME fixed
``sp`` -- never reading the R script's own ``eta``/``coef`` (:class:`RMultiTermRecipe`
structurally has neither key, the same ADR-193 mechanical-test-by-type PR #202
review established for :mod:`~polaris_re.analytics.gam_family_conformance`).

**Anchor 2, restated for a multi-term model specifically.** A model with a
numeric-``by`` smooth (unconstrained, ADR-200) and a ``ti()`` tensor (its own
two-level rescaling, ADR-205) gives ``mgcv`` even more freedom to reparameterise
than a single-term case does. ``coef`` travels in the R payload for diagnostic
reading only; :data:`MULTITERM_CLAIM` does not name it, and no function in this
module compares it.

**What this does NOT yet do.** Anchor 2's *primary* metric is the MI contrast on
a pinned prediction grid, evaluated away from the training rows; this module
compares ``eta`` at the training design only, the same regime slice 3's
:data:`~polaris_re.analytics.gam_family_conformance.FAMILY_CLAIM` and slice 4's
``REML_SCORE_CLAIM`` already used. Predicting at new covariate values needs the
same knot vector and (for the reference and MI terms) the same identifiability
constraint transform re-applied at unseen ``x`` -- a genuine additional question
this module does not answer, named rather than assumed (CLAUDE.md: mark the
uncertainty). Extending this comparator to a held-out grid is separate follow-on
work, not a gap in what is claimed here.
"""

from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import Family, binomial_cloglog
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_stage_a import build_python_cr_term, build_python_ti_term
from polaris_re.analytics.gam_term_spec import TermSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "MULTITERM_CLAIM",
    "MultiTermCaseComparison",
    "MultiTermDesign",
    "RMultiTermPayload",
    "RMultiTermRecipe",
    "assemble_multiterm_design",
    "compare_multiterm_case",
    "fit_multiterm_case",
]

_AGREEMENT_TOLERANCE = 1e-9
"""Same order as Stage A's and slice 3's -- an exact comparison at fixed sp over
a shared, well-conditioned design (Anchor 8: derived from the existing verified
regime, not chosen to make this check green)."""

_REF_LABEL = "s(AttdAge)"
_BY_LABEL = "s(AttdAge,by=StudyYear_C)"
_TI_LABEL = "ti(AttdAge,PolYear)"


class RMultiTermRecipe(TypedDict):
    """The shared-recipe fields of ``scripts/gam_multiterm_probe.R``'s output --
    everything both sides need to pose the SAME multi-term regression problem,
    and nothing either side computed. :func:`fit_multiterm_case` is typed to
    accept only this, not :class:`RMultiTermPayload` -- the same structural
    mechanical-test enforcement
    :class:`~polaris_re.analytics.gam_family_conformance.RFamilyCaseRecipe`
    established (PR #202 review [P1])."""

    n: int
    AttdAge: list[float]
    PolYear: list[float]
    StudyYear_C: list[float]
    ExposCnt: list[float]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]
    sp: list[float]


class RMultiTermPayload(RMultiTermRecipe):
    """The recipe plus the R script's OWN fit. Read by
    :func:`compare_multiterm_case` only; :func:`fit_multiterm_case` cannot see
    ``eta``/``coef`` at all through its narrower parameter type."""

    eta: list[float]
    coef: list[float]
    converged: bool


MULTITERM_CLAIM = VerificationClaim(
    claim=(
        "polaris_re assembles the three-term design (build_python_cr_term for "
        "the reference s(AttdAge,k=13,bs='cr') term, build_python_cr_term(by=...) "
        "for the MI term s(AttdAge,by=StudyYear_C,k=13,bs='cr'), and "
        "build_python_ti_term for ti(AttdAge,PolYear,k=(13,6),bs='cr')) from the "
        "shared recipe (AttdAge, PolYear, StudyYear_C, the target formula's own "
        "knot vectors) and fits it with gam_fit.penalized_irls_general at a "
        "FIXED, externally-supplied sp (one per block) under binomial/cloglog "
        "with ExposCnt weights; mgcv computes the identical three-term model "
        "natively via gam(y ~ s(AttdAge,k=13,bs='cr') + "
        "s(AttdAge,by=StudyYear_C,k=13,bs='cr') + "
        "ti(AttdAge,PolYear,k=c(13,6),bs='cr'), family=binomial(link='cloglog'), "
        "weights=ExposCnt, sp=sp_fixed); compared on eta at the training design."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta",
            left_producer=(
                "gam_fit.penalized_irls_general over a design assembled from "
                "gam_basis_cr's independently-verified cr/by/ti producers"
            ),
            right_producer=(
                "mgcv::predict(m, type='link') on a gam() fit of the identical "
                "three-term formula at the same fixed sp"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 5's remaining-scope provenance declaration (ADR-193). ``eta`` is
INDEPENDENT: :func:`fit_multiterm_case` never reads
``scripts/gam_multiterm_probe.R``'s ``eta`` or ``coef`` fields, only the shared
recipe -- the mechanical test applied to its signature (:class:`RMultiTermRecipe`
structurally excludes both). This is the first multi-term mgcv-native Stage-B
result in the epic: every prior Stage-B claim
(:data:`~polaris_re.analytics.gam_family_conformance.FAMILY_CLAIM`,
``REML_SCORE_CLAIM``) fit either a single supplied ``raw``/``paraPen`` design or a
synthetic Fourier one, never a design built from the epic's own independently-
verified ``cr``/``by``/``ti`` basis producers together."""


class MultiTermDesign(TypedDict):
    """The assembled full design and its four independently-scaled penalty
    blocks, in the SAME column/block order ``mgcv`` assigns to this formula:
    intercept (unpenalized), reference age, MI by-term, ti() block 1, ti() block
    2."""

    x: np.ndarray
    penalty_blocks: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]


def assemble_multiterm_design(r_case: RMultiTermRecipe) -> MultiTermDesign:
    """Build the three-term design from the shared recipe -- never from
    ``mgcv``'s own ``X``/``coef`` (there is none in the recipe to read;
    :class:`RMultiTermRecipe` has no such key).

    Column order matches ``mgcv``'s own formula-order convention for
    ``y ~ s(AttdAge) + s(AttdAge, by=StudyYear_C) + ti(AttdAge, PolYear)`` with no
    other parametric term: an intercept column first (mgcv always fits one unless
    the formula suppresses it), then each smooth term's own columns in formula
    order. Each of the four penalty blocks is padded with zeros outside its own
    term's columns, the same convention
    :class:`~polaris_re.analytics.experience_mgcv_conformance.DesignExport`'s
    ``s_age``/``s_year`` and
    :func:`~polaris_re.analytics.gam_reml_optimize.penalized_fit_and_score`'s
    ``penalty_blocks`` already use.
    """
    age = np.asarray(r_case["AttdAge"], dtype=np.float64)
    year = np.asarray(r_case["PolYear"], dtype=np.float64)
    by = np.asarray(r_case["StudyYear_C"], dtype=np.float64)
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    year_knots = tuple(float(v) for v in r_case["year_knots"])
    n = age.shape[0]

    ref_term = TermSpec(
        label=_REF_LABEL,
        variables=("AttdAge",),
        basis="cr",
        k=(len(age_knots),),
        knots=(("AttdAge", age_knots),),
    )
    by_term = TermSpec(
        label=_BY_LABEL,
        variables=("AttdAge",),
        basis="cr",
        k=(len(age_knots),),
        knots=(("AttdAge", age_knots),),
        by="StudyYear_C",
    )
    ti_term = TermSpec(
        label=_TI_LABEL,
        variables=("AttdAge", "PolYear"),
        basis="ti",
        k=(len(age_knots), len(year_knots)),
        knots=(("AttdAge", age_knots), ("PolYear", year_knots)),
    )

    ref = build_python_cr_term(age, ref_term)
    by_extract = build_python_cr_term(age, by_term, by=by)
    ti = build_python_ti_term(age, year, ti_term)

    intercept = np.ones((n, 1), dtype=np.float64)
    x = np.hstack([intercept, ref.design, by_extract.design, ti.design])
    p_total = x.shape[1]

    def _pad(width_start: int, block: np.ndarray) -> np.ndarray:
        width = block.shape[0]
        padded = np.zeros((p_total, p_total), dtype=np.float64)
        padded[width_start : width_start + width, width_start : width_start + width] = block
        return padded

    ref_start = 1
    by_start = ref_start + ref.design.shape[1]
    ti_start = by_start + by_extract.design.shape[1]
    # ti()'s two penalty blocks (ADR-205) both apply to the SAME ti() column
    # range -- two different penalties on one tensor design, not two disjoint
    # column ranges -- so both pad at ti_start, not sequentially.

    penalty_blocks = (
        _pad(ref_start, ref.s[0]),
        _pad(by_start, by_extract.s[0]),
        _pad(ti_start, ti.s[0]),
        _pad(ti_start, ti.s[1]),
    )
    return MultiTermDesign(x=x, penalty_blocks=penalty_blocks)


def fit_multiterm_case(r_case: RMultiTermRecipe) -> tuple[GeneralIRLSFit, MultiTermDesign]:
    """The independent Python producer: assemble the design, then fit it at the
    recipe's own fixed ``sp`` -- never reading ``mgcv``'s ``eta``/``coef``
    (:class:`RMultiTermRecipe` has neither key; a caller passing a wider payload
    still cannot make this function see them, the ADR-193 mechanical test
    enforced structurally, PR #202 review [P1])."""
    sp = r_case["sp"]
    if len(sp) != 4:
        raise PolarisValidationError(
            f"fit_multiterm_case: expected 4 sp values (reference, by, ti#1, ti#2), got {len(sp)}."
        )
    design = assemble_multiterm_design(r_case)
    penalty = np.zeros_like(design["penalty_blocks"][0])
    for sp_j, block in zip(sp, design["penalty_blocks"], strict=True):
        penalty = penalty + float(sp_j) * block

    family: Family = binomial_cloglog()
    y = np.asarray(r_case["y"], dtype=np.float64)
    weights = np.asarray(r_case["ExposCnt"], dtype=np.float64)
    fit = penalized_irls_general(design["x"], y, family=family, penalty=penalty, weights=weights)
    return fit, design


class MultiTermCaseComparison(TypedDict):
    max_abs_eta_diff: float
    agrees: bool
    evidence: VerificationClaim


def compare_multiterm_case(
    python_fit: GeneralIRLSFit, r_case: RMultiTermPayload
) -> MultiTermCaseComparison:
    """Compare the independent Python fit's ``eta`` against the R payload's own
    ``eta`` -- the only quantity :data:`MULTITERM_CLAIM` declares."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_multiterm_case: R eta has shape {r_eta.shape}, Python eta "
            f"has shape {python_fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.eta)))
    return MultiTermCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        agrees=max_abs_eta_diff < _AGREEMENT_TOLERANCE,
        evidence=MULTITERM_CLAIM,
    )

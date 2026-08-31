"""Stage-B, multi-term conformance for an ``sz`` term -- mgcv-parity engine,
PLAN slice 6b (``docs/PLAN_mgcv_parity_engine.md``).

ADR-215 closed slice 6's Stage A: :func:`~polaris_re.analytics.gam_stage_a.build_python_sz_term`
agrees with ``smoothCon(bs="sz", absorb.cons=TRUE)`` to float round-trip
precision on an isolated term. **Nothing yet fits a multi-term model
containing an ``sz`` term and compares it against mgcv's own native fit** --
the same gap ADR-206 closed for ``ti()``/numeric-``by`` (slice 5's remaining
scope). This module is that comparison for ``sz``, built the identical way::

    y ~ s(AttdAge, k=13, bs="cr")                                  # reference age
      + s(FaceSize, AttdAge, k=13, bs="sz", xt=list(bs="cr"))       # level deviations
    family = binomial(link="cloglog"), weights = ExposCnt            # Anchor 5, absolute

``s(FaceSize, AttdAge, ...)`` is the target formula's own first ``sz`` term
verbatim (PLAN Section 1), at its own AttdAge k=13 knot vector -- the same
knots ADR-215's "sz-target-attdage-k13" Stage-A case already used.

``scripts/gam_multiterm_sz_probe.R`` builds the shared recipe (``AttdAge``,
``FaceSize``'s 0-indexed level code, ``ExposCnt``, ``y``, the reference
term's own knot vector, and the fixed ``sp`` for all three blocks --
1 for the reference ``cr`` term, 2 for the two-level ``sz`` term, ADR-215's
own "one block per factor level" contract) deterministically and fits it
natively. :func:`fit_sz_multiterm_case` reads back **only that recipe** and
assembles its own design from :func:`~polaris_re.analytics.gam_model.assemble_model_design`
(PLAN slice 5b, generalised to ``"sz"`` terms by this slice) -- built from
the two ALREADY-INDEPENDENTLY-VERIFIED basis producers
(:func:`~polaris_re.analytics.gam_stage_a.build_python_cr_term`,
:func:`~polaris_re.analytics.gam_stage_a.build_python_sz_term` -- ADR-194,
ADR-215) -- and fits with
:func:`~polaris_re.analytics.gam_fit.penalized_irls_general` at the SAME
fixed ``sp``, never reading the R script's own ``eta``/``coef``
(:class:`RSzMultiTermRecipe` structurally has neither key, the same
ADR-193 mechanical-test-by-type discipline
:class:`~polaris_re.analytics.gam_multiterm_conformance.RMultiTermRecipe`
already established).

**Anchor 2, restated for an ``sz``-carrying multi-term model specifically.**
``mgcv``'s sum-to-zero constraint on a factor-smooth interaction is at least
as much reparameterisation freedom as the ``ti()``/numeric-``by`` terms
ADR-206 already measured. ``coef`` travels in the R payload for diagnostic
reading only; :data:`SZ_MULTITERM_CLAIM` does not name it, and no function
in this module compares it.

**Not in scope here** (PLAN slice 6b's own scope line): extending
:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`
to an ``sz``-shaped block structure (one smoothing parameter per factor
level) -- this module fits at a FIXED, externally-supplied ``sp`` only, the
same regime ADR-206's ``MULTITERM_CLAIM`` used before ADR-208 built the
free-``sp`` counterpart for the ``ti``/``by`` model.
"""

from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import Family, binomial_cloglog
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_model import ModelDesign, assemble_model_design
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "SZ_MULTITERM_CLAIM",
    "RSzMultiTermPayload",
    "RSzMultiTermRecipe",
    "SzMultiTermCaseComparison",
    "compare_sz_multiterm_case",
    "fit_sz_multiterm_case",
]

_AGREEMENT_TOLERANCE = 1e-9
"""Same order as slice 5's `MULTITERM_CLAIM` (`gam_multiterm_conformance.py`)
-- an exact comparison at fixed sp over a shared, well-conditioned design
(Anchor 8: derived from the existing verified regime, not chosen to make
this check green)."""

_REF_LABEL = "s(AttdAge)"
_SZ_LABEL = "s(FaceSize,AttdAge)"


class RSzMultiTermRecipe(TypedDict):
    """The shared-recipe fields of ``scripts/gam_multiterm_sz_probe.R``'s
    output -- everything both sides need to pose the SAME two-term
    regression problem, and nothing either side computed. :func:`fit_sz_multiterm_case`
    is typed to accept only this, not :class:`RSzMultiTermPayload` -- the
    same structural mechanical-test enforcement
    :class:`~polaris_re.analytics.gam_multiterm_conformance.RMultiTermRecipe`
    already established (PR #202/#210 review pattern)."""

    n: int
    AttdAge: list[float]
    face_size_group: list[int]
    face_size_n_levels: int
    ExposCnt: list[float]
    y: list[float]
    age_knots: list[float]
    sp: list[float]


class RSzMultiTermPayload(RSzMultiTermRecipe):
    """The recipe plus the R script's OWN fit. Read by
    :func:`compare_sz_multiterm_case` only; :func:`fit_sz_multiterm_case`
    cannot see ``eta``/``coef`` at all through its narrower parameter type."""

    eta: list[float]
    coef: list[float]
    converged: bool


SZ_MULTITERM_CLAIM = VerificationClaim(
    claim=(
        "polaris_re assembles the two-term design "
        "(gam_model.assemble_model_design, built from build_python_cr_term "
        "for the reference s(AttdAge,k=13,bs='cr') term and "
        "build_python_sz_term for s(FaceSize,AttdAge,k=13,bs='sz',"
        "xt=list(bs='cr'))) from the shared recipe (AttdAge, FaceSize's "
        "0-indexed level code, the reference term's own knot vector) and "
        "fits it with gam_fit.penalized_irls_general at a FIXED, "
        "externally-supplied sp (one per block: 1 for the reference term, "
        "2 for the two-level sz term) under binomial/cloglog with ExposCnt "
        "weights; mgcv computes the identical two-term model natively via "
        "gam(y ~ s(AttdAge,k=13,bs='cr') + s(FaceSize,AttdAge,k=13,bs='sz',"
        "xt=list(bs='cr')), family=binomial(link='cloglog'), "
        "weights=ExposCnt, sp=sp_fixed); compared on eta at the training "
        "design."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta",
            left_producer=(
                "gam_fit.penalized_irls_general over a design assembled from "
                "gam_model.assemble_model_design's independently-verified "
                "cr/sz producers"
            ),
            right_producer=(
                "mgcv::predict(m, type='link') on a gam() fit of the identical "
                "two-term formula at the same fixed sp"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 6b's provenance declaration (ADR-193). ``eta`` is INDEPENDENT:
:func:`fit_sz_multiterm_case` never reads ``scripts/gam_multiterm_sz_probe.R``'s
``eta`` or ``coef`` fields, only the shared recipe -- the mechanical test
applied to its signature (:class:`RSzMultiTermRecipe` structurally excludes
both). This is the first multi-term mgcv-native Stage-B result in the epic
to include an ``sz`` term -- every prior multi-term Stage-B claim
(:data:`~polaris_re.analytics.gam_multiterm_conformance.MULTITERM_CLAIM`,
:data:`~polaris_re.analytics.gam_model_conformance.FREE_SP_MODEL_CLAIM`) fit
only ``cr``/``ti``/numeric-``by`` terms."""


def _sz_multiterm_model_spec(age_knots: tuple[float, ...], n_levels: int) -> ModelSpec:
    """The two-term ``ModelSpec`` this module fits, expressed in the shape
    :func:`~polaris_re.analytics.gam_model.assemble_model_design` (PLAN
    slice 5b, generalised to ``sz`` by slice 6b) takes."""
    ref_term = TermSpec(
        label=_REF_LABEL,
        variables=("AttdAge",),
        basis="cr",
        k=(len(age_knots),),
        knots=(("AttdAge", age_knots),),
    )
    sz_term = TermSpec(
        label=_SZ_LABEL,
        variables=("FaceSize", "AttdAge"),
        basis="sz",
        k=(len(age_knots),),
        knots=(("AttdAge", age_knots),),
        n_levels=n_levels,
    )
    return ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(ref_term, sz_term),
        weights_column="ExposCnt",
    )


def fit_sz_multiterm_case(r_case: RSzMultiTermRecipe) -> tuple[GeneralIRLSFit, ModelDesign]:
    """The independent Python producer: assemble the design, then fit it at
    the recipe's own fixed ``sp`` -- never reading ``mgcv``'s ``eta``/``coef``
    (:class:`RSzMultiTermRecipe` has neither key; a caller passing a wider
    payload still cannot make this function see them, the ADR-193 mechanical
    test enforced structurally)."""
    n_levels = int(r_case["face_size_n_levels"])
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    model = _sz_multiterm_model_spec(age_knots, n_levels)
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "FaceSize": np.asarray(r_case["face_size_group"], dtype=np.int64),
    }
    design = assemble_model_design(model, data)

    sp = r_case["sp"]
    n_blocks = 1 + n_levels
    if len(sp) != n_blocks:
        raise PolarisValidationError(
            f"fit_sz_multiterm_case: expected {n_blocks} sp values (1 "
            f"reference + {n_levels} sz factor levels), got {len(sp)}."
        )
    penalty = np.zeros_like(design["penalty_blocks"][0])
    for sp_j, block in zip(sp, design["penalty_blocks"], strict=True):
        penalty = penalty + float(sp_j) * block

    family: Family = binomial_cloglog()
    y = np.asarray(r_case["y"], dtype=np.float64)
    weights = np.asarray(r_case["ExposCnt"], dtype=np.float64)
    fit = penalized_irls_general(design["x"], y, family=family, penalty=penalty, weights=weights)
    return fit, design


class SzMultiTermCaseComparison(TypedDict):
    max_abs_eta_diff: float
    agrees: bool
    evidence: VerificationClaim


def compare_sz_multiterm_case(
    python_fit: GeneralIRLSFit, r_case: RSzMultiTermPayload
) -> SzMultiTermCaseComparison:
    """Compare the independent Python fit's ``eta`` against the R payload's
    own ``eta`` -- the only quantity :data:`SZ_MULTITERM_CLAIM` declares."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_sz_multiterm_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.eta)))
    return SzMultiTermCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        agrees=max_abs_eta_diff < _AGREEMENT_TOLERANCE,
        evidence=SZ_MULTITERM_CLAIM,
    )

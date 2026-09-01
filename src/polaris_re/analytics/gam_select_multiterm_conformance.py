"""Stage-B conformance for ``select = TRUE`` on a multi-term model -- mgcv-parity
engine, PLAN slice 7.

The same three-term model :mod:`~polaris_re.analytics.gam_multiterm_conformance`
(slice 5, ADR-206) already verified at fixed ``sp``::

    y ~ s(AttdAge, k=13, bs="cr")                       # reference age
      + s(AttdAge, by=StudyYear_C, k=13, bs="cr")        # the MI term (ADR-200)
      + ti(AttdAge, PolYear, k=(13,6), bs="cr")          # age x duration (ADR-205)
    family = binomial(link="cloglog"), weights = ExposCnt  # Anchor 5, absolute idiom

fit with ``ModelSpec.select=True`` (PLAN slice 7, ADR-217): each term's own
null-space penalty (:func:`~polaris_re.analytics.gam_select_penalty.null_space_penalty`)
is appended after its existing block(s), taking the block count from 4 to 7
(2 + 2 + 3 -- one extra block per term, never one per existing penalty,
measured for this exact three-term shape by
``scripts/gam_select_penalty_probe.R``'s ``ti-attdage-polyear`` case).

``scripts/gam_select_multiterm_probe.R`` builds the identical shared recipe
``gam_multiterm_probe.R`` uses (same knots, same covariate recipe shape,
distinct RNG seed) and fits natively with ``select = TRUE`` at a FIXED sp for
all 7 blocks. :func:`fit_select_multiterm_case` reads back **only that
recipe** and assembles its own design via
:func:`~polaris_re.analytics.gam_model.assemble_model_design` with
``ModelSpec.select=True`` -- reusing the three already-independently-verified
basis producers (ADR-194, ADR-200, ADR-205) AND the already-independently-
verified null-space-penalty producer (ADR-217) unchanged -- then fits with
:func:`~polaris_re.analytics.gam_fit.penalized_irls_general` at the SAME
fixed ``sp``, never reading the R script's own ``eta``/``coef``.

**What this does NOT yet do.** Free-``sp`` selection under ``select=True``
(extending :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`
to the doubled block count this module's own fixed-sp case already exercises)
is PLAN slice 7's own remaining scope, named rather than attempted here --
the same Stage-A-then-fixed-sp-Stage-B-then-free-sp progression slices 2/3/4/5
each used.
"""

from dataclasses import replace
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import Family, binomial_cloglog
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_model import assemble_model_design
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "SELECT_MULTITERM_CLAIM",
    "RSelectMultiTermPayload",
    "RSelectMultiTermRecipe",
    "SelectMultiTermCaseComparison",
    "compare_select_multiterm_case",
    "fit_select_multiterm_case",
]

_AGREEMENT_TOLERANCE = 1e-9
"""Same order as ``gam_multiterm_conformance``'s own Stage-B tolerance --
not imported from there (that constant belongs to the fixed-block-count
harness this module does not touch), but derived for the identical reason:
an exact comparison at fixed sp over a shared, well-conditioned design."""

_N_BLOCKS = 7
"""2 (s(AttdAge): existing + null) + 2 (s(AttdAge,by=StudyYear_C): existing +
null) + 3 (ti(...): its own existing 2 plus one null-space block, dimension
1 -- ``scripts/gam_select_penalty_probe.R``'s own "ti-attdage-polyear" case,
ADR-217). Every block, not just the null ones, since ``select=True`` changes
nothing about how many EXISTING blocks a term carries."""


class RSelectMultiTermRecipe(TypedDict):
    """The shared-recipe fields of ``scripts/gam_select_multiterm_probe.R``'s
    output -- structurally identical to
    :class:`~polaris_re.analytics.gam_multiterm_conformance.RMultiTermRecipe`
    (same covariates, same knots), but ``sp`` carries 7 entries, not 4."""

    n: int
    AttdAge: list[float]
    PolYear: list[float]
    StudyYear_C: list[float]
    ExposCnt: list[float]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]
    sp: list[float]


class RSelectMultiTermPayload(RSelectMultiTermRecipe):
    """The recipe plus the R script's OWN fit. Read by
    :func:`compare_select_multiterm_case` only; :func:`fit_select_multiterm_case`
    cannot see ``eta``/``coef`` at all through its narrower parameter type."""

    eta: list[float]
    coef: list[float]
    converged: bool


SELECT_MULTITERM_CLAIM = VerificationClaim(
    claim=(
        "polaris_re assembles the three-term design (the same reference/by/ti "
        "producers gam_multiterm_conformance.MULTITERM_CLAIM already declares "
        "INDEPENDENT) via gam_model.assemble_model_design(ModelSpec(..., "
        "select=True)), which appends each term's own null-space penalty via "
        "gam_select_penalty.null_space_penalty (ADR-217, itself independently "
        "verified against mgcv's select=TRUE setup path), then fits with "
        "gam_fit.penalized_irls_general at a FIXED, externally-supplied sp (one "
        "per block, 7 total) under binomial/cloglog with ExposCnt weights; mgcv "
        "computes the identical three-term model natively via gam(y ~ "
        "s(AttdAge,k=13,bs='cr') + s(AttdAge,by=StudyYear_C,k=13,bs='cr') + "
        "ti(AttdAge,PolYear,k=c(13,6),bs='cr'), family=binomial(link='cloglog'), "
        "weights=ExposCnt, select=TRUE, sp=sp_fixed); compared on eta at the "
        "training design."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta",
            left_producer=(
                "gam_fit.penalized_irls_general over a design assembled from "
                "gam_basis_cr's independently-verified cr/by/ti producers plus "
                "gam_select_penalty.null_space_penalty"
            ),
            right_producer=(
                "mgcv::predict(m, type='link') on a gam(..., select=TRUE) fit of "
                "the identical three-term formula at the same fixed sp"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""PLAN slice 7's Stage-B provenance declaration (ADR-193/ADR-217).
:func:`fit_select_multiterm_case`'s signature takes only
:class:`RSelectMultiTermRecipe`, which structurally excludes ``eta``/``coef``
-- the same mechanical-test-by-type discipline
:data:`~polaris_re.analytics.gam_multiterm_conformance.MULTITERM_CLAIM` uses."""


def fit_select_multiterm_case(
    r_case: RSelectMultiTermRecipe,
) -> tuple[GeneralIRLSFit, tuple[np.ndarray, ...]]:
    """The independent Python producer: assemble the ``select=True`` design,
    then fit it at the recipe's own fixed ``sp`` -- never reading ``mgcv``'s
    ``eta``/``coef`` (:class:`RSelectMultiTermRecipe` has neither key)."""
    sp = r_case["sp"]
    if len(sp) != _N_BLOCKS:
        raise PolarisValidationError(
            f"fit_select_multiterm_case: expected {_N_BLOCKS} sp values (one per "
            f"block, existing-then-null within each term), got {len(sp)}."
        )
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    year_knots = tuple(float(v) for v in r_case["year_knots"])
    model = replace(_multiterm_model_spec(age_knots, year_knots), select=True)
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "StudyYear_C": np.asarray(r_case["StudyYear_C"], dtype=np.float64),
    }
    design = assemble_model_design(model, data)
    if len(design["penalty_blocks"]) != _N_BLOCKS:
        raise PolarisValidationError(
            f"fit_select_multiterm_case: assembled {len(design['penalty_blocks'])} "
            f"penalty block(s) under select=True, expected {_N_BLOCKS} -- did a "
            "term's own null-space penalty go missing or double up?"
        )

    penalty = np.zeros_like(design["penalty_blocks"][0])
    for sp_j, block in zip(sp, design["penalty_blocks"], strict=True):
        penalty = penalty + float(sp_j) * block

    family: Family = binomial_cloglog()
    y = np.asarray(r_case["y"], dtype=np.float64)
    weights = np.asarray(r_case["ExposCnt"], dtype=np.float64)
    fit = penalized_irls_general(design["x"], y, family=family, penalty=penalty, weights=weights)
    return fit, design["penalty_blocks"]


class SelectMultiTermCaseComparison(TypedDict):
    max_abs_eta_diff: float
    agrees: bool
    evidence: VerificationClaim


def compare_select_multiterm_case(
    python_fit: GeneralIRLSFit, r_case: RSelectMultiTermPayload
) -> SelectMultiTermCaseComparison:
    """Compare the independent Python fit's ``eta`` against the R payload's
    own ``eta`` -- the only quantity :data:`SELECT_MULTITERM_CLAIM` declares."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_select_multiterm_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.eta)))
    return SelectMultiTermCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        agrees=max_abs_eta_diff < _AGREEMENT_TOLERANCE,
        evidence=SELECT_MULTITERM_CLAIM,
    )

"""``gaussian(identity)`` against ``mgcv`` at fixed ``sp`` — capability ladder
rung **L1** (``docs/PLAN_mgcv_capability_ladder.md`` slice 1).

**What this measures, and what it deliberately holds fixed.** The compared model
is the SAME three-term design
:mod:`~polaris_re.analytics.gam_multiterm_conformance` already measures —
``s(AttdAge) + s(AttdAge, by=StudyYear_C) + ti(AttdAge, PolYear)``, the target
formula's own knot vectors, a fixed externally-supplied ``sp`` per block. The
**only** thing changed is the family.

That is the point. Every basis in that design is tier-3 verified (``cr``
ADR-194, ``cr``+numeric-``by`` ADR-200, ``ti`` ADR-205) and the assembly itself
is verified (ADR-208), so a disagreement here **cannot** be a basis or assembly
defect — those are held fixed against an already-measured case. Introducing a
new design alongside a new family would confound the two, and this rung exists
precisely to be the regime where nothing is confounded.

**Why L1 is the bottom of the ladder.** At Gaussian identity ``V(mu) = 1`` and
``g'(mu) = 1``, so the IRLS weights are constant and the working response is
``y`` itself: the first solve is exact (measured — ``n_iter <= 2``, and against
the closed-form ridge to ``1e-12``, in ``tests/test_analytics/test_gam_family.py``).
A basis or penalty disagreement therefore cannot hide behind IRLS convergence
here, which is what makes every rung above it cheaper to diagnose.

**FIXED ``sp`` only, and why that is a complete measurement of this rung rather
than a hedge.** Gaussian estimates its scale (``dispersion_fixed=False``) and
:func:`~polaris_re.analytics.gam_reml.reml_score_general` raises on a free
scale — the blocker ``PLAN_mgcv_capability_ladder.md`` §2.2 names, which rung L5
clears at slice 3. But at fixed ``sp`` the Gaussian fit is ordinary **penalized
least squares**, ``(X'WX + S)^-1 X'Wz``, and **the scale does not enter it at
all**: the scale is needed to *choose* ``sp``, not to fit at a given one. So this
module measures the whole of what L1 claims — the family's recursion and its
interaction with the penalty — and the part it cannot reach is exactly the part
L5 owns.

**The gate is ADR-221's, imported and never re-derived.** Anchor W5 forbids this
epic introducing a tolerance or re-gating anything, so :data:`_ETA_TOLERANCE` /
:data:`_EDF_TOLERANCE` are *imported* from
:mod:`~polaris_re.analytics.gam_select_free_sp_conformance` rather than
redeclared — a copied constant can drift, an imported one cannot.

**Provenance (ADR-193, ADR-228).** Both compared quantities are ``INDEPENDENT``:
this engine is one of the two producers. Nothing here is ``REFERENCE_INTERNAL``
— that member is for ``mgcv``-vs-``mgcv`` comparisons, and there are none in this
module.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import Family, gaussian_identity
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_model import assemble_model_design
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "GAUSSIAN_CLAIM",
    "GAUSSIAN_CLAIM_SENTENCE",
    "GaussianCaseComparison",
    "RGaussianPayload",
    "RGaussianRecipe",
    "compare_gaussian_case",
    "fit_gaussian_case",
    "gaussian_model_spec",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's committed ``eta`` half of the acceptance gate (``2e-2``),
**imported, not redeclared** (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's committed ``edf_total`` half of the acceptance gate (``1.0``),
imported for the same reason as :data:`_ETA_TOLERANCE`."""

_N_PENALTY_BLOCKS = 4
"""``s(AttdAge)`` 1 + ``s(AttdAge, by=StudyYear_C)`` 1 + ``ti(AttdAge, PolYear)``
2 (ADR-205 decision 2: one per margin)."""

_REF_LABEL = "s(AttdAge)"
_BY_LABEL = "s(AttdAge):StudyYear_C"
_TI_LABEL = "ti(AttdAge,PolYear)"


class RGaussianRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**.

    The ADR-193 mechanical test applied structurally: this type has no ``eta``,
    ``coef`` or ``edf_total`` key, so :func:`fit_gaussian_case` cannot read
    ``mgcv``'s own fit even if a caller hands it the wider
    :class:`RGaussianPayload`.
    """

    n: int
    AttdAge: list[float]
    PolYear: list[float]
    StudyYear_C: list[float]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]
    sp: list[float]


class RGaussianPayload(RGaussianRecipe):
    """The recipe plus ``scripts/gam_gaussian_probe.R``'s OWN fit. Read by
    :func:`compare_gaussian_case` only."""

    eta: list[float]
    edf_total: float
    offset_gap: float
    coef: list[float]
    converged: bool


GAUSSIAN_CLAIM_SENTENCE = (
    "polaris_re assembles the three-term design (build_python_cr_term for "
    "s(AttdAge,k=13,bs='cr'), build_python_cr_term(by=...) for "
    "s(AttdAge,by=StudyYear_C,k=13,bs='cr'), and build_python_ti_term for "
    "ti(AttdAge,PolYear,k=(13,6),bs='cr')) through assemble_model_design from "
    "the shared recipe (AttdAge, PolYear, StudyYear_C, y, the target formula's "
    "own knot vectors, sp), and fits it with gam_fit.penalized_irls_general "
    "under gaussian(link='identity') at a FIXED, externally-supplied sp — one "
    "per penalty block, four blocks — never reading mgcv's own eta, coef or "
    "edf. mgcv computes the identical model natively via "
    "gam(y ~ s(AttdAge,k=13,bs='cr') + s(AttdAge,by=StudyYear_C,k=13,bs='cr') + "
    "ti(AttdAge,PolYear,k=c(13,6),bs='cr'), family=gaussian(link='identity'), "
    "knots=<the same vectors>, sp=sp_fixed) and reports m$linear.predictors and "
    "sum(m$edf) (scripts/gam_gaussian_probe.R). Compared on eta at the training "
    "design and on edf_total, against ADR-221's committed criterion "
    "(max_abs_eta_diff < 2e-2 and abs(edf_total_diff) < 1.0), IMPORTED and not "
    "redeclared. The design is held identical to the already tier-3-verified "
    "multi-term case so that the FAMILY is the only unverified thing in the "
    "comparison. FIXED sp only: gaussian estimates its scale and "
    "reml_score_general raises on a free scale until ladder rung L5, so free-sp "
    "selection is NOT measured here and NOT claimed. Coefficients are never "
    "compared (PLAN Anchor 2)."
)
"""The claim sentence, written before the code per
``docs/VERIFICATION_STANDARD.md`` §3.2. It names the two producers, the compared
quantities, the imported tolerances, and — explicitly — the regime it does *not*
reach."""


GAUSSIAN_CLAIM = VerificationClaim(
    claim=GAUSSIAN_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris gaussian/identity vs mgcv, fixed sp)",
            left_producer=(
                "gam_fit.penalized_irls_general with gaussian_identity() over a "
                "design from assemble_model_design's independently-verified "
                "cr/by/ti producers, at the recipe's own fixed sp"
            ),
            right_producer=(
                "mgcv gam(..., family=gaussian(link='identity'), sp=sp_fixed), "
                "read as m$linear.predictors"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris gaussian/identity vs mgcv, fixed sp)",
            left_producer=(
                "trace of the Polaris hat matrix at the same fixed sp, from the same design"
            ),
            right_producer="mgcv's own sum(m$edf) at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L1's provenance declaration. **Both quantities INDEPENDENT** — this
engine is one of the two producers in each, which is what separates them from
the ``REFERENCE_INTERNAL`` rows ADR-228 introduced for ``mgcv``-vs-``mgcv``
comparisons. :func:`fit_gaussian_case` takes :class:`RGaussianRecipe`, which
structurally carries no ``eta``/``edf_total`` key."""


def gaussian_model_spec(age_knots: tuple[float, ...], year_knots: tuple[float, ...]) -> ModelSpec:
    """The three-term ``ModelSpec`` under ``gaussian(identity)``.

    Identical in every term to
    :mod:`~polaris_re.analytics.gam_multiterm_conformance`'s own spec except for
    ``family``/``link`` and the absence of prior weights — which is the whole
    design of this comparison (see the module docstring).
    """
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
    return ModelSpec(
        family="gaussian",
        link="identity",
        terms=(ref_term, by_term, ti_term),
    )


@dataclass(frozen=True)
class GaussianFit:
    """The Polaris side's fit plus the ``edf_total`` derived from it."""

    fit: GeneralIRLSFit
    edf_total: float


def fit_gaussian_case(r_case: RGaussianRecipe) -> GaussianFit:
    """The independent Python producer.

    Assembles the design from the shared recipe and fits at the recipe's own
    fixed ``sp`` — never reading ``mgcv``'s ``eta``/``edf_total``
    (:class:`RGaussianRecipe` has neither key; a caller passing the wider
    payload still cannot make this function see them).

    ``edf_total`` is ``tr(F)`` with ``F = (X'WX + S)^-1 X'WX``, the same
    definition ``mgcv``'s ``sum(m$edf)`` uses. Computed here from this side's own
    design and weights, never read from the payload.
    """
    sp = r_case["sp"]
    if len(sp) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_gaussian_case: expected {_N_PENALTY_BLOCKS} sp values "
            f"(reference, by, ti#1, ti#2), got {len(sp)}."
        )
    age = np.asarray(r_case["AttdAge"], dtype=np.float64)
    year = np.asarray(r_case["PolYear"], dtype=np.float64)
    by = np.asarray(r_case["StudyYear_C"], dtype=np.float64)
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    year_knots = tuple(float(v) for v in r_case["year_knots"])

    model = gaussian_model_spec(age_knots, year_knots)
    design = assemble_model_design(model, {"AttdAge": age, "PolYear": year, "StudyYear_C": by})
    x = design["x"]
    blocks = design["penalty_blocks"]
    if len(blocks) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_gaussian_case: assembled {len(blocks)} penalty blocks, expected "
            f"{_N_PENALTY_BLOCKS}."
        )

    penalty = np.zeros_like(blocks[0])
    for sp_j, block in zip(sp, blocks, strict=True):
        penalty = penalty + float(sp_j) * block

    family: Family = gaussian_identity()
    y = np.asarray(r_case["y"], dtype=np.float64)
    fit = penalized_irls_general(x, y, family=family, penalty=penalty)

    # tr(F), F = (X'WX + S)^-1 X'WX. At Gaussian identity the IRLS weights are
    # constant at 1, so W is the identity — written out anyway rather than
    # special-cased, so this reads the same as every other family's edf.
    mu_eta = family.link.mu_eta(fit.eta)
    weights = (mu_eta**2) / family.variance(fit.mu)
    xtwx = x.T @ (weights[:, None] * x)
    edf_total = float(np.trace(np.linalg.solve(xtwx + penalty, xtwx)))
    return GaussianFit(fit=fit, edf_total=edf_total)


class GaussianCaseComparison(TypedDict):
    max_abs_eta_diff: float
    edf_total_diff: float
    python_edf_total: float
    mgcv_edf_total: float
    offset_gap: float
    agrees: bool
    evidence: VerificationClaim


def compare_gaussian_case(
    python_fit: GaussianFit, r_case: RGaussianPayload
) -> GaussianCaseComparison:
    """Compare the independent Python fit against the R payload, on the two
    quantities :data:`GAUSSIAN_CLAIM` declares and no others.

    ``offset_gap`` is carried through from the probe as a **tripwire, not a
    gated quantity**: it is the probe's own measurement that
    ``m$linear.predictors`` and ``predict(type='link')`` agree on this recipe
    (they must — it carries no offset). A non-zero value would mean an offset had
    been added and ``predict()`` was silently dropping it, which produced one
    false ``1.9751``-against-``2e-2`` reading earlier in this epic. It is
    reported so a reader can see the trap was checked rather than assumed.
    """
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.fit.eta.shape:
        raise PolarisValidationError(
            f"compare_gaussian_case: R eta has shape {r_eta.shape}, Python eta "
            f"has shape {python_fit.fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.fit.eta)))
    mgcv_edf_total = float(r_case["edf_total"])
    edf_total_diff = python_fit.edf_total - mgcv_edf_total
    agrees = max_abs_eta_diff < _ETA_TOLERANCE and abs(edf_total_diff) < _EDF_TOLERANCE
    return GaussianCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        edf_total_diff=edf_total_diff,
        python_edf_total=python_fit.edf_total,
        mgcv_edf_total=mgcv_edf_total,
        offset_gap=float(r_case["offset_gap"]),
        agrees=agrees,
        evidence=GAUSSIAN_CLAIM,
    )

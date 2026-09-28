"""``cr`` + ``re`` + ``ti`` fit JOINTLY against ``mgcv`` — capability ladder
slice 6 (``docs/PLAN_mgcv_capability_ladder.md``), Stage B.

Each of the three bases is independently tier-3 verified (``cr`` ADR-194,
``re`` ADR-230, ``ti`` ADR-205/206) but they had never been fit together in
one model. This module poses the model::

    y ~ s(AttdAge, k=13, bs="cr")
      + s(GroupFac, bs="re")
      + ti(AttdAge, PolYear, k=c(13,6), bs="cr")

at the maintainer's near-term narrow target's own structure (four penalty
blocks: the ``cr`` smooth's one, the ``re`` term's one, and ``ti()``'s two).
``AttdAge`` feeds BOTH the ``cr`` reference smooth and one ``ti`` margin;
``ti()`` excludes its margins' main effects by construction, which is the
identifiability interaction this composition is the first to exercise.

**Three cases, one shared recipe shape.** ``gaussian_fixed`` (``gaussian
(identity)`` at externally-supplied ``sp`` — a single linear solve, so a
composition defect cannot hide behind IRLS convergence), ``gaussian_free``
(``mgcv``'s and Polaris's own free-``sp`` REML selection under ladder rung
L5's free-scale criterion) and ``poisson_free`` (the IRLS path on the same
composition; ``poisson(log)`` is the already-verified fixed-dispersion
stand-in for the PLAN's quasi-Poisson, which is slices 3b/7).

**The gate is ADR-221's, imported and never re-derived** (Anchor W5), from
:mod:`~polaris_re.analytics.gam_select_free_sp_conformance`, exactly as every
capability-ladder Stage-B module does.

**Provenance (ADR-193).** Every compared quantity is ``INDEPENDENT``: this
engine is one of the two producers throughout. Neither
:func:`fit_cr_re_ti_fixed_sp_case` nor :func:`fit_cr_re_ti_free_sp_case`
takes an R payload — each takes only the narrower recipe type, which
structurally excludes ``mgcv``'s own ``eta``/``coef``/``mgcv_sp``/``edf``. The
one ``TRANSPORT``-style check — that ``mgcv``'s ``summary(m)$s.table`` rows
are in the same term order Polaris labels them — is an alignment guard that
raises, not a compared quantity.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_model import (
    PolarisGAMFit,
    assemble_model_design,
    fit_polaris_gam,
    resolve_family,
)
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
    "CR_RE_TI_FIXED_SP_CLAIM",
    "CR_RE_TI_FREE_SP_CLAIM",
    "TERM_LABELS",
    "CrReTiFixedSpComparison",
    "CrReTiFixedSpFit",
    "CrReTiFreeSpComparison",
    "RCrReTiFixedSpPayload",
    "RCrReTiFixedSpRecipe",
    "RCrReTiFreeSpPayload",
    "RCrReTiFreeSpRecipe",
    "compare_cr_re_ti_fixed_sp_case",
    "compare_cr_re_ti_free_sp_case",
    "cr_re_ti_model_spec",
    "fit_cr_re_ti_fixed_sp_case",
    "fit_cr_re_ti_free_sp_case",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's committed ``eta`` half of the gate (``2e-2``), **imported** (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's committed ``edf_total`` half of the gate (``1.0``), imported."""

_REF_LABEL = "s(AttdAge)"
_RE_LABEL = "s(GroupFac)"
_TI_LABEL = "ti(AttdAge,PolYear)"
TERM_LABELS: tuple[str, str, str] = (_REF_LABEL, _RE_LABEL, _TI_LABEL)
"""The three smooth terms in ``mgcv``'s formula order, spelled exactly as
``rownames(summary(m)$s.table)`` spells them."""

_N_PENALTY_BLOCKS = 4
"""``cr`` 1 + ``re`` 1 (one block regardless of level count) + ``ti`` 2."""

_FREE_SP_BOUNDS = (-2.0, 12.0)
"""Same as :data:`~polaris_re.analytics.gam_model.PRODUCTION_LOG10_BOUNDS`."""


def cr_re_ti_model_spec(
    family: str,
    link: str,
    age_knots: tuple[float, ...],
    year_knots: tuple[float, ...],
    n_levels: int,
) -> ModelSpec:
    """The three-term ``ModelSpec`` (four penalty blocks) under
    ``family``/``link``."""
    ref_term = TermSpec(
        label=_REF_LABEL,
        variables=("AttdAge",),
        basis="cr",
        k=(len(age_knots),),
        knots=(("AttdAge", age_knots),),
    )
    re_term = TermSpec(label=_RE_LABEL, variables=("GroupFac",), basis="re", n_levels=n_levels)
    ti_term = TermSpec(
        label=_TI_LABEL,
        variables=("AttdAge", "PolYear"),
        basis="ti",
        k=(len(age_knots), len(year_knots)),
        knots=(("AttdAge", age_knots), ("PolYear", year_knots)),
    )
    return ModelSpec(family=family, link=link, terms=(ref_term, re_term, ti_term))


class RCrReTiFreeSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**. No ``sp``
    key: free ``sp`` is what the free comparison measures."""

    family: str
    link: str
    n: int
    n_levels: int
    AttdAge: list[float]
    PolYear: list[float]
    group: list[int]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]


class RCrReTiFreeSpPayload(RCrReTiFreeSpRecipe):
    """The recipe plus ``scripts/gam_cr_re_ti_probe.R``'s OWN free-``sp`` fit.
    Read by :func:`compare_cr_re_ti_free_sp_case` only."""

    eta: list[float]
    mgcv_sp: list[float]
    edf_total: float
    term_edf: list[float]
    term_labels: list[str]
    offset_gap: float
    coef: list[float]
    converged: bool


class RCrReTiFixedSpRecipe(TypedDict):
    """The shared recipe plus the SUPPLIED ``sp_fixed`` — an input to both
    sides, never an ``mgcv`` output. Still no ``eta``/``coef``/``edf_total``
    key (the ADR-193 mechanical test, by type)."""

    family: str
    link: str
    n: int
    n_levels: int
    AttdAge: list[float]
    PolYear: list[float]
    group: list[int]
    y: list[float]
    age_knots: list[float]
    year_knots: list[float]
    sp_fixed: list[float]


class RCrReTiFixedSpPayload(RCrReTiFixedSpRecipe):
    """The fixed-``sp`` recipe plus ``mgcv``'s own fit at that ``sp``. Read by
    :func:`compare_cr_re_ti_fixed_sp_case` only."""

    eta: list[float]
    edf_total: float
    term_edf: list[float]
    term_labels: list[str]
    offset_gap: float
    coef: list[float]
    converged: bool


def _data(r_case: RCrReTiFreeSpRecipe | RCrReTiFixedSpRecipe) -> dict[str, np.ndarray]:
    return {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "GroupFac": np.asarray(r_case["group"], dtype=np.int64),
    }


def _spec(r_case: RCrReTiFreeSpRecipe | RCrReTiFixedSpRecipe) -> ModelSpec:
    return cr_re_ti_model_spec(
        r_case["family"],
        r_case["link"],
        tuple(float(v) for v in r_case["age_knots"]),
        tuple(float(v) for v in r_case["year_knots"]),
        int(r_case["n_levels"]),
    )


def _check_labels(who: str, r_labels: list[str]) -> None:
    if tuple(r_labels) != TERM_LABELS:
        raise PolarisValidationError(
            f"{who}: mgcv's s.table rows are {tuple(r_labels)}, expected {TERM_LABELS}; "
            "per-term edf would be compared out of alignment."
        )


# ---------------------------------------------------------------------------
# Fixed sp
# ---------------------------------------------------------------------------

CR_RE_TI_FIXED_SP_CLAIM_SENTENCE = (
    "polaris_re assembles the three-term design (build_python_cr_term for "
    "s(AttdAge,k=13,bs='cr'), build_python_re_term for s(GroupFac,bs='re'), "
    "build_python_ti_term for ti(AttdAge,PolYear,k=c(13,6),bs='cr')) through "
    "assemble_model_design from the shared recipe (AttdAge, PolYear, group, "
    "n_levels, y, the target formula's own age/year knots, sp_fixed), and fits "
    "it with gam_fit.penalized_irls_general under gaussian(link='identity') at "
    "a FIXED, externally-supplied sp -- one per penalty block, four blocks -- "
    "never reading mgcv's own eta, coef or edf. mgcv computes the identical "
    "model natively via gam(y ~ s(AttdAge,k=13,bs='cr') + s(GroupFac,bs='re') "
    "+ ti(AttdAge,PolYear,k=c(13,6),bs='cr'), family=gaussian(link='identity'),"
    " knots=<the same vectors>, sp=sp_fixed) and reports m$linear.predictors "
    "and sum(m$edf) (scripts/gam_cr_re_ti_probe.R, case gaussian_fixed). "
    "Compared on eta at the training design and on edf_total, against "
    "ADR-221's committed criterion (max_abs_eta_diff < 2e-2 and "
    "abs(edf_total_diff) < 1.0), IMPORTED and not redeclared. Coefficients "
    "are never compared (PLAN Anchor 2)."
)
"""The claim sentence, written before the code per
``docs/VERIFICATION_STANDARD.md`` §3.2."""

CR_RE_TI_FIXED_SP_CLAIM = VerificationClaim(
    claim=CR_RE_TI_FIXED_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris cr+re+ti vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "gam_fit.penalized_irls_general with gaussian_identity() over a design "
                "from assemble_model_design's cr + re + ti producers, at the recipe's "
                "own fixed sp"
            ),
            right_producer=(
                "mgcv gam(..., family=gaussian(link='identity'), sp=sp_fixed), "
                "read as m$linear.predictors"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris cr+re+ti vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "trace of the Polaris hat matrix at the same fixed sp, from the same design"
            ),
            right_producer="mgcv's own sum(m$edf) at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 6 Stage B (fixed `sp`)'s provenance declaration."""


@dataclass(frozen=True)
class CrReTiFixedSpFit:
    """The Polaris side's fixed-``sp`` fit plus the ``edf_total`` derived from it."""

    fit: GeneralIRLSFit
    edf_total: float


def fit_cr_re_ti_fixed_sp_case(r_case: RCrReTiFixedSpRecipe) -> CrReTiFixedSpFit:
    """The independent Python producer for the fixed-``sp`` regime — never
    reads ``mgcv``'s ``eta``/``edf_total`` (the recipe type has neither)."""
    sp = r_case["sp_fixed"]
    if len(sp) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_cr_re_ti_fixed_sp_case: expected {_N_PENALTY_BLOCKS} sp values "
            f"(cr, re, ti#1, ti#2), got {len(sp)}."
        )
    model = _spec(r_case)
    design = assemble_model_design(model, _data(r_case))
    x = design["x"]
    blocks = design["penalty_blocks"]
    if len(blocks) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_cr_re_ti_fixed_sp_case: assembled {len(blocks)} penalty blocks, "
            f"expected {_N_PENALTY_BLOCKS}."
        )
    penalty = np.zeros_like(blocks[0])
    for sp_j, block in zip(sp, blocks, strict=True):
        penalty = penalty + float(sp_j) * block

    family: Family = resolve_family(r_case["family"], r_case["link"])
    y = np.asarray(r_case["y"], dtype=np.float64)
    fit = penalized_irls_general(x, y, family=family, penalty=penalty)

    mu_eta = family.link.mu_eta(fit.eta)
    weights = (mu_eta**2) / family.variance(fit.mu)
    xtwx = x.T @ (weights[:, None] * x)
    edf_total = float(np.trace(np.linalg.solve(xtwx + penalty, xtwx)))
    return CrReTiFixedSpFit(fit=fit, edf_total=edf_total)


@dataclass(frozen=True)
class CrReTiFixedSpComparison:
    """One fixed-``sp`` case's verdict — every quantity
    :data:`CR_RE_TI_FIXED_SP_CLAIM` declares."""

    max_abs_eta_diff: float
    edf_total_diff: float
    python_edf_total: float
    mgcv_edf_total: float
    offset_gap: float
    agrees: bool
    evidence: VerificationClaim


def compare_cr_re_ti_fixed_sp_case(
    python_fit: CrReTiFixedSpFit, r_case: RCrReTiFixedSpPayload
) -> CrReTiFixedSpComparison:
    """Compare the independent Python fit against the R payload, on the two
    quantities :data:`CR_RE_TI_FIXED_SP_CLAIM` declares and no others."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.fit.eta.shape:
        raise PolarisValidationError(
            f"compare_cr_re_ti_fixed_sp_case: R eta has shape {r_eta.shape}, Python "
            f"eta has shape {python_fit.fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.fit.eta)))
    mgcv_edf_total = float(r_case["edf_total"])
    edf_total_diff = python_fit.edf_total - mgcv_edf_total
    return CrReTiFixedSpComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        edf_total_diff=edf_total_diff,
        python_edf_total=python_fit.edf_total,
        mgcv_edf_total=mgcv_edf_total,
        offset_gap=float(r_case["offset_gap"]),
        agrees=max_abs_eta_diff < _ETA_TOLERANCE and abs(edf_total_diff) < _EDF_TOLERANCE,
        evidence=CR_RE_TI_FIXED_SP_CLAIM,
    )


# ---------------------------------------------------------------------------
# Free sp
# ---------------------------------------------------------------------------

CR_RE_TI_FREE_SP_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) assembles the "
    "three-term design (cr + re + ti, four penalty blocks) from the shared "
    "recipe (AttdAge, PolYear, group, n_levels, y, the target formula's own "
    "knots, family/link) via assemble_model_design, selects every "
    "log10(lambda) by minimizing gam_reml.reml_score_general (fixed-dispersion "
    "for poisson(log), ladder rung L5's free-scale branch for "
    "gaussian(identity)) via gam_reml_optimize.select_lambdas_continuous, and "
    "fits with gam_fit.penalized_irls_general -- never reading mgcv's own eta, "
    "coef, sp or edf; mgcv computes the identical formula via "
    "gam(..., method='REML') with free sp, selecting its own smoothing "
    "parameters independently (scripts/gam_cr_re_ti_probe.R, cases "
    "gaussian_free and poisson_free). Compared on eta at the training design, "
    "per-block log10(sp), edf_total and per-term edf, gated on ADR-221's "
    "committed criterion (max_abs_eta_diff < 2e-2 and "
    "abs(edf_total_diff) < 1.0), IMPORTED and not redeclared."
)

CR_RE_TI_FREE_SP_CLAIM = VerificationClaim(
    claim=CR_RE_TI_FREE_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris cr+re+ti vs mgcv, free sp)",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda",
            right_producer="mgcv gam(method='REML') free-sp fit, m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per block (Polaris cr+re+ti vs mgcv, free sp)",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda",
            right_producer="mgcv's own log10(m$sp) at its free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris cr+re+ti vs mgcv, free sp)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-term edf (Polaris cr+re+ti vs mgcv, free sp)",
            left_producer="PolarisGAMFit.edf_per_term (hat-matrix diagonal sum per term span)",
            right_producer="mgcv's own summary(m)$s.table[, 'edf'], one row per smooth term",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 6 Stage B (free `sp`)'s provenance declaration."""


def fit_cr_re_ti_free_sp_case(
    r_case: RCrReTiFreeSpRecipe, *, multistart: bool = False
) -> PolarisGAMFit:
    """The independent Python producer for the free-``sp`` regime — never
    reads ``mgcv``'s ``eta``/``coef``/``mgcv_sp``/``edf`` (the recipe type has
    none of these keys)."""
    y = np.asarray(r_case["y"], dtype=np.float64)
    return fit_polaris_gam(
        _spec(r_case), _data(r_case), y, bounds=_FREE_SP_BOUNDS, multistart=multistart
    )


@dataclass(frozen=True)
class CrReTiFreeSpComparison:
    """One free-``sp`` case's verdict — every quantity
    :data:`CR_RE_TI_FREE_SP_CLAIM` declares."""

    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    per_block_log10_sp_diff: tuple[float, ...]
    edf_total_diff: float
    max_abs_term_edf_diff: float
    offset_gap: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_cr_re_ti_free_sp_case(
    python_fit: PolarisGAMFit, r_case: RCrReTiFreeSpPayload
) -> CrReTiFreeSpComparison:
    """Compare the independent Python free-``sp`` fit against ``mgcv``'s, on
    every quantity :data:`CR_RE_TI_FREE_SP_CLAIM` declares.

    ``agrees`` is ADR-221's committed ``eta``/``edf_total`` criterion
    (imported) — never a fresh ``log10(sp)`` bar (Anchor W5); ``log10(sp)``
    is reported, as at every prior free-``sp`` rung.
    """
    _check_labels("compare_cr_re_ti_free_sp_case", r_case["term_labels"])
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_cr_re_ti_free_sp_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    r_log_sp = np.log10(np.asarray(r_case["mgcv_sp"], dtype=np.float64))
    if r_log_sp.shape != python_fit.log_lambda.shape:
        raise PolarisValidationError(
            f"compare_cr_re_ti_free_sp_case: R sp has {r_log_sp.shape[0]} entries, "
            f"Python log_lambda has {python_fit.log_lambda.shape[0]}."
        )
    r_term_edf = np.asarray(r_case["term_edf"], dtype=np.float64)
    python_term_edf = np.asarray([python_fit.edf_per_term[lb] for lb in TERM_LABELS])

    per_block = np.abs(python_fit.log_lambda - r_log_sp)
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.eta)))
    edf_total_diff = float(python_fit.edf_total - r_case["edf_total"])
    agrees = (
        python_fit.converged
        and bool(r_case["converged"])
        and max_abs_eta_diff < _ETA_TOLERANCE
        and abs(edf_total_diff) < _EDF_TOLERANCE
    )
    return CrReTiFreeSpComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=float(np.max(per_block)),
        per_block_log10_sp_diff=tuple(float(v) for v in per_block),
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=float(np.max(np.abs(python_term_edf - r_term_edf))),
        offset_gap=float(r_case["offset_gap"]),
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        evidence=CR_RE_TI_FREE_SP_CLAIM,
    )

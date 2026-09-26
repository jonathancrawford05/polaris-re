"""Factor-``by`` against ``mgcv`` — capability ladder rung **L3**
(``docs/PLAN_mgcv_capability_ladder.md`` slice 4), Stage B, both `sp` regimes.

Stage A (the basis itself, independent of any fit) lives in
:mod:`polaris_re.analytics.gam_basis_cr` (:func:`by_factor_mask_design`) and
:data:`polaris_re.analytics.gam_stage_a.CR_BY_FACTOR_BASIS_CLAIM`. This module is
Stage B: does a **model** built from a factor-``by`` term (``n_levels`` separate
:class:`~polaris_re.analytics.gam_term_spec.TermSpec` objects, via
:func:`~polaris_re.analytics.gam_term_spec.factor_by_terms`) plus an
already-verified ``"cr"`` term reproduce ``mgcv``'s own fit, both at a FIXED,
externally-supplied ``sp`` (one per block) and at ``mgcv``'s own FREELY SELECTED
``sp``?

**One family throughout, unlike ladder rung L2's own two-family split.**
Capability ladder rung L5 (ADR-231) already closed
:func:`~polaris_re.analytics.gam_reml.reml_score_general`'s free-scale branch
*before* this slice was written, so — unlike rung L2's ``re`` conformance
(:mod:`gam_re_conformance`), which had to route its free-``sp`` half through
``poisson(log)`` to dodge a blocker that did not yet have a fix — both
:data:`BY_FACTOR_FIXED_SP_CLAIM` and :data:`BY_FACTOR_FREE_SP_CLAIM` use
``gaussian(identity)``. One family end to end is simpler, and there is no
remaining reason to avoid it.

**The two smoothed covariates are deliberately different** (``PolYear`` for the
reference term, ``AttdAge`` for the factor-``by`` term) so the two cannot be
confounded with each other the way two terms sharing one covariate could be —
a disagreement is then attributable to the factor-``by`` construction, not to
an ambiguous split of signal between two terms on the same variable.

**The gate is ADR-221's, imported and never re-derived.** Anchor W5 forbids
this epic introducing a tolerance or re-gating anything, so
:data:`_ETA_TOLERANCE` / :data:`_EDF_TOLERANCE` are *imported* from
:mod:`~polaris_re.analytics.gam_select_free_sp_conformance`, the same import
every prior capability-ladder Stage-B module in this epic uses.

**Provenance (ADR-193, ADR-228).** Every compared quantity in both claims is
``INDEPENDENT``: this engine is one of the two producers throughout. Neither
:func:`fit_by_factor_fixed_sp_case` nor :func:`fit_by_factor_free_sp_case`
takes an R payload — each takes only the narrower :class:`RByFactorFixedSpRecipe`
/ :class:`RByFactorFreeSpRecipe`, which structurally excludes ``mgcv``'s own
``eta``/``coef``/``sp``/``edf`` (the ADR-193 mechanical test enforced by the
type, the same discipline every prior conformance module in this epic uses).

**Suspicion, not just a check.** Both R probes give the ``by``-term's levels
genuinely different slopes so ``edf_total`` has something to move against —
the same discipline ladder slices 1/2 carried for their own near-exact
agreements; this module's own test suite carries the same strip/perturb pair.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import Family, gaussian_identity
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_model import PolarisGAMFit, assemble_model_design, fit_polaris_gam
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "BY_FACTOR_FIXED_SP_CLAIM",
    "BY_FACTOR_FREE_SP_CLAIM",
    "RByFactorFixedSpCaseComparison",
    "RByFactorFixedSpPayload",
    "RByFactorFixedSpRecipe",
    "RByFactorFreeSpCaseComparison",
    "RByFactorFreeSpPayload",
    "RByFactorFreeSpRecipe",
    "by_factor_fixed_sp_model_spec",
    "by_factor_free_sp_model_spec",
    "compare_by_factor_fixed_sp_case",
    "compare_by_factor_free_sp_case",
    "fit_by_factor_fixed_sp_case",
    "fit_by_factor_free_sp_case",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's committed ``eta`` half of the acceptance gate (``2e-2``),
**imported, not redeclared** (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's committed ``edf_total`` half of the acceptance gate (``1.0``),
imported for the same reason as :data:`_ETA_TOLERANCE`."""

_REF_LABEL = "s(PolYear)"
_BY_LABEL = "s(AttdAge)"


def _n_penalty_blocks(n_levels: int) -> int:
    """``s(PolYear)`` 1 + ``s(AttdAge, by=GroupFac)`` ``n_levels`` — a factor-``by``
    term contributes exactly ``n_levels`` separate smoothing parameters, one per
    level (module docstring / ``docs/MGCV_NOTATION_PRIMER.md`` §4), unlike
    ``re``'s single shared block regardless of level count."""
    return 1 + n_levels


def _by_factor_model_spec(
    family: str,
    link: str,
    polyear_knots: tuple[float, ...],
    age_knots: tuple[float, ...],
    n_levels: int,
) -> ModelSpec:
    ref_term = TermSpec(
        label=_REF_LABEL,
        variables=("PolYear",),
        basis="cr",
        k=(len(polyear_knots),),
        knots=(("PolYear", polyear_knots),),
    )
    by_terms = factor_by_terms(
        base_label=_BY_LABEL,
        variable="AttdAge",
        k=len(age_knots),
        by_factor="GroupFac",
        n_levels=n_levels,
        knots=age_knots,
    )
    return ModelSpec(family=family, link=link, terms=(ref_term, *by_terms))


def by_factor_fixed_sp_model_spec(
    polyear_knots: tuple[float, ...], age_knots: tuple[float, ...], n_levels: int
) -> ModelSpec:
    """The ``(1 + n_levels)``-term ``ModelSpec`` under ``gaussian(identity)``
    (fixed ``sp``)."""
    return _by_factor_model_spec("gaussian", "identity", polyear_knots, age_knots, n_levels)


def by_factor_free_sp_model_spec(
    polyear_knots: tuple[float, ...], age_knots: tuple[float, ...], n_levels: int
) -> ModelSpec:
    """The same ``ModelSpec`` shape, for the free-``sp`` regime. Identical to
    :func:`by_factor_fixed_sp_model_spec` today (both regimes use
    ``gaussian(identity)``, module docstring) — kept as a separate function so a
    future divergence between the two regimes (as ladder rung L2 needed) does
    not require renaming call sites."""
    return _by_factor_model_spec("gaussian", "identity", polyear_knots, age_knots, n_levels)


# ---------------------------------------------------------------------------
# Fixed sp
# ---------------------------------------------------------------------------


class RByFactorFixedSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**.

    The ADR-193 mechanical test applied structurally: this type has no
    ``eta``, ``coef`` or ``edf_total`` key, so :func:`fit_by_factor_fixed_sp_case`
    cannot read ``mgcv``'s own fit even if a caller hands it the wider
    :class:`RByFactorFixedSpPayload`.
    """

    n: int
    n_levels: int
    PolYear: list[float]
    AttdAge: list[float]
    group: list[int]
    y: list[float]
    polyear_knots: list[float]
    age_knots: list[float]
    sp: list[float]


class RByFactorFixedSpPayload(RByFactorFixedSpRecipe):
    """The recipe plus ``scripts/gam_by_factor_probe.R``'s OWN fit. Read by
    :func:`compare_by_factor_fixed_sp_case` only."""

    eta: list[float]
    edf_total: float
    term_edf: list[float]
    offset_gap: float
    coef: list[float]
    converged: bool


BY_FACTOR_FIXED_SP_CLAIM_SENTENCE = (
    "polaris_re assembles the (1+n_levels)-term design (build_python_cr_term "
    "for s(PolYear,k=6,bs='cr'), gam_term_spec.factor_by_terms + "
    "build_python_cr_by_factor_term for s(AttdAge,by=GroupFac,k=13,bs='cr')) "
    "through assemble_model_design from the shared recipe (PolYear, AttdAge, "
    "group, n_levels, y, the target formula's own knots, sp), and fits it "
    "with gam_fit.penalized_irls_general under gaussian(link='identity') at "
    "a FIXED, externally-supplied sp -- one per penalty block, 1+n_levels "
    "blocks -- never reading mgcv's own eta, coef or edf. mgcv computes the "
    "identical model natively via gam(y ~ s(PolYear,k=6,bs='cr') + "
    "s(AttdAge,by=GroupFac,k=13,bs='cr'), family=gaussian(link='identity'), "
    "knots=<the same vectors>, sp=sp_fixed) and reports m$linear.predictors "
    "and sum(m$edf) (scripts/gam_by_factor_probe.R). Compared on eta at the "
    "training design and on edf_total, against ADR-221's committed criterion "
    "(max_abs_eta_diff < 2e-2 and abs(edf_total_diff) < 1.0), IMPORTED and "
    "not redeclared. Coefficients are never compared (PLAN Anchor 2)."
)
"""The claim sentence, written before the code per
``docs/VERIFICATION_STANDARD.md`` §3.2."""


BY_FACTOR_FIXED_SP_CLAIM = VerificationClaim(
    claim=BY_FACTOR_FIXED_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris cr+by-factor vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "gam_fit.penalized_irls_general with gaussian_identity() over a "
                "design from assemble_model_design's cr + NEW factor-by producers, "
                "at the recipe's own fixed sp"
            ),
            right_producer=(
                "mgcv gam(..., family=gaussian(link='identity'), sp=sp_fixed), "
                "read as m$linear.predictors"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris cr+by-factor vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "trace of the Polaris hat matrix at the same fixed sp, from the same design"
            ),
            right_producer="mgcv's own sum(m$edf) at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L3 Stage B (fixed `sp`)'s provenance declaration. Both quantities
INDEPENDENT — :func:`fit_by_factor_fixed_sp_case` takes
:class:`RByFactorFixedSpRecipe`, which structurally carries no
`eta`/`edf_total` key."""


@dataclass(frozen=True)
class ByFactorFixedSpFit:
    """The Polaris side's fixed-``sp`` fit plus the ``edf_total`` derived
    from it."""

    fit: GeneralIRLSFit
    edf_total: float


def fit_by_factor_fixed_sp_case(r_case: RByFactorFixedSpRecipe) -> ByFactorFixedSpFit:
    """The independent Python producer for the fixed-``sp`` regime.

    Assembles the design from the shared recipe and fits at the recipe's own
    fixed ``sp`` — never reading ``mgcv``'s ``eta``/``edf_total``
    (:class:`RByFactorFixedSpRecipe` has neither key).
    """
    n_levels = int(r_case["n_levels"])
    sp = r_case["sp"]
    expected_blocks = _n_penalty_blocks(n_levels)
    if len(sp) != expected_blocks:
        raise PolarisValidationError(
            f"fit_by_factor_fixed_sp_case: expected {expected_blocks} sp values "
            f"(reference + {n_levels} level(s)), got {len(sp)}."
        )
    polyear = np.asarray(r_case["PolYear"], dtype=np.float64)
    age = np.asarray(r_case["AttdAge"], dtype=np.float64)
    group = np.asarray(r_case["group"], dtype=np.int64)
    polyear_knots = tuple(float(v) for v in r_case["polyear_knots"])
    age_knots = tuple(float(v) for v in r_case["age_knots"])

    model = by_factor_fixed_sp_model_spec(polyear_knots, age_knots, n_levels)
    design = assemble_model_design(model, {"PolYear": polyear, "AttdAge": age, "GroupFac": group})
    x = design["x"]
    blocks = design["penalty_blocks"]
    if len(blocks) != expected_blocks:
        raise PolarisValidationError(
            f"fit_by_factor_fixed_sp_case: assembled {len(blocks)} penalty blocks, "
            f"expected {expected_blocks}."
        )

    penalty = np.zeros_like(blocks[0])
    for sp_j, block in zip(sp, blocks, strict=True):
        penalty = penalty + float(sp_j) * block

    family: Family = gaussian_identity()
    y = np.asarray(r_case["y"], dtype=np.float64)
    fit = penalized_irls_general(x, y, family=family, penalty=penalty)

    mu_eta = family.link.mu_eta(fit.eta)
    weights = (mu_eta**2) / family.variance(fit.mu)
    xtwx = x.T @ (weights[:, None] * x)
    edf_total = float(np.trace(np.linalg.solve(xtwx + penalty, xtwx)))
    return ByFactorFixedSpFit(fit=fit, edf_total=edf_total)


class RByFactorFixedSpCaseComparison(TypedDict):
    max_abs_eta_diff: float
    edf_total_diff: float
    python_edf_total: float
    mgcv_edf_total: float
    offset_gap: float
    agrees: bool
    evidence: VerificationClaim


def compare_by_factor_fixed_sp_case(
    python_fit: ByFactorFixedSpFit, r_case: RByFactorFixedSpPayload
) -> RByFactorFixedSpCaseComparison:
    """Compare the independent Python fit against the R payload, on the two
    quantities :data:`BY_FACTOR_FIXED_SP_CLAIM` declares and no others."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.fit.eta.shape:
        raise PolarisValidationError(
            f"compare_by_factor_fixed_sp_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.fit.eta)))
    mgcv_edf_total = float(r_case["edf_total"])
    edf_total_diff = python_fit.edf_total - mgcv_edf_total
    agrees = max_abs_eta_diff < _ETA_TOLERANCE and abs(edf_total_diff) < _EDF_TOLERANCE
    return RByFactorFixedSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        edf_total_diff=edf_total_diff,
        python_edf_total=python_fit.edf_total,
        mgcv_edf_total=mgcv_edf_total,
        offset_gap=float(r_case["offset_gap"]),
        agrees=agrees,
        evidence=BY_FACTOR_FIXED_SP_CLAIM,
    )


# ---------------------------------------------------------------------------
# Free sp
# ---------------------------------------------------------------------------


class RByFactorFreeSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**. No ``sp``
    key: free ``sp`` is what this comparison measures, not a value either
    side is handed."""

    n: int
    n_levels: int
    PolYear: list[float]
    AttdAge: list[float]
    group: list[int]
    y: list[float]
    polyear_knots: list[float]
    age_knots: list[float]


class RByFactorFreeSpPayload(RByFactorFreeSpRecipe):
    """The recipe plus ``mgcv``'s own free-``sp`` fit. Read by
    :func:`compare_by_factor_free_sp_case` only."""

    eta: list[float]
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    offset_gap: float
    coef: list[float]
    converged: bool


BY_FACTOR_FREE_SP_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) assembles the "
    "(1+n_levels)-term design (s(PolYear,k=6,bs='cr') + "
    "s(AttdAge,by=GroupFac,k=13,bs='cr')) from the shared recipe (PolYear, "
    "AttdAge, group, n_levels, y, the target formula's own knots) via the "
    "already-independently-verified cr producer and the NEW factor-by "
    "producer, then selects its own log10(lambda) per block by minimizing "
    "gam_reml.reml_score_general (ladder rung L5's free-scale branch, "
    "ADR-231) via gam_reml_optimize.select_lambdas_continuous, and fits "
    "with gam_fit.penalized_irls_general -- never reading mgcv's own eta, "
    "coef, sp or edf; mgcv computes the identical formula via "
    "gam(family=gaussian(link='identity'), method='REML') with free sp, "
    "selecting its own smoothing parameters independently "
    "(scripts/gam_by_factor_free_sp_probe.R). Compared on eta at the "
    "training design, log10(sp) per block, edf_total and per-term edf, "
    "gated on ADR-221's committed criterion (max_abs_eta_diff < 2e-2 and "
    "abs(edf_total_diff) < 1.0), IMPORTED and not redeclared."
)


BY_FACTOR_FREE_SP_CLAIM = VerificationClaim(
    claim=BY_FACTOR_FREE_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris cr+by-factor vs mgcv, free sp, gaussian identity)",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda",
            right_producer="mgcv gam(method='REML') free-sp fit, m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per block (Polaris cr+by-factor vs mgcv, free sp, gaussian)",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda",
            right_producer="mgcv's own log10(m$sp) at its free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris cr+by-factor vs mgcv, free sp, gaussian identity)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-term edf (Polaris cr+by-factor vs mgcv, free sp, gaussian identity)",
            left_producer="PolarisGAMFit.edf_per_term (hat-matrix diagonal sum per term span)",
            right_producer=(
                "mgcv's own summary(m)$s.table[, 'edf'], read positionally in formula order"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L3 Stage B (free `sp`)'s provenance declaration. Every quantity
INDEPENDENT — :func:`fit_by_factor_free_sp_case` takes
:class:`RByFactorFreeSpRecipe`, which structurally excludes
`eta`/`coef`/`sp`/`edf_total`/`term_edf`."""

_FREE_SP_BOUNDS = (-2.0, 12.0)
"""Same as :data:`~polaris_re.analytics.gam_model.PRODUCTION_LOG10_BOUNDS` —
the R probe's own free-sp reference reads a reference-term `log10(sp)` near
8 (`sp ~ 1.15e8`), well inside."""


def fit_by_factor_free_sp_case(
    r_case: RByFactorFreeSpRecipe, *, multistart: bool = False
) -> PolarisGAMFit:
    """The independent Python producer: assemble the design, select its own
    lambda, and fit — never reading ``mgcv``'s ``eta``/``coef``/``sp``/``edf``
    (:class:`RByFactorFreeSpRecipe` has none of these keys).

    Args:
        r_case: the shared recipe.
        multistart: passed through to
            :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`. Default
            ``False`` — a small block count at 3 levels is far smaller than
            the epic's `select=TRUE` structures that needed it.
    """
    n_levels = int(r_case["n_levels"])
    polyear_knots = tuple(float(v) for v in r_case["polyear_knots"])
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    model = by_factor_free_sp_model_spec(polyear_knots, age_knots, n_levels)
    data = {
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "GroupFac": np.asarray(r_case["group"], dtype=np.int64),
    }
    y = np.asarray(r_case["y"], dtype=np.float64)
    return fit_polaris_gam(model, data, y, bounds=_FREE_SP_BOUNDS, multistart=multistart)


@dataclass(frozen=True)
class RByFactorFreeSpCaseComparison:
    """One free-``sp`` case's verdict, every quantity
    :data:`BY_FACTOR_FREE_SP_CLAIM` declares."""

    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    offset_gap: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_by_factor_free_sp_case(
    python_fit: PolarisGAMFit, r_case: RByFactorFreeSpPayload
) -> RByFactorFreeSpCaseComparison:
    """Compare the independent Python free-``sp`` fit against the R payload's
    own free-``sp`` fit, on every quantity :data:`BY_FACTOR_FREE_SP_CLAIM`
    declares.

    ``agrees`` uses ADR-221's committed ``eta``/``edf_total`` criterion
    (imported, :data:`_ETA_TOLERANCE` / :data:`_EDF_TOLERANCE`) — the SAME
    gate this module's own fixed-``sp`` claim uses, per this slice's own
    acceptance criterion (never a fresh `log10(sp)`-only bar, and never
    re-derived, Anchor W5).
    """
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_by_factor_free_sp_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    r_log_sp = np.log10(np.asarray(r_case["sp"], dtype=np.float64))
    if r_log_sp.shape != python_fit.log_lambda.shape:
        raise PolarisValidationError(
            f"compare_by_factor_free_sp_case: R sp has {r_log_sp.shape[0]} "
            f"entries, Python log_lambda has {python_fit.log_lambda.shape[0]}."
        )
    r_term_edf = np.asarray(r_case["term_edf"], dtype=np.float64)
    python_term_edf = np.asarray(list(python_fit.edf_per_term.values()), dtype=np.float64)
    if r_term_edf.shape != python_term_edf.shape:
        raise PolarisValidationError(
            f"compare_by_factor_free_sp_case: R term_edf has {r_term_edf.shape[0]} "
            f"entries, Python edf_per_term has {python_term_edf.shape[0]}."
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
    return RByFactorFreeSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=max_abs_log10_sp_diff,
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=max_abs_term_edf_diff,
        offset_gap=float(r_case["offset_gap"]),
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        evidence=BY_FACTOR_FREE_SP_CLAIM,
    )

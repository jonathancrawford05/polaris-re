"""Unpenalized parametric block against ``mgcv`` — capability ladder rung
**L4** (``docs/PLAN_mgcv_capability_ladder.md`` slice 5), Stage B, both `sp`
regimes.

Stage A (the basis itself, independent of any fit) lives in
:mod:`polaris_re.analytics.gam_basis_parametric` and
:data:`polaris_re.analytics.gam_stage_a.PARAMETRIC_BASIS_CLAIM`, measured
against ``scripts/gam_parametric_stage_a_probe.R``'s own ``model.matrix()``
export. This module is Stage B: does a **model** built from the target
formula's own opening parametric terms (``FaceSize + Smoke +
FaceSize:Smoke``, three ``TermSpec`` objects via :func:`parametric_terms`)
plus an already-verified ``"cr"`` term reproduce ``mgcv``'s own fit, both at
a FIXED, externally-supplied ``sp`` (the smooth's own — the parametric block
carries none) and at ``mgcv``'s own FREELY SELECTED ``sp``?

**One family throughout, matching ladder rungs L3/L5.** Capability ladder
rung L5 (ADR-231) already closed
:func:`~polaris_re.analytics.gam_reml.reml_score_general`'s free-scale branch
before this slice was written, so both :data:`PARAMETRIC_FIXED_SP_CLAIM` and
:data:`PARAMETRIC_FREE_SP_CLAIM` use ``gaussian(identity)`` — no family
switch needed between the two regimes.

**``FaceSize``/``Smoke`` are deliberately independent of ``AttdAge``** (drawn
with no shared covariate) so the parametric block and the smooth cannot be
confounded with each other — a disagreement is then attributable to the
parametric-block construction, not to an ambiguous split of signal.

**The gate is ADR-221's, imported and never re-derived.** Anchor W5 forbids
this epic introducing a tolerance or re-gating anything, so
:data:`_ETA_TOLERANCE` / :data:`_EDF_TOLERANCE` are *imported* from
:mod:`~polaris_re.analytics.gam_select_free_sp_conformance`, the same import
every prior capability-ladder Stage-B module in this epic uses.

**Provenance (ADR-193, ADR-228).** Every compared quantity in both claims is
``INDEPENDENT``: this engine is one of the two producers throughout. Neither
:func:`fit_parametric_fixed_sp_case` nor :func:`fit_parametric_free_sp_case`
takes an R payload — each takes only the narrower
:class:`RParametricFixedSpRecipe` / :class:`RParametricFreeSpRecipe`, which
structurally excludes ``mgcv``'s own ``eta``/``coef``/``sp``/``edf`` (the
ADR-193 mechanical test enforced by the type, the same discipline every
prior conformance module in this epic uses).

**Suspicion, not just a check.** Both R probes give ``FaceSize``, ``Smoke``
and their interaction genuinely different effects on the mean so the
parametric block's own coefficients have something real to fit against, the
same discipline ladder slices 1-4 each carried for their own near-exact
agreements; this module's own test suite carries the same strip/perturb
pair.
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
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "PARAMETRIC_FIXED_SP_CLAIM",
    "PARAMETRIC_FREE_SP_CLAIM",
    "RParametricFixedSpCaseComparison",
    "RParametricFixedSpPayload",
    "RParametricFixedSpRecipe",
    "RParametricFreeSpCaseComparison",
    "RParametricFreeSpPayload",
    "RParametricFreeSpRecipe",
    "compare_parametric_fixed_sp_case",
    "compare_parametric_free_sp_case",
    "fit_parametric_fixed_sp_case",
    "fit_parametric_free_sp_case",
    "parametric_fixed_sp_model_spec",
    "parametric_free_sp_model_spec",
    "parametric_terms",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's committed ``eta`` half of the acceptance gate (``2e-2``),
**imported, not redeclared** (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's committed ``edf_total`` half of the acceptance gate (``1.0``),
imported for the same reason as :data:`_ETA_TOLERANCE`."""

_SMOOTH_LABEL = "s(AttdAge)"
_N_PENALTY_BLOCKS = 1
"""``FaceSize``/``Smoke``/``FaceSize:Smoke`` are unpenalized (module docstring,
:mod:`~polaris_re.analytics.gam_basis_parametric`) and contribute zero
blocks — the smooth's own single block is the whole model's penalty count,
unlike ``re``/factor-``by``'s own multi-block structure."""


def parametric_terms(n_face_levels: int, n_smoke_levels: int) -> tuple[TermSpec, ...]:
    """The three ``TermSpec`` objects the target formula's own ``FaceSize +
    Smoke + FaceSize:Smoke`` expands into — a main effect for each factor,
    then their interaction, all ``basis="parametric"``."""
    return (
        TermSpec(
            label="FaceSize", variables=("FaceSize",), basis="parametric", levels=(n_face_levels,)
        ),
        TermSpec(label="Smoke", variables=("Smoke",), basis="parametric", levels=(n_smoke_levels,)),
        TermSpec(
            label="FaceSize:Smoke",
            variables=("FaceSize", "Smoke"),
            basis="parametric",
            levels=(n_face_levels, n_smoke_levels),
        ),
    )


def _parametric_model_spec(
    n_face_levels: int, n_smoke_levels: int, age_knots: tuple[float, ...]
) -> ModelSpec:
    smooth_term = TermSpec(
        label=_SMOOTH_LABEL,
        variables=("AttdAge",),
        basis="cr",
        k=(len(age_knots),),
        knots=(("AttdAge", age_knots),),
    )
    return ModelSpec(
        family="gaussian",
        link="identity",
        terms=(*parametric_terms(n_face_levels, n_smoke_levels), smooth_term),
    )


def parametric_fixed_sp_model_spec(
    n_face_levels: int, n_smoke_levels: int, age_knots: tuple[float, ...]
) -> ModelSpec:
    """The four-term ``ModelSpec`` (three parametric + one smooth) under
    ``gaussian(identity)`` (fixed ``sp``)."""
    return _parametric_model_spec(n_face_levels, n_smoke_levels, age_knots)


def parametric_free_sp_model_spec(
    n_face_levels: int, n_smoke_levels: int, age_knots: tuple[float, ...]
) -> ModelSpec:
    """The same ``ModelSpec`` shape, for the free-``sp`` regime. Identical to
    :func:`parametric_fixed_sp_model_spec` today (both regimes use
    ``gaussian(identity)``, module docstring) — kept as a separate function so
    a future divergence between the two regimes does not require renaming
    call sites."""
    return _parametric_model_spec(n_face_levels, n_smoke_levels, age_knots)


def _data_from_recipe(
    face_group: list[int], smoke_group: list[int], attd_age: list[float]
) -> dict[str, np.ndarray]:
    return {
        "FaceSize": np.asarray(face_group, dtype=np.int64),
        "Smoke": np.asarray(smoke_group, dtype=np.int64),
        "AttdAge": np.asarray(attd_age, dtype=np.float64),
    }


# ---------------------------------------------------------------------------
# Fixed sp
# ---------------------------------------------------------------------------


class RParametricFixedSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**.

    The ADR-193 mechanical test applied structurally: this type has no
    ``eta``, ``coef`` or ``edf_total`` key, so
    :func:`fit_parametric_fixed_sp_case` cannot read ``mgcv``'s own fit even
    if a caller hands it the wider :class:`RParametricFixedSpPayload`.
    """

    n: int
    face_levels: list[str]
    smoke_levels: list[str]
    face_group: list[int]
    smoke_group: list[int]
    AttdAge: list[float]
    y: list[float]
    age_knots: list[float]
    sp: list[float]


class RParametricFixedSpPayload(RParametricFixedSpRecipe):
    """The recipe plus ``scripts/gam_parametric_probe.R``'s OWN fit. Read by
    :func:`compare_parametric_fixed_sp_case` only."""

    eta: list[float]
    edf_total: float
    term_edf: list[float]
    offset_gap: float
    coef: list[float]
    converged: bool


PARAMETRIC_FIXED_SP_CLAIM_SENTENCE = (
    "polaris_re assembles the four-term design (build_python_parametric_term "
    "for FaceSize, Smoke and FaceSize:Smoke; build_python_cr_term for "
    "s(AttdAge,k=13,bs='cr')) through assemble_model_design from the shared "
    "recipe (face_group, smoke_group, AttdAge, y, the target formula's own "
    "AttdAge knots, sp), and fits it with gam_fit.penalized_irls_general "
    "under gaussian(link='identity') at a FIXED, externally-supplied sp for "
    "the smooth's own single penalty block -- never reading mgcv's own eta, "
    "coef or edf. mgcv computes the identical model natively via "
    "gam(y ~ FaceSize + Smoke + FaceSize:Smoke + s(AttdAge,k=13,bs='cr'), "
    "family=gaussian(link='identity'), knots=<the same vector>, sp=sp_fixed) "
    "and reports m$linear.predictors and sum(m$edf) "
    "(scripts/gam_parametric_probe.R). Compared on eta at the training "
    "design and on edf_total, against ADR-221's committed criterion "
    "(max_abs_eta_diff < 2e-2 and abs(edf_total_diff) < 1.0), IMPORTED and "
    "not redeclared. Coefficients are never compared (PLAN Anchor 2)."
)
"""The claim sentence, written before the code per
``docs/VERIFICATION_STANDARD.md`` §3.2."""


PARAMETRIC_FIXED_SP_CLAIM = VerificationClaim(
    claim=PARAMETRIC_FIXED_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris parametric+cr vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "gam_fit.penalized_irls_general with gaussian_identity() over a "
                "design from assemble_model_design's NEW parametric producer plus "
                "the existing cr producer, at the recipe's own fixed sp"
            ),
            right_producer=(
                "mgcv gam(..., family=gaussian(link='identity'), sp=sp_fixed), "
                "read as m$linear.predictors"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris parametric+cr vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "trace of the Polaris hat matrix at the same fixed sp, from the same design"
            ),
            right_producer="mgcv's own sum(m$edf) at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L4 Stage B (fixed `sp`)'s provenance declaration. Both quantities
INDEPENDENT — :func:`fit_parametric_fixed_sp_case` takes
:class:`RParametricFixedSpRecipe`, which structurally carries no
`eta`/`edf_total` key."""


@dataclass(frozen=True)
class ParametricFixedSpFit:
    """The Polaris side's fixed-``sp`` fit plus the ``edf_total`` derived
    from it."""

    fit: GeneralIRLSFit
    edf_total: float


def fit_parametric_fixed_sp_case(r_case: RParametricFixedSpRecipe) -> ParametricFixedSpFit:
    """The independent Python producer for the fixed-``sp`` regime.

    Assembles the design from the shared recipe and fits at the recipe's own
    fixed ``sp`` — never reading ``mgcv``'s ``eta``/``edf_total``
    (:class:`RParametricFixedSpRecipe` has neither key).
    """
    sp = r_case["sp"]
    if len(sp) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_parametric_fixed_sp_case: expected {_N_PENALTY_BLOCKS} sp "
            f"value(s) (the smooth's own single block), got {len(sp)}."
        )
    n_face_levels = len(r_case["face_levels"])
    n_smoke_levels = len(r_case["smoke_levels"])
    age_knots = tuple(float(v) for v in r_case["age_knots"])

    model = parametric_fixed_sp_model_spec(n_face_levels, n_smoke_levels, age_knots)
    data = _data_from_recipe(r_case["face_group"], r_case["smoke_group"], r_case["AttdAge"])
    design = assemble_model_design(model, data)
    x = design["x"]
    blocks = design["penalty_blocks"]
    if len(blocks) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_parametric_fixed_sp_case: assembled {len(blocks)} penalty "
            f"blocks, expected {_N_PENALTY_BLOCKS}."
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
    return ParametricFixedSpFit(fit=fit, edf_total=edf_total)


class RParametricFixedSpCaseComparison(TypedDict):
    max_abs_eta_diff: float
    edf_total_diff: float
    python_edf_total: float
    mgcv_edf_total: float
    offset_gap: float
    agrees: bool
    evidence: VerificationClaim


def compare_parametric_fixed_sp_case(
    python_fit: ParametricFixedSpFit, r_case: RParametricFixedSpPayload
) -> RParametricFixedSpCaseComparison:
    """Compare the independent Python fit against the R payload, on the two
    quantities :data:`PARAMETRIC_FIXED_SP_CLAIM` declares and no others."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.fit.eta.shape:
        raise PolarisValidationError(
            f"compare_parametric_fixed_sp_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.fit.eta)))
    mgcv_edf_total = float(r_case["edf_total"])
    edf_total_diff = python_fit.edf_total - mgcv_edf_total
    agrees = max_abs_eta_diff < _ETA_TOLERANCE and abs(edf_total_diff) < _EDF_TOLERANCE
    return RParametricFixedSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        edf_total_diff=edf_total_diff,
        python_edf_total=python_fit.edf_total,
        mgcv_edf_total=mgcv_edf_total,
        offset_gap=float(r_case["offset_gap"]),
        agrees=agrees,
        evidence=PARAMETRIC_FIXED_SP_CLAIM,
    )


# ---------------------------------------------------------------------------
# Free sp
# ---------------------------------------------------------------------------


class RParametricFreeSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**. No ``sp``
    key: free ``sp`` is what this comparison measures, not a value either
    side is handed."""

    n: int
    face_levels: list[str]
    smoke_levels: list[str]
    face_group: list[int]
    smoke_group: list[int]
    AttdAge: list[float]
    y: list[float]
    age_knots: list[float]


class RParametricFreeSpPayload(RParametricFreeSpRecipe):
    """The recipe plus ``mgcv``'s own free-``sp`` fit. Read by
    :func:`compare_parametric_free_sp_case` only."""

    eta: list[float]
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    offset_gap: float
    coef: list[float]
    converged: bool


PARAMETRIC_FREE_SP_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) assembles the "
    "four-term design (FaceSize + Smoke + FaceSize:Smoke + "
    "s(AttdAge,k=13,bs='cr')) from the shared recipe (face_group, "
    "smoke_group, AttdAge, y, the target formula's own AttdAge knots) via "
    "the NEW parametric producer and the already-independently-verified cr "
    "producer, then selects the smooth's own log10(lambda) by minimizing "
    "gam_reml.reml_score_general (ladder rung L5's free-scale branch, "
    "ADR-231) via gam_reml_optimize.select_lambdas_continuous, and fits "
    "with gam_fit.penalized_irls_general -- never reading mgcv's own eta, "
    "coef, sp or edf; mgcv computes the identical formula via "
    "gam(family=gaussian(link='identity'), method='REML') with free sp, "
    "selecting its own smoothing parameter independently "
    "(scripts/gam_parametric_free_sp_probe.R). Compared on eta at the "
    "training design, log10(sp), edf_total and per-term edf, gated on "
    "ADR-221's committed criterion (max_abs_eta_diff < 2e-2 and "
    "abs(edf_total_diff) < 1.0), IMPORTED and not redeclared."
)


PARAMETRIC_FREE_SP_CLAIM = VerificationClaim(
    claim=PARAMETRIC_FREE_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris parametric+cr vs mgcv, free sp, gaussian identity)",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda",
            right_producer="mgcv gam(method='REML') free-sp fit, m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) (Polaris parametric+cr vs mgcv, free sp, gaussian identity)",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda",
            right_producer="mgcv's own log10(m$sp) at its free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris parametric+cr vs mgcv, free sp, gaussian identity)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-term edf (Polaris parametric+cr vs mgcv, free sp, gaussian identity)",
            left_producer="PolarisGAMFit.edf_per_term (hat-matrix diagonal sum per term span)",
            right_producer=(
                "mgcv's own summary(m)$s.table[, 'edf'] -- the smooth's own edf; the "
                "parametric block carries none (unpenalized, no summary$s.table row)"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L4 Stage B (free `sp`)'s provenance declaration. Every quantity
INDEPENDENT — :func:`fit_parametric_free_sp_case` takes
:class:`RParametricFreeSpRecipe`, which structurally excludes
`eta`/`coef`/`sp`/`edf_total`/`term_edf`."""

_FREE_SP_BOUNDS = (-2.0, 12.0)
"""Same as :data:`~polaris_re.analytics.gam_model.PRODUCTION_LOG10_BOUNDS`."""


def fit_parametric_free_sp_case(
    r_case: RParametricFreeSpRecipe, *, multistart: bool = False
) -> PolarisGAMFit:
    """The independent Python producer: assemble the design, select the
    smooth's own lambda, and fit — never reading ``mgcv``'s
    ``eta``/``coef``/``sp``/``edf`` (:class:`RParametricFreeSpRecipe` has none
    of these keys).

    Args:
        r_case: the shared recipe.
        multistart: passed through to
            :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`. Default
            ``False`` — a single penalized block is far smaller than the
            epic's `select=TRUE` structures that needed it.
    """
    n_face_levels = len(r_case["face_levels"])
    n_smoke_levels = len(r_case["smoke_levels"])
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    model = parametric_free_sp_model_spec(n_face_levels, n_smoke_levels, age_knots)
    data = _data_from_recipe(r_case["face_group"], r_case["smoke_group"], r_case["AttdAge"])
    y = np.asarray(r_case["y"], dtype=np.float64)
    return fit_polaris_gam(model, data, y, bounds=_FREE_SP_BOUNDS, multistart=multistart)


@dataclass(frozen=True)
class RParametricFreeSpCaseComparison:
    """One free-``sp`` case's verdict, every quantity
    :data:`PARAMETRIC_FREE_SP_CLAIM` declares."""

    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    offset_gap: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_parametric_free_sp_case(
    python_fit: PolarisGAMFit, r_case: RParametricFreeSpPayload
) -> RParametricFreeSpCaseComparison:
    """Compare the independent Python free-``sp`` fit against the R payload's
    own free-``sp`` fit, on every quantity :data:`PARAMETRIC_FREE_SP_CLAIM`
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
            f"compare_parametric_free_sp_case: R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    r_log_sp = np.log10(np.asarray(r_case["sp"], dtype=np.float64))
    if r_log_sp.shape != python_fit.log_lambda.shape:
        raise PolarisValidationError(
            f"compare_parametric_free_sp_case: R sp has {r_log_sp.shape[0]} "
            f"entries, Python log_lambda has {python_fit.log_lambda.shape[0]}."
        )
    r_term_edf = np.asarray(r_case["term_edf"], dtype=np.float64)
    # mgcv's summary(m)$s.table carries only the SMOOTH's own row (the
    # parametric block is unpenalized and has no s.table entry at all) --
    # Python's edf_per_term carries one entry PER TermSpec, including the
    # three zero-penalty parametric ones, so it is filtered to the smooth
    # term for a shape-comparable reading, matching what mgcv reports.
    python_term_edf = np.asarray([python_fit.edf_per_term[_SMOOTH_LABEL]], dtype=np.float64)
    if r_term_edf.shape != python_term_edf.shape:
        raise PolarisValidationError(
            f"compare_parametric_free_sp_case: R term_edf has {r_term_edf.shape[0]} "
            f"entries, Python's smooth-only edf has {python_term_edf.shape[0]}."
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
    return RParametricFreeSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=max_abs_log10_sp_diff,
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=max_abs_term_edf_diff,
        offset_gap=float(r_case["offset_gap"]),
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        evidence=PARAMETRIC_FREE_SP_CLAIM,
    )

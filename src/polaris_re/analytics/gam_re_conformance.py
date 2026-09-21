"""``bs="re"`` against ``mgcv`` — capability ladder rung **L2**
(``docs/PLAN_mgcv_capability_ladder.md`` slice 2), Stage B, both `sp` regimes.

Stage A (the basis itself, independent of any fit) lives in
:mod:`polaris_re.analytics.gam_basis_re` and
:data:`polaris_re.analytics.gam_stage_a.RE_BASIS_CLAIM`. This module is Stage B:
does a **model** built from a ``"re"`` term plus an already-verified ``"cr"``
term reproduce ``mgcv``'s own fit, both at a FIXED, externally-supplied ``sp``
and at ``mgcv``'s own FREELY SELECTED ``sp``?

**Two claims, two families, and why they differ from each other.**

* :data:`RE_FIXED_SP_CLAIM` — ``gaussian(identity)``, the SAME reasoning
  ladder rung L1 (:mod:`gam_gaussian_conformance`) used: at fixed ``sp`` the
  Gaussian fit is ordinary penalized least squares and the (estimated) scale
  never enters it, so this is a complete measurement of the ``"re"`` term's
  construction and its interaction with the fitter, not a hedge.
* :data:`RE_FREE_SP_CLAIM` — ``poisson(log)``. Gaussian's scale is unknown
  (``dispersion_fixed=False``) and :func:`~polaris_re.analytics.gam_reml.reml_score_general`
  raises on a free scale until capability-ladder rung L5 (slice 3) — the
  blocker ``PLAN_mgcv_capability_ladder.md`` §2.2 names. Poisson-log carries
  ``dispersion_fixed=True`` and its free-``sp`` search is ALREADY verified
  elsewhere in this epic (``gam_multiterm_free_sp_probe.R`` uses
  ``binomial(cloglog)``; ADR-196-199 verify the criterion and its continuous
  outer search under a fixed-dispersion family). So the ``"re"`` term's own
  free-``sp`` search is measured WITHOUT waiting on L5 — the plan's own point
  for this slice.

**The gate is ADR-221's, imported and never re-derived.** Anchor W5 forbids
this epic introducing a tolerance or re-gating anything, so
:data:`_ETA_TOLERANCE` / :data:`_EDF_TOLERANCE` are *imported* from
:mod:`~polaris_re.analytics.gam_select_free_sp_conformance` rather than
redeclared — same import :mod:`gam_gaussian_conformance` already uses.

**Provenance (ADR-193, ADR-228).** Every compared quantity in both claims is
``INDEPENDENT``: this engine is one of the two producers throughout. Neither
:func:`fit_re_fixed_sp_case` nor :func:`fit_re_free_sp_case` takes an R
payload — each takes only the narrower :class:`RReRecipe` /
:class:`RReFreeSpRecipe`, which structurally excludes ``mgcv``'s own
``eta``/``coef``/``sp``/``edf`` (the ADR-193 mechanical test enforced by the
type, the same discipline every prior conformance module in this epic uses).

**Suspicion, not just a check (the continuation's own instruction for this
slice).** ``bs="re"``'s penalty is the identity and its ``edf`` has a closed
form, so a near-exact agreement here is a suspicion before it is a result.
This module's own test suite carries the SAME pair of independence tests
ADR-229 (ladder slice 1) used to make its own near-exact agreement
reportable: (1) every ``mgcv``-produced key stripped from the payload still
gives a bit-identical Polaris fit (:class:`RReRecipe` / :class:`RReFreeSpRecipe`
carry none of those keys, checked structurally and by a runtime test), and
(2) ``edf_total`` measurably moves when the ``"re"`` block's own penalty
changes (a passing comparison must not be vacuously insensitive to the term
under test).
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
    "RE_FIXED_SP_CLAIM",
    "RE_FREE_SP_CLAIM",
    "RReFixedSpCaseComparison",
    "RReFixedSpPayload",
    "RReFixedSpRecipe",
    "RReFreeSpCaseComparison",
    "RReFreeSpPayload",
    "RReFreeSpRecipe",
    "compare_re_fixed_sp_case",
    "compare_re_free_sp_case",
    "fit_re_fixed_sp_case",
    "fit_re_free_sp_case",
    "re_fixed_sp_model_spec",
    "re_free_sp_model_spec",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's committed ``eta`` half of the acceptance gate (``2e-2``),
**imported, not redeclared** (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's committed ``edf_total`` half of the acceptance gate (``1.0``),
imported for the same reason as :data:`_ETA_TOLERANCE`."""

_N_PENALTY_BLOCKS = 2
"""``s(AttdAge)`` 1 + ``s(GroupFac, bs="re")`` 1 — a ``re`` term carries
exactly ONE penalty block regardless of its factor's level count (module
docstring / ``docs/MGCV_NOTATION_PRIMER.md`` §4), unlike ``sz``'s
one-block-per-level."""

_REF_LABEL = "s(AttdAge)"
_RE_LABEL = "s(GroupFac)"


def _re_model_spec(
    family: str, link: str, age_knots: tuple[float, ...], n_levels: int
) -> ModelSpec:
    ref_term = TermSpec(
        label=_REF_LABEL,
        variables=("AttdAge",),
        basis="cr",
        k=(len(age_knots),),
        knots=(("AttdAge", age_knots),),
    )
    re_term = TermSpec(
        label=_RE_LABEL,
        variables=("GroupFac",),
        basis="re",
        n_levels=n_levels,
    )
    return ModelSpec(family=family, link=link, terms=(ref_term, re_term))


def re_fixed_sp_model_spec(age_knots: tuple[float, ...], n_levels: int) -> ModelSpec:
    """The two-term ``ModelSpec`` under ``gaussian(identity)`` (fixed ``sp``)."""
    return _re_model_spec("gaussian", "identity", age_knots, n_levels)


def re_free_sp_model_spec(age_knots: tuple[float, ...], n_levels: int) -> ModelSpec:
    """The two-term ``ModelSpec`` under ``poisson(log)`` (free ``sp``)."""
    return _re_model_spec("poisson", "log", age_knots, n_levels)


# ---------------------------------------------------------------------------
# Fixed sp — gaussian(identity), the ladder slice-1 pattern.
# ---------------------------------------------------------------------------


class RReFixedSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**.

    The ADR-193 mechanical test applied structurally: this type has no
    ``eta``, ``coef`` or ``edf_total`` key, so :func:`fit_re_fixed_sp_case`
    cannot read ``mgcv``'s own fit even if a caller hands it the wider
    :class:`RReFixedSpPayload`.
    """

    n: int
    n_levels: int
    AttdAge: list[float]
    group: list[int]
    y: list[float]
    age_knots: list[float]
    sp: list[float]


class RReFixedSpPayload(RReFixedSpRecipe):
    """The recipe plus ``scripts/gam_re_probe.R``'s OWN fit. Read by
    :func:`compare_re_fixed_sp_case` only."""

    eta: list[float]
    edf_total: float
    term_edf: list[float]
    offset_gap: float
    coef: list[float]
    converged: bool


RE_FIXED_SP_CLAIM_SENTENCE = (
    "polaris_re assembles the two-term design (build_python_cr_term for "
    "s(AttdAge,k=13,bs='cr'), build_python_re_term for "
    "s(GroupFac,bs='re')) through assemble_model_design from the shared "
    "recipe (AttdAge, group, n_levels, y, the target formula's own age "
    "knots, sp), and fits it with gam_fit.penalized_irls_general under "
    "gaussian(link='identity') at a FIXED, externally-supplied sp — one per "
    "penalty block, two blocks — never reading mgcv's own eta, coef or edf. "
    "mgcv computes the identical model natively via "
    "gam(y ~ s(AttdAge,k=13,bs='cr') + s(GroupFac,bs='re'), "
    "family=gaussian(link='identity'), knots=<the same vector>, sp=sp_fixed) "
    "and reports m$linear.predictors and sum(m$edf) "
    "(scripts/gam_re_probe.R). Compared on eta at the training design and "
    "on edf_total, against ADR-221's committed criterion "
    "(max_abs_eta_diff < 2e-2 and abs(edf_total_diff) < 1.0), IMPORTED and "
    "not redeclared. FIXED sp only, for the same reason ladder rung L1 is "
    "fixed-sp only: gaussian estimates its scale and reml_score_general "
    "raises on a free scale until ladder rung L5. Coefficients are never "
    "compared (PLAN Anchor 2)."
)
"""The claim sentence, written before the code per
``docs/VERIFICATION_STANDARD.md`` §3.2."""


RE_FIXED_SP_CLAIM = VerificationClaim(
    claim=RE_FIXED_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris re+cr vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "gam_fit.penalized_irls_general with gaussian_identity() over a "
                "design from assemble_model_design's cr + NEW re producers, at "
                "the recipe's own fixed sp"
            ),
            right_producer=(
                "mgcv gam(..., family=gaussian(link='identity'), sp=sp_fixed), "
                "read as m$linear.predictors"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris re+cr vs mgcv, fixed sp, gaussian identity)",
            left_producer=(
                "trace of the Polaris hat matrix at the same fixed sp, from the same design"
            ),
            right_producer="mgcv's own sum(m$edf) at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L2 Stage B (fixed `sp`)'s provenance declaration. Both quantities
INDEPENDENT — :func:`fit_re_fixed_sp_case` takes :class:`RReFixedSpRecipe`,
which structurally carries no `eta`/`edf_total` key."""


@dataclass(frozen=True)
class ReFixedSpFit:
    """The Polaris side's fixed-``sp`` fit plus the ``edf_total`` derived
    from it."""

    fit: GeneralIRLSFit
    edf_total: float


def fit_re_fixed_sp_case(r_case: RReFixedSpRecipe) -> ReFixedSpFit:
    """The independent Python producer for the fixed-``sp`` regime.

    Assembles the design from the shared recipe and fits at the recipe's own
    fixed ``sp`` — never reading ``mgcv``'s ``eta``/``edf_total``
    (:class:`RReFixedSpRecipe` has neither key).
    """
    sp = r_case["sp"]
    if len(sp) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_re_fixed_sp_case: expected {_N_PENALTY_BLOCKS} sp values "
            f"(reference, re), got {len(sp)}."
        )
    age = np.asarray(r_case["AttdAge"], dtype=np.float64)
    group = np.asarray(r_case["group"], dtype=np.int64)
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    n_levels = int(r_case["n_levels"])

    model = re_fixed_sp_model_spec(age_knots, n_levels)
    design = assemble_model_design(model, {"AttdAge": age, "GroupFac": group})
    x = design["x"]
    blocks = design["penalty_blocks"]
    if len(blocks) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_re_fixed_sp_case: assembled {len(blocks)} penalty blocks, "
            f"expected {_N_PENALTY_BLOCKS}."
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
    return ReFixedSpFit(fit=fit, edf_total=edf_total)


class RReFixedSpCaseComparison(TypedDict):
    max_abs_eta_diff: float
    edf_total_diff: float
    python_edf_total: float
    mgcv_edf_total: float
    offset_gap: float
    agrees: bool
    evidence: VerificationClaim


def compare_re_fixed_sp_case(
    python_fit: ReFixedSpFit, r_case: RReFixedSpPayload
) -> RReFixedSpCaseComparison:
    """Compare the independent Python fit against the R payload, on the two
    quantities :data:`RE_FIXED_SP_CLAIM` declares and no others."""
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.fit.eta.shape:
        raise PolarisValidationError(
            f"compare_re_fixed_sp_case: R eta has shape {r_eta.shape}, Python "
            f"eta has shape {python_fit.fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.fit.eta)))
    mgcv_edf_total = float(r_case["edf_total"])
    edf_total_diff = python_fit.edf_total - mgcv_edf_total
    agrees = max_abs_eta_diff < _ETA_TOLERANCE and abs(edf_total_diff) < _EDF_TOLERANCE
    return RReFixedSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        edf_total_diff=edf_total_diff,
        python_edf_total=python_fit.edf_total,
        mgcv_edf_total=mgcv_edf_total,
        offset_gap=float(r_case["offset_gap"]),
        agrees=agrees,
        evidence=RE_FIXED_SP_CLAIM,
    )


# ---------------------------------------------------------------------------
# Free sp — poisson(log), so the search does not wait on rung L5.
# ---------------------------------------------------------------------------


class RReFreeSpRecipe(TypedDict):
    """The shared recipe both sides fit — and **nothing else**. No ``sp``
    key: free ``sp`` is what this comparison measures, not a value either
    side is handed."""

    n: int
    n_levels: int
    AttdAge: list[float]
    group: list[int]
    y: list[float]
    age_knots: list[float]


class RReFreeSpPayload(RReFreeSpRecipe):
    """The recipe plus ``mgcv``'s own free-``sp`` fit. Read by
    :func:`compare_re_free_sp_case` only."""

    eta: list[float]
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    offset_gap: float
    coef: list[float]
    converged: bool


RE_FREE_SP_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) assembles the "
    "two-term design (s(AttdAge,k=13,bs='cr') + s(GroupFac,bs='re')) from "
    "the shared recipe (AttdAge, group, n_levels, y, the target formula's "
    "own age knots) via the already-independently-verified cr producer and "
    "the NEW re producer, then selects its own log10(lambda) per block by "
    "minimizing gam_reml.reml_score_general via "
    "gam_reml_optimize.select_lambdas_continuous, and fits with "
    "gam_fit.penalized_irls_general — never reading mgcv's own eta, coef, "
    "sp or edf; mgcv computes the identical two-term formula via "
    "gam(family=poisson(link='log'), method='REML') with free sp, "
    "selecting its own smoothing parameters independently "
    "(scripts/gam_re_free_sp_probe.R). poisson(log) is used (not gaussian) "
    "so the search does not wait on ladder rung L5 (scale-estimated REML) — "
    "it carries dispersion_fixed=True and its free-sp search is already "
    "verified elsewhere in this epic. Compared on eta at the training "
    "design, log10(sp) per block, edf_total and per-term edf, gated on "
    "ADR-221's committed criterion (max_abs_eta_diff < 2e-2 and "
    "abs(edf_total_diff) < 1.0), IMPORTED and not redeclared."
)


RE_FREE_SP_CLAIM = VerificationClaim(
    claim=RE_FREE_SP_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris re+cr vs mgcv, free sp, poisson log)",
            left_producer="gam_model.fit_polaris_gam at its own selected log_lambda",
            right_producer="mgcv gam(method='REML') free-sp fit, m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per block (Polaris re+cr vs mgcv, free sp, poisson log)",
            left_producer="gam_reml_optimize.select_lambdas_continuous's own log_lambda",
            right_producer="mgcv's own log10(m$sp) at its free-sp REML selection",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris re+cr vs mgcv, free sp, poisson log)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-term edf (Polaris re+cr vs mgcv, free sp, poisson log)",
            left_producer="PolarisGAMFit.edf_per_term (hat-matrix diagonal sum per term span)",
            right_producer=(
                "mgcv's own summary(m)$s.table[, 'edf'], read positionally in formula order"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L2 Stage B (free `sp`)'s provenance declaration. Every quantity
INDEPENDENT — :func:`fit_re_free_sp_case` takes :class:`RReFreeSpRecipe`,
which structurally excludes `eta`/`coef`/`sp`/`edf_total`/`term_edf`."""

_FREE_SP_BOUNDS = (-2.0, 12.0)
"""Same as :data:`~polaris_re.analytics.gam_model.PRODUCTION_LOG10_BOUNDS` —
this tier-1 recipe's own free-sp read on the `cr` block lands near
`log10(sp) ~ 6.75` (well inside), reused here rather than a fresh literal so
the two never drift independently."""


def fit_re_free_sp_case(r_case: RReFreeSpRecipe, *, multistart: bool = False) -> PolarisGAMFit:
    """The independent Python producer: assemble the design, select its own
    lambda, and fit — never reading ``mgcv``'s ``eta``/``coef``/``sp``/``edf``
    (:class:`RReFreeSpRecipe` has none of these keys).

    Args:
        r_case: the shared recipe.
        multistart: passed through to
            :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`. Default
            ``False`` — a two-block search is far smaller than the epic's
            7-block `select=TRUE` structures that needed it.
    """
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    n_levels = int(r_case["n_levels"])
    model = re_free_sp_model_spec(age_knots, n_levels)
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "GroupFac": np.asarray(r_case["group"], dtype=np.int64),
    }
    y = np.asarray(r_case["y"], dtype=np.float64)
    return fit_polaris_gam(model, data, y, bounds=_FREE_SP_BOUNDS, multistart=multistart)


@dataclass(frozen=True)
class RReFreeSpCaseComparison:
    """One free-``sp`` case's verdict, every quantity :data:`RE_FREE_SP_CLAIM`
    declares."""

    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    edf_total_diff: float
    max_abs_term_edf_diff: float
    offset_gap: float
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def compare_re_free_sp_case(
    python_fit: PolarisGAMFit, r_case: RReFreeSpPayload
) -> RReFreeSpCaseComparison:
    """Compare the independent Python free-``sp`` fit against the R payload's
    own free-``sp`` fit, on every quantity :data:`RE_FREE_SP_CLAIM` declares.

    ``agrees`` uses ADR-221's committed ``eta``/``edf_total`` criterion
    (imported, :data:`_ETA_TOLERANCE` / :data:`_EDF_TOLERANCE`) — the SAME
    gate ladder rung L1 and this module's own fixed-``sp`` claim use, per
    this slice's own acceptance criterion (never a fresh `log10(sp)`-only
    bar, and never re-derived, Anchor W5).
    """
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_re_free_sp_case: R eta has shape {r_eta.shape}, Python "
            f"eta has shape {python_fit.eta.shape}."
        )
    r_log_sp = np.log10(np.asarray(r_case["sp"], dtype=np.float64))
    if r_log_sp.shape != python_fit.log_lambda.shape:
        raise PolarisValidationError(
            f"compare_re_free_sp_case: R sp has {r_log_sp.shape[0]} entries, "
            f"Python log_lambda has {python_fit.log_lambda.shape[0]}."
        )
    r_term_edf = np.asarray(r_case["term_edf"], dtype=np.float64)
    python_term_edf = np.asarray(list(python_fit.edf_per_term.values()), dtype=np.float64)
    if r_term_edf.shape != python_term_edf.shape:
        raise PolarisValidationError(
            f"compare_re_free_sp_case: R term_edf has {r_term_edf.shape[0]} "
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
    return RReFreeSpCaseComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        max_abs_log10_sp_diff=max_abs_log10_sp_diff,
        edf_total_diff=edf_total_diff,
        max_abs_term_edf_diff=max_abs_term_edf_diff,
        offset_gap=float(r_case["offset_gap"]),
        at_bound=python_fit.at_bound,
        converged=python_fit.converged,
        agrees=agrees,
        evidence=RE_FREE_SP_CLAIM,
    )

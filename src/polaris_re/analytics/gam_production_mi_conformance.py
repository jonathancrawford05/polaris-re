"""A four-term penalized ANOVA-shaped HGAM, measured against ``mgcv`` — the
production wiring epic's slice 1 (``docs/PLAN_gam_production_wiring.md``).

**READ THIS FIRST: the premise this module was built on was false, and the
correction is the durable finding.** ADR-227 amendment 1, 2026-09-16.

This module was written to measure "the shipped dashboard's ``te()`` model form"
because ``PLAN_gam_production_wiring.md`` blocker A said that is what the
dashboard fits. **It is not.** The ``te(...)`` came from ``TensorMIModel``'s
docstring, whose same sentence glosses it as *"a tensor-product B-spline
surface"* — prose, not an ``mgcv`` formula. What the dashboard actually does:

.. code-block:: text

    bs(age, df=6) + bs(year, df=4) + bs(age):bs(year) + bs(duration, df=4)
    fitted by sm.GLM(..., family=Poisson(), offset=...)      # NO PENALTY

Two consequences, either fatal to the original framing:

1. The design is **main effect + main effect + interaction** — the ANOVA shape,
   i.e. ``s+s+ti``-shaped, not ``te``-shaped.
   :mod:`~polaris_re.analytics.experience_gam_penalized`'s own docstring already
   said so: *"``TensorMIModel`` builds ``1 + bs(age) + bs(year) + interaction``
   — patsy's main-effects form."*
2. The fit is **unpenalized**, so "a different penalty structure" described a
   property the shipped model does not have. Measured with ``fx=TRUE``:
   unpenalized, ``te`` and ``s+s+ti`` agree to ``8.88e-16`` (tier 3;
   ``2.14e-15`` tier 1). **100% of the penalized gap is a penalty artefact.**

**The dashboard is a placeholder, not the parity target** (maintainer,
2026-09-16). The objective is parity across a suite of mgcv model forms —
see ``docs/MGCV_FEATURE_COVERAGE.md``, which carries the coverage table and the
capability ladder this work is now sequenced behind.

**What this module is still good for, and it is not nothing.** It measures
:func:`~polaris_re.analytics.gam_model.fit_polaris_gam` against ``mgcv`` on a
genuinely production-shaped four-term penalized HGAM —
``s(age) + s(year) + ti(age, year) + s(duration)``, Poisson-log with an offset,
free ``sp`` REML — and reads ``max_abs_eta_diff = 3.18e-05`` against ADR-221's
``2e-2``, tier-3 confirmed. **A capability data point, not a gate verdict.**

``scripts/gam_production_mi_probe.R`` fits both forms natively, so the
comparison separates three questions:

===  ==========================  ===================================  ==============================
#    comparison                  what it answers                      provenance
===  ==========================  ===================================  ==============================
(1)  Polaris vs mgcv ``anova``   does our engine reproduce this       INDEPENDENT (about Polaris)
                                 4-term penalized HGAM?
(2)  Polaris vs mgcv ``te``      does the decomposition reproduce a   INDEPENDENT (about Polaris)
                                 full tensor, under penalty?
(3)  mgcv ``anova`` vs ``te``    are the two penalized forms the      INDEPENDENT, but entirely
                                 same fit?                            inside R — real evidence
                                                                      about ``mgcv``, **none**
                                                                      about Polaris
===  ==========================  ===================================  ==============================

(3) is the localiser — it separates "our engine is wrong" from "these are two
different models" — and read against the probe's ``unpenalized`` block it is
also what shows the difference to be purely a penalty effect. Its evidence class
has precedent: ``docs/VERIFICATION_STANDARD.md`` §5 lists the R-side
``smoothCon``/``lpmatrix`` guard the same way.

**The gate is ADR-221's, reused verbatim and never re-derived.** Anchor W5
forbids this epic widening a tolerance, so :data:`_ETA_TOLERANCE` /
:data:`_EDF_TOLERANCE` are *imported* from
:mod:`~polaris_re.analytics.gam_select_free_sp_conformance` rather than
redeclared — a copied constant can drift, an imported one cannot. ``log10(sp)``
is reported and **never gated**: the two forms do not carry the same number of
smoothing parameters (3 against 5), so it is undefined between them.

**LIMITS, stated up front rather than discovered downstream.**

* **The amount basis is out of scope** — quasi-Poisson, and
  ``gam_reml.reml_score_general`` raises on ``dispersion_fixed=False`` (the
  plan's blocker B). PLAN slice 1's own stated scope is the count basis.
* **Unpenalized parametric columns are not expressible.**
  :func:`~polaris_re.analytics.gam_model.assemble_model_design` builds an
  unpenalized intercept and then penalized ``cr``/``ti``/``sz`` terms; it has no
  route for parametric *columns*. The recipe therefore carries none. This is a
  real gap, and it blocks the **target formula** (whose parametric block is
  ``FaceSize + Smoke + FaceSize:Smoke``), not merely the dashboard — registered
  as rung **L4** of ``docs/MGCV_FEATURE_COVERAGE.md``.
* **No band.** Anchor W2 — the point estimate and the interval are wired in
  separate slices, never the same one.
* **Coefficients are never compared** (PLAN Anchor 2): ``mgcv``
  reparameterises, so ``coef`` is basis-dependent and ``eta`` is not.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_model import (
    PRODUCTION_LOG10_BOUNDS,
    PolarisGAMFit,
    fit_polaris_gam,
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
    "PRODUCTION_MI_CLAIM_SENTENCE",
    "PRODUCTION_MI_MODEL_CLAIM",
    "ProductionMICaseComparison",
    "RInternalFormComparison",
    "RProductionMIFit",
    "RProductionMIPayload",
    "RProductionMIRecipe",
    "compare_production_mi_case",
    "compare_r_internal_forms",
    "fit_production_mi_case",
    "production_mi_model_spec",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's committed ``eta`` half of the acceptance gate (``2e-2``),
**imported, not redeclared** — Anchor W5 forbids this epic introducing a new
tolerance or re-gating anything, and an imported constant cannot drift from the
one ADR-221 derived. See
:data:`~polaris_re.analytics.gam_select_free_sp_conformance._AGREEMENT_TOLERANCE_ETA`
for the derivation (headroom over a measured floor, never a number chosen to
make a reading pass)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's committed ``edf_total`` half of the acceptance gate (``1.0``),
imported for the same reason as :data:`_ETA_TOLERANCE`."""

_N_PENALTY_BLOCKS = 5
"""``s(attained_age)`` 1 + ``s(calendar_year)`` 1 + ``ti(age, year)`` 2
(ADR-205 decision 2: one per margin) + ``s(duration_years)`` 1. ``mgcv``'s own
``te()`` fit of the same span carries **3** (two tensor margins plus duration)
— that difference in penalty count *is* blocker A, made countable."""

_SPAN_RESIDUAL_TOLERANCE = 1.0e-9
"""How small a two-way projection residual counts as "the same column space"
(:attr:`RInternalFormComparison.max_span_residual`).

**Not a parity tolerance and not gated on** — it decides a STRUCTURAL question
(do these two designs span the same subspace?) whose honest answer is
0-or-not-0, so it needs only to sit far above floating-point noise and far below
anything meaningful.

**Measured floor** (a QR-based two-way projection over the 39-column design at
`n = 1260`, where the spans genuinely coincide): `6.88e-15` to `1.02e-14` on the
pinned digest across two runs, `2.95e-13` on local apt R. The figures differ by
an order of magnitude between BLAS implementations, which is exactly why the
bound is set well clear of both rather than snugly above either: `1e-9` is ~4
orders above the loosest observed floor and still ~7 orders below any difference
that would indicate a real basis mismatch.

Anchor W5 is untouched: this gates nothing ADR-221 gates, and the ``eta``/``edf``
bounds are imported (see :data:`_ETA_TOLERANCE`)."""

_AGE_LABEL = "s(attained_age)"
_YEAR_LABEL = "s(calendar_year)"
_TI_LABEL = "ti(attained_age,calendar_year)"
_DURATION_LABEL = "s(duration_years)"


class RProductionMIFit(TypedDict):
    """One of the two native ``mgcv`` fits the probe exports. Read by
    :func:`compare_production_mi_case` / :func:`compare_r_internal_forms` only —
    :func:`fit_production_mi_case` cannot see either of these through its
    narrower parameter type."""

    eta: list[float]
    coef: list[float]
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    n_coef: int
    converged: bool
    reml: float


class RProductionMIRecipe(TypedDict):
    """The shared-recipe fields of ``scripts/gam_production_mi_probe.R``'s
    output — everything needed to **pose** the regression problem and nothing
    that answers it.

    Structurally has no ``"te"`` or ``"anova"`` key, so the ADR-193 mechanical
    test is enforced by type rather than by discipline: the function producing
    the Polaris operand cannot reach ``mgcv``'s ``eta``/``coef``/``sp``/``edf``
    even if a caller hands it the wider :class:`RProductionMIPayload`."""

    n: int
    attained_age: list[float]
    calendar_year: list[float]
    duration_years: list[float]
    exposure: list[float]
    q_base: list[float]
    deaths: list[float]
    log_offset: list[float]
    age_knots: list[float]
    year_knots: list[float]
    duration_knots: list[float]
    age_k: int
    year_k: int
    duration_k: int


class RProductionMIPayload(RProductionMIRecipe):
    """The recipe plus ``mgcv``'s own free-``sp`` REML fits of **both** forms:
    :attr:`te` (a penalized full tensor) and :attr:`anova` (the four-term
    ANOVA-shaped HGAM this module's Polaris side builds). **Neither is the
    shipped dashboard's model**, which is unpenalized — ADR-227 amendment 1."""

    te: RProductionMIFit
    anova: RProductionMIFit
    offset_gap_te: float
    offset_gap_anova: float
    """The probe's own tripwire on how ``eta`` is defined, reported and never
    gated. ``mgcv``'s ``predict.gam(type="link")`` does **not** add back an
    offset supplied through ``gam()``'s ``offset=`` argument, while
    ``m$linear.predictors`` does — and
    :attr:`~polaris_re.analytics.gam_model.PolarisGAMFit.eta` is
    ``offset + X @ coef``, so ``m$linear.predictors`` is the like-for-like
    quantity. Using ``predict(type="link")`` instead made ``max_abs_eta_diff``
    read ``1.9751`` on this recipe against a ``2e-2`` bound — a spurious 99x
    "failure" that was entirely ``max(log(exposure * q_base))``. These fields
    are ``m$linear.predictors - (predict(type="link") + offset)`` and stay at
    machine epsilon while that behaviour holds. No earlier probe in this epic
    could hit the trap: the parity epic's target formula uses *weights* and no
    offset (PLAN Anchor 5's table), which is why the dashboard's own
    Poisson-offset form is where it first appears."""
    unpenalized: dict[str, float]
    """The fx=TRUE fits of both forms — **the decisive block**. The plan's
    blocker A asserts the dashboard fits te(...); it does not. It builds
    bs(age) + bs(year) + bs(age):bs(year) (the ANOVA shape) and fits it with
    an **unpenalized** sm.GLM. Since the two forms span the same space,
    removing the penalty must make them coincide — and it does, to ``8.88e-16``
    (tier 3) / ``2.14e-15`` (tier 1). So
    the whole penalized gap is an artefact of a penalty the shipped model does
    not have."""
    anova_spelling: dict[str, float]
    span_residual_anova_in_te: float
    span_residual_te_in_anova: float
    """Two-way projection residuals between the two designs' column spaces,
    computed in R from ``predict(m, type="lpmatrix")``. See
    :attr:`RInternalFormComparison.max_span_residual` — these are what
    establish "same span, different penalty", instead of inferring it from
    equal column counts, which would not establish it at all."""
    rank_te: int
    rank_anova: int
    rank_combined: int


PRODUCTION_MI_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam, multistart=True) "
    "assembles a four-term penalized ANOVA-shaped HGAM — s(attained_age) + "
    "s(calendar_year) + ti(attained_age, calendar_year) + s(duration_years), "
    "poisson(link='log') with offset(log(exposure*q_base)) — through "
    "assemble_model_design, from the shared recipe (covariates, exposure, "
    "q_base, deaths, the supplied knot vectors and k) via the "
    "already-independently-verified cr/ti basis producers, then selects all 5 "
    "log10(lambda) by minimizing gam_reml.reml_score_general via "
    "gam_reml_optimize.select_lambdas_continuous_multistart — never reading "
    "mgcv's own eta, coef, sp or edf. mgcv computes the same form natively via "
    "gam(family=poisson(link='log'), offset=log_offset, knots=<the same "
    "vectors>, method='REML') with free sp "
    "(scripts/gam_production_mi_probe.R). Compared on eta at the training "
    "design and edf_total, against ADR-221's committed criterion "
    "(max_abs_eta_diff < 2e-2 and abs(edf_total_diff) < 1.0). A SECOND axis "
    "compares the same Polaris fit against mgcv's own fit of a full tensor, "
    "te(attained_age, calendar_year) + s(duration_years) — a DIFFERENT "
    "penalized model (3 smoothing parameters against 5), NOT the shipped "
    "dashboard's form and NOT Anchor W6's target specification; it measures "
    "how far a penalized ANOVA decomposition sits from a penalized full "
    "tensor, nothing more. R-INTERNAL quantities (mgcv on BOTH sides, Polaris "
    "absent) are declared separately and are evidence about mgcv only. "
    "log10(sp) is NOT gated: ADR-221 moved the criterion off it, Anchor W5 "
    "forbids re-gating, and the two forms do not carry the same number of "
    "smoothing parameters so the comparison is undefined between them. "
    "Coefficients are never compared (PLAN Anchor 2)."
)
"""**Written before the code**, per ``docs/VERIFICATION_STANDARD.md`` §3.2, and
**AMENDED 2026-09-18** (PR #235 review [P0-2]).

The original sentence called this "the SHIPPED dashboard's own count-basis MI
model form" and called ``te()`` "the TARGET form … Anchor W6's own question".
**Both were false** — the dashboard fits an *unpenalized* patsy
``bs(age)+bs(year)+bs(age):bs(year)`` design, and the target specification is
the HGAM/BAM suite, not this form (ADR-227 amendment 1). That mattered beyond
the prose: :func:`~polaris_re.core.verification.evidence_markdown` prints this
sentence **verbatim** into the CI job summary, so every run was publishing a
premise the author no longer believed, in the same summary that elsewhere said
it was void. ``VERIFICATION_STANDARD.md`` §3.3 makes the derived headline
load-bearing precisely to prevent that.

Narrow in the three ways ADR-219 amendment 1's marketing constraint requires:
it names one structure (this four-term penalized HGAM, on this recipe), one
search configuration (``multistart=True`` — blocker D; the single-start reading
is recorded beside it and is not what the claim rests on), and states both
tolerances explicitly rather than leaving "agrees" undefined. **No unqualified
"mgcv parity" claim is made anywhere by this sentence**, and nothing here
touches conformance level 4's standing disagreement (ADR-190)."""


# The three mgcv-vs-mgcv quantities below carry ``REFERENCE_INTERNAL``: two real,
# genuinely independent producers, but BOTH of them are the reference and this
# engine is absent. They can disagree — the ``te`` vs ``s+s+ti`` localiser does,
# at 3.72e-02 — so they are real measurements, just not measurements OF US.
#
# PR #235 review round 2 [P1-4] is why this member exists. These rows shipped as
# ``INDEPENDENT`` (which ``VERIFICATION_STANDARD.md`` Sec. 5 prescribed at the
# time, and which was truthful about the producers), but ``is_parity_evidence``
# is True for INDEPENDENT, so ``evidence_markdown`` listed them under "Parity
# comparison" and printed "yes" against them — while their own labels said
# "Polaris absent". The headline overstated in the one line
# ``VERIFICATION_STANDARD.md`` Sec. 3.3 makes load-bearing. ADR-228.
#
# Consequence to expect, and it is correct: this claim's ``is_parity_claim`` is
# now False. Four columns are parity evidence for this engine and three are not,
# so the headline reads "Parity comparison, with reference-internal columns"
# rather than folding all seven into one verdict.
PRODUCTION_MI_MODEL_CLAIM = VerificationClaim(
    claim=PRODUCTION_MI_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="eta (Polaris s+s+ti vs mgcv s+s+ti)",
            left_producer=(
                "gam_model.fit_polaris_gam at its own multistart-selected log_lambda "
                "(5 blocks), design from assemble_model_design"
            ),
            right_producer=(
                "mgcv gam(s(attained_age)+s(calendar_year)+ti(attained_age,calendar_year)"
                "+s(duration_years), family=poisson(log), method='REML'), predict(type='link')"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (Polaris s+s+ti vs mgcv s+s+ti)",
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit of the same form",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="eta (Polaris s+s+ti vs mgcv te — a penalized full tensor, NOT the target)",
            left_producer=(
                "gam_model.fit_polaris_gam at its own multistart-selected log_lambda "
                "(5 blocks), design from assemble_model_design"
            ),
            right_producer=(
                "mgcv gam(te(attained_age,calendar_year,bs='cr')+s(duration_years), "
                "family=poisson(log), method='REML'), predict(type='link')"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity=(
                "edf_total (Polaris s+s+ti vs mgcv te — a penalized full tensor, NOT the target)"
            ),
            left_producer="PolarisGAMFit.edf_total at the selected log_lambda",
            right_producer="mgcv's own sum(m$edf) at its free-sp REML fit of the te() form",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="eta / edf_total (mgcv te vs mgcv s+s+ti — the R-internal localiser)",
            left_producer="mgcv gam(te(...)+s(duration_years), method='REML')",
            right_producer="mgcv gam(s(...)+s(...)+ti(...)+s(duration_years), method='REML')",
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
        ComparedQuantity(
            quantity=(
                "eta / edf_total UNPENALIZED (mgcv te fx=TRUE vs mgcv s+s+ti fx=TRUE) "
                "— R-INTERNAL, Polaris absent"
            ),
            left_producer="mgcv gam(te(..., fx=TRUE)+s(..., fx=TRUE), method='REML')",
            right_producer=(
                "mgcv gam(s(...,fx=TRUE)+s(...,fx=TRUE)+ti(...,fx=TRUE)+s(...,fx=TRUE), "
                "method='REML')"
            ),
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
        ComparedQuantity(
            quantity=(
                "eta / edf_total SPELLING (mgcv s+s+ti vs mgcv ti+ti+ti) "
                "— R-INTERNAL, Polaris absent"
            ),
            left_producer="mgcv gam(s(...)+s(...)+ti(...)+s(...), method='REML')",
            right_producer="mgcv gam(ti(...)+ti(...)+ti(...)+s(...), method='REML')",
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
    ),
)
"""PLAN slice 1's provenance declaration (ADR-193).

**Every quantity is INDEPENDENT, and this slice genuinely is a two-producer
comparison** — unlike the several slices before it, which were correctly
classed ``MEASUREMENT (own criterion)`` because no second producer's value sat
opposite ours. Here Polaris's own fit sits opposite ``mgcv``'s own fit of the
same recipe. The ADR-193 mechanical test applied to the producing function's
signature: :func:`fit_production_mi_case` takes :class:`RProductionMIRecipe`,
which structurally has no ``te``/``anova`` key, so it cannot read either of
``mgcv``'s fits — a caller passing the wider :class:`RProductionMIPayload`
still cannot make it see them.

**The last THREE quantities are INDEPENDENT but say nothing about Polaris.**
Both producers are ``mgcv`` in each; they are evidence about ``mgcv``'s own
formula forms, the same class ``docs/VERIFICATION_STANDARD.md`` §5 already
records for the R-side ``smoothCon``/``lpmatrix`` guard. They must never be
read as parity evidence for this engine.

**The ``UNPENALIZED`` row was added 2026-09-18 (PR #235 review [P1-1]) and it
carries the whole retraction.** Its ``8.88e-16`` is the measurement that voided
blocker A, and it is published in the PR body, ADR-227 amendment 1, the ledger
row, the CI job summary and ``MGCV_NOTATION_PRIMER.md`` — but it shipped with
no declared ``VerificationClaim``, which ``VERIFICATION_STANDARD.md`` §4.4
makes a [P1]. The risk is concrete rather than procedural: a
machine-precision zero published under a table headed only ``| regime |``
reads at a glance as *Polaris* agreeing with ``mgcv``, when Polaris appears
nowhere in it. The ``SPELLING`` row (``1.11e-15``) had the same gap."""


def production_mi_model_spec(
    age_knots: tuple[float, ...],
    year_knots: tuple[float, ...],
    duration_knots: tuple[float, ...],
) -> ModelSpec:
    """The dashboard's MI form as a ``ModelSpec``, re-expressed for the bases
    :func:`~polaris_re.analytics.gam_model.assemble_model_design` can build.

    ``te(attained_age, calendar_year)`` becomes ``s(attained_age) +
    s(calendar_year) + ti(attained_age, calendar_year)`` — branch (a) of PLAN
    slice 1's own "the ``te`` decision is the substance", chosen over branch (b)
    (build a ``te`` basis producer) because it is what this slice exists to
    *test*: the cheap branch is only cheap if the equivalence holds, and
    measuring whether it holds is strictly prior to spending solver work on
    either branch.

    ``k`` is derived from the page's own widget defaults, not chosen (PLAN
    Anchor 4). The dashboard's margins are patsy ``bs(col, df=D)`` — ``D``
    columns, no intercept — while ``s(x, bs="cr", k=K)`` carries ``K - 1``
    columns after the sum-to-zero constraint, so ``K = D + 1`` reproduces the
    shipped margin width exactly: ``age_df=6 -> k=7``, ``year_df=4 -> k=5``,
    ``duration_df=4 -> k=5``, and the tensor block totals agree cell for cell
    (``6 + 4 + 24 = 34 == 7*5 - 1``). The caller passes the knot vectors, whose
    lengths carry ``k``.

    Family/link is ``poisson``/``log`` with an ``offset`` and **no weights** —
    ``TensorMIModel``'s own count-basis idiom (PLAN Anchor 5: weights and
    offset are orthogonal, neither inferred from the other). ``select`` stays
    ``False``: the shipped form has no ``select = TRUE``, and adding one would
    measure a different model.
    """
    age_term = TermSpec(
        label=_AGE_LABEL,
        variables=("attained_age",),
        basis="cr",
        k=(len(age_knots),),
        knots=(("attained_age", age_knots),),
    )
    year_term = TermSpec(
        label=_YEAR_LABEL,
        variables=("calendar_year",),
        basis="cr",
        k=(len(year_knots),),
        knots=(("calendar_year", year_knots),),
    )
    ti_term = TermSpec(
        label=_TI_LABEL,
        variables=("attained_age", "calendar_year"),
        basis="ti",
        k=(len(age_knots), len(year_knots)),
        knots=(("attained_age", age_knots), ("calendar_year", year_knots)),
    )
    duration_term = TermSpec(
        label=_DURATION_LABEL,
        variables=("duration_years",),
        basis="cr",
        k=(len(duration_knots),),
        knots=(("duration_years", duration_knots),),
    )
    return ModelSpec(
        family="poisson",
        link="log",
        terms=(age_term, year_term, ti_term, duration_term),
        offset_column="log_offset",
    )


def fit_production_mi_case(
    r_case: RProductionMIRecipe,
    *,
    multistart: bool = True,
    n_starts: int = 9,
    analytic_gradient: bool = False,
) -> PolarisGAMFit:
    """The independent Python producer: assemble the re-expressed design from
    the shared recipe, select its own 5 lambdas, and fit.

    Never reads ``mgcv``'s ``eta``/``coef``/``sp``/``edf``
    (:class:`RProductionMIRecipe` has no such key — the ADR-193 mechanical test
    enforced structurally by the parameter type, the same discipline
    :func:`~polaris_re.analytics.gam_select_free_sp_conformance.fit_select_free_sp_case`
    uses).

    Args:
        r_case: the shared recipe.
        multistart: **defaults to ``True`` here**, unlike
            :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`'s own
            default — blocker D (PLAN ``docs/PLAN_gam_production_wiring.md``):
            a plain single-start call is the configuration that *fails*
            ADR-221's gate, and ADR-226 measured ``multistart(9)`` as the only
            configuration to pass both reproducibility axes. Any wiring must
            pin it explicitly, so this module pins it rather than inheriting a
            default that would be wrong for production. The single-start
            reading is still obtainable (``multistart=False``) and PLAN slice
            1's DoD requires it to be recorded beside the pinned one, so the
            gap stays visible.
        n_starts: passed through when ``multistart=True`` (ADR-213's best-of-9,
            the count ADR-226 measured).
        analytic_gradient: passed through (PLAN parity slice 7d). Default
            ``False``.

    Raises:
        PolarisValidationError: if the assembled design does not carry the
            :data:`_N_PENALTY_BLOCKS` penalty blocks this form implies — a
            guard against a silent change in how ``ti`` contributes penalties
            (ADR-205 decision 2) going unnoticed as an agreement.
    """
    age_knots = tuple(float(v) for v in r_case["age_knots"])
    year_knots = tuple(float(v) for v in r_case["year_knots"])
    duration_knots = tuple(float(v) for v in r_case["duration_knots"])
    model = production_mi_model_spec(age_knots, year_knots, duration_knots)
    data = {
        "attained_age": np.asarray(r_case["attained_age"], dtype=np.float64),
        "calendar_year": np.asarray(r_case["calendar_year"], dtype=np.float64),
        "duration_years": np.asarray(r_case["duration_years"], dtype=np.float64),
        "log_offset": np.asarray(r_case["log_offset"], dtype=np.float64),
    }
    y = np.asarray(r_case["deaths"], dtype=np.float64)
    fit = fit_polaris_gam(
        model,
        data,
        y,
        bounds=PRODUCTION_LOG10_BOUNDS,
        multistart=multistart,
        n_starts=n_starts,
        analytic_gradient=analytic_gradient,
    )
    if len(fit.design["penalty_blocks"]) != _N_PENALTY_BLOCKS:
        raise PolarisValidationError(
            f"fit_production_mi_case: assembled {len(fit.design['penalty_blocks'])} "
            f"penalty block(s), expected {_N_PENALTY_BLOCKS} "
            "(s(attained_age) 1 + s(calendar_year) 1 + ti(...) 2 + s(duration_years) 1)."
        )
    return fit


@dataclass(frozen=True)
class ProductionMICaseComparison:
    """One Polaris-vs-``mgcv`` reading on the dashboard's MI form.

    ``agrees`` is ADR-221's committed criterion, reused verbatim and not
    re-derived (Anchor W5): ``converged and max_abs_eta_diff < eta_tolerance
    and abs(edf_total_diff) < edf_tolerance``. There is deliberately **no**
    ``log10(sp)`` verdict here — see the module docstring."""

    target: str
    """Which ``mgcv`` fit this reading is against: ``"anova"`` (the same
    four-term ANOVA-shaped HGAM, so the comparison is about our engine) or
    ``"te"`` (a penalized full tensor — a DIFFERENT model, neither the
    dashboard's form nor Anchor W6's target spec; see the module docstring)."""
    max_abs_eta_diff: float
    edf_total_diff: float
    n_sp_python: int
    n_sp_mgcv: int
    """Reported, never gated, and never differenced: ``te`` carries 3 smoothing
    parameters where the re-expression carries 5, which is blocker A made
    countable rather than a quantity to compare."""
    at_bound: bool
    converged: bool
    agrees: bool
    eta_tolerance: float
    edf_tolerance: float
    evidence: VerificationClaim


def _fit_payload(r_case: RProductionMIPayload, target: str) -> RProductionMIFit:
    if target not in {"te", "anova"}:
        raise PolarisValidationError(
            f"compare_production_mi_case: target={target!r}; expected 'te' (the "
            "dashboard's own form) or 'anova' (the s+s+ti re-expression)."
        )
    return r_case["te"] if target == "te" else r_case["anova"]


def compare_production_mi_case(
    python_fit: PolarisGAMFit,
    r_case: RProductionMIPayload,
    *,
    target: str,
    eta_tolerance: float = _ETA_TOLERANCE,
    edf_tolerance: float = _EDF_TOLERANCE,
) -> ProductionMICaseComparison:
    """Compare the independent Python fit against one of the two native
    ``mgcv`` fits, on ADR-221's committed ``eta``/``edf`` criterion.

    Args:
        python_fit: the independent Polaris producer's result, from
            :func:`fit_production_mi_case`.
        r_case: the full payload (recipe **and** both ``mgcv`` fits).
        target: ``"anova"`` — against ``mgcv``'s own fit of the same four-term
            ANOVA-shaped HGAM, which asks whether our engine reproduces it;
            or ``"te"`` — against ``mgcv``'s own fit of a penalized full
            tensor, a DIFFERENT model that is neither the dashboard's form nor
            Anchor W6's target specification (ADR-227 amendment 1).
        eta_tolerance, edf_tolerance: ADR-221's committed bounds. Exposed as
            parameters the same way
            :func:`~polaris_re.analytics.gam_select_free_sp_conformance.compare_select_free_sp_case`
            exposes its own — so a reader of one result can audit what bar it
            was measured against — and defaulted to the *imported* ADR-221
            constants so nothing here can widen them (Anchor W5).
    """
    fit = _fit_payload(r_case, target)
    r_eta = np.asarray(fit["eta"], dtype=np.float64)
    py_eta = np.asarray(python_fit.eta, dtype=np.float64)
    if r_eta.shape != py_eta.shape:
        raise PolarisValidationError(
            f"compare_production_mi_case: mgcv's {target!r} eta has shape "
            f"{r_eta.shape} but the Polaris fit's has {py_eta.shape} — the two "
            "sides were not posed on the same recipe."
        )
    max_abs_eta_diff = float(np.max(np.abs(py_eta - r_eta)))
    edf_total_diff = float(python_fit.edf_total - float(fit["edf_total"]))
    converged = bool(python_fit.converged)
    agrees = converged and max_abs_eta_diff < eta_tolerance and abs(edf_total_diff) < edf_tolerance
    return ProductionMICaseComparison(
        target=target,
        max_abs_eta_diff=max_abs_eta_diff,
        edf_total_diff=edf_total_diff,
        n_sp_python=len(python_fit.log_lambda),
        n_sp_mgcv=len(fit["sp"]),
        at_bound=bool(python_fit.at_bound),
        converged=converged,
        agrees=agrees,
        eta_tolerance=eta_tolerance,
        edf_tolerance=edf_tolerance,
        evidence=PRODUCTION_MI_MODEL_CLAIM,
    )


@dataclass(frozen=True)
class RInternalFormComparison:
    """``mgcv``'s own ``te()`` against ``mgcv``'s own ``s()+s()+ti()``, on the
    same recipe, the same knots, the same family and the same ``method="REML"``.

    **This is the blocker-A localiser, and it says nothing about Polaris.**
    Both producers are ``mgcv``; Polaris appears nowhere in it. Its whole value
    is that it isolates the *re-expression* from the *engine*: if the two forms
    already disagree here by more than ADR-221's bound, then no Polaris fit of
    the re-expression can agree with the target form, however correct the
    engine is."""

    max_abs_eta_diff: float
    edf_total_diff: float
    n_sp_te: int
    n_sp_anova: int
    n_coef_te: int
    n_coef_anova: int
    max_span_residual: float
    """The worst two-way projection residual between the two designs' column
    spaces: ``max`` over ``|X_anova - proj_{col(X_te)} X_anova|`` and
    ``|X_te - proj_{col(X_anova)} X_te|``, computed in R by the probe.

    **Equal column counts do NOT establish equal span** — two 39-column bases
    can span different 39-dimensional subspaces — so the earlier version of this
    dataclass, which inferred ``spans_match`` from the counts alone, was
    asserting more than it had measured. Mutual containment to machine precision
    is what actually licenses "same span, DIFFERENT penalty", and it is what
    makes the ``eta`` difference attributable to the PENALTY rather than to the
    basis (PLAN slice 1's registered prediction's own fallback)."""
    rank_te: int
    rank_anova: int
    rank_combined: int
    """``rank([X_te X_anova])``. Equal to both individual ranks iff neither
    design adds a direction the other lacks — the same fact
    :attr:`max_span_residual` establishes, by an independent route, so a
    disagreement between the two readings is itself informative."""
    spans_match: bool
    """**Measured, not inferred from column counts.** True iff the two-way
    projection residual is at machine precision AND the three ranks agree."""
    equivalent_within_adr221: bool
    """Whether the two ``mgcv`` fits agree with each other under ADR-221's own
    committed criterion. **False means the ``te == s+s+ti`` hypothesis is
    refuted on this recipe**, as a property of ``mgcv``, before Polaris is
    considered at all."""
    eta_tolerance: float
    edf_tolerance: float


def compare_r_internal_forms(
    r_case: RProductionMIPayload,
    *,
    eta_tolerance: float = _ETA_TOLERANCE,
    edf_tolerance: float = _EDF_TOLERANCE,
) -> RInternalFormComparison:
    """Read ``mgcv``'s own two fits against each other — the (3) axis of the
    module docstring's table.

    Applies the **same** ADR-221 bounds the Polaris comparisons are gated on,
    deliberately: the question is whether the re-expression reproduces the
    target *to the standard this project has committed to*, not to some looser
    standard invented for the occasion (Anchor W5)."""
    te_eta = np.asarray(r_case["te"]["eta"], dtype=np.float64)
    anova_eta = np.asarray(r_case["anova"]["eta"], dtype=np.float64)
    if te_eta.shape != anova_eta.shape:
        raise PolarisValidationError(
            "compare_r_internal_forms: the two mgcv fits have different eta "
            f"shapes ({te_eta.shape} vs {anova_eta.shape}) — they were not "
            "fitted on the same recipe."
        )
    max_abs_eta_diff = float(np.max(np.abs(anova_eta - te_eta)))
    edf_total_diff = float(r_case["anova"]["edf_total"] - r_case["te"]["edf_total"])
    n_coef_te = int(r_case["te"]["n_coef"])
    n_coef_anova = int(r_case["anova"]["n_coef"])
    max_span_residual = max(
        float(r_case["span_residual_anova_in_te"]),
        float(r_case["span_residual_te_in_anova"]),
    )
    rank_te = int(r_case["rank_te"])
    rank_anova = int(r_case["rank_anova"])
    rank_combined = int(r_case["rank_combined"])
    return RInternalFormComparison(
        max_abs_eta_diff=max_abs_eta_diff,
        edf_total_diff=edf_total_diff,
        n_sp_te=len(r_case["te"]["sp"]),
        n_sp_anova=len(r_case["anova"]["sp"]),
        n_coef_te=n_coef_te,
        n_coef_anova=n_coef_anova,
        max_span_residual=max_span_residual,
        rank_te=rank_te,
        rank_anova=rank_anova,
        rank_combined=rank_combined,
        spans_match=(
            max_span_residual < _SPAN_RESIDUAL_TOLERANCE and rank_te == rank_anova == rank_combined
        ),
        equivalent_within_adr221=(
            max_abs_eta_diff < eta_tolerance and abs(edf_total_diff) < edf_tolerance
        ),
        eta_tolerance=eta_tolerance,
        edf_tolerance=edf_tolerance,
    )

"""Stage-C REML-score conformance — mgcv-parity engine, slice 4 part A.

``docs/PLAN_mgcv_parity_engine.md`` slice 4: before any outer smoothing-parameter
optimiser can be built, the criterion it would search over has to itself agree
with ``mgcv``'s, for the target formula's own family (binomial) and for more
than the tensor MI surface's fixed two penalty blocks. ``scripts/gam_reml_probe.R``
builds a SHARED ``(X, S1, S2, y, weights)`` recipe — two independently-scaled
penalty blocks on one binomial/logit design — and fits it at three FIXED
``(sp1, sp2)`` points via ``paraPen`` with ``method="REML"``, so ``m$gcv.ubre``
reports the REML criterion at that fixed point (no optimisation runs — the full
``sp`` vector is supplied).

This module reads back **only the recipe fields** (``X``, ``S1``, ``S2``, ``y``,
``weights``, and the ``sp`` points themselves — a shared setting, not a computed
quantity) and fits + scores independently via
:func:`polaris_re.analytics.gam_fit.penalized_irls_general` and
:func:`polaris_re.analytics.gam_reml.reml_score_general` — never the R script's
own ``gcv_ubre`` — which is what makes the comparison INDEPENDENT (ADR-193's
mechanical test).

**Why the comparison is on score DIFFERENCES, not the absolute value.**
ADR-189 amendment 1 already measured, for the already-verified Poisson case,
that the raw REML score carries a convention offset against ``mgcv``'s own
(``≈ -l_sat/gamma``, the saturated log-likelihood) plus a further residual of
0.93-3.17 that amendment explicitly left "unexplained" and marked "not a
compared metric." Re-litigating that residual is not this module's job. What
actually matters for an optimiser is the criterion's SHAPE in lambda —
``score(point A) - score(point B)`` — which cancels any purely additive offset
regardless of its source. Comparing differences is therefore both the honest
sidestep of an already-open question and the quantity an optimiser would
actually use.
"""

from itertools import combinations
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import binomial_logit
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "REML_SCORE_CLAIM",
    "RReplPayload",
    "RReplPoint",
    "RReplRecipe",
    "ReplDevianceComparison",
    "ReplPointComparison",
    "compare_reml_deviance",
    "compare_reml_points",
    "deviance_reml_point",
    "score_reml_point",
]


_AGREEMENT_TOLERANCE = 1e-6
"""Deliberately tight — score DIFFERENCES at fixed sp are, if the formula is
right, an exact function of the shared recipe with no fitting noise beyond
IRLS convergence (the same regime slice 3's `eta` comparison earned 1e-9 in).
Not loosened to make a disagreement pass (CLAUDE.md, Anchor 8): if this
tolerance is missed, that is the finding, not a reason to widen it. Applied to
BOTH `reml_score_pairwise_diff` and `deviance` — PR #203 review [P1-2]: an
earlier revision of this module's callers described results as "2 of 3 pairs
disagree" while every published table showed `agrees=False` on all three
against this exact tolerance (the third pair's residual, ~9.3e-4, is ~935x
this tolerance — small relative to the other two, not passing). Never
describe a result more favourably than this constant actually evaluates."""


def _independent_fit(
    x: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    sp: tuple[float, float],
) -> GeneralIRLSFit:
    """The one independent fit both :func:`score_reml_point` and
    :func:`deviance_reml_point` are built on — takes plain arrays and the
    ``sp`` setting itself, never a dict shaped like the R payload (PR #203
    review [P1-1]: `deviance` needs the SAME independent fit `score_reml_point`
    already produces, not a second, differently-sourced one)."""
    sp1, sp2 = sp
    penalty = sp1 * s1 + sp2 * s2
    family = binomial_logit()
    return penalized_irls_general(x, y, family=family, penalty=penalty, weights=weights)


class RReplPoint(TypedDict):
    """One fixed-``sp`` point from ``scripts/gam_reml_probe.R``'s ``points``
    array — the recipe half only (``sp``), never ``gcv_ubre``, so
    :func:`score_reml_point`'s signature cannot read the R side's own score
    (ADR-193's mechanical test, same shape as ``gam_family_conformance``'s
    ``RFamilyCaseRecipe``/``RFamilyCasePayload`` split)."""

    sp: list[float]


class RReplPointPayload(RReplPoint):
    """:class:`RReplPoint` plus the R script's own fit at that point. Read only
    by :func:`compare_reml_points`."""

    gcv_ubre: float
    edf_total: float
    deviance: float
    converged: bool


class RReplRecipe(TypedDict):
    """The shared-recipe fields of the whole probe — everything both sides
    need to pose the SAME regression problem at every point. ``points`` here
    carries only :class:`RReplPoint` (``sp``, never ``gcv_ubre``), so
    :func:`score_reml_point`'s parameter type structurally has no score field
    to read — the ADR-193 mechanical test enforced by the type, not just the
    function body (PR #202 review [P1]'s fix, applied here from the start)."""

    X: list[list[float]]
    S1: list[list[float]]
    S2: list[list[float]]
    y: list[float]
    weights: list[float]
    points: list[RReplPoint]


class RReplPayload(TypedDict):
    """Same shared fields as :class:`RReplRecipe`, but with each point's own
    R fit attached (:class:`RReplPointPayload` rather than
    :class:`RReplPoint`). A fresh ``TypedDict`` rather than a subclass of
    :class:`RReplRecipe`, because ``list`` is invariant and a subclass cannot
    soundly widen ``points``'s element type. Read only by
    :func:`compare_reml_points`, never by :func:`score_reml_point`."""

    X: list[list[float]]
    S1: list[list[float]]
    S2: list[list[float]]
    y: list[float]
    weights: list[float]
    points: list[RReplPointPayload]


REML_SCORE_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_reml.reml_score_general computes the REML "
        "criterion from the shared design, two independently-scaled penalty "
        "blocks, response and weights, evaluated at coefficients fitted "
        "independently via gam_fit.penalized_irls_general; mgcv computes the "
        "same criterion via gam(family=binomial(link='logit'), weights=..., "
        "paraPen=list(X=list(S1, S2, sp=c(sp1, sp2))), method='REML')$gcv.ubre "
        "at the SAME fixed sp point; compared on the PAIRWISE DIFFERENCE of "
        "the score between two sp points, not the absolute value (see the "
        "module docstring for why the absolute value is not compared)."
    ),
    quantities=(
        ComparedQuantity(
            quantity="reml_score_pairwise_diff",
            left_producer=(
                "gam_reml.reml_score_general on an independently-converged "
                "gam_fit.penalized_irls_general fit"
            ),
            right_producer="mgcv gam(..., method='REML')$gcv.ubre at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="deviance",
            left_producer=(
                "gam_family.Family.deviance on the SAME independently-converged "
                "gam_fit.penalized_irls_general fit score_reml_point uses"
            ),
            right_producer="mgcv m$deviance at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 4 part A's provenance declaration (ADR-193). INDEPENDENT: neither side
reads the other's fit or score, only the shared recipe (``X``, ``S1``, ``S2``,
``y``, ``weights``, and the ``sp`` points, which are a shared SETTING both
sides fit at, not a quantity either side computed). `deviance` (PR #203 review
[P1-1]) is what rules out the most plausible harness artifact — that `mgcv`
rescaled the supplied penalty blocks (`gam.control`'s `scalePenalty`), which
would make both sides fit at a different effective lambda and turn the whole
comparison into an artifact. Declaring and printing it, rather than citing it
only in prose, is what makes that rebuttal auditable."""


def score_reml_point(
    x: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    sp: tuple[float, float],
) -> float:
    """The independent Python producer for one probe point's REML score.

    Takes plain arrays and the ``sp`` setting itself — never a dict shaped
    like the R payload, so there is structurally nothing here that could read
    ``gcv_ubre`` even by accident (a stronger form of ADR-193's mechanical
    test than typing a narrowed recipe dict: this function does not accept
    any R-payload-shaped argument at all).
    """
    fit = _independent_fit(x, s1, s2, y, weights, sp)
    return reml_score_general(
        y, x, binomial_logit(), fit.coef, (s1, s2), np.asarray(sp), weights=weights
    )


def deviance_reml_point(
    x: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    sp: tuple[float, float],
) -> float:
    """The independent Python producer for one probe point's deviance.

    Same signature shape as :func:`score_reml_point` (no R-payload-shaped
    argument) and the SAME independent fit (:func:`_independent_fit`) — the
    fit that licenses "the fit itself is correct" is not a second,
    differently-sourced computation from the one the score is built on
    (PR #203 review [P1-1]).
    """
    fit = _independent_fit(x, s1, s2, y, weights, sp)
    mu = binomial_logit().link.linkinv(fit.eta)
    return binomial_logit().deviance(y, mu, weights)


class ReplDevianceComparison(TypedDict):
    sp: tuple[float, float]
    python_deviance: float
    r_deviance: float
    diff: float
    agrees: bool


def compare_reml_deviance(
    x: np.ndarray, s1: np.ndarray, s2: np.ndarray, r_payload: RReplPayload
) -> tuple[ReplDevianceComparison, ...]:
    """The deviance at every probe point, Python vs mgcv — per point, not
    pairwise (unlike the score, deviance carries no additive convention
    offset to cancel, so the absolute value is the right comparison).

    This is what licenses "the fit itself is correct" wherever ADR-196 and
    the session log say it: before this function existed, that claim came
    from an ad-hoc session measurement with no committed producer (PR #203
    review [P1-1]). It is what rules out the most plausible harness
    artifact — `mgcv` rescaling the supplied penalty blocks, which would fit
    both sides at a different effective lambda and make the whole score
    comparison uninterpretable.
    """
    y = np.asarray(r_payload["y"], dtype=np.float64)
    weights = np.asarray(r_payload["weights"], dtype=np.float64)
    out: list[ReplDevianceComparison] = []
    for p in r_payload["points"]:
        sp = (p["sp"][0], p["sp"][1])
        python_deviance = deviance_reml_point(x, s1, s2, y, weights, sp)
        r_deviance = float(p["deviance"])
        diff = python_deviance - r_deviance
        out.append(
            ReplDevianceComparison(
                sp=sp,
                python_deviance=python_deviance,
                r_deviance=r_deviance,
                diff=diff,
                agrees=abs(diff) < _AGREEMENT_TOLERANCE,
            )
        )
    return tuple(out)


class ReplPointComparison(TypedDict):
    point_a: tuple[float, float]
    point_b: tuple[float, float]
    python_diff: float
    r_diff: float
    residual: float
    agrees: bool


def compare_reml_points(
    x: np.ndarray, s1: np.ndarray, s2: np.ndarray, r_payload: RReplPayload
) -> tuple[ReplPointComparison, ...]:
    """Every pairwise score difference among the probe's points, Python vs mgcv.

    ``r_payload`` here is the full payload (recipe + each point's own
    ``gcv_ubre``) — read by this function only, which is what makes it the
    comparison side rather than the independent producer (see
    :func:`score_reml_point`, which is typed to see only the recipe).
    """
    y = np.asarray(r_payload["y"], dtype=np.float64)
    weights = np.asarray(r_payload["weights"], dtype=np.float64)
    points: list[tuple[float, float]] = [(p["sp"][0], p["sp"][1]) for p in r_payload["points"]]
    n_points = len(points)
    python_scores = [score_reml_point(x, s1, s2, y, weights, sp) for sp in points]
    r_scores = [float(p["gcv_ubre"]) for p in r_payload["points"]]

    out: list[ReplPointComparison] = []
    for i, j in combinations(range(n_points), 2):
        python_diff = python_scores[i] - python_scores[j]
        r_diff = r_scores[i] - r_scores[j]
        residual = python_diff - r_diff
        out.append(
            ReplPointComparison(
                point_a=points[i],
                point_b=points[j],
                python_diff=python_diff,
                r_diff=r_diff,
                residual=residual,
                agrees=abs(residual) < _AGREEMENT_TOLERANCE,
            )
        )
    return tuple(out)

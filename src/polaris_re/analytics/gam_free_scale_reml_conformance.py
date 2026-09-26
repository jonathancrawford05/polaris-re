"""Stage-C REML-score conformance for FREE-scale families — capability ladder
rung **L5** (``docs/PLAN_mgcv_capability_ladder.md`` slice 3).

``gam_reml_conformance.py`` measured the KNOWN-scale criterion
(``dispersion_fixed=True`` — binomial, Poisson) against ``mgcv``'s own
``m$gcv.ubre`` and found a convention offset it explicitly declined to
compare on (score DIFFERENCES only, ADR-196). This module is the same shape
for the branch :func:`~polaris_re.analytics.gam_reml.reml_score_general`
added for a **FREE**-scale family (``dispersion_fixed=False`` — Gaussian,
quasi-Poisson): ``scripts/gam_free_scale_reml_score_probe.R`` builds ONE
shared two-block design and fits it under BOTH families at three fixed
``(sp1, sp2)`` points via ``paraPen``, ``method="REML"``, so ``m$gcv.ubre``
reports the free-scale REML criterion at that exact point (no optimisation
runs — the full ``sp`` vector is supplied).

**Why Gaussian is compared on the ABSOLUTE score, not only pairwise
differences.** The free-scale formula (module docstring,
:mod:`~polaris_re.analytics.gam_reml`, "PLAN slice 3 (ladder), L5") was
derived by differentiating Wood (2011) §2 eq. (4) w.r.t. the unknown scale
and substituting the resulting ``phi_hat`` back in — including every additive
constant, not just the ``lambda``-dependent shape. Measured directly against
``mgcv`` (a standalone R check, not this module) BEFORE this module existed:
the formula reproduces ``m$gcv.ubre`` for Gaussian to float round-trip
precision (~1e-13), absolute value, across an unpenalized case and a
penalized one at four widely-spread fixed ``sp``. So Gaussian's claim here is
the STRONGER one: the absolute score, not merely its shape.

**Why quasi-Poisson is compared on pairwise differences only, the SAME
convention `gam_reml_conformance.py` already uses for the known-scale
binomial case.** Quasi-likelihood has no proper saturated log-likelihood —
its own ``a(y, phi)`` normalizing term is not uniquely defined by the
quasi-score equations alone — so ``ls(phi)`` in Wood's eq. (4) is not the
same well-defined quantity for quasi-Poisson that it is for a genuine
exponential family. Measured (this module's own R probe): quasi-Poisson
carries a small, nearly-``lambda``-independent additive residual against
``m$gcv.ubre`` (order ~1e0-1e2, stable to roughly 1 part in ``1e5`` across the
three ``sp`` points) — exactly the shape of finding ADR-196 already accepted
for the known-scale Poisson criterion's own convention offset ("what matters
for an optimiser is the criterion's SHAPE ... cancels any purely additive
offset regardless of source"). This module therefore compares quasi-Poisson
on PAIRWISE DIFFERENCES only, never claims absolute agreement for it, and
that asymmetry is declared per-family in the claim below rather than averaged
into one verdict.

Neither family's SCORE comparison is this rung's acceptance criterion —
ADR-221's ``eta``/``edf_total`` gate on the actual free-``sp`` FIT is
(``gam_gaussian_conformance.GAUSSIAN_FREE_SP_CLAIM``). This module exists
because Anchor 1's own discipline says a search should not be built on a
criterion that has not itself been measured against ``mgcv`` first.
"""

from itertools import combinations
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import Family, gaussian_identity, quasipoisson_log
from polaris_re.analytics.gam_fit import GeneralIRLSFit, penalized_irls_general
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "FREE_SCALE_REML_SCORE_CLAIM",
    "FreeScaleAbsoluteComparison",
    "FreeScalePairwiseComparison",
    "RFreeScaleReplPayload",
    "RFreeScaleReplPoint",
    "RFreeScaleReplRecipe",
    "compare_free_scale_absolute",
    "compare_free_scale_pairwise",
    "score_free_scale_point",
]

_PAIRWISE_TOLERANCE = 1e-6
"""Same tight bound as ``gam_reml_conformance._AGREEMENT_TOLERANCE`` and for
the same reason: a score DIFFERENCE at fixed ``sp`` is, if the formula is
right, an exact function of the shared recipe with no fitting noise beyond
IRLS convergence."""

_GAUSSIAN_ABSOLUTE_TOLERANCE = 1e-6
"""For Gaussian ONLY (see module docstring) — the ABSOLUTE score, not a
difference, is compared to this bound. Not derived from a measured floor the
way ADR-221's ``eta`` tolerance is; it is the same order as
``gam_reml_conformance``'s own tight bound, appropriate for a quantity that is
(per the standalone R check the module docstring cites) an exact function of
the recipe to float round-trip precision."""


def _independent_fit(
    x: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    y: np.ndarray,
    family: Family,
    sp: tuple[float, float],
) -> GeneralIRLSFit:
    """The one independent fit both comparison functions are built on — takes
    plain arrays and the ``sp`` setting itself, never a dict shaped like the R
    payload."""
    sp1, sp2 = sp
    penalty = sp1 * s1 + sp2 * s2
    return penalized_irls_general(x, y, family=family, penalty=penalty)


class RFreeScaleReplPoint(TypedDict):
    """One fixed-``sp`` point — the recipe half only (``sp``), never
    ``gcv_ubre``, so :func:`score_free_scale_point`'s signature cannot read
    the R side's own score."""

    sp: list[float]


class RFreeScaleReplPointPayload(RFreeScaleReplPoint):
    """:class:`RFreeScaleReplPoint` plus the R script's own fit at that
    point. Read only by the ``compare_*`` functions."""

    gcv_ubre: float
    edf_total: float
    deviance: float
    scale: float
    converged: bool


class RFreeScaleReplRecipe(TypedDict):
    """The shared-recipe fields both sides fit — no ``gcv_ubre`` anywhere, so
    :func:`score_free_scale_point` cannot read either family's R score even
    if handed the wider payload."""

    X: list[list[float]]
    S1: list[list[float]]
    S2: list[list[float]]
    y_gaussian: list[float]
    y_quasipoisson: list[float]
    points_gaussian: list[RFreeScaleReplPoint]
    points_quasipoisson: list[RFreeScaleReplPoint]


class RFreeScaleReplPayload(TypedDict):
    """Same shared fields as :class:`RFreeScaleReplRecipe`, but with each
    point's own R fit attached. Read only by the ``compare_*`` functions,
    never by :func:`score_free_scale_point`."""

    X: list[list[float]]
    S1: list[list[float]]
    S2: list[list[float]]
    y_gaussian: list[float]
    y_quasipoisson: list[float]
    points_gaussian: list[RFreeScaleReplPointPayload]
    points_quasipoisson: list[RFreeScaleReplPointPayload]


FREE_SCALE_REML_SCORE_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_reml.reml_score_general's FREE-scale branch "
        "computes the profiled REML criterion (Wood 2011 eq. 4, differentiated "
        "w.r.t. the unknown scale and substituted back) from the shared "
        "design, two independently-scaled penalty blocks and response, "
        "evaluated at coefficients fitted independently via "
        "gam_fit.penalized_irls_general; mgcv computes the same criterion via "
        "gam(family=gaussian(link='identity')|quasipoisson(link='log'), "
        "paraPen=list(X=list(S1, S2, sp=c(sp1, sp2))), method='REML')$gcv.ubre "
        "at the SAME fixed sp point (scripts/gam_free_scale_reml_score_probe.R). "
        "Gaussian is compared on the ABSOLUTE score "
        "(max_abs_score_diff < 1e-6, matching a standalone check that "
        "reproduced mgcv's own gcv.ubre to float round-trip precision "
        "including every additive constant); quasi-Poisson is compared on the "
        "PAIRWISE DIFFERENCE only, the SAME convention gam_reml_conformance "
        "already uses for the known-scale binomial case, because "
        "quasi-likelihood has no proper saturated log-likelihood and so "
        "carries its own small, near-constant additive residual (see the "
        "module docstring)."
    ),
    quantities=(
        ComparedQuantity(
            quantity="gaussian_reml_score (absolute)",
            left_producer=(
                "gam_reml.reml_score_general (free-scale branch) on an "
                "independently-converged gam_fit.penalized_irls_general fit "
                "under gaussian_identity()"
            ),
            right_producer=(
                "mgcv gam(family=gaussian(), method='REML')$gcv.ubre at the same fixed sp"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="quasipoisson_reml_score_pairwise_diff",
            left_producer=(
                "gam_reml.reml_score_general (free-scale branch) on an "
                "independently-converged gam_fit.penalized_irls_general fit "
                "under quasipoisson_log()"
            ),
            right_producer=(
                "mgcv gam(family=quasipoisson(), method='REML')$gcv.ubre at the same fixed sp"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Rung L5's score-level provenance declaration (ADR-193). Both quantities
INDEPENDENT — neither producer reads the other's fit or score, only the
shared recipe (``X``, ``S1``, ``S2``, ``y``, and the ``sp`` points, a shared
SETTING both sides fit at, not a computed quantity)."""


def score_free_scale_point(
    x: np.ndarray,
    s1: np.ndarray,
    s2: np.ndarray,
    y: np.ndarray,
    family: Family,
    sp: tuple[float, float],
) -> float:
    """The independent Python producer for one probe point's free-scale REML
    score. Takes plain arrays and the ``sp`` setting itself — never a dict
    shaped like the R payload."""
    fit = _independent_fit(x, s1, s2, y, family, sp)
    return reml_score_general(y, x, family, fit.coef, (s1, s2), np.asarray(sp))


class FreeScaleAbsoluteComparison(TypedDict):
    sp: tuple[float, float]
    python_score: float
    r_score: float
    diff: float
    agrees: bool


def compare_free_scale_absolute(
    x: np.ndarray, s1: np.ndarray, s2: np.ndarray, r_payload: RFreeScaleReplPayload
) -> tuple[FreeScaleAbsoluteComparison, ...]:
    """Gaussian's ABSOLUTE score at every probe point, Python vs ``mgcv``."""
    y = np.asarray(r_payload["y_gaussian"], dtype=np.float64)
    family = gaussian_identity()
    out: list[FreeScaleAbsoluteComparison] = []
    for point in r_payload["points_gaussian"]:
        sp = (float(point["sp"][0]), float(point["sp"][1]))
        python_score = score_free_scale_point(x, s1, s2, y, family, sp)
        r_score = float(point["gcv_ubre"])
        diff = python_score - r_score
        out.append(
            FreeScaleAbsoluteComparison(
                sp=sp,
                python_score=python_score,
                r_score=r_score,
                diff=diff,
                agrees=abs(diff) < _GAUSSIAN_ABSOLUTE_TOLERANCE,
            )
        )
    return tuple(out)


class FreeScalePairwiseComparison(TypedDict):
    point_a: tuple[float, float]
    point_b: tuple[float, float]
    python_diff: float
    r_diff: float
    residual: float
    agrees: bool


def compare_free_scale_pairwise(
    x: np.ndarray, s1: np.ndarray, s2: np.ndarray, r_payload: RFreeScaleReplPayload
) -> tuple[FreeScalePairwiseComparison, ...]:
    """Quasi-Poisson's pairwise score differences among the probe's points,
    Python vs ``mgcv`` — the same convention
    ``gam_reml_conformance.compare_reml_points`` uses for the known-scale
    binomial case."""
    y = np.asarray(r_payload["y_quasipoisson"], dtype=np.float64)
    family = quasipoisson_log()
    points: list[tuple[float, float]] = [
        (float(p["sp"][0]), float(p["sp"][1])) for p in r_payload["points_quasipoisson"]
    ]
    n_points = len(points)
    python_scores = [score_free_scale_point(x, s1, s2, y, family, sp) for sp in points]
    r_scores = [float(p["gcv_ubre"]) for p in r_payload["points_quasipoisson"]]

    out: list[FreeScalePairwiseComparison] = []
    for i, j in combinations(range(n_points), 2):
        python_diff = python_scores[i] - python_scores[j]
        r_diff = r_scores[i] - r_scores[j]
        residual = python_diff - r_diff
        out.append(
            FreeScalePairwiseComparison(
                point_a=points[i],
                point_b=points[j],
                python_diff=python_diff,
                r_diff=r_diff,
                residual=residual,
                agrees=abs(residual) < _PAIRWISE_TOLERANCE,
            )
        )
    return tuple(out)

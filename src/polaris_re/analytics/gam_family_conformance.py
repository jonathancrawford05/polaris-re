"""Stage-B family/link conformance — mgcv-parity engine, slice 3.

``docs/PLAN_mgcv_parity_engine.md`` slice 3's acceptance criterion: "at fixed sp
on a shared design, eta matches for each family/link/weight combination."
``scripts/gam_family_probe.R`` builds a shared ``(X, S)`` design deterministically
(``set.seed``, ADR-074 — no wall clock) and fits it under four combinations —
binomial logit/cloglog with prior weights, quasi-Poisson, and Poisson with a log
offset — writing both the recipe (``X``, ``S``, ``y``, ``weights``/``offset``,
``sp``) and its own fit (``eta``, ``coef``, ``dispersion``) to one JSON.

This module reads back **only the recipe fields** and fits independently via
:func:`polaris_re.analytics.gam_fit.penalized_irls_general` — never the R script's
``eta`` or ``coef`` — which is what makes the ``eta`` comparison INDEPENDENT
(ADR-193's mechanical test: :func:`fit_family_case`'s signature takes the recipe,
not the R payload).

**Anchor 2, applied here specifically.** ``coef`` travels in the R payload for
human reading only. :data:`FAMILY_CLAIM` does not name it, and no function in this
module compares it — the fitted surface (``eta``) is the acceptance criterion, and
``mgcv``'s own reparameterisation makes coefficients incomparable across two
independent implementations even when they agree perfectly on the surface.

**Dispersion is the second genuinely comparable quantity** PLAN slice 3 names
("phi matches where it is estimated"): :func:`polaris_re.analytics.gam_fit.pearson_dispersion`
computes it from the Python fit's own residuals, independently of ``mgcv``'s
``m$sig2`` — a real second INDEPENDENT column, not a diagnostic aside.
"""

from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import (
    Family,
    binomial_cloglog,
    binomial_logit,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_fit import (
    GeneralIRLSFit,
    effective_degrees_of_freedom,
    pearson_dispersion,
    penalized_irls_general,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "FAMILY_BY_CASE",
    "FAMILY_CLAIM",
    "FamilyCaseComparison",
    "RFamilyCasePayload",
    "compare_family_case",
    "fit_family_case",
]


_FAMILY_FACTORIES = {
    ("binomial", "logit"): binomial_logit,
    ("binomial", "cloglog"): binomial_cloglog,
    ("quasipoisson", "log"): quasipoisson_log,
    ("poisson", "log"): poisson_log,
}

FAMILY_BY_CASE: dict[str, tuple[str, str]] = {
    "binomial-logit": ("binomial", "logit"),
    "binomial-cloglog": ("binomial", "cloglog"),
    "quasipoisson-log": ("quasipoisson", "log"),
    "poisson-log-offset": ("poisson", "log"),
}
"""Case name (matching ``scripts/gam_family_probe.R``'s ``cases`` keys) to
``(family, link)`` — the recipe is data (PLAN Anchor 3's spirit applied to Stage
B), not a hardcoded branch per case."""


_AGREEMENT_TOLERANCE = 1e-9
"""Same order as Stage A's (``gam_stage_a.py``) — this is an exact comparison at
fixed sp over a shared, well-conditioned design, the same regime ADR-189
amendment 1 verified the Poisson case to 5e-13 in."""


class RFamilyCasePayload(TypedDict):
    """One entry of ``scripts/gam_family_probe.R``'s ``cases`` — the keys this
    module reads. ``eta``/``coef``/``dispersion`` are the R side's OWN fit,
    read only for the comparison, never as an input to
    :func:`fit_family_case`."""

    family: str
    link: str
    y: list[float]
    weights: list[float] | None
    offset: list[float] | None
    sp: float
    eta: list[float]
    coef: list[float]
    dispersion: float
    scale_estimated: bool
    converged: bool


FAMILY_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_fit.penalized_irls_general solves the penalized "
        "IRLS recursion for a given family/link from the shared design, penalty, "
        "response, weights and offset; mgcv computes the same fit via "
        "gam(family=..., weights=..., paraPen=list(X=list(S, sp=sp))) at the "
        "SAME fixed sp; compared on eta (every case) and dispersion "
        "(quasipoisson-log, the one case where mgcv estimates it)."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta",
            left_producer="gam_fit.penalized_irls_general (independent IRLS implementation)",
            right_producer="mgcv::predict(m, type='link') on a gam() fit at the same fixed sp",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="dispersion",
            left_producer="gam_fit.pearson_dispersion on the Python fit's own residuals",
            right_producer="mgcv m$sig2 (mgcv's own Pearson dispersion estimate)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 3's provenance declaration (ADR-193). Both quantities are INDEPENDENT:
:func:`fit_family_case` never reads ``scripts/gam_family_probe.R``'s ``eta``,
``coef`` or ``dispersion`` fields, only the shared recipe (``X``, ``S``, ``y``,
``weights``, ``offset``, ``sp``) — the mechanical test applied to
:func:`fit_family_case`'s signature. ``coef`` is deliberately absent from this
claim (Anchor 2: never a Stage-B acceptance criterion)."""


def fit_family_case(
    case_name: str,
    x: np.ndarray,
    s: np.ndarray,
    r_case: RFamilyCasePayload,
) -> GeneralIRLSFit:
    """The independent Python producer for one slice-3 case.

    Takes only the shared recipe fields off ``r_case`` (``y``, ``weights``,
    ``offset``, ``sp``) — never ``eta``, ``coef`` or ``dispersion`` — which is
    what makes this function's output comparable to the R side's fit as
    INDEPENDENT evidence rather than a read-back.
    """
    if case_name not in FAMILY_BY_CASE:
        raise PolarisValidationError(
            f"fit_family_case: unknown case {case_name!r}; known cases are "
            f"{sorted(FAMILY_BY_CASE)}."
        )
    family_name, link_name = FAMILY_BY_CASE[case_name]
    if (r_case["family"], r_case["link"]) != (family_name, link_name):
        raise PolarisValidationError(
            f"fit_family_case: case {case_name!r} names family/link "
            f"{(family_name, link_name)}, but the R payload says "
            f"{(r_case['family'], r_case['link'])!r}."
        )
    family: Family = _FAMILY_FACTORIES[(family_name, link_name)]()

    y = np.asarray(r_case["y"], dtype=np.float64)
    weights = None if r_case["weights"] is None else np.asarray(r_case["weights"], dtype=np.float64)
    offset = None if r_case["offset"] is None else np.asarray(r_case["offset"], dtype=np.float64)
    sp = float(r_case["sp"])

    penalty = sp * np.asarray(s, dtype=np.float64)
    return penalized_irls_general(
        np.asarray(x, dtype=np.float64),
        y,
        family=family,
        penalty=penalty,
        offset=offset,
        weights=weights,
    )


class FamilyCaseComparison(TypedDict):
    case_name: str
    max_abs_eta_diff: float
    dispersion_diff: float | None
    """``None`` when the family holds dispersion fixed at 1 (mgcv does not
    estimate it there, so there is nothing to compare — PLAN slice 3: "phi
    matches WHERE IT IS ESTIMATED")."""
    agrees: bool
    evidence: VerificationClaim


def compare_family_case(
    case_name: str,
    x: np.ndarray,
    s: np.ndarray,
    python_fit: GeneralIRLSFit,
    r_case: RFamilyCasePayload,
) -> FamilyCaseComparison:
    """Compare the independent Python fit against the R payload's own fit.

    ``x``/``s`` are the shared recipe (needed again here to compute ``tr(F)`` at
    the converged fit for the dispersion check) — the same recipe
    :func:`fit_family_case` was given, not a second read of the R side's
    output.
    """
    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    if r_eta.shape != python_fit.eta.shape:
        raise PolarisValidationError(
            f"compare_family_case({case_name!r}): R eta has shape {r_eta.shape}, "
            f"Python eta has shape {python_fit.eta.shape}."
        )
    max_abs_eta_diff = float(np.max(np.abs(r_eta - python_fit.eta)))

    dispersion_diff: float | None = None
    agrees = max_abs_eta_diff < _AGREEMENT_TOLERANCE
    if r_case["scale_estimated"]:
        family: Family = _FAMILY_FACTORIES[FAMILY_BY_CASE[case_name]]()
        weights = (
            np.ones_like(python_fit.mu)
            if r_case["weights"] is None
            else np.asarray(r_case["weights"], dtype=np.float64)
        )
        y = np.asarray(r_case["y"], dtype=np.float64)
        penalty = float(r_case["sp"]) * np.asarray(s, dtype=np.float64)
        edf = effective_degrees_of_freedom(
            np.asarray(x, dtype=np.float64),
            family,
            python_fit.eta,
            python_fit.mu,
            penalty,
            weights=weights,
        )
        phi_python = pearson_dispersion(y, python_fit.mu, weights, family, edf=edf)
        dispersion_diff = float(phi_python - r_case["dispersion"])
        # Relative tolerance: dispersion is a ratio of Pearson residuals to
        # residual dof, not a linear-predictor value, so it earns its own
        # (looser, relative) tolerance rather than eta's absolute one — same
        # reasoning RUNBOOK's level-4 metrics already apply to a ratio metric.
        agrees = agrees and abs(dispersion_diff) < 1e-4 * max(abs(r_case["dispersion"]), 1.0)

    return FamilyCaseComparison(
        case_name=case_name,
        max_abs_eta_diff=max_abs_eta_diff,
        dispersion_diff=dispersion_diff,
        agrees=agrees,
        evidence=FAMILY_CLAIM,
    )

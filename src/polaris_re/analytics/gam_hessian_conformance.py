"""Exact REML Hessian vs ``mgcv``'s ``outer.info$hess`` — outer-solver epic Slice 2.

The Python side of ``scripts/gam_hessian_probe.R``.

**The claim (ADR-193, written before the code):** ``gam_reml_hessian`` computes
the Hessian of the REML criterion in natural-log ``sp`` by differentiating this
engine's own analytic gradient (Wood 2011 §3.4-3.5, derived in that module),
from a Polaris penalized fit at the shared ``sp``; ``mgcv`` computes it inside
``gam(method="REML")``'s Newton outer loop (``m$outer.info$hess``) from its own
fit and its own derivative code; compared element-wise, each entry scaled by
``sqrt(H_ii H_jj)`` of ``mgcv``'s matrix (so the ``lambda -> infinity`` block's
tiny curvature is not hidden behind the large one — the failure the level-4
inflation ratio showed, ``gam_uncertainty_conformance``).

**What is and is not shared.** :class:`RHessianRecipe` carries the design,
penalty blocks, ``y``, prior weights and ``mgcv``'s SELECTED ``sp`` — the last
only as the POINT OF EVALUATION (a Hessian is a function of ``rho``;
``docs/VERIFICATION_STANDARD.md`` §2.1). It structurally excludes
``outer_hessian``, ``scale`` and the gradient, so :func:`hessian_at_recipe`
cannot read the reference even if handed the wider :class:`RHessianPayload`.

**Free scale.** ``mgcv`` appends ``log(phi)`` to the search vector, so its
Hessian is ``(M+1) x (M+1)``. The comparable object is the PROFILE Hessian, the
Schur complement over ``log phi`` of ``mgcv``'s matrix, against
:func:`~polaris_re.analytics.gam_reml_hessian.reml_score_hessian_profiled`
(which profiles ``phi`` analytically from ``phi_hat = Dp/(n - Mp)``). The
estimated scale itself is a second INDEPENDENT quantity.

**Tolerance.** :data:`HESSIAN_AGREEMENT_TOL` is ``mgcv``'s own
``gam.control()$newton$conv.tol`` (``1e-6``): ``mgcv`` evaluates its Hessian at
a ``rho`` it certifies only to a gradient of that size, and the Hessian varies
at order one per unit ``rho``. It is that control constant, named as such, not
fitted to the readings (Anchor 8).
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_family import (
    Family,
    binomial_cloglog,
    binomial_logit,
    gaussian_identity,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_reml import penalty_block_square_roots
from polaris_re.analytics.gam_reml_appendix_b import appendix_b_transform
from polaris_re.analytics.gam_reml_hessian import (
    reml_score_hessian,
    reml_score_hessian_profiled,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "HESSIAN_AGREEMENT_TOL",
    "HESSIAN_CLAIM",
    "HessianComparison",
    "HessianProduced",
    "RHessianPayload",
    "RHessianRecipe",
    "compare_hessian_case",
    "hessian_at_recipe",
    "recipe_of",
]

HESSIAN_AGREEMENT_TOL = 1.0e-6
"""``gam.control()$newton$conv.tol`` — see the module docstring."""

_FAMILIES: dict[tuple[str, str], Family] = {
    ("poisson", "log"): poisson_log(),
    ("binomial", "logit"): binomial_logit(),
    ("binomial", "cloglog"): binomial_cloglog(),
    ("quasipoisson", "log"): quasipoisson_log(),
    ("gaussian", "identity"): gaussian_identity(),
}


class RHessianRecipe(TypedDict):
    """The shared recipe — and **nothing else** (the ADR-193 mechanical test,
    applied structurally: no ``outer_hessian``/``scale``/gradient key)."""

    label: str
    family: str
    link: str
    y: list[float]
    prior_weights: list[float]
    selected_sp: list[float]


class RHessianPayload(RHessianRecipe):
    """The recipe plus ``mgcv``'s own Hessian and scale. Read by
    :func:`compare_hessian_case` only."""

    outer_hessian: list[float]
    hess_dim: int
    scale: float
    scale_estimated: bool


HESSIAN_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_reml_hessian computes the Hessian of the REML "
        "criterion in natural-log sp by differentiating Polaris's own analytic "
        "gradient (Wood 2011 s3.4-3.5), from a Polaris penalized fit over the "
        "shared (X, S_j, y, prior weights) evaluated at the shared sp; mgcv "
        "computes it as gam(method='REML')$outer.info$hess from its own fit and "
        "derivative code; compared element-wise, scaled by sqrt(H_ii H_jj), "
        "(free scale: the Schur complement over log(phi))."
    ),
    quantities=(
        ComparedQuantity(
            quantity="rho_hessian",
            left_producer=(
                "gam_reml_hessian.reml_score_hessian[_profiled] (own fit via "
                "penalized_irls_general, own exact second derivative)"
            ),
            right_producer=(
                "mgcv gam(method='REML')$outer.info$hess (Schur over log phi if free scale)"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="scale_hat",
            left_producer="phi_hat = Dp/(n - Mp) from Polaris's own fit (gaussian only)",
            right_producer="mgcv gam(method='REML')$sig2 (gaussian only)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Both quantities INDEPENDENT: :func:`hessian_at_recipe` takes
:class:`RHessianRecipe`, which has no key through which ``mgcv``'s Hessian or
scale could enter. The ONE shared input is ``selected_sp`` as the point of
evaluation — disclosed, and not an operand."""


@dataclass(frozen=True)
class HessianProduced:
    """What the Polaris producer returns, carrying its own provenance."""

    hessian: np.ndarray
    scale_hat: float | None
    evidence: VerificationClaim


def recipe_of(payload: RHessianPayload) -> RHessianRecipe:
    """The payload narrowed to the recipe — the only thing the producer sees."""
    return RHessianRecipe(
        label=payload["label"],
        family=payload["family"],
        link=payload["link"],
        y=payload["y"],
        prior_weights=payload["prior_weights"],
        selected_sp=payload["selected_sp"],
    )


def hessian_at_recipe(
    recipe: RHessianRecipe,
    design: np.ndarray,
    penalties: tuple[np.ndarray, ...],
) -> HessianProduced:
    """The independent Python producer: fit at the shared ``sp`` and return the
    exact Hessian (profile Hessian for a free-scale family)."""
    key = (recipe["family"], recipe["link"])
    if key not in _FAMILIES:
        raise PolarisValidationError(f"hessian_at_recipe: no Family recorded for {key}.")
    family = _FAMILIES[key]
    y = np.asarray(recipe["y"], dtype=np.float64)
    weights = np.asarray(recipe["prior_weights"], dtype=np.float64)
    sp = np.asarray(recipe["selected_sp"], dtype=np.float64)
    s_total = sum(lam * block for lam, block in zip(sp, penalties, strict=True))
    fit = penalized_irls_general(design, y, family=family, penalty=s_total, weights=weights)
    if family.dispersion_fixed:
        hessian = reml_score_hessian(y, design, family, fit.coef, penalties, sp, weights=weights)
        return HessianProduced(hessian, None, HESSIAN_CLAIM)
    hessian = reml_score_hessian_profiled(
        y, design, family, fit.coef, penalties, sp, weights=weights
    )
    sqrt_blocks = penalty_block_square_roots(penalties)
    dp = family.deviance(y, fit.mu, weights) + sum(
        lam * float(np.sum((root.T @ fit.coef) ** 2))
        for lam, root in zip(sp, sqrt_blocks, strict=True)
    )
    mp = design.shape[1] - appendix_b_transform(penalties, sp).rank
    return HessianProduced(hessian, dp / (design.shape[0] - mp), HESSIAN_CLAIM)


def _mgcv_profile_hessian(payload: RHessianPayload) -> np.ndarray:
    """``mgcv``'s Hessian over ``log sp``, Schur-reduced over ``log phi`` when the
    scale was estimated (``hess_dim = M + 1``)."""
    m = len(payload["selected_sp"])
    dim = int(payload["hess_dim"])
    if len(payload["outer_hessian"]) != dim * dim:
        raise PolarisValidationError(
            f"mgcv Hessian payload has {len(payload['outer_hessian'])} entries for "
            f"hess_dim={dim}; expected {dim * dim}."
        )
    full = np.asarray(payload["outer_hessian"], dtype=np.float64).reshape(dim, dim)
    if dim == m:
        return full
    if dim != m + 1:
        raise PolarisValidationError(
            f"mgcv Hessian is {dim}x{dim} for {m} smoothing parameters — expected {m} or {m + 1}."
        )
    rr, rp, pp = full[:m, :m], full[:m, m:], full[m:, m:]
    return np.asarray(rr - rp @ np.linalg.solve(pp, rp.T), dtype=np.float64)


@dataclass(frozen=True)
class HessianComparison:
    """One case's verdict. ``max_scaled_diff`` is the governing number."""

    label: str
    ours: np.ndarray
    mgcv: np.ndarray
    max_scaled_diff: float
    max_abs_diff: float
    scale_rel_diff: float | None
    agrees: bool
    tolerance: float
    evidence: VerificationClaim


def compare_hessian_case(
    payload: RHessianPayload,
    design: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    tolerance: float = HESSIAN_AGREEMENT_TOL,
) -> HessianComparison:
    """Produce Polaris's Hessian from the RECIPE alone and compare it to ``mgcv``'s."""
    produced = hessian_at_recipe(recipe_of(payload), design, penalties)
    reference = _mgcv_profile_hessian(payload)
    diag = np.sqrt(np.abs(np.diag(reference)))
    scaled = np.abs(produced.hessian - reference) / np.outer(diag, diag)
    scale_diff = (
        abs(produced.scale_hat - float(payload["scale"])) / float(payload["scale"])
        if produced.scale_hat is not None and payload["family"] == "gaussian"
        else None
    )
    max_scaled = float(np.max(scaled))
    return HessianComparison(
        label=str(payload["label"]),
        ours=produced.hessian,
        mgcv=reference,
        max_scaled_diff=max_scaled,
        max_abs_diff=float(np.max(np.abs(produced.hessian - reference))),
        scale_rel_diff=scale_diff,
        agrees=bool(max_scaled < tolerance and (scale_diff is None or scale_diff < tolerance)),
        tolerance=tolerance,
        evidence=produced.evidence,
    )

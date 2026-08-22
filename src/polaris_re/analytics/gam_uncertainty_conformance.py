"""Conformance for Wood, Pya and Saefken (2016) eq. (7) against ``mgcv``.

``docs/WORK_ORDER_level4_wps2016.md``. The Python side of
``scripts/gam_vc_probe.R``, and the comparison that closes ADR-190's level-4
formula gap.

**The claim (ADR-193):** :func:`~polaris_re.analytics.gam_uncertainty.unconditional_covariance`
assembles the corrected covariance from eq. (7) given a converged fit and the
shared ``(X, S_j, lambda)``; ``mgcv`` computes ``vcov(m, unconditional = TRUE)``
through its own machinery; compared **element-wise** on ``Vc - Vp``, and on the
inflation ratio the conformance suite already reports.

**Element-wise, not just the ratio.** The scalar inflation ratio averages
diagonals, and during this slice it read 0.39% while the element-wise residual
was 26.7% — it hid a real structural disagreement behind a green headline. Both
are reported; the element-wise number is the one that governs.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_derivatives import (
    d_beta_d_rho,
    d_eta_d_rho,
    dw_drho,
    newton_working_weights,
)
from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_uncertainty import unconditional_covariance
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "VC_CLAIM",
    "RVcCase",
    "VcComparison",
    "compare_vc_case",
]


class RVcCase(TypedDict):
    """One case of ``scripts/gam_vc_probe.R``'s output.

    ``y``/``prior_weights``/``selected_sp``/``outer_hessian`` are shared recipe;
    ``vcov_full`` and ``vcov_unconditional_full`` are the reference operand.
    """

    label: str
    family: str
    link: str
    y: list[float]
    prior_weights: list[float]
    selected_sp: list[float]
    outer_hessian: list[float]
    vcov_full: list[float]
    vcov_unconditional_full: list[float]
    mgcv_inflation: float


VC_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_uncertainty assembles the corrected covariance "
        "from Wood, Pya and Saefken (2016) eq. (7) — V_beta + J Vrho J^T + V'' — "
        "given a converged penalized fit over the shared (X, S_j, lambda); mgcv "
        "computes vcov(m, unconditional = TRUE) through its own internal "
        "machinery; compared element-wise on the correction (Vc - Vp) and on the "
        "mean-diagonal inflation ratio."
    ),
    quantities=(
        ComparedQuantity(
            quantity="unconditional_correction",
            left_producer=(
                "gam_uncertainty.unconditional_covariance (eq. (7), assembled from "
                "our own V_beta, J, dw/drho and rho Hessian)"
            ),
            right_producer="mgcv vcov(m, unconditional = TRUE) - vcov(m)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="inflation_ratio",
            left_producer="mean(diag(V'_beta)) / mean(diag(V_beta)), ours throughout",
            right_producer="mean(diag(mgcv Vc)) / mean(diag(mgcv Vp))",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Provenance for the level-4 comparison (ADR-193).

Both quantities INDEPENDENT: we assemble eq. (7) from our own fit and
derivatives; ``mgcv`` produces ``Vc`` through machinery we never read. The
shared recipe is ``(X, S_j, y, prior weights)`` plus ``mgcv``'s selected
``lambda`` — the last so that a lambda disagreement cannot masquerade as a
correction disagreement, which is RUNBOOK level 4's own stated hazard.

The ``rho`` Hessian is read from ``mgcv``'s ``outer.info$hess`` **as a shared
input**, not as an answer: our own finite-difference Hessian reproduces it
(eigenvalues match, ADR-201's session), so this removes a second-order
difference from the comparison rather than importing the result."""


@dataclass(frozen=True)
class VcComparison:
    """One case's level-4 verdict."""

    label: str
    max_rel_correction_diff: float
    ours_inflation: float
    mgcv_inflation: float
    rel_inflation_diff: float
    agrees: bool
    tolerance: float
    evidence: VerificationClaim


def compare_vc_case(
    r_case: RVcCase,
    design: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    family: Family,
    tolerance: float = 0.02,
) -> VcComparison:
    """Assemble eq. (7) independently and compare against ``mgcv``'s ``Vc``.

    ``tolerance`` is on the **element-wise** relative residual. 2% is set by the
    measured floor of the approximation, not by what makes a check pass: eq. (7)
    comes from a first-order Taylor expansion whose remainder ``r`` the paper
    drops, so exact agreement is not available in principle. Across five
    held-out cases the worst residual was 0.730%, so 2% leaves under a factor of
    three of headroom over the observed spread (Anchor 8).
    """
    p = design.shape[1]
    y = np.asarray(r_case["y"], dtype=np.float64)
    prior_weights = np.asarray(r_case["prior_weights"], dtype=np.float64)
    rho = np.log(np.asarray(r_case["selected_sp"], dtype=np.float64))
    m = rho.shape[0]

    s_total = np.zeros((p, p), dtype=np.float64)
    for lam_k, block in zip(np.exp(rho), penalties, strict=True):
        s_total = s_total + lam_k * block
    fit = penalized_irls_general(design, y, family=family, penalty=s_total, weights=prior_weights)
    hess_weights = newton_working_weights(family, y, fit.eta, fit.mu, prior_weights)
    v_beta = np.linalg.inv(design.T @ (hess_weights[:, None] * design) + s_total)
    j = d_beta_d_rho(design, penalties, hess_weights, fit.coef, rho)
    deta = d_eta_d_rho(design, penalties, hess_weights, fit.coef, rho)
    dw = dw_drho(family, fit.eta, fit.mu, deta, prior_weights)
    rho_hessian = np.asarray(r_case["outer_hessian"], dtype=np.float64).reshape(m, m)

    corr = unconditional_covariance(v_beta, design, j, dw, penalties, rho, rho_hessian)

    mgcv_vp = np.asarray(r_case["vcov_full"], dtype=np.float64).reshape(p, p)
    mgcv_vc = np.asarray(r_case["vcov_unconditional_full"], dtype=np.float64).reshape(p, p)
    mgcv_correction = mgcv_vc - mgcv_vp
    ours_correction = corr.first_order + corr.second_order
    max_rel = float(
        np.max(np.abs(ours_correction - mgcv_correction)) / np.max(np.abs(mgcv_correction))
    )

    ours_infl = corr.inflation(corr.full)
    mgcv_infl = float(r_case["mgcv_inflation"])
    return VcComparison(
        label=str(r_case["label"]),
        max_rel_correction_diff=max_rel,
        ours_inflation=ours_infl,
        mgcv_inflation=mgcv_infl,
        rel_inflation_diff=abs(ours_infl - mgcv_infl) / mgcv_infl,
        agrees=bool(max_rel < tolerance),
        tolerance=tolerance,
        evidence=VC_CLAIM,
    )

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
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.analytics.gam_uncertainty import unconditional_covariance
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "FD_HESSIAN_STEP",
    "VC_CLAIM",
    "RVcCase",
    "VcComparison",
    "compare_vc_case",
    "finite_difference_rho_hessian",
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
input**, not as an answer, so that a Hessian disagreement cannot masquerade as a
correction disagreement.

**How strong that disclosure is, stated precisely** (PR #207 review [P1], which
found the previous wording overstated on all three counts):

* The supporting evidence is an *eigenvalue* comparison, recorded in
  ``docs/WORK_ORDER_level4_wps2016.md`` §2 — **not** in ADR-201 or its session
  log, which the earlier wording cited and which contain no Hessian comparison
  at all.
* Eigenvalue agreement is **weaker than matrix agreement**. ``V' = J H⁻¹ Jᵀ``
  depends on the eigenvectors too, so matching spectra do not by themselves
  establish that substituting our own Hessian leaves ``Vc - Vp`` unchanged.
* Nothing committed pinned it: no test, and the probe had no path that
  substituted our own Hessian. :func:`finite_difference_rho_hessian` and the
  ``own_hessian_*`` fields of :class:`VcComparison` now close that: every case
  reports the full-matrix difference against ``mgcv``'s Hessian **and** the
  correction residual recomputed with ours substituted.

What still supports the INDEPENDENT declaration is the mechanical test itself —
the compared quantity is ``Vc - Vp``, and it demonstrably *can* disagree while
using ``mgcv``'s own ``Vrho``: ADR-190's level 4 did exactly that, at 3.2-4.1x."""


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

    max_rel_own_hessian_diff: float = float("nan")
    """Full-matrix relative difference between our finite-difference ``rho``
    Hessian and ``mgcv``'s ``outer.info$hess``.

    **Reported, never gated.** The Hessian is a shared *input* to the comparison,
    so a disagreement here is a caveat on the disclosure rather than a level-4
    failure — and gating on it would quietly convert a shared input into a
    compared quantity, which is not what ``VC_CLAIM`` declares."""

    max_rel_correction_diff_own_hessian: float = float("nan")
    """The element-wise correction residual, recomputed with **our** Hessian
    substituted for ``mgcv``'s.

    This is the number PR #207's review actually asked for. Eigenvalue agreement
    does not establish that ``V' = J H⁻¹ Jᵀ`` is unchanged, because that depends
    on the eigenvectors too. Substituting and re-measuring does."""


FD_HESSIAN_STEP = 0.05
"""Central-difference step in natural log lambda for :func:`finite_difference_rho_hessian`.

Not tuned to make anything agree (PLAN Anchor 8). It is the same order as
``experience_gam_penalized.KS_LOG_STEP`` (``ln(10) * 0.25`` = 0.576) reduced for the
smoother general criterion, and the quantity it feeds is *reported*, never gated on.
"""


def finite_difference_rho_hessian(
    design: np.ndarray,
    y: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    family: Family,
    prior_weights: np.ndarray,
    rho: np.ndarray,
    step: float = FD_HESSIAN_STEP,
) -> np.ndarray:
    """Our own Hessian of the REML criterion in ``rho``, by central differences.

    Exists because PR #207's review was right that the claim "our own Hessian
    reproduces mgcv's" was **unpinned**: the supporting record was an eigenvalue
    comparison in a work order, eigenvalues are weaker than the matrix
    ``V' = J H⁻¹ Jᵀ`` actually depends on, and no committed path substituted our
    own. This is that path.

    Built entirely from already-verified pieces —
    :func:`~polaris_re.analytics.gam_fit.penalized_irls_general` (ADR-195) and
    :func:`~polaris_re.analytics.gam_reml.reml_score_general` (ADR-196/197) — so it
    introduces no new fitting or scoring formula.
    """
    m = rho.shape[0]
    p = design.shape[1]

    def score_at(offsets: np.ndarray) -> float:
        lambdas = np.exp(rho + offsets)
        s_total = np.zeros((p, p), dtype=np.float64)
        for lam_k, block in zip(lambdas, penalties, strict=True):
            s_total = s_total + lam_k * block
        fit = penalized_irls_general(
            design, y, family=family, penalty=s_total, weights=prior_weights
        )
        return reml_score_general(
            y, design, family, fit.coef, penalties, lambdas, weights=prior_weights
        )

    zero = np.zeros(m, dtype=np.float64)
    centre = score_at(zero)
    hessian = np.zeros((m, m), dtype=np.float64)
    for j in range(m):
        e_j = np.zeros(m, dtype=np.float64)
        e_j[j] = step
        hessian[j, j] = (score_at(e_j) - 2.0 * centre + score_at(-e_j)) / (step * step)
        for k in range(j + 1, m):
            e_k = np.zeros(m, dtype=np.float64)
            e_k[k] = step
            mixed = (
                score_at(e_j + e_k)
                - score_at(e_j - e_k)
                - score_at(-e_j + e_k)
                + score_at(-e_j - e_k)
            ) / (4.0 * step * step)
            hessian[j, k] = mixed
            hessian[k, j] = mixed
    return np.asarray(hessian, dtype=np.float64)


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

    # PR #207 review [P1]: the claim "our own Hessian reproduces mgcv's" was
    # unpinned. Both halves of the reviewer's ask are answered here — the full
    # matrix is compared, and the whole correction is recomputed with ours
    # substituted, because eigenvalue agreement does not establish that
    # V' = J H^-1 J^T is unchanged. Reported, never gated: the Hessian is a shared
    # input, and gating on it would silently promote it to a compared quantity.
    own_hessian = finite_difference_rho_hessian(design, y, penalties, family, prior_weights, rho)
    max_rel_own_hessian_diff = float(
        np.max(np.abs(own_hessian - rho_hessian)) / np.max(np.abs(rho_hessian))
    )
    corr_own = unconditional_covariance(v_beta, design, j, dw, penalties, rho, own_hessian)

    mgcv_vp = np.asarray(r_case["vcov_full"], dtype=np.float64).reshape(p, p)
    mgcv_vc = np.asarray(r_case["vcov_unconditional_full"], dtype=np.float64).reshape(p, p)
    mgcv_correction = mgcv_vc - mgcv_vp
    ours_correction = corr.first_order + corr.second_order
    max_rel = float(
        np.max(np.abs(ours_correction - mgcv_correction)) / np.max(np.abs(mgcv_correction))
    )

    ours_correction_own = corr_own.first_order + corr_own.second_order

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
        max_rel_own_hessian_diff=max_rel_own_hessian_diff,
        max_rel_correction_diff_own_hessian=float(
            np.max(np.abs(ours_correction_own - mgcv_correction)) / np.max(np.abs(mgcv_correction))
        ),
    )

"""Conformance for Wood (2011)'s ``dη/drho`` and ``dw/drho`` against ``mgcv``.

``docs/WORK_ORDER_dw_drho_wood2011.md``. The Python side of
``scripts/gam_deriv_probe.R``.

**The claim (ADR-193), written before the code:**
:mod:`polaris_re.analytics.gam_derivatives` computes ``dη/drho`` and ``dw/drho``
analytically from Wood (2011) §3.4 and Appendix D, given a converged penalized
fit and the shared ``(X, {Sⱼ})``; ``mgcv`` computes the same quantities by **its
own refits at perturbed smoothing parameters**, central-differenced; compared on
``d_eta_d_rho`` and ``dw_drho``.

**The mechanical test, applied to the signature.** :func:`analytic_derivatives`
takes the shared recipe only — design, penalties, response, prior weights, the
family spec and the ``rho`` grid. It never receives the R side's ``eta``, ``w``, or
any difference of them. The R side never sees a Python number. Both operands are
independently produced, so a disagreement here is a real result about the
derivative, not a broken round trip.

**Why ``dη/drho`` rather than ``dβ̂/drho``.** PLAN Anchor 2: ``mgcv``
reparameterises internally, so ``β̂`` is basis-dependent and ``η`` is not.
``dβ̂/drho`` is computed internally by
:func:`~polaris_re.analytics.gam_derivatives.d_beta_d_rho` and is deliberately
**not** a compared quantity.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_derivatives import (
    d_eta_d_rho,
    dw_drho,
    newton_working_weights,
)
from polaris_re.analytics.gam_family import (
    Family,
    binomial_cloglog,
    binomial_logit,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "DERIVATIVE_CLAIM",
    "DerivativeComparison",
    "RDerivCase",
    "RPerturbedFit",
    "analytic_derivatives",
    "compare_derivative_case",
    "family_for",
]


class RPerturbedFit(TypedDict):
    """One ``mgcv`` refit at ``rho +/- h`` for a single penalty block."""

    h: float
    block: int
    eta_plus: list[float]
    eta_minus: list[float]
    w_plus: list[float]
    w_minus: list[float]


class RDerivCase(TypedDict):
    """One case of ``scripts/gam_deriv_probe.R``'s output.

    Documented in the type rather than left as an untyped ``dict`` (CLAUDE.md
    section 5), matching :class:`~polaris_re.analytics.gam_stage_a.RTermPayload`'s
    convention for the same job.

    ``family``/``link``/``y``/``prior_weights`` are **shared recipe** — the Python
    side reads them so both sides solve the same problem. ``eta``/``w``/
    ``perturbed`` are the **reference operand** and are never read by the Python
    producer, only by the comparator (ADR-193's mechanical test).
    """

    label: str
    family: str
    link: str
    eta: list[float]
    w: list[float]
    y: list[float]
    prior_weights: list[float]
    perturbed: dict[str, RPerturbedFit]


DERIVATIVE_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_derivatives computes d(eta)/d(rho) and "
        "d(w)/d(rho) analytically from Wood (2011) section 3.4 and Appendix D, "
        "given a converged penalized fit over the shared (X, S_j); mgcv computes "
        "the same quantities by refitting at rho +/- h and central-differencing "
        "its own eta and its own working weights; compared on d_eta_d_rho and "
        "dw_drho, per penalty block. Coefficients are never compared "
        "(PLAN Anchor 2)."
    ),
    quantities=(
        ComparedQuantity(
            quantity="d_eta_d_rho",
            left_producer=(
                "gam_derivatives.d_eta_d_rho (Wood 2011 sec 3.4, analytic, at the "
                "observed-Hessian working weights)"
            ),
            right_producer=(
                "central difference of mgcv's own predict(type='link') at rho +/- h "
                "(scripts/gam_deriv_probe.R)"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="dw_drho",
            left_producer=("gam_derivatives.dw_drho (Wood 2011 Appendix D, analytic chain rule)"),
            right_producer=(
                "central difference of mgcv's own m$weights at rho +/- h "
                "(scripts/gam_deriv_probe.R)"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Provenance for the Wood (2011) derivative slice (ADR-193).

Both quantities are INDEPENDENT: the analytic formula on one side, ``mgcv``'s own
refits differenced on the other. Neither producer reads the other's output.

**What a zero here does and does not establish.** It establishes that this
engine's ``dη/drho`` and ``dw/drho`` match ``mgcv``'s actual behaviour — the
ingredient ADR-190 named as missing for the level-4 correction. It does **not**
establish anything about ``vcov(unconditional = TRUE)`` itself: how ``dw/drho``
assembles into ``Vc`` is Wood, Pya & Säfken (2016)'s contribution, and Wood (2011)
contains no unconditional-covariance formula at all. Level 4 stays open."""


_FAMILIES = {
    ("poisson", "log"): poisson_log,
    ("quasipoisson", "log"): quasipoisson_log,
    ("binomial", "logit"): binomial_logit,
    ("binomial", "cloglog"): binomial_cloglog,
}


def family_for(family_name: str, link_name: str) -> Family:
    """The :class:`Family` matching the R payload's own ``family``/``link`` strings.

    A lookup on the shared *recipe* (which distribution and link the case declares),
    not on any fitted value — reading the recipe is what makes both sides solve the
    same problem, and is the same status ``x`` and the knot vector already have
    elsewhere in this epic (ADR-193's mechanical test)."""
    key = (family_name, link_name)
    if key not in _FAMILIES:
        raise PolarisValidationError(
            f"gam_derivatives_conformance: no Family for {family_name!r}/{link_name!r}; "
            f"known: {sorted(_FAMILIES)}."
        )
    return _FAMILIES[key]()


@dataclass(frozen=True)
class DerivativeComparison:
    """One case's verdict, per compared quantity and per penalty block."""

    label: str
    max_abs_deta_drho_diff: float
    max_abs_dw_drho_diff: float
    max_abs_eta_diff: float
    deta_drho_richardson_ratio: float
    agrees: bool
    tolerance: float
    evidence: VerificationClaim


def analytic_derivatives(
    design: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    y: np.ndarray,
    prior_weights: np.ndarray,
    family: Family,
    log_lambda: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fit independently, then differentiate analytically — the left operand.

    Takes the shared recipe only; no R-produced ``eta``, ``w`` or difference of
    them appears in this signature (ADR-193's mechanical test).

    Returns:
        ``(deta_drho, dw_drho_value, eta)`` — ``(M, n)``, ``(M, n)``, ``(n,)``.
    """
    s_total = np.zeros((design.shape[1], design.shape[1]), dtype=np.float64)
    for rho_j, block in zip(np.exp(log_lambda), penalties, strict=True):
        s_total = s_total + rho_j * block
    fit = penalized_irls_general(design, y, family=family, penalty=s_total, weights=prior_weights)
    # The DERIVATIVE needs the observed (Newton) Hessian even though the FIT used
    # Fisher weights — see gam_derivatives.newton_working_weights. On a canonical
    # link the two coincide exactly; on cloglog they do not, and using Fisher here
    # is wrong by ~5 orders of magnitude.
    hessian_weights = newton_working_weights(family, y, fit.eta, fit.mu, prior_weights)
    deta = d_eta_d_rho(design, penalties, hessian_weights, fit.coef, log_lambda)
    dw = dw_drho(family, fit.eta, fit.mu, deta, prior_weights)
    return deta, dw, fit.eta


def compare_derivative_case(
    r_case: RDerivCase,
    design: np.ndarray,
    penalties: tuple[np.ndarray, ...],
    base_rho: np.ndarray,
    tolerance: float = 1e-6,
) -> DerivativeComparison:
    """Compare the analytic derivative against ``mgcv``'s own differenced refits.

    ``r_case`` is one entry of ``scripts/gam_deriv_probe.R``'s ``cases``. Its
    ``eta``/``w``/``perturbed`` fields are the **reference operand**; the Python
    side reads only ``y``, ``prior_weights``, ``family`` and ``link`` from it,
    which are shared recipe.

    Two ``h`` regimes are reported, because one step size cannot demonstrate both
    of the things that need demonstrating (see ``gam_deriv_probe.R``):

    - :attr:`~DerivativeComparison.deta_drho_richardson_ratio` is computed from
      the **largest** pair (``1e-2``, ``5e-3``), where truncation dominates and a
      central difference's ``O(h²)`` law is visible. A ratio near 4 is the
      evidence that the analytic derivative is the ``h → 0`` limit of ``mgcv``'s
      own behaviour, not merely near it at one arbitrary step.
    - :attr:`~DerivativeComparison.max_abs_deta_drho_diff` is reported at the
      **smallest** ``h``, where agreement is tightest and the residual is
      round-off limited — differencing two separately-converged ``mgcv`` fits has
      its own noise floor, and below ``h ≈ 1e-4`` shrinking ``h`` makes the
      *reference* worse rather than better.

    Reporting only the small ``h`` would overstate what the convergence check
    proves; reporting only the large ``h`` would understate the agreement.
    """
    family = family_for(r_case["family"], r_case["link"])
    y = np.asarray(r_case["y"], dtype=np.float64)
    prior_weights = np.asarray(r_case["prior_weights"], dtype=np.float64)
    deta, dw, eta = analytic_derivatives(design, penalties, y, prior_weights, family, base_rho)

    r_eta = np.asarray(r_case["eta"], dtype=np.float64)
    max_abs_eta_diff = float(np.max(np.abs(r_eta - eta)))

    by_h: dict[float, float] = {}
    dw_by_h: dict[float, float] = {}
    for entry in r_case["perturbed"].values():
        h = float(entry["h"])
        block = int(entry["block"]) - 1  # R is 1-indexed
        fd_eta = (
            np.asarray(entry["eta_plus"], dtype=np.float64)
            - np.asarray(entry["eta_minus"], dtype=np.float64)
        ) / (2.0 * h)
        fd_w = (
            np.asarray(entry["w_plus"], dtype=np.float64)
            - np.asarray(entry["w_minus"], dtype=np.float64)
        ) / (2.0 * h)
        by_h[h] = max(by_h.get(h, 0.0), float(np.max(np.abs(deta[block] - fd_eta))))
        dw_by_h[h] = max(dw_by_h.get(h, 0.0), float(np.max(np.abs(dw[block] - fd_w))))

    # Tightest agreement: the SMALLEST h (round-off limited).
    smallest = min(by_h)
    worst_deta = by_h[smallest]
    worst_dw = dw_by_h[smallest]

    # Convergence evidence: the LARGEST pair, where truncation dominates and the
    # O(h^2) law is actually observable.
    descending = sorted(by_h, reverse=True)
    ratio = float("nan")
    if len(descending) >= 2 and by_h[descending[1]] > 0:
        ratio = float(by_h[descending[0]] / by_h[descending[1]])

    return DerivativeComparison(
        label=str(r_case["label"]),
        max_abs_deta_drho_diff=worst_deta,
        max_abs_dw_drho_diff=worst_dw,
        max_abs_eta_diff=max_abs_eta_diff,
        deta_drho_richardson_ratio=ratio,
        agrees=bool(worst_deta < tolerance and worst_dw < tolerance),
        tolerance=tolerance,
        evidence=DERIVATIVE_CLAIM,
    )

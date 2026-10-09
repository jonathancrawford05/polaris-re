"""``GamFit.summary()`` against ``summary.gam(m)`` — preview epic Slice P4
(``docs/PLAN_gam_parity_preview.md``, ADR-253).

**Claim sentence (ADR-193), written before the code.** *"Polaris
(:meth:`polaris_re.gam.GamFit.summary`) computes the deviance explained, the scale, the
per-smooth ``edf`` and the REML score from its own Newton fit of the formula string —
its own family deviance, its own intercept-only (offset-aware) null fit, its own Fletcher
dispersion; ``mgcv`` computes them via ``summary.gam(gam(<same string>, method='REML'))``
and ``m$gcv.ubre``; compared on those columns."*

**Provenance.** Every compared column is INDEPENDENT except ``n`` (ECHO: the row count of
the data both sides were handed — a no-tampering check, not parity). The producer is
:func:`fit_summary_case`, whose signature takes
:class:`~polaris_re.gam.formula_conformance.FormulaRecipe` only. The Newton convergence
report (iterations, the relative projected gradient) has no ``mgcv`` counterpart on the same
criterion; it is a MEASUREMENT of Polaris against its own ``epsilon_rel``, reported beside
the table and never inside the claim.

**Tolerances are derived, not chosen (ADR-253, fixed before the first tier-3 run).** The
engine's agreement criterion is ADR-221's: ``eta`` within :data:`_ETA_TOLERANCE` on every
row and ``edf_total`` within :data:`_EDF_TOLERANCE`. ``summary`` quantities are functionals
of ``(eta, edf)``, so two fits that meet ADR-221 can differ in them by at most what that
perturbation implies. :func:`implied_gates` evaluates that bound from **Polaris's own** fit
(never from ``mgcv``'s numbers): it moves ``eta`` by ``+-delta`` along the sign of the
quantity's gradient, ``edf`` by ``+-`` the ``edf`` gate, and re-evaluates the quantity. A
disagreement beyond that bound is not explained by ADR-221's slack and is a real result.
``log10(sp)`` and the REML score are reported, never gated (ADR-221/248; the REML score
carries ADR-231's additive convention offset for non-Gaussian families).
"""

import time
from dataclasses import dataclass, field
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_dispersion import dispersion_estimates
from polaris_re.analytics.gam_model import resolve_family
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam.api import GamFit
from polaris_re.gam.formula_conformance import EXPECTED_REFUSALS, FormulaRecipe, fit_formula_case
from polaris_re.gam.summary import GamSummary

__all__ = [
    "SUMMARY_CLAIM",
    "ImpliedGates",
    "SummaryCaseComparison",
    "SummaryCaseFit",
    "SummaryPayload",
    "compare_summary_case",
    "fit_summary_case",
    "implied_gates",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
_FIXED_SCALE_TOLERANCE = 1.0e-12


class _MgcvSummaryOutputs(TypedDict):
    n: int
    scale: float
    dev_expl: float
    reml: float
    deviance: float
    null_deviance: float
    edf_s: float | list[float]
    sp: float | list[float]


class SummaryPayload(FormulaRecipe):
    """The R probe's cell: the recipe, plus ``summary.gam``'s own outputs."""

    summary: _MgcvSummaryOutputs


@dataclass(frozen=True)
class SummaryCaseFit:
    """Polaris's side of one cell."""

    name: str
    fit: GamFit | None
    summary: GamSummary | None
    seconds: float
    refusal: str | None = None


def fit_summary_case(recipe: FormulaRecipe) -> SummaryCaseFit:
    """The independent Python producer. Its signature takes :class:`FormulaRecipe` only
    (formula string, family, data), so it cannot read ``summary.gam``'s numbers."""
    start = time.perf_counter()
    case = fit_formula_case(recipe)
    seconds = time.perf_counter() - start
    if case.fit is None:
        return SummaryCaseFit(
            name=case.name, fit=None, summary=None, seconds=seconds, refusal=case.refusal
        )
    return SummaryCaseFit(name=case.name, fit=case.fit, summary=case.fit.summary(), seconds=seconds)


@dataclass(frozen=True)
class ImpliedGates:
    """What ADR-221's two gates allow each summary quantity to differ by."""

    deviance_explained: float
    """Absolute, on the 0-1 fraction."""
    scale_relative: float
    """Relative; ``0`` for a fixed-scale family (compared to ``1e-12``)."""
    per_term_edf: float
    """Absolute (ADR-221's ``edf`` gate, no tighter one has been derived)."""


def implied_gates(fit: GamFit, summary: GamSummary) -> ImpliedGates:
    """The bound ADR-221's slack implies, evaluated at Polaris's own fit (ADR-253)."""
    family = resolve_family(fit.model.family, fit.model.link)
    if fit.y is None:
        raise PolarisValidationError("implied_gates: this fit carries no training response.")
    y = fit.y
    w = np.ones_like(y) if fit.prior_weights is None else fit.prior_weights
    eta = fit.eta
    mu = family.link.linkinv(eta)
    delta = _ETA_TOLERANCE

    # deviance explained = 1 - D/D0; D0 is a function of the data alone, so the move is dD/D0.
    d_eta = -2.0 * w * (y - mu) * family.link.mu_eta(eta) / family.variance(mu)
    direction = np.sign(d_eta)
    base_dev = family.deviance(y, mu, w)
    shifts = [
        abs(family.deviance(y, family.link.linkinv(eta + sign * delta * direction), w) - base_dev)
        for sign in (1.0, -1.0)
    ]
    dev_gate = max(shifts) / summary.null_deviance if summary.null_deviance > 0 else float("nan")

    if family.dispersion_fixed:
        scale_gate = 0.0
    else:
        resid = y - mu
        v = family.variance(mu)
        d_pearson = (
            w
            * (-2.0 * resid / v - resid**2 * family.variance_prime(mu) / v**2)
            * family.link.mu_eta(eta)
        )
        sdir = np.sign(d_pearson)
        base = dispersion_estimates(y, mu, family, summary.edf_total, weights=w).fletcher
        moved = []
        for e_sign in (1.0, -1.0):
            mu_moved = family.link.linkinv(eta + e_sign * delta * sdir)
            for d_sign in (1.0, -1.0):
                moved.append(
                    dispersion_estimates(
                        y, mu_moved, family, summary.edf_total + d_sign * _EDF_TOLERANCE, weights=w
                    ).fletcher
                )
        scale_gate = max(abs(m - base) for m in moved) / abs(base)
    return ImpliedGates(
        deviance_explained=float(dev_gate),
        scale_relative=float(scale_gate),
        per_term_edf=_EDF_TOLERANCE,
    )


_CLAIM_SENTENCE = (
    "Polaris (GamFit.summary) computes deviance explained, scale, per-smooth edf and the REML "
    "score from its own Newton fit of the formula string (its own family deviance, its own "
    "offset-aware intercept-only null fit, its own Fletcher dispersion); mgcv computes them via "
    "summary.gam(gam(<same string>, method='REML')) and m$gcv.ubre; compared on those columns."
)

SUMMARY_CLAIM = VerificationClaim(
    claim=_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="deviance explained (gated by the bound ADR-221 implies, ADR-253)",
            left_producer="GamSummary.deviance_explained: family.deviance at the fitted mu over "
            "an intercept-only offset-aware null fit",
            right_producer="summary.gam(m)$dev.expl",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="scale (gated by the bound ADR-221 implies, ADR-253)",
            left_producer="GamSummary.scale: 1 for a fixed-scale family, else Fletcher "
            "dispersion at the fitted mu and edf",
            right_producer="summary.gam(m)$scale",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-smooth edf (gated at ADR-221's edf gate)",
            left_producer="GamSummary.smooths[i].edf: tr(F) over each term's columns",
            right_producer="summary.gam(m)$s.table[, 'edf']",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="REML score (reported; additive convention offset for non-Gaussian, ADR-231)",
            left_producer="GamSummary.reml_score from the Newton search",
            right_producer="mgcv m$gcv.ubre",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="deviance and null deviance (reported; components of the first row)",
            left_producer="GamSummary.deviance / null_deviance",
            right_producer="mgcv m$deviance / m$null.deviance",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per penalty (reported, never gated: ADR-221/248)",
            left_producer="GamSummary.smooths[i].log10_sp from the Newton search",
            right_producer="mgcv log10(m$sp)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="n (exact; a no-tampering check)",
            left_producer="GamSummary.n: rows of the DataFrame it was handed",
            right_producer="summary.gam(m)$n: rows of the data frame it was handed",
            provenance=ComparisonProvenance.ECHO,
        ),
    ),
)
"""Six columns INDEPENDENT, one ECHO. The headline is derived by ``evidence_markdown``."""


def _floats(value: float | list[float]) -> list[float]:
    return list(value) if isinstance(value, list) else [value]


@dataclass(frozen=True)
class SummaryCaseComparison:
    name: str
    refused: bool
    n_match: bool | None
    scale_rel_diff: float | None
    scale_gate: float | None
    dev_expl_diff: float | None
    dev_expl_gate: float | None
    max_term_edf_diff: float | None
    n_terms_match: bool | None
    reml_diff: float | None
    deviance_rel_diff: float | None
    null_deviance_rel_diff: float | None
    max_abs_log10_sp_diff: float | None
    converged: bool | None
    rel_gradient_over_epsilon: float | None
    n_iterations: int | None
    n_function_evals: int | None
    n_penalties: int | None
    seconds: float
    agrees: bool
    evidence: VerificationClaim = field(default=SUMMARY_CLAIM)


def compare_summary_case(python: SummaryCaseFit, payload: SummaryPayload) -> SummaryCaseComparison:
    """Compare ``GamFit.summary()`` with ``summary.gam`` on every declared column."""
    if python.fit is None or python.summary is None:
        return SummaryCaseComparison(
            name=python.name,
            refused=True,
            n_match=None,
            scale_rel_diff=None,
            scale_gate=None,
            dev_expl_diff=None,
            dev_expl_gate=None,
            max_term_edf_diff=None,
            n_terms_match=None,
            reml_diff=None,
            deviance_rel_diff=None,
            null_deviance_rel_diff=None,
            max_abs_log10_sp_diff=None,
            converged=None,
            rel_gradient_over_epsilon=None,
            n_iterations=None,
            n_function_evals=None,
            n_penalties=None,
            seconds=python.seconds,
            agrees=python.name in EXPECTED_REFUSALS,
        )
    s, mg = python.summary, payload["summary"]
    gates = implied_gates(python.fit, s)
    ref_edf = np.asarray(_floats(mg["edf_s"]), dtype=np.float64)
    mine_edf = np.asarray([t.edf for t in s.smooths], dtype=np.float64)
    n_terms_match = ref_edf.size == mine_edf.size
    if not n_terms_match:
        raise PolarisValidationError(
            f"compare_summary_case: {mine_edf.size} smooth terms vs {ref_edf.size} in s.table."
        )
    term_diff = float(np.max(np.abs(mine_edf - ref_edf))) if mine_edf.size else 0.0
    sp_ref = np.log10(np.asarray(_floats(mg["sp"]), dtype=np.float64))
    sp_mine = np.asarray([v for t in s.smooths for v in t.log10_sp], dtype=np.float64)
    sp_diff = float(np.max(np.abs(sp_mine - sp_ref))) if sp_mine.size == sp_ref.size else None
    if not s.scale_estimated:
        scale_diff = abs(s.scale - mg["scale"])
        scale_ok = scale_diff < _FIXED_SCALE_TOLERANCE
    else:
        scale_diff = abs(s.scale - mg["scale"]) / abs(mg["scale"])
        scale_ok = scale_diff <= gates.scale_relative
    dev_diff = abs(s.deviance_explained - mg["dev_expl"])
    rel_grad = s.rel_projected_gradient
    agrees = (
        s.n == int(mg["n"])
        and scale_ok
        and dev_diff <= gates.deviance_explained
        and term_diff < gates.per_term_edf
    )
    return SummaryCaseComparison(
        name=python.name,
        refused=False,
        n_match=s.n == int(mg["n"]),
        scale_rel_diff=float(scale_diff),
        scale_gate=gates.scale_relative,
        dev_expl_diff=float(dev_diff),
        dev_expl_gate=gates.deviance_explained,
        max_term_edf_diff=term_diff,
        n_terms_match=n_terms_match,
        reml_diff=float(s.reml_score - mg["reml"]),
        deviance_rel_diff=float(abs(s.deviance - mg["deviance"]) / abs(mg["deviance"])),
        null_deviance_rel_diff=float(
            abs(s.null_deviance - mg["null_deviance"]) / abs(mg["null_deviance"])
        ),
        max_abs_log10_sp_diff=sp_diff,
        converged=s.converged,
        rel_gradient_over_epsilon=None if rel_grad is None else rel_grad / s.epsilon_rel,
        n_iterations=s.n_iterations,
        n_function_evals=s.n_function_evals,
        n_penalties=int(python.fit.log_lambda.size),
        seconds=python.seconds,
        agrees=bool(agrees),
    )

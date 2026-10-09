"""``GamFit.summary()`` — the fit report (preview epic Slice P4, ADR-253).

Mirrors the parts of ``mgcv``'s ``summary.gam`` that the verified engine produces
independently: per-smooth ``edf``, the smoothing parameters, the scale, the REML score,
the deviance explained and ``n`` — plus the Newton search's own convergence report
(iterations, the final relative projected gradient against ``epsilon_rel = 1e-6``,
ADR-248).

**There are no p-values.** ``summary.gam``'s smooth-term tests are Wood (2013) and are
a separate method (PLAN §2, out of scope); the printed footer says so.

``deviance_explained`` follows ``mgcv``: ``(null.deviance - deviance) / null.deviance``,
the null model being the intercept-only fit **with the offset** when there is one
(:func:`null_deviance`).
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_model import PolarisGAMFit, resolve_family
from polaris_re.analytics.gam_reml_newton import MGCV_NEWTON_CONV_TOL

__all__ = [
    "EPSILON_REL",
    "GamSummary",
    "SmoothSummary",
    "build_summary",
    "null_deviance",
]

EPSILON_REL: float = MGCV_NEWTON_CONV_TOL
"""The Newton search's relative gradient tolerance (``gam.control()$newton$conv.tol``,
ADR-248), imported rather than redeclared."""


@dataclass(frozen=True)
class SmoothSummary:
    """One smooth term's row."""

    label: str
    edf: float
    log10_sp: tuple[float, ...]
    """``log10`` of each of the term's smoothing parameters (``ti`` and ``select=TRUE``
    terms carry more than one), in penalty-block order."""
    n_coef: int


@dataclass(frozen=True)
class GamSummary:
    """What :meth:`polaris_re.gam.GamFit.summary` returns. Plain data; ``str()`` prints
    the report. Field meanings follow ``summary.gam`` where it has the counterpart."""

    formula: str
    family: str
    link: str
    n: int
    n_parametric: int
    smooths: tuple[SmoothSummary, ...]
    edf_total: float
    scale: float
    scale_estimated: bool
    reml_score: float
    deviance: float
    null_deviance: float
    deviance_explained: float
    converged: bool
    outer: str
    n_iterations: int | None
    max_abs_projected_gradient: float | None
    rel_projected_gradient: float | None
    epsilon_rel: float
    n_function_evals: int
    at_bound_blocks: tuple[str, ...]

    def __str__(self) -> str:
        lines = [
            f"Family: {self.family}  Link function: {self.link}",
            f"Formula: {self.formula}",
            "",
            f"Parametric coefficients: {self.n_parametric} (intercept included)",
            "",
            "Smooth terms:",
            f"  {'term':<28}{'coef':>6}{'edf':>10}   log10(sp)",
        ]
        for s in self.smooths:
            sps = ", ".join(f"{v:.3f}" for v in s.log10_sp) or "—"
            lines.append(f"  {s.label:<28}{s.n_coef:>6}{s.edf:>10.4f}   {sps}")
        lines += [
            "",
            f"n = {self.n}   total edf = {self.edf_total:.4f}",
            f"scale est. = {self.scale:.6g}"
            + ("" if self.scale_estimated else "  (fixed by the family)"),
            f"REML score = {self.reml_score:.6f}",
            f"Deviance explained = {100.0 * self.deviance_explained:.3f}%"
            f"  (deviance {self.deviance:.6g}, null {self.null_deviance:.6g})",
        ]
        if self.rel_projected_gradient is not None:
            lines.append(
                f"Newton REML search: {self.n_iterations} iterations, "
                f"{self.n_function_evals} penalised fits, relative projected gradient "
                f"{self.rel_projected_gradient:.3e} vs epsilon_rel {self.epsilon_rel:.0e} — "
                + ("converged" if self.converged else "NOT CONVERGED")
            )
        else:
            lines.append(
                f"Outer search: {self.outer}, {self.n_function_evals} penalised fits — "
                + ("converged" if self.converged else "NOT CONVERGED")
            )
        if self.at_bound_blocks:
            lines.append(
                f"Smoothed to the null space (upper bound of the search): "
                f"{', '.join(self.at_bound_blocks)}"
            )
        lines += [
            "",
            "No p-values are reported: the smooth-term tests of summary.gam (Wood 2013) are "
            "not in the verified preview subset.",
        ]
        return "\n".join(lines)


def null_deviance(
    y: np.ndarray, family: Family, weights: np.ndarray | None, offset: np.ndarray | None
) -> float:
    """The intercept-only deviance, with the offset when there is one.

    ``mgcv`` evaluates the null model at the weighted mean when there is no offset and
    refits the intercept with the offset otherwise; both are the root ``b`` of the
    intercept score ``sum(w (y - mu) mu'/V) = 0`` at ``eta = offset + b``, which is what
    is solved here (the score is monotone in ``b``). Returns NaN when the score has no
    root (e.g. an all-zero count response).
    """
    w = np.ones_like(y) if weights is None else weights
    off = np.zeros_like(y) if offset is None else offset

    def score(b: float) -> float:
        eta = off + b
        mu = family.link.linkinv(eta)
        return float(np.sum(w * (y - mu) * family.link.mu_eta(eta) / family.variance(mu)))

    lo, hi = -1.0, 1.0
    for _ in range(60):
        if score(lo) > 0.0 > score(hi):
            break
        lo, hi = lo * 2.0, hi * 2.0
    else:
        return float("nan")
    b = brentq(score, lo, hi, xtol=1e-14, rtol=1e-14)
    mu0 = family.link.linkinv(off + b)
    return family.deviance(y, mu0, w)


def build_summary(
    fit: PolarisGAMFit, formula: str, smooth_labels: tuple[str, ...], n_parametric: int
) -> GamSummary:
    """Assemble the :class:`GamSummary` of ``fit``. ``smooth_labels`` are the smooth
    terms (the parametric block is counted as ``n_parametric`` = ``m$nsdf``, not listed,
    as in ``summary.gam``)."""
    if fit.y is None:
        raise ValueError("summary(): this fit carries no training response.")
    family = resolve_family(fit.model.family, fit.model.link)
    w = np.ones_like(fit.y) if fit.prior_weights is None else fit.prior_weights
    mu = np.asarray(family.link.linkinv(fit.eta), dtype=np.float64)
    deviance = family.deviance(fit.y, mu, w)
    null_dev = null_deviance(fit.y, family, fit.prior_weights, fit.offset)
    explained = (
        (null_dev - deviance) / null_dev
        if np.isfinite(null_dev) and null_dev > 0
        else (float("nan"))
    )
    scale = 1.0 if family.dispersion_fixed else float(fit.dispersion.fletcher)

    blocks = {b["label"]: b for b in fit.design["term_blocks"]}
    offsets = {}
    cursor = 0
    for b in fit.design["term_blocks"]:
        offsets[b["label"]] = cursor
        cursor += b["n_penalties"]
    smooths = tuple(
        SmoothSummary(
            label=label,
            edf=float(fit.edf_per_term[label]),
            log10_sp=tuple(
                float(v)
                for v in fit.log_lambda[
                    offsets[label] : offsets[label] + blocks[label]["n_penalties"]
                ]
            ),
            n_coef=int(blocks[label]["end"] - blocks[label]["start"]),
        )
        for label in smooth_labels
    )
    rel_grad = (
        None
        if fit.max_abs_projected_gradient is None
        else fit.max_abs_projected_gradient / (1.0 + abs(fit.reml_score))
    )
    return GamSummary(
        formula=formula,
        family=fit.model.family,
        link=fit.model.link,
        n=int(fit.y.size),
        n_parametric=n_parametric,
        smooths=smooths,
        edf_total=float(fit.edf_total),
        scale=scale,
        scale_estimated=not family.dispersion_fixed,
        reml_score=float(fit.reml_score),
        deviance=float(deviance),
        null_deviance=float(null_dev),
        deviance_explained=float(explained),
        converged=bool(fit.converged),
        outer="newton" if fit.n_iterations is not None else "lbfgsb",
        n_iterations=fit.n_iterations,
        max_abs_projected_gradient=fit.max_abs_projected_gradient,
        rel_projected_gradient=rel_grad,
        epsilon_rel=EPSILON_REL,
        n_function_evals=int(fit.n_function_evals),
        at_bound_blocks=fit.at_bound_blocks,
    )

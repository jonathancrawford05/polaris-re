"""Partial effects and the improvement surface from a fitted HGAM — dashboard slice D2
(``docs/PLAN_gam_dashboard.md`` §4, ADR-263).

Two read-only derived quantities of a :class:`~polaris_re.gam.GamFit`. Nothing here is a
new fitting formula and nothing feeds pricing; both are MEASUREMENTS of the fitted model
(own criterion) unless a test compares them to a closed form (``truth_recovery_claim``).

**Partial effect** of a term: ``B(grid) @ beta[block]``, the term's design block at a grid
times its own coefficients. Reference (``plot.gam``'s convention): the intercept, the
offset and every other term are excluded; a smooth term is already centred by the
sum-to-zero constraint absorbed from the TRAINING rows (so it is centred over the training
data, not over the grid). The band is ``z * se`` with ``se = sqrt(diag(B Vp_block B^T))``,
``Vp_block`` the term's own block of :meth:`GamFit.vcov` (conditional ``Vp``). A numeric
``by`` term is shown per unit of ``by`` (``by = 1``); a factor-``by`` / ``sz`` term gets one
effect per level; a factor term (``re``, ``parametric``) one value per level combination
(the reference level is 0 by construction).

**Improvement surface** ``MI_x(y) = 1 - exp(eta(x, y) - eta(x, y - step))``, the definition
the older ``TensorMIModel.improvement_surface`` documents. Every term that does not involve
the calendar-year covariate cancels in the difference exactly. The offset is set to 0 rather than
differenced, so with a `q_base` offset (`log_expected`) the surface is the year-on-year
change in the A/E multiplier on `q_base`: it equals total improvement only if `q_base` does
not itself vary by calendar year (true for a static select-and-ultimate base). The band is
the delta method on the linear contrast ``d = D beta`` with ``D = X(x, y) - X(x, y - step)``
(two rows of :func:`~polaris_re.analytics.gam_predict.predict_design`) and
``Var(d) = D Vp D^T`` — never two independent pointwise standard errors, because the
covariance between the two points is the whole point. ``MI`` is monotone decreasing in
``d``, so the band maps through ``1 - exp(d +- z se)``. Other numeric covariates sit at the
median of ``data`` and factors at their first level, which matters only for a term that
involves BOTH the year and that covariate (a ``by`` smooth of the year).
"""

import itertools
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal

import numpy as np
import polars as pl

from polaris_re.analytics.gam_predict import predict_design, predict_term_design
from polaris_re.analytics.gam_term_spec import TermSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam.api import GamFit

__all__ = [
    "ImprovementSurface",
    "PartialEffect",
    "improvement_surface",
    "partial_effects",
    "truth_recovery_claim",
]


@dataclass(frozen=True)
class PartialEffect:
    """One term's contribution on a grid (see the module docstring for the reference)."""

    label: str
    kind: Literal["curve", "surface", "levels"]
    variables: tuple[str, ...]
    axes: tuple[np.ndarray, ...]
    """Grid per axis: one for a curve, two for a surface, none for ``levels``."""
    effect: np.ndarray
    se: np.ndarray
    level_names: tuple[str, ...] = ()
    """For ``levels``: the level (combination) each entry of ``effect`` belongs to."""
    note: str = ""


@dataclass(frozen=True)
class ImprovementSurface:
    """``MI_x(y)`` on an age x year grid, with a delta-method band."""

    ages: np.ndarray
    years: np.ndarray
    mi: np.ndarray
    mi_lower: np.ndarray
    mi_upper: np.ndarray
    mi_se: np.ndarray
    """Delta-method standard error of ``MI`` (``exp(d) * se(d)``)."""
    d: np.ndarray
    d_se: np.ndarray
    level: float
    age_var: str
    year_var: str
    step: float
    reference: dict[str, str]
    """The values the other covariates were held at (stated, never silent)."""


def _numeric_array(data: pl.DataFrame, name: str) -> np.ndarray:
    if name not in data.columns:
        raise PolarisValidationError(f"effects: the data has no column {name!r}.")
    return np.asarray(data.get_column(name).cast(pl.Float64).to_numpy(), dtype=np.float64)


def _reference_columns(
    fit: GamFit, data: pl.DataFrame, n: int, skip: set[str]
) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Every column the fit reads, at a constant: numeric at the median, factors at code 0."""
    cols: dict[str, np.ndarray] = {}
    ref: dict[str, str] = {}
    for name in fit.numeric_columns:
        if name in skip:
            continue
        if name == fit.model.offset_column:
            cols[name] = np.zeros(n, dtype=np.float64)
            continue
        med = float(np.median(_numeric_array(data, name)))
        cols[name] = np.full(n, med, dtype=np.float64)
        ref[name] = f"median {med:.6g}"
    for name, levels in fit.factor_levels.items():
        if name in skip:
            continue
        cols[name] = np.zeros(n, dtype=np.int64)
        ref[name] = f"first level {levels[0]!r}"
    if fit.model.offset_column is not None and fit.model.offset_column not in cols:
        cols[fit.model.offset_column] = np.zeros(n, dtype=np.float64)
    return cols, ref


def _block(fit: GamFit, index: int) -> slice:
    tb = fit.design["term_blocks"][index]
    return slice(tb["start"], tb["end"])


def _grid(data: pl.DataFrame, name: str, points: int) -> np.ndarray:
    col = _numeric_array(data, name)
    return np.linspace(float(col.min()), float(col.max()), points)


def _effect_and_se(
    fit: GamFit, index: int, block: np.ndarray, vcov: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    sl = _block(fit, index)
    coef = fit.coef_full[sl]
    v = vcov[sl, sl]
    effect = block @ coef
    var = np.einsum("ij,jk,ik->i", block, v, block)
    return np.asarray(effect, dtype=np.float64), np.sqrt(np.clip(var, 0.0, None))


def partial_effects(fit: GamFit, data: pl.DataFrame, points: int = 50) -> list[PartialEffect]:
    """The partial effect of every term of ``fit`` (see the module docstring).

    ``data`` is the frame the fit used (read for covariate ranges and medians only).
    """
    vcov = fit.vcov()
    out: list[PartialEffect] = []
    for index, state in enumerate(fit.term_states):
        term: TermSpec = state.term
        numeric = [v for v in term.variables if v in fit.numeric_columns]
        factors = [v for v in term.variables if v in fit.factor_levels]
        if term.basis in ("re", "parametric"):
            names = [fit.factor_levels[v] for v in factors]
            combos = list(itertools.product(*[range(len(lv)) for lv in names]))
            n = len(combos)
            cols, _ = _reference_columns(fit, data, n, set(factors))
            for j, v in enumerate(factors):
                cols[v] = np.array([c[j] for c in combos], dtype=np.int64)
            block = predict_term_design(state, cols)
            eff, se = _effect_and_se(fit, index, block, vcov)
            labels = tuple(":".join(names[j][c[j]] for j in range(len(factors))) for c in combos)
            out.append(
                PartialEffect(
                    term.label,
                    "levels",
                    tuple(factors),
                    (),
                    eff,
                    se,
                    labels,
                    "reference level is 0 by construction"
                    if term.basis == "parametric"
                    else "random-effect level deviations (penalised toward 0)",
                )
            )
            continue
        smooth_vars = [v for v in numeric if v != term.by]
        if not smooth_vars:
            continue
        if len(smooth_vars) == 2:
            g1, g2 = (_grid(data, v, points) for v in smooth_vars)
            n = g1.size * g2.size
            cols, _ = _reference_columns(fit, data, n, set(smooth_vars))
            cols[smooth_vars[0]] = np.repeat(g1, g2.size)
            cols[smooth_vars[1]] = np.tile(g2, g1.size)
            block = predict_term_design(state, cols)
            eff, se = _effect_and_se(fit, index, block, vcov)
            out.append(
                PartialEffect(
                    term.label,
                    "surface",
                    tuple(smooth_vars),
                    (g1, g2),
                    eff.reshape(g1.size, g2.size),
                    se.reshape(g1.size, g2.size),
                )
            )
            continue
        grid = _grid(data, smooth_vars[0], points)
        # one curve for a plain / numeric-by / factor-by(level) term; one per level for sz
        level_codes: list[tuple[str, int | None]] = [("", None)]
        if term.basis == "sz":
            level_codes = [(lv, i) for i, lv in enumerate(fit.factor_levels[factors[0]])]
        for lvl, code in level_codes:
            n = grid.size
            cols, _ = _reference_columns(fit, data, n, {smooth_vars[0], *factors})
            cols[smooth_vars[0]] = grid
            for f in factors:
                cols[f] = np.full(
                    n, code if code is not None and f == factors[0] else (term.by_level or 0)
                ).astype(np.int64)
            if term.by is not None:
                cols[term.by] = np.ones(n, dtype=np.float64)
            block = predict_term_design(state, cols)
            eff, se = _effect_and_se(fit, index, block, vcov)
            note = "per unit of the numeric by variable" if term.by is not None else ""
            out.append(
                PartialEffect(
                    f"{term.label}[{lvl}]" if lvl else term.label,
                    "curve",
                    tuple(smooth_vars),
                    (grid,),
                    eff,
                    se,
                    note=note,
                )
            )
    return out


def improvement_surface(
    fit: GamFit,
    data: pl.DataFrame,
    *,
    age_var: str = "attained_age",
    year_var: str = "calendar_year",
    ages: np.ndarray | None = None,
    years: np.ndarray | None = None,
    step: float = 1.0,
    level: float = 0.95,
    unconditional: bool = False,
) -> ImprovementSurface:
    """``MI_x(y) = 1 - exp(eta(x, y) - eta(x, y - step))`` with a delta-method band.

    ``years`` are the ``y`` values reported (default: the data's years from ``min + step``,
    so ``y - step`` is inside the observed range). Refused, with the standard message, when
    the fitted formula has no smooth of ``year_var``.
    """
    if not 0.0 < level < 1.0:
        raise PolarisValidationError(f"improvement_surface: level must be in (0, 1), got {level}.")
    if not any(year_var in s.term.variables for s in fit.term_states):
        raise PolarisValidationError(
            f"improvement_surface: the fitted formula has no smooth term of {year_var!r}, so "
            "there is no improvement to read (MI is the year-on-year change in eta). Add e.g. "
            f's({year_var}, bs="cr", k=5) and ti({age_var}, {year_var}, bs="cr") to the formula.'
        )
    if age_var not in fit.numeric_columns or year_var not in fit.numeric_columns:
        raise PolarisValidationError(
            f"improvement_surface: {age_var!r} and {year_var!r} must both be numeric covariates "
            f"of the fit (it reads {list(fit.numeric_columns)})."
        )
    age_col = _numeric_array(data, age_var)
    year_col = _numeric_array(data, year_var)
    a = np.unique(age_col) if ages is None else np.asarray(ages, dtype=np.float64)
    if years is None:
        y = np.arange(float(year_col.min()) + step, float(year_col.max()) + 1e-9, step)
    else:
        y = np.asarray(years, dtype=np.float64)
    if a.size == 0 or y.size == 0:
        raise PolarisValidationError("improvement_surface: empty age or year grid.")
    n = a.size * y.size
    aa = np.repeat(a, y.size)
    yy = np.tile(y, a.size)
    cols, ref = _reference_columns(fit, data, n, {age_var, year_var})
    hi = {**cols, age_var: aa, year_var: yy}
    lo = {**cols, age_var: aa, year_var: yy - step}
    d_mat = predict_design(fit.model, fit.term_states, hi) - predict_design(
        fit.model, fit.term_states, lo
    )
    coef = fit.coef_full
    vcov = fit.vcov(unconditional=unconditional)
    d = d_mat @ coef
    var = np.einsum("ij,jk,ik->i", d_mat, vcov, d_mat)
    d_se = np.sqrt(np.clip(var, 0.0, None))
    z = NormalDist().inv_cdf(0.5 + level / 2.0)
    mi = 1.0 - np.exp(d)
    shape = (a.size, y.size)
    return ImprovementSurface(
        ages=a,
        years=y,
        mi=mi.reshape(shape),
        mi_lower=(1.0 - np.exp(d + z * d_se)).reshape(shape),
        mi_upper=(1.0 - np.exp(d - z * d_se)).reshape(shape),
        mi_se=(np.exp(d) * d_se).reshape(shape),
        d=d.reshape(shape),
        d_se=d_se.reshape(shape),
        level=level,
        age_var=age_var,
        year_var=year_var,
        step=step,
        reference=ref,
    )


def truth_recovery_claim() -> VerificationClaim:
    """The declared provenance of the D2 truth-recovery check (ADR-193, ADR-263).

    A comparison against a CLOSED FORM, not ``mgcv`` parity: the two producers are the
    generating formula of the synthetic data and the fitted HGAM."""
    return VerificationClaim(
        claim=(
            "The data generator computes MI_x(y) from its closed-form improvement law; "
            "improvement_surface computes MI_x(y) from the HGAM fitted to a draw of that data; "
            "compared on MI at each (age, year) cell and on band coverage. Closed-form truth "
            "recovery, not mgcv parity."
        ),
        quantities=(
            ComparedQuantity(
                quantity="mi_age_year",
                left_producer="test generator closed form 1 - exp(-(b0 + b1 (age - 40)))",
                right_producer="polaris_re.gam.effects.improvement_surface on gam()/bam fit",
                provenance=ComparisonProvenance.INDEPENDENT,
            ),
            ComparedQuantity(
                quantity="band_coverage",
                left_producer="test generator closed form (truth inside or outside)",
                right_producer="improvement_surface delta-method band D Vp D^T",
                provenance=ComparisonProvenance.INDEPENDENT,
            ),
        ),
    )

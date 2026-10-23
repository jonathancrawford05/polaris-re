"""A measured cost model for ``gam()`` / ``bam`` fits — dashboard slice D1 (ADR-262).

The experience-improvement page warns BEFORE a fit runs: expected runtime and memory for the
chosen engine and input size. The numbers come from two committed measurement tables, never a
guess (``docs/PLAN_gam_dashboard.md`` §3 decisions 4-5, §5 rule 5):

* ``gam`` (exact REML) seconds: the 15 fitted cells of the R2 ILEC trial
  (``docs/measurements/gam_real_data_trial_2026-10-15.json``), regressed as
  ``log t = a + b log(n_rows) + c log(n_coef)``.
* ``bam`` seconds and peak RSS: the nine real-data cells of ADR-260 amendments 15-16, regressed
  as ``log t = a + b log(n_rows)`` and ``GB = a + b n_rows``.

Every number is **MEASUREMENT (own criterion)**: Polaris against itself on one machine
(Apple M4, 4P+6E cores, 24 GB, macOS, 1 thread). It is not parity evidence and compares nothing
with ``mgcv``. Off that machine the stated band is too narrow, and the model says so
(:attr:`CostEstimate.notes`); outside the measured range of ``n_rows`` or ``n_coef`` it refuses to
extrapolate silently (``extrapolated`` is True and the warning says so).

``gam`` peak memory is NOT modelled: the R2 JSON's ``peak_rss_mb`` is the high-water mark of a
long-lived process (it never decreases across the cells that process fitted), so per cell it is
only an upper bound. The model reports that bound; the memory the page can state is the
``bam`` model and the synthetic ``gam`` measurement in
``docs/measurements/gam_dashboard_memory_*.json``.
"""

import math
from dataclasses import dataclass, field
from typing import Final, Literal

import numpy as np
import polars as pl

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam.formula import SmoothCall, TensorCall, parse_formula

__all__ = [
    "BAM_DEFAULT_THRESHOLD_ROWS",
    "BAM_MEASURED",
    "GAM_MEASURED",
    "CostEstimate",
    "CostModel",
    "PreRunWarning",
    "bam_refusal",
    "default_engine",
    "dense_design_floor_gb",
    "estimate_n_coef",
    "fit_cost_model",
    "physical_memory_gb",
    "pre_run_warning",
]

type Engine = Literal["gam", "bam"]

BAM_DEFAULT_THRESHOLD_ROWS: Final = 300_000
"""Maintainer decision 2026-10-21 (PLAN §3.3): default ``gam`` at or below, ``bam`` above."""

GAM_MEMORY_FLOOR_MULTIPLIER: Final = 12.0
"""ASSUMPTION for the RAM block only: peak RSS over the dense-design floor. The synthetic sweep
(``docs/measurements/gam_dashboard_memory_2026-10-22.json``) gives 11.1x at 10k rows and 5.6x at
40k (above the import baseline; 39x at 2k is dominated by fixed overhead); 12 is the larger of
the n >= 10k ratios, rounded up. Off-range and off-machine: stated in the warning text."""

GAM_R2_RSS_UPPER_BOUND_GB: Final = 10.2
"""R2 JSON ``polaris.peak_rss_mb`` maximum over fitted cells (10,434 MB): a process high-water
mark, an upper bound per cell, not attributable."""

MACHINE: Final = "Apple M4 (4P+6E), 24 GB RAM, macOS, OPENBLAS_NUM_THREADS=1 (maintainer's MacBook)"

# (cell, n_rows, n_coef, best-of-repeats fit seconds): the R2 trial, every `fitted` cell.
GAM_MEASURED: Final[tuple[tuple[str, int, int, float], ...]] = (
    ("S2 coarse", 342_271, 122, 115.877),
    ("S2 mid", 648_372, 122, 208.559),
    ("S3 coarse", 471_987, 152, 215.120),
    ("S3 mid", 886_189, 152, 486.443),
    ("T1 coarse", 19_182, 78, 3.723),
    ("T1 full", 413_776, 78, 57.359),
    ("T1 mid", 109_158, 78, 14.084),
    ("T2 coarse", 471_987, 110, 144.174),
    ("T2 mid", 886_189, 110, 256.994),
    ("T3a coarse", 471_987, 145, 275.425),
    ("T3a mid", 886_189, 145, 473.471),
    ("T3b coarse", 471_987, 146, 379.459),
    ("T3b mid", 886_189, 146, 841.362),
    ("T3c coarse", 471_987, 74, 127.799),
    ("T3c mid", 886_189, 74, 176.530),
)
"""``tests/test_gam/test_cost_model.py`` asserts this table equals the committed JSON."""

# (cell, n_rows, fit seconds, peak RSS GB): ADR-260 amendment 15's table (S1_mid: amendment 16),
# real ILEC cells, tier L. Guarded by tests/test_gam/test_cost_model.py against docs/DECISIONS.md.
BAM_MEASURED: Final[tuple[tuple[str, int, float, float], ...]] = (
    ("T1_mid", 109_158, 0.28, 0.5),
    ("T1_full", 413_776, 1.1, 1.6),
    ("S2_mid", 648_372, 3.4, 3.8),
    ("T2_mid", 886_189, 3.5, 4.1),
    ("T3c_mid", 886_189, 3.1, 3.5),
    ("T3a_mid", 886_189, 7.7, 5.3),
    ("S1_mid", 886_189, 3.9, 4.5),
    ("T3c_full", 3_015_224, 11.1, 8.0),
    ("T2_full", 3_015_224, 16.6, 8.3),
)


@dataclass(frozen=True)
class CostEstimate:
    """A pre-run estimate for one engine, input size and model width."""

    engine: Engine
    n_rows: int
    n_coef: int
    seconds: float
    seconds_low: float
    seconds_high: float
    memory_gb: float | None
    """``bam``: the linear model of peak RSS. ``gam``: ``None`` (not modelled, see the module
    docstring)."""
    memory_upper_bound_gb: float | None
    extrapolated: bool
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CostModel:
    """Fitted coefficients plus the leave-one-out evidence that bounds them."""

    gam_coef: tuple[float, float, float]
    """``(a, b, c)`` of ``log t = a + b log n + c log p``."""
    gam_band: float
    """The largest leave-one-out factor (over- or under-prediction) of the ``gam`` model."""
    gam_loo_within_3x: float
    bam_time_coef: tuple[float, float]
    bam_band: float
    bam_mem_coef: tuple[float, float]
    """``(a, b)`` of ``GB = a + b n``."""
    bam_mem_band_gb: float
    """The largest leave-one-out absolute error of the memory line, GB."""
    gam_range_n: tuple[int, int]
    gam_range_p: tuple[int, int]
    bam_range_n: tuple[int, int]

    def estimate(
        self,
        engine: Engine,
        n_rows: int,
        n_coef: int,
        *,
        gam_peak_rss_upper_bound_gb: float | None = None,
    ) -> CostEstimate:
        """The estimate with its band; flags extrapolation beyond the measured range."""
        if n_rows < 1 or n_coef < 1:
            raise PolarisValidationError("CostModel.estimate(): n_rows and n_coef must be >= 1.")
        notes = [f"Measured on {MACHINE}; a different machine moves every figure."]
        if engine == "gam":
            a, b, c = self.gam_coef
            sec = math.exp(a + b * math.log(n_rows) + c * math.log(n_coef))
            band = self.gam_band
            lo_n, hi_n = self.gam_range_n
            lo_p, hi_p = self.gam_range_p
            extrapolated = not (lo_n <= n_rows <= hi_n and lo_p <= n_coef <= hi_p)
            if extrapolated:
                notes.append(
                    f"Outside the measured range (rows {lo_n:,}-{hi_n:,}, coefficients "
                    f"{lo_p}-{hi_p}): extrapolated, the band below is NOT valid there."
                )
            return CostEstimate(
                "gam",
                n_rows,
                n_coef,
                sec,
                sec / band,
                sec * band,
                None,
                gam_peak_rss_upper_bound_gb,
                extrapolated,
                tuple(notes),
            )
        a2, b2 = self.bam_time_coef
        sec = math.exp(a2 + b2 * math.log(n_rows))
        ma, mb = self.bam_mem_coef
        mem = max(ma + mb * n_rows, 0.0)
        lo_n, hi_n = self.bam_range_n
        extrapolated = not (lo_n <= n_rows <= hi_n)
        if extrapolated:
            notes.append(
                f"Outside the measured range ({lo_n:,}-{hi_n:,} rows): extrapolated, the band "
                "below is NOT valid there."
            )
        return CostEstimate(
            "bam",
            n_rows,
            n_coef,
            sec,
            sec / self.bam_band,
            sec * self.bam_band,
            mem,
            None,
            extrapolated,
            tuple(notes),
        )


def _ols(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.asarray(np.linalg.lstsq(x, y, rcond=None)[0], dtype=np.float64)


def fit_cost_model(
    gam_measured: tuple[tuple[str, int, int, float], ...] = GAM_MEASURED,
    bam_measured: tuple[tuple[str, int, float, float], ...] = BAM_MEASURED,
) -> CostModel:
    """Fit the model on the measured tables and attach the leave-one-out evidence."""
    n = np.array([r[1] for r in gam_measured], dtype=np.float64)
    p = np.array([r[2] for r in gam_measured], dtype=np.float64)
    t = np.array([r[3] for r in gam_measured], dtype=np.float64)
    x = np.column_stack([np.ones_like(n), np.log(n), np.log(p)])
    y = np.log(t)
    coef = _ols(x, y)
    ratios = []
    for i in range(len(t)):
        keep = np.arange(len(t)) != i
        c = _ols(x[keep], y[keep])
        ratios.append(math.exp(float(x[i] @ c - y[i])))
    ratios_a = np.asarray(ratios)
    factor = np.maximum(ratios_a, 1.0 / ratios_a)
    gam_band = float(factor.max())
    within3 = float(np.mean(factor < 3.0))

    bn = np.array([r[1] for r in bam_measured], dtype=np.float64)
    bt = np.array([r[2] for r in bam_measured], dtype=np.float64)
    bm = np.array([r[3] for r in bam_measured], dtype=np.float64)
    xt = np.column_stack([np.ones_like(bn), np.log(bn)])
    tc = _ols(xt, np.log(bt))
    xm = np.column_stack([np.ones_like(bn), bn])
    mc = _ols(xm, bm)
    t_fac, m_err = [], []
    for i in range(len(bn)):
        keep = np.arange(len(bn)) != i
        ct = _ols(xt[keep], np.log(bt[keep]))
        r = math.exp(float(xt[i] @ ct - np.log(bt[i])))
        t_fac.append(max(r, 1.0 / r))
        cm = _ols(xm[keep], bm[keep])
        m_err.append(abs(float(xm[i] @ cm - bm[i])))
    return CostModel(
        gam_coef=(float(coef[0]), float(coef[1]), float(coef[2])),
        gam_band=gam_band,
        gam_loo_within_3x=within3,
        bam_time_coef=(float(tc[0]), float(tc[1])),
        bam_band=float(max(t_fac)),
        bam_mem_coef=(float(mc[0]), float(mc[1])),
        bam_mem_band_gb=float(max(m_err)),
        gam_range_n=(int(n.min()), int(n.max())),
        gam_range_p=(int(p.min()), int(p.max())),
        bam_range_n=(int(bn.min()), int(bn.max())),
    )


def default_engine(n_rows: int) -> Engine:
    """``gam`` at or below :data:`BAM_DEFAULT_THRESHOLD_ROWS` rows, ``bam`` above (PLAN §3.3)."""
    return "gam" if n_rows <= BAM_DEFAULT_THRESHOLD_ROWS else "bam"


def bam_refusal(formula: str, family: str) -> str | None:
    """Why ``bam`` cannot fit this request, else ``None``; the page states it, never falls back.

    Mirrors the refusals of ``fit_polaris_bam`` (ADR-260 amendment 2, ADR-261) so the warning
    precedes the click rather than following it.
    """
    base = family.split("(")[0].strip()
    if base not in ("poisson", "binomial"):
        return (
            f"bam supports poisson and binomial only; family {family!r} needs the gam engine "
            "(ADR-260 amendment 2). Nothing is substituted."
        )
    parsed = parse_formula(formula)
    for term in parsed.terms:
        if isinstance(term, SmoothCall) and term.basis == "tp":
            return (
                'bam refuses thin-plate (tp) terms, including a bare s(x): write bs="cr" '
                "(ADR-261). Nothing is substituted."
            )
    return None


def estimate_n_coef(formula: str, data: pl.DataFrame) -> int:
    """The coefficient count the formula implies on ``data`` (intercept included).

    Only as exact as a cost model needs: ``s(x, k)`` is ``k - 1``; a factor-``by`` smooth is
    ``levels * (k - 1)``; a numeric ``by`` is ``k``; ``ti`` is ``prod(k_i - 1)``;
    ``s(f, bs="re")`` is the number of levels; a factor adds ``levels - 1`` and an interaction
    the product. The test compares it with ``len(fit.coef)`` on synthetic fits.
    """
    parsed = parse_formula(formula)
    total = 1
    for term in parsed.terms:
        if isinstance(term, SmoothCall):
            k = term.k if term.k is not None else 10
            if term.basis == "re":
                total += _levels(data, term.variable)
            elif term.by is not None and _is_factor(data, term.by):
                total += _levels(data, term.by) * (k - 1)
            elif term.by is not None:
                total += k
            else:
                total += k - 1
        elif isinstance(term, TensorCall):
            total += int(np.prod([kk - 1 for kk in term.k]))
        else:
            cols = 1
            for name in term.variables:
                if _is_factor(data, name):
                    cols *= max(_levels(data, name) - 1, 1)
            total += cols
    return max(total, 1)


def _is_factor(data: pl.DataFrame, name: str) -> bool:
    if name not in data.columns:
        raise PolarisValidationError(f"estimate_n_coef(): the data has no column {name!r}.")
    dtype = data.schema[name]
    return dtype in (pl.String, pl.Categorical) or isinstance(dtype, pl.Enum)


def _levels(data: pl.DataFrame, name: str) -> int:
    if name not in data.columns:
        raise PolarisValidationError(f"estimate_n_coef(): the data has no column {name!r}.")
    return int(data.get_column(name).n_unique())


def dense_design_floor_gb(n_rows: int, n_coef: int) -> float:
    """The dense ``n x p`` float64 design alone, in GB: a DERIVED floor, not a measurement.

    Real peak memory is several times this (assembly temporaries); it is the one ``gam``
    memory figure that does not depend on a machine.
    """
    return n_rows * n_coef * 8.0 / 1e9


@dataclass(frozen=True)
class PreRunWarning:
    """What the page shows before a fit: a severity and the lines, one per fact."""

    level: Literal["info", "warning", "error"]
    lines: tuple[str, ...]
    blocked: bool
    """True when the request cannot run as selected (``bam`` refusal) or does not fit in
    memory; the page then asks for an explicit override rather than attempting it."""


def pre_run_warning(
    model: CostModel,
    engine: Engine,
    n_rows: int,
    n_coef: int,
    *,
    formula: str,
    family: str,
    available_gb: float | None,
) -> PreRunWarning:
    """The mandatory pre-run warning (PLAN §3 decisions 4-6) for an engine and input size."""
    lines: list[str] = []
    level: Literal["info", "warning", "error"] = "info"
    blocked = False
    if engine == "bam":
        reason = bam_refusal(formula, family)
        if reason is not None:
            return PreRunWarning("error", (reason,), True)
        lines.append(
            "bam (fREML, discrete=TRUE): its smoothing parameters come from a different "
            "algorithm than gam's (a performance iteration), so edf and log10(sp) differ from "
            "gam's by design. summary() and the REML score are not available on this path."
        )
    else:
        lines.append("gam: exact Laplace REML (the verified default).")
    est = model.estimate(engine, n_rows, n_coef)
    lines.append(
        f"Expected runtime ~{_fmt_s(est.seconds)} (band {_fmt_s(est.seconds_low)} to "
        f"{_fmt_s(est.seconds_high)}) for {n_rows:,} rows and ~{n_coef} coefficients."
    )
    floor = dense_design_floor_gb(n_rows, n_coef)
    if est.memory_gb is not None:
        lines.append(
            f"Expected peak memory ~{est.memory_gb:.1f} GB (+/- {model.bam_mem_band_gb:.1f} GB)."
        )
        need = est.memory_gb + model.bam_mem_band_gb
    else:
        lines.append(
            f"Peak memory for gam is NOT modelled. The dense design alone needs {floor:.2f} GB; "
            f"the real peak is several times that (R2 gam fits of 0.3M-0.9M rows reached "
            f"{GAM_R2_RSS_UPPER_BOUND_GB:.1f} GB as a process high-water mark, an upper bound). "
            f"The block check ASSUMES {GAM_MEMORY_FLOOR_MULTIPLIER:.0f}x the floor "
            f"(~{floor * GAM_MEMORY_FLOOR_MULTIPLIER:.1f} GB); that multiplier is the largest "
            "above-baseline peak/floor ratio of the synthetic sweep at 10k rows or more, on a "
            "different machine and at 18 coefficients, not a fitted model."
        )
        need = floor * GAM_MEMORY_FLOOR_MULTIPLIER
    lines.extend(est.notes)
    if est.seconds_high > 600.0:
        level = "warning"
        lines.append(
            "This may exceed 10 minutes (the R2 gam fits of 0.9M rows took 177-841 s). "
            "The run is explicit and blocks the page until it finishes."
        )
    if available_gb is not None and need > 0.8 * available_gb:
        level, blocked = "error", True
        lines.append(
            f"This machine has {available_gb:.1f} GB; the request needs about {need:.1f} GB. "
            "It will probably be killed and may take the dashboard down."
        )
    if est.extrapolated and level == "info":
        level = "warning"
    return PreRunWarning(level, tuple(lines), blocked)


def _fmt_s(sec: float) -> str:
    if sec < 90:
        return f"{sec:.1f} s"
    return f"{sec / 60:.1f} min"


def physical_memory_gb() -> float | None:
    """Physical RAM of this machine in GB, or ``None`` when the platform cannot say."""
    import os

    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError, AttributeError):
        return None

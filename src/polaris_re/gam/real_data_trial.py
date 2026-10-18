"""The ILEC trial for the ``mgcv``-parity GAM fitter — Slice R2 of
``docs/PLAN_gam_real_data_readiness.md`` (ADR-259).

This module is the *routine half* of a maintainer-run slice (PLAN §3): everything that can be
written and tested on synthetic cells without the licensed data. The maintainer's machine runs
``scripts/gam_real_data_trial.py`` (following ``docs/RUNBOOK_gam_real_data_trial.md``) and gets
ONE JSON file of derived scalars.

Claim sentence (ADR-193), written before the code: *Polaris (``gam()``) fits the trial formula
from the ILEC-derived cell columns; ``mgcv`` (pinned digest, ``gam(method="REML")``) fits the same
string on the same columns; compared on ``eta``, ``edf_total``, per-smooth edf, the ``Vp``
``se.fit``, ``log10(sp)``, the REML score and the scale.* Neither fit function takes the other's
output (:func:`fit_polaris` reads cells and a formula; the R companion reads cells and a spec;
:func:`compare` is the only function that sees both and it produces neither).

Provenance, per column (also :data:`CLAIM`):

- ``eta``, ``edf_total``, per-smooth edf, ``se.fit``, scale, REML score, ``log10(sp)``:
  INDEPENDENT. The shared inputs (cells, offset, weights, factor level order) are the recipe, not
  a compared quantity.
- ``max |d eta| / se.fit_mgcv``: INDEPENDENT numerator; the denominator is ``mgcv``'s own
  ``se.fit`` (a unit of measurement, not a second compared quantity).
- Wall times, peak memory, iteration counts, phase split: MEASUREMENT of each engine against
  itself. Their ratio is a timing reading, never agreement.

**The derived-scalars-only contract (PLAN §3, ADR-257 decision 3).** A committed result carries
only the keys in :data:`OUTPUT_KEYS`. :func:`assert_derived_scalars_only` is the enforcement:
it rejects any other key, any string value that is not on a fixed vocabulary, any container of
numbers longer than :data:`MAX_SEQUENCE`, and any non-finite-or-non-scalar leaf. No row, cell key,
level name, level count, exposure, death count, rate, A/E, fitted curve, coefficient or contrast
can pass it.
"""

import cProfile
import json
import math
import platform
import pstats
import re
import resource
import sys
import time
import warnings
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam import COUNT_MEASURES
from polaris_re.analytics.gam_model import resolve_family
from polaris_re.analytics.gam_predict_conformance import _SE_REL_TOLERANCE
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam.api import GamFit, gam
from polaris_re.gam.summary import SmoothSummary

__all__ = [
    "CLAIM",
    "EDF_GATE",
    "ETA_GATE",
    "FORMULAS",
    "GRANULARITIES",
    "OUTPUT_KEYS",
    "SCALED_ETA_FLAG",
    "SCALED_ETA_GATE",
    "SE_REL_GATE",
    "TrialFormula",
    "aggregate_cells",
    "assert_data_rules",
    "assert_derived_scalars_only",
    "clean",
    "compare",
    "dumps",
    "fit_polaris",
    "floor_trials_at_deaths",
    "machine_description",
    "required_columns",
    "sanitise_refusal",
    "term_kind",
    "terms_block",
    "to_factor_frame",
    "trial_frame",
]

# --- the gates (imported or fixed BEFORE the first real run; none is edited afterwards) ------

ETA_GATE: Final = _AGREEMENT_TOLERANCE_ETA
"""ADR-221 ``eta`` gate (``2e-2``), imported, never redeclared (Anchor W5)."""
EDF_GATE: Final = _AGREEMENT_TOLERANCE_EDF
"""ADR-221 ``|edf_total|`` gate (``1``), imported."""
SE_REL_GATE: Final = _SE_REL_TOLERANCE
"""ADR-250 relative ``Vp`` ``se.fit`` gate (``2e-2``), imported."""
SCALED_ETA_GATE: Final = 0.1
"""PLAN §2 / Q-R2e: ``max |eta_P - eta_mgcv| / se.fit_mgcv <= 0.1`` — fixed by the maintainer
(2026-10-10) before R2 runs; never relaxed to pass another gate."""
SCALED_ETA_FLAG: Final = 0.01
"""Any reading above this is FLAGGED for investigation (a flag, not a failure; Q-R2e)."""

GRANULARITIES: Final[tuple[str, ...]] = ("coarse", "mid", "full")
"""Cell-key sets, PLAN R2. ``coarse``: ``attained_age x calendar_year``; ``mid``: coarse plus
``duration, sex, smoker``; ``full``: the committed banded run's keys (``attained_age,
calendar_year, duration, sex, smoker, uw_class``). Each is UNIONED with the variables the formula
needs (``face_band`` for T2/T3, ``issue_year`` inputs for S3), because a cell fit that lacks a
formula variable cannot be fitted at all (Q-R2g records this reading)."""

_GRANULARITY_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "coarse": ("attained_age", "calendar_year"),
    "mid": ("attained_age", "calendar_year", "duration_months", "sex", "smoker"),
    "full": ("attained_age", "calendar_year", "duration_months", "sex", "smoker", "uw_class"),
}

DURATION_CAP: Final = 26
"""Policy years from this value up are one level of the numeric ``duration`` (maintainer,
2026-10-11: all integer durations to a ceiling of 26, as a numeric covariate; not banded)."""

EXPOSURE: Final = COUNT_MEASURES[0]
DEATHS: Final = COUNT_MEASURES[1]


# --- the trial formulas (PLAN R2, maintainer-approved 2026-10-10) ----------------------------

_T1_SMOOTH = (
    's(attained_age, bs="cr", k=13) + s(duration, bs="cr", k=6) '
    '+ ti(attained_age, duration, bs="cr", k=c(13, 6))'
)
_T2_BLOCK = "face_band + smoker + face_band:smoker"
_OFFSET = "offset(log_exposure)"
_BY = 's(attained_age, bs="cr", k=13, by=smoker)'


@dataclass(frozen=True)
class TrialFormula:
    """One trial fit: a formula string and everything both engines need to fit it."""

    name: str
    formula: str
    family: str = "poisson"
    select: bool = False
    weights: str | None = None
    role: str = "main"
    """``main`` (T1-T3: the 1.5 wall-time trigger applies at ``full``), ``sensitivity``
    (S1-S3: reported only), or ``candidate`` (a formula the maintainer has not approved;
    reported separately and never read as the approved T3)."""
    drop_unknown_smoker: bool = False
    """S2: drop the ``U`` smoker level before aggregating."""
    allow_unverified_select: bool = False
    """T3b: skip the ADR-258 refusal to MEASURE the limitation on real data."""
    needs_issue_year: bool = False
    """S3: needs ``issue_year = calendar_year - duration + 1`` (derived, no loader change)."""

    def variables(self) -> frozenset[str]:
        """Column names the formula reads (everything identifier-like that is a cell column)."""
        known = {
            "attained_age",
            "duration",
            "face_band",
            "smoker",
            "log_exposure",
            "issue_year",
            "deaths",
            "death_rate",
            "exposure",
        }
        return frozenset(
            t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", self.formula) if t in known
        )


FORMULAS: Final[tuple[TrialFormula, ...]] = (
    TrialFormula("T1", f"deaths ~ {_T1_SMOOTH} + {_OFFSET}"),
    TrialFormula("T2", f"deaths ~ {_T1_SMOOTH} + {_T2_BLOCK} + {_OFFSET}"),
    TrialFormula(
        "T3a",
        f"deaths ~ {_T1_SMOOTH} + {_T2_BLOCK} + {_BY} + {_OFFSET}",
        select=False,
    ),
    TrialFormula(
        "T3b",
        f"deaths ~ {_T1_SMOOTH} + {_T2_BLOCK} + {_BY} + {_OFFSET}",
        select=True,
        allow_unverified_select=True,
        role="candidate",
    ),
    TrialFormula(
        "T3c",
        f'deaths ~ s(duration, bs="cr", k=6) + {_T2_BLOCK} + {_BY} + {_OFFSET}',
        select=True,
        role="candidate",
    ),
    TrialFormula(
        "S1",
        f"death_rate ~ {_T1_SMOOTH} + {_T2_BLOCK}",
        family='binomial(link="cloglog")',
        weights="exposure",
        role="sensitivity",
    ),
    TrialFormula(
        "S2",
        f"deaths ~ {_T1_SMOOTH} + {_T2_BLOCK} + {_BY} + {_OFFSET}",
        select=False,
        role="sensitivity",
        drop_unknown_smoker=True,
    ),
    TrialFormula(
        "S3",
        f'deaths ~ {_T1_SMOOTH} + {_T2_BLOCK} + {_BY} + s(issue_year, bs="cr", k=8) + {_OFFSET}',
        select=False,
        role="sensitivity",
        needs_issue_year=True,
    ),
)
"""The PLAN's T3 (`T1 smooths + T2 block + s(attained_age, by=smoker)`, `select=TRUE`) holds a plain
`s(attained_age)` and a `ti` over age beside the factor-`by` smooth, which `gam()` refuses under
`select=TRUE` (ADR-258; the refusal is about the smooth structure, not the basis syntax). The
maintainer (2026-10-11) asked for ALL THREE routes, to learn from the contrast: **T3a** the same
formula with `select=FALSE` (a pivoted fit, Slice 9); **T3b** the same formula with `select=TRUE`
and the refusal skipped by `allow_unverified_select` (measures the limitation on real data); **T3c**
the allowlisted shape without the plain age smooth and the `ti`. S2 and S3 are built on T3a."""


def required_columns(formula: TrialFormula, granularity: str) -> tuple[str, ...]:
    """The cell-key columns a (formula, granularity) fit aggregates to."""
    if granularity not in _GRANULARITY_KEYS:
        raise PolarisValidationError(
            f"unknown granularity {granularity!r}; expected one of {GRANULARITIES}"
        )
    keys = list(_GRANULARITY_KEYS[granularity])
    extra = ["attained_age"]
    v = formula.variables()
    if "duration" in v or formula.needs_issue_year:
        extra.append("duration_months")
    if "smoker" in v:
        extra.append("smoker")
    if "face_band" in v:
        extra.append("band")
    if formula.needs_issue_year:
        extra.append("calendar_year")
    for c in extra:
        if c not in keys:
            keys.append(c)
    return tuple(keys)


# --- the data rules the runbook pins (PLAN R2) -------------------------------------------------

SMOKER_LEVELS: Final[frozenset[str]] = frozenset({"NS", "S", "U"})


def assert_data_rules(cells: pl.DataFrame) -> None:
    """Assert the PLAN R2 data rules on loader cells BEFORE banding.

    1. ``Attained_Age = Issue_Age + Duration - 1`` (loader: ``duration_months = (d-1)*12``).
    2. Smoker labels are the loader's canonical ``NS``/``S``/``U``.
    3. Zero-exposure cells hold zero deaths (the drop itself is :func:`trial_frame`).

    A failure is a stop-and-report condition; the message carries counts only.
    """
    if {"issue_age", "duration_months", "attained_age"} <= set(cells.columns):
        bad = cells.filter(
            pl.col("attained_age") != pl.col("issue_age") + pl.col("duration_months") // 12
        ).height
        if bad:
            raise PolarisValidationError(
                f"data rule 1 failed on {bad} cells: attained_age != issue_age + duration - 1"
            )
    if "smoker" in cells.columns:
        extra = set(cells["smoker"].unique().to_list()) - SMOKER_LEVELS
        if extra:
            raise PolarisValidationError(
                f"data rule 2 failed: {len(extra)} smoker label(s) outside NS/S/U"
            )
    zero = cells.filter(pl.col(EXPOSURE) <= 0.0)
    if zero.height and float(zero[DEATHS].sum()) != 0.0:
        raise PolarisValidationError("data rule 3 failed: zero-exposure cells hold deaths")


# --- cells -------------------------------------------------------------------------------------


def aggregate_cells(
    cells: pl.DataFrame,
    formula: TrialFormula,
    granularity: str,
    *,
    duration_cap: int = DURATION_CAP,
) -> pl.DataFrame:
    """Collapse loader cells to the fit's key set, adding the derived model columns.

    Collapsing rows to cells is lossless for Poisson counts with an exposure offset (PLAN R2).
    ``duration`` is the numeric policy year, every integer value kept and capped at
    :data:`DURATION_CAP` (maintainer, 2026-10-11): no banding.
    """
    keys = list(required_columns(formula, granularity))
    frame = cells
    if formula.drop_unknown_smoker:
        frame = frame.filter(pl.col("smoker") != "U")
    frame = frame.with_columns(pl.col("duration_months").clip(upper_bound=(duration_cap - 1) * 12))
    grouped = frame.group_by(keys).agg(pl.col(EXPOSURE).sum(), pl.col(DEATHS).sum())
    return trial_frame(grouped.sort(keys))


def trial_frame(cells: pl.DataFrame) -> pl.DataFrame:
    """Add the model columns (``exposure``, ``deaths``, ``log_exposure``, ``death_rate``,
    ``duration``, ``face_band``, ``issue_year``) to aggregated cells, dropping zero exposure.

    Zero-exposure cells are dropped only after asserting they hold zero deaths (PLAN R2 data
    rules). Raises :class:`PolarisValidationError` otherwise — a stop-and-report condition.
    """
    zero = cells.filter(pl.col(EXPOSURE) <= 0.0)
    if zero.height and float(zero[DEATHS].sum()) != 0.0:
        raise PolarisValidationError(
            "zero-exposure cells hold deaths; this violates the data rules (stop and report)."
        )
    out = cells.filter(pl.col(EXPOSURE) > 0.0).with_columns(
        pl.col(EXPOSURE).alias("exposure"),
        pl.col(DEATHS).cast(pl.Float64).alias("deaths"),
        pl.col(EXPOSURE).log().alias("log_exposure"),
        (pl.col(DEATHS) / pl.col(EXPOSURE)).alias("death_rate"),
        pl.col("attained_age").cast(pl.Float64),
    )
    if "duration_months" in out.columns:
        out = out.with_columns((pl.col("duration_months") / 12.0 + 1.0).alias("duration"))
    if "band" in out.columns:
        out = out.rename({"band": "face_band"})
    if "calendar_year" in out.columns and "duration" in out.columns:
        out = out.with_columns(
            (pl.col("calendar_year") - pl.col("duration") + 1.0).alias("issue_year")
        )
    return out


def floor_trials_at_deaths(cells: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Binomial trials floored at deaths: ``exposure := max(exposure, deaths)``, then ``death_rate``
    is recomputed (so it is at most one). Returns the frame and the NUMBER of cells changed.

    A MODELLING CHOICE the maintainer asked for (2026-10-18), for the ``S1`` sensitivity only and
    never the default: ``Policies_Exposed`` is fractional policy-years, so ``deaths > exposure`` can
    occur in sparse cells, which a binomial proportion cannot represent. Flooring treats such a cell
    as ``deaths`` trials all of which died: it BIASES those cells' rate upward relative to the
    Poisson model, so every result carries the flag and the changed-cell count.
    """
    changed = int(cells.filter(pl.col("deaths") > pl.col("exposure")).height)
    out = cells.with_columns(
        pl.max_horizontal("exposure", "deaths").alias("exposure")
    ).with_columns((pl.col("deaths") / pl.col("exposure")).alias("death_rate"))
    return out, changed


def to_factor_frame(frame: pl.DataFrame, factors: Iterable[str]) -> pl.DataFrame:
    """Cast ``factors`` to a Polars ``Enum`` with ONE level order, shared with the R side
    through the cell spec. Level order does not change ``eta``/``edf`` (a reparameterisation),
    and fixing it removes locale collation from the comparison.

    ``face_band`` levels are RENAMED to ``B00, B01, ...`` in sorted order: real band labels hold
    characters ``gam()`` refuses in a level name, and renaming keeps the labels out of the cell
    files and out of any message (the mapping is never written anywhere).
    """
    cols = []
    for f in factors:
        if f not in frame.columns:
            continue
        raw = sorted(frame[f].cast(pl.String).unique().to_list())
        if f == "face_band":
            mapping = {v: f"B{i:02d}" for i, v in enumerate(raw)}
            levels = list(mapping.values())
            col = pl.col(f).cast(pl.String).replace_strict(mapping, return_dtype=pl.String)
        else:
            levels = raw
            col = pl.col(f).cast(pl.String)
        cols.append(col.cast(pl.Enum(levels)).alias(f))
    return frame.with_columns(cols) if cols else frame


# --- the Polaris side --------------------------------------------------------------------------

PHASE_FUNCTIONS: Final[dict[str, tuple[str, ...]]] = {
    "design_assembly": ("assemble_model_design",),
    "pivot": ("pivot_design",),
    "pirls": ("penalized_irls_general",),
    "reml_gradient": ("reml_score_gradient", "reml_score_gradient_profiled"),
    "reml_hessian": ("reml_score_hessian", "reml_score_hessian_profiled"),
    "penalized_fit_and_score": ("penalized_fit_and_score",),
    "newton_outer_total": ("newton_select_lambdas",),
    "fit_total": ("fit_polaris_gam",),
}
"""cProfile buckets: cumulative seconds under each function NAME. Buckets nest (the Newton search
contains the PIRLS calls), so they are readings, not a partition. Names, not data."""


@dataclass
class PolarisSide:
    """What :func:`fit_polaris` produced. Holds per-row arrays; never written to the output."""

    status: str
    fit: GamFit | None = None
    eta: np.ndarray | None = None
    se: np.ndarray | None = None
    refusal: str | None = None
    fit_seconds: list[float] = field(default_factory=list)
    phase_seconds: dict[str, float] = field(default_factory=dict)
    peak_rss_mb: float = float("nan")
    rank_deficient: bool = False
    warnings_seen: int = 0


def peak_rss_mb() -> float:
    """Peak resident set size of this process in MB (``ru_maxrss`` is KB on Linux, bytes on
    macOS)."""
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return float(r) / (1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0)


def _repeat(fn: Callable[[], object], repeats: int, budget_s: float) -> tuple[object, list[float]]:
    """Run ``fn`` up to ``repeats`` times, stopping once cumulative time passes ``budget_s``
    (a long fit is timed once; ``k`` actually used is recorded by the caller as ``len(times)``)."""
    times: list[float] = []
    result: object = None
    while len(times) < repeats and (not times or sum(times) < budget_s):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return result, times


def fit_polaris(
    formula: TrialFormula,
    data: pl.DataFrame,
    *,
    repeats: int = 3,
    budget_s: float = 600.0,
    profile: bool = True,
) -> PolarisSide:
    """Fit ``formula`` through the public ``gam()``; time it best-of-``repeats``.

    A refusal (:class:`PolarisValidationError` from ``gam()``) is a RESULT: ``status="refused"``.
    The signature takes no ``mgcv`` output (ADR-193 mechanical test).
    """

    caught_last: list[warnings.WarningMessage] = []

    def run() -> GamFit:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            f = gam(
                formula.formula,
                data,
                formula.family,
                weights=formula.weights,
                select=formula.select,
                allow_unverified_select=formula.allow_unverified_select,
            )
        caught_last[:] = caught
        return f

    try:
        fit, times = _repeat(run, repeats, budget_s)
    except PolarisValidationError as exc:
        return PolarisSide(status="refused", refusal=str(exc))
    assert isinstance(fit, GamFit)
    caught = list(caught_last)
    side = PolarisSide(
        status="fitted",
        fit=fit,
        fit_seconds=times,
        rank_deficient=any("RankDeficiency" in type(w.message).__name__ for w in caught),
        warnings_seen=len(caught),
    )
    side.eta = np.asarray(fit.eta, dtype=np.float64)
    pred = fit.predict(data, "link", se_fit=True)
    side.se = np.asarray(pred[1], dtype=np.float64)
    if profile:
        prof = cProfile.Profile()
        prof.enable()
        try:
            run()
        finally:
            prof.disable()
        stats = pstats.Stats(prof).stats  # type: ignore[attr-defined]
        by_name: dict[str, float] = {}
        for (_, _, name), (_, _, _, ct, _) in stats.items():
            by_name[name] = by_name.get(name, 0.0) + float(ct)
        side.phase_seconds = {
            phase: sum(by_name.get(n, 0.0) for n in names)
            for phase, names in PHASE_FUNCTIONS.items()
        }
    side.peak_rss_mb = peak_rss_mb()
    return side


# --- the comparison ----------------------------------------------------------------------------

CLAIM: Final = VerificationClaim(
    claim=(
        "Polaris (gam() -> fit_polaris_gam, Newton REML) fits the trial formula from the "
        "ILEC-derived cell columns; mgcv (pinned digest, gam(method='REML')) fits the same "
        "string on the same columns; compared on eta, edf_total, per-smooth edf, the Vp se.fit, "
        "log10(sp), the REML score and the scale. The same comparison runs on real cells (tier L, "
        "maintainer-run) and on synthetic cells (CI, tier 3)."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta at the cell rows (gated: ADR-221 and the scaled criterion)",
            left_producer="GamFit.eta",
            right_producer="mgcv m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (gated: ADR-221)",
            left_producer="GamFit.edf_total",
            right_producer="mgcv sum(m$edf)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="Vp se.fit (gated: ADR-250 relative 2e-2)",
            left_producer="GamFit.predict(se_fit=True)",
            right_producer="mgcv predict.gam(se.fit=TRUE)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="per-smooth edf, log10(sp), REML score, scale (reported, never gated)",
            left_producer="GamFit.summary()",
            right_producer="mgcv m$edf, m$sp, m$gcv.ubre, m$scale",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Declared per column (ADR-193). Wall times are NOT in this claim: they are MEASUREMENTs of each
engine against itself, and the Polaris/mgcv ratio is a timing reading, not agreement."""


@dataclass(frozen=True)
class Agreement:
    """The differences, as scalars. Nothing here is a row, a key or a curve."""

    eta_max_abs: float
    eta_rms: float
    eta_scaled_max: float
    edf_total_abs: float
    se_rel_max: float
    term_edf_max_abs: float
    log10_sp_max_abs: float
    log10_sp_rms: float
    reml_abs: float
    score_gap_at_mgcv_sp: float
    scale_rel: float
    n_coef_diff: int
    n_terms_df_mismatch: int
    n_terms_compared: int
    n_terms_unmatched: int
    eta_gate_met: bool
    edf_gate_met: bool
    se_gate_met: bool
    scaled_gate_met: bool
    scaled_flag: bool


def _score_gap(fit: GamFit, mgcv: Mapping[str, object]) -> float:
    """MEASUREMENT of Polaris against its OWN criterion (not a comparison): Polaris's REML score
    evaluated at ``mgcv``'s ``sp`` minus at Polaris's selected ``sp``. ``mgcv``'s ``sp`` enters
    only as the evaluation point. Negative = ``mgcv``'s point scores better under Polaris's
    criterion, i.e. the disagreement is the OUTER SEARCH (mechanism class iii, ADR-241).
    ``nan`` when it cannot be formed (a pivoted design, a different penalty count, a non-fixed
    scale family)."""
    try:
        sp_m = np.concatenate(
            [np.atleast_1d(np.asarray(s["log10_sp"], dtype=np.float64)) for s in mgcv["smooths"]]  # type: ignore[attr-defined,index]
        )
        if sp_m.shape != fit.log_lambda.shape or fit.y is None:
            return float("nan")
        _, score = penalized_fit_and_score(
            fit.y,
            fit.design["x"],
            resolve_family(fit.model.family, fit.model.link),
            fit.design["penalty_blocks"],
            sp_m,
            offset=fit.offset,
            weights=fit.prior_weights,
        )
        return float(score - fit.reml_score)
    except (
        PolarisValidationError,
        PolarisComputationError,
        KeyError,
        ValueError,
        np.linalg.LinAlgError,
    ):
        # a measurement that cannot be formed (pivoted design, other penalty count) is nan;
        # anything else is a real defect and propagates
        return float("nan")


def compare(side: PolarisSide, mgcv: Mapping[str, object]) -> Agreement:
    """Reduce two independently produced fits to scalar differences.

    ``mgcv`` is the R companion's scratch payload (``eta``, ``se_fit``, ``edf_total``,
    ``smooths`` as ``{label, edf, log10_sp}``, ``reml``, ``scale``). Per-row arrays are consumed
    here and are not returned.
    """
    if side.fit is None or side.eta is None or side.se is None:
        raise PolarisValidationError("compare(): the Polaris side was not fitted.")
    eta_m = np.asarray(mgcv["eta"], dtype=np.float64)
    se_m = np.asarray(mgcv["se_fit"], dtype=np.float64)
    if eta_m.shape != side.eta.shape:
        raise PolarisValidationError("compare(): the two fits have different row counts.")
    d = np.abs(side.eta - eta_m)
    scaled = float(np.max(d / se_m)) if np.all(se_m > 0) else float("inf")
    se_rel = float(np.max(np.abs(side.se - se_m) / se_m)) if np.all(se_m > 0) else float("inf")
    summ = side.fit.summary()
    m_smooths = {s["label"]: s for s in mgcv["smooths"]}  # type: ignore[attr-defined,index]
    term_d: list[float] = []
    sp_d: list[float] = []
    unmatched = 0
    df_mismatch = 0
    for s in summ.smooths:
        ms = m_smooths.get(s.label)
        if ms is None:
            unmatched += 1
            continue
        df_mismatch += int(int(ms.get("df", s.n_coef)) != s.n_coef)
        term_d.append(abs(s.edf - float(ms["edf"])))
        ps, msp = (
            np.asarray(s.log10_sp),
            np.atleast_1d(np.asarray(ms["log10_sp"], dtype=np.float64)),
        )
        if ps.shape == msp.shape:
            sp_d.extend(np.abs(ps - msp).tolist())
    reml_m = float(mgcv["reml"])  # type: ignore[arg-type]
    scale_m = float(mgcv["scale"])  # type: ignore[arg-type]
    edf_abs = abs(float(side.fit.edf_total) - float(mgcv["edf_total"]))  # type: ignore[arg-type]
    eta_max = float(d.max())
    return Agreement(
        eta_max_abs=eta_max,
        eta_rms=float(math.sqrt(float(np.mean(d**2)))),
        eta_scaled_max=scaled,
        edf_total_abs=edf_abs,
        se_rel_max=se_rel,
        term_edf_max_abs=max(term_d, default=float("nan")),
        log10_sp_max_abs=max(sp_d, default=float("nan")),
        log10_sp_rms=float(math.sqrt(float(np.mean(np.square(sp_d))))) if sp_d else float("nan"),
        reml_abs=abs(float(summ.reml_score) - reml_m),
        score_gap_at_mgcv_sp=_score_gap(side.fit, mgcv),
        scale_rel=abs(float(summ.scale) - scale_m) / max(abs(scale_m), 1e-300),
        n_coef_diff=int(mgcv.get("n_coef", 0)) - int(side.fit.coef.shape[0]),  # type: ignore[call-overload,arg-type]
        n_terms_df_mismatch=df_mismatch,
        n_terms_compared=len(term_d),
        n_terms_unmatched=unmatched,
        eta_gate_met=eta_max < ETA_GATE,
        edf_gate_met=edf_abs < EDF_GATE,
        se_gate_met=se_rel < SE_REL_GATE,
        scaled_gate_met=scaled <= SCALED_ETA_GATE,
        scaled_flag=scaled > SCALED_ETA_FLAG,
    )


# --- the derived-scalars-only contract ---------------------------------------------------------

OUTPUT_KEYS: Final[frozenset[str]] = frozenset(
    {
        # envelope
        "schema_version",
        "tier",
        "oracle_image_digest",
        "openblas_num_threads",
        "polaris_environment",
        "mgcv_environment",
        "polaris_commit",
        "r_version",
        "mgcv_version",
        "image_architecture",
        "host_architecture",
        "like_for_like",
        "machine",
        "results",
        "claim",
        "q_r2g_reading",
        # machine description (PLAN R2)
        "chip",
        "performance_cores",
        "efficiency_cores",
        "ram_gb",
        "os",
        "docker_cpu_limit",
        "docker_memory_gb",
        "power_source",
        "low_power_mode",
        "python",
        "polars",
        "numpy",
        # one result per (formula, granularity)
        "formula",
        "granularity",
        "role",
        "status",
        "refusal",
        "family",
        "select",
        "n_cells",
        "n_coef",
        "n_penalties",
        "n_smooths",
        "polaris",
        "mgcv",
        "agreement",
        "timing",
        "term",
        # polaris/mgcv fit scalars
        "converged",
        "n_iterations",
        "n_function_evals",
        "rank_deficient_warning",
        "edf_total",
        "reml_score",
        "scale",
        "peak_rss_mb",
        "fit_seconds",
        "repeats_used",
        "best_seconds",
        "phase_seconds",
        "ratio_polaris_over_mgcv",
        "ratio_comparable",
        # per-term (positional, no labels)
        "terms",
        "index",
        "kind",
        "edf",
        "log10_sp_min",
        "log10_sp_max",
        # agreement scalars
        "eta_max_abs",
        "eta_rms",
        "eta_scaled_max",
        "edf_total_abs",
        "se_rel_max",
        "term_edf_max_abs",
        "log10_sp_max_abs",
        "log10_sp_rms",
        "reml_abs",
        "score_gap_at_mgcv_sp",
        "scale_rel",
        "n_coef_diff",
        "n_terms_df_mismatch",
        "n_terms_compared",
        "n_terms_unmatched",
        "eta_gate_met",
        "edf_gate_met",
        "se_gate_met",
        "scaled_gate_met",
        "scaled_flag",
        "all_gates_met",
        # time ceiling
        "ceiling_seconds",
        "ceiling_met",
        # phase buckets (names fixed in PHASE_FUNCTIONS)
        *PHASE_FUNCTIONS,
    }
)
"""Every key a committed result may carry. Adding one is a maintainer decision (Q-R2c)."""

_VOCAB: Final = re.compile(
    r"^(?:T[12]|T3[abc]|S[123]|coarse|mid|full|main|sensitivity|candidate|fitted|refused|not_run"
    r"|failed|native|container|tier L|poisson|quasipoisson|gaussian"
    r"|binomial\(link=\"cloglog\"\)|binomial"
    r"|cr|ti|re|cr_by_level|cr_by_numeric|other|AC|battery|on|off|unknown)$"
)
_KEY_STRING_RULES: Final[dict[str, re.Pattern[str]]] = {
    "oracle_image_digest": re.compile(r"^sha256:[0-9a-f]{64}$"),
    "polaris_commit": re.compile(r"^[0-9a-f]{7,40}$"),
    "image_architecture": re.compile(r"^linux/(?:amd64|arm64)$"),
    "host_architecture": re.compile(r"^(?:x86_64|arm64|aarch64|amd64)$"),
    "r_version": re.compile(r"^R version [0-9.]+ \([0-9\-]+\)$"),
    "mgcv_version": re.compile(r"^[0-9]+(?:\.[0-9]+)*(?:-[0-9]+)?$"),
    "openblas_num_threads": re.compile(r"^[0-9]{1,3}$"),
    "python": re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}$"),
    "polars": re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}$"),
    "numpy": re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}$"),
}
MAX_SEQUENCE: Final = 64
"""Longest list a result may carry. A fitted curve or a column of rows would exceed it."""
_CHIP_OK: Final = re.compile(r"^[A-Za-z0-9 ._\-+()]{0,60}$")
_FREE_TEXT_KEYS: Final = frozenset({"chip", "os", "claim", "q_r2g_reading", "refusal"})
_FREE_TEXT_MAX: Final = 1200


def assert_derived_scalars_only(obj: object, *, path: str = "$") -> None:
    """Raise :class:`PolarisValidationError` unless ``obj`` honours PLAN §3.

    Keys must be in :data:`OUTPUT_KEYS`; string leaves must match a fixed vocabulary (the
    free-text keys ``chip``, ``os``, ``claim``, ``q_r2g_reading`` and ``refusal`` are length-capped
    and ``refusal`` must already have passed :func:`sanitise_refusal`; version/digest/architecture
    keys have their own patterns); lists are at most
    :data:`MAX_SEQUENCE` long; numeric leaves are scalars.
    """
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if k not in OUTPUT_KEYS:
                raise PolarisValidationError(f"output key {k!r} at {path} is not whitelisted")
            if isinstance(v, str) and k in _FREE_TEXT_KEYS:
                if len(v) > _FREE_TEXT_MAX or (k == "chip" and not _CHIP_OK.match(v)):
                    raise PolarisValidationError(f"free-text value at {path}.{k} too long/odd")
                continue
            assert_derived_scalars_only(v, path=f"{path}.{k}")
    elif isinstance(obj, list | tuple):
        if len(obj) > MAX_SEQUENCE:
            raise PolarisValidationError(f"sequence at {path} longer than {MAX_SEQUENCE}")
        for i, v in enumerate(obj):
            assert_derived_scalars_only(v, path=f"{path}[{i}]")
    elif isinstance(obj, str):
        rule = _KEY_STRING_RULES.get(path.rsplit(".", 1)[-1])
        if not (rule.match(obj) if rule else _VOCAB.match(obj)):
            raise PolarisValidationError(f"string value at {path} is not on the vocabulary")
    elif obj is None or isinstance(obj, bool | int | float):
        return
    else:
        raise PolarisValidationError(f"value of type {type(obj).__name__} at {path}")


def sanitise_refusal(message: str, levels: Iterable[str] = ()) -> str:
    """A refusal message safe to commit: the text is kept only if it contains none of the data's
    factor levels (the unseen-level refusal quotes one); otherwise it is replaced."""
    text = " ".join(message.split())[:600]
    if any(len(lv) > 0 and lv in text for lv in levels):
        return "<redacted: the refusal quoted a data value>"
    return text


def term_kind(label: str) -> str:
    """Positional kind of a smooth from its mgcv label, never carrying a level name."""
    if label.startswith("ti("):
        return "ti"
    if label.startswith("s(") and ":" in label:
        tail = label.split(":", 1)[1]
        return "cr_by_level" if tail and not tail[0].isdigit() else "cr_by_numeric"
    if label.startswith("s("):
        return "cr"
    return "other"


def terms_block(summary_smooths: Iterable[SmoothSummary]) -> list[dict[str, object]]:
    """Per-smooth scalars by position, with no label (a factor-``by`` label carries a level)."""
    out: list[dict[str, object]] = []
    for i, s in enumerate(summary_smooths):
        sp = list(s.log10_sp)
        out.append(
            {
                "index": i,
                "kind": term_kind(s.label),
                "edf": float(s.edf),
                "log10_sp_min": float(min(sp)) if sp else None,
                "log10_sp_max": float(max(sp)) if sp else None,
            }
        )
    return out


def machine_description(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    """What the script can discover about the host. Chip, core counts, RAM and the Docker limits
    are filled by the runbook's step 1 through ``overrides`` (a laptop's chip is not reliably
    discoverable from inside a container)."""
    out: dict[str, object] = {
        "chip": re.sub(r"[^A-Za-z0-9 ._\-+()]", "?", platform.processor() or platform.machine())[
            :60
        ],
        "os": f"{platform.system()} {platform.release()}"[:60],
        "python": platform.python_version(),
        "polars": pl.__version__,
        "numpy": np.__version__,
    }
    out.update(overrides or {})
    return out


def clean(obj: object) -> object:
    """Replace non-finite floats by ``None`` (JSON has no NaN) and numpy scalars by Python ones."""
    if isinstance(obj, Mapping):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [clean(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def dumps(result: object) -> str:
    """Serialise a result after cleaning it and enforcing the contract."""
    out = clean(result)
    assert_derived_scalars_only(out)
    return json.dumps(out, indent=2, sort_keys=True, allow_nan=False)

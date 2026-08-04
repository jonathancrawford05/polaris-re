"""
Real-data diligence harness for the tensor mortality-improvement (MI) surface.

Slice 1 of ``docs/PLAN_experience_gam_realdata.md``. The A4' epic validated the
tensor GAM exclusively against synthetic data with an *injected* surface, which
proves the implementation recovers a surface it was handed and says nothing about
whether it recovers real improvement from real experience. This module is the
harness that closes that gap: it loads a local HMD or SOA-ILEC cache, fits
``te(attained_age, calendar_year)``, and emits a **structured findings report**
(JSON + Markdown) that can be committed on its own.

Three things are deliberate, because each is easy to get wrong in the flattering
direction:

1. **Falsifiable output, not a pretty picture.** The report leads with the
   decade-over-decade window comparison — the improvement *slowdown* test named in
   advance in PLAN §2 — and on the ILEC path with A/E against SOA's own published
   expected deaths. A run that reports "no slowdown" is a **successful** run.
   Nothing here tunes anything until it agrees.
2. **The aggregation level is a first-class, stated parameter.** The real ILEC
   2012-2019 release is 9,714,592 canonical cells; the MI surface needs ~10^4.
   Collapsing is necessary — and collapsing across ``smoker``/``uw_class`` pools
   populations with genuinely different mortality, so the default does not, and
   whatever level is used is echoed in the report.
3. **Loaders, not data** (Design Anchor 6). Nothing here reads from or writes to
   the repo tree: input comes from ``default_experience_cache_dir()`` and the
   output is *findings*. Input file paths are reported as **basenames**, so a
   committed report carries no home directory.

**No plots.** Numbers and tables commit and diff; images do not.

**No wall clock** (ADR-074), and floats rounded to
:data:`REPORT_SIGNIFICANT_DIGITS`: two runs over the same inputs produce
byte-identical JSON, so a re-run diffs cleanly against a committed finding.
Removing the clock alone is *not* enough — the delta-method band runs through
multithreaded BLAS, which reassociates its sums run to run; see
:data:`REPORT_SIGNIFICANT_DIGITS` for the measurement.

Entry point: :func:`run_diligence`. The command-line wrapper is
``scripts/experience_diligence.py``.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re import __version__
from polaris_re.analytics.experience_gam import (
    AMOUNT_MEASURES,
    COUNT_MEASURES,
    MISurface,
    MISurfaceResult,
    TensorMIModel,
)
from polaris_re.analytics.experience_loaders import (
    ILEC_2012_19_COLUMN_MAP,
    ILEC_COLUMN_MAP,
    ILEC_EXPECTED_AMOUNT_MEASURES,
    ILEC_EXPECTED_COUNT_MEASURES,
    default_experience_cache_dir,
    load_hmd,
    load_ilec,
)
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "DEFAULT_REFERENCE_AGES",
    "EMPIRICAL_BASE_KEYS",
    "HMD_GROUP_KEYS",
    "ILEC_GROUP_KEYS",
    "ILEC_VINTAGES",
    "REPORT_SIGNIFICANT_DIGITS",
    "RUNBOOK_PATH",
    "UNKNOWN_UW_CLASS",
    "AEByYear",
    "DiligenceReport",
    "EmpiricalBase",
    "ExperienceCacheMissingError",
    "IlecVintage",
    "SoaSurfaceComparison",
    "WindowComparison",
    "WindowMI",
    "attach_empirical_base",
    "default_windows",
    "render_markdown",
    "resolve_hmd_paths",
    "resolve_ilec_path",
    "run_diligence",
]

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
"""Anything that survives a ``json.dumps`` round trip. The report serialises to
this rather than to ``Any`` (CLAUDE.md §5)."""


RUNBOOK_PATH = "docs/RUNBOOK_experience_data_acquisition.md"
"""Where a maintainer is sent when the cache is missing or empty. Every
data-absent error names it — the first thing hit should be a sentence, not a
stack trace."""

SCHEMA_VERSION = 1
"""Report schema version. Bump on any breaking change to :meth:`DiligenceReport.to_dict`
so a committed finding stays interpretable against a later harness."""

REPORT_SIGNIFICANT_DIGITS = 12
"""Significant digits every float in the JSON report is rounded to.

**Not cosmetic — this is what makes the artefact diffable.** Removing the wall
clock is necessary for byte-stability but not sufficient: the delta-method band
goes through ``cov_params`` and an ``einsum``, both of which run on multithreaded
BLAS, and BLAS reassociates its sums differently depending on how the threads
happen to carve up the work. Measured on this harness, two runs of the *same*
script over the *same* cache differ by up to **1.2e-14 relative** in
``mi_lower`` / ``mi_upper`` — invisible actuarially, and enough to make a
committed finding show a spurious diff on every re-run. (Pinning
``OMP_NUM_THREADS=1`` removes it entirely, which confirms the cause; a library
has no business setting that for the whole process.)

Rounding at 12 significant digits sits ~80x above the observed jitter and ~9
orders of magnitude below anything an actuary would read. It makes a spurious
diff vanishingly unlikely rather than impossible — a value landing within 1e-14
relative of a 12th-digit boundary could still tip — which is the honest claim.
Point estimates were already stable; only the covariance path moves.
(PR #185 review, on the determinism over-claim.)"""

DEFAULT_REFERENCE_AGES: tuple[int, ...] = (45, 55, 65, 75, 85)
"""Attained ages the surface is reported at. Interior to a typical 25-95 fit, so
none of them sits on a B-spline boundary where the surface wiggles."""

HMD_GROUP_KEYS: tuple[str, ...] = ("attained_age", "calendar_year", "sex")
"""Aggregation level for population data — which is *already* at this grain, so
the group-by is a no-op that exists to make the level explicit in the report."""

ILEC_GROUP_KEYS: tuple[str, ...] = (
    "attained_age",
    "calendar_year",
    "sex",
    "smoker",
    "uw_class",
)
"""Conservative default aggregation for insured data.

Keeps ``smoker`` and ``uw_class`` — pooling those merges populations with
genuinely different mortality. Drops ``issue_age``/``duration_months``/``product``/
``band``: retaining ``duration_months`` alone multiplies the cell count by ~60 for
a term the MI contrast does not need, and the surface's calendar gradient is a
*within-cell* contrast. That is a real limitation, not a free lunch — duration mix
drifting with calendar year would leak into the trend — so it is stated as a
caveat in every report rather than left implicit. Override with ``group_keys``."""

EMPIRICAL_BASE_KEYS: tuple[str, ...] = ("attained_age", "duration_months", "sex", "smoker")
"""Covariates the empirical base rate may depend on.

Deliberately the same determinant set the static-base guard (Design Anchor 1)
groups on: a base that varied with a covariate *outside* this set — ``uw_class``,
say — would show a within-group spread and the guard would read it as a
generational base. Covariates outside the set belong in the model as factors,
which is exactly where the GAM puts them."""

UNKNOWN_UW_CLASS = "U"
"""The ILEC underwriting-class *missing-data* sentinel (~2% of rows in the
2012-2019 release), as distinct from ``"NA"`` = *not applicable* (no preferred
structure), which is a legitimate stratum and is pooled as its own level. ``U`` is
held out of class-conditioned inference by default — see ``keep_unknown_uw_class``."""

_MIN_YEARS_FOR_WINDOWS = 4
"""Fewer observed years than this and the early/late comparison cannot be formed
from two disjoint windows each spanning at least one annual step."""

_LONG_WINDOW = 10
"""Window length used when the observed range is long enough for two of them
(e.g. HMD 1990-2019 -> 1990-1999 vs 2010-2019)."""


@dataclass(frozen=True)
class IlecVintage:
    """A named ILEC release: its column spelling and its field delimiter."""

    name: str
    column_map: dict[str, str]
    separator: str
    description: str


ILEC_VINTAGES: dict[str, IlecVintage] = {
    "2012-19": IlecVintage(
        name="2012-19",
        column_map=ILEC_2012_19_COLUMN_MAP,
        separator="\t",
        description=(
            "2012-2019 release (ILEC_2012_19 - 20240429.txt): underscored headers, "
            "'Sex' not 'Gender', TAB-delimited despite the .txt name, and publishes "
            "SOA's own expected deaths."
        ),
    ),
    "generic": IlecVintage(
        name="generic",
        column_map=ILEC_COLUMN_MAP,
        separator=",",
        description="Space-separated header spelling, comma-delimited (older flat files).",
    ),
}
"""Known ILEC releases. The delimiter is part of the vintage because the file
extension carries no format information — the 2012-2019 release is tab-delimited
despite shipping as ``.txt``."""


# --- Cache discovery ------------------------------------------------------------


class ExperienceCacheMissingError(PolarisValidationError):
    """The local experience cache holds no usable input for the requested source.

    A distinct **type** rather than a distinguishable message, because the CLI
    wrapper maps this to its documented ``exit 2`` and every other validation
    failure to ``exit 1``. Classifying on wording instead drifts silently the
    first time one of these messages is reworded — which is exactly how the ILEC
    path came to exit 1 against a documented 2 (PR #185 review [P1]).

    Subclasses :class:`PolarisValidationError`, so callers that catch the base
    class are unaffected.
    """


def _cache_root(cache_dir: str | Path | None) -> Path:
    return Path(cache_dir) if cache_dir is not None else default_experience_cache_dir()


def resolve_hmd_paths(country: str, *, cache_dir: str | Path | None = None) -> tuple[Path, Path]:
    """Locate a country's ``Deaths_1x1.txt`` / ``Exposures_1x1.txt`` in the cache.

    Searches the layout :func:`~polaris_re.analytics.experience_loaders.fetch_hmd`
    produces (``{cache}/hmd/{COUNTRY}/``) **and** the ``STATS/`` subdirectory the
    zipped "Statistics" bundle extracts into — the manual download route the
    runbook documents lands in the latter, and a harness that only knew about the
    former would report "not found" while staring at the file.

    Args:
        country:   HMD country code, e.g. ``"USA"`` or ``"GBRTENW"``.
        cache_dir: Cache root override; defaults to
                   :func:`~polaris_re.analytics.experience_loaders.default_experience_cache_dir`.

    Returns:
        ``(deaths_path, exposures_path)``.

    Raises:
        PolarisValidationError: If either file is absent, naming every directory
            searched and pointing at the acquisition runbook.
    """
    root = _cache_root(cache_dir)
    country_dir = root / "hmd" / country
    candidates = (country_dir, country_dir / "STATS")

    found: dict[str, Path] = {}
    for stem in ("Deaths", "Exposures"):
        for directory in candidates:
            path = directory / f"{stem}_1x1.txt"
            if path.exists():
                found[stem] = path
                break

    missing = [s for s in ("Deaths", "Exposures") if s not in found]
    if missing:
        searched = "\n  ".join(str(d / f"{s}_1x1.txt") for s in missing for d in candidates)
        raise ExperienceCacheMissingError(
            f"HMD 1x1 file(s) not found for country {country!r}: "
            f"{', '.join(f'{s}_1x1.txt' for s in missing)}.\nSearched:\n  {searched}\n"
            f"Download them (DATA -> Zipped Data Files -> Statistics) and place them "
            f"under {country_dir} — see {RUNBOOK_PATH} §1b. Note 1x1 specifically: "
            f"1x5 / 5x1 / 5x5 are not single-age single-year cells and will not parse."
        )
    return found["Deaths"], found["Exposures"]


def resolve_ilec_path(*, cache_dir: str | Path | None = None, filename: str | None = None) -> Path:
    """Locate the ILEC flat file in ``{cache}/ilec/``.

    Args:
        cache_dir: Cache root override.
        filename:  Exact file name to use. Required when the directory holds more
                   than one candidate — guessing between vintages would silently
                   produce findings about the wrong release.

    Returns:
        The resolved path.

    Raises:
        PolarisValidationError: If the directory is missing, holds no candidate, or
            holds several and ``filename`` was not given.
    """
    root = _cache_root(cache_dir)
    ilec_dir = root / "ilec"

    if filename is not None:
        path = ilec_dir / filename if not Path(filename).is_absolute() else Path(filename)
        if not path.exists():
            raise ExperienceCacheMissingError(
                f"ILEC file not found: {path}. See {RUNBOOK_PATH} §2 for the download "
                f"and the `unzip -d` that keeps it out of the repo tree."
            )
        return path

    if not ilec_dir.is_dir():
        raise ExperienceCacheMissingError(
            f"No ILEC cache directory at {ilec_dir}. The release is a manual, "
            f"terms-accepting download (there is no fetch helper on purpose) — see "
            f"{RUNBOOK_PATH} §2. Unzip it with `unzip -d`, or it lands in your "
            f"current directory."
        )

    candidates = sorted(p for p in ilec_dir.iterdir() if p.suffix.lower() in {".txt", ".csv"})
    if not candidates:
        raise ExperienceCacheMissingError(
            f"ILEC cache directory {ilec_dir} holds no .txt/.csv file. See {RUNBOOK_PATH} §2."
        )
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise ExperienceCacheMissingError(
            f"ILEC cache directory {ilec_dir} holds {len(candidates)} candidate files "
            f"({names}). Pass an explicit filename — picking one would silently "
            f"produce findings about a release you did not choose."
        )
    return candidates[0]


# --- Empirical base rate --------------------------------------------------------


@dataclass(frozen=True)
class EmpiricalBase:
    """Cells carrying a data-derived static ``q_base``, plus what it cost."""

    cells: pl.DataFrame
    """The input cells with a ``q_base`` column, minus any dropped strata."""

    keys: tuple[str, ...]
    """Covariates the base varies over (a subset of :data:`EMPIRICAL_BASE_KEYS`)."""

    n_strata: int
    """Distinct base strata retained."""

    n_strata_dropped: int
    """Strata dropped for having zero deaths across the whole observed window —
    they carry no information about a mortality *trend*, and their base rate is
    not estimable."""

    dropped_exposure_share: float
    """Share of total exposure in the dropped strata. Small is reassuring; large
    means the aggregation level is too fine for the data."""

    n_clipped: int
    """Cells whose crude rate exceeded 1.0 and were clipped. Non-zero is expected
    only at extreme ages, where a central rate can exceed one."""


def attach_empirical_base(
    cells: pl.DataFrame,
    *,
    exposure_col: str,
    deaths_col: str,
    column: str = "q_base",
) -> EmpiricalBase:
    """Attach a **static** base rate estimated from the data itself.

    ``q_base`` is the pooled crude rate ``Σ deaths / Σ exposure`` over the whole
    calendar window within each stratum of :data:`EMPIRICAL_BASE_KEYS`. It is
    calendar-invariant by construction, so it satisfies Design Anchor 1 and the
    static-base guard.

    **Why this is a legitimate offset, not a shortcut.** The fitted improvement
    ``MI_x(y) = 1 - exp[η(x, y) - η(x, y-1)]`` is a *calendar contrast*: every
    calendar-invariant term — the offset included — cancels in the difference. So
    the MI surface is identical whatever static base is used, and using the data's
    own pooled rate buys three things a standard table does not: it needs no table
    files (so this runs in CI and on population data, for which no insured table is
    the right base), it cannot introduce a spurious trend, and it makes
    ``overall_ae`` ≈ 1 by construction — which is the honest reading, since an A/E
    against a base fitted to the same data is not an independent check. On the ILEC
    path the *independent* check is SOA's own published expected deaths.

    Strata with zero total deaths are dropped (their rate is not estimable and they
    carry no trend information); crude rates above 1.0 are clipped.

    Args:
        cells:        Grouped cells carrying ``attained_age`` and the measure pair.
        exposure_col: Exposure measure column.
        deaths_col:   Deaths measure column.
        column:       Output column name.

    Returns:
        An :class:`EmpiricalBase`.

    Raises:
        PolarisValidationError: If ``attained_age`` is absent, or every stratum was
            dropped for having no deaths.
    """
    if "attained_age" not in cells.columns:
        raise PolarisValidationError(
            "attach_empirical_base requires an 'attained_age' column in the cells."
        )
    keys = tuple(k for k in EMPIRICAL_BASE_KEYS if k in cells.columns)

    total_exposure = float(cells[exposure_col].sum())
    strata = cells.group_by(list(keys)).agg(
        pl.col(deaths_col).sum().alias("_deaths"),
        pl.col(exposure_col).sum().alias("_exposure"),
    )
    n_strata_all = strata.height
    live = strata.filter((pl.col("_deaths") > 0.0) & (pl.col("_exposure") > 0.0))
    dropped_exposure = float(strata["_exposure"].sum()) - float(live["_exposure"].sum())

    if live.height == 0:
        raise PolarisValidationError(
            "Every base stratum has zero deaths (or zero exposure) — an empirical "
            "base rate is not estimable. Widen the calendar/age window or coarsen "
            "the aggregation level."
        )

    rate = (pl.col("_deaths") / pl.col("_exposure")).alias(column)
    live = live.with_columns(rate)
    n_clipped = int(live.filter(pl.col(column) > 1.0).height)
    live = live.with_columns(pl.col(column).clip(upper_bound=1.0))

    out = cells.join(live.select(*keys, column), on=list(keys), how="inner")
    return EmpiricalBase(
        cells=out,
        keys=keys,
        n_strata=live.height,
        n_strata_dropped=n_strata_all - live.height,
        dropped_exposure_share=(dropped_exposure / total_exposure) if total_exposure > 0 else 0.0,
        n_clipped=n_clipped,
    )


# --- Window comparison (the slowdown test) --------------------------------------


@dataclass(frozen=True)
class WindowMI:
    """Annualised improvement over one calendar window, at each reference age."""

    start_year: int
    end_year: int
    ages: tuple[int, ...]
    annualised_mi: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]

    @property
    def n_steps(self) -> int:
        """Annual steps the window spans."""
        return self.end_year - self.start_year


@dataclass(frozen=True)
class WindowComparison:
    """Early-vs-late annualised improvement — the falsifiable slowdown test."""

    early: WindowMI
    late: WindowMI
    delta: tuple[float, ...]
    """``late - early`` annualised MI per reference age. Negative = slowdown."""

    bands_overlap: tuple[bool, ...]
    """Whether the two windows' bands overlap at each age. **Indicative only** —
    it is *not* a significance test for the difference, because the two window
    contrasts are computed from the same fitted coefficients and are therefore
    correlated. A non-overlap is suggestive; an overlap does not establish
    equality."""

    verdict: str
    """``'slowdown'`` (late < early at **every** reference age), ``'acceleration'``
    (late > early at every age), or ``'mixed'`` — which includes the degenerate
    case of an exactly zero delta somewhere, since a zero is neither slower nor
    faster and calling it acceleration would overstate the finding."""

    n_ages_slower: int
    n_ages: int


def _verdict(delta: tuple[float, ...]) -> tuple[str, int]:
    """Classify a set of per-age ``late - early`` deltas, and count the slower ones.

    Both directions are tested strictly rather than one being the negation of the
    other: ``n_slower == 0`` would report ``acceleration`` for a delta of exactly
    zero, which is neither slower nor faster and would overstate the finding
    (PR #185 review [P2]). A pure function so the rule is testable on exact
    inputs, including the zeros a real fit will never produce.
    """
    n_slower = sum(1 for d in delta if d < 0.0)
    n_faster = sum(1 for d in delta if d > 0.0)
    n_ages = len(delta)
    if n_ages and n_slower == n_ages:
        return "slowdown", n_slower
    if n_ages and n_faster == n_ages:
        return "acceleration", n_slower
    return "mixed", n_slower


def _window_mi(
    result: MISurfaceResult,
    ages: np.ndarray,
    start_year: int,
    end_year: int,
    confidence_level: float,
) -> WindowMI:
    """Annualised MI over ``[start_year, end_year]`` with an exact delta-method band.

    Asking :meth:`MISurfaceResult.improvement_surface` for the **two-year** grid
    ``[start, end]`` makes its single annual "step" the contrast
    ``η(x, end) - η(x, start)`` — which is exactly the window contrast, since the
    per-year steps telescope. The band it returns is therefore the delta-method
    interval for the *window*, not a per-year one re-scaled; nothing is
    approximated. Annualising divides that log-change by the number of steps, a
    monotone transform, so the band's endpoints carry through.
    """
    surface = result.improvement_surface(
        ages=ages,
        years=np.array([start_year, end_year], dtype=np.int64),
        confidence_level=confidence_level,
    )
    n_steps = end_year - start_year

    def annualise(grid: np.ndarray) -> tuple[float, ...]:
        # grid is (A, 1): total MI over the window. 1 - MI = exp(Δη) > 0 always.
        total = grid[:, 0].astype(np.float64)
        return tuple(float(x) for x in 1.0 - np.power(1.0 - total, 1.0 / n_steps))

    return WindowMI(
        start_year=start_year,
        end_year=end_year,
        ages=tuple(int(a) for a in surface.ages),
        annualised_mi=annualise(surface.mi_grid),
        lower=annualise(surface.mi_lower),
        upper=annualise(surface.mi_upper),
    )


def default_windows(min_year: int, max_year: int) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Pick disjoint early/late windows from an observed calendar range.

    Ranges of 20+ years get two 10-year windows at the ends (HMD 1990-2019 ->
    1990-1999 vs 2010-2019, the exact comparison the documented US slowdown is
    stated in). Shorter ranges are split into contiguous halves. Returns ``None``
    when the range is too short to form two windows each spanning an annual step.
    """
    n_years = max_year - min_year + 1
    if n_years < _MIN_YEARS_FOR_WINDOWS:
        return None
    if n_years >= 2 * _LONG_WINDOW:
        return (
            (min_year, min_year + _LONG_WINDOW - 1),
            (max_year - _LONG_WINDOW + 1, max_year),
        )
    half = n_years // 2
    return (min_year, min_year + half - 1), (min_year + half, max_year)


def _compare_windows(
    result: MISurfaceResult,
    ages: np.ndarray,
    early: tuple[int, int],
    late: tuple[int, int],
    confidence_level: float,
) -> WindowComparison:
    early_mi = _window_mi(result, ages, early[0], early[1], confidence_level)
    late_mi = _window_mi(result, ages, late[0], late[1], confidence_level)

    delta = tuple(
        late - early
        for late, early in zip(late_mi.annualised_mi, early_mi.annualised_mi, strict=True)
    )
    overlap = tuple(
        not (lu < el or eu < ll)
        for el, eu, ll, lu in zip(
            early_mi.lower, early_mi.upper, late_mi.lower, late_mi.upper, strict=True
        )
    )
    verdict, n_slower = _verdict(delta)
    n_ages = len(delta)

    return WindowComparison(
        early=early_mi,
        late=late_mi,
        delta=delta,
        bands_overlap=overlap,
        verdict=verdict,
        n_ages_slower=n_slower,
        n_ages=n_ages,
    )


# --- SOA's published expected deaths (the independent check) --------------------


@dataclass(frozen=True)
class AEByYear:
    """A/E by calendar year against SOA's own published expected deaths."""

    frame: pl.DataFrame
    """``calendar_year, actual, expected, expected_mi, ae, ae_mi``."""

    ae_mi_slope_per_year: float
    """Exposure-weighted OLS slope of ``ae_mi`` on calendar year. **Flat is
    agreement**: a systematic drift means our experience window disagrees with the
    improvement SOA applied, by a measurable amount in a specific direction."""

    ae_mi_relative_drift_per_year: float
    """The slope as a fraction of the mean ``ae_mi`` — the same finding in units
    that compare across books ("A/E drifts 0.4%/yr")."""

    overall_ae: float
    overall_ae_mi: float


@dataclass(frozen=True)
class SoaSurfaceComparison:
    """Our fitted ``MI_x(y)`` against SOA's own, age by age and year by year.

    SOA publishes expected deaths both without and with mortality improvement on
    identical cells, so their ratio *is* SOA's cumulative MI factor — and its
    year-over-year change within a fixed attained age is SOA's annual improvement
    at that age. That makes this a surface-to-surface comparison in the same units,
    with no model of ours standing in between.
    """

    frame: pl.DataFrame
    """``attained_age, calendar_year, soa_mi, fitted_mi, difference``."""

    mean_difference: float
    """Weighted mean of ``fitted_mi - soa_mi``. Positive = we fit *more*
    improvement than SOA assumed."""

    mean_absolute_difference: float
    weight_column: str


def _ae_by_year(cells: pl.DataFrame, *, deaths_col: str, expected: tuple[str, str]) -> AEByYear:
    """A/E by calendar year, plus the drift in A/E-with-improvement."""
    plain, with_mi = expected
    frame = (
        cells.group_by("calendar_year")
        .agg(
            pl.col(deaths_col).sum().alias("actual"),
            pl.col(plain).sum().alias("expected"),
            pl.col(with_mi).sum().alias("expected_mi"),
        )
        .sort("calendar_year")
        .with_columns(
            (pl.col("actual") / pl.col("expected")).alias("ae"),
            (pl.col("actual") / pl.col("expected_mi")).alias("ae_mi"),
        )
    )

    years = frame["calendar_year"].to_numpy().astype(np.float64)
    ae_mi = frame["ae_mi"].to_numpy().astype(np.float64)
    weights = frame["expected_mi"].to_numpy().astype(np.float64)
    slope = _weighted_slope(years, ae_mi, weights)
    mean_ae_mi = float(np.average(ae_mi, weights=weights)) if weights.sum() > 0 else float("nan")

    return AEByYear(
        frame=frame,
        ae_mi_slope_per_year=slope,
        ae_mi_relative_drift_per_year=slope / mean_ae_mi if mean_ae_mi else float("nan"),
        overall_ae=float(frame["actual"].sum()) / float(frame["expected"].sum()),
        overall_ae_mi=float(frame["actual"].sum()) / float(frame["expected_mi"].sum()),
    )


def _weighted_slope(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    """Weighted least-squares slope of ``y`` on ``x``. NaN if ``x`` does not vary."""
    total = float(w.sum())
    if total <= 0.0 or len(x) < 2:
        return float("nan")
    x_bar = float(np.average(x, weights=w))
    y_bar = float(np.average(y, weights=w))
    var = float(np.sum(w * (x - x_bar) ** 2))
    if var <= 0.0:
        return float("nan")
    return float(np.sum(w * (x - x_bar) * (y - y_bar)) / var)


def _soa_surface_comparison(
    cells: pl.DataFrame,
    surface: MISurface,
    *,
    expected: tuple[str, str],
    reference_ages: tuple[int, ...],
) -> SoaSurfaceComparison | None:
    """Compare our ``MI_x(y)`` to SOA's implied one at the reference ages.

    Returns ``None`` when no (age, year) pair survives the join — e.g. a fixture
    with a single calendar year, where no annual step exists.
    """
    plain, with_mi = expected
    per_age = (
        cells.filter(pl.col("attained_age").is_in(list(reference_ages)))
        .group_by(["attained_age", "calendar_year"])
        .agg(
            pl.col(plain).sum().alias("_expected"),
            pl.col(with_mi).sum().alias("_expected_mi"),
        )
        # Both legs must be positive to form a ratio. A cell whose with-MI leg
        # summed to zero (every contributing row null) would otherwise yield
        # factor 0 and a nonsensical 100% improvement in the next step.
        .filter((pl.col("_expected") > 0.0) & (pl.col("_expected_mi") > 0.0))
        .with_columns((pl.col("_expected_mi") / pl.col("_expected")).alias("_factor"))
        .sort(["attained_age", "calendar_year"])
    )
    if per_age.height == 0:
        return None

    # SOA's annual MI at an age: 1 - factor(y) / factor(y-1). Only consecutive
    # years form a step, so a gap in the calendar axis is dropped rather than
    # silently annualised over a multi-year jump.
    per_age = per_age.with_columns(
        pl.col("_factor").shift(1).over("attained_age").alias("_prev_factor"),
        pl.col("calendar_year").shift(1).over("attained_age").alias("_prev_year"),
        pl.col("_expected_mi").alias("_weight"),
    ).filter(
        pl.col("_prev_factor").is_not_null()
        & (pl.col("calendar_year") - pl.col("_prev_year") == 1)
        & (pl.col("_prev_factor") > 0.0)
    )
    if per_age.height == 0:
        return None
    per_age = per_age.with_columns(
        (1.0 - pl.col("_factor") / pl.col("_prev_factor")).alias("soa_mi")
    )

    fitted = surface.to_frame().select(
        pl.col("attained_age").cast(pl.Int64),
        pl.col("calendar_year").cast(pl.Int64),
        pl.col("mi").alias("fitted_mi"),
    )
    joined = (
        per_age.select(
            pl.col("attained_age").cast(pl.Int64),
            pl.col("calendar_year").cast(pl.Int64),
            "soa_mi",
            "_weight",
        )
        .join(fitted, on=["attained_age", "calendar_year"], how="inner")
        .with_columns((pl.col("fitted_mi") - pl.col("soa_mi")).alias("difference"))
        .sort(["attained_age", "calendar_year"])
    )
    if joined.height == 0:
        return None

    w = joined["_weight"].to_numpy().astype(np.float64)
    diff = joined["difference"].to_numpy().astype(np.float64)
    if w.sum() <= 0.0:
        w = np.ones_like(diff)
    return SoaSurfaceComparison(
        frame=joined.drop("_weight"),
        mean_difference=float(np.average(diff, weights=w)),
        mean_absolute_difference=float(np.average(np.abs(diff), weights=w)),
        weight_column="expected_deaths_with_mi",
    )


# --- The report -----------------------------------------------------------------


@dataclass(frozen=True)
class DiligenceReport:
    """A complete, committable finding from one diligence run.

    Serialises to JSON with no timestamp and no absolute path, so re-running over
    the same cache reproduces it byte for byte and the diff of a committed finding
    means something.
    """

    source: str
    inputs: dict[str, JsonValue]
    aggregation: dict[str, JsonValue]
    base: dict[str, JsonValue]
    fit: dict[str, JsonValue]
    surface: pl.DataFrame
    """``attained_age, calendar_year, mi, mi_lower, mi_upper`` at the reference ages."""

    window_comparison: WindowComparison | None
    ae_by_year: AEByYear | None
    soa_comparison: SoaSurfaceComparison | None
    caveats: tuple[str, ...]
    polaris_version: str = __version__
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, JsonValue]:
        """The report as plain JSON-serialisable data."""
        out: dict[str, JsonValue] = {
            "schema_version": self.schema_version,
            "polaris_version": self.polaris_version,
            "source": self.source,
            "inputs": self.inputs,
            "aggregation": self.aggregation,
            "base": self.base,
            "fit": self.fit,
            "improvement_surface": _frame_records(self.surface),
            "caveats": list(self.caveats),
        }
        if self.window_comparison is not None:
            wc = self.window_comparison
            out["window_comparison"] = {
                "verdict": wc.verdict,
                "n_ages_slower": wc.n_ages_slower,
                "n_ages": wc.n_ages,
                "early_window": [wc.early.start_year, wc.early.end_year],
                "late_window": [wc.late.start_year, wc.late.end_year],
                "rows": [
                    {
                        "attained_age": age,
                        "early_annualised_mi": e,
                        "early_lower": el,
                        "early_upper": eu,
                        "late_annualised_mi": late,
                        "late_lower": ll,
                        "late_upper": lu,
                        "delta": d,
                        "bands_overlap": overlap,
                    }
                    for age, e, el, eu, late, ll, lu, d, overlap in zip(
                        wc.early.ages,
                        wc.early.annualised_mi,
                        wc.early.lower,
                        wc.early.upper,
                        wc.late.annualised_mi,
                        wc.late.lower,
                        wc.late.upper,
                        wc.delta,
                        wc.bands_overlap,
                        strict=True,
                    )
                ],
                "bands_overlap_is_not_a_significance_test": True,
            }
        if self.ae_by_year is not None:
            ae = self.ae_by_year
            out["ae_by_year"] = {
                "overall_ae": ae.overall_ae,
                "overall_ae_with_mi": ae.overall_ae_mi,
                "ae_mi_slope_per_year": ae.ae_mi_slope_per_year,
                "ae_mi_relative_drift_per_year": ae.ae_mi_relative_drift_per_year,
                "rows": _frame_records(ae.frame),
            }
        if self.soa_comparison is not None:
            sc = self.soa_comparison
            out["soa_surface_comparison"] = {
                "mean_difference": sc.mean_difference,
                "mean_absolute_difference": sc.mean_absolute_difference,
                "weight_column": sc.weight_column,
                "rows": _frame_records(sc.frame),
            }
        return {key: _round_json(value) for key, value in out.items()}

    def to_json(self, *, indent: int = 2) -> str:
        """Reproducible JSON — same inputs, same bytes.

        See :data:`REPORT_SIGNIFICANT_DIGITS` for why "same bytes" needs a
        rounding step rather than following from the absence of a clock.
        """
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False, allow_nan=True)


def _round_significant(value: float) -> float:
    """Round to :data:`REPORT_SIGNIFICANT_DIGITS` significant digits."""
    if not math.isfinite(value) or value == 0.0:
        return value
    exponent = math.floor(math.log10(abs(value)))
    return round(value, REPORT_SIGNIFICANT_DIGITS - 1 - exponent)


def _round_json(value: JsonValue) -> JsonValue:
    """Recursively round every float in a report payload. Ints and bools pass
    through untouched (``bool`` is checked first — it is an ``int`` subclass)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return _round_significant(value)
    if isinstance(value, dict):
        return {k: _round_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_json(v) for v in value]
    return value


def _frame_records(frame: pl.DataFrame) -> list[JsonValue]:
    """Rows as JSON-safe dicts, with non-finite floats passed through as-is."""
    records: list[JsonValue] = []
    for row in frame.iter_rows(named=True):
        record: dict[str, JsonValue] = {}
        for key, value in row.items():
            if isinstance(value, bool | str) or value is None:
                record[key] = value
            elif isinstance(value, int):
                record[key] = int(value)
            elif isinstance(value, float):
                record[key] = float(value)
            else:
                record[key] = str(value)
        records.append(record)
    return records


# --- Markdown rendering ---------------------------------------------------------


def _fmt(value: float, *, pct: bool = False, places: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value * 100:.{places - 2}f}%" if pct else f"{value:.{places}f}"


def render_markdown(report: DiligenceReport) -> str:
    """Render the report as a Markdown document — the committable artefact."""
    lines: list[str] = []
    add = lines.append

    add(f"# Experience GAM diligence — {report.source.upper()}")
    add("")
    add(
        f"Generated by `scripts/experience_diligence.py` (polaris-re "
        f"{report.polaris_version}, report schema v{report.schema_version}). "
        f"No plots, no timestamps: re-running over the same cache reproduces this "
        f"file byte for byte."
    )
    add("")

    add("## Inputs")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    for key, value in report.inputs.items():
        add(f"| `{key}` | {value} |")
    add("")

    add("## Aggregation")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    for key, value in report.aggregation.items():
        add(f"| `{key}` | {value} |")
    add("")

    add("## Base rate")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    for key, value in report.base.items():
        add(f"| `{key}` | {value} |")
    add("")

    add("## Fit diagnostics")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    for key, value in report.fit.items():
        add(f"| `{key}` | {value} |")
    add("")

    if report.window_comparison is not None:
        wc = report.window_comparison
        add("## Improvement slowdown test")
        add("")
        add(
            f"**Verdict: `{wc.verdict}`** — annualised improvement is lower in "
            f"{wc.late.start_year}-{wc.late.end_year} than in "
            f"{wc.early.start_year}-{wc.early.end_year} at {wc.n_ages_slower} of "
            f"{wc.n_ages} reference ages."
        )
        add("")
        add(
            "The band on each window is the exact delta-method interval for that "
            "window's contrast. The overlap column is **indicative only** — the two "
            "contrasts come from the same fitted coefficients and are correlated, so "
            "this is not a significance test for the difference."
        )
        add("")
        add(
            f"| Age | MI {wc.early.start_year}-{wc.early.end_year} | band | "
            f"MI {wc.late.start_year}-{wc.late.end_year} | band | Δ | bands overlap |"
        )
        add("|---:|---:|---|---:|---|---:|:---:|")
        for i, age in enumerate(wc.early.ages):
            add(
                f"| {age} | {_fmt(wc.early.annualised_mi[i], pct=True)} | "
                f"{_fmt(wc.early.lower[i], pct=True)} to {_fmt(wc.early.upper[i], pct=True)} | "
                f"{_fmt(wc.late.annualised_mi[i], pct=True)} | "
                f"{_fmt(wc.late.lower[i], pct=True)} to {_fmt(wc.late.upper[i], pct=True)} | "
                f"{_fmt(wc.delta[i], pct=True)} | {'yes' if wc.bands_overlap[i] else 'no'} |"
            )
        add("")

    if report.ae_by_year is not None:
        ae = report.ae_by_year
        add("## A/E against SOA's published expected deaths")
        add("")
        add(
            f"Overall A/E **{ae.overall_ae:.4f}** on the VBT 2015 basis, "
            f"**{ae.overall_ae_mi:.4f}** with SOA's mortality improvement. The "
            f"finding is the *drift*, not the level: A/E-with-MI moves "
            f"**{ae.ae_mi_slope_per_year:+.5f} per year** "
            f"({ae.ae_mi_relative_drift_per_year * 100:+.3f}% of its mean). Flat is "
            f"agreement with SOA's improvement assumption; a slope is a "
            f"disagreement of measurable size and direction."
        )
        add("")
        add("| Year | Actual | Expected | Expected (w/ MI) | A/E | A/E (w/ MI) |")
        add("|---:|---:|---:|---:|---:|---:|")
        for row in ae.frame.iter_rows(named=True):
            add(
                f"| {row['calendar_year']} | {row['actual']:,.1f} | "
                f"{row['expected']:,.1f} | {row['expected_mi']:,.1f} | "
                f"{row['ae']:.4f} | {row['ae_mi']:.4f} |"
            )
        add("")

    if report.soa_comparison is not None:
        sc = report.soa_comparison
        add("## Fitted MI vs SOA's own MI")
        add("")
        add(
            f"SOA's expected-with-MI over expected-without is their cumulative "
            f"improvement factor on identical cells; its year-over-year change "
            f"within a fixed attained age is their annual MI. Weighted mean "
            f"difference (ours minus theirs): **{sc.mean_difference:+.5f}**, mean "
            f"absolute **{sc.mean_absolute_difference:.5f}**."
        )
        add("")
        add("| Age | Year | SOA MI | Fitted MI | Δ |")
        add("|---:|---:|---:|---:|---:|")
        for row in sc.frame.iter_rows(named=True):
            add(
                f"| {row['attained_age']} | {row['calendar_year']} | "
                f"{_fmt(row['soa_mi'], pct=True)} | {_fmt(row['fitted_mi'], pct=True)} | "
                f"{_fmt(row['difference'], pct=True)} |"
            )
        add("")

    add("## Improvement surface at the reference ages")
    add("")
    add("| Age | Year | MI | lower | upper |")
    add("|---:|---:|---:|---:|---:|")
    for row in report.surface.iter_rows(named=True):
        add(
            f"| {row['attained_age']} | {row['calendar_year']} | "
            f"{_fmt(row['mi'], pct=True)} | {_fmt(row['mi_lower'], pct=True)} | "
            f"{_fmt(row['mi_upper'], pct=True)} |"
        )
    add("")

    add("## Caveats")
    add("")
    for caveat in report.caveats:
        add(f"- {caveat}")
    add("")
    return "\n".join(lines)


# --- The harness ----------------------------------------------------------------


def _filter_window(
    cells: pl.DataFrame,
    *,
    min_year: int | None,
    max_year: int | None,
    min_age: int | None,
    max_age: int | None,
) -> pl.DataFrame:
    predicates: list[pl.Expr] = []
    if min_year is not None:
        predicates.append(pl.col("calendar_year") >= min_year)
    if max_year is not None:
        predicates.append(pl.col("calendar_year") <= max_year)
    if min_age is not None:
        predicates.append(pl.col("attained_age") >= min_age)
    if max_age is not None:
        predicates.append(pl.col("attained_age") <= max_age)
    for pred in predicates:
        cells = cells.filter(pred)
    return cells


def _regroup(
    cells: pl.DataFrame, keys: tuple[str, ...], sum_columns: tuple[str, ...]
) -> pl.DataFrame:
    """Sum the measures over ``keys``, keeping only keys actually present."""
    present = [k for k in keys if k in cells.columns]
    if not present:
        raise PolarisValidationError(
            f"None of the requested grouping keys {list(keys)} are present in the "
            f"loaded cells (columns: {cells.columns})."
        )
    return (
        cells.group_by(present)
        .agg([pl.col(c).sum().alias(c) for c in sum_columns if c in cells.columns])
        .sort(present)
    )


def run_diligence(
    *,
    source: str,
    cache_dir: str | Path | None = None,
    country: str = "USA",
    ilec_filename: str | None = None,
    ilec_vintage: str = "2012-19",
    ilec_separator: str | None = None,
    include_expected: bool = True,
    basis: str = "count",
    min_year: int | None = None,
    max_year: int | None = None,
    min_age: int | None = 25,
    max_age: int | None = 95,
    group_keys: tuple[str, ...] | None = None,
    reference_ages: tuple[int, ...] = DEFAULT_REFERENCE_AGES,
    early_window: tuple[int, int] | None = None,
    late_window: tuple[int, int] | None = None,
    age_df: int = 6,
    year_df: int = 4,
    confidence_level: float = 0.95,
    keep_unknown_uw_class: bool = False,
) -> DiligenceReport:
    """Load a real experience cache, fit the tensor MI surface, and report findings.

    Args:
        source:            ``"hmd"`` (population) or ``"ilec"`` (insured).
        cache_dir:         Cache root override; defaults to the loaders' resolution
                           order (``$POLARIS_EXPERIENCE_CACHE_DIR`` first).
        country:           HMD country code. Ignored for ILEC.
        ilec_filename:     ILEC file name within ``{cache}/ilec/``; required when
                           the directory holds more than one candidate.
        ilec_vintage:      Key into :data:`ILEC_VINTAGES` — selects the header
                           spelling *and* the delimiter.
        ilec_separator:    Override the vintage's delimiter.
        include_expected:  Carry SOA's published expected deaths (ILEC only) and
                           produce the A/E and surface-comparison sections. Turn
                           off for a vintage that does not publish them.
        basis:             ``"count"`` or ``"amount"``.
        min_year/max_year: Inclusive calendar window. Leaving ``max_year`` open on
                           HMD will pull the COVID years into a smooth surface,
                           which attributes a shock to improvement — pass 2019.
        min_age/max_age:   Inclusive attained-age window.
        group_keys:        Aggregation level. Defaults to :data:`HMD_GROUP_KEYS` /
                           :data:`ILEC_GROUP_KEYS`.
        reference_ages:    Ages the surface and comparisons are reported at.
        early_window:      ``(start, end)`` for the early comparison window;
                           defaults via :func:`default_windows`.
        late_window:       ``(start, end)`` for the late window.
        age_df/year_df:    Spline degrees of freedom for the tensor margins.
        confidence_level:  Two-sided level for the delta-method bands.
        keep_unknown_uw_class: Keep ILEC ``uw_class == "U"`` rows (the missing-data
                           sentinel). Off by default — unknown underwriting is not
                           a stratum, and pooling it with underwritten business
                           would misattribute its mortality.

    Returns:
        A :class:`DiligenceReport`.

    Raises:
        PolarisValidationError: On an unknown source/vintage, a missing or
            ambiguous cache, an unusable aggregation level, or a window outside
            the observed calendar range.
        PolarisComputationError: If the GAM backend is absent or the fit diverges.
    """
    source = source.lower()
    if source not in {"hmd", "ilec"}:
        raise PolarisValidationError(f"Unknown source {source!r}; expected 'hmd' or 'ilec'.")
    if basis not in {"count", "amount"}:
        raise PolarisValidationError(f"basis must be 'count' or 'amount', got {basis!r}.")

    exposure_col, deaths_col = COUNT_MEASURES if basis == "count" else AMOUNT_MEASURES
    expected_cols = (
        ILEC_EXPECTED_COUNT_MEASURES if basis == "count" else ILEC_EXPECTED_AMOUNT_MEASURES
    )
    caveats: list[str] = []
    inputs: dict[str, JsonValue] = {"source": source, "basis": basis}

    # --- Load ------------------------------------------------------------------
    if source == "hmd":
        # Checked before the load: the 1x1 files are large and the answer does not
        # depend on reading them.
        if basis == "amount":
            raise PolarisValidationError(
                "HMD is population data and carries no face amounts — basis='amount' "
                "is only meaningful for ILEC."
            )
        deaths_path, exposures_path = resolve_hmd_paths(country, cache_dir=cache_dir)
        cells = load_hmd(
            deaths_path,
            exposures_path,
            min_year=min_year,
            max_year=max_year,
            min_age=min_age,
            max_age=max_age,
        )
        inputs.update(
            {
                "country": country,
                # Basenames only: a committed finding must not carry a home directory.
                "deaths_file": deaths_path.name,
                "exposures_file": exposures_path.name,
                "deaths_file_bytes": deaths_path.stat().st_size,
                "exposures_file_bytes": exposures_path.stat().st_size,
            }
        )
        default_keys = HMD_GROUP_KEYS
        carry_expected = False
    else:
        if ilec_vintage not in ILEC_VINTAGES:
            raise PolarisValidationError(
                f"Unknown ILEC vintage {ilec_vintage!r}; expected one of {sorted(ILEC_VINTAGES)}."
            )
        vintage = ILEC_VINTAGES[ilec_vintage]
        separator = ilec_separator if ilec_separator is not None else vintage.separator
        path = resolve_ilec_path(cache_dir=cache_dir, filename=ilec_filename)
        cells = load_ilec(
            path,
            basis=basis,
            column_map=vintage.column_map,
            separator=separator,
            include_expected=include_expected,
        )
        cells = _filter_window(
            cells, min_year=min_year, max_year=max_year, min_age=min_age, max_age=max_age
        )
        inputs.update(
            {
                "ilec_file": path.name,
                "ilec_file_bytes": path.stat().st_size,
                "vintage": vintage.name,
                "separator": repr(separator),
                "include_expected": include_expected,
            }
        )
        default_keys = ILEC_GROUP_KEYS
        carry_expected = include_expected

    if cells.height == 0:
        raise PolarisValidationError(
            "No cells survived the year/age filters — check --min-year/--max-year "
            "and --min-age/--max-age against the file's actual coverage."
        )

    n_loaded = cells.height

    # --- Hold the unknown underwriting class out of class-conditioned inference --
    keys = group_keys if group_keys is not None else default_keys
    n_unknown_uw = 0
    if "uw_class" in cells.columns and "uw_class" in keys and not keep_unknown_uw_class:
        unknown = cells.filter(pl.col("uw_class").cast(pl.Utf8) == UNKNOWN_UW_CLASS)
        n_unknown_uw = unknown.height
        if n_unknown_uw:
            cells = cells.filter(pl.col("uw_class").cast(pl.Utf8) != UNKNOWN_UW_CLASS)
            caveats.append(
                f"{n_unknown_uw:,} cells with uw_class == 'U' (underwriting class "
                f"*unknown*, not *not applicable*) were held out of this "
                f"class-conditioned fit. 'NA' rows are retained as their own "
                f"stratum. Pass keep_unknown_uw_class=True to include them."
            )
        if cells.height == 0:
            raise PolarisValidationError(
                "Every cell has uw_class == 'U'; nothing is left after holding the "
                "unknown class out. Pass keep_unknown_uw_class=True, or drop "
                "'uw_class' from the grouping keys."
            )

    # --- Aggregate to the stated level -----------------------------------------
    sum_columns: tuple[str, ...] = (exposure_col, deaths_col)
    if carry_expected:
        sum_columns = (*sum_columns, *expected_cols)
    grouped = _regroup(cells, keys, sum_columns)
    used_keys = tuple(k for k in keys if k in cells.columns)
    if len(used_keys) < len(keys):
        # A typo in --group-by would otherwise coarsen the fit silently, which is
        # the one direction the plan calls hazardous.
        caveats.append(
            f"Requested grouping key(s) {sorted(set(keys) - set(used_keys))} are not "
            f"present in the loaded cells and were ignored — the fit is COARSER than "
            f"asked for. Present columns: {sorted(cells.columns)}."
        )
    dropped_keys = tuple(
        c
        for c in cells.columns
        if c not in used_keys and c not in sum_columns and not c.startswith("_")
    )

    # --- Base rate --------------------------------------------------------------
    base = attach_empirical_base(grouped, exposure_col=exposure_col, deaths_col=deaths_col)
    fit_cells = base.cells
    if base.n_strata_dropped:
        caveats.append(
            f"{base.n_strata_dropped:,} base strata "
            f"({base.dropped_exposure_share * 100:.3f}% of exposure) had zero deaths "
            f"across the whole window and were dropped — their base rate is not "
            f"estimable and they carry no trend information."
        )

    # --- Fit --------------------------------------------------------------------
    model = TensorMIModel(
        fit_cells,
        basis=basis,
        age_df=age_df,
        year_df=year_df,
        age_varying=True,
    )
    result = model.fit()

    observed_min, observed_max = result.observed_years
    ref_ages = tuple(
        a for a in reference_ages if result.observed_ages[0] <= a <= result.observed_ages[1]
    )
    if not ref_ages:
        raise PolarisValidationError(
            f"No reference age in {list(reference_ages)} lies inside the observed "
            f"attained-age range {result.observed_ages}. Pass reference_ages that "
            f"the data covers."
        )
    if len(ref_ages) < len(reference_ages):
        # Silently reporting on fewer ages than were asked for would read as a
        # thinner finding rather than a narrower age window.
        caveats.append(
            f"Reference age(s) "
            f"{sorted(set(reference_ages) - set(ref_ages))} lie outside the observed "
            f"attained-age range {list(result.observed_ages)} and were not reported. "
            f"The surface is not extrapolated beyond the data."
        )
    ref_age_array = np.array(ref_ages, dtype=np.int64)

    surface = result.improvement_surface(
        ages=ref_age_array,
        years=np.arange(observed_min, observed_max + 1, dtype=np.int64),
        confidence_level=confidence_level,
    )

    # --- Window comparison ------------------------------------------------------
    comparison: WindowComparison | None = None
    if early_window is None or late_window is None:
        windows = default_windows(observed_min, observed_max)
        if windows is None:
            caveats.append(
                f"Only {observed_max - observed_min + 1} calendar year(s) observed — "
                f"too few to form two disjoint comparison windows, so the "
                f"improvement-slowdown test was not run."
            )
        else:
            early_window, late_window = windows
    if early_window is not None and late_window is not None:
        for label, window in (("early", early_window), ("late", late_window)):
            if window[0] >= window[1]:
                raise PolarisValidationError(
                    f"The {label} window {window} must span at least one annual step (start < end)."
                )
            if window[0] < observed_min or window[1] > observed_max:
                raise PolarisValidationError(
                    f"The {label} window {window} falls outside the observed calendar "
                    f"range ({observed_min}, {observed_max}). The surface is not "
                    f"extrapolated beyond the data."
                )
        if early_window[1] > late_window[0]:
            caveats.append(
                f"The early {early_window} and late {late_window} windows overlap, so "
                f"the two contrasts share annual steps and the comparison understates "
                f"any difference."
            )
        comparison = _compare_windows(
            result, ref_age_array, early_window, late_window, confidence_level
        )

    # --- SOA's independent denominator (ILEC only) ------------------------------
    ae: AEByYear | None = None
    soa: SoaSurfaceComparison | None = None
    if carry_expected and all(c in cells.columns for c in expected_cols):
        # The loader's group-and-sum turns a null expected-death value into a
        # zero, so by here a partially-populated vintage looks like a cell that
        # simply expects no deaths. Detected as *positive exposure with a
        # non-positive denominator*, which is the shape the damage actually takes:
        # those cells add to the numerator and nothing to the denominator, biasing
        # every A/E upward. Reported rather than silently absorbed.
        missing_expected = cells.filter(
            (pl.col(exposure_col) > 0.0)
            & pl.any_horizontal([pl.col(c).is_null() | (pl.col(c) <= 0.0) for c in expected_cols])
        )
        if missing_expected.height:
            share = float(missing_expected[exposure_col].sum()) / float(cells[exposure_col].sum())
            caveats.append(
                f"{missing_expected.height:,} cells ({share * 100:.3f}% of exposure) "
                f"have positive exposure but null or zero SOA expected deaths. They "
                f"add to the numerator and nothing to the denominator, so the A/E "
                f"ratios below are biased upward by that much."
            )
        # A/E deliberately runs over the whole loaded book, not over the fitted
        # cells: SOA's published denominator covers every cell they priced, and
        # narrowing it to ours would make the ratio answer a different question.
        # Whenever the two populations actually differ, say so — a reader of a
        # committed finding should not have to derive it from `n_cells_grouped`
        # vs `n_cells_fitted` (PR #185 review [P2]).
        if base.n_strata_dropped:
            caveats.append(
                f"The A/E section covers the full loaded book "
                f"({grouped.height:,} cells), while the fitted surface covers "
                f"{fit_cells.height:,} — the zero-death strata above are excluded "
                f"from the fit but retained in A/E, because SOA's denominator "
                f"covers every cell they priced. The two populations differ by "
                f"{base.dropped_exposure_share * 100:.3f}% of exposure."
            )
        ae = _ae_by_year(cells, deaths_col=deaths_col, expected=expected_cols)
        soa = _soa_surface_comparison(
            cells, surface, expected=expected_cols, reference_ages=ref_ages
        )
        if soa is None:
            caveats.append(
                "No (reference age, consecutive year) pair carried SOA expected "
                "deaths, so the fitted-vs-SOA surface comparison was skipped."
            )

    # --- Standing caveats -------------------------------------------------------
    if "duration_months" not in used_keys and source == "ilec":
        caveats.append(
            "Cells are pooled across duration, so select-period mortality is "
            "absorbed into the attained-age effect. If the duration mix drifts with "
            "calendar year, part of that drift lands in the fitted improvement. Pass "
            "group_keys including 'duration_months' to separate them, at ~60x the "
            "cell count."
        )
    caveats.append(
        "The base offset is estimated from these same cells, so `overall_ae` is ~1 "
        "by construction and is not an independent check on the level. The fitted "
        "improvement is unaffected: it is a calendar contrast, and every "
        "calendar-invariant term — the offset included — cancels in the difference."
    )
    if source == "hmd" and (max_year is None or max_year >= 2020):
        caveats.append(
            "The calendar window reaches 2020 or later. A smooth tensor surface "
            "fitted through the COVID shock attributes it to improvement, which is "
            "wrong. Fit 1990-2019 and treat 2020+ as a separate window."
        )

    aggregation: dict[str, JsonValue] = {
        "group_keys": list(used_keys),
        "dropped_keys": list(dropped_keys),
        "n_cells_loaded": n_loaded,
        "n_cells_grouped": grouped.height,
        "n_cells_fitted": fit_cells.height,
        "n_cells_unknown_uw_class_excluded": n_unknown_uw,
        "total_exposure": float(fit_cells[exposure_col].sum()),
        "total_deaths": float(fit_cells[deaths_col].sum()),
    }
    base_info: dict[str, JsonValue] = {
        "kind": "empirical (pooled crude rate over the calendar window)",
        "keys": list(base.keys),
        "n_strata": base.n_strata,
        "n_strata_dropped": base.n_strata_dropped,
        "dropped_exposure_share": base.dropped_exposure_share,
        "n_clipped_above_one": base.n_clipped,
    }
    fit_info: dict[str, JsonValue] = {
        "basis": result.basis,
        "factors": list(result.factors),
        "age_varying": result.age_varying,
        "n_cells": result.n_cells,
        "overall_ae": result.overall_ae,
        "dispersion": result.dispersion,
        "overdispersion_applied": result.overdispersion_applied,
        "observed_ages": list(result.observed_ages),
        "observed_years": list(result.observed_years),
        "age_df": age_df,
        "year_df": year_df,
        "confidence_level": confidence_level,
        "reference_ages": list(ref_ages),
    }

    return DiligenceReport(
        source=source,
        inputs=inputs,
        aggregation=aggregation,
        base=base_info,
        fit=fit_info,
        surface=surface.to_frame(),
        window_comparison=comparison,
        ae_by_year=ae,
        soa_comparison=soa,
        caveats=tuple(caveats),
    )

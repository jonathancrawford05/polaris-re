"""Static matplotlib diagnostic plots for the experience-GAM capability (A4').

Renders the three Slice-4d diagnostics straight from the public data structures
produced by :mod:`polaris_re.analytics.experience_gam` — no re-derivation of
feature ranges or bands:

* :func:`plot_effects` — the fitted per-feature effect shapes from
  :meth:`GAMFitResult.all_effects` (smooths as line + shaded band, factors as
  point + error bars).
* :func:`plot_mi_surface` — 1-D slices of a fitted mortality-improvement
  :class:`~polaris_re.analytics.experience_gam.MISurface` (MI vs calendar year
  for selected ages; MI vs age for selected years), each line + shaded band.
* :func:`plot_mi_surface_bandwidth` — a band-*width* heatmap over the age-by-year
  grid, showing where the surface is well- vs poorly-identified.
* :func:`plot_mi_projection` — a fan chart of a forward
  :class:`~polaris_re.analytics.experience_gam.MIProjection` for one age, where
  the band shape (widest at the join, narrowing to the long-term rate) is the
  point.

**Uncertainty bands are on by default** — they are already first-class in the
data structures, so rendering them is the default, not extra scope. Every band
is captioned with its *kind* (:data:`BandKind`): frequentist ``confidence`` vs
Bayesian ``credible`` vs projection ``posterior-predictive`` are NOT
interchangeable, so the caller declares which one a surface carries.

This module is **dev / report-only**. ``matplotlib`` is imported lazily (only
when a helper is called) and is required via the optional ``[viz]`` extra; the
pricing path never imports it.
"""

from typing import TYPE_CHECKING, Literal

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam import MIProjection, MISurface
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

__all__ = [
    "BandKind",
    "plot_effects",
    "plot_mi_projection",
    "plot_mi_surface",
    "plot_mi_surface_bandwidth",
]

type BandKind = Literal["confidence", "credible", "posterior-predictive"]
"""Which kind of uncertainty band a surface carries. Frequentist ``confidence``
(the statsmodels backend), Bayesian ``credible`` (the HSGP backend), and
``posterior-predictive`` (the forward projection) are NOT interchangeable and
are labelled distinctly in every caption/legend."""

_BAND_KINDS: frozenset[str] = frozenset({"confidence", "credible", "posterior-predictive"})

# House palette (matches dashboard/components/charts.py).
_LINE_COLOR = "#2c3e50"
_BAND_COLOR = "#3498db"
_REF_COLOR = "#e74c3c"
_LTR_COLOR = "#27ae60"


def _require_matplotlib() -> object:
    """Import ``matplotlib.pyplot`` lazily, or raise a clear Polaris error.

    Keeps ``matplotlib`` off every import path except an explicit plot call, so
    ``import polaris_re.viz`` works without the ``[viz]`` extra installed.
    """
    try:
        import matplotlib.pyplot as plt  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised only without [viz]
        raise PolarisComputationError(
            "matplotlib is required for polaris_re.viz plotting helpers; "
            "install the optional extra with `uv sync --extra viz`."
        ) from exc
    return plt


def _band_caption(band_kind: BandKind, confidence_level: float | None) -> str:
    """Human caption for a band, e.g. ``'95% confidence band'``.

    Validates ``band_kind`` against :data:`BandKind` so a mislabelled band
    (which would misrepresent frequentist vs Bayesian uncertainty) fails loudly.
    """
    if band_kind not in _BAND_KINDS:
        raise PolarisValidationError(
            f"band_kind must be one of {sorted(_BAND_KINDS)}, got {band_kind!r}"
        )
    if confidence_level is None:
        return f"{band_kind} band"
    if not 0.0 < confidence_level < 1.0:
        raise PolarisValidationError(f"confidence_level must be in (0, 1), got {confidence_level}")
    return f"{confidence_level * 100:g}% {band_kind} band"


def _pick_representatives(values: np.ndarray, n: int) -> np.ndarray:
    """Up to ``n`` evenly-spaced representative values from a sorted unique set.

    Always includes the extremes (min and max) so a slice plot shows the full
    identified range, not just its interior.
    """
    unique = np.unique(values)
    if unique.size <= n:
        return unique
    idx = np.linspace(0, unique.size - 1, n).round().astype(int)
    return unique[np.unique(idx)]


def plot_effects(
    effects: pl.DataFrame,
    *,
    band_kind: BandKind = "confidence",
    confidence_level: float | None = None,
    title: str | None = None,
) -> "Figure":
    """Plot fitted per-feature effect shapes from :meth:`GAMFitResult.all_effects`.

    One panel per ``feature``. Smooth terms render as a line over ``x_value``
    with a shaded ``fill_between`` band (``lower``/``upper``); factor terms
    render as points with error bars at each level. A dashed reference line
    marks the A/E-neutral multiplier of 1.0.

    Args:
        effects: The tidy long-format frame from
            :meth:`~polaris_re.analytics.experience_gam.GAMFitResult.all_effects`
            (columns ``feature, term_type, x, x_value, multiplier, lower,
            upper``).
        band_kind: Which uncertainty band the frame carries (see
            :data:`BandKind`); labelled in each panel's band legend entry.
        confidence_level: Two-sided level for the caption (e.g. ``0.95``);
            ``None`` omits the percentage.
        title: Figure suptitle; a sensible default is used when ``None``.

    Returns:
        The rendered :class:`matplotlib.figure.Figure` (caller owns closing it).

    Raises:
        PolarisValidationError: If ``effects`` is empty, is missing a required
            column, or ``band_kind`` is not a valid :data:`BandKind`.
    """
    plt = _require_matplotlib()
    required = {"feature", "term_type", "x", "x_value", "multiplier", "lower", "upper"}
    missing = required - set(effects.columns)
    if missing:
        raise PolarisValidationError(
            f"effects frame is missing required columns: {sorted(missing)}"
        )
    if effects.height == 0:
        raise PolarisValidationError("effects frame is empty — nothing to plot.")

    band_label = _band_caption(band_kind, confidence_level)
    features = list(effects["feature"].unique(maintain_order=True))
    fig, axes = plt.subplots(1, len(features), figsize=(5.0 * len(features), 4.2), squeeze=False)

    for ax, feature in zip(axes[0], features, strict=True):
        block = effects.filter(pl.col("feature") == feature)
        term_type = block["term_type"][0]
        if term_type == "smooth":
            _plot_smooth_panel(ax, block, band_label)
        else:
            _plot_factor_panel(ax, block, band_label)
        ax.axhline(1.0, color=_REF_COLOR, linestyle="--", linewidth=0.9, label="A/E = 1")
        ax.set_title(str(feature))
        ax.set_ylabel("A/E multiplier")
        ax.legend(fontsize=8, loc="best")

    fig.suptitle(title or "Experience-GAM fitted effects")
    fig.tight_layout()
    return fig


def _plot_smooth_panel(ax: "Axes", block: pl.DataFrame, band_label: str) -> None:
    """Render one smooth term: line over ``x_value`` + shaded band."""
    x = block["x_value"].to_numpy().astype(np.float64)
    mult = block["multiplier"].to_numpy().astype(np.float64)
    lower = block["lower"].to_numpy().astype(np.float64)
    upper = block["upper"].to_numpy().astype(np.float64)
    order = np.argsort(x)
    ax.fill_between(
        x[order], lower[order], upper[order], color=_BAND_COLOR, alpha=0.25, label=band_label
    )
    ax.plot(x[order], mult[order], color=_LINE_COLOR, linewidth=1.6, label="fitted effect")
    ax.set_xlabel(str(block["feature"][0]))


def _plot_factor_panel(ax: "Axes", block: pl.DataFrame, band_label: str) -> None:
    """Render one factor term: point + error bars per level."""
    labels = [str(v) for v in block["x"].to_list()]
    mult = block["multiplier"].to_numpy().astype(np.float64)
    lower = block["lower"].to_numpy().astype(np.float64)
    upper = block["upper"].to_numpy().astype(np.float64)
    positions = np.arange(len(labels), dtype=np.float64)
    yerr = np.vstack([mult - lower, upper - mult])
    ax.errorbar(
        positions,
        mult,
        yerr=yerr,
        fmt="o",
        color=_LINE_COLOR,
        ecolor=_BAND_COLOR,
        elinewidth=2.0,
        capsize=4.0,
        label=band_label,
    )
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_xlabel(str(block["feature"][0]))


def plot_mi_surface(
    surface: MISurface,
    *,
    ages: list[int] | None = None,
    years: list[int] | None = None,
    band_kind: BandKind = "confidence",
    title: str | None = None,
) -> "Figure":
    """Plot 1-D slices of a mortality-improvement surface with uncertainty bands.

    A 3-D age-by-year surface cannot legibly carry a band, so this renders two
    slice panels instead (the locked Slice-4d choice): left, ``MI`` vs calendar
    year for a few selected ages; right, ``MI`` vs age for a few selected years.
    Each slice is a line + shaded band.

    Args:
        surface: The fitted
            :class:`~polaris_re.analytics.experience_gam.MISurface`.
        ages: Attained ages to slice on the left panel; defaults to the min,
            middle, and max fitted ages. Values not on the surface are ignored.
        years: Step-end calendar years to slice on the right panel; defaults to
            the min, middle, and max fitted years.
        band_kind: Which band the surface carries (``confidence`` for the
            frequentist backend, ``credible`` for the Bayesian one).
        title: Figure suptitle; a sensible default is used when ``None``.

    Returns:
        The rendered :class:`matplotlib.figure.Figure`.

    Raises:
        PolarisValidationError: If no requested age/year lands on the surface,
            or ``band_kind`` is invalid.
    """
    plt = _require_matplotlib()
    band_label = _band_caption(band_kind, surface.confidence_level)

    sel_ages = (
        np.asarray(ages, dtype=np.int64)
        if ages is not None
        else _pick_representatives(surface.ages, 3)
    )
    sel_years = (
        np.asarray(years, dtype=np.int64)
        if years is not None
        else _pick_representatives(surface.years, 3)
    )

    fig, (ax_year, ax_age) = plt.subplots(1, 2, figsize=(12.0, 4.6))

    plotted_age = 0
    for age in sel_ages:
        rows = np.nonzero(surface.ages == age)[0]
        if rows.size == 0:
            continue
        i = int(rows[0])
        ax_year.fill_between(surface.years, surface.mi_lower[i], surface.mi_upper[i], alpha=0.18)
        ax_year.plot(surface.years, surface.mi_grid[i], linewidth=1.6, label=f"age {int(age)}")
        plotted_age += 1
    if plotted_age == 0:
        plt.close(fig)
        raise PolarisValidationError(
            f"none of the requested ages {sel_ages.tolist()} are on the surface "
            f"(ages {int(surface.ages.min())}-{int(surface.ages.max())})."
        )
    ax_year.set_xlabel("calendar year (step end)")
    ax_year.set_ylabel("annual MI rate")
    ax_year.set_title("MI vs calendar year")
    ax_year.legend(fontsize=8, title=band_label)

    plotted_year = 0
    for year in sel_years:
        cols = np.nonzero(surface.years == year)[0]
        if cols.size == 0:
            continue
        j = int(cols[0])
        ax_age.fill_between(
            surface.ages, surface.mi_lower[:, j], surface.mi_upper[:, j], alpha=0.18
        )
        ax_age.plot(surface.ages, surface.mi_grid[:, j], linewidth=1.6, label=f"year {int(year)}")
        plotted_year += 1
    if plotted_year == 0:
        plt.close(fig)
        raise PolarisValidationError(
            f"none of the requested years {sel_years.tolist()} are on the surface "
            f"(years {int(surface.years.min())}-{int(surface.years.max())})."
        )
    ax_age.set_xlabel("attained age")
    ax_age.set_ylabel("annual MI rate")
    ax_age.set_title("MI vs attained age")
    ax_age.legend(fontsize=8, title=band_label)

    fig.suptitle(title or "Mortality-improvement surface slices")
    fig.tight_layout()
    return fig


def plot_mi_surface_bandwidth(
    surface: MISurface,
    *,
    title: str | None = None,
) -> "Figure":
    """Heatmap of band *width* (``mi_upper - mi_lower``) over the age-by-year grid.

    Complements :func:`plot_mi_surface`: rather than painting a band onto a 3-D
    surface (unreadable), this shows *where* the surface is well-identified
    (narrow band, dark) vs poorly-identified (wide band, bright — typically the
    edges and thin cells).

    Args:
        surface: The fitted
            :class:`~polaris_re.analytics.experience_gam.MISurface`.
        title: Figure suptitle; a sensible default is used when ``None``.

    Returns:
        The rendered :class:`matplotlib.figure.Figure`.
    """
    plt = _require_matplotlib()
    width = (surface.mi_upper - surface.mi_lower).astype(np.float64)
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    extent = (
        float(surface.years.min()) - 0.5,
        float(surface.years.max()) + 0.5,
        float(surface.ages.max()) + 0.5,
        float(surface.ages.min()) - 0.5,
    )
    im = ax.imshow(width, aspect="auto", cmap="viridis", extent=extent, interpolation="nearest")
    ax.set_xlabel("calendar year (step end)")
    ax.set_ylabel("attained age")
    ax.set_title(
        title or f"MI band width ({surface.confidence_level * 100:g}% interval, upper - lower)"
    )
    fig.colorbar(im, ax=ax, label="band width")
    fig.tight_layout()
    return fig


def plot_mi_projection(
    projection: MIProjection,
    *,
    age: int | None = None,
    band_kind: BandKind = "posterior-predictive",
    title: str | None = None,
) -> "Figure":
    """Fan chart of a forward MI projection for one attained age.

    The band shape is the point: the credible band is widest at the join (the
    first projected year, where it equals the in-window surface band) and
    narrows as each age's improvement converges to the deterministic
    ``long_term_rate``. A dashed line marks that long-term rate.

    Args:
        projection: The forward
            :class:`~polaris_re.analytics.experience_gam.MIProjection`.
        age: Attained age to chart; defaults to the middle projected age. Must
            be one of the projected ages.
        band_kind: Which band the projection carries; defaults to
            ``posterior-predictive`` (the projection's own kind).
        title: Figure suptitle; a sensible default is used when ``None``.

    Returns:
        The rendered :class:`matplotlib.figure.Figure`.

    Raises:
        PolarisValidationError: If ``age`` is not among the projected ages, or
            ``band_kind`` is invalid.
    """
    plt = _require_matplotlib()
    band_label = _band_caption(band_kind, projection.confidence_level)

    target = int(age) if age is not None else int(_pick_representatives(projection.ages, 1)[0])
    rows = np.nonzero(projection.ages == target)[0]
    if rows.size == 0:
        raise PolarisValidationError(
            f"age {target} is not among the projected ages {projection.ages.tolist()}."
        )
    i = int(rows[0])

    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    ax.fill_between(
        projection.years,
        projection.mi_lower[i],
        projection.mi_upper[i],
        color=_BAND_COLOR,
        alpha=0.25,
        label=band_label,
    )
    ax.plot(
        projection.years,
        projection.mi_grid[i],
        color=_LINE_COLOR,
        linewidth=1.8,
        marker="o",
        markersize=3.0,
        label=f"projected MI (age {target})",
    )
    ax.axhline(
        projection.long_term_rate,
        color=_LTR_COLOR,
        linestyle="--",
        linewidth=1.1,
        label=f"long-term rate {projection.long_term_rate:g}",
    )
    ax.set_xlabel("projected calendar year")
    ax.set_ylabel("annual MI rate")
    ax.set_title(
        title
        or f"MI projection fan — age {target} "
        f"(reverting over {projection.convergence_period}y, {projection.method})"
    )
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    return fig

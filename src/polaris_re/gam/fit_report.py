"""Fit-report honesty for the HGAM dashboard — slice S1 (ADR-265).

Three small, read-only checks that say when a fit or a surface cannot be trusted. All are
MEASUREMENT (own criterion): no second producer, no ``mgcv`` comparison, nothing feeds pricing.

* :func:`saturated_terms` — smooth terms using at least ``SATURATION_THRESHOLD`` (0.95) of their
  coefficients. ``edf <= n_coef`` (the design block width after constraints), so ``edf/n_coef``
  is the fraction of available flexibility used; a value near 1 says the basis, not the
  penalty, may be limiting the fit.
* :func:`mask_surface` — which :class:`~polaris_re.gam.effects.ImprovementSurface` cells have
  no exposure or a band more than :data:`MASK_BAND_MULTIPLE` times the median band.
* :func:`nonpositive_exposure` — rows whose exposure is not strictly positive.

The two constants are fixed in ADR-265 before the first run and are not tuned.
"""

from dataclasses import dataclass

import numpy as np
import polars as pl

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam.api import GamFit
from polaris_re.gam.effects import ImprovementSurface
from polaris_re.gam.summary import SATURATION_THRESHOLD

__all__ = [
    "MASK_BAND_MULTIPLE",
    "SATURATION_THRESHOLD",
    "MaskedSurface",
    "SaturatedTerm",
    "drop_nonpositive_exposure",
    "exposure_vector",
    "mask_surface",
    "nonpositive_exposure",
    "nonpositive_exposure_message",
    "saturated_terms",
    "saturation_lines",
    "term_saturation",
]

MASK_BAND_MULTIPLE: float = 5.0
"""A cell is masked as wide when its band exceeds this multiple of the median band
(ADR-265 decision 2; fixed before the first run)."""


@dataclass(frozen=True)
class SaturatedTerm:
    """One smooth block and how much of its basis the fit used."""

    label: str
    edf: float
    n_coef: int

    @property
    def ratio(self) -> float:
        return self.edf / self.n_coef

    @property
    def saturated(self) -> bool:
        return self.edf >= SATURATION_THRESHOLD * self.n_coef


def term_saturation(fit: GamFit) -> list[SaturatedTerm]:
    """Every smooth block with its edf and constrained coefficient count, in model order.

    Read from the design's term blocks (not ``summary()``) so it also serves a ``bam`` fit.
    """
    out: list[SaturatedTerm] = []
    for block in fit.design["term_blocks"]:
        label = block["label"]
        if label not in fit.smooth_labels or label not in fit.edf_per_term:
            continue
        n_coef = int(block["end"] - block["start"])
        if n_coef <= 0:
            continue
        out.append(SaturatedTerm(label, float(fit.edf_per_term[label]), n_coef))
    return out


def saturated_terms(fit: GamFit) -> list[SaturatedTerm]:
    """The smooth blocks with ``edf >= 0.95 x n_coef`` (ADR-265 decision 1)."""
    return [t for t in term_saturation(fit) if t.saturated]


def saturation_lines(fit: GamFit) -> list[str]:
    """One sentence per saturated term, stating the threshold; empty when none is."""
    return [
        f"{t.label}: edf {t.edf:.2f} of {t.n_coef} coefficients ({t.ratio:.0%}, threshold "
        f"{SATURATION_THRESHOLD:.0%}) — the basis, not the penalty, may be limiting this term; "
        "consider a larger k."
        for t in saturated_terms(fit)
    ]


@dataclass(frozen=True)
class MaskedSurface:
    """Mask over an :class:`ImprovementSurface` grid (same shape as ``surface.mi``)."""

    no_exposure: np.ndarray
    wide_band: np.ndarray
    median_band: float
    multiple: float
    exposure_known: bool

    @property
    def masked(self) -> np.ndarray:
        return self.no_exposure | self.wide_band

    @property
    def n_cells(self) -> int:
        return int(self.masked.size)

    @property
    def n_no_exposure(self) -> int:
        return int(self.no_exposure.sum())

    @property
    def n_wide(self) -> int:
        return int((self.wide_band & ~self.no_exposure).sum())

    def reason(self) -> np.ndarray:
        """``no_exposure`` / ``wide_band`` / empty, per cell (no exposure takes precedence)."""
        out = np.full(self.masked.shape, "", dtype=object)
        out[self.wide_band] = "wide_band"
        out[self.no_exposure] = "no_exposure"
        return out

    def apply(self, values: np.ndarray) -> np.ndarray:
        """``values`` with masked cells set to NaN (never plotted as values)."""
        return np.where(self.masked, np.nan, values)

    def summary(self) -> str:
        if self.n_cells == 0:
            return "No surface cells."
        base = (
            f"{int(self.masked.sum())} of {self.n_cells} cells masked: "
            f"{self.n_no_exposure} with no exposure, {self.n_wide} with a band wider than "
            f"{self.multiple:g} x the median band ({self.median_band:.3g})."
        )
        if not self.exposure_known:
            base += " No exposure column was available, so cells were not checked for exposure."
        return base


def exposure_vector(data: pl.DataFrame) -> np.ndarray | None:
    """Row exposure: ``central_exposure``, else ``exp(log_exposure)``, else ``None``."""
    if "central_exposure" in data.columns:
        return data.get_column("central_exposure").cast(pl.Float64).to_numpy()
    if "log_exposure" in data.columns:
        return np.exp(data.get_column("log_exposure").cast(pl.Float64).to_numpy())
    return None


def mask_surface(
    surface: ImprovementSurface,
    data: pl.DataFrame,
    *,
    multiple: float = MASK_BAND_MULTIPLE,
) -> MaskedSurface:
    """Mask cells with no exposure at ``(x, y)`` or ``(x, y - step)``, or a too-wide band.

    The median band is taken over the cells that HAVE exposure (and a finite band), so empty
    cells do not drag the reference. Non-finite bands count as wide.
    """
    shape = surface.mi.shape
    width = surface.mi_upper - surface.mi_lower
    expo = exposure_vector(data)
    if expo is None:
        no_expo = np.zeros(shape, dtype=bool)
        known = False
    else:
        age = data.get_column(surface.age_var).cast(pl.Float64).to_numpy()
        year = data.get_column(surface.year_var).cast(pl.Float64).to_numpy()
        keep = np.isfinite(expo) & (expo > 0.0)
        have = set(zip(age[keep].tolist(), year[keep].tolist(), strict=True))
        no_expo = np.zeros(shape, dtype=bool)
        for i, a in enumerate(surface.ages.tolist()):
            for j, y in enumerate(surface.years.tolist()):
                no_expo[i, j] = (a, y) not in have or (a, y - surface.step) not in have
        known = True
    ok = ~no_expo & np.isfinite(width)
    median = float(np.median(width[ok])) if ok.any() else float("nan")
    wide = ~np.isfinite(width)
    if np.isfinite(median):
        with np.errstate(invalid="ignore"):
            wide = wide | (width > multiple * median)
    return MaskedSurface(no_expo, wide, median, multiple, known)


def nonpositive_exposure(data: pl.DataFrame) -> int:
    """Rows whose exposure is null, NaN or ``<= 0`` (0 when the frame has no exposure column)."""
    expo = exposure_vector(data)
    if expo is None:
        return 0
    return int((~(np.isfinite(expo) & (expo > 0.0))).sum())


def drop_nonpositive_exposure(data: pl.DataFrame) -> pl.DataFrame:
    """``data`` without the rows :func:`nonpositive_exposure` counts."""
    expo = exposure_vector(data)
    if expo is None:
        return data
    return data.filter(pl.Series(np.isfinite(expo) & (expo > 0.0)))


def nonpositive_exposure_message(n_bad: int, n_rows: int) -> str:
    """The refusal text: names the cause and the remedy, not the downstream symptom."""
    if n_bad <= 0:
        raise PolarisValidationError("nonpositive_exposure_message: there are no bad rows.")
    return (
        f"{n_bad} of {n_rows} rows have exposure that is zero, negative or missing. The "
        "offset is the log of exposure, which is undefined there, so the model cannot be fitted "
        "on them. Tick 'Drop these rows' to fit on the remaining rows (the count dropped is "
        "shown), or fix the exposure in the source data."
    )

"""Static (matplotlib) diagnostic plots for Polaris RE analytics.

This subpackage is **dev / report-only** and is deliberately kept off the
pricing path: nothing in :mod:`polaris_re.core`, :mod:`polaris_re.products`,
:mod:`polaris_re.reinsurance`, or the ``polaris price`` CLI imports it, and
``matplotlib`` is required only via the optional ``[viz]`` extra (imported
lazily inside each helper). Importing ``polaris_re.viz`` without ``matplotlib``
installed is fine; calling a plotting helper without it raises a clear
:class:`~polaris_re.core.exceptions.PolarisComputationError`.

The current surface renders the experience-GAM (A4') diagnostics — fitted
effect shapes, mortality-improvement surface slices, and the projection fan —
each with its **uncertainty band on by default** (the locked Slice-4d spec).
"""

from polaris_re.viz.experience_plots import (
    BandKind,
    plot_effects,
    plot_mi_projection,
    plot_mi_surface,
    plot_mi_surface_bandwidth,
)

__all__ = [
    "BandKind",
    "plot_effects",
    "plot_mi_projection",
    "plot_mi_surface",
    "plot_mi_surface_bandwidth",
]

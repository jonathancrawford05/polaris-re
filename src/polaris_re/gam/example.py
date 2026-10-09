"""The worked example of ``docs/GAM_USER_GUIDE.md`` — one formula, one data set.

Preview slice P5. The same formula string and the same committed CSVs are read by the
guide, the notebook, and the R probe that fits the example under ``mgcv``
(``scripts/gam_formula_probe.R``), so the guide's example is itself a row of the
generated parity report. The data are synthetic (``scripts/gam_guide_example_data.py``).
"""

from pathlib import Path

import polars as pl

__all__ = ["GUIDE_FAMILY", "GUIDE_FORMULA", "default_data_dir", "load_guide_example"]

GUIDE_FORMULA = (
    "deaths ~ offset(log_exposure) + sex + s(age, k = 8, bs = 'cr') + "
    "s(duration, k = 6, bs = 'cr') + ti(age, duration, k = c(6, 4), bs = 'cr')"
)
"""Verified-subset terms only: offset, a parametric factor, two ``cr`` smooths, a ``ti``."""

GUIDE_FAMILY = "quasipoisson"


def default_data_dir() -> Path:
    """``data/gam_preview`` in a repository checkout."""
    return Path(__file__).resolve().parents[3] / "data" / "gam_preview"


def load_guide_example(data_dir: Path | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """``(train, new)``: the training rows (with ``deaths``) and 60 held-out covariate rows."""
    root = data_dir if data_dir is not None else default_data_dir()
    return (
        pl.read_csv(root / "guide_example_train.csv"),
        pl.read_csv(root / "guide_example_new.csv"),
    )

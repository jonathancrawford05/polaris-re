"""``polaris_re.gam`` — the public entry point to the ``mgcv``-parity GAM engine.

Preview epic Slice P3 (``docs/PLAN_gam_parity_preview.md``, ADR-251). Depends on
``polaris_re.analytics`` and ``polaris_re.core``; nothing in those packages imports
this one.

    from polaris_re.gam import gam
    fit = gam('y ~ s(x, bs="cr", k=8)', df, "gaussian")
"""

from polaris_re.gam.api import (
    ORACLE_COLLATION,
    GamFit,
    gam,
    r_factor_levels,
    structural_rank_deficiency,
)
from polaris_re.gam.formula import ParsedFormula, parse_formula
from polaris_re.gam.summary import GamSummary, SmoothSummary

__all__ = [
    "ORACLE_COLLATION",
    "GamFit",
    "GamSummary",
    "ParsedFormula",
    "SmoothSummary",
    "gam",
    "parse_formula",
    "r_factor_levels",
    "structural_rank_deficiency",
]

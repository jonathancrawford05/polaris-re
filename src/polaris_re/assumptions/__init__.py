"""
Actuarial assumption models for Polaris RE.

Provides mortality tables, improvement scales, lapse rates, ML-enhanced
assumptions, and the AssumptionSet container that bundles all assumptions
for a projection run.
"""

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.ml_lapse import MLLapseAssumption
from polaris_re.assumptions.ml_mortality import MLMortalityAssumption
from polaris_re.assumptions.morbidity import MorbidityTable, MorbidityTableType
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.assumptions.version_store import (
    DEFAULT_ASSUMPTION_KIND,
    AssumptionVersion,
    AssumptionVersionStore,
)

__all__ = [
    "DEFAULT_ASSUMPTION_KIND",
    "AssumptionSet",
    "AssumptionVersion",
    "AssumptionVersionStore",
    "LapseAssumption",
    "MLLapseAssumption",
    "MLMortalityAssumption",
    "MorbidityTable",
    "MorbidityTableType",
    "MortalityTable",
    "MortalityTableSource",
]

"""
Actuarial assumption models for Polaris RE.

Provides mortality tables, improvement scales, lapse rates, and the
AssumptionSet container that bundles all assumptions for a projection run.
"""

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource

__all__ = [
    "AssumptionSet",
    "LapseAssumption",
    "MortalityTable",
    "MortalityTableSource",
]

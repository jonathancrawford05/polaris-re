"""
Product engines for Polaris RE.

Each product class takes an InforceBlock, AssumptionSet, and ProjectionConfig
and returns a CashFlowResult. Product engines are responsible for gross
cash flow projections only — reinsurance modifications are applied separately.
"""

from polaris_re.products.base_product import BaseProduct
from polaris_re.products.disability import DisabilityProduct
from polaris_re.products.dispatch import get_product_engine
from polaris_re.products.term_life import TermLife
from polaris_re.products.universal_life import UniversalLife
from polaris_re.products.whole_life import WholeLife, WholeLifeVariant

__all__ = [
    "BaseProduct",
    "DisabilityProduct",
    "TermLife",
    "UniversalLife",
    "WholeLife",
    "WholeLifeVariant",
    "get_product_engine",
]

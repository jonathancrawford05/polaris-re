"""
Product engines for Polaris RE.

Each product class takes an InforceBlock, AssumptionSet, and ProjectionConfig
and returns a CashFlowResult. Product engines are responsible for gross
cash flow projections only — reinsurance modifications are applied separately.
"""

from polaris_re.products.base_product import BaseProduct
from polaris_re.products.term_life import TermLife

__all__ = ["BaseProduct", "TermLife"]

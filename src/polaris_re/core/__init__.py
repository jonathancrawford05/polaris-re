"""
Core foundational types for Polaris RE.

Exports the primary data models used throughout the engine:
Policy, InforceBlock, ProjectionConfig, CashFlowResult, and base exceptions.
"""

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig

__all__ = [
    "PolarisBaseModel",
    "CashFlowResult",
    "PolarisComputationError",
    "PolarisValidationError",
    "InforceBlock",
    "Policy",
    "ProductType",
    "Sex",
    "SmokerStatus",
    "ProjectionConfig",
]

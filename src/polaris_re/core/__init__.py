"""
Core foundational types for Polaris RE.

Exports the primary data models used throughout the engine:
Policy, InforceBlock, ProjectionConfig, CashFlowResult, base exceptions,
and the shared pipeline builder.
"""

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
)
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig

__all__ = [
    "CashFlowResult",
    "DealConfig",
    "InforceBlock",
    "LapseConfig",
    "MortalityConfig",
    "PipelineInputs",
    "PolarisBaseModel",
    "PolarisComputationError",
    "PolarisValidationError",
    "Policy",
    "ProductType",
    "ProjectionConfig",
    "Sex",
    "SmokerStatus",
    "build_pipeline",
]

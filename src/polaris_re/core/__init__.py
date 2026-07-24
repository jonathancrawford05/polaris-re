"""
Core foundational types for Polaris RE.

Exports the primary data models used throughout the engine:
Policy, InforceBlock, ProjectionConfig, CashFlowResult, base exceptions,
and the asset model.

The pipeline builder (``DealConfig``/``build_pipeline``/etc.) deliberately is
NOT re-exported here. ``core/pipeline.py`` imports from ``assumptions/`` (a
CLAUDE.md §6 layering exception it is granted as the composition root), so an
eager re-export made a leaf ``core.base`` import drag ``pipeline`` — and thus
``assumptions``, mid-initialisation — into the graph, producing a latent
circular ImportError. Import those symbols from ``polaris_re.core.pipeline``
directly. See ADR-155.
"""

from polaris_re.core.asset import AssetPortfolio, Bond
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis

__all__ = [
    "AssetPortfolio",
    "Bond",
    "CashFlowResult",
    "InforceBlock",
    "PolarisBaseModel",
    "PolarisComputationError",
    "PolarisValidationError",
    "Policy",
    "ProductType",
    "ProjectionConfig",
    "ReserveBasis",
    "Sex",
    "SmokerStatus",
]

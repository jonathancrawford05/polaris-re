"""
Core foundational types for Polaris RE.

Exports the primary data models used throughout the engine:
Policy, InforceBlock, ProjectionConfig, CashFlowResult, base exceptions,
and the asset model.

The pipeline builder (``DealConfig``/``build_pipeline``/etc.) is not part of the
``core`` layer at all: it is the deal **composition root** and lives at the
package top level, ``polaris_re.pipeline``. It imports from ``assumptions/`` (and
every other sub-package), which the CLAUDE.md §6 rule forbids ``core/`` from
doing — so it must sit above ``core/``, not inside it. Import those symbols from
``polaris_re.pipeline`` directly. ADR-156 relocated the module out of ``core/``
to retire that §6 exception entirely; ADR-155 was the earlier symptom-only fix
(removing an eager re-export from this ``__init__``).
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

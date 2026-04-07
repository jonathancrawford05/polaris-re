"""Product engine dispatch — maps ProductType to the correct projection engine.

Provides a single ``get_product_engine()`` factory used by the CLI, API,
and Streamlit dashboard so that product dispatch logic is defined once.
"""

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.base_product import BaseProduct

__all__ = ["get_product_engine"]

# Maps ProductType enum values to their engine classes (lazy imports avoided
# because all product modules are lightweight and already importable).
_PRODUCT_ENGINES: dict[ProductType, type[BaseProduct]] = {}


def _ensure_registry() -> None:
    """Populate the registry on first call (avoids circular imports)."""
    if _PRODUCT_ENGINES:
        return

    from polaris_re.products.term_life import TermLife
    from polaris_re.products.universal_life import UniversalLife
    from polaris_re.products.whole_life import WholeLife

    _PRODUCT_ENGINES[ProductType.TERM] = TermLife
    _PRODUCT_ENGINES[ProductType.WHOLE_LIFE] = WholeLife
    _PRODUCT_ENGINES[ProductType.UNIVERSAL_LIFE] = UniversalLife


def get_product_engine(
    inforce: InforceBlock,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
) -> BaseProduct:
    """Return the appropriate product engine for the given inforce block.

    Determines the product type from the first policy in the block.
    All policies in the block must share the same product type (this
    is enforced by each product engine's ``_validate_inputs``).

    Args:
        inforce: InforceBlock (all policies must share the same product type).
        assumptions: AssumptionSet with mortality and lapse tables.
        config: ProjectionConfig with horizon, discount rate, expenses.

    Returns:
        A concrete BaseProduct subclass instance ready to call ``.project()``.

    Raises:
        PolarisValidationError: If the product type is not supported or
            the inforce block is empty.
    """
    _ensure_registry()

    if not inforce.policies:
        raise PolarisValidationError("Cannot dispatch product engine for empty inforce block.")

    product_type = inforce.policies[0].product_type

    engine_cls = _PRODUCT_ENGINES.get(product_type)
    if engine_cls is None:
        supported = ", ".join(pt.value for pt in _PRODUCT_ENGINES)
        raise PolarisValidationError(
            f"No product engine registered for ProductType.{product_type.value}. "
            f"Supported types: {supported}"
        )

    return engine_cls(inforce=inforce, assumptions=assumptions, config=config)

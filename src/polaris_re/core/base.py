"""
Base Pydantic model configuration shared across all Polaris RE models.

All domain models inherit from PolarisBaseModel to ensure consistent
validation, serialization, and immutability behaviour.
"""

from pydantic import BaseModel, ConfigDict

__all__ = ["PolarisBaseModel"]


class PolarisBaseModel(BaseModel):
    """
    Base class for all Polaris RE data models.

    Configuration:
    - frozen=True: Models are immutable after construction (assumption safety).
    - validate_assignment=True: Validators run on attribute assignment (if unfrozen subclass).
    - extra="forbid": No undeclared fields allowed — prevents silent data errors.
    - populate_by_name=True: Allows both alias and field name for construction.
    """

    model_config = ConfigDict(
        frozen=True,
        validate_assignment=True,
        extra="forbid",
        populate_by_name=True,
    )

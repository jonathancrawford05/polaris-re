"""
ProjectionConfig — configuration for a cash flow projection run.

Defines the time horizon, discount rate, time step, and valuation date.
Passed to all projection engines and analytics components.
"""

from datetime import date

from pydantic import Field, field_validator

from polaris_re.core.base import PolarisBaseModel

__all__ = ["ProjectionConfig"]


class ProjectionConfig(PolarisBaseModel):
    """
    Configuration parameters for a projection run.

    Projection time step is fixed at monthly (1/12 year). All horizons
    are expressed in years but stored as integer month counts internally.
    """

    valuation_date: date = Field(
        description="The date from which the projection starts. Must match policy valuation dates."
    )
    projection_horizon_years: int = Field(
        ge=1,
        le=100,
        description=(
            "Number of years to project. Typically equals remaining policy term for term life."
        ),
    )
    discount_rate: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Annual discount rate for present value calculations. "
            "Used for profit testing and APV computations. "
            "Typical range: 0.04-0.08 for valuation, 0.08-0.12 for pricing."
        ),
    )
    valuation_interest_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Annual interest rate used for reserve calculations (net premium reserve recursion). "
            "If None, defaults to discount_rate. "
            "Regulatory: IFRS 17 uses a risk-free rate; US GAAP uses a locked-in rate."
        ),
    )

    @field_validator("projection_horizon_years")
    @classmethod
    def horizon_reasonable(cls, v: int) -> int:
        if v > 100:
            raise ValueError("Projection horizon exceeds 100 years. Check input.")
        return v

    @property
    def projection_months(self) -> int:
        """Total number of monthly time steps in the projection."""
        return self.projection_horizon_years * 12

    @property
    def monthly_discount_factor(self) -> float:
        """Discount factor per monthly time step: v = (1 + i)^(-1/12)."""
        return (1.0 + self.discount_rate) ** (-1.0 / 12.0)

    @property
    def monthly_accumulation_factor(self) -> float:
        """Accumulation factor per monthly time step: (1 + i)^(1/12)."""
        return (1.0 + self.discount_rate) ** (1.0 / 12.0)

    @property
    def effective_valuation_rate(self) -> float:
        """Interest rate for reserve recursion. Falls back to discount_rate."""
        return (
            self.valuation_interest_rate
            if self.valuation_interest_rate is not None
            else self.discount_rate
        )

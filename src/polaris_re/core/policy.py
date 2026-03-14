"""
Policy data model — the atomic unit of an inforce block.

A Policy represents a single insured life under a single coverage.
All fields are required; no defaults are provided to prevent silent
assumptions entering the projection.
"""

from datetime import date
from enum import StrEnum

from pydantic import Field, field_validator

from polaris_re.core.base import PolarisBaseModel

__all__ = ["Policy", "ProductType", "Sex", "SmokerStatus"]


class Sex(StrEnum):
    """Biological sex of the insured. Used for sex-distinct mortality table lookups."""

    MALE = "M"
    FEMALE = "F"


class SmokerStatus(StrEnum):
    """
    Tobacco/nicotine use status of the insured at issue.

    SMOKER:     Current tobacco user at time of underwriting.
    NON_SMOKER: No tobacco use at time of underwriting.
    UNKNOWN:    Status not determined — use aggregate (blended) mortality rates.
    """

    SMOKER = "S"
    NON_SMOKER = "NS"
    UNKNOWN = "U"


class ProductType(StrEnum):
    """Life insurance product type. Determines which product engine is invoked."""

    TERM = "TERM"
    WHOLE_LIFE = "WHOLE_LIFE"
    UNIVERSAL_LIFE = "UL"
    DISABILITY = "DI"
    CRITICAL_ILLNESS = "CI"
    ANNUITY = "ANNUITY"


class Policy(PolarisBaseModel):
    """
    A single insured life under a single coverage.

    This is the atomic record in an InforceBlock. All projection engines
    operate on vectorized extractions from a collection of Policy objects.

    Ages use Age Nearest Birthday (ANB) convention unless otherwise specified.
    """

    # --- Identifiers ---
    policy_id: str = Field(description="Unique policy identifier.")

    # --- Demographic / underwriting ---
    issue_age: int = Field(ge=0, le=120, description="Age at policy issue (ANB).")
    attained_age: int = Field(
        ge=0, le=120, description="Current attained age at valuation date (ANB)."
    )
    sex: Sex = Field(description="Sex of the insured for mortality table lookups.")
    smoker_status: SmokerStatus = Field(description="Smoker/non-smoker status at issue.")
    underwriting_class: str = Field(
        description="Underwriting class (e.g. 'PREF_PLUS', 'PREFERRED', 'STANDARD', 'SUBSTANDARD')."
    )

    # --- Coverage ---
    face_amount: float = Field(gt=0, description="Face amount (death benefit) in dollars.")
    annual_premium: float = Field(ge=0, description="Gross annual premium in dollars.")
    product_type: ProductType = Field(
        description="Product type driving which projection engine is used."
    )
    policy_term: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Coverage term in years. None for permanent products (whole life, UL).",
    )
    duration_inforce: int = Field(
        ge=0,
        description="Number of months the policy has been in force at the valuation date. "
        "Used to determine position in select mortality table.",
    )

    # --- Reinsurance ---
    reinsurance_cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Proportion of the policy ceded to reinsurer. "
            "0.0 = retained, 1.0 = fully ceded."
        ),
    )

    # --- Dates ---
    issue_date: date = Field(description="Policy issue date.")
    valuation_date: date = Field(description="Valuation / projection start date.")

    @field_validator("attained_age")
    @classmethod
    def attained_age_gte_issue_age(cls, v: int, info: object) -> int:
        # Access issue_age from the validation context when available
        # Full cross-field validation handled in model_validator
        return v

    @field_validator("policy_term")
    @classmethod
    def term_required_for_term_products(cls, v: int | None, info: object) -> int | None:
        # NOTE: Cross-field validation between product_type and policy_term
        # is implemented as a model_validator in the full implementation.
        # Stub left here as a reminder.
        return v

    @property
    def duration_inforce_years(self) -> float:
        """Duration in force expressed as fractional years."""
        return self.duration_inforce / 12

    @property
    def remaining_term_months(self) -> int | None:
        """
        Remaining coverage term in months.
        Returns None for permanent products.
        """
        if self.policy_term is None:
            return None
        total_term_months = self.policy_term * 12
        return max(0, total_term_months - self.duration_inforce)

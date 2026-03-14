"""
InforceBlock — a validated collection of Policy objects with vectorized attribute access.

The InforceBlock is the primary input to all projection engines. It provides
zero-copy numpy array views over policy attributes, enabling fully vectorized
projection code without policy-level Python loops.
"""

from typing import Self

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus

__all__ = ["InforceBlock"]


class InforceBlock(PolarisBaseModel):
    """
    A collection of policies representing an inforce book of business.

    Vectorized attribute access (e.g., `.attained_age_vec`) returns numpy arrays
    suitable for direct use in projection computations.

    All policies in a block must share the same valuation_date.
    Mixed product-type blocks can be split using `.filter_by_product()`.
    """

    policies: list[Policy] = Field(min_length=1, description="List of policies in the inforce block.")
    block_id: str | None = Field(default=None, description="Optional identifier for this block (e.g. deal name).")

    @model_validator(mode="after")
    def validate_consistent_valuation_dates(self) -> Self:
        """All policies must share the same valuation date."""
        dates = {p.valuation_date for p in self.policies}
        if len(dates) > 1:
            raise PolarisValidationError(
                f"InforceBlock contains policies with mixed valuation dates: {dates}. "
                "All policies must share the same valuation_date."
            )
        return self

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def n_policies(self) -> int:
        """Number of policies in the block."""
        return len(self.policies)

    @property
    def product_types(self) -> set[ProductType]:
        """Set of distinct product types present in the block."""
        return {p.product_type for p in self.policies}

    # ------------------------------------------------------------------
    # Vectorized attribute access — shape (N,)
    # ------------------------------------------------------------------

    @property
    def policy_id_vec(self) -> list[str]:
        """Policy IDs as a list (strings — not numpy)."""
        return [p.policy_id for p in self.policies]

    @property
    def attained_age_vec(self) -> np.ndarray:
        """Attained ages, shape (N,), dtype int32."""
        return np.array([p.attained_age for p in self.policies], dtype=np.int32)

    @property
    def issue_age_vec(self) -> np.ndarray:
        """Issue ages, shape (N,), dtype int32."""
        return np.array([p.issue_age for p in self.policies], dtype=np.int32)

    @property
    def duration_inforce_vec(self) -> np.ndarray:
        """Duration in force (months), shape (N,), dtype int32."""
        return np.array([p.duration_inforce for p in self.policies], dtype=np.int32)

    @property
    def face_amount_vec(self) -> np.ndarray:
        """Face amounts, shape (N,), dtype float64."""
        return np.array([p.face_amount for p in self.policies], dtype=np.float64)

    @property
    def annual_premium_vec(self) -> np.ndarray:
        """Annual gross premiums, shape (N,), dtype float64."""
        return np.array([p.annual_premium for p in self.policies], dtype=np.float64)

    @property
    def monthly_premium_vec(self) -> np.ndarray:
        """Monthly gross premiums = annual / 12, shape (N,), dtype float64."""
        return self.annual_premium_vec / 12.0

    @property
    def cession_pct_vec(self) -> np.ndarray:
        """Reinsurance cession percentages, shape (N,), dtype float64."""
        return np.array([p.reinsurance_cession_pct for p in self.policies], dtype=np.float64)

    @property
    def is_smoker_vec(self) -> np.ndarray:
        """Boolean mask: True where smoker_status == SMOKER, shape (N,)."""
        return np.array([p.smoker_status == SmokerStatus.SMOKER for p in self.policies], dtype=bool)

    @property
    def is_male_vec(self) -> np.ndarray:
        """Boolean mask: True where sex == MALE, shape (N,)."""
        return np.array([p.sex == Sex.MALE for p in self.policies], dtype=bool)

    @property
    def remaining_term_months_vec(self) -> np.ndarray:
        """Remaining coverage term (months), shape (N,), dtype int32. -1 for permanent products."""
        return np.array(
            [p.remaining_term_months if p.remaining_term_months is not None else -1
             for p in self.policies],
            dtype=np.int32,
        )

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter_by_product(self, product_type: ProductType) -> Self:
        """Return a new InforceBlock containing only policies of the given product type."""
        filtered = [p for p in self.policies if p.product_type == product_type]
        if not filtered:
            raise PolarisValidationError(
                f"No policies of product type {product_type} found in block."
            )
        return InforceBlock(policies=filtered, block_id=self.block_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    def total_face_amount(self) -> float:
        """Sum of all policy face amounts."""
        return float(self.face_amount_vec.sum())

    def total_annual_premium(self) -> float:
        """Sum of all policy annual premiums."""
        return float(self.annual_premium_vec.sum())

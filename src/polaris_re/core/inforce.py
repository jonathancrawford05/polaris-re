"""
InforceBlock — a validated collection of Policy objects with vectorized attribute access.

The InforceBlock is the primary input to all projection engines. It provides
zero-copy numpy array views over policy attributes, enabling fully vectorized
projection code without policy-level Python loops.

Supports construction from:
  - A list of ``Policy`` objects (standard)
  - A normalised CSV file via ``InforceBlock.from_csv()`` (Phase 4)
"""

from datetime import date as date_type
from pathlib import Path
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

    policies: list[Policy] = Field(
        min_length=1, description="List of policies in the inforce block."
    )
    block_id: str | None = Field(
        default=None, description="Optional identifier for this block (e.g. deal name)."
    )

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
        """Reinsurance cession percentages, shape (N,), dtype float64.

        Returns NaN for policies where reinsurance_cession_pct is None
        (meaning 'use treaty default'). Use effective_cession_vec() to
        resolve None values against a treaty-level default.
        """
        return np.array(
            [
                p.reinsurance_cession_pct if p.reinsurance_cession_pct is not None else np.nan
                for p in self.policies
            ],
            dtype=np.float64,
        )

    def effective_cession_vec(self, treaty_default: float) -> np.ndarray:
        """Per-policy effective cession rates, shape (N,), dtype float64.

        For each policy: uses the policy-level reinsurance_cession_pct if set,
        otherwise falls back to treaty_default.

        Args:
            treaty_default: Treaty-level cession percentage used when a
                policy's reinsurance_cession_pct is None.

        Returns:
            Effective cession rates, shape (N,), dtype float64.
        """
        raw = self.cession_pct_vec
        return np.where(np.isnan(raw), treaty_default, raw)

    def face_weighted_cession(self, treaty_default: float) -> float:
        """Face-amount-weighted average effective cession rate (scalar).

        Computes the blended cession rate across all policies, weighted by
        face amount. This is the correct aggregate cession rate for
        proportional treaty application on aggregate cash flows.

        Args:
            treaty_default: Treaty-level cession percentage used when a
                policy's reinsurance_cession_pct is None.

        Returns:
            Scalar face-weighted average cession rate.
        """
        effective = self.effective_cession_vec(treaty_default)
        face = self.face_amount_vec
        total_face = face.sum()
        if total_face == 0.0:
            return treaty_default
        return float(np.dot(effective, face) / total_face)

    @property
    def is_smoker_vec(self) -> np.ndarray:
        """Boolean mask: True where smoker_status == SMOKER, shape (N,)."""
        return np.array([p.smoker_status == SmokerStatus.SMOKER for p in self.policies], dtype=bool)

    @property
    def is_male_vec(self) -> np.ndarray:
        """Boolean mask: True where sex == MALE, shape (N,)."""
        return np.array([p.sex == Sex.MALE for p in self.policies], dtype=bool)

    def attained_age_vec_at(self, valuation_date: date_type) -> np.ndarray:
        """Compute attained ages relative to a given valuation date.

        Attained age = issue_age + whole years elapsed from issue_date to
        valuation_date.  This allows the same inforce block to be re-valued
        at different dates without reloading.

        Args:
            valuation_date: The reference date for age calculation.

        Returns:
            Attained ages, shape (N,), dtype int32.
        """
        from polaris_re.utils.date_utils import months_between

        return np.array(
            [
                p.issue_age + months_between(p.issue_date, valuation_date) // 12
                for p in self.policies
            ],
            dtype=np.int32,
        )

    def duration_inforce_vec_at(self, valuation_date: date_type) -> np.ndarray:
        """Compute duration in force (months) relative to a given valuation date.

        Duration = months between each policy's issue_date and the given
        valuation_date.  This allows the same inforce block to be re-valued
        at different dates without reloading.

        Args:
            valuation_date: The reference date for duration calculation.

        Returns:
            Duration in force (months), shape (N,), dtype int32.
        """
        from polaris_re.utils.date_utils import months_between

        return np.array(
            [months_between(p.issue_date, valuation_date) for p in self.policies],
            dtype=np.int32,
        )

    @property
    def remaining_term_months_vec(self) -> np.ndarray:
        """Remaining coverage term (months), shape (N,), dtype int32. -1 for permanent products."""
        return np.array(
            [
                p.remaining_term_months if p.remaining_term_months is not None else -1
                for p in self.policies
            ],
            dtype=np.int32,
        )

    # ------------------------------------------------------------------
    # Projection horizon recommendation
    # ------------------------------------------------------------------

    def recommended_projection_years(self, omega: int = 121) -> int:
        """Recommend a projection horizon (years) that covers the whole block.

        Computes a per-policy horizon based on product type and returns the
        maximum, capped at 100 to respect ``ProjectionConfig`` limits:

          * ``TERM``:        ceil(remaining_term_months / 12)   (minimum 1)
          * ``WHOLE_LIFE``:  omega - attained_age
          * ``UL``:          max(ceil(remaining_term_months / 12), 50)
                             — permanent UL (no term) uses 50 as a
                             conservative runoff until UL dynamics are modelled
          * other products:  30

        Args:
            omega: Terminal age used for whole-life policies. Defaults to 121,
                matching the SOA 2017 CSO and CIA 2014 table extensions.

        Returns:
            The recommended projection horizon in years, ``int``, capped at 100.
        """
        product_types = np.array([p.product_type for p in self.policies], dtype=object)
        attained = self.attained_age_vec
        remaining_months = self.remaining_term_months_vec

        # Default horizon (DI, CI, ANNUITY, unknown): 30 years
        years = np.full(self.n_policies, 30, dtype=np.int32)

        # TERM: ceil(remaining_months / 12), at least 1 year
        term_mask = product_types == ProductType.TERM
        if term_mask.any():
            term_rem = remaining_months[term_mask]
            # remaining_term_months is always >= 0 for TERM (not -1) because
            # policy_term is required for term products.
            term_years = np.ceil(term_rem / 12.0).astype(np.int32)
            years[term_mask] = np.maximum(term_years, 1)

        # WHOLE_LIFE: omega - attained_age
        wl_mask = product_types == ProductType.WHOLE_LIFE
        if wl_mask.any():
            years[wl_mask] = np.maximum((omega - attained[wl_mask]).astype(np.int32), 1)

        # UL: max(ceil(remaining/12), 50). Permanent UL has remaining = -1,
        # which ceils to 0; the max with 50 handles both cases.
        ul_mask = product_types == ProductType.UNIVERSAL_LIFE
        if ul_mask.any():
            ul_rem = remaining_months[ul_mask]
            ul_years = np.where(
                ul_rem > 0,
                np.ceil(ul_rem / 12.0).astype(np.int32),
                0,
            )
            years[ul_mask] = np.maximum(ul_years, 50)

        return int(min(int(years.max()), 100))

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_csv(
        cls,
        path: Path,
        block_id: str | None = None,
    ) -> Self:
        """
        Construct an InforceBlock from a normalised Polaris RE CSV file.

        The CSV must follow the schema produced by ``generate_synthetic_block.py``:
        columns match the ``Policy`` model fields.

        Args:
            path:     Path to the normalised CSV file.
            block_id: Optional block identifier.

        Returns:
            A validated InforceBlock.

        Raises:
            FileNotFoundError: CSV file not found.
            PolarisValidationError: Data fails validation.
        """
        import polars as pl

        if not path.exists():
            raise FileNotFoundError(f"Inforce CSV not found: {path}")

        df = pl.read_csv(path)

        required = [
            "policy_id",
            "issue_age",
            "attained_age",
            "sex",
            "smoker_status",
            "face_amount",
            "annual_premium",
            "product_type",
            "duration_inforce",
            "issue_date",
            "valuation_date",
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise PolarisValidationError(
                f"Missing required columns in CSV: {missing}. Available: {list(df.columns)}"
            )

        policies: list[Policy] = []
        for row in df.iter_rows(named=True):
            policy_term = row.get("policy_term")
            if policy_term is not None:
                policy_term = int(policy_term)

            # Parse dates — handle both string and date objects
            issue_date_val = row["issue_date"]
            if isinstance(issue_date_val, str):
                issue_date_val = date_type.fromisoformat(issue_date_val)

            val_date_val = row["valuation_date"]
            if isinstance(val_date_val, str):
                val_date_val = date_type.fromisoformat(val_date_val)

            policy = Policy(
                policy_id=str(row["policy_id"]),
                issue_age=int(row["issue_age"]),
                attained_age=int(row["attained_age"]),
                sex=Sex(str(row["sex"])),
                smoker_status=SmokerStatus(str(row["smoker_status"])),
                underwriting_class=str(row.get("underwriting_class", "STANDARD")),
                face_amount=float(row["face_amount"]),
                annual_premium=float(row["annual_premium"]),
                product_type=ProductType(str(row["product_type"])),
                policy_term=policy_term,
                duration_inforce=int(row["duration_inforce"]),
                reinsurance_cession_pct=(
                    float(row["reinsurance_cession_pct"])
                    if row.get("reinsurance_cession_pct") is not None
                    else None
                ),
                issue_date=issue_date_val,
                valuation_date=val_date_val,
            )
            policies.append(policy)

        return cls(policies=policies, block_id=block_id)  # type: ignore[return-value]

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

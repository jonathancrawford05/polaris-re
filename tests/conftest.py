"""
Pytest configuration and shared fixtures for the Polaris RE test suite.

Fixtures defined here are available to all test modules without explicit imports.
"""

from __future__ import annotations

from datetime import date

import pytest

from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig

# ---------------------------------------------------------------------------
# Canonical single-policy fixture — used in closed-form verification tests
# ---------------------------------------------------------------------------


@pytest.fixture
def single_male_ns_term_policy() -> Policy:
    """
    A single male non-smoker preferred term life policy.
    Issue age 40, attained age 40 (new business), 20-year term, $500k face.
    Used for closed-form verification tests — results should match hand calculations.
    """
    return Policy(
        policy_id="TEST_001",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="PREFERRED",
        face_amount=500_000.0,
        annual_premium=1_500.0,
        product_type=ProductType.TERM,
        policy_term=20,
        duration_inforce=0,
        reinsurance_cession_pct=0.50,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


@pytest.fixture
def single_policy_block(single_male_ns_term_policy: Policy) -> InforceBlock:
    """InforceBlock containing the single canonical term life policy."""
    return InforceBlock(policies=[single_male_ns_term_policy])


@pytest.fixture
def small_mixed_block() -> InforceBlock:
    """
    Small inforce block of 5 term life policies with varying attributes.
    Used for integration tests and vectorization verification.
    """
    policies = [
        Policy(
            policy_id=f"TEST_{i:03d}",
            issue_age=age,
            attained_age=age + dur // 12,
            sex=sex,
            smoker_status=smoker,
            underwriting_class="STANDARD",
            face_amount=face,
            annual_premium=face * 0.003,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=dur,
            reinsurance_cession_pct=0.50,
            issue_date=date(2025 - dur // 12, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        for i, (age, dur, sex, smoker, face) in enumerate(
            [
                (35, 0, Sex.MALE, SmokerStatus.NON_SMOKER, 250_000),
                (45, 24, Sex.FEMALE, SmokerStatus.NON_SMOKER, 500_000),
                (50, 60, Sex.MALE, SmokerStatus.SMOKER, 300_000),
                (38, 12, Sex.FEMALE, SmokerStatus.NON_SMOKER, 750_000),
                (55, 36, Sex.MALE, SmokerStatus.NON_SMOKER, 1_000_000),
            ]
        )
    ]
    return InforceBlock(policies=policies, block_id="TEST_BLOCK_MIXED")


@pytest.fixture
def standard_projection_config() -> ProjectionConfig:
    """Standard 20-year projection config with 5% discount rate."""
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
    )


@pytest.fixture
def pricing_projection_config() -> ProjectionConfig:
    """Projection config for deal pricing — 10% hurdle rate over 20 years."""
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.10,
    )

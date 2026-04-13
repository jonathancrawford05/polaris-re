"""
Tests for ``polaris_re.core.inforce.InforceBlock``.

Focuses on block-level helpers that depend on multiple policies
(e.g. ``recommended_projection_years``), complementing the per-property
tests covered indirectly by product and treaty engine tests.
"""

from datetime import date

import pytest

from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VAL_DATE = date(2025, 1, 1)


def _make_policy(
    *,
    policy_id: str = "P",
    product_type: ProductType = ProductType.TERM,
    issue_age: int = 40,
    attained_age: int | None = None,
    policy_term: int | None = 20,
    duration_inforce: int = 0,
    face_amount: float = 500_000.0,
) -> Policy:
    """Construct a Policy with sensible defaults for horizon tests."""
    if attained_age is None:
        attained_age = issue_age + duration_inforce // 12
    issue_year = _VAL_DATE.year - duration_inforce // 12
    return Policy(
        policy_id=policy_id,
        issue_age=issue_age,
        attained_age=attained_age,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face_amount,
        annual_premium=face_amount * 0.003,
        product_type=product_type,
        policy_term=policy_term,
        duration_inforce=duration_inforce,
        issue_date=date(issue_year, 1, 1),
        valuation_date=_VAL_DATE,
    )


# ---------------------------------------------------------------------------
# recommended_projection_years — parametrised single-policy cases
# ---------------------------------------------------------------------------


class TestRecommendedProjectionYears:
    """Verify horizon recommendations for each product type."""

    @pytest.mark.parametrize(
        ("product_type", "attained_age", "policy_term", "duration_inforce", "expected"),
        [
            # TERM: remaining = policy_term * 12 - duration_inforce months
            ("TERM", 40, 20, 0, 20),  # new business, 20yr term
            ("TERM", 45, 20, 60, 15),  # 5 years in-force on 20yr term
            ("TERM", 49, 10, 114, 1),  # near expiry: 6 months → ceil = 1
            ("TERM", 50, 10, 120, 1),  # just expired → clamped to 1
            # WHOLE_LIFE: omega - attained_age
            ("WHOLE_LIFE", 49, None, 0, 72),  # 121 - 49
            ("WHOLE_LIFE", 90, None, 0, 31),  # 121 - 90
            # UL: conservative 50yr for permanent UL
            ("UL", 45, None, 0, 50),
            ("UL", 70, None, 0, 50),
            # Other product types (DI, CI, ANNUITY): default 30
            ("DI", 40, None, 0, 30),
            ("CI", 40, None, 0, 30),
            ("ANNUITY", 65, None, 0, 30),
        ],
    )
    def test_single_policy_horizon(
        self,
        product_type: str,
        attained_age: int,
        policy_term: int | None,
        duration_inforce: int,
        expected: int,
    ) -> None:
        policy = _make_policy(
            policy_id="H1",
            product_type=ProductType(product_type),
            issue_age=attained_age - duration_inforce // 12,
            attained_age=attained_age,
            policy_term=policy_term,
            duration_inforce=duration_inforce,
        )
        block = InforceBlock(policies=[policy])
        assert block.recommended_projection_years() == expected

    def test_mixed_block_uses_max(self) -> None:
        """WL drives horizon in a mixed TERM + WL block."""
        policies = [
            _make_policy(
                policy_id="T1",
                product_type=ProductType.TERM,
                issue_age=40,
                attained_age=40,
                policy_term=20,
                duration_inforce=0,
            ),
            _make_policy(
                policy_id="W1",
                product_type=ProductType.WHOLE_LIFE,
                issue_age=49,
                attained_age=49,
                policy_term=None,
                duration_inforce=0,
            ),
        ]
        block = InforceBlock(policies=policies)
        assert block.recommended_projection_years() == 72  # 121 - 49

    def test_capped_at_100(self) -> None:
        """Horizon is capped at 100 to respect ProjectionConfig bounds."""
        policy = _make_policy(
            policy_id="W_YOUNG",
            product_type=ProductType.WHOLE_LIFE,
            issue_age=10,
            attained_age=10,
            policy_term=None,
            duration_inforce=0,
        )
        block = InforceBlock(policies=[policy])
        # Raw: 121 - 10 = 111 → capped at 100
        assert block.recommended_projection_years() == 100

    def test_custom_omega(self) -> None:
        """The omega parameter overrides the default terminal age."""
        policy = _make_policy(
            policy_id="W_OMEGA",
            product_type=ProductType.WHOLE_LIFE,
            issue_age=50,
            attained_age=50,
            policy_term=None,
            duration_inforce=0,
        )
        block = InforceBlock(policies=[policy])
        # omega=110 → 110 - 50 = 60
        assert block.recommended_projection_years(omega=110) == 60

    def test_returns_python_int(self) -> None:
        """Return type is a native ``int``, not ``np.int32``."""
        policy = _make_policy(
            policy_id="T_INT",
            product_type=ProductType.TERM,
            policy_term=15,
            duration_inforce=0,
        )
        block = InforceBlock(policies=[policy])
        result = block.recommended_projection_years()
        assert isinstance(result, int)
        assert not isinstance(result, bool)

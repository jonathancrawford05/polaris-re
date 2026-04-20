"""Tests for core data models: Policy, InforceBlock, ProjectionConfig, CashFlowResult."""

from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus


class TestPolicy:
    """Verify Policy model validation and computed properties."""

    def test_valid_policy_construction(self, single_male_ns_term_policy):
        p = single_male_ns_term_policy
        assert p.policy_id == "TEST_001"
        assert p.face_amount == 500_000.0
        assert p.sex == Sex.MALE

    def test_remaining_term_months_new_business(self, single_male_ns_term_policy):
        assert single_male_ns_term_policy.remaining_term_months == 240  # 20 years * 12

    def test_remaining_term_months_mid_policy(self):
        p = Policy(
            policy_id="X",
            issue_age=40,
            attained_age=45,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=100_000,
            annual_premium=500,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=60,  # 5 years in force
            reinsurance_cession_pct=0.5,
            issue_date=date(2020, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        assert p.remaining_term_months == 180  # 15 years remaining

    def test_permanent_policy_has_no_remaining_term(self):
        p = Policy(
            policy_id="WL001",
            issue_age=40,
            attained_age=40,
            sex=Sex.FEMALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="PREFERRED",
            face_amount=200_000,
            annual_premium=2_000,
            product_type=ProductType.WHOLE_LIFE,
            policy_term=None,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        assert p.remaining_term_months is None

    def test_invalid_negative_face_amount(self):
        with pytest.raises(ValidationError):  # Pydantic ValidationError
            Policy(
                policy_id="BAD",
                issue_age=40,
                attained_age=40,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=-100_000,  # invalid
                annual_premium=500,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=0.5,
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            )

    def test_invalid_cession_pct_above_one(self):
        with pytest.raises(ValidationError):
            Policy(
                policy_id="BAD2",
                issue_age=40,
                attained_age=40,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=100_000,
                annual_premium=500,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=1.5,  # invalid
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            )


class TestPolicySubstandardRating:
    """Verify the substandard-rating fields on Policy (ADR-042)."""

    def _base_kwargs(self) -> dict:
        return dict(
            policy_id="SUB_001",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="SUBSTANDARD",
            face_amount=500_000,
            annual_premium=3_000,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )

    def test_default_multiplier_is_one(self, single_male_ns_term_policy):
        assert single_male_ns_term_policy.mortality_multiplier == 1.0

    def test_default_flat_extra_is_zero(self, single_male_ns_term_policy):
        assert single_male_ns_term_policy.flat_extra_per_1000 == 0.0

    def test_explicit_table_2(self):
        p = Policy(**self._base_kwargs(), mortality_multiplier=2.0)
        assert p.mortality_multiplier == 2.0
        assert p.flat_extra_per_1000 == 0.0

    def test_explicit_flat_extra(self):
        p = Policy(**self._base_kwargs(), flat_extra_per_1000=5.0)
        assert p.flat_extra_per_1000 == 5.0
        assert p.mortality_multiplier == 1.0

    def test_negative_multiplier_rejected(self):
        with pytest.raises(ValidationError):
            Policy(**self._base_kwargs(), mortality_multiplier=-0.5)

    def test_multiplier_above_bound_rejected(self):
        with pytest.raises(ValidationError):
            Policy(**self._base_kwargs(), mortality_multiplier=25.0)

    def test_negative_flat_extra_rejected(self):
        with pytest.raises(ValidationError):
            Policy(**self._base_kwargs(), flat_extra_per_1000=-1.0)

    def test_flat_extra_above_bound_rejected(self):
        with pytest.raises(ValidationError):
            Policy(**self._base_kwargs(), flat_extra_per_1000=150.0)


class TestInforceBlock:
    """Verify InforceBlock construction and vectorized attribute access."""

    def test_n_policies(self, small_mixed_block):
        assert small_mixed_block.n_policies == 5

    def test_attained_age_vec_shape_and_dtype(self, small_mixed_block):
        vec = small_mixed_block.attained_age_vec
        assert vec.shape == (5,)
        assert vec.dtype == np.int32

    def test_face_amount_vec_values(self, small_mixed_block):
        expected = np.array([250_000, 500_000, 300_000, 750_000, 1_000_000], dtype=np.float64)
        np.testing.assert_array_equal(small_mixed_block.face_amount_vec, expected)

    def test_monthly_premium_vec(self, single_policy_block):
        expected = 1_500.0 / 12.0
        np.testing.assert_allclose(single_policy_block.monthly_premium_vec[0], expected)

    def test_total_face_amount(self, small_mixed_block):
        expected = 250_000 + 500_000 + 300_000 + 750_000 + 1_000_000
        assert small_mixed_block.total_face_amount() == expected

    def test_mixed_valuation_dates_raises(self):
        p1 = Policy(
            policy_id="P1",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=100_000,
            annual_premium=500,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        p2 = Policy(
            policy_id="P2",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=100_000,
            annual_premium=500,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2026, 1, 1),  # different date!
        )
        with pytest.raises(PolarisValidationError):
            InforceBlock(policies=[p1, p2])


class TestInforceBlockSubstandardVecs:
    """Verify vectorized access to substandard-rating fields (ADR-042)."""

    def test_defaults_are_neutral(self, small_mixed_block):
        # small_mixed_block was constructed without specifying rating fields;
        # defaults (1.0, 0.0) must flow through to the vec properties so
        # downstream engines can safely multiply/add them into rate arrays.
        mult = small_mixed_block.mortality_multiplier_vec
        flat = small_mixed_block.flat_extra_vec
        assert mult.shape == (5,)
        assert flat.shape == (5,)
        assert mult.dtype == np.float64
        assert flat.dtype == np.float64
        np.testing.assert_array_equal(mult, np.ones(5, dtype=np.float64))
        np.testing.assert_array_equal(flat, np.zeros(5, dtype=np.float64))

    def test_explicit_ratings_flow_through(self):
        policies = [
            Policy(
                policy_id="STD",
                issue_age=40,
                attained_age=40,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=100_000,
                annual_premium=500,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            ),
            Policy(
                policy_id="TABLE_4",
                issue_age=40,
                attained_age=40,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="SUBSTANDARD",
                face_amount=100_000,
                annual_premium=500,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                mortality_multiplier=4.0,
                flat_extra_per_1000=5.0,
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            ),
        ]
        block = InforceBlock(policies=policies)
        np.testing.assert_array_equal(
            block.mortality_multiplier_vec, np.array([1.0, 4.0], dtype=np.float64)
        )
        np.testing.assert_array_equal(block.flat_extra_vec, np.array([0.0, 5.0], dtype=np.float64))


class TestProjectionConfig:
    """Verify ProjectionConfig computed properties."""

    def test_projection_months(self, standard_projection_config):
        assert standard_projection_config.projection_months == 240

    def test_monthly_discount_factor(self, standard_projection_config):
        expected = (1.05) ** (-1 / 12)
        np.testing.assert_allclose(
            standard_projection_config.monthly_discount_factor,
            expected,
            rtol=1e-10,
        )

    def test_monthly_accumulation_factor_inverse_of_discount(self, standard_projection_config):
        v = standard_projection_config.monthly_discount_factor
        u = standard_projection_config.monthly_accumulation_factor
        np.testing.assert_allclose(v * u, 1.0, rtol=1e-10)

    def test_effective_valuation_rate_uses_explicit_rate(self, standard_projection_config):
        assert standard_projection_config.effective_valuation_rate == 0.035

    def test_effective_valuation_rate_falls_back_to_discount(self, pricing_projection_config):
        assert pricing_projection_config.effective_valuation_rate == 0.10

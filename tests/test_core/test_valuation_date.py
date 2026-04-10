"""Tests for valuation date feature — dynamic age/duration computation.

Verifies that InforceBlock.attained_age_vec_at() and
duration_inforce_vec_at() correctly compute ages and durations relative
to a given valuation date, and that DealConfig propagates valuation_date
through the pipeline.
"""

from datetime import date

import numpy as np

from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import DealConfig, PipelineInputs, build_projection_config
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus


def _make_policy(
    issue_age: int = 40,
    issue_date: date = date(2020, 1, 1),
    valuation_date: date = date(2025, 1, 1),
    policy_id: str = "TEST_VAL",
) -> Policy:
    """Helper to create a policy with specified issue/valuation dates."""
    elapsed_years = valuation_date.year - issue_date.year
    return Policy(
        policy_id=policy_id,
        issue_age=issue_age,
        attained_age=issue_age + elapsed_years,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=500_000.0,
        annual_premium=5_000.0,
        product_type=ProductType.TERM,
        policy_term=20,
        duration_inforce=(valuation_date.year - issue_date.year) * 12,
        reinsurance_cession_pct=0.50,
        issue_date=issue_date,
        valuation_date=valuation_date,
    )


class TestAttainedAgeVecAt:
    """Verify dynamic attained age computation relative to valuation date."""

    def test_same_date_as_issue(self):
        """When valuation_date == issue_date, attained_age == issue_age."""
        p = _make_policy(issue_age=40, issue_date=date(2025, 1, 1), valuation_date=date(2025, 1, 1))
        block = InforceBlock(policies=[p])
        ages = block.attained_age_vec_at(date(2025, 1, 1))
        assert ages[0] == 40

    def test_five_years_later(self):
        """Attained age shifts by 5 when valuation date is 5 years after issue."""
        p = _make_policy(issue_age=40, issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        block = InforceBlock(policies=[p])
        ages = block.attained_age_vec_at(date(2025, 1, 1))
        assert ages[0] == 45

    def test_ten_years_later(self):
        """Attained age shifts by 10 for a 10-year gap."""
        p = _make_policy(issue_age=30, issue_date=date(2015, 1, 1), valuation_date=date(2015, 1, 1))
        block = InforceBlock(policies=[p])
        ages = block.attained_age_vec_at(date(2025, 1, 1))
        assert ages[0] == 40

    def test_partial_year_truncates(self):
        """Partial years are truncated (whole years only)."""
        p = _make_policy(
            issue_age=40, issue_date=date(2020, 6, 15), valuation_date=date(2020, 6, 15)
        )
        block = InforceBlock(policies=[p])
        # 4 years and ~6 months → 4 whole years elapsed
        ages = block.attained_age_vec_at(date(2025, 1, 1))
        assert ages[0] == 44

    def test_revalue_at_different_dates(self):
        """Same block re-valued at two dates gives different ages."""
        p = _make_policy(issue_age=35, issue_date=date(2020, 1, 1), valuation_date=date(2020, 1, 1))
        block = InforceBlock(policies=[p])

        ages_2023 = block.attained_age_vec_at(date(2023, 1, 1))
        ages_2028 = block.attained_age_vec_at(date(2028, 1, 1))

        assert ages_2023[0] == 38
        assert ages_2028[0] == 43

    def test_multi_policy_block(self):
        """Correct vectorised computation across multiple policies."""
        policies = [
            _make_policy(
                issue_age=30,
                issue_date=date(2018, 1, 1),
                valuation_date=date(2025, 1, 1),
                policy_id="P1",
            ),
            _make_policy(
                issue_age=50,
                issue_date=date(2023, 1, 1),
                valuation_date=date(2025, 1, 1),
                policy_id="P2",
            ),
        ]
        block = InforceBlock(policies=policies)

        ages = block.attained_age_vec_at(date(2025, 1, 1))
        np.testing.assert_array_equal(ages, np.array([37, 52], dtype=np.int32))

    def test_dtype_is_int32(self):
        """Return array has dtype int32."""
        p = _make_policy()
        block = InforceBlock(policies=[p])
        ages = block.attained_age_vec_at(date(2025, 1, 1))
        assert ages.dtype == np.int32


class TestDurationInforceVecAt:
    """Verify dynamic duration-in-force computation relative to valuation date."""

    def test_same_date_as_issue(self):
        """Duration is 0 when valuation_date == issue_date."""
        p = _make_policy(issue_date=date(2025, 1, 1), valuation_date=date(2025, 1, 1))
        block = InforceBlock(policies=[p])
        durations = block.duration_inforce_vec_at(date(2025, 1, 1))
        assert durations[0] == 0

    def test_five_years_gives_60_months(self):
        """5 years → 60 months."""
        p = _make_policy(issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        block = InforceBlock(policies=[p])
        durations = block.duration_inforce_vec_at(date(2025, 1, 1))
        assert durations[0] == 60

    def test_partial_month(self):
        """Partial months are not counted (whole months only)."""
        p = _make_policy(issue_date=date(2024, 1, 15), valuation_date=date(2024, 1, 15))
        block = InforceBlock(policies=[p])
        # Jan 15 → Apr 10: 2 complete months (Feb 15, Mar 15 passed; Apr 15 not reached)
        durations = block.duration_inforce_vec_at(date(2024, 4, 10))
        assert durations[0] == 2

    def test_revalue_at_different_dates(self):
        """Same block re-valued at two dates gives different durations."""
        p = _make_policy(issue_date=date(2020, 1, 1), valuation_date=date(2020, 1, 1))
        block = InforceBlock(policies=[p])

        dur_2023 = block.duration_inforce_vec_at(date(2023, 1, 1))
        dur_2028 = block.duration_inforce_vec_at(date(2028, 1, 1))

        assert dur_2023[0] == 36
        assert dur_2028[0] == 96

    def test_multi_policy_block(self):
        """Correct vectorised computation across multiple policies."""
        policies = [
            _make_policy(
                issue_date=date(2022, 1, 1),
                valuation_date=date(2025, 1, 1),
                policy_id="P1",
            ),
            _make_policy(
                issue_date=date(2024, 7, 1),
                valuation_date=date(2025, 1, 1),
                policy_id="P2",
            ),
        ]
        block = InforceBlock(policies=policies)

        durations = block.duration_inforce_vec_at(date(2025, 1, 1))
        np.testing.assert_array_equal(durations, np.array([36, 6], dtype=np.int32))

    def test_dtype_is_int32(self):
        """Return array has dtype int32."""
        p = _make_policy()
        block = InforceBlock(policies=[p])
        durations = block.duration_inforce_vec_at(date(2025, 1, 1))
        assert durations.dtype == np.int32


class TestDealConfigValuationDate:
    """Verify DealConfig valuation_date propagation."""

    def test_default_is_today(self):
        """DealConfig.valuation_date defaults to date.today()."""
        cfg = DealConfig()
        assert cfg.valuation_date == date.today()

    def test_explicit_valuation_date(self):
        """DealConfig accepts an explicit valuation_date."""
        cfg = DealConfig(valuation_date=date(2024, 6, 30))
        assert cfg.valuation_date == date(2024, 6, 30)

    def test_to_dict_includes_valuation_date(self):
        """to_dict() includes valuation_date."""
        cfg = DealConfig(valuation_date=date(2024, 6, 30))
        d = cfg.to_dict()
        assert d["valuation_date"] == date(2024, 6, 30)

    def test_build_projection_config_uses_deal_valuation_date(self):
        """build_projection_config uses DealConfig.valuation_date."""
        deal = DealConfig(valuation_date=date(2024, 3, 15))
        inputs = PipelineInputs(deal=deal)
        config = build_projection_config(inputs)
        assert config.valuation_date == date(2024, 3, 15)

    def test_explicit_override_takes_precedence(self):
        """Explicit valuation_date arg overrides DealConfig."""
        deal = DealConfig(valuation_date=date(2024, 3, 15))
        inputs = PipelineInputs(deal=deal)
        config = build_projection_config(inputs, valuation_date=date(2023, 12, 31))
        assert config.valuation_date == date(2023, 12, 31)


class TestConsistencyBetweenStaticAndDynamic:
    """Verify that dynamic methods match static fields for the original valuation date."""

    def test_ages_match_at_original_valuation_date(self):
        """attained_age_vec_at(original_date) matches attained_age_vec."""
        p = _make_policy(issue_age=40, issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        block = InforceBlock(policies=[p])

        static_ages = block.attained_age_vec
        dynamic_ages = block.attained_age_vec_at(date(2025, 1, 1))

        np.testing.assert_array_equal(static_ages, dynamic_ages)

    def test_durations_match_at_original_valuation_date(self):
        """duration_inforce_vec_at(original_date) matches duration_inforce_vec."""
        p = _make_policy(issue_age=40, issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        block = InforceBlock(policies=[p])

        static_dur = block.duration_inforce_vec
        dynamic_dur = block.duration_inforce_vec_at(date(2025, 1, 1))

        np.testing.assert_array_equal(static_dur, dynamic_dur)

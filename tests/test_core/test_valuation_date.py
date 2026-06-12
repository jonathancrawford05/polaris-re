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
    """Verify DealConfig valuation_date propagation (ADR-074)."""

    def test_default_is_none(self):
        """DealConfig.valuation_date defaults to None — defer to the block.

        A wall-clock default here would make the block-date fallback in
        build_pipeline unreachable and let results drift with the run
        date (ADR-074).
        """
        cfg = DealConfig()
        assert cfg.valuation_date is None

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

    def test_build_projection_config_today_only_without_deal_date(self):
        """With no explicit arg and no deal date, today is the terminal fallback.

        This is the generated-data path — build_projection_config has no
        block access; block-aware callers go through build_pipeline.
        """
        config = build_projection_config(PipelineInputs())
        assert config.valuation_date == date.today()


class TestBuildPipelineResolution:
    """build_pipeline resolution chain: explicit → deal → block → today (ADR-074)."""

    @staticmethod
    def _block(valuation_date: date) -> InforceBlock:
        return InforceBlock(
            policies=[
                _make_policy(
                    issue_date=valuation_date,
                    valuation_date=valuation_date,
                    policy_id="RES_1",
                )
            ]
        )

    @staticmethod
    def _inputs(deal: DealConfig | None = None) -> PipelineInputs:
        # Flat mortality so no SOA table CSVs are required.
        from polaris_re.core.pipeline import MortalityConfig

        kwargs = {"mortality": MortalityConfig(source="flat", flat_qx=0.003)}
        if deal is not None:
            kwargs["deal"] = deal
        return PipelineInputs(**kwargs)

    def test_block_date_wins_when_deal_date_unset(self):
        """Default DealConfig (valuation_date=None) resolves to the block date.

        This is the QA-gap regression: the resolved config must never
        silently land on date.today() when the block carries real dates.
        """
        from polaris_re.core.pipeline import build_pipeline

        block_date = date(2025, 7, 1)
        _inf, _assumptions, config = build_pipeline(self._block(block_date), self._inputs())
        assert config.valuation_date == block_date
        assert config.valuation_date != date.today()

    def test_deal_date_overrides_block_date(self):
        """An explicit DealConfig.valuation_date beats the block date."""
        from polaris_re.core.pipeline import build_pipeline

        inputs = self._inputs(DealConfig(valuation_date=date(2025, 9, 1)))
        _inf, _assumptions, config = build_pipeline(self._block(date(2025, 7, 1)), inputs)
        assert config.valuation_date == date(2025, 9, 1)

    def test_explicit_arg_overrides_everything(self):
        """The explicit valuation_date argument beats deal and block dates."""
        from polaris_re.core.pipeline import build_pipeline

        inputs = self._inputs(DealConfig(valuation_date=date(2025, 9, 1)))
        _inf, _assumptions, config = build_pipeline(
            self._block(date(2025, 7, 1)), inputs, valuation_date=date(2025, 11, 1)
        )
        assert config.valuation_date == date(2025, 11, 1)


class TestValidateDateConsistency:
    """InforceBlock.validate_date_consistency — load-time guard (ADR-074)."""

    def test_consistent_block_passes(self):
        """Stored scalars matching the dates pass silently."""
        p = _make_policy(issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        InforceBlock(policies=[p]).validate_date_consistency()

    def test_duration_mismatch_raises(self):
        """Stored duration far from the date-derived months is rejected."""
        import pytest

        from polaris_re.core.exceptions import PolarisValidationError

        p = _make_policy(issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        p = p.model_copy(update={"duration_inforce": 0})  # dates imply 60
        with pytest.raises(PolarisValidationError, match="duration_inforce=0"):
            InforceBlock(policies=[p]).validate_date_consistency()

    def test_attained_age_mismatch_raises(self):
        """Stored attained_age far from issue_age + elapsed years is rejected."""
        import pytest

        from polaris_re.core.exceptions import PolarisValidationError

        p = _make_policy(issue_age=40, issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        p = p.model_copy(update={"attained_age": 49})  # derived is 45
        with pytest.raises(PolarisValidationError, match="attained_age=49"):
            InforceBlock(policies=[p]).validate_date_consistency()

    def test_one_month_tolerance_accepted(self):
        """±1 month duration gap (partial-month conventions) is tolerated."""
        p = _make_policy(issue_date=date(2020, 1, 1), valuation_date=date(2025, 1, 1))
        p = p.model_copy(update={"duration_inforce": 59})  # derived is 60
        InforceBlock(policies=[p]).validate_date_consistency()

    def test_load_inforce_runs_guard_on_dicts(self):
        """load_inforce(policies_dict=...) rejects inconsistent rows."""
        import pytest

        from polaris_re.core.exceptions import PolarisValidationError
        from polaris_re.core.pipeline import load_inforce

        with pytest.raises(PolarisValidationError, match="internally inconsistent"):
            load_inforce(
                policies_dict=[
                    {
                        "policy_id": "BAD-1",
                        "issue_age": 40,
                        "attained_age": 40,
                        "sex": "M",
                        "smoker": False,
                        "face_amount": 100_000.0,
                        "annual_premium": 500.0,
                        "policy_term": 20,
                        "duration_inforce": 0,
                        "issue_date": "2020-01-01",
                        "valuation_date": "2025-01-01",
                    }
                ]
            )


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

"""Tests for YRT Rate Schedule Generator."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.rate_schedule import YRTRateSchedule
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def assumptions():
    """Create assumptions for rate schedule tests."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.UNKNOWN,
    )
    lapse = LapseAssumption.from_duration_table(
        {1: 0.10, 2: 0.08, 3: 0.06, 4: 0.05, 5: 0.04, "ultimate": 0.03}
    )
    return AssumptionSet(mortality=mortality, lapse=lapse, version="test-schedule")


@pytest.fixture()
def config():
    """Projection config for rate schedule tests."""
    return ProjectionConfig(
        projection_horizon_years=20,
        discount_rate=0.05,
        valuation_date=date(2025, 1, 1),
    )


class TestYRTRateSchedule:
    """Tests for rate schedule generation."""

    def test_basic_generation(self, assumptions, config):
        """Generates a rate schedule for a few ages."""
        scheduler = YRTRateSchedule(assumptions=assumptions, config=config, target_irr=0.10)
        df = scheduler.generate(
            ages=[35, 45],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
            policy_term=20,
        )
        assert len(df) == 2
        assert "rate_per_1000" in df.columns
        assert "issue_age" in df.columns

    def test_rates_are_positive(self, assumptions, config):
        """Solved rates should be positive."""
        scheduler = YRTRateSchedule(assumptions=assumptions, config=config, target_irr=0.10)
        df = scheduler.generate(
            ages=[35, 40, 45],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
        )
        rates = df["rate_per_1000"].to_numpy()
        valid_rates = rates[~np.isnan(rates)]
        assert len(valid_rates) > 0
        assert np.all(valid_rates > 0)

    def test_rates_increase_with_age(self, assumptions, config):
        """Rates should generally increase with age (higher mortality = higher rate)."""
        scheduler = YRTRateSchedule(assumptions=assumptions, config=config, target_irr=0.10)
        df = scheduler.generate(
            ages=[30, 40, 50],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
        )
        rates = df["rate_per_1000"].to_numpy()
        valid = rates[~np.isnan(rates)]
        if len(valid) >= 2:
            # At minimum, oldest should have higher rate than youngest
            assert valid[-1] > valid[0]

    def test_output_columns(self, assumptions, config):
        """Output DataFrame has expected columns."""
        scheduler = YRTRateSchedule(assumptions=assumptions, config=config)
        df = scheduler.generate(ages=[40], sexes=[Sex.MALE], smoker_statuses=[SmokerStatus.UNKNOWN])
        expected = {"issue_age", "sex", "smoker_status", "policy_term", "rate_per_1000", "irr"}
        assert set(df.columns) == expected

    def test_grid_size(self, assumptions, config):
        """Output has correct number of rows for the grid."""
        scheduler = YRTRateSchedule(assumptions=assumptions, config=config)
        df = scheduler.generate(
            ages=[30, 40, 50],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
        )
        assert len(df) == 3  # 3 ages x 1 sex x 1 smoker

    def test_different_target_irr(self, assumptions, config):
        """Different target IRR produces different rates."""
        sched_low = YRTRateSchedule(assumptions=assumptions, config=config, target_irr=0.08)
        sched_high = YRTRateSchedule(assumptions=assumptions, config=config, target_irr=0.15)

        df_low = sched_low.generate(
            ages=[40], sexes=[Sex.MALE], smoker_statuses=[SmokerStatus.UNKNOWN]
        )
        df_high = sched_high.generate(
            ages=[40], sexes=[Sex.MALE], smoker_statuses=[SmokerStatus.UNKNOWN]
        )

        rate_low = df_low["rate_per_1000"][0]
        rate_high = df_high["rate_per_1000"][0]

        if not (np.isnan(rate_low) or np.isnan(rate_high)):
            # Rates should differ for different target IRRs
            assert rate_low != rate_high
            # Higher hurdle rate discounts future claim outflows more, so
            # the reinsurer can accept a lower rate and still hit IRR
            assert rate_high < rate_low


class TestGenerateTable:
    """Tests for `YRTRateSchedule.generate_table()` (Slice 2 of YRT rate table)."""

    def test_generate_table_returns_yrt_rate_table(self, assumptions, config):
        """generate_table() returns a populated YRTRateTable."""
        from polaris_re.reinsurance import YRTRateTable

        scheduler = YRTRateSchedule(assumptions=assumptions, config=config)
        table = scheduler.generate_table(
            ages=[35, 40, 45],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
            policy_term=20,
            select_period_years=0,
        )
        assert isinstance(table, YRTRateTable)
        assert table.min_age == 35
        assert table.max_age == 45
        assert table.select_period_years == 0
        # The (MALE, UNKNOWN) cohort must be loaded.
        assert "M_U" in table.arrays

    def test_generate_table_round_trips_through_treaty(self, assumptions, config):
        """A generated table fed back into YRTTreaty.apply() produces a
        non-empty ceded premium series with no errors. This is the closed-
        loop sanity check for the Slice 2 contract."""
        from polaris_re.core.inforce import InforceBlock
        from polaris_re.core.policy import Policy, ProductType
        from polaris_re.products.term_life import TermLife
        from polaris_re.reinsurance import YRTTreaty

        scheduler = YRTRateSchedule(assumptions=assumptions, config=config)
        table = scheduler.generate_table(
            ages=[40],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
            policy_term=20,
            select_period_years=0,
        )

        policy = Policy(
            policy_id="ROUND_TRIP",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.UNKNOWN,
            underwriting_class="STANDARD",
            face_amount=1_000_000.0,
            annual_premium=12_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=1.0,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        gross = TermLife(block, assumptions, config).project(seriatim=True)

        treaty = YRTTreaty(
            cession_pct=1.0,
            total_face_amount=1_000_000.0,
            yrt_rate_table=table,
        )
        net, ceded = treaty.apply(gross, inforce=block)
        # No NaNs / Infs allowed in either output.
        assert np.all(np.isfinite(ceded.gross_premiums))
        assert np.all(np.isfinite(net.net_cash_flow))
        # Some ceded premium must be collected.
        assert ceded.gross_premiums.sum() > 0


class TestExcelOutput:
    """Tests for Excel rate schedule export."""

    def test_excel_output(self, assumptions, config, tmp_path):
        """Excel file is created with correct structure."""
        from polaris_re.utils.excel_output import write_rate_schedule_excel

        scheduler = YRTRateSchedule(assumptions=assumptions, config=config)
        df = scheduler.generate(
            ages=[35, 45],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
        )

        excel_path = tmp_path / "rates.xlsx"
        write_rate_schedule_excel(df, excel_path)

        assert excel_path.exists()
        assert excel_path.stat().st_size > 0

    def test_excel_has_sheets(self, assumptions, config, tmp_path):
        """Excel workbook has correct sheet names."""
        from openpyxl import load_workbook

        from polaris_re.utils.excel_output import write_rate_schedule_excel

        scheduler = YRTRateSchedule(assumptions=assumptions, config=config)
        df = scheduler.generate(
            ages=[40],
            sexes=[Sex.MALE],
            smoker_statuses=[SmokerStatus.UNKNOWN],
        )

        excel_path = tmp_path / "rates.xlsx"
        write_rate_schedule_excel(df, excel_path)

        wb = load_workbook(excel_path)
        assert "Summary" in wb.sheetnames
        assert "M_U" in wb.sheetnames

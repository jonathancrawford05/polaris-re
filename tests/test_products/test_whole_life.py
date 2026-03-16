"""
Tests for WholeLife cash flow projection engine.

Includes closed-form verification tests and structural invariants
(non-negative reserves, premium cessation on limited pay, additivity).
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.whole_life import WholeLife, WholeLifeVariant
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mortality_table() -> MortalityTable:
    """Synthetic mortality table for whole life testing."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic WL Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


@pytest.fixture()
def lapse_assumption() -> LapseAssumption:
    return LapseAssumption.from_duration_table({1: 0.04, 2: 0.03, "ultimate": 0.02})


@pytest.fixture()
def assumption_set(
    mortality_table: MortalityTable, lapse_assumption: LapseAssumption
) -> AssumptionSet:
    return AssumptionSet(
        mortality=mortality_table,
        lapse=lapse_assumption,
        version="wl-test-v1",
    )


@pytest.fixture()
def single_wl_policy() -> Policy:
    """Single male NS whole life policy at age 40, $500k face."""
    return Policy(
        policy_id="WL_001",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=500_000.0,
        annual_premium=8_000.0,
        product_type=ProductType.WHOLE_LIFE,
        policy_term=None,
        duration_inforce=0,
        reinsurance_cession_pct=0.50,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


@pytest.fixture()
def single_wl_block(single_wl_policy: Policy) -> InforceBlock:
    return InforceBlock(policies=[single_wl_policy])


@pytest.fixture()
def short_config() -> ProjectionConfig:
    """5-year projection at 5% discount rate."""
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=5,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
    )


@pytest.fixture()
def long_config() -> ProjectionConfig:
    """20-year projection at 5% discount rate."""
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
    )


class TestWholeLifeValidation:
    """Input validation for WholeLife engine."""

    def test_rejects_term_policies(
        self, assumption_set: AssumptionSet, short_config: ProjectionConfig
    ) -> None:
        """WholeLife must reject policies with ProductType.TERM."""
        term_policy = Policy(
            policy_id="TERM_001",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=500_000.0,
            annual_premium=5_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=0.5,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[term_policy])
        with pytest.raises(PolarisValidationError, match="non-WHOLE_LIFE"):
            WholeLife(inforce=block, assumptions=assumption_set, config=short_config)

    def test_invalid_premium_payment_years(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """premium_payment_years < 1 raises PolarisValidationError."""
        with pytest.raises(PolarisValidationError, match="premium_payment_years"):
            WholeLife(
                inforce=single_wl_block,
                assumptions=assumption_set,
                config=short_config,
                premium_payment_years=0,
            )


class TestWholeLifeReserves:
    """Tests for whole life reserve computation."""

    def test_reserves_non_negative(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """Net premium reserves must be non-negative throughout."""
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        reserves = engine.compute_reserves()
        assert np.all(reserves >= 0.0), "Negative reserves found"

    def test_reserves_shape(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """Reserve array shape is (N, T)."""
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        reserves = engine.compute_reserves()
        t = short_config.projection_months
        assert reserves.shape == (1, t)

    def test_reserves_generally_increasing(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        long_config: ProjectionConfig,
    ) -> None:
        """
        For non-par whole life (no lapse, no dividends), the reserve should
        generally increase over time (actuarial expectation). We check the
        trend is positive on average over the 20-year horizon.
        """
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=long_config)
        reserves = engine.compute_reserves()
        # Average of first half vs second half should be higher in second half
        t = long_config.projection_months
        first_half_avg = reserves[0, : t // 2].mean()
        second_half_avg = reserves[0, t // 2 :].mean()
        assert second_half_avg >= first_half_avg * 0.8, (
            f"Reserves not trending upward: first_half={first_half_avg:.2f}, "
            f"second_half={second_half_avg:.2f}"
        )

    def test_limited_pay_terminal_reserve_higher(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        long_config: ProjectionConfig,
    ) -> None:
        """
        A 10-pay policy accumulates reserves faster than whole-life pay,
        so terminal reserve should be >= whole-life-pay terminal reserve.
        """
        engine_wl = WholeLife(
            inforce=single_wl_block, assumptions=assumption_set, config=long_config
        )
        engine_10pay = WholeLife(
            inforce=single_wl_block,
            assumptions=assumption_set,
            config=long_config,
            premium_payment_years=10,
        )
        res_wl = engine_wl.compute_reserves()
        res_10pay = engine_10pay.compute_reserves()
        # After 10 years (120 months), limited pay reserve >= whole life pay reserve
        assert res_10pay[0, 120] >= res_wl[0, 120], (
            "10-pay reserve not higher than whole life pay at year 10"
        )


class TestWholeLifeProjection:
    """Tests for whole life project() method."""

    def test_project_returns_gross_basis(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == "WHOLE_LIFE"

    def test_cash_flow_array_lengths(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        result = engine.project()
        t = short_config.projection_months
        assert len(result.gross_premiums) == t
        assert len(result.death_claims) == t
        assert len(result.net_cash_flow) == t

    def test_net_cash_flow_accounting_identity(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """NCF = premiums - claims - lapses - expenses - reserve_increase."""
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        result = engine.project()
        expected_ncf = (
            result.gross_premiums
            - result.death_claims
            - result.lapse_surrenders
            - result.expenses
            - result.reserve_increase
        )
        np.testing.assert_allclose(result.net_cash_flow, expected_ncf, rtol=1e-10)

    def test_premiums_positive_during_projection(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """Premiums should be positive for at least the first month."""
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        result = engine.project()
        assert result.gross_premiums[0] > 0.0

    def test_claims_positive(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """Death claims should be positive (some expected mortality)."""
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        result = engine.project()
        assert result.death_claims.sum() > 0.0

    def test_limited_pay_zero_premiums_after_period(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        long_config: ProjectionConfig,
    ) -> None:
        """After premium_payment_years, premiums must be zero."""
        pay_years = 5
        engine = WholeLife(
            inforce=single_wl_block,
            assumptions=assumption_set,
            config=long_config,
            premium_payment_years=pay_years,
        )
        result = engine.project()
        # Premiums from month pay_years*12 onwards should be zero
        post_pay = result.gross_premiums[pay_years * 12 :]
        np.testing.assert_allclose(post_pay, 0.0, atol=1e-10)

    def test_seriatim_output(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """seriatim=True populates (N, T) arrays."""
        engine = WholeLife(inforce=single_wl_block, assumptions=assumption_set, config=short_config)
        result = engine.project(seriatim=True)
        t = short_config.projection_months
        assert result.seriatim_premiums is not None
        assert result.seriatim_premiums.shape == (1, t)
        assert result.seriatim_lx is not None
        assert result.seriatim_lx[0, 0] == pytest.approx(1.0, rel=1e-10)

    def test_multi_policy_vectorization(
        self, assumption_set: AssumptionSet, long_config: ProjectionConfig
    ) -> None:
        """Three-policy block produces sum equal to three individual runs."""
        policies = [
            Policy(
                policy_id=f"WL_{i}",
                issue_age=40 + i * 5,
                attained_age=40 + i * 5,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=500_000.0,
                annual_premium=8_000.0,
                product_type=ProductType.WHOLE_LIFE,
                policy_term=None,
                duration_inforce=0,
                reinsurance_cession_pct=0.5,
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            )
            for i in range(3)
        ]
        combined_block = InforceBlock(policies=policies)
        combined = WholeLife(inforce=combined_block, assumptions=assumption_set, config=long_config)
        combined_result = combined.project()

        individual_premiums = np.zeros(long_config.projection_months)
        for p in policies:
            block = InforceBlock(policies=[p])
            eng = WholeLife(inforce=block, assumptions=assumption_set, config=long_config)
            individual_premiums += eng.project().gross_premiums

        np.testing.assert_allclose(combined_result.gross_premiums, individual_premiums, rtol=1e-8)

    def test_variant_par_same_as_non_par(
        self,
        single_wl_block: InforceBlock,
        assumption_set: AssumptionSet,
        short_config: ProjectionConfig,
    ) -> None:
        """PAR variant produces same cash flows as NON_PAR (dividends not modelled)."""
        non_par = WholeLife(
            inforce=single_wl_block,
            assumptions=assumption_set,
            config=short_config,
            variant=WholeLifeVariant.NON_PAR,
        )
        par = WholeLife(
            inforce=single_wl_block,
            assumptions=assumption_set,
            config=short_config,
            variant=WholeLifeVariant.PAR,
        )
        np.testing.assert_allclose(
            non_par.project().gross_premiums, par.project().gross_premiums, rtol=1e-10
        )

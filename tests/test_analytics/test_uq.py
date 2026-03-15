"""
Tests for MonteCarloUQ — Monte Carlo uncertainty quantification.

Fast tests use n_scenarios=20 to keep the suite snappy.
Slow tests (marked @pytest.mark.slow) use larger n_scenarios.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.uq import MonteCarloUQ, UQParameters, UQResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mortality_table() -> MortalityTable:
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic UQ Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


@pytest.fixture()
def assumption_set(mortality_table: MortalityTable) -> AssumptionSet:
    lapse = LapseAssumption.from_duration_table({1: 0.06, 2: 0.04, "ultimate": 0.02})
    return AssumptionSet(
        mortality=mortality_table,
        lapse=lapse,
        version="uq-test-v1",
    )


@pytest.fixture()
def inforce() -> InforceBlock:
    policy = Policy(
        policy_id="UQ_001",
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
        reinsurance_cession_pct=0.50,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )
    return InforceBlock(policies=[policy])


@pytest.fixture()
def config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.08,
        valuation_interest_rate=0.035,
    )


@pytest.fixture()
def yrt_treaty() -> YRTTreaty:
    return YRTTreaty(
        cession_pct=0.50,
        total_face_amount=500_000.0,
        flat_yrt_rate_per_1000=1.5,
    )


class TestUQParameters:
    """Tests for UQParameters dataclass."""

    def test_defaults(self) -> None:
        p = UQParameters()
        assert p.mortality_log_sigma == pytest.approx(0.10)
        assert p.lapse_log_sigma == pytest.approx(0.15)
        assert p.interest_rate_sigma == pytest.approx(0.005)

    def test_custom_params(self) -> None:
        p = UQParameters(mortality_log_sigma=0.05, lapse_log_sigma=0.08, interest_rate_sigma=0.002)
        assert p.mortality_log_sigma == pytest.approx(0.05)


class TestMonteCarloUQSmall:
    """Fast tests using small n_scenarios."""

    def test_run_returns_uq_result(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
        yrt_treaty: YRTTreaty,
    ) -> None:
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=10,
            seed=42,
        )
        result = uq.run()
        assert isinstance(result, UQResult)
        assert result.n_scenarios == 10

    def test_output_array_shapes(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
        yrt_treaty: YRTTreaty,
    ) -> None:
        n = 20
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=n,
            seed=42,
        )
        result = uq.run()
        assert result.pv_profits.shape == (n,)
        assert result.irrs.shape == (n,)
        assert result.profit_margins.shape == (n,)
        assert result.mort_multipliers.shape == (n,)

    def test_reproducibility_same_seed(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
        yrt_treaty: YRTTreaty,
    ) -> None:
        """Same seed → identical results."""
        uq1 = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=10,
            seed=123,
        )
        uq2 = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=10,
            seed=123,
        )
        r1 = uq1.run()
        r2 = uq2.run()
        np.testing.assert_array_equal(r1.pv_profits, r2.pv_profits)
        np.testing.assert_array_equal(r1.mort_multipliers, r2.mort_multipliers)

    def test_different_seeds_give_different_results(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
        yrt_treaty: YRTTreaty,
    ) -> None:
        """Different seeds → different multiplier samples."""
        uq1 = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=10,
            seed=1,
        )
        uq2 = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=10,
            seed=2,
        )
        r1 = uq1.run()
        r2 = uq2.run()
        assert not np.allclose(r1.mort_multipliers, r2.mort_multipliers)

    def test_no_treaty(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
    ) -> None:
        """treaty=None runs on gross basis (direct pricing)."""
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=None,
            hurdle_rate=0.08,
            n_scenarios=5,
            seed=42,
        )
        result = uq.run()
        assert result.pv_profits.shape == (5,)

    def test_mort_multipliers_lognormal_mean_approx_one(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
        yrt_treaty: YRTTreaty,
    ) -> None:
        """
        LogNormal(mean=0, sigma=sigma) has E[X] = exp(sigma^2/2).
        For sigma=0.10, mean ≈ 1.005, close to 1.0.
        """
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=1000,
            seed=42,
        )
        result = uq.run()
        # Mean of lognormal should be exp(sigma^2/2) ≈ 1.005
        expected_mean = np.exp(0.10**2 / 2)
        np.testing.assert_allclose(
            result.mort_multipliers.mean(), expected_mean, rtol=0.05
        )


class TestUQResultMetrics:
    """Tests for UQResult metrics (percentile, VaR, CVaR)."""

    @pytest.fixture()
    def sample_result(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
        yrt_treaty: YRTTreaty,
    ) -> UQResult:
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=50,
            seed=42,
        )
        return uq.run()

    def test_percentile_keys(self, sample_result: UQResult) -> None:
        pct = sample_result.percentile(50.0)
        assert "pv_profit" in pct
        assert "irr" in pct
        assert "profit_margin" in pct

    def test_percentile_50_within_range(self, sample_result: UQResult) -> None:
        p50 = sample_result.percentile(50.0)
        p10 = sample_result.percentile(10.0)
        p90 = sample_result.percentile(90.0)
        assert p10["pv_profit"] <= p50["pv_profit"] <= p90["pv_profit"]

    def test_var_definition(self, sample_result: UQResult) -> None:
        """VaR_95 is the 5th percentile of PV profits."""
        var_95 = sample_result.var(confidence=0.95)
        p5 = float(np.percentile(sample_result.pv_profits, 5.0))
        np.testing.assert_allclose(var_95, p5, rtol=1e-10)

    def test_cvar_le_var(self, sample_result: UQResult) -> None:
        """CVaR should be <= VaR (CVaR is mean of the worst tail, should be worse or equal)."""
        var_95 = sample_result.var(confidence=0.95)
        cvar_95 = sample_result.cvar(confidence=0.95)
        assert cvar_95 <= var_95 + 1e-8  # CVaR ≤ VaR

    def test_base_pv_profit_stored(self, sample_result: UQResult) -> None:
        """base_pv_profit is recorded and is a finite number."""
        assert np.isfinite(sample_result.base_pv_profit)

    def test_irrs_valid_when_not_nan(self, sample_result: UQResult) -> None:
        """All non-NaN IRR values must be finite (NaN is acceptable when NCF never changes sign)."""
        non_nan = sample_result.irrs[~np.isnan(sample_result.irrs)]
        # Simple YRT deals may have all-NaN IRRs (no capital-intensive structure),
        # so we only require that any computed IRRs are finite real numbers.
        assert np.all(np.isfinite(non_nan)), "Non-NaN IRR values contain Inf"


@pytest.mark.slow
class TestUQResultSlowN1000:
    """Larger-scale UQ tests. Marked slow; excluded from default test run."""

    def test_n1000_completes(
        self,
        inforce: InforceBlock,
        assumption_set: AssumptionSet,
        config: ProjectionConfig,
        yrt_treaty: YRTTreaty,
    ) -> None:
        uq = MonteCarloUQ(
            inforce=inforce,
            base_assumptions=assumption_set,
            base_config=config,
            treaty=yrt_treaty,
            hurdle_rate=0.08,
            n_scenarios=1000,
            seed=42,
        )
        result = uq.run()
        assert result.pv_profits.shape == (1000,)

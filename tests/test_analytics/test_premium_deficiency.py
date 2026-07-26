"""
PremiumDeficiencyTester tests — loss-recognition / premium-deficiency-reserve floor.

Key closed-form tests:
  1. Flat deterministic deficient block at rate 0 -> PDR is exact arithmetic.
  2. Sufficient block -> gross premium reserve negative, PDR floored at 0.
  3. existing_reserve nets against the gross premium reserve (FAS 60).
  4. gross_premium_reserve == -(sufficiency_margin) for the same block/rate
     (the analyzer this tool turns into a reserve floor).
  5. Single payment at month 12 -> PV equals v**12 exactly.
  6. reserve_floor == existing_reserve + premium_deficiency_reserve identity.
  7. Zero premium -> the whole benefit+expense PV is a deficiency.
  8. Validation: negative existing_reserve raises ValueError.
  9. Integration: TermLife GROSS projection -> coherent, sufficiency-consistent.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.premium_deficiency import (
    PremiumDeficiencyResult,
    PremiumDeficiencyTester,
)
from polaris_re.analytics.premium_sufficiency import PremiumSufficiencyTester
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_cashflow(
    *,
    premiums: np.ndarray,
    claims: np.ndarray | None = None,
    surrenders: np.ndarray | None = None,
    expenses: np.ndarray | None = None,
    basis: str = "GROSS",
) -> CashFlowResult:
    """Build a minimal CashFlowResult for premium-deficiency testing."""
    t = len(premiums)
    zeros = np.zeros(t, dtype=np.float64)
    claims = zeros if claims is None else claims
    surrenders = zeros if surrenders is None else surrenders
    expenses = zeros if expenses is None else expenses
    net = premiums - claims - surrenders - expenses
    return CashFlowResult(
        run_id="test",
        valuation_date=date(2025, 1, 1),
        basis=basis,  # type: ignore[arg-type]
        assumption_set_version="v1",
        product_type="TERM",
        projection_months=t,
        time_index=np.arange(
            np.datetime64("2025-01"), np.datetime64("2025-01") + t, dtype="datetime64[M]"
        ),
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=surrenders,
        expenses=expenses,
        reserve_balance=zeros,
        net_cash_flow=net,
    )


class TestClosedFormDeficientBlock:
    """Rate-0 arithmetic: PV is a plain sum, so every quantity is exact."""

    def _result(self, existing_reserve: float = 0.0) -> PremiumDeficiencyResult:
        # 12 months: premium 100, benefits 90, expenses 30 => net cost 20/mo.
        prem = np.full(12, 100.0, dtype=np.float64)
        claims = np.full(12, 90.0, dtype=np.float64)
        exp = np.full(12, 30.0, dtype=np.float64)
        cf = _make_cashflow(premiums=prem, claims=claims, expenses=exp)
        return PremiumDeficiencyTester(
            cf, discount_rate=0.0, existing_reserve=existing_reserve
        ).run()

    def test_gross_premium_reserve_is_exact(self) -> None:
        r = self._result()
        # PV(benefits+exp) - PV(prem) = 12*(90+30) - 12*100 = 1440 - 1200 = 240.
        np.testing.assert_allclose(r.gross_premium_reserve, 240.0)

    def test_pdr_equals_gross_premium_reserve_with_no_existing_reserve(self) -> None:
        r = self._result(existing_reserve=0.0)
        np.testing.assert_allclose(r.premium_deficiency_reserve, 240.0)
        np.testing.assert_allclose(r.reserve_floor, 240.0)
        assert r.is_deficient is True

    def test_pv_components_recorded(self) -> None:
        r = self._result()
        np.testing.assert_allclose(r.pv_premiums, 1200.0)
        np.testing.assert_allclose(r.pv_benefits, 1080.0)
        np.testing.assert_allclose(r.pv_expenses, 360.0)


class TestSufficientBlockIsFlooredAtZero:
    def test_surplus_produces_no_deficiency(self) -> None:
        prem = np.full(12, 100.0, dtype=np.float64)
        claims = np.full(12, 40.0, dtype=np.float64)
        exp = np.full(12, 20.0, dtype=np.float64)
        cf = _make_cashflow(premiums=prem, claims=claims, expenses=exp)
        r = PremiumDeficiencyTester(cf, discount_rate=0.0).run()
        # GPV = 12*(40+20) - 12*100 = 720 - 1200 = -480 (a surplus).
        np.testing.assert_allclose(r.gross_premium_reserve, -480.0)
        # A surplus never produces a negative reserve; the floor is 0.
        np.testing.assert_allclose(r.premium_deficiency_reserve, 0.0)
        np.testing.assert_allclose(r.reserve_floor, 0.0)
        assert r.is_deficient is False


class TestExistingReserveNetting:
    """FAS 60: PDR = max(0, GPV - existing_reserve)."""

    def _gpv_240(self, existing_reserve: float) -> PremiumDeficiencyResult:
        prem = np.full(12, 100.0, dtype=np.float64)
        claims = np.full(12, 90.0, dtype=np.float64)
        exp = np.full(12, 30.0, dtype=np.float64)
        cf = _make_cashflow(premiums=prem, claims=claims, expenses=exp)
        return PremiumDeficiencyTester(
            cf, discount_rate=0.0, existing_reserve=existing_reserve
        ).run()

    @pytest.mark.parametrize(
        ("existing_reserve", "expected_pdr", "expected_floor", "deficient"),
        [
            (0.0, 240.0, 240.0, True),
            (100.0, 140.0, 240.0, True),
            (240.0, 0.0, 240.0, False),  # reserve exactly covers -> not deficient
            (300.0, 0.0, 300.0, False),  # reserve already exceeds GPV
        ],
    )
    def test_netting(
        self,
        existing_reserve: float,
        expected_pdr: float,
        expected_floor: float,
        deficient: bool,
    ) -> None:
        r = self._gpv_240(existing_reserve)
        np.testing.assert_allclose(r.premium_deficiency_reserve, expected_pdr)
        np.testing.assert_allclose(r.reserve_floor, expected_floor)
        assert r.is_deficient is deficient

    def test_floor_identity(self) -> None:
        # reserve_floor == existing_reserve + premium_deficiency_reserve, always.
        for er in (0.0, 100.0, 240.0, 300.0):
            r = self._gpv_240(er)
            np.testing.assert_allclose(
                r.reserve_floor, r.existing_reserve + r.premium_deficiency_reserve
            )


class TestConsistencyWithSufficiency:
    """The tool turns the sufficiency analyzer's inception value into a floor."""

    @pytest.mark.parametrize("rate", [0.0, 0.03, 0.06, 0.10])
    def test_gross_premium_reserve_is_negative_sufficiency_margin(self, rate: float) -> None:
        rng = np.random.default_rng(7)
        prem = rng.uniform(50, 150, size=24)
        claims = rng.uniform(20, 120, size=24)
        surr = rng.uniform(0, 30, size=24)
        exp = rng.uniform(5, 40, size=24)
        cf = _make_cashflow(premiums=prem, claims=claims, surrenders=surr, expenses=exp)
        pdr = PremiumDeficiencyTester(cf, discount_rate=rate).run()
        suff = PremiumSufficiencyTester(cf, discount_rate=rate).run()
        # Same monthly discounting convention -> exact agreement.
        np.testing.assert_allclose(
            pdr.gross_premium_reserve, -suff.sufficiency_margin, rtol=0, atol=1e-9
        )
        np.testing.assert_allclose(pdr.pv_premiums, suff.pv_premiums, rtol=0, atol=1e-9)
        np.testing.assert_allclose(pdr.pv_benefits, suff.pv_benefits, rtol=0, atol=1e-9)


class TestDiscounting:
    def test_single_payment_month_12(self) -> None:
        t = 12
        prem = np.zeros(t, dtype=np.float64)
        claims = np.zeros(t, dtype=np.float64)
        claims[11] = 1000.0  # a single benefit at month 12
        cf = _make_cashflow(premiums=prem, claims=claims)
        rate = 0.06
        r = PremiumDeficiencyTester(cf, discount_rate=rate).run()
        v = (1.0 + rate) ** (-1.0 / 12.0)
        # Zero premium, one benefit: GPV = 1000 * v**12, all a deficiency.
        np.testing.assert_allclose(r.gross_premium_reserve, 1000.0 * v**12)
        np.testing.assert_allclose(r.premium_deficiency_reserve, 1000.0 * v**12)
        assert r.is_deficient is True


class TestEdgeCases:
    def test_zero_premium_whole_cost_is_deficiency(self) -> None:
        prem = np.zeros(12, dtype=np.float64)
        claims = np.full(12, 10.0, dtype=np.float64)
        exp = np.full(12, 5.0, dtype=np.float64)
        cf = _make_cashflow(premiums=prem, claims=claims, expenses=exp)
        r = PremiumDeficiencyTester(cf, discount_rate=0.0).run()
        np.testing.assert_allclose(r.gross_premium_reserve, 12 * 15.0)
        np.testing.assert_allclose(r.premium_deficiency_reserve, 180.0)
        assert r.is_deficient is True

    def test_empty_projection(self) -> None:
        cf = _make_cashflow(premiums=np.array([], dtype=np.float64))
        r = PremiumDeficiencyTester(cf, discount_rate=0.04).run()
        np.testing.assert_allclose(r.gross_premium_reserve, 0.0)
        np.testing.assert_allclose(r.premium_deficiency_reserve, 0.0)
        assert r.is_deficient is False

    def test_negative_existing_reserve_raises(self) -> None:
        cf = _make_cashflow(premiums=np.full(12, 100.0, dtype=np.float64))
        with pytest.raises(ValueError, match="existing_reserve"):
            PremiumDeficiencyTester(cf, discount_rate=0.04, existing_reserve=-1.0)


class TestTermLifeIntegration:
    def _term_gross(self) -> CashFlowResult:
        policy = Policy(
            policy_id="P1",
            issue_age=40,
            attained_age=40,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=1_000_000.0,
            annual_premium=12_000.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=0.0,
            issue_date=date(2025, 1, 1),
            valuation_date=date(2025, 1, 1),
        )
        block = InforceBlock(policies=[policy])
        table_array = load_mortality_csv(
            FIXTURES / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )
        mortality = MortalityTable.from_table_array(
            source=MortalityTableSource.SOA_VBT_2015,
            table_name="Synthetic Test",
            table_array=table_array,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
        )
        lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
        assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="test-v1")
        config = ProjectionConfig(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=20,
            discount_rate=0.04,
        )
        return TermLife(block, assumptions, config).project()

    def test_integration_coherent_and_sufficiency_consistent(self) -> None:
        cf = self._term_gross()
        r = PremiumDeficiencyTester(cf, discount_rate=0.04).run()
        suff = PremiumSufficiencyTester(cf, discount_rate=0.04).run()
        # Reserve floor is coherent and never below the held reserve credit.
        assert r.premium_deficiency_reserve >= 0.0
        np.testing.assert_allclose(
            r.reserve_floor, max(r.existing_reserve, r.gross_premium_reserve)
        )
        np.testing.assert_allclose(
            r.gross_premium_reserve, -suff.sufficiency_margin, rtol=0, atol=1e-6
        )

"""
Portfolio aggregation tests (Milestone 5.2, Slice 1).

Verifies the `Portfolio` multi-deal runner:
  1. Builder validation — duplicate ids, empty / multi-product blocks,
     non-proportional treaties.
  2. Closed-form aggregation — aggregate NCF equals the month-by-month
     sum of the independently computed per-deal reinsurer cash flows,
     including deals with mismatched projection horizons.
  3. PV-profit linearity — portfolio total equals the sum of per-deal
     PV profits.
  4. Concentration metrics — face shares and Herfindahl indices by
     cedant, product type, and treaty type.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.portfolio import (
    Deal,
    DealResult,
    Portfolio,
    PortfolioResult,
)
from polaris_re.analytics.profit_test import ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import ceded_to_reinsurer_view
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.reinsurance.modco import ModcoTreaty
from polaris_re.reinsurance.stop_loss import StopLossTreaty
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import MortalityTableArray

HURDLE = 0.10


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _mortality(qx: float = 0.003) -> MortalityTable:
    """Flat male non-smoker mortality table covering ages 18-120."""
    n_ages = 121 - 18
    rates = np.full((n_ages, 1), qx, dtype=np.float64)
    table_array = MortalityTableArray(
        rates=rates,
        min_age=18,
        max_age=120,
        select_period=0,
        source_file=Path("synthetic"),
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.CSO_2001,
        table_name=f"Flat {qx}",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


def _assumptions() -> AssumptionSet:
    lapse = LapseAssumption.from_duration_table({1: 0.06, 2: 0.05, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(mortality=_mortality(), lapse=lapse, version="portfolio-test-v1")


def _policy(policy_id: str, product: ProductType, face: float) -> Policy:
    is_term = product == ProductType.TERM
    return Policy(
        policy_id=policy_id,
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=face * (0.005 if is_term else 0.015),
        product_type=product,
        policy_term=20 if is_term else None,
        duration_inforce=0,
        reinsurance_cession_pct=0.0,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


def _block(
    prefix: str,
    product: ProductType = ProductType.TERM,
    n_policies: int = 2,
    face: float = 500_000.0,
) -> InforceBlock:
    return InforceBlock(
        policies=[_policy(f"{prefix}_{i:03d}", product, face) for i in range(n_policies)],
    )


def _config(horizon_years: int = 20) -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=horizon_years,
        discount_rate=0.05,
    )


def _deal_spec(
    deal_id: str,
    cedant: str,
    *,
    product: ProductType = ProductType.TERM,
    treaty: object | None = None,
    horizon_years: int = 20,
    n_policies: int = 2,
    face: float = 500_000.0,
) -> dict[str, object]:
    """Return a kwargs dict ready to splat into `Portfolio.add_deal`."""
    block = _block(deal_id, product, n_policies, face)
    if treaty is None:
        treaty = CoinsuranceTreaty(cession_pct=0.5, treaty_name=f"{deal_id}-coins")
    return {
        "deal_id": deal_id,
        "cedant": cedant,
        "inforce": block,
        "assumptions": _assumptions(),
        "config": _config(horizon_years),
        "treaty": treaty,
    }


def _independent_reinsurer_ncf(spec: dict[str, object]) -> np.ndarray:
    """Project a deal spec end-to-end and return the reinsurer NCF vector.

    Mirrors `Portfolio._run_deal` using the product engine + treaty
    directly, so the portfolio aggregate can be cross-checked against an
    independently computed figure.
    """
    engine = get_product_engine(
        inforce=spec["inforce"],  # type: ignore[arg-type]
        assumptions=spec["assumptions"],  # type: ignore[arg-type]
        config=spec["config"],  # type: ignore[arg-type]
    )
    gross = engine.project()
    _net, ceded = spec["treaty"].apply(gross)  # type: ignore[attr-defined]
    return ceded_to_reinsurer_view(ceded).net_cash_flow


# ---------------------------------------------------------------------------
# Builder validation
# ---------------------------------------------------------------------------


class TestPortfolioBuilder:
    def test_add_deal_is_chainable(self):
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
        )
        assert isinstance(portfolio, Portfolio)
        assert portfolio.n_deals == 2

    def test_deals_property_exposes_typed_deals(self):
        portfolio = Portfolio().add_deal(**_deal_spec("D1", "CedantA"))
        assert len(portfolio.deals) == 1
        assert isinstance(portfolio.deals[0], Deal)
        assert portfolio.deals[0].deal_id == "D1"
        assert portfolio.deals[0].product_type == "TERM"
        assert portfolio.deals[0].treaty_type == "Coinsurance"

    def test_duplicate_deal_id_rejected(self):
        portfolio = Portfolio().add_deal(**_deal_spec("D1", "CedantA"))
        with pytest.raises(PolarisValidationError, match="Duplicate deal_id"):
            portfolio.add_deal(**_deal_spec("D1", "CedantB"))

    def test_multi_product_block_rejected(self):
        spec = _deal_spec("D1", "CedantA")
        spec["inforce"] = InforceBlock(
            policies=[
                _policy("MIX_T", ProductType.TERM, 500_000.0),
                _policy("MIX_W", ProductType.WHOLE_LIFE, 500_000.0),
            ]
        )
        with pytest.raises(PolarisValidationError, match="exactly one product type"):
            Portfolio().add_deal(**spec)

    def test_non_proportional_treaty_rejected(self):
        spec = _deal_spec("D1", "CedantA")
        spec["treaty"] = StopLossTreaty(
            attachment_point=100_000.0,
            exhaustion_point=500_000.0,
            stop_loss_premium=10_000.0,
        )
        with pytest.raises(PolarisValidationError, match="proportional treaties only"):
            Portfolio().add_deal(**spec)


# ---------------------------------------------------------------------------
# run() — shape and validation
# ---------------------------------------------------------------------------


class TestPortfolioRun:
    def test_empty_portfolio_run_rejected(self):
        with pytest.raises(PolarisValidationError, match="empty portfolio"):
            Portfolio().run(HURDLE)

    def test_invalid_hurdle_rate_rejected(self):
        portfolio = Portfolio().add_deal(**_deal_spec("D1", "CedantA"))
        with pytest.raises(PolarisValidationError, match="hurdle_rate must be"):
            portfolio.run(-1.5)

    def test_run_returns_portfolio_result(self):
        portfolio = Portfolio().add_deal(**_deal_spec("D1", "CedantA"))
        result = portfolio.run(HURDLE)
        assert isinstance(result, PortfolioResult)
        assert result.n_deals == 1
        assert result.hurdle_rate == HURDLE

    def test_projection_months_is_max_horizon(self):
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", horizon_years=20))
            .add_deal(**_deal_spec("D2", "CedantB", horizon_years=10))
        )
        result = portfolio.run(HURDLE)
        assert result.projection_months == 240
        assert len(result.aggregate_net_cash_flow) == 240

    def test_deal_results_count_matches(self):
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .add_deal(**_deal_spec("D3", "CedantA"))
        )
        result = portfolio.run(HURDLE)
        assert len(result.deal_results) == 3
        assert all(isinstance(dr, DealResult) for dr in result.deal_results)


# ---------------------------------------------------------------------------
# Aggregation — closed-form additivity
# ---------------------------------------------------------------------------


class TestPortfolioAggregation:
    def test_two_deal_ncf_additivity(self):
        """Aggregate NCF equals the sum of independently computed deal NCFs."""
        spec_a = _deal_spec("D1", "CedantA")
        spec_b = _deal_spec("D2", "CedantB")
        expected = _independent_reinsurer_ncf(spec_a) + _independent_reinsurer_ncf(spec_b)

        result = Portfolio().add_deal(**spec_a).add_deal(**spec_b).run(HURDLE)
        np.testing.assert_allclose(result.aggregate_net_cash_flow, expected, rtol=1e-12)

    def test_additivity_with_mismatched_horizons(self):
        """A 10y deal contributes zero beyond month 120; the 20y deal alone
        drives the aggregate tail."""
        spec_a = _deal_spec("D1", "CedantA", horizon_years=20)
        spec_b = _deal_spec("D2", "CedantB", horizon_years=10)
        ncf_a = _independent_reinsurer_ncf(spec_a)
        ncf_b = _independent_reinsurer_ncf(spec_b)

        result = Portfolio().add_deal(**spec_a).add_deal(**spec_b).run(HURDLE)

        assert len(ncf_a) == 240
        assert len(ncf_b) == 120
        # Months 0-119: both deals contribute.
        np.testing.assert_allclose(
            result.aggregate_net_cash_flow[:120], ncf_a[:120] + ncf_b, rtol=1e-12
        )
        # Months 120-239: only the 20-year deal contributes.
        np.testing.assert_allclose(result.aggregate_net_cash_flow[120:], ncf_a[120:], rtol=1e-12)

    def test_total_pv_profits_equals_sum_of_deal_pv(self):
        """PV is linear: portfolio total == sum of per-deal PV profits."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB", horizon_years=15))
            .run(HURDLE)
        )
        per_deal_sum = sum(dr.profit_test.pv_profits for dr in result.deal_results)
        np.testing.assert_allclose(result.total_pv_profits, per_deal_sum, rtol=1e-9)

    def test_total_face_amount_sums_deal_faces(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", n_policies=2, face=500_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", n_policies=3, face=200_000.0))
            .run(HURDLE)
        )
        # 2 x 500k + 3 x 200k
        assert result.total_face_amount == pytest.approx(1_600_000.0)

    def test_total_ceded_face_uses_treaty_cession(self):
        result = (
            Portfolio()
            .add_deal(
                **_deal_spec(
                    "D1",
                    "CedantA",
                    treaty=CoinsuranceTreaty(cession_pct=0.4, treaty_name="t1"),
                )
            )
            .add_deal(
                **_deal_spec(
                    "D2",
                    "CedantB",
                    treaty=CoinsuranceTreaty(cession_pct=0.9, treaty_name="t2"),
                )
            )
            .run(HURDLE)
        )
        # Each block is 2 x 500k = 1.0M face.
        assert result.total_ceded_face == pytest.approx(0.4e6 + 0.9e6)

    def test_yrt_deal_populates_ceded_nar(self):
        yrt = YRTTreaty(
            treaty_name="yrt-1",
            cession_pct=0.8,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.5,
        )
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA", treaty=yrt)).run(HURDLE)
        assert result.peak_ceded_nar > 0.0
        assert np.any(result.aggregate_ceded_nar > 0.0)

    def test_coinsurance_only_portfolio_has_zero_ceded_nar(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        assert result.peak_ceded_nar == 0.0
        np.testing.assert_array_equal(
            result.aggregate_ceded_nar, np.zeros(result.projection_months)
        )

    @pytest.mark.parametrize(
        "treaty",
        [
            CoinsuranceTreaty(cession_pct=0.5, treaty_name="c"),
            ModcoTreaty(cession_pct=0.5, modco_interest_rate=0.045, treaty_name="m"),
            YRTTreaty(
                treaty_name="y",
                cession_pct=0.5,
                total_face_amount=1_000_000.0,
                flat_yrt_rate_per_1000=2.0,
            ),
        ],
    )
    def test_runs_for_each_proportional_treaty_type(self, treaty):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA", treaty=treaty)).run(HURDLE)
        assert result.n_deals == 1
        assert isinstance(result.total_pv_profits, float)


# ---------------------------------------------------------------------------
# Concentration metrics
# ---------------------------------------------------------------------------


class TestPortfolioConcentration:
    def test_concentration_by_cedant_shares(self):
        """Two equal-face deals from the same cedant -> 100% concentration."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "BigCo"))
            .add_deal(**_deal_spec("D2", "BigCo"))
            .run(HURDLE)
        )
        assert result.concentration_by_cedant == {"BigCo": pytest.approx(1.0)}
        assert result.hhi["cedant"] == pytest.approx(1.0)

    def test_concentration_two_cedants_equal_split(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        assert result.concentration_by_cedant["CedantA"] == pytest.approx(0.5)
        assert result.concentration_by_cedant["CedantB"] == pytest.approx(0.5)
        # HHI for two equal shares = 0.5^2 + 0.5^2 = 0.5.
        assert result.hhi["cedant"] == pytest.approx(0.5)

    def test_concentration_shares_sum_to_one(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=700_000.0))
            .add_deal(**_deal_spec("D3", "CedantC", face=100_000.0))
            .run(HURDLE)
        )
        for dimension in (
            result.concentration_by_cedant,
            result.concentration_by_product,
            result.concentration_by_treaty,
        ):
            assert sum(dimension.values()) == pytest.approx(1.0)

    def test_concentration_by_product(self):
        """A TERM deal and a WHOLE_LIFE deal of equal ceded face split 50/50."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", product=ProductType.TERM))
            .add_deal(**_deal_spec("D2", "CedantB", product=ProductType.WHOLE_LIFE))
            .run(HURDLE)
        )
        assert result.concentration_by_product["TERM"] == pytest.approx(0.5)
        assert result.concentration_by_product["WHOLE_LIFE"] == pytest.approx(0.5)

    def test_concentration_by_treaty(self):
        """Ceded face weights the treaty mix: 0.5M YRT vs 0.5M coinsurance."""
        yrt = YRTTreaty(
            treaty_name="y",
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.0,
        )
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", treaty=yrt))
            .add_deal(
                **_deal_spec(
                    "D2",
                    "CedantB",
                    treaty=CoinsuranceTreaty(cession_pct=0.5, treaty_name="c"),
                )
            )
            .run(HURDLE)
        )
        assert result.concentration_by_treaty["YRT"] == pytest.approx(0.5)
        assert result.concentration_by_treaty["Coinsurance"] == pytest.approx(0.5)

    def test_single_deal_hhi_is_one(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        assert result.hhi["cedant"] == pytest.approx(1.0)
        assert result.hhi["product"] == pytest.approx(1.0)
        assert result.hhi["treaty"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Per-deal breakdown
# ---------------------------------------------------------------------------


class TestPortfolioDealBreakdown:
    def test_deal_result_fields_populated(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        dr = result.deal_results[0]
        assert dr.deal_id == "D1"
        assert dr.cedant == "CedantA"
        assert dr.product_type == "TERM"
        assert dr.treaty_type == "Coinsurance"
        assert dr.n_policies == 2
        assert dr.face_amount == pytest.approx(1_000_000.0)
        assert dr.ceded_face == pytest.approx(500_000.0)
        assert isinstance(dr.profit_test, ProfitTestResult)
        assert len(dr.net_cash_flow) == 240

    def test_deal_profit_test_uses_portfolio_hurdle(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(0.08)
        assert result.deal_results[0].profit_test.hurdle_rate == 0.08

    def test_deal_net_cash_flow_matches_independent_projection(self):
        spec = _deal_spec("D1", "CedantA")
        expected = _independent_reinsurer_ncf(spec)
        result = Portfolio().add_deal(**spec).run(HURDLE)
        np.testing.assert_allclose(result.deal_results[0].net_cash_flow, expected, rtol=1e-12)

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

from polaris_re.analytics.capital import LICATCapital, LICATFactors
from polaris_re.analytics.capital_base import CapitalModel
from polaris_re.analytics.portfolio import (
    Deal,
    DealResult,
    Portfolio,
    PortfolioResult,
    PortfolioResultWithCapital,
    PortfolioScenarioResult,
)
from polaris_re.analytics.profit_test import ProfitTestResult
from polaris_re.analytics.rbc import RBCCapital
from polaris_re.analytics.scenario import ScenarioAdjustment, ScenarioRunner
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.pipeline import ceded_to_reinsurer_view
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


def _policy(
    policy_id: str,
    product: ProductType,
    face: float,
    start: date = date(2025, 1, 1),
) -> Policy:
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
        issue_date=start,
        valuation_date=start,
    )


def _block(
    prefix: str,
    product: ProductType = ProductType.TERM,
    n_policies: int = 2,
    face: float = 500_000.0,
    start: date = date(2025, 1, 1),
) -> InforceBlock:
    return InforceBlock(
        policies=[_policy(f"{prefix}_{i:03d}", product, face, start) for i in range(n_policies)],
    )


def _config(horizon_years: int = 20, start: date = date(2025, 1, 1)) -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=start,
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
    start: date = date(2025, 1, 1),
) -> dict[str, object]:
    """Return a kwargs dict ready to splat into `Portfolio.add_deal`.

    ``start`` shifts both the policies' ``issue_date`` and the config
    ``valuation_date`` together, so a deal's duration-driven projection is
    identical regardless of its calendar inception — only its position on a
    calendar-aligned portfolio grid changes.
    """
    block = _block(deal_id, product, n_policies, face, start)
    if treaty is None:
        treaty = CoinsuranceTreaty(cession_pct=0.5, treaty_name=f"{deal_id}-coins")
    return {
        "deal_id": deal_id,
        "cedant": cedant,
        "inforce": block,
        "assumptions": _assumptions(),
        "config": _config(horizon_years, start),
        "treaty": treaty,
    }


def _independent_reinsurer_ncf(spec: dict[str, object]) -> np.ndarray:
    """Project a deal spec end-to-end and return the reinsurer NCF vector.

    Mirrors `Portfolio._run_deal` using the product engine + treaty
    directly, so the portfolio aggregate can be cross-checked against an
    independently computed figure.
    """
    return _independent_reinsurer_view(spec).net_cash_flow


def _independent_reinsurer_view(spec: dict[str, object]) -> CashFlowResult:
    """Project a deal spec end-to-end and return the reinsurer CashFlowResult."""
    engine = get_product_engine(
        inforce=spec["inforce"],  # type: ignore[arg-type]
        assumptions=spec["assumptions"],  # type: ignore[arg-type]
        config=spec["config"],  # type: ignore[arg-type]
    )
    gross = engine.project()
    _net, ceded = spec["treaty"].apply(gross)  # type: ignore[attr-defined]
    return ceded_to_reinsurer_view(ceded)


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

    def test_mismatched_valuation_dates_rejected(self):
        """Deals with different valuation dates cannot be index-summed."""
        spec_a = _deal_spec("D1", "CedantA")
        spec_b = _deal_spec("D2", "CedantB")
        spec_b["config"] = ProjectionConfig(
            valuation_date=date(2025, 7, 1),
            projection_horizon_years=20,
            discount_rate=0.05,
        )
        portfolio = Portfolio().add_deal(**spec_a).add_deal(**spec_b)
        with pytest.raises(PolarisValidationError, match="same valuation date"):
            portfolio.run(HURDLE)

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
# Weighted concentration variants (ADR-069)
# ---------------------------------------------------------------------------


class TestPortfolioConcentrationByBasis:
    """``concentration_by_basis`` exposes share-of-total under multiple weight bases.

    The default ``ceded_face`` basis matches the flat ``concentration_by_*`` fields
    bit-for-bit. ``ceded_nar_peak`` and ``pv_premium`` re-weight by per-deal
    risk and revenue exposure so a coinsurance / YRT mix concentrates differently
    on each basis (ADR-069).
    """

    def test_supported_bases_present(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        assert set(result.concentration_by_basis.keys()) == {
            "ceded_face",
            "ceded_nar_peak",
            "pv_premium",
        }
        for basis in result.concentration_by_basis.values():
            assert set(basis.keys()) == {"cedant", "product", "treaty"}

    def test_ceded_face_basis_matches_flat_concentration(self):
        """``concentration_by_basis['ceded_face']`` reproduces the flat fields."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=700_000.0))
            .add_deal(**_deal_spec("D3", "CedantC", face=100_000.0))
            .run(HURDLE)
        )
        face_basis = result.concentration_by_basis["ceded_face"]
        assert face_basis["cedant"] == result.concentration_by_cedant
        assert face_basis["product"] == result.concentration_by_product
        assert face_basis["treaty"] == result.concentration_by_treaty

    def test_ceded_face_hhi_matches_flat_hhi(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=400_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=600_000.0))
            .run(HURDLE)
        )
        face_hhi = result.hhi_by_basis["ceded_face"]
        for dimension in ("cedant", "product", "treaty"):
            assert face_hhi[dimension] == pytest.approx(result.hhi[dimension])

    def test_all_bases_shares_sum_to_one(self):
        """Every (basis, dimension) share dict sums to 1.0."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=700_000.0))
            .run(HURDLE)
        )
        for basis, dims in result.concentration_by_basis.items():
            for dimension, shares in dims.items():
                assert sum(shares.values()) == pytest.approx(1.0), (
                    f"basis={basis} dimension={dimension} shares={shares}"
                )

    def test_nar_peak_basis_concentrates_on_yrt(self):
        """YRT exposes ceded NAR; coinsurance does not — NAR-peak weight
        should put 100% of the cedant share on the YRT deal."""
        yrt = YRTTreaty(
            treaty_name="y",
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.0,
        )
        result = (
            Portfolio()
            .add_deal(**_deal_spec("YRT_DEAL", "CedantA", treaty=yrt))
            .add_deal(
                **_deal_spec(
                    "COIN_DEAL",
                    "CedantB",
                    treaty=CoinsuranceTreaty(cession_pct=0.5, treaty_name="c"),
                )
            )
            .run(HURDLE)
        )
        nar_basis = result.concentration_by_basis["ceded_nar_peak"]
        # All NAR comes from the YRT deal (CedantA), so CedantA share = 1.0.
        assert nar_basis["cedant"]["CedantA"] == pytest.approx(1.0)
        assert nar_basis["cedant"].get("CedantB", 0.0) == pytest.approx(0.0)
        # Treaty dimension: 100% YRT under NAR-peak weighting.
        assert nar_basis["treaty"]["YRT"] == pytest.approx(1.0)
        # On ceded-face basis the same portfolio splits 50/50 — the bases differ.
        assert result.concentration_by_basis["ceded_face"]["treaty"]["YRT"] == pytest.approx(0.5)

    def test_pv_premium_basis_weights_by_revenue(self):
        """Closed-form: a deal with 3x the premium dominates the PV-premium share.

        With identical assumptions, mortality, and cession_pct, doubling the
        face amount on a TERM deal exactly doubles its reinsurer-side
        pv_premiums — so a 300K/900K split concentrates 25%/75% by PV-premium.
        """
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=900_000.0))
            .run(HURDLE)
        )
        pv_basis = result.concentration_by_basis["pv_premium"]
        assert pv_basis["cedant"]["CedantA"] == pytest.approx(0.25)
        assert pv_basis["cedant"]["CedantB"] == pytest.approx(0.75)

    def test_pv_premium_basis_matches_per_deal_pv_premiums(self):
        """Direct closed-form: PV-premium share equals each deal's
        ``profit_test.pv_premiums`` divided by the portfolio total."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=400_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=600_000.0))
            .run(HURDLE)
        )
        per_deal_pv_premiums = {dr.cedant: dr.profit_test.pv_premiums for dr in result.deal_results}
        total = sum(per_deal_pv_premiums.values())
        expected = {cedant: pv / total for cedant, pv in per_deal_pv_premiums.items()}
        pv_basis = result.concentration_by_basis["pv_premium"]
        for cedant, share in expected.items():
            assert pv_basis["cedant"][cedant] == pytest.approx(share)

    def test_hhi_by_basis_matches_squared_shares(self):
        """HHI per basis is the sum of squared shares for each dimension."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=700_000.0))
            .run(HURDLE)
        )
        for basis, dims in result.concentration_by_basis.items():
            for dimension, shares in dims.items():
                expected_hhi = sum(s * s for s in shares.values())
                assert result.hhi_by_basis[basis][dimension] == pytest.approx(expected_hhi)

    def test_single_deal_all_bases_concentrate_fully(self):
        """A single deal owns 100% of every (basis, dimension)."""
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        for basis, dims in result.concentration_by_basis.items():
            for dimension in ("cedant", "product", "treaty"):
                assert sum(dims[dimension].values()) == pytest.approx(1.0)
                assert result.hhi_by_basis[basis][dimension] == pytest.approx(1.0)

    def test_concentration_by_basis_in_to_dict(self):
        """``to_dict`` carries the nested ``concentration_by_basis`` + ``hhi_by_basis``."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        d = result.to_dict()
        assert "concentration_by_basis" in d
        assert "hhi_by_basis" in d
        cbb = d["concentration_by_basis"]
        assert set(cbb.keys()) == {"ceded_face", "ceded_nar_peak", "pv_premium"}
        # The flat ``concentration`` key is unchanged for backward compatibility.
        assert d["concentration"]["cedant"] == result.concentration_by_cedant
        # The new nested key matches the flat one on the ceded_face basis.
        assert cbb["ceded_face"]["cedant"] == result.concentration_by_cedant

    def test_to_dict_is_json_serialisable(self):
        """The whole flattened result, including the new keys, round-trips through JSON."""
        import json

        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        json.dumps(result.to_dict())


class TestPortfolioConcentrationByDimension:
    """``concentration_by_dimension`` and ``hhi_by_dimension`` transpose
    the basis-outer fields into a dimension-outer view (ADR-073).

    The transposed shape ``{dimension: {basis: ...}}`` mirrors the
    ``concentration[dimension][weight_basis]`` access pattern originally
    proposed in PRODUCT_DIRECTION_2026-05-23 and reads naturally for a
    consumer (e.g. a dashboard control) that flips weight basis for a
    fixed dimension. The helpers do not duplicate storage — every value
    comes directly from the underlying ``concentration_by_basis`` /
    ``hhi_by_basis`` fields.
    """

    def test_concentration_by_dimension_top_level_keys_are_dimensions(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        transposed = result.concentration_by_dimension()
        assert set(transposed.keys()) == {"cedant", "product", "treaty"}

    def test_concentration_by_dimension_inner_keys_are_bases(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        transposed = result.concentration_by_dimension()
        for dimension, by_basis in transposed.items():
            assert set(by_basis.keys()) == {
                "ceded_face",
                "ceded_nar_peak",
                "pv_premium",
            }, f"dimension={dimension}"

    def test_concentration_by_dimension_preserves_values(self):
        """Every (basis, dimension, label) value matches the basis-outer view bit-for-bit."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=700_000.0))
            .run(HURDLE)
        )
        transposed = result.concentration_by_dimension()
        for basis, dims in result.concentration_by_basis.items():
            for dimension, shares in dims.items():
                assert transposed[dimension][basis] == shares

    def test_concentration_by_dimension_round_trips_via_basis_outer(self):
        """Re-transposing the dimension-outer view returns the basis-outer original."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=700_000.0))
            .run(HURDLE)
        )
        transposed = result.concentration_by_dimension()
        round_trip: dict[str, dict[str, dict[str, float]]] = {}
        for dimension, by_basis in transposed.items():
            for basis, shares in by_basis.items():
                round_trip.setdefault(basis, {})[dimension] = shares
        assert round_trip == result.concentration_by_basis

    def test_hhi_by_dimension_top_level_keys_are_dimensions(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        transposed = result.hhi_by_dimension()
        assert set(transposed.keys()) == {"cedant", "product", "treaty"}

    def test_hhi_by_dimension_inner_keys_are_bases(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        transposed = result.hhi_by_dimension()
        for dimension, by_basis in transposed.items():
            assert set(by_basis.keys()) == {
                "ceded_face",
                "ceded_nar_peak",
                "pv_premium",
            }, f"dimension={dimension}"

    def test_hhi_by_dimension_preserves_values(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", face=300_000.0))
            .add_deal(**_deal_spec("D2", "CedantB", face=700_000.0))
            .run(HURDLE)
        )
        transposed = result.hhi_by_dimension()
        for basis, dims in result.hhi_by_basis.items():
            for dimension, hhi in dims.items():
                assert transposed[dimension][basis] == pytest.approx(hhi)

    def test_dimension_outer_does_not_duplicate_storage(self):
        """The transposed view returns the same nested share dict instances as the
        underlying ``concentration_by_basis`` field — no copying."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        transposed = result.concentration_by_dimension()
        for basis, dims in result.concentration_by_basis.items():
            for dimension, shares in dims.items():
                assert transposed[dimension][basis] is shares


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


# ---------------------------------------------------------------------------
# to_dict() — JSON-friendly serialisation
# ---------------------------------------------------------------------------


class TestPortfolioResultToDict:
    """``PortfolioResult.to_dict`` flattens the result for JSON / Rich rendering."""

    def test_returns_plain_dict(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        d = result.to_dict()
        assert isinstance(d, dict)

    def test_top_level_keys(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        d = result.to_dict()
        expected_keys = {
            "n_deals",
            "hurdle_rate",
            "projection_months",
            "total_pv_profits",
            "total_irr",
            "breakeven_year",
            "profit_margin",
            "total_undiscounted_profit",
            "total_face_amount",
            "total_ceded_face",
            "peak_ceded_nar",
            "aggregate_net_cash_flow",
            "aggregate_ceded_nar",
            "deals",
            "concentration",
            "hhi",
        }
        assert expected_keys.issubset(d.keys())

    def test_deals_block_is_list_of_dicts(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        deals = result.to_dict()["deals"]
        assert isinstance(deals, list)
        assert len(deals) == 2
        first = deals[0]
        assert first["deal_id"] == "D1"
        assert first["cedant"] == "CedantA"
        assert first["product_type"] == "TERM"
        assert first["treaty_type"] == "Coinsurance"
        assert first["n_policies"] == 2
        # Profit-test nested
        assert "pv_profits" in first["profit_test"]
        assert "irr" in first["profit_test"]

    def test_arrays_serialised_as_lists(self):
        """NumPy arrays must be plain lists so ``json.dumps`` works."""
        import json

        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        d = result.to_dict()
        assert isinstance(d["aggregate_net_cash_flow"], list)
        assert isinstance(d["aggregate_ceded_nar"], list)
        assert len(d["aggregate_net_cash_flow"]) == d["projection_months"]
        # JSON serialisable end-to-end
        json.dumps(d)

    def test_concentration_and_hhi_grouped(self):
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        d = result.to_dict()
        # Concentration is grouped by dimension for ergonomic access
        assert set(d["concentration"].keys()) == {"cedant", "product", "treaty"}
        assert set(d["hhi"].keys()) == {"cedant", "product", "treaty"}
        assert sum(d["concentration"]["cedant"].values()) == pytest.approx(1.0)

    def test_profit_test_fields_match_source(self):
        """The flattened deal block carries the same numbers as the ProfitTestResult."""
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        d = result.to_dict()
        dr = result.deal_results[0]
        first = d["deals"][0]
        assert first["profit_test"]["pv_profits"] == dr.profit_test.pv_profits
        assert first["profit_test"]["irr"] == dr.profit_test.irr


# ---------------------------------------------------------------------------
# Aggregate CashFlowResult — full reinsurer-side cash flow lines
# ---------------------------------------------------------------------------


class TestPortfolioAggregateCashFlow:
    """``PortfolioResult.aggregate_cash_flow`` carries the full reinsurer view.

    Slice 1 only summed gross_premiums + net_cash_flow (all that ProfitTester
    needs). Loss-ratio reporting and portfolio-level RoC need claims,
    expenses, and reserves too — see PRODUCT_DIRECTION_2026-05-23
    "Aggregate CashFlowResult claims / expenses / reserves on Portfolio.run".
    """

    def test_aggregate_cash_flow_is_cashflow_result(self):
        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        assert isinstance(result.aggregate_cash_flow, CashFlowResult)
        assert result.aggregate_cash_flow.basis == "NET"
        assert result.aggregate_cash_flow.product_type == "PORTFOLIO"

    def test_aggregate_cash_flow_arrays_sum_per_deal_reinsurer_views(self):
        """Every aggregated array equals the month-by-month sum across deals."""
        spec_a = _deal_spec("D1", "CedantA")
        spec_b = _deal_spec("D2", "CedantB")
        view_a = _independent_reinsurer_view(spec_a)
        view_b = _independent_reinsurer_view(spec_b)

        result = Portfolio().add_deal(**spec_a).add_deal(**spec_b).run(HURDLE)
        cf = result.aggregate_cash_flow

        for field_name in (
            "gross_premiums",
            "death_claims",
            "lapse_surrenders",
            "expenses",
            "reserve_balance",
            "reserve_increase",
            "net_cash_flow",
        ):
            expected = getattr(view_a, field_name) + getattr(view_b, field_name)
            np.testing.assert_allclose(
                getattr(cf, field_name),
                expected,
                rtol=1e-12,
                err_msg=f"aggregate {field_name} mismatch",
            )

    def test_aggregate_cash_flow_pads_shorter_horizon_with_zeros(self):
        """A 10y deal contributes zero claims/expenses beyond month 120."""
        spec_a = _deal_spec("D1", "CedantA", horizon_years=20)
        spec_b = _deal_spec("D2", "CedantB", horizon_years=10)
        view_a = _independent_reinsurer_view(spec_a)
        view_b = _independent_reinsurer_view(spec_b)

        result = Portfolio().add_deal(**spec_a).add_deal(**spec_b).run(HURDLE)
        cf = result.aggregate_cash_flow

        assert cf.projection_months == 240
        # Months 0-119: both contribute.
        np.testing.assert_allclose(
            cf.death_claims[:120],
            view_a.death_claims[:120] + view_b.death_claims,
            rtol=1e-12,
        )
        # Months 120-239: only the 20y deal contributes.
        np.testing.assert_allclose(cf.death_claims[120:], view_a.death_claims[120:], rtol=1e-12)

    def test_aggregate_loss_ratio_matches_independent_calculation(self):
        """``loss_ratio()`` on the aggregate equals total claims / total premiums."""
        spec_a = _deal_spec("D1", "CedantA")
        spec_b = _deal_spec("D2", "CedantB")
        view_a = _independent_reinsurer_view(spec_a)
        view_b = _independent_reinsurer_view(spec_b)
        expected = float(
            (view_a.death_claims.sum() + view_b.death_claims.sum())
            / (view_a.gross_premiums.sum() + view_b.gross_premiums.sum())
        )

        result = Portfolio().add_deal(**spec_a).add_deal(**spec_b).run(HURDLE)
        assert result.aggregate_cash_flow.loss_ratio() == pytest.approx(expected, rel=1e-12)

    def test_aggregate_cash_flow_arrays_have_consistent_length(self):
        """All aggregated arrays carry ``projection_months`` entries."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", horizon_years=20))
            .add_deal(**_deal_spec("D2", "CedantB", horizon_years=10))
            .run(HURDLE)
        )
        cf = result.aggregate_cash_flow
        for field_name in (
            "gross_premiums",
            "death_claims",
            "lapse_surrenders",
            "expenses",
            "reserve_balance",
            "reserve_increase",
            "net_cash_flow",
        ):
            assert len(getattr(cf, field_name)) == cf.projection_months

    def test_aggregate_net_cash_flow_property_unchanged(self):
        """The pre-existing top-level ``aggregate_net_cash_flow`` still equals
        the aggregate CashFlowResult's net_cash_flow — backward compatibility."""
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB"))
            .run(HURDLE)
        )
        np.testing.assert_array_equal(
            result.aggregate_net_cash_flow, result.aggregate_cash_flow.net_cash_flow
        )

    def test_to_dict_exposes_aggregate_cash_flow_arrays(self):
        """``to_dict`` carries the new aggregate arrays under ``aggregate_cash_flow``."""
        import json

        result = Portfolio().add_deal(**_deal_spec("D1", "CedantA")).run(HURDLE)
        d = result.to_dict()
        assert "aggregate_cash_flow" in d
        block = d["aggregate_cash_flow"]
        for field_name in (
            "gross_premiums",
            "death_claims",
            "lapse_surrenders",
            "expenses",
            "reserve_balance",
            "reserve_increase",
            "net_cash_flow",
        ):
            assert field_name in block, f"missing {field_name} in aggregate_cash_flow dict"
            assert isinstance(block[field_name], list)
            assert len(block[field_name]) == d["projection_months"]
        # Still JSON-serialisable end-to-end.
        json.dumps(d)


# ---------------------------------------------------------------------------
# Portfolio.run_with_capital — aggregate LICAT capital + return-on-capital
# ---------------------------------------------------------------------------


def _yrt(*, cession_pct: float = 0.5, total_face: float = 1_000_000.0) -> YRTTreaty:
    """Build a YRTTreaty matching the default ``_deal_spec`` face (2x500k = 1M).

    Tests for ``run_with_capital`` need YRT cessions so ``aggregate_ceded_nar``
    is non-zero — otherwise the default C-2 factor cannot produce positive
    capital.
    """
    return YRTTreaty(
        treaty_name="yrt-test",
        cession_pct=cession_pct,
        total_face_amount=total_face,
        flat_yrt_rate_per_1000=2.5,
    )


class TestPortfolioRunWithCapital:
    """``Portfolio.run_with_capital`` rolls a single LICATCapital call onto
    the aggregate reinsurer cash flow and aggregate ceded NAR, returning a
    ``PortfolioResultWithCapital`` that carries every ``PortfolioResult``
    field plus capital metrics (peak/initial/PV capital, return-on-capital,
    capital-adjusted IRR).

    Source: PRODUCT_DIRECTION_2026-05-23 — IMPORTANT, "Aggregate
    return-on-capital on Portfolio" (depends on ADR-059).
    """

    def test_returns_portfolio_result_with_capital(self):
        portfolio = Portfolio().add_deal(
            **_deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5))
        )
        capital = LICATCapital.for_product(ProductType.TERM)
        result = portfolio.run_with_capital(HURDLE, capital)

        assert isinstance(result, PortfolioResultWithCapital)
        # Must remain a PortfolioResult — every consumer of the base contract
        # keeps working.
        assert isinstance(result, PortfolioResult)
        assert result.peak_capital > 0.0
        assert result.pv_capital > 0.0
        assert result.return_on_capital is not None

    def test_base_portfolio_fields_preserved(self):
        """run_with_capital preserves every PortfolioResult field unchanged
        relative to a bare run() with the same hurdle rate."""
        spec_a = _deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5))
        spec_b = _deal_spec("D2", "CedantB", treaty=_yrt(cession_pct=0.5))
        portfolio = Portfolio().add_deal(**spec_a).add_deal(**spec_b)
        capital = LICATCapital.for_product(ProductType.TERM)

        base = portfolio.run(HURDLE)
        joint = portfolio.run_with_capital(HURDLE, capital)

        assert joint.n_deals == base.n_deals
        assert joint.hurdle_rate == base.hurdle_rate
        assert joint.projection_months == base.projection_months
        assert joint.total_pv_profits == pytest.approx(base.total_pv_profits)
        assert joint.total_irr == base.total_irr
        assert joint.breakeven_year == base.breakeven_year
        assert joint.profit_margin == base.profit_margin
        assert joint.total_undiscounted_profit == pytest.approx(base.total_undiscounted_profit)
        assert joint.total_face_amount == base.total_face_amount
        assert joint.total_ceded_face == base.total_ceded_face
        assert joint.peak_ceded_nar == base.peak_ceded_nar
        np.testing.assert_array_equal(joint.aggregate_net_cash_flow, base.aggregate_net_cash_flow)
        np.testing.assert_array_equal(joint.aggregate_ceded_nar, base.aggregate_ceded_nar)

    def test_capital_equals_single_call_on_aggregate(self):
        """CLOSED-FORM: aggregate capital schedule equals a single LICATCapital
        call on (aggregate_cash_flow, aggregate_ceded_nar)."""
        spec_a = _deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5))
        spec_b = _deal_spec("D2", "CedantB", treaty=_yrt(cession_pct=0.5))
        portfolio = Portfolio().add_deal(**spec_a).add_deal(**spec_b)
        capital = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))

        base = portfolio.run(HURDLE)
        joint = portfolio.run_with_capital(HURDLE, capital)

        expected_schedule = capital.required_capital(
            base.aggregate_cash_flow, nar=base.aggregate_ceded_nar
        )
        np.testing.assert_allclose(
            joint.capital_by_period, expected_schedule.capital_by_period, rtol=1e-12
        )
        assert joint.initial_capital == pytest.approx(expected_schedule.initial_capital)
        assert joint.peak_capital == pytest.approx(expected_schedule.peak_capital)

    def test_capital_linearity_matches_sum_of_per_deal_capital(self):
        """CLOSED-FORM: with the same LICATFactors applied to every deal, the
        single-call portfolio capital equals the month-by-month sum of the
        per-deal capital schedules. This is the actuarial invariant the
        "single LICATCapital call at the portfolio level" design relies on."""
        spec_a = _deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5))
        spec_b = _deal_spec("D2", "CedantB", treaty=_yrt(cession_pct=0.5))
        portfolio = Portfolio().add_deal(**spec_a).add_deal(**spec_b)
        capital = LICATCapital(
            factors=LICATFactors(
                c1_asset_default=0.005,
                c2_mortality_factor=0.10,
                c3_interest_rate=0.01,
            )
        )

        joint = portfolio.run_with_capital(HURDLE, capital)

        # Independently compute per-deal capital schedules. The reinsurer
        # view (basis NET) carries the reserve_balance / net_cash_flow the
        # calculator consumes; ``ceded_to_reinsurer_view`` does not forward
        # ``nar``, so we extract it from the ``ceded`` cash flow directly.
        per_deal_capitals = []
        for spec in (spec_a, spec_b):
            engine = get_product_engine(
                inforce=spec["inforce"],
                assumptions=spec["assumptions"],
                config=spec["config"],
            )
            _net, ceded = spec["treaty"].apply(engine.project())
            view = ceded_to_reinsurer_view(ceded)
            nar = (
                np.asarray(ceded.nar, dtype=np.float64)
                if ceded.nar is not None
                else np.zeros(ceded.projection_months, dtype=np.float64)
            )
            per_deal_capitals.append(capital.required_capital(view, nar=nar))

        expected = per_deal_capitals[0].capital_by_period + per_deal_capitals[1].capital_by_period
        np.testing.assert_allclose(joint.capital_by_period, expected, rtol=1e-12)

    def test_roc_closed_form_pv_profits_over_pv_capital(self):
        """CLOSED-FORM: return_on_capital == total_pv_profits / pv_capital."""
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5)))
            .add_deal(**_deal_spec("D2", "CedantB", treaty=_yrt(cession_pct=0.5)))
        )
        capital = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))

        result = portfolio.run_with_capital(HURDLE, capital)

        assert result.pv_capital > 0.0
        expected_roc = result.total_pv_profits / result.pv_capital
        assert result.return_on_capital == pytest.approx(expected_roc)

    def test_zero_capital_factor_yields_none_roc(self):
        """A zero-factor capital model produces pv_capital == 0 -> RoC None."""
        portfolio = Portfolio().add_deal(
            **_deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5))
        )
        capital = LICATCapital(
            factors=LICATFactors(
                c1_asset_default=0.0, c2_mortality_factor=0.0, c3_interest_rate=0.0
            )
        )

        result = portfolio.run_with_capital(HURDLE, capital)

        assert result.pv_capital == 0.0
        assert result.return_on_capital is None

    def test_doubling_c2_factor_halves_roc(self):
        """Sensitivity: with a YRT-only portfolio (capital comes from C-2 on
        NAR), doubling the C-2 factor doubles pv_capital and halves RoC."""
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5)))
            .add_deal(**_deal_spec("D2", "CedantB", treaty=_yrt(cession_pct=0.5)))
        )
        cap_low = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.05))
        cap_high = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))

        r_low = portfolio.run_with_capital(HURDLE, cap_low)
        r_high = portfolio.run_with_capital(HURDLE, cap_high)

        assert r_low.return_on_capital is not None
        assert r_high.return_on_capital is not None
        assert r_high.pv_capital == pytest.approx(2.0 * r_low.pv_capital)
        assert r_high.return_on_capital == pytest.approx(r_low.return_on_capital / 2.0)

    def test_empty_portfolio_run_with_capital_rejected(self):
        """An empty portfolio still rejects, just like ``run``."""
        capital = LICATCapital.for_product(ProductType.TERM)
        with pytest.raises(PolarisValidationError, match="empty portfolio"):
            Portfolio().run_with_capital(HURDLE, capital)

    def test_capital_by_period_shape_matches_projection_months(self):
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5), horizon_years=20))
            .add_deal(**_deal_spec("D2", "CedantB", treaty=_yrt(cession_pct=0.5), horizon_years=10))
        )
        capital = LICATCapital.for_product(ProductType.TERM)

        result = portfolio.run_with_capital(HURDLE, capital)

        assert result.capital_by_period.shape == (result.projection_months,)
        # Beyond the shorter deal's horizon (months 120-239), only D1
        # contributes NAR -> capital strictly decreases at the seam, not
        # increases.
        assert result.capital_by_period[120] <= result.capital_by_period[119]

    def test_to_dict_exposes_capital_block(self):
        """``to_dict`` carries the new capital block alongside the base keys."""
        import json

        portfolio = Portfolio().add_deal(
            **_deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5))
        )
        capital = LICATCapital.for_product(ProductType.TERM)
        result = portfolio.run_with_capital(HURDLE, capital)

        d = result.to_dict()
        # Base keys still present
        assert "aggregate_cash_flow" in d
        assert "concentration" in d
        # New capital block
        assert "capital" in d
        cap_block = d["capital"]
        for key in (
            "initial_capital",
            "peak_capital",
            "pv_capital",
            "pv_capital_strain",
            "return_on_capital",
            "capital_adjusted_irr",
            "capital_by_period",
        ):
            assert key in cap_block, f"missing {key!r} in capital block"
        assert isinstance(cap_block["capital_by_period"], list)
        assert len(cap_block["capital_by_period"]) == d["projection_months"]
        # Round-trip JSON serialisable.
        json.dumps(d)

    def test_accepts_rbc_capital_model(self):
        """Epic 3 Slice 2 (ADR-099): the aggregate RoC entry point accepts any
        ``CapitalModel`` — driving it with US ``RBCCapital`` returns the same
        contract (peak/PV capital, RoC, capital-adjusted IRR) as LICAT."""
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", treaty=_yrt(cession_pct=0.5)))
            .add_deal(**_deal_spec("D2", "CedantB", treaty=_yrt(cession_pct=0.5)))
        )
        capital = RBCCapital.for_product(ProductType.TERM)
        assert isinstance(capital, CapitalModel)

        result = portfolio.run_with_capital(HURDLE, capital)

        assert isinstance(result, PortfolioResultWithCapital)
        assert result.peak_capital > 0.0
        assert result.pv_capital > 0.0
        assert result.return_on_capital is not None
        # RoC uses the same denominator formula; only the capital number differs.
        expected_schedule = capital.required_capital(
            result.aggregate_cash_flow, nar=result.aggregate_ceded_nar
        )
        np.testing.assert_allclose(
            result.capital_by_period, expected_schedule.capital_by_period, rtol=1e-12
        )
        assert result.return_on_capital == pytest.approx(
            result.total_pv_profits / result.pv_capital
        )


# ---------------------------------------------------------------------------
# Calendar-aligned aggregation (ADR-061)
# ---------------------------------------------------------------------------


class TestPortfolioCalendarAlignment:
    """``Portfolio.run(align="calendar")`` aggregates deals with different
    inception dates onto a common monthly calendar grid keyed off the
    earliest valuation date.

    Closed-form checks pin the two behaviours that distinguish calendar
    alignment from the default ``align="strict"`` month-index sum:
      1. A deal inception-dated ``o`` months after the grid origin has its
         cash flows placed at grid offset ``o`` (zeros before it starts).
      2. Because PV discounts from the common origin, a deal at offset ``o``
         contributes ``v**o`` times its standalone PV — so the aggregate PV
         is NOT the naive sum of per-deal PVs once inception dates differ.
    """

    def test_calendar_mode_accepts_mixed_valuation_dates(self):
        """Unlike strict mode, calendar mode does not reject mixed dates."""
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", start=date(2025, 1, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", start=date(2025, 7, 1)))
        )
        result = portfolio.run(HURDLE, align="calendar")
        assert isinstance(result, PortfolioResult)
        assert result.n_deals == 2

    def test_grid_origin_is_earliest_valuation_date(self):
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", start=date(2025, 7, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", start=date(2025, 1, 1)))
        )
        result = portfolio.run(HURDLE, align="calendar")
        assert result.aggregate_cash_flow.valuation_date == date(2025, 1, 1)

    def test_offset_deal_cash_flows_placed_on_common_grid(self):
        """CLOSED-FORM: aggregate NCF[k] = ncf_a[k] + ncf_b[k - 6], with the
        6-month-later deal contributing zero before it starts."""
        spec_a = _deal_spec("D1", "CedantA", start=date(2025, 1, 1))
        spec_b = _deal_spec("D2", "CedantB", start=date(2025, 7, 1))
        ncf_a = _independent_reinsurer_ncf(spec_a)
        ncf_b = _independent_reinsurer_ncf(spec_b)

        result = Portfolio().add_deal(**spec_a).add_deal(**spec_b).run(HURDLE, align="calendar")

        offset = 6
        t_a, t_b = len(ncf_a), len(ncf_b)
        assert result.projection_months == max(t_a, offset + t_b)
        expected = np.zeros(result.projection_months, dtype=np.float64)
        expected[:t_a] += ncf_a
        expected[offset : offset + t_b] += ncf_b
        np.testing.assert_allclose(result.aggregate_net_cash_flow, expected, rtol=1e-12)
        # The later deal contributes nothing in the months before it starts.
        np.testing.assert_allclose(
            result.aggregate_net_cash_flow[:offset], ncf_a[:offset], rtol=1e-12
        )

    def test_aggregate_pv_discounts_offset_deal_by_v_to_the_offset(self):
        """CLOSED-FORM: with identical specs, the deal offset by 6 months
        contributes v**6 times its standalone PV, so the aggregate PV is
        P + v**6 * P, NOT the naive sum 2 * P."""
        offset = 6
        spec_a = _deal_spec("D1", "CedantA", start=date(2025, 1, 1))
        spec_b = _deal_spec("D2", "CedantB", start=date(2025, 7, 1))
        result = Portfolio().add_deal(**spec_a).add_deal(**spec_b).run(HURDLE, align="calendar")

        pv_a = result.deal_results[0].profit_test.pv_profits
        pv_b = result.deal_results[1].profit_test.pv_profits
        # Identical specs ⇒ identical standalone PVs.
        np.testing.assert_allclose(pv_a, pv_b, rtol=1e-12)

        v = (1.0 + HURDLE) ** (-1.0 / 12.0)
        expected_total = pv_a + (v**offset) * pv_b
        np.testing.assert_allclose(result.total_pv_profits, expected_total, rtol=1e-9)
        # And the calendar PV is strictly below the naive sum (offset discounting).
        assert result.total_pv_profits < pv_a + pv_b

    def test_calendar_matches_strict_when_dates_equal(self):
        """When every deal shares a valuation date, calendar mode reduces to
        the strict month-index aggregate exactly."""
        strict = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB", horizon_years=15))
            .run(HURDLE)
        )
        calendar = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA"))
            .add_deal(**_deal_spec("D2", "CedantB", horizon_years=15))
            .run(HURDLE, align="calendar")
        )
        assert calendar.projection_months == strict.projection_months
        np.testing.assert_allclose(
            calendar.aggregate_net_cash_flow, strict.aggregate_net_cash_flow, rtol=1e-12
        )
        np.testing.assert_allclose(calendar.total_pv_profits, strict.total_pv_profits, rtol=1e-12)
        assert calendar.aggregate_cash_flow.valuation_date == date(2025, 1, 1)

    def test_aggregate_ceded_nar_aligned_for_yrt(self):
        """A YRT deal inception-dated later contributes NAR at the grid offset
        and zero before it starts."""
        yrt = _yrt(cession_pct=0.8)
        spec = _deal_spec("D2", "CedantB", treaty=yrt, start=date(2025, 7, 1))
        result = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", start=date(2025, 1, 1)))
            .add_deal(**spec)
            .run(HURDLE, align="calendar")
        )
        # Coinsurance deal A carries no NAR; all NAR comes from the offset YRT.
        np.testing.assert_array_equal(result.aggregate_ceded_nar[:6], np.zeros(6, dtype=np.float64))
        assert np.any(result.aggregate_ceded_nar[6:] > 0.0)

    def test_strict_mode_default_still_rejects_mixed_dates(self):
        """The default mode is unchanged — mixed dates are rejected."""
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", start=date(2025, 1, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", start=date(2025, 7, 1)))
        )
        with pytest.raises(PolarisValidationError, match="same valuation date"):
            portfolio.run(HURDLE)

    def test_calendar_requires_common_day_of_month(self):
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", start=date(2025, 1, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", start=date(2025, 7, 15)))
        )
        with pytest.raises(PolarisValidationError, match="day-of-month"):
            portfolio.run(HURDLE, align="calendar")

    def test_invalid_align_mode_rejected(self):
        portfolio = Portfolio().add_deal(**_deal_spec("D1", "CedantA"))
        with pytest.raises(PolarisValidationError, match="align must be"):
            portfolio.run(HURDLE, align="bogus")  # type: ignore[arg-type]

    def test_run_with_capital_threads_calendar_alignment(self):
        """``run_with_capital(align="calendar")`` aggregates on the calendar
        grid and rolls the capital schedule over the full aligned horizon."""
        capital = LICATCapital(factors=LICATFactors(c2_mortality_factor=0.10))
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", treaty=_yrt(), start=date(2025, 1, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", treaty=_yrt(), start=date(2025, 7, 1)))
        )
        base = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", treaty=_yrt(), start=date(2025, 1, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", treaty=_yrt(), start=date(2025, 7, 1)))
            .run(HURDLE, align="calendar")
        )
        result = portfolio.run_with_capital(HURDLE, capital, align="calendar")
        assert isinstance(result, PortfolioResultWithCapital)
        assert result.projection_months == base.projection_months
        np.testing.assert_allclose(
            result.aggregate_net_cash_flow, base.aggregate_net_cash_flow, rtol=1e-12
        )
        assert len(result.capital_by_period) == base.projection_months


# ---------------------------------------------------------------------------
# run_scenarios() — portfolio-level stress aggregation (ADR-064)
# ---------------------------------------------------------------------------


def _two_deal_portfolio() -> Portfolio:
    """A two-deal portfolio that's heavy enough to exhibit scenario sensitivity."""
    return (
        Portfolio(name="scenario-test")
        .add_deal(**_deal_spec("D1", "CedantA", n_policies=3, face=500_000.0))
        .add_deal(**_deal_spec("D2", "CedantB", n_policies=2, face=750_000.0))
    )


def _stub_portfolio_result(
    *, total_irr: float | None, total_pv_profits: float = 0.0
) -> PortfolioResult:
    """Build a minimal :class:`PortfolioResult` for helper unit-tests.

    Only the fields exercised by :class:`PortfolioScenarioResult` helpers
    (``total_irr``, ``total_pv_profits``) carry meaningful values; the
    remaining fields are zero / empty placeholders.
    """
    empty_cf = CashFlowResult(
        run_id="stub",
        valuation_date=date(2025, 1, 1),
        basis="NET",
        assumption_set_version="stub",
        product_type="PORTFOLIO",
        block_id="stub",
        projection_months=0,
        time_index=np.zeros(0, dtype=np.int32),
        gross_premiums=np.zeros(0, dtype=np.float64),
        death_claims=np.zeros(0, dtype=np.float64),
        lapse_surrenders=np.zeros(0, dtype=np.float64),
        expenses=np.zeros(0, dtype=np.float64),
        reserve_balance=np.zeros(0, dtype=np.float64),
        reserve_increase=np.zeros(0, dtype=np.float64),
        net_cash_flow=np.zeros(0, dtype=np.float64),
    )
    return PortfolioResult(
        n_deals=0,
        hurdle_rate=HURDLE,
        projection_months=0,
        aggregate_cash_flow=empty_cf,
        aggregate_net_cash_flow=np.zeros(0, dtype=np.float64),
        aggregate_ceded_nar=np.zeros(0, dtype=np.float64),
        total_pv_profits=total_pv_profits,
        total_irr=total_irr,
        breakeven_year=None,
        profit_margin=None,
        total_undiscounted_profit=0.0,
        total_face_amount=0.0,
        total_ceded_face=0.0,
        peak_ceded_nar=0.0,
        deal_results=[],
        concentration_by_cedant={},
        concentration_by_product={},
        concentration_by_treaty={},
        hhi={},
    )


class TestPortfolioRunScenarios:
    """Closed-form and sensitivity tests for the multi-scenario portfolio runner."""

    def test_returns_portfolio_scenario_result(self):
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(HURDLE, scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])
        assert isinstance(result, PortfolioScenarioResult)
        assert len(result.scenarios) == 1
        name, payload = result.scenarios[0]
        assert name == "BASE"
        assert isinstance(payload, PortfolioResult)

    def test_default_scenarios_match_standard_set(self):
        """Default scenarios match ``ScenarioRunner.standard_stress_scenarios()``."""
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(HURDLE)
        expected = [s.name for s in ScenarioRunner.standard_stress_scenarios()]
        assert [name for name, _ in result.scenarios] == expected

    def test_base_scenario_matches_direct_portfolio_run(self):
        """Closed-form: BASE scenario aggregate == portfolio.run() directly."""
        portfolio = _two_deal_portfolio()
        direct = _two_deal_portfolio().run(HURDLE)
        scenario_result = portfolio.run_scenarios(
            HURDLE, scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)]
        )
        base = scenario_result.scenarios[0][1]
        np.testing.assert_allclose(base.total_pv_profits, direct.total_pv_profits, rtol=1e-10)
        np.testing.assert_allclose(
            base.aggregate_net_cash_flow, direct.aggregate_net_cash_flow, rtol=1e-12
        )
        np.testing.assert_allclose(base.aggregate_ceded_nar, direct.aggregate_ceded_nar, rtol=1e-12)
        assert base.n_deals == direct.n_deals
        assert base.total_face_amount == pytest.approx(direct.total_face_amount)

    def test_adverse_mortality_reduces_aggregate_pv_profits(self):
        """Reinsurer assuming coinsurance loses PV under +10% mortality."""
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(
            HURDLE,
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ],
        )
        base_pv = result.scenarios[0][1].total_pv_profits
        adverse_pv = result.scenarios[1][1].total_pv_profits
        assert adverse_pv < base_pv

    def test_favorable_mortality_increases_aggregate_pv_profits(self):
        """The symmetric leg: -10% mortality improves PV profits."""
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(
            HURDLE,
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_90", 0.90, 1.0),
            ],
        )
        base_pv = result.scenarios[0][1].total_pv_profits
        favorable_pv = result.scenarios[1][1].total_pv_profits
        assert favorable_pv > base_pv

    def test_stress_is_correlated_across_deals(self):
        """Every deal sees the same multiplier — the stress is uniform.

        Under +10% mortality, every per-deal reinsurer profit test should
        drop versus BASE. This guards against accidental partial-stress
        regressions (e.g. only applying the scenario to the first deal).
        """
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(
            HURDLE,
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ],
        )
        base_deals = {dr.deal_id: dr for dr in result.scenarios[0][1].deal_results}
        adverse_deals = {dr.deal_id: dr for dr in result.scenarios[1][1].deal_results}
        assert set(base_deals) == set(adverse_deals) == {"D1", "D2"}
        for deal_id in ("D1", "D2"):
            base_pv = base_deals[deal_id].profit_test.pv_profits
            adverse_pv = adverse_deals[deal_id].profit_test.pv_profits
            assert adverse_pv < base_pv, (
                f"Deal {deal_id}: adverse mortality did not reduce PV "
                f"(base={base_pv}, adverse={adverse_pv})"
            )

    def test_run_scenarios_does_not_mutate_portfolio(self):
        """Running scenarios leaves the original portfolio's deals unchanged.

        Each scenario applies a fresh multiplier to the base assumptions;
        calling :meth:`run` afterward must still match the BASE result.
        """
        portfolio = _two_deal_portfolio()
        original_versions = [deal.assumptions.version for deal in portfolio.deals]
        scenario_result = portfolio.run_scenarios(
            HURDLE,
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ],
        )
        post_versions = [deal.assumptions.version for deal in portfolio.deals]
        assert post_versions == original_versions

        base_pv = scenario_result.scenarios[0][1].total_pv_profits
        post_run_pv = portfolio.run(HURDLE).total_pv_profits
        np.testing.assert_allclose(post_run_pv, base_pv, rtol=1e-10)

    def test_run_scenarios_threads_calendar_alignment(self):
        """Mixed inception dates flow through ``align='calendar'``."""
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", start=date(2025, 1, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", start=date(2025, 7, 1)))
        )
        result = portfolio.run_scenarios(
            HURDLE,
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ],
            align="calendar",
        )
        base = result.scenarios[0][1]
        adverse = result.scenarios[1][1]
        # Calendar alignment preserves the projection horizon and deal count.
        assert base.n_deals == adverse.n_deals == 2
        assert base.projection_months == adverse.projection_months
        # Sensitivity must still hold under calendar alignment.
        assert adverse.total_pv_profits < base.total_pv_profits

    def test_run_scenarios_calendar_rejects_mixed_day_of_month(self):
        """Validation in ``run`` propagates through every scenario."""
        portfolio = (
            Portfolio()
            .add_deal(**_deal_spec("D1", "CedantA", start=date(2025, 1, 1)))
            .add_deal(**_deal_spec("D2", "CedantB", start=date(2025, 7, 15)))
        )
        with pytest.raises(PolarisValidationError, match="day-of-month"):
            portfolio.run_scenarios(
                HURDLE,
                scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)],
                align="calendar",
            )

    def test_empty_scenarios_list_rejected(self):
        portfolio = _two_deal_portfolio()
        with pytest.raises(PolarisValidationError, match="scenarios list is empty"):
            portfolio.run_scenarios(HURDLE, scenarios=[])

    def test_empty_portfolio_rejected(self):
        with pytest.raises(PolarisValidationError, match="empty portfolio"):
            Portfolio().run_scenarios(HURDLE, scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])

    def test_invalid_hurdle_rate_rejected(self):
        portfolio = _two_deal_portfolio()
        with pytest.raises(PolarisValidationError, match="hurdle_rate"):
            portfolio.run_scenarios(-1.5, scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])

    def test_invalid_align_mode_rejected(self):
        portfolio = _two_deal_portfolio()
        with pytest.raises(PolarisValidationError, match="align must be"):
            portfolio.run_scenarios(
                HURDLE,
                scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)],
                align="bogus",  # type: ignore[arg-type]
            )

    def test_lapse_stress_changes_aggregate_pv(self):
        """Lapse multiplier flows into the aggregate (LAPSE_80 vs BASE)."""
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(
            HURDLE,
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("LAPSE_80", 1.0, 0.80),
            ],
        )
        base_pv = result.scenarios[0][1].total_pv_profits
        lapse_pv = result.scenarios[1][1].total_pv_profits
        # Lapse-sensitivity sign depends on cash-flow pattern; require only
        # that the scenario actually moved the aggregate (i.e. the lapse
        # multiplier reached every deal's projection).
        assert lapse_pv != pytest.approx(base_pv, rel=1e-6)


class TestPortfolioScenarioResultHelpers:
    """``PortfolioScenarioResult`` helpers mirror ``ScenarioResult``."""

    def test_base_case_returns_base_portfolio_result(self):
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(HURDLE)
        base = result.base_case()
        assert base is not None
        assert isinstance(base, PortfolioResult)
        assert base.n_deals == 2

    def test_base_case_returns_none_when_absent(self):
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(
            HURDLE, scenarios=[ScenarioAdjustment("MORT_110", 1.10, 1.0)]
        )
        assert result.base_case() is None

    def test_worst_case_picks_lowest_aggregate_irr(self):
        """``worst_case`` picks by ``total_irr``, skipping ``None`` values.

        Unit-tests the helper directly against a hand-built
        :class:`PortfolioScenarioResult` so the assertion does not depend on
        synthetic projection setups producing valid IRRs (the standard
        coinsurance fixture's reserve-heavy cash flow trips the ADR-041
        suppression guardrail).
        """
        result = PortfolioScenarioResult(
            scenarios=[
                ("BASE", _stub_portfolio_result(total_irr=0.12)),
                ("MORT_110", _stub_portfolio_result(total_irr=0.07)),
                ("MORT_90", _stub_portfolio_result(total_irr=0.16)),
            ]
        )
        worst = result.worst_case()
        assert worst is not None
        assert worst[0] == "MORT_110"

    def test_worst_case_skips_none_irrs(self):
        """Scenarios with ``total_irr=None`` are skipped, not treated as -inf."""
        result = PortfolioScenarioResult(
            scenarios=[
                ("BASE", _stub_portfolio_result(total_irr=None)),
                ("MORT_110", _stub_portfolio_result(total_irr=0.07)),
            ]
        )
        worst = result.worst_case()
        assert worst is not None
        assert worst[0] == "MORT_110"

    def test_worst_case_returns_none_when_all_irrs_suppressed(self):
        result = PortfolioScenarioResult(
            scenarios=[
                ("BASE", _stub_portfolio_result(total_irr=None)),
                ("MORT_110", _stub_portfolio_result(total_irr=None)),
            ]
        )
        assert result.worst_case() is None

    def test_irr_range_is_ordered(self):
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(HURDLE)
        irr_min, irr_max = result.irr_range()
        if irr_min is not None and irr_max is not None:
            assert irr_min <= irr_max

    def test_empty_result_helpers_return_none(self):
        result = PortfolioScenarioResult()
        assert result.base_case() is None
        assert result.worst_case() is None
        assert result.irr_range() == (None, None)

    def test_to_dict_shape(self):
        portfolio = _two_deal_portfolio()
        result = portfolio.run_scenarios(
            HURDLE,
            scenarios=[
                ScenarioAdjustment("BASE", 1.0, 1.0),
                ScenarioAdjustment("MORT_110", 1.10, 1.0),
            ],
        )
        flat = result.to_dict()
        assert set(flat) == {"scenarios"}
        assert len(flat["scenarios"]) == 2  # type: ignore[arg-type]
        first = flat["scenarios"][0]  # type: ignore[index]
        assert first["name"] == "BASE"
        # Nested result must carry the full PortfolioResult.to_dict shape.
        assert "total_pv_profits" in first["result"]
        assert "deals" in first["result"]
        assert "concentration" in first["result"]
        assert "hhi" in first["result"]

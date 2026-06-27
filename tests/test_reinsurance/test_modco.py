"""
Tests for ModcoTreaty — Modified Coinsurance reinsurance treaty.

Verifies NCF additivity invariant, modco interest calculation,
and key distinctions from coinsurance (reserve not transferred).
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.core.asset import AssetPortfolio, Bond
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.reinsurance.modco import ModcoTreaty


def _make_gross(n_months: int = 120, face: float = 1_000_000.0) -> CashFlowResult:
    """Build a synthetic GROSS CashFlowResult for treaty testing."""
    rng = np.random.default_rng(42)
    premiums = np.full(n_months, 5_000.0, dtype=np.float64)
    claims = rng.uniform(0, 3_000.0, size=n_months).astype(np.float64)
    lapses = np.full(n_months, 200.0, dtype=np.float64)
    expenses = np.full(n_months, 100.0, dtype=np.float64)
    # Reserves: linearly increasing then decreasing (typical WL pattern)
    reserves = np.concatenate(
        [
            np.linspace(0, face * 0.3, n_months // 2),
            np.linspace(face * 0.3, face * 0.1, n_months - n_months // 2),
        ]
    ).astype(np.float64)
    reserve_inc = np.zeros(n_months, dtype=np.float64)
    reserve_inc[0] = reserves[0]
    reserve_inc[1:] = reserves[1:] - reserves[:-1]
    net_cf = premiums - claims - lapses - expenses - reserve_inc
    time_idx = np.array(
        [f"2025-{m % 12 + 1:02d}" for m in range(n_months)],
        dtype="datetime64[M]",
    )
    return CashFlowResult(
        run_id="TEST",
        valuation_date=date(2025, 1, 1),
        basis="GROSS",
        assumption_set_version="test-v1",
        product_type="WHOLE_LIFE",
        projection_months=n_months,
        time_index=time_idx,
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=lapses,
        expenses=expenses,
        reserve_balance=reserves,
        reserve_increase=reserve_inc,
        net_cash_flow=net_cf,
    )


@pytest.fixture()
def gross_120m() -> CashFlowResult:
    return _make_gross(n_months=120)


@pytest.fixture()
def modco_50pct() -> ModcoTreaty:
    return ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.045)


class TestModcoAdditivity:
    """NCF and cash flow additivity invariants."""

    def test_net_cash_flow_additivity(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """net_ncf + ceded_ncf == gross_ncf for all time steps."""
        net, ceded = modco_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow,
            gross_120m.net_cash_flow,
            rtol=1e-8,
            err_msg="NCF additivity failed",
        )

    def test_premium_additivity(self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty) -> None:
        """net_premiums + ceded_premiums == gross_premiums."""
        net, ceded = modco_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            net.gross_premiums + ceded.gross_premiums,
            gross_120m.gross_premiums,
            rtol=1e-10,
        )

    def test_claims_additivity(self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty) -> None:
        """net_claims + ceded_claims == gross_claims."""
        net, ceded = modco_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            net.death_claims + ceded.death_claims,
            gross_120m.death_claims,
            rtol=1e-10,
        )

    def test_verify_additivity_method(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """BaseTreaty.verify_additivity() passes for modco."""
        net, ceded = modco_50pct.apply(gross_120m)
        modco_50pct.verify_additivity(gross_120m, net, ceded)


class TestModcoReserveHandling:
    """Reserve is NOT transferred in Modco (key distinction from coinsurance)."""

    def test_net_reserve_equals_gross_reserve(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """Net reserve balance must equal gross (not split like coinsurance)."""
        net, _ceded = modco_50pct.apply(gross_120m)
        np.testing.assert_allclose(net.reserve_balance, gross_120m.reserve_balance, rtol=1e-10)

    def test_net_reserve_increase_equals_gross(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """Net reserve increase equals gross (entire reserve liability stays)."""
        net, _ceded = modco_50pct.apply(gross_120m)
        np.testing.assert_allclose(net.reserve_increase, gross_120m.reserve_increase, rtol=1e-10)

    def test_ceded_reserve_is_notional(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """Ceded reserve balance is notional (cession_pct * gross) for tracking."""
        _net, ceded = modco_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            ceded.reserve_balance, gross_120m.reserve_balance * 0.50, rtol=1e-10
        )


class TestModcoInterest:
    """Modco interest calculation."""

    def test_modco_interest_positive_reserves(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """Modco interest > 0 when reserves > 0."""
        net, _ceded = modco_50pct.apply(gross_120m)
        # Some reserve balance is positive, so some modco interest must be positive
        assert net.modco_interest is not None
        assert net.modco_interest.sum() > 0.0

    def test_modco_interest_formula(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """
        CLOSED-FORM: modco_interest = ceded_reserve * modco_rate / 12
        Verify for first month.
        """
        net, _ceded = modco_50pct.apply(gross_120m)
        expected_t0 = gross_120m.reserve_balance[0] * 0.50 * 0.045 / 12.0
        assert net.modco_interest is not None
        np.testing.assert_allclose(net.modco_interest[0], expected_t0, rtol=1e-10)

    def test_modco_interest_zero_when_zero_cession(self, gross_120m: CashFlowResult) -> None:
        """Modco interest = 0 when cession_pct = 0."""
        treaty = ModcoTreaty(cession_pct=0.0, modco_interest_rate=0.045)
        net, _ceded = treaty.apply(gross_120m)
        assert net.modco_interest is not None
        np.testing.assert_allclose(net.modco_interest, 0.0, atol=1e-10)

    def test_modco_interest_zero_when_zero_rate(self, gross_120m: CashFlowResult) -> None:
        """Modco interest = 0 when modco_interest_rate = 0."""
        treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.0)
        net, _ceded = treaty.apply(gross_120m)
        assert net.modco_interest is not None
        np.testing.assert_allclose(net.modco_interest, 0.0, atol=1e-10)

    def test_modco_interest_both_sides_equal(
        self, gross_120m: CashFlowResult, modco_50pct: ModcoTreaty
    ) -> None:
        """Net and ceded sides have the same modco_interest (same outflow/inflow)."""
        net, ceded = modco_50pct.apply(gross_120m)
        assert net.modco_interest is not None
        assert ceded.modco_interest is not None
        np.testing.assert_allclose(net.modco_interest, ceded.modco_interest, rtol=1e-10)


class TestModcoVsCoinsurance:
    """Compare Modco to Coinsurance — same P&L economics, different reserve treatment."""

    def test_net_ncf_differs_from_coinsurance(self, gross_120m: CashFlowResult) -> None:
        """Modco net NCF != coinsurance net NCF due to modco interest."""
        from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty

        modco = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.045)
        coins = CoinsuranceTreaty(cession_pct=0.50)

        net_modco, _ = modco.apply(gross_120m)
        net_coins, _ = coins.apply(gross_120m)

        # NCFs will differ because modco includes reserve increase and modco interest
        # while coinsurance splits reserve increase but not modco interest
        # The total sum should differ
        modco_total = net_modco.net_cash_flow.sum()
        coins_total = net_coins.net_cash_flow.sum()
        assert modco_total != pytest.approx(coins_total, rel=0.001), (
            "Modco and coinsurance NCF should differ due to reserve treatment"
        )


@pytest.fixture()
def par_portfolio_5pct() -> AssetPortfolio:
    """Annual-pay par bond carried at par → gross book yield == coupon (0.05)."""
    return AssetPortfolio(
        bonds=[
            Bond(
                face_value=1_000_000.0,
                coupon_rate=0.05,
                coupon_frequency=1,
                term_months=120,
                book_value=1_000_000.0,
            )
        ]
    )


@pytest.fixture()
def zero_book_portfolio() -> AssetPortfolio:
    """Bond carried at zero book value → book_yield() has no sign change → None."""
    return AssetPortfolio(
        bonds=[
            Bond(
                face_value=1_000_000.0,
                coupon_rate=0.04,
                coupon_frequency=2,
                term_months=120,
                book_value=0.0,
            )
        ]
    )


class TestModcoAssetDriven:
    """Slice 3 — asset book yield drives modco interest (Option A precedence)."""

    def test_book_yield_drives_modco_interest_closed_form(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        """
        CLOSED-FORM: with an asset portfolio supplied, modco interest is driven
        by the portfolio book yield: modco_interest = ceded_reserve * y_book / 12.
        The par portfolio's book yield is its coupon (0.05).
        """
        # Flat rate deliberately different from the book yield to prove precedence.
        treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.01)
        net, _ceded = treaty.apply(gross_120m, asset_portfolio=par_portfolio_5pct)
        y_book = par_portfolio_5pct.book_yield()
        assert y_book is not None
        expected = gross_120m.reserve_balance * 0.50 * y_book / 12.0
        assert net.modco_interest is not None
        np.testing.assert_allclose(net.modco_interest, expected, rtol=1e-9)

    def test_asset_yield_takes_precedence_over_flat_rate(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        """Asset book yield (0.05) overrides the flat modco_interest_rate (0.01)."""
        asset_treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.01)
        # A flat treaty pinned at the book yield should reproduce the asset path.
        flat_at_book = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.05)

        net_asset, _ = asset_treaty.apply(gross_120m, asset_portfolio=par_portfolio_5pct)
        net_flat, _ = flat_at_book.apply(gross_120m)

        assert net_asset.modco_interest is not None
        assert net_flat.modco_interest is not None
        np.testing.assert_allclose(net_asset.modco_interest, net_flat.modco_interest, rtol=1e-8)
        # And NOT the same as the treaty's own flat 0.01 rate.
        net_flat_low, _ = asset_treaty.apply(gross_120m)
        assert net_asset.modco_interest.sum() > net_flat_low.modco_interest.sum()

    def test_fallback_to_flat_rate_when_book_yield_none(
        self, gross_120m: CashFlowResult, zero_book_portfolio: AssetPortfolio
    ) -> None:
        """When book_yield() is None, the flat modco_interest_rate is the fallback."""
        assert zero_book_portfolio.book_yield() is None
        treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.045)
        net_asset, _ = treaty.apply(gross_120m, asset_portfolio=zero_book_portfolio)
        net_flat, _ = treaty.apply(gross_120m)
        assert net_asset.modco_interest is not None
        assert net_flat.modco_interest is not None
        np.testing.assert_allclose(net_asset.modco_interest, net_flat.modco_interest, rtol=1e-12)

    def test_no_portfolio_path_byte_identical(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        """Omitting asset_portfolio leaves the flat-rate result exactly unchanged."""
        treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.045)
        net_default, ceded_default = treaty.apply(gross_120m)
        net_none, ceded_none = treaty.apply(gross_120m, asset_portfolio=None)
        assert net_default.modco_interest is not None
        assert net_none.modco_interest is not None
        np.testing.assert_array_equal(net_default.modco_interest, net_none.modco_interest)
        np.testing.assert_array_equal(net_default.net_cash_flow, net_none.net_cash_flow)
        np.testing.assert_array_equal(ceded_default.net_cash_flow, ceded_none.net_cash_flow)

    def test_additivity_holds_with_asset_portfolio(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        """NCF additivity (net + ceded == gross) holds with an asset-driven rate."""
        treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.01)
        net, ceded = treaty.apply(gross_120m, asset_portfolio=par_portfolio_5pct)
        treaty.verify_additivity(gross_120m, net, ceded)
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow, gross_120m.net_cash_flow, rtol=1e-8
        )

    def test_both_sides_equal_modco_interest_with_asset(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        """Asset-driven modco interest is the same outflow/inflow on both sides."""
        treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.01)
        net, ceded = treaty.apply(gross_120m, asset_portfolio=par_portfolio_5pct)
        assert net.modco_interest is not None
        assert ceded.modco_interest is not None
        np.testing.assert_allclose(net.modco_interest, ceded.modco_interest, rtol=1e-12)


class TestModcoEdgeCases:
    """Edge cases and error handling."""

    def test_requires_reserve_balance(self) -> None:
        """Raises PolarisComputationError when reserve_balance is empty."""
        gross = CashFlowResult(
            run_id="TEST",
            valuation_date=date(2025, 1, 1),
            basis="GROSS",
            assumption_set_version="v1",
            product_type="WHOLE_LIFE",
            projection_months=0,
            time_index=np.array([], dtype="datetime64[M]"),
            gross_premiums=np.array([], dtype=np.float64),
            death_claims=np.array([], dtype=np.float64),
            lapse_surrenders=np.array([], dtype=np.float64),
            expenses=np.array([], dtype=np.float64),
            reserve_balance=np.array([], dtype=np.float64),
            reserve_increase=np.array([], dtype=np.float64),
            net_cash_flow=np.array([], dtype=np.float64),
        )
        treaty = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.045)
        with pytest.raises(PolarisComputationError):
            treaty.apply(gross)

    def test_full_cession(self, gross_120m: CashFlowResult) -> None:
        """At 100% cession, net premiums = 0, ceded premiums = gross premiums."""
        treaty = ModcoTreaty(cession_pct=1.0, modco_interest_rate=0.04)
        net, ceded = treaty.apply(gross_120m)
        np.testing.assert_allclose(net.gross_premiums, 0.0, atol=1e-10)
        np.testing.assert_allclose(ceded.gross_premiums, gross_120m.gross_premiums, rtol=1e-10)

    def test_zero_cession(self, gross_120m: CashFlowResult) -> None:
        """At 0% cession, net == gross and ceded == 0."""
        treaty = ModcoTreaty(cession_pct=0.0, modco_interest_rate=0.04)
        net, ceded = treaty.apply(gross_120m)
        np.testing.assert_allclose(net.gross_premiums, gross_120m.gross_premiums, rtol=1e-10)
        np.testing.assert_allclose(ceded.gross_premiums, 0.0, atol=1e-10)

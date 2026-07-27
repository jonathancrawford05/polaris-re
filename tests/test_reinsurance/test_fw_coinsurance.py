"""
Tests for FWCoinsuranceTreaty — Funds-Withheld Coinsurance reinsurance treaty.

Verifies the NCF additivity invariant, the funds-withheld interest calculation,
the coinsurance-style proportional reserve transfer (the key distinction from
Modco), and the Option-A asset-book-yield precedence (shared with Modco).
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.core.asset import AssetPortfolio, Bond
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.reinsurance.fw_coinsurance import FWCoinsuranceTreaty
from polaris_re.reinsurance.modco import ModcoTreaty


def _make_gross(n_months: int = 120, face: float = 1_000_000.0) -> CashFlowResult:
    """Build a synthetic GROSS CashFlowResult for treaty testing.

    Deterministic (seeded RNG) so every assertion is reproducible; no wall-clock
    dependence (valuation_date pinned) per the ADR-074 guardrail.
    """
    rng = np.random.default_rng(42)
    premiums = np.full(n_months, 5_000.0, dtype=np.float64)
    claims = rng.uniform(0, 3_000.0, size=n_months).astype(np.float64)
    lapses = np.full(n_months, 200.0, dtype=np.float64)
    expenses = np.full(n_months, 100.0, dtype=np.float64)
    # Reserves: linearly increasing then decreasing (typical WL pattern).
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
def fw_50pct() -> FWCoinsuranceTreaty:
    return FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.045)


class TestFWCoinsuranceAdditivity:
    """NCF and cash flow additivity invariants — the funds-withheld interest cancels."""

    def test_net_cash_flow_additivity(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        """net_ncf + ceded_ncf == gross_ncf for all time steps."""
        net, ceded = fw_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow,
            gross_120m.net_cash_flow,
            rtol=1e-8,
            err_msg="NCF additivity failed",
        )

    @pytest.mark.parametrize("cession", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_additivity_across_cessions(self, gross_120m: CashFlowResult, cession: float) -> None:
        """Additivity holds across the full cession range."""
        treaty = FWCoinsuranceTreaty(cession_pct=cession, funds_withheld_rate=0.045)
        net, ceded = treaty.apply(gross_120m)
        treaty.verify_additivity(gross_120m, net, ceded)
        for line in ("gross_premiums", "death_claims", "lapse_surrenders", "expenses"):
            np.testing.assert_allclose(
                getattr(net, line) + getattr(ceded, line),
                getattr(gross_120m, line),
                rtol=1e-10,
                err_msg=f"{line} additivity failed at cession={cession}",
            )

    def test_reserve_additivity(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        """Reserve balance and increase are additive (transferred, unlike modco)."""
        net, ceded = fw_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            net.reserve_balance + ceded.reserve_balance, gross_120m.reserve_balance, rtol=1e-10
        )
        np.testing.assert_allclose(
            net.reserve_increase + ceded.reserve_increase, gross_120m.reserve_increase, rtol=1e-10
        )


class TestFWCoinsuranceReserveTransfer:
    """Reserve IS transferred proportionally (key distinction from Modco)."""

    def test_net_reserve_is_retention_share(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        """Net reserve balance = gross * (1 - c), NOT the full gross (modco)."""
        net, _ceded = fw_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            net.reserve_balance, gross_120m.reserve_balance * 0.50, rtol=1e-10
        )

    def test_ceded_reserve_is_cession_share(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        """Ceded reserve balance = gross * c (a real transfer, not notional)."""
        _net, ceded = fw_50pct.apply(gross_120m)
        np.testing.assert_allclose(
            ceded.reserve_balance, gross_120m.reserve_balance * 0.50, rtol=1e-10
        )


class TestFundsWithheldInterest:
    """Funds-withheld interest credit calculation."""

    def test_interest_positive_when_reserves_positive(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        net, _ceded = fw_50pct.apply(gross_120m)
        assert net.funds_withheld_interest is not None
        assert net.funds_withheld_interest.sum() > 0.0

    def test_interest_formula_closed_form(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        """CLOSED-FORM: fwi = ceded_reserve * rate / 12, checked over the whole vector."""
        net, _ceded = fw_50pct.apply(gross_120m)
        expected = gross_120m.reserve_balance * 0.50 * 0.045 / 12.0
        assert net.funds_withheld_interest is not None
        np.testing.assert_allclose(net.funds_withheld_interest, expected, rtol=1e-10)

    def test_interest_zero_when_zero_cession(self, gross_120m: CashFlowResult) -> None:
        treaty = FWCoinsuranceTreaty(cession_pct=0.0, funds_withheld_rate=0.045)
        net, _ceded = treaty.apply(gross_120m)
        assert net.funds_withheld_interest is not None
        np.testing.assert_allclose(net.funds_withheld_interest, 0.0, atol=1e-10)

    def test_interest_zero_when_zero_rate(self, gross_120m: CashFlowResult) -> None:
        treaty = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.0)
        net, _ceded = treaty.apply(gross_120m)
        assert net.funds_withheld_interest is not None
        np.testing.assert_allclose(net.funds_withheld_interest, 0.0, atol=1e-10)

    def test_interest_both_sides_equal(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        """Net and ceded carry the same interest (one transfer, opposite signs in NCF)."""
        net, ceded = fw_50pct.apply(gross_120m)
        assert net.funds_withheld_interest is not None
        assert ceded.funds_withheld_interest is not None
        np.testing.assert_allclose(
            net.funds_withheld_interest, ceded.funds_withheld_interest, rtol=1e-12
        )

    def test_interest_scales_linearly_with_rate(self, gross_120m: CashFlowResult) -> None:
        """CLOSED-FORM sensitivity: doubling the rate doubles the interest."""
        low, _ = FWCoinsuranceTreaty(cession_pct=0.5, funds_withheld_rate=0.02).apply(gross_120m)
        high, _ = FWCoinsuranceTreaty(cession_pct=0.5, funds_withheld_rate=0.04).apply(gross_120m)
        assert low.funds_withheld_interest is not None
        assert high.funds_withheld_interest is not None
        np.testing.assert_allclose(
            high.funds_withheld_interest, 2.0 * low.funds_withheld_interest, rtol=1e-10
        )


class TestFWCoinsuranceVsPeers:
    """Relationship to Coinsurance and Modco."""

    def test_equals_coinsurance_plus_interest_transfer(self, gross_120m: CashFlowResult) -> None:
        """
        CLOSED-FORM identity: FW coinsurance NCF == coinsurance NCF with the
        funds-withheld interest folded in (net pays, ceded receives).
        """
        fw = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.045)
        coins = CoinsuranceTreaty(cession_pct=0.50, include_expense_allowance=True)

        net_fw, ceded_fw = fw.apply(gross_120m)
        net_co, ceded_co = coins.apply(gross_120m)

        assert net_fw.funds_withheld_interest is not None
        fwi = net_fw.funds_withheld_interest
        np.testing.assert_allclose(net_fw.net_cash_flow, net_co.net_cash_flow - fwi, rtol=1e-9)
        np.testing.assert_allclose(ceded_fw.net_cash_flow, ceded_co.net_cash_flow + fwi, rtol=1e-9)

    def test_reserve_treatment_differs_from_modco(self, gross_120m: CashFlowResult) -> None:
        """Modco keeps the full reserve with the cedant; FW coinsurance transfers it."""
        fw = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.045)
        modco = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.045)

        net_fw, _ = fw.apply(gross_120m)
        net_modco, _ = modco.apply(gross_120m)

        # Modco: net reserve == gross reserve; FW: net reserve == half gross.
        np.testing.assert_allclose(
            net_modco.reserve_balance, gross_120m.reserve_balance, rtol=1e-10
        )
        assert not np.allclose(net_fw.reserve_balance, gross_120m.reserve_balance)

    def test_interest_matches_modco_interest_same_rate(self, gross_120m: CashFlowResult) -> None:
        """The interest mechanic is identical to modco on the same notional reserve."""
        fw = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.045)
        modco = ModcoTreaty(cession_pct=0.50, modco_interest_rate=0.045)
        net_fw, _ = fw.apply(gross_120m)
        net_modco, _ = modco.apply(gross_120m)
        assert net_fw.funds_withheld_interest is not None
        assert net_modco.modco_interest is not None
        np.testing.assert_allclose(
            net_fw.funds_withheld_interest, net_modco.modco_interest, rtol=1e-12
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


class TestFWCoinsuranceAssetDriven:
    """Asset book yield drives the funds-withheld interest (Option A precedence)."""

    def test_book_yield_drives_interest_closed_form(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        """CLOSED-FORM: fwi = ceded_reserve * y_book / 12; par book yield == coupon (0.05)."""
        treaty = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.01)
        net, _ = treaty.apply(gross_120m, asset_portfolio=par_portfolio_5pct)
        y_book = par_portfolio_5pct.book_yield()
        assert y_book is not None
        expected = gross_120m.reserve_balance * 0.50 * y_book / 12.0
        assert net.funds_withheld_interest is not None
        np.testing.assert_allclose(net.funds_withheld_interest, expected, rtol=1e-9)

    def test_asset_yield_takes_precedence_over_flat_rate(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        asset_treaty = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.01)
        flat_at_book = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.05)
        net_asset, _ = asset_treaty.apply(gross_120m, asset_portfolio=par_portfolio_5pct)
        net_flat, _ = flat_at_book.apply(gross_120m)
        assert net_asset.funds_withheld_interest is not None
        assert net_flat.funds_withheld_interest is not None
        np.testing.assert_allclose(
            net_asset.funds_withheld_interest, net_flat.funds_withheld_interest, rtol=1e-8
        )

    def test_fallback_to_flat_rate_when_book_yield_none(
        self, gross_120m: CashFlowResult, zero_book_portfolio: AssetPortfolio
    ) -> None:
        assert zero_book_portfolio.book_yield() is None
        treaty = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.045)
        net_asset, _ = treaty.apply(gross_120m, asset_portfolio=zero_book_portfolio)
        net_flat, _ = treaty.apply(gross_120m)
        assert net_asset.funds_withheld_interest is not None
        assert net_flat.funds_withheld_interest is not None
        np.testing.assert_allclose(
            net_asset.funds_withheld_interest, net_flat.funds_withheld_interest, rtol=1e-12
        )

    def test_no_portfolio_path_byte_identical(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        """Omitting asset_portfolio leaves the flat-rate result exactly unchanged."""
        treaty = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.045)
        net_default, ceded_default = treaty.apply(gross_120m)
        net_none, ceded_none = treaty.apply(gross_120m, asset_portfolio=None)
        assert net_default.funds_withheld_interest is not None
        assert net_none.funds_withheld_interest is not None
        np.testing.assert_array_equal(
            net_default.funds_withheld_interest, net_none.funds_withheld_interest
        )
        np.testing.assert_array_equal(net_default.net_cash_flow, net_none.net_cash_flow)
        np.testing.assert_array_equal(ceded_default.net_cash_flow, ceded_none.net_cash_flow)

    def test_additivity_holds_with_asset_portfolio(
        self, gross_120m: CashFlowResult, par_portfolio_5pct: AssetPortfolio
    ) -> None:
        treaty = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.01)
        net, ceded = treaty.apply(gross_120m, asset_portfolio=par_portfolio_5pct)
        treaty.verify_additivity(gross_120m, net, ceded)
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow, gross_120m.net_cash_flow, rtol=1e-8
        )


class TestFWCoinsuranceExpenseToggle:
    """include_expense_allowance controls whether expenses split or stay with cedant."""

    def test_expenses_split_when_enabled(
        self, gross_120m: CashFlowResult, fw_50pct: FWCoinsuranceTreaty
    ) -> None:
        net, ceded = fw_50pct.apply(gross_120m)
        np.testing.assert_allclose(net.expenses, gross_120m.expenses * 0.50, rtol=1e-10)
        np.testing.assert_allclose(ceded.expenses, gross_120m.expenses * 0.50, rtol=1e-10)

    def test_expenses_stay_with_cedant_when_disabled(self, gross_120m: CashFlowResult) -> None:
        treaty = FWCoinsuranceTreaty(
            cession_pct=0.50, funds_withheld_rate=0.045, include_expense_allowance=False
        )
        net, ceded = treaty.apply(gross_120m)
        np.testing.assert_allclose(net.expenses, gross_120m.expenses, rtol=1e-10)
        np.testing.assert_allclose(ceded.expenses, 0.0, atol=1e-10)
        # Additivity still holds with the interest transfer.
        treaty.verify_additivity(gross_120m, net, ceded)


class TestFWCoinsuranceEdgeCases:
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
        treaty = FWCoinsuranceTreaty(cession_pct=0.50, funds_withheld_rate=0.045)
        with pytest.raises(PolarisComputationError):
            treaty.apply(gross)

    def test_full_cession(self, gross_120m: CashFlowResult) -> None:
        """At 100% cession, net premiums = 0, ceded premiums = gross premiums."""
        treaty = FWCoinsuranceTreaty(cession_pct=1.0, funds_withheld_rate=0.04)
        net, ceded = treaty.apply(gross_120m)
        np.testing.assert_allclose(net.gross_premiums, 0.0, atol=1e-10)
        np.testing.assert_allclose(ceded.gross_premiums, gross_120m.gross_premiums, rtol=1e-10)
        np.testing.assert_allclose(net.reserve_balance, 0.0, atol=1e-6)

    def test_zero_cession(self, gross_120m: CashFlowResult) -> None:
        """At 0% cession, net == gross and ceded == 0."""
        treaty = FWCoinsuranceTreaty(cession_pct=0.0, funds_withheld_rate=0.04)
        net, ceded = treaty.apply(gross_120m)
        np.testing.assert_allclose(net.gross_premiums, gross_120m.gross_premiums, rtol=1e-10)
        np.testing.assert_allclose(ceded.gross_premiums, 0.0, atol=1e-10)

    def test_negative_rate_rejected(self) -> None:
        """funds_withheld_rate must be >= 0 (Field ge=0 constraint)."""
        with pytest.raises(ValueError):
            FWCoinsuranceTreaty(cession_pct=0.5, funds_withheld_rate=-0.01)

    def test_cession_out_of_range_rejected(self) -> None:
        """cession_pct is bounded to [0, 1]."""
        with pytest.raises(ValueError):
            FWCoinsuranceTreaty(cession_pct=1.5, funds_withheld_rate=0.04)


class TestFWCoinsuranceExport:
    """The treaty is exported from the reinsurance package."""

    def test_importable_from_package(self) -> None:
        from polaris_re.reinsurance import FWCoinsuranceTreaty as Exported

        assert Exported is FWCoinsuranceTreaty

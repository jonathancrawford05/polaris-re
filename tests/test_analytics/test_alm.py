"""
Tests for analytics/alm.py — asset-liability duration-gap analysis (Epic 4,
Asset / ALM, Slice 4).

Closed-form verifications:
- ``duration_measures`` of a single bullet cash flow at month N: Macaulay = N/12
  years, modified = (N/12)/(1+y), PV = cf * v**N.
- modified = Macaulay / (1 + y) for an arbitrary stream.
- ``duration_measures`` on an ``AssetPortfolio``'s aggregate cash flows
  reproduces that portfolio's own duration API exactly (the same closed form).
- ``duration_gap`` differences the two modified durations and dollar durations;
  a perfectly matched (assets == liability) block has both gaps zero.
- The gap's sign tracks the relative term of assets vs liability.
- ``liability_cash_flows`` extracts net benefit outgo with the documented sign.
- Non-positive present value raises ``PolarisComputationError``.
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.analytics.alm import (
    DurationGapResult,
    DurationMeasures,
    duration_gap,
    duration_measures,
    liability_cash_flows,
)
from polaris_re.core.asset import AssetPortfolio, Bond
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError


def _v(annual_yield: float) -> float:
    """Engine monthly discount factor."""
    return (1.0 + annual_yield) ** (-1.0 / 12.0)


# ---------------------------------------------------------------------------
# duration_measures — closed forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("months", [12, 36, 120])
@pytest.mark.parametrize("y", [0.0, 0.03, 0.06])
def test_bullet_cash_flow_duration_closed_form(months: int, y: float) -> None:
    """A single cash flow at month N has Macaulay = N/12 years, modified = that/(1+y)."""
    cf = np.zeros(months, dtype=np.float64)
    cf[months - 1] = 1_000.0
    m = duration_measures(cf, y)

    n_years = months / 12.0
    expected_pv = 1_000.0 * _v(y) ** months
    np.testing.assert_allclose(m.present_value, expected_pv)
    np.testing.assert_allclose(m.macaulay_duration, n_years)
    np.testing.assert_allclose(m.modified_duration, n_years / (1.0 + y))


def test_modified_equals_macaulay_over_one_plus_y() -> None:
    """For an arbitrary coupon-like stream, modified = Macaulay / (1 + y)."""
    cf = np.array([10.0, 10.0, 10.0, 1_010.0], dtype=np.float64)
    y = 0.05
    m = duration_measures(cf, y)
    np.testing.assert_allclose(m.modified_duration, m.macaulay_duration / (1.0 + y))


def test_duration_measures_returns_model_and_float_fields() -> None:
    cf = np.array([0.0, 0.0, 500.0], dtype=np.float64)
    m = duration_measures(cf, 0.04)
    assert isinstance(m, DurationMeasures)
    assert isinstance(m.present_value, float)
    assert isinstance(m.macaulay_duration, float)
    assert isinstance(m.modified_duration, float)


def test_duration_measures_matches_asset_portfolio_api() -> None:
    """The generic primitive reproduces AssetPortfolio's own duration measures."""
    portfolio = AssetPortfolio(
        bonds=[
            Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=2, term_months=120),
            Bond(face_value=2_000.0, coupon_rate=0.03, coupon_frequency=1, term_months=60),
        ]
    )
    y = 0.04
    m = duration_measures(portfolio.cash_flow_vector(), y)
    np.testing.assert_allclose(m.macaulay_duration, portfolio.macaulay_duration(y))
    np.testing.assert_allclose(m.modified_duration, portfolio.modified_duration(y))
    np.testing.assert_allclose(m.present_value, portfolio.market_value(y))


def test_duration_measures_raises_on_nonpositive_pv() -> None:
    cf = np.array([-100.0, -50.0, -25.0], dtype=np.float64)
    with pytest.raises(PolarisComputationError, match="non-positive present value"):
        duration_measures(cf, 0.05)


def test_duration_measures_rejects_empty_vector() -> None:
    with pytest.raises(PolarisValidationError, match="non-empty"):
        duration_measures(np.array([], dtype=np.float64), 0.05)


# ---------------------------------------------------------------------------
# liability_cash_flows — extraction from a CashFlowResult
# ---------------------------------------------------------------------------


def _make_result(
    *,
    premiums: np.ndarray,
    claims: np.ndarray,
    lapses: np.ndarray,
    expenses: np.ndarray,
) -> CashFlowResult:
    return CashFlowResult(
        run_id="alm-test",
        valuation_date=date(2026, 1, 1),
        basis="NET",
        assumption_set_version="v1",
        product_type="TERM",
        gross_premiums=premiums,
        death_claims=claims,
        lapse_surrenders=lapses,
        expenses=expenses,
        net_cash_flow=premiums - claims - lapses - expenses,
    )


def test_liability_cash_flows_extraction() -> None:
    """Liability outgo = claims + lapses + expenses - premiums, with the right sign."""
    premiums = np.array([100.0, 90.0, 80.0], dtype=np.float64)
    claims = np.array([20.0, 40.0, 200.0], dtype=np.float64)
    lapses = np.array([5.0, 5.0, 5.0], dtype=np.float64)
    expenses = np.array([10.0, 10.0, 10.0], dtype=np.float64)
    result = _make_result(premiums=premiums, claims=claims, lapses=lapses, expenses=expenses)

    liab = liability_cash_flows(result)
    expected = claims + lapses + expenses - premiums
    assert liab.dtype == np.float64
    np.testing.assert_allclose(liab, expected)
    # Net inflow early (premiums dominate) -> negative; net outflow late -> positive.
    assert liab[0] < 0.0
    assert liab[-1] > 0.0


def test_liability_cash_flows_benefit_heavy_block_has_positive_pv() -> None:
    """A benefit-heavy block discounts to a positive liability PV (duration defined)."""
    premiums = np.array([50.0, 40.0, 30.0], dtype=np.float64)
    claims = np.array([100.0, 120.0, 140.0], dtype=np.float64)
    lapses = np.zeros(3, dtype=np.float64)
    expenses = np.array([5.0, 5.0, 5.0], dtype=np.float64)
    result = _make_result(premiums=premiums, claims=claims, lapses=lapses, expenses=expenses)

    m = duration_measures(liability_cash_flows(result), 0.05)
    assert m.present_value > 0.0


# ---------------------------------------------------------------------------
# duration_gap — differencing and dollar duration
# ---------------------------------------------------------------------------


def test_duration_gap_differences_modified_durations() -> None:
    """gap = asset modified duration - liability modified duration."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.04, coupon_frequency=2, term_months=120)]
    )
    # Liability: a single bullet at 60 months (shorter than the 10y asset).
    liab = np.zeros(120, dtype=np.float64)
    liab[59] = 1_000.0
    y = 0.04

    res = duration_gap(portfolio, liab, y)
    assert isinstance(res, DurationGapResult)

    np.testing.assert_allclose(res.asset_modified_duration, portfolio.modified_duration(y))
    np.testing.assert_allclose(res.asset_macaulay_duration, portfolio.macaulay_duration(y))
    np.testing.assert_allclose(res.asset_market_value, portfolio.market_value(y))

    liab_m = duration_measures(liab, y)
    np.testing.assert_allclose(res.liability_modified_duration, liab_m.modified_duration)
    np.testing.assert_allclose(
        res.duration_gap, res.asset_modified_duration - liab_m.modified_duration
    )
    # 10y coupon bond is longer than a 5y bullet -> positive gap.
    assert res.duration_gap > 0.0


def test_dollar_duration_gap_closed_form() -> None:
    """Dollar durations = modified duration * value; gap is their difference."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=5_000.0, coupon_rate=0.03, coupon_frequency=1, term_months=84)]
    )
    liab = np.zeros(84, dtype=np.float64)
    liab[83] = 6_000.0
    y = 0.05

    res = duration_gap(portfolio, liab, y)
    liab_m = duration_measures(liab, y)

    np.testing.assert_allclose(
        res.dollar_duration_asset, res.asset_modified_duration * portfolio.market_value(y)
    )
    np.testing.assert_allclose(
        res.dollar_duration_liability, liab_m.modified_duration * liab_m.present_value
    )
    np.testing.assert_allclose(
        res.dollar_duration_gap, res.dollar_duration_asset - res.dollar_duration_liability
    )


def test_perfectly_matched_block_has_zero_gap() -> None:
    """Assets whose cash flows equal the liability's are immunised: both gaps ~0."""
    bond = Bond(face_value=1_000.0, coupon_rate=0.06, coupon_frequency=2, term_months=60)
    portfolio = AssetPortfolio(bonds=[bond])
    liab = portfolio.cash_flow_vector()  # identical stream
    y = 0.045

    res = duration_gap(portfolio, liab, y)
    np.testing.assert_allclose(res.duration_gap, 0.0, atol=1e-12)
    np.testing.assert_allclose(res.dollar_duration_gap, 0.0, atol=1e-6)
    np.testing.assert_allclose(res.asset_market_value, res.liability_present_value)


def test_gap_sign_flips_when_liability_is_longer() -> None:
    """A long liability against short assets gives a negative duration gap."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.04, coupon_frequency=2, term_months=24)]
    )
    liab = np.zeros(240, dtype=np.float64)
    liab[239] = 1_000.0  # 20-year bullet liability
    y = 0.04

    res = duration_gap(portfolio, liab, y)
    assert res.duration_gap < 0.0
    assert res.liability_modified_duration > res.asset_modified_duration


def test_duration_gap_raises_on_nonpositive_liability_pv() -> None:
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.04, coupon_frequency=2, term_months=24)]
    )
    bad_liab = np.array([-1.0, -2.0, -3.0], dtype=np.float64)
    with pytest.raises(PolarisComputationError, match="non-positive present value"):
        duration_gap(portfolio, bad_liab, 0.04)

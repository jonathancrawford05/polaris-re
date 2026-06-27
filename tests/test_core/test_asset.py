"""
Tests for core/asset.py — bond cash-flow model and AssetPortfolio (Epic 4,
Slice 1).

Closed-form verifications:
- A par bond (annual-pay, coupon = yield) prices exactly to par.
- A zero-coupon bond prices to face * (1 + y) ** (-N / 12).
- Coupon + principal land on the correct monthly grid indices.
- A portfolio's cash-flow vector and market value are the sum of its bonds'.
- Field validation rejects malformed instruments.
"""

import numpy as np
import pytest
from pydantic import ValidationError

from polaris_re.core.asset import AssetPortfolio, Bond
from polaris_re.core.exceptions import PolarisComputationError

# ---------------------------------------------------------------------------
# Bond.cash_flow_vector — coupon + principal land on the right months
# ---------------------------------------------------------------------------


def test_annual_bond_cash_flow_vector_timing() -> None:
    """A 2-year annual-pay 5% bond on $1,000 pays 50 at m12, 1050 at m24."""
    bond = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)
    cf = bond.cash_flow_vector(24)

    assert cf.dtype == np.float64
    assert cf.shape == (24,)
    expected = np.zeros(24, dtype=np.float64)
    expected[11] = 50.0  # month 12 (1-indexed) -> index 11
    expected[23] = 1_050.0  # month 24 coupon 50 + principal 1000
    np.testing.assert_allclose(cf, expected)


def test_semiannual_bond_cash_flow_vector_timing() -> None:
    """A 1-year semiannual 4% bond on $1,000 pays 20 at m6, 1020 at m12."""
    bond = Bond(face_value=1_000.0, coupon_rate=0.04, coupon_frequency=2, term_months=12)
    cf = bond.cash_flow_vector(12)

    expected = np.zeros(12, dtype=np.float64)
    expected[5] = 20.0  # month 6 coupon
    expected[11] = 1_020.0  # month 12 coupon 20 + principal 1000
    np.testing.assert_allclose(cf, expected)


def test_zero_coupon_bond_cash_flow_vector() -> None:
    """A zero-coupon bond pays only the face at maturity."""
    bond = Bond(face_value=1_000.0, coupon_rate=0.0, coupon_frequency=1, term_months=36)
    cf = bond.cash_flow_vector(36)

    expected = np.zeros(36, dtype=np.float64)
    expected[35] = 1_000.0
    np.testing.assert_allclose(cf, expected)


def test_cash_flow_vector_horizon_shorter_than_term_truncates() -> None:
    """Requesting fewer months than the term drops the later cash flows."""
    bond = Bond(face_value=1_000.0, coupon_rate=0.06, coupon_frequency=1, term_months=24)
    cf = bond.cash_flow_vector(12)

    expected = np.zeros(12, dtype=np.float64)
    expected[11] = 60.0  # only the first annual coupon falls inside 12 months
    np.testing.assert_allclose(cf, expected)


def test_cash_flow_vector_horizon_longer_than_term_pads_zeros() -> None:
    """Requesting more months than the term pads with zeros after maturity."""
    bond = Bond(face_value=1_000.0, coupon_rate=0.0, coupon_frequency=1, term_months=12)
    cf = bond.cash_flow_vector(24)

    assert cf.shape == (24,)
    np.testing.assert_allclose(cf[11], 1_000.0)
    np.testing.assert_allclose(cf[12:], np.zeros(12))


# ---------------------------------------------------------------------------
# Bond.price — closed-form PV checks
# ---------------------------------------------------------------------------


def test_par_bond_prices_to_par() -> None:
    """Annual-pay bond with coupon == yield prices exactly to face value.

    Under the engine's effective-annual discounting (v = (1+y)^(-1/12)), an
    annual-pay bond at coupon = yield telescopes to par:
        price = face*y*sum_k v^{12k} + face*v^{12N}
              = face*(1 - v^{12N}) + face*v^{12N} = face
    """
    y = 0.05
    bond = Bond(face_value=1_000.0, coupon_rate=y, coupon_frequency=1, term_months=120)
    assert bond.price(y) == pytest.approx(1_000.0, abs=1e-6)


def test_zero_coupon_bond_price_closed_form() -> None:
    """Zero-coupon price = face * (1 + y) ** (-N / 12)."""
    y = 0.04
    n_months = 60
    bond = Bond(face_value=1_000.0, coupon_rate=0.0, coupon_frequency=1, term_months=n_months)
    expected = 1_000.0 * (1.0 + y) ** (-n_months / 12.0)
    assert bond.price(y) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize(
    ("coupon", "yld", "direction"),
    [
        (0.06, 0.04, "premium"),  # coupon > yield -> price above par
        (0.04, 0.04, "par"),  # coupon == yield -> par
        (0.02, 0.04, "discount"),  # coupon < yield -> price below par
    ],
)
def test_price_par_premium_discount(coupon: float, yld: float, direction: str) -> None:
    """Coupon vs yield determines premium / par / discount pricing."""
    bond = Bond(face_value=1_000.0, coupon_rate=coupon, coupon_frequency=1, term_months=120)
    price = bond.price(yld)
    if direction == "premium":
        assert price > 1_000.0
    elif direction == "par":
        assert price == pytest.approx(1_000.0, abs=1e-6)
    else:
        assert price < 1_000.0


def test_price_matches_manual_discounting() -> None:
    """Bond price equals manual v^t discounting of its cash-flow vector."""
    y = 0.045
    bond = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=2, term_months=24)
    cf = bond.cash_flow_vector(24)
    v = (1.0 + y) ** (-1.0 / 12.0)
    discount = v ** np.arange(1, 25)
    expected = float(np.dot(cf, discount))
    assert bond.price(y) == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# AssetPortfolio — aggregation
# ---------------------------------------------------------------------------


def test_portfolio_cash_flow_vector_is_sum_of_bonds() -> None:
    b1 = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)
    b2 = Bond(face_value=2_000.0, coupon_rate=0.03, coupon_frequency=2, term_months=12)
    pf = AssetPortfolio(bonds=[b1, b2])

    cf = pf.cash_flow_vector(24)
    expected = b1.cash_flow_vector(24) + b2.cash_flow_vector(24)
    np.testing.assert_allclose(cf, expected)


def test_portfolio_cash_flow_vector_default_horizon_is_max_term() -> None:
    b1 = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)
    b2 = Bond(face_value=2_000.0, coupon_rate=0.03, coupon_frequency=2, term_months=36)
    pf = AssetPortfolio(bonds=[b1, b2])

    cf = pf.cash_flow_vector()
    assert cf.shape == (36,)


def test_portfolio_market_value_is_sum_of_prices() -> None:
    y = 0.04
    b1 = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)
    b2 = Bond(face_value=2_000.0, coupon_rate=0.03, coupon_frequency=2, term_months=12)
    pf = AssetPortfolio(bonds=[b1, b2])

    assert pf.market_value(y) == pytest.approx(b1.price(y) + b2.price(y), abs=1e-9)


def test_portfolio_book_and_face_totals() -> None:
    b1 = Bond(
        face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24, book_value=980.0
    )
    b2 = Bond(face_value=2_000.0, coupon_rate=0.03, coupon_frequency=2, term_months=12)
    pf = AssetPortfolio(bonds=[b1, b2])

    # b2 has no explicit book value -> defaults to its face (2000)
    assert pf.book_value == pytest.approx(980.0 + 2_000.0)
    assert pf.total_face_value == pytest.approx(3_000.0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_bond_carrying_value_defaults_to_face() -> None:
    bond = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)
    assert bond.book_value is None  # raw input unset
    np.testing.assert_allclose(bond.carrying_value, 1_000.0)  # resolved to par


def test_bond_carrying_value_uses_explicit_book_value() -> None:
    bond = Bond(
        face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24, book_value=970.0
    )
    np.testing.assert_allclose(bond.carrying_value, 970.0)


@pytest.mark.parametrize("freq", [0, 5, 7, 8, 24])
def test_coupon_frequency_must_divide_12(freq: int) -> None:
    with pytest.raises(ValueError):
        Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=freq, term_months=24)


@pytest.mark.parametrize("freq", [1, 2, 3, 4, 6, 12])
def test_valid_coupon_frequencies_accepted(freq: int) -> None:
    bond = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=freq, term_months=24)
    assert bond.coupon_frequency == freq


def test_negative_face_value_rejected() -> None:
    with pytest.raises(ValueError):
        Bond(face_value=-1.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)


def test_negative_coupon_rate_rejected() -> None:
    with pytest.raises(ValueError):
        Bond(face_value=1_000.0, coupon_rate=-0.01, coupon_frequency=1, term_months=24)


def test_nonpositive_term_rejected() -> None:
    with pytest.raises(ValueError):
        Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=0)


def test_empty_portfolio_rejected() -> None:
    with pytest.raises(ValueError):
        AssetPortfolio(bonds=[])


def test_cash_flow_vector_nonpositive_months_rejected() -> None:
    bond = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)
    with pytest.raises(ValueError):
        bond.cash_flow_vector(0)


def test_models_are_frozen() -> None:
    bond = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)
    with pytest.raises(ValidationError):
        bond.face_value = 2_000.0  # type: ignore[misc]


# ===========================================================================
# Slice 2 — book yield, investment income, duration / convexity
# ===========================================================================


# ---------------------------------------------------------------------------
# book_yield — gross IRR of carrying value vs cash flows
# ---------------------------------------------------------------------------


def test_book_yield_par_book_recovers_coupon_yield() -> None:
    """
    A par-priced annual-pay bond carried at par has book_yield = its coupon.

    From Slice 1, an annual-pay bond whose coupon equals the yield prices to
    par; so when carried at par (book == face) the IRR that equates discounted
    cash flows to the carrying value is exactly the coupon rate.
    """
    bond = Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=120)
    portfolio = AssetPortfolio(bonds=[bond])

    y = portfolio.book_yield()
    assert y is not None
    np.testing.assert_allclose(y, 0.05, rtol=1e-7)


def test_book_yield_zero_coupon_recovers_purchase_yield() -> None:
    """
    A zero carried at its discounted price recovers the discount yield.

    A 10-year zero on the engine convention has price face * (1 + y0)^(-N/12).
    Carried at that price, its IRR is exactly y0.
    """
    n_months = 120
    y0 = 0.04
    face = 1_000.0
    purchase_price = face * (1.0 + y0) ** (-n_months / 12.0)
    bond = Bond(
        face_value=face,
        coupon_rate=0.0,
        coupon_frequency=1,
        term_months=n_months,
        book_value=purchase_price,
    )
    portfolio = AssetPortfolio(bonds=[bond])

    y = portfolio.book_yield()
    assert y is not None
    np.testing.assert_allclose(y, y0, rtol=1e-7)


def test_book_yield_discount_bond_exceeds_coupon() -> None:
    """A bond carried below par yields more than its coupon (price < par)."""
    bond = Bond(face_value=1_000.0, coupon_rate=0.04, coupon_frequency=2, term_months=120)
    portfolio = AssetPortfolio(
        bonds=[
            bond,
            Bond(
                face_value=1_000.0,
                coupon_rate=0.04,
                coupon_frequency=2,
                term_months=120,
                book_value=900.0,
            ),
        ]
    )
    # The portfolio carrying value is below the sum of pars; book yield > coupon.
    y = portfolio.book_yield()
    assert y is not None
    assert y > 0.04


def test_book_yield_none_when_no_sign_change() -> None:
    """
    A portfolio carried at zero has no recoverable IRR in the bracket.

    Paying nothing for positive cash flows means the excess PV is positive at
    every yield in [-0.99, 100.0] — no sign change — so book_yield is None,
    mirroring ProfitTester's None-on-no-sign-change guard.
    """
    bond = Bond(
        face_value=1_000.0,
        coupon_rate=0.05,
        coupon_frequency=1,
        term_months=24,
        book_value=0.0,
    )
    portfolio = AssetPortfolio(bonds=[bond])
    assert portfolio.book_yield() is None


def test_book_yield_market_value_reconciles() -> None:
    """At the solved book yield, market value equals carrying value."""
    bonds = [
        Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=2, term_months=60),
        Bond(
            face_value=2_000.0,
            coupon_rate=0.03,
            coupon_frequency=4,
            term_months=120,
            book_value=1_850.0,
        ),
    ]
    portfolio = AssetPortfolio(bonds=bonds)
    y = portfolio.book_yield()
    assert y is not None
    np.testing.assert_allclose(portfolio.market_value(y), portfolio.book_value, rtol=1e-7)


# ---------------------------------------------------------------------------
# investment_income — reserve * yield / 12
# ---------------------------------------------------------------------------


def test_investment_income_explicit_yield_closed_form() -> None:
    """investment_income[t] = reserve[t] * yield / 12 on an explicit yield."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=24)]
    )
    reserves = np.array([100_000.0, 90_000.0, 80_000.0], dtype=np.float64)

    income = portfolio.investment_income(reserves, annual_yield=0.06)

    assert income.dtype == np.float64
    assert income.shape == (3,)
    np.testing.assert_allclose(income, reserves * 0.06 / 12.0)


def test_investment_income_uses_book_yield_when_unspecified() -> None:
    """With no explicit yield, investment income uses the portfolio book yield."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=1, term_months=120)]
    )
    reserves = np.full(12, 50_000.0, dtype=np.float64)

    income = portfolio.investment_income(reserves)

    # Par book → book_yield == coupon (0.05).
    np.testing.assert_allclose(income, reserves * 0.05 / 12.0, rtol=1e-7)


def test_investment_income_raises_without_recoverable_yield() -> None:
    """investment_income raises if no yield given and book_yield is None."""
    portfolio = AssetPortfolio(
        bonds=[
            Bond(
                face_value=1_000.0,
                coupon_rate=0.05,
                coupon_frequency=1,
                term_months=24,
                book_value=0.0,
            )
        ]
    )
    with pytest.raises(PolarisComputationError):
        portfolio.investment_income(np.ones(3, dtype=np.float64))


# ---------------------------------------------------------------------------
# Macaulay / modified duration and convexity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_months", [12, 60, 120, 240])
def test_macaulay_duration_of_zero_is_its_term(n_months: int) -> None:
    """A zero's Macaulay duration equals its term in years, at any yield."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.0, coupon_frequency=1, term_months=n_months)]
    )
    np.testing.assert_allclose(portfolio.macaulay_duration(0.04), n_months / 12.0, rtol=1e-9)


def test_modified_duration_is_macaulay_over_one_plus_yield() -> None:
    """Modified duration = Macaulay / (1 + y) under the effective-annual yield."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.05, coupon_frequency=2, term_months=120)]
    )
    y = 0.045
    np.testing.assert_allclose(
        portfolio.modified_duration(y),
        portfolio.macaulay_duration(y) / (1.0 + y),
        rtol=1e-12,
    )


def test_convexity_of_zero_matches_textbook() -> None:
    """A zero maturing in N years has convexity N(N+1)/(1+y)^2 (years²)."""
    n_years = 10.0
    y = 0.04
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.0, coupon_frequency=1, term_months=120)]
    )
    expected = n_years * (n_years + 1.0) / (1.0 + y) ** 2
    np.testing.assert_allclose(portfolio.convexity(y), expected, rtol=1e-9)


def test_coupon_bond_duration_below_maturity() -> None:
    """A coupon-paying bond has Macaulay duration strictly below its maturity."""
    portfolio = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.06, coupon_frequency=2, term_months=120)]
    )
    mac = portfolio.macaulay_duration(0.05)
    assert 0.0 < mac < 10.0


def test_duration_is_pv_weighted_across_portfolio() -> None:
    """
    A two-bond portfolio's Macaulay duration is the price-weighted average of
    the constituents' durations (the defining property of duration additivity).
    """
    short = Bond(face_value=1_000.0, coupon_rate=0.04, coupon_frequency=2, term_months=24)
    long = Bond(face_value=1_000.0, coupon_rate=0.04, coupon_frequency=2, term_months=240)
    y = 0.04
    p_short = AssetPortfolio(bonds=[short])
    p_long = AssetPortfolio(bonds=[long])
    p_both = AssetPortfolio(bonds=[short, long])

    price_s = short.price(y)
    price_l = long.price(y)
    expected = (p_short.macaulay_duration(y) * price_s + p_long.macaulay_duration(y) * price_l) / (
        price_s + price_l
    )

    np.testing.assert_allclose(p_both.macaulay_duration(y), expected, rtol=1e-9)


def test_convexity_exceeds_for_longer_bond() -> None:
    """Convexity rises with maturity — a longer zero is more convex."""
    short = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.0, coupon_frequency=1, term_months=60)]
    )
    long = AssetPortfolio(
        bonds=[Bond(face_value=1_000.0, coupon_rate=0.0, coupon_frequency=1, term_months=240)]
    )
    assert long.convexity(0.04) > short.convexity(0.04)

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

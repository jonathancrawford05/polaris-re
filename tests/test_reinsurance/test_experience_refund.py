"""
ExperienceRefund model + computation primitive tests (Slice 3a).

The experience refund settles a share of the accumulated favourable experience
back to the cedant. The experience account is built from the ceded cash flows,
net of any expense allowance already paid and the reinsurer's retained margin,
and may be accumulated at interest. These tests verify:
1. Closed-form experience-account balance and refund (with and without interest).
2. The retention threshold and the reinsurer-margin charge.
3. Non-negativity (unfavourable experience refunds nothing).
4. Validation of mismatched shapes / field ranges and edge cases.
"""

import numpy as np
import pytest
from pydantic import ValidationError

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.reinsurance.experience_refund import ExperienceRefund

# ----------------------------------------------------------------------
# Experience-account balance — closed form
# ----------------------------------------------------------------------


def test_balance_simple_sum_no_interest():
    """Balance with no interest is Σ(premium - claims) when margin/allowance are 0."""
    refund = ExperienceRefund(refund_pct=0.5)
    premiums = np.full(12, 1_000.0, dtype=np.float64)  # 12,000 total
    claims = np.full(12, 600.0, dtype=np.float64)  # 7,200 total

    # 12,000 - 7,200 = 4,800 favourable.
    np.testing.assert_allclose(refund.experience_balance(premiums, claims), 4_800.0)


def test_balance_nets_allowance_and_margin():
    """Allowance and reinsurer margin both reduce the favourable balance."""
    refund = ExperienceRefund(refund_pct=0.5, reinsurer_margin_pct=0.10)
    premiums = np.full(12, 1_000.0, dtype=np.float64)  # 12,000
    claims = np.full(12, 500.0, dtype=np.float64)  # 6,000
    allowances = np.full(12, 50.0, dtype=np.float64)  # 600

    # 12,000 - 6,000 - 600 - 0.10*12,000 = 12,000 - 6,000 - 600 - 1,200 = 4,200.
    np.testing.assert_allclose(refund.experience_balance(premiums, claims, allowances), 4_200.0)


def test_balance_accumulates_at_interest():
    """Two annual contributions of 100 at 10% → 100*1.1 + 100 = 210."""
    refund = ExperienceRefund(refund_pct=1.0, interest_rate=0.10, months_per_year=1)
    premiums = np.array([100.0, 100.0], dtype=np.float64)
    claims = np.zeros(2, dtype=np.float64)

    # Period 0 accumulates one year (x1.1), period 1 is at the settlement point.
    np.testing.assert_allclose(refund.experience_balance(premiums, claims), 210.0)


def test_balance_can_be_negative():
    """Unfavourable experience (claims > premium) yields a negative balance."""
    refund = ExperienceRefund(refund_pct=0.5)
    premiums = np.full(6, 1_000.0, dtype=np.float64)  # 6,000
    claims = np.full(6, 1_500.0, dtype=np.float64)  # 9,000

    np.testing.assert_allclose(refund.experience_balance(premiums, claims), -3_000.0)


# ----------------------------------------------------------------------
# Refund — closed form
# ----------------------------------------------------------------------


def test_refund_is_share_of_favourable_balance():
    """50% of a 4,800 favourable balance (no retention) → 2,400."""
    refund = ExperienceRefund(refund_pct=0.5)
    premiums = np.full(12, 1_000.0, dtype=np.float64)
    claims = np.full(12, 600.0, dtype=np.float64)

    np.testing.assert_allclose(refund.compute_refund(premiums, claims), 2_400.0)


def test_refund_applies_retention_first():
    """Retention is subtracted before sharing: 0.5*(4,800 - 1,000) = 1,900."""
    refund = ExperienceRefund(refund_pct=0.5, retention=1_000.0)
    premiums = np.full(12, 1_000.0, dtype=np.float64)
    claims = np.full(12, 600.0, dtype=np.float64)

    np.testing.assert_allclose(refund.compute_refund(premiums, claims), 1_900.0)


def test_refund_zero_when_balance_below_retention():
    """A favourable balance below the retention refunds nothing."""
    refund = ExperienceRefund(refund_pct=0.5, retention=10_000.0)
    premiums = np.full(12, 1_000.0, dtype=np.float64)  # balance 4,800 < 10,000
    claims = np.full(12, 600.0, dtype=np.float64)

    np.testing.assert_allclose(refund.compute_refund(premiums, claims), 0.0)


def test_refund_zero_on_unfavourable_experience():
    """A negative (unfavourable) balance refunds nothing — cedant never pays in."""
    refund = ExperienceRefund(refund_pct=0.5)
    premiums = np.full(6, 1_000.0, dtype=np.float64)
    claims = np.full(6, 1_500.0, dtype=np.float64)  # balance -3,000

    np.testing.assert_allclose(refund.compute_refund(premiums, claims), 0.0)


def test_refund_scales_linearly_with_refund_pct():
    """The refund is linear in refund_pct above the retention."""
    premiums = np.full(12, 1_000.0, dtype=np.float64)
    claims = np.full(12, 600.0, dtype=np.float64)
    r1 = ExperienceRefund(refund_pct=0.25).compute_refund(premiums, claims)
    r2 = ExperienceRefund(refund_pct=0.50).compute_refund(premiums, claims)
    np.testing.assert_allclose(r2, r1 * 2.0)


def test_refund_with_interest_closed_form():
    """Interest accumulation flows through to the refund."""
    refund = ExperienceRefund(refund_pct=0.5, interest_rate=0.10, months_per_year=1)
    premiums = np.array([100.0, 100.0], dtype=np.float64)
    claims = np.zeros(2, dtype=np.float64)
    # Balance 210 (see balance test) → 0.5*210 = 105.
    np.testing.assert_allclose(refund.compute_refund(premiums, claims), 105.0)


@pytest.mark.parametrize(
    ("margin_pct", "expected_refund"),
    [
        (0.0, 2_400.0),  # 0.5*(12,000 - 7,200)
        (0.10, 1_800.0),  # 0.5*(12,000 - 7,200 - 1,200)
        (0.20, 1_200.0),  # 0.5*(12,000 - 7,200 - 2,400)
    ],
)
def test_refund_sensitivity_to_margin(margin_pct, expected_refund):
    """The reinsurer margin reduces the sharable balance pound-for-pound."""
    refund = ExperienceRefund(refund_pct=0.5, reinsurer_margin_pct=margin_pct)
    premiums = np.full(12, 1_000.0, dtype=np.float64)
    claims = np.full(12, 600.0, dtype=np.float64)
    np.testing.assert_allclose(refund.compute_refund(premiums, claims), expected_refund)


# ----------------------------------------------------------------------
# Edge cases & validation
# ----------------------------------------------------------------------


def test_empty_arrays_refund_zero():
    """Zero-length cash flows produce a zero balance and zero refund."""
    refund = ExperienceRefund(refund_pct=0.5)
    empty = np.array([], dtype=np.float64)
    np.testing.assert_allclose(refund.experience_balance(empty, empty), 0.0)
    np.testing.assert_allclose(refund.compute_refund(empty, empty), 0.0)


def test_no_interest_default_matches_simple_sum():
    """interest_rate defaults to 0 → balance equals the undiscounted contribution sum."""
    refund = ExperienceRefund(refund_pct=1.0)
    premiums = np.array([100.0, 200.0, 300.0], dtype=np.float64)
    claims = np.array([10.0, 20.0, 30.0], dtype=np.float64)
    contributions = premiums - claims
    np.testing.assert_allclose(refund.experience_balance(premiums, claims), contributions.sum())


def test_mismatched_claims_shape_raises():
    refund = ExperienceRefund(refund_pct=0.5)
    premiums = np.full(12, 1_000.0, dtype=np.float64)
    claims = np.full(6, 600.0, dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="ceded_claims shape"):
        refund.experience_balance(premiums, claims)


def test_mismatched_allowance_shape_raises():
    refund = ExperienceRefund(refund_pct=0.5)
    premiums = np.full(12, 1_000.0, dtype=np.float64)
    claims = np.full(12, 600.0, dtype=np.float64)
    allowances = np.full(6, 50.0, dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="allowances shape"):
        refund.experience_balance(premiums, claims, allowances)


def test_non_1d_premiums_raises():
    refund = ExperienceRefund(refund_pct=0.5)
    premiums = np.ones((3, 4), dtype=np.float64)
    claims = np.ones((3, 4), dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="must be 1-D"):
        refund.experience_balance(premiums, claims)


@pytest.mark.parametrize("bad_pct", [-0.1, 1.1])
def test_refund_pct_out_of_range_rejected(bad_pct):
    with pytest.raises(ValidationError):
        ExperienceRefund(refund_pct=bad_pct)


def test_negative_retention_rejected():
    with pytest.raises(ValidationError):
        ExperienceRefund(refund_pct=0.5, retention=-1.0)


@pytest.mark.parametrize("bad_margin", [-0.1, 1.1])
def test_reinsurer_margin_out_of_range_rejected(bad_margin):
    with pytest.raises(ValidationError):
        ExperienceRefund(refund_pct=0.5, reinsurer_margin_pct=bad_margin)


def test_negative_interest_rate_rejected():
    with pytest.raises(ValidationError):
        ExperienceRefund(refund_pct=0.5, interest_rate=-0.01)


def test_zero_months_per_year_rejected():
    with pytest.raises(ValidationError):
        ExperienceRefund(refund_pct=0.5, months_per_year=0)

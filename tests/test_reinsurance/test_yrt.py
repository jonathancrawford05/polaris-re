"""
YRT treaty tests.

KEY INVARIANT TO VERIFY FOR ALL TESTS:
    net_cashflow + ceded_cashflow == gross_cashflow (for premiums and claims)

All monetary assertions use np.testing.assert_allclose(rtol=1e-5).
"""

import pytest

pytestmark = pytest.mark.xfail(
    reason="YRTTreaty.apply() not yet implemented.",
    strict=False,
)


class TestYRTTreaty:
    def test_additivity_premiums(self):
        """net premiums + ceded premiums must equal gross premiums."""
        pytest.skip("Requires TermLife projection — implement after Milestone 1.3")

    def test_additivity_claims(self):
        """net claims + ceded claims must equal gross claims."""
        pytest.skip("Requires TermLife projection")

    def test_reserves_not_transferred(self):
        """In YRT, reserves stay with cedant: net reserves == gross reserves."""
        pytest.skip("Requires TermLife projection")

    def test_nar_equals_face_minus_reserve(self):
        """
        CLOSED-FORM: For a new-business term policy (reserve ≈ 0 in year 1):
        NAR ≈ face_amount.
        ceded_premium ≈ face_amount * cession_pct * yrt_rate / 1000
        """
        pytest.skip("Requires TermLife projection")

    def test_zero_cession_pct_no_ceded_cashflows(self):
        """With cession_pct=0, ceded cashflows should all be zero."""
        pytest.skip("Requires TermLife projection")

    def test_full_cession_pct_net_equals_premium_minus_yrt(self):
        """With cession_pct=1.0, net = gross_premium - yrt_premium."""
        pytest.skip("Requires TermLife projection")

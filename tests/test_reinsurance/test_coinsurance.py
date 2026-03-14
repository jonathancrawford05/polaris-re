"""
Coinsurance treaty tests.

KEY INVARIANTS:
1. net + ceded == gross for all cash flow lines (premiums, claims, expenses, reserves)
2. Reserve transfer: ceded_reserve == gross_reserve * cession_pct at every time step
3. Net reserve == gross_reserve * (1 - cession_pct) at every time step
"""

import pytest

pytestmark = pytest.mark.xfail(
    reason="CoinsuranceTreaty.apply() not yet implemented.",
    strict=False,
)


class TestCoinsuranceTreaty:
    def test_additivity_all_lines(self):
        """net + ceded == gross for premiums, claims, expenses, reserves."""
        pytest.skip("Requires TermLife projection — implement after Milestone 1.3")

    def test_reserve_split_proportional(self):
        """
        CLOSED-FORM: 50% coinsurance → ceded reserve = 50% of gross reserve at all t.
        Net reserve = 50% of gross reserve at all t.
        """
        pytest.skip("Requires TermLife projection")

    def test_zero_cession_net_equals_gross(self):
        """With cession_pct=0, net == gross and ceded == 0 for all cash flows."""
        pytest.skip("Requires TermLife projection")

    def test_full_cession_net_all_zero(self):
        """With cession_pct=1.0, net cash flows are all zero, ceded == gross."""
        pytest.skip("Requires TermLife projection")

    def test_initial_reserve_transfer_cash_flow(self):
        """
        At t=0, cedant receives the initial reserve transfer (coinsurance allowance).
        This should appear as a positive cash flow in the net result at t=0.
        """
        pytest.skip("Requires TermLife projection")

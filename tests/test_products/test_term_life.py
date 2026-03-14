"""
Term Life projection tests.

CRITICAL: Every test in this file must include a closed-form verification —
a hand-calculable expected result that is hardcoded and asserted exactly.
Do not test implementation against itself.

Closed-form reference calculations are documented inline. These should be
verified independently by a credentialed actuary before deployment.
"""

import pytest
import numpy as np

# Tests are currently marked xfail because TermLife.project() is not yet implemented.
# Remove the xfail markers as each method is implemented.

pytestmark = pytest.mark.xfail(
    reason="TermLife projection engine not yet implemented.",
    strict=False,
)


class TestTermLifeProjection:
    """Closed-form verification of term life cash flow projection."""

    def test_single_policy_total_premiums(
        self, single_policy_block, standard_projection_config
    ):
        """
        CLOSED-FORM: For a 20-year term policy with $1,500 annual premium,
        if lapse rate = 0 and mortality is very low, total premiums should be
        approximately $1,500 * 20 = $30,000. With mortality and lapses,
        somewhat less.

        Hand calculation: sum(lx_t * monthly_premium) over 240 months.
        """
        from polaris_re.products.term_life import TermLife
        # TODO: requires a real AssumptionSet — inject a mock with known rates
        pytest.skip("Requires AssumptionSet fixture — implement after Milestone 1.2")

    def test_reserves_zero_at_expiry(
        self, single_policy_block, standard_projection_config
    ):
        """
        FUNDAMENTAL INVARIANT: Term life reserves must equal zero at policy expiry.
        V_T = 0 by construction (prospective method: no future benefits = 0 reserve).
        """
        from polaris_re.products.term_life import TermLife
        pytest.skip("Requires AssumptionSet fixture")

    def test_reserves_non_negative_throughout(
        self, single_policy_block, standard_projection_config
    ):
        """
        Net premium reserves must be non-negative for all t in [0, T].
        A negative reserve indicates a calculation error.
        """
        from polaris_re.products.term_life import TermLife
        pytest.skip("Requires AssumptionSet fixture")

    def test_lx_monotonically_decreasing(
        self, single_policy_block, standard_projection_config
    ):
        """
        In-force factors must be monotonically non-increasing:
        lx[:, t] <= lx[:, t-1] for all t.
        Policies can only leave (death or lapse), never re-enter.
        """
        from polaris_re.products.term_life import TermLife
        pytest.skip("Requires AssumptionSet fixture")

    def test_zero_lapse_zero_mortality_full_premiums(self):
        """
        CLOSED-FORM: With q=0 and w=0 for all t:
        - lx[:, t] = 1.0 for all t
        - total premiums = face * 20 (annual) summed monthly
        - total claims = 0
        This is the simplest verifiable case.
        """
        pytest.skip("Requires mock AssumptionSet with zero rates")

    def test_net_cash_flow_accounting_identity(
        self, single_policy_block, standard_projection_config
    ):
        """
        ACCOUNTING IDENTITY:
        net_cash_flow_t = gross_premiums_t - death_claims_t - expenses_t - reserve_increase_t

        Must hold exactly (to floating point precision) for all t.
        """
        from polaris_re.products.term_life import TermLife
        pytest.skip("Requires AssumptionSet fixture")

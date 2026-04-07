"""
Net Premium Calculator — classical equivalence-principle premium solver
parameterised by an arbitrary mortality basis.

Solves for the level annual premium ``P`` that equates the expected present
value (EPV) of future premiums to the EPV of future benefits under a
user-supplied ``MortalityTable`` and flat discount rate:

    Whole life:   P * ä_x          = FA * A_x
    n-year term:  P * ä_{x:n}      = FA * A^1_{x:n}

where

    A_x      = Σ_{t≥0} v^{t+1} · _t p_x · q_{x+t}           (EOY death benefit)
    ä_x      = Σ_{t≥0} v^{t}   · _t p_x                     (annuity-due of 1)
    _t p_x   = Π_{k<t} (1 - q_{x+k})

All annual rates are recovered from the (monthly) public
``MortalityTable.get_qx_vector`` API by compounding under the
constant-force assumption — lossless to float precision. Select-period
position is driven by the chosen basis age:

    basis_age="issue"    — price as a fresh select issue at ``issue_age``
                           (what a new quote would look like today)
    basis_age="attained" — price as a fresh select issue at ``attained_age``
                           (re-pricing an inforce life at today's age)

The calculator is pure-Python / numpy — no dependency on projection engines,
treaty logic, or profit testing. It is suitable for (a) priming the
``annual_premium`` column of synthetic inforce blocks with actuarially
consistent numbers, and (b) quick benchmark calculations against the
full projection stack.

Supported products: ``WHOLE_LIFE``, ``TERM``. All other product types raise
``PolarisValidationError`` — use the relevant projection engine instead.
"""

from typing import Literal

import numpy as np
from pydantic import Field

from polaris_re.assumptions.mortality import MortalityTable
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType

__all__ = ["NetPremiumCalculator", "NetPremiumResult"]


BasisAge = Literal["issue", "attained"]


class NetPremiumResult(PolarisBaseModel):
    """
    Immutable result of a single-policy net premium calculation.

    Attributes
    ----------
    policy_id:
        Identifier of the policy that was priced.
    basis_age:
        Which age was used as the pricing age ("issue" or "attained").
    pricing_age:
        The integer age corresponding to ``basis_age``.
    product_type:
        Product type string (WHOLE_LIFE or TERM).
    coverage_years:
        Number of years of coverage priced (omega - pricing_age + 1 for WL;
        policy_term for TERM).
    A_x:
        EPV of a $1 death benefit (end-of-year of death).
    a_due_x:
        EPV of a $1-per-year annuity-due of premium payments.
    net_rate_per_1:
        Level net annual premium expressed as a rate per $1 of face amount
        ( = A_x / a_due_x ). Multiply by face amount to get a dollar premium.
    net_rate_per_1000:
        Same, per $1,000 of face — the canonical reinsurance quotation unit.
    net_annual_premium:
        Level net annual premium in dollars ( = net_rate_per_1 * face_amount ).
    gross_annual_premium:
        ``net_annual_premium * (1 + expense_loading)``.
    discount_rate:
        Flat annual discount rate used.
    expense_loading:
        Multiplicative loading applied to net to produce gross.
    mortality_basis:
        Name of the mortality table that was used (e.g. "SOA VBT 2015").
    """

    policy_id: str
    basis_age: BasisAge
    pricing_age: int
    product_type: str
    coverage_years: int
    A_x: float = Field(ge=0.0, le=1.0)
    a_due_x: float = Field(gt=0.0)
    net_rate_per_1: float = Field(ge=0.0)
    net_rate_per_1000: float = Field(ge=0.0)
    net_annual_premium: float = Field(ge=0.0)
    gross_annual_premium: float = Field(ge=0.0)
    discount_rate: float
    expense_loading: float = Field(ge=0.0)
    mortality_basis: str


class NetPremiumCalculator:
    """
    Price whole-life and term policies via the equivalence principle against
    a user-supplied mortality basis.

    Parameters
    ----------
    mortality:
        Loaded ``MortalityTable`` (any supported source: CIA 2014,
        SOA VBT 2015, 2001 CSO, or a synthetic table built via
        ``MortalityTable.from_table_array``).
    discount_rate:
        Flat annual effective discount rate applied to all cash flows.
        Defaults to 4%.
    expense_loading:
        Multiplicative loading applied to the net premium to produce a
        gross premium ( gross = net * (1 + loading) ). Defaults to 0 (no
        loading → net premium equals gross premium).
    basis_age:
        "issue" (default) prices each policy as a fresh select issue at
        its issue age. "attained" prices it as a fresh select issue at
        the current attained age — useful for indicative re-pricing of
        an inforce life.
    terminal_age:
        Optional terminal age ω. At this age the calculator forces
        ``q = 1`` so the EPV sums are finite. Defaults to
        ``mortality.max_age``.

    Notes
    -----
    The calculator does not model lapses, expense cash flows other than a
    flat multiplicative loading, interest-sensitive cash values, or any
    policyholder-behaviour dynamics. It is a classical net-premium
    calculator, intended for benchmarking and for priming synthetic
    inforce files with consistent premium levels — not as a substitute
    for the full projection-engine pricing pipeline.
    """

    def __init__(
        self,
        mortality: MortalityTable,
        discount_rate: float = 0.04,
        expense_loading: float = 0.0,
        basis_age: BasisAge = "issue",
        terminal_age: int | None = None,
    ) -> None:
        if discount_rate <= -1.0:
            raise PolarisValidationError(f"discount_rate must be > -1, got {discount_rate}.")
        if expense_loading < 0.0:
            raise PolarisValidationError(f"expense_loading must be >= 0, got {expense_loading}.")
        if basis_age not in ("issue", "attained"):
            raise PolarisValidationError(
                f"basis_age must be 'issue' or 'attained', got {basis_age!r}."
            )

        self.mortality = mortality
        self.discount_rate = float(discount_rate)
        self.expense_loading = float(expense_loading)
        self.basis_age: BasisAge = basis_age
        self.terminal_age = int(terminal_age) if terminal_age is not None else mortality.max_age

        if self.terminal_age > mortality.max_age:
            raise PolarisValidationError(
                f"terminal_age {self.terminal_age} exceeds table max_age {mortality.max_age}."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def price(self, policy: Policy) -> NetPremiumResult:
        """Price a single policy. Dispatches on ``policy.product_type``."""
        if policy.product_type == ProductType.WHOLE_LIFE:
            return self._price_whole_life(policy)
        if policy.product_type == ProductType.TERM:
            return self._price_term(policy)
        raise PolarisValidationError(
            f"NetPremiumCalculator supports WHOLE_LIFE and TERM only; "
            f"got product_type={policy.product_type.value}. "
            f"Use the full projection engine for this product."
        )

    def price_block(self, block: InforceBlock) -> list[NetPremiumResult]:
        """Price every policy in an inforce block."""
        return [self.price(p) for p in block.policies]

    # ------------------------------------------------------------------
    # Core annual-rate extraction
    # ------------------------------------------------------------------

    def _annual_qx_curve(self, policy: Policy, pricing_age: int) -> np.ndarray:
        """
        Return annual mortality rates from ``pricing_age`` through ``terminal_age``.

        The policy is treated as a fresh select issue at ``pricing_age``:
        duration 0 in the select table, advancing one year per entry until
        the ultimate column is reached. The final entry is forced to 1.0
        so survivorship sums terminate cleanly.
        """
        ages = np.arange(pricing_age, self.terminal_age + 1, dtype=np.int32)
        # Duration at start of each year, expressed in months, measured from
        # pricing_age. get_qx_vector divides by 12 internally to look up the
        # correct select column.
        durations_months = (ages - pricing_age) * 12
        durations_months = durations_months.astype(np.int32)

        q_monthly = self.mortality.get_qx_vector(
            ages=ages,
            sex=policy.sex,
            smoker_status=policy.smoker_status,
            durations=durations_months,
        )
        # Round-trip monthly → annual under constant force. This is an
        # identity operation to within float precision, so using the
        # public (monthly) API is lossless.
        q_annual = 1.0 - np.power(1.0 - q_monthly, 12.0)

        # Force terminal q = 1 so the tail is finite.
        q_annual = q_annual.copy()
        q_annual[-1] = 1.0
        # Defensive: clip anything that drifted numerically.
        return np.clip(q_annual, 0.0, 1.0)

    # ------------------------------------------------------------------
    # Product-specific pricing
    # ------------------------------------------------------------------

    def _resolve_pricing_age(self, policy: Policy) -> int:
        """Return the integer age at which to price, per the configured basis."""
        if self.basis_age == "issue":
            return policy.issue_age
        return policy.attained_age

    def _price_whole_life(self, policy: Policy) -> NetPremiumResult:
        pricing_age = self._resolve_pricing_age(policy)
        if pricing_age > self.terminal_age:
            raise PolarisValidationError(
                f"Pricing age {pricing_age} exceeds terminal age {self.terminal_age}; "
                f"cannot price policy {policy.policy_id}."
            )

        q = self._annual_qx_curve(policy, pricing_age)
        A_x, a_due = _compute_epvs(q, self.discount_rate)  # noqa: N806
        return self._build_result(
            policy=policy,
            pricing_age=pricing_age,
            coverage_years=len(q),
            A_x=A_x,
            a_due=a_due,
        )

    def _price_term(self, policy: Policy) -> NetPremiumResult:
        if policy.policy_term is None:
            raise PolarisValidationError(f"TERM policy {policy.policy_id} has no policy_term set.")
        pricing_age = self._resolve_pricing_age(policy)
        n = int(policy.policy_term)
        max_possible = self.terminal_age - pricing_age + 1
        if n > max_possible:
            raise PolarisValidationError(
                f"Policy term {n}y exceeds available coverage years "
                f"{max_possible} at pricing age {pricing_age} (terminal age "
                f"{self.terminal_age})."
            )

        # Truncate the WL curve to n years. The final entry within the
        # truncation window is NOT forced to 1 — a term policy that
        # survives to the end simply expires, carrying no benefit.
        full = self._annual_qx_curve(policy, pricing_age)
        q = full[:n].copy()
        # The final year's q should be the native annual rate, not 1.
        # If n equals the full WL horizon we keep the forced terminal.
        if n < len(full):
            # Recover the un-forced annual q at (pricing_age + n - 1) by
            # re-reading from the table — cheap and avoids any
            # ambiguity with the terminal clamp.
            age = np.array([pricing_age + n - 1], dtype=np.int32)
            dur = np.array([(n - 1) * 12], dtype=np.int32)
            q_m = self.mortality.get_qx_vector(
                ages=age,
                sex=policy.sex,
                smoker_status=policy.smoker_status,
                durations=dur,
            )[0]
            q[-1] = float(1.0 - (1.0 - q_m) ** 12)

        A_x, a_due = _compute_epvs(q, self.discount_rate)  # noqa: N806
        return self._build_result(
            policy=policy,
            pricing_age=pricing_age,
            coverage_years=n,
            A_x=A_x,
            a_due=a_due,
        )

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def _build_result(
        self,
        *,
        policy: Policy,
        pricing_age: int,
        coverage_years: int,
        A_x: float,  # noqa: N803
        a_due: float,
    ) -> NetPremiumResult:
        if a_due <= 0.0:
            raise PolarisValidationError(
                f"Degenerate annuity-due (ä_x = {a_due}) for policy {policy.policy_id}."
            )
        net_rate = A_x / a_due
        net_prem = net_rate * policy.face_amount
        gross_prem = net_prem * (1.0 + self.expense_loading)
        return NetPremiumResult(
            policy_id=policy.policy_id,
            basis_age=self.basis_age,
            pricing_age=pricing_age,
            product_type=policy.product_type.value,
            coverage_years=coverage_years,
            A_x=float(A_x),
            a_due_x=float(a_due),
            net_rate_per_1=float(net_rate),
            net_rate_per_1000=float(net_rate * 1_000.0),
            net_annual_premium=float(net_prem),
            gross_annual_premium=float(gross_prem),
            discount_rate=self.discount_rate,
            expense_loading=self.expense_loading,
            mortality_basis=self.mortality.table_name,
        )


# ----------------------------------------------------------------------
# Stateless numerical core — exposed at module level for unit testing.
# ----------------------------------------------------------------------


def _compute_epvs(q_annual: np.ndarray, discount_rate: float) -> tuple[float, float]:
    """
    Compute (A_x, ä_x) for a one-dimensional annual mortality curve.

    Args:
        q_annual:      Annual mortality rates starting at the pricing age.
                       Shape (n,). The final entry should typically be 1
                       (whole-life terminal clamp) or the native annual
                       rate at the last coverage year (n-year term).
        discount_rate: Flat annual effective discount rate.

    Returns:
        (A_x, a_due_x) — EPV of a $1 end-of-year death benefit and EPV of
        a $1/yr annuity-due paid at the start of each coverage year.
    """
    if q_annual.ndim != 1 or q_annual.size == 0:
        raise PolarisValidationError("q_annual must be a non-empty 1-D array.")
    v = 1.0 / (1.0 + discount_rate)
    # _t p_x: probability of surviving from the pricing age to the start
    # of year t (so _0 p_x = 1).
    surv = np.concatenate([[1.0], np.cumprod(1.0 - q_annual)[:-1]])
    t = np.arange(q_annual.size, dtype=np.float64)
    A_x = float(np.sum(v ** (t + 1.0) * surv * q_annual))  # noqa: N806
    a_due = float(np.sum(v**t * surv))
    return A_x, a_due

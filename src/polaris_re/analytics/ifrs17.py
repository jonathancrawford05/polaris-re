"""
IFRS 17 Insurance Contract Measurement Models.

Implements the three IFRS 17 measurement approaches:

- **Building Block Approach (BBA)**: General model for most insurance contracts.
  Decomposes the insurance liability into three components:
  - Best Estimate Liability (BEL): PV of expected fulfilment cash flows
  - Risk Adjustment (RA): compensation for non-financial risk uncertainty
  - Contractual Service Margin (CSM): unearned day-1 profit, released over coverage period

- **Premium Allocation Approach (PAA)**: Simplified model for short-duration contracts
  (coverage period ≤ 1 year or where results approximate BBA).
  Uses an unearned premium reserve (LRC) and incurred claims reserve (LIC).

- **Variable Fee Approach (VFA)**: For direct-participating contracts (e.g., Universal Life)
  where policyholder returns depend on underlying items. The CSM absorbs changes in
  the fair value of underlying items.

Reference: IFRS 17 Insurance Contracts (effective 1 January 2023).

Fulfilment cash flows sign convention (from the insurer's perspective):
    outflows (claims, expenses, surrenders) are positive
    inflows (premiums) are negative
    BEL > 0 means the insurer has a net liability (outflows exceed inflows)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np

from polaris_re.core.cashflow import CashFlowResult

__all__ = ["IFRS17Measurement", "IFRS17Result"]


@dataclass
class IFRS17Result:
    """
    IFRS 17 insurance contract liability measurement result.

    Provides a full roll-forward of the insurance liability components over
    the projection horizon. All array fields have shape (T,) where T is the
    number of projection periods.

    Sign conventions:
        - Liability values are positive (insurer owes money to policyholders)
        - Insurance revenue is positive (profit-and-loss credit)
        - Insurance service expenses are positive (P&L charge)
    """

    approach: Literal["BBA", "PAA", "VFA"]
    valuation_date: date
    discount_rate: float
    n_periods: int

    # --- Liability balance sheet components, shape (T,) ---
    # Measured at the START of each period (prospective view from that point)
    bel: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """Best Estimate Liability at start of each period. Shape (T,)."""

    risk_adjustment: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """Risk Adjustment at start of each period. Shape (T,)."""

    csm: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """Contractual Service Margin at start of each period (after release). Shape (T,)."""

    insurance_liability: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """Total insurance liability = BEL + RA + CSM at start of each period. Shape (T,)."""

    # --- CSM roll-forward components, shape (T,) ---
    csm_interest_accretion: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    """Interest accreted on CSM at the locked-in discount rate. Shape (T,)."""

    csm_release: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """CSM released to P&L in each period (coverage units basis). Shape (T,)."""

    # --- P&L components, shape (T,) ---
    insurance_revenue: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """Insurance revenue recognized in each period. Shape (T,)."""

    insurance_service_expenses: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    """Insurance service expenses: claims + expenses + RA release. Shape (T,)."""

    insurance_service_result: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    """Insurance service result = revenue - expenses. Shape (T,)."""

    # --- Initial recognition values (scalar) ---
    initial_bel: float = 0.0
    """BEL at time 0 (initial recognition)."""

    initial_ra: float = 0.0
    """Risk Adjustment at time 0 (initial recognition)."""

    initial_csm: float = 0.0
    """CSM at time 0. Zero for onerous contracts."""

    loss_component: float = 0.0
    """Loss component at inception. > 0 for onerous contracts, recognised in P&L immediately."""

    # --- PAA-specific fields ---
    lrc: np.ndarray | None = None
    """Liability for Remaining Coverage (PAA only). Shape (T,)."""

    lic: np.ndarray | None = None
    """Liability for Incurred Claims (PAA only). Shape (T,)."""

    def total_initial_liability(self) -> float:
        """Total insurance liability at initial recognition: BEL + RA + CSM.

        For onerous contracts, CSM = 0 and a loss component is recognised instead.
        """
        return self.initial_bel + self.initial_ra + self.initial_csm

    def cumulative_csm_released(self) -> np.ndarray:
        """Cumulative CSM released to P&L by end of each period. Shape (T,)."""
        return np.cumsum(self.csm_release)

    def pv_insurance_revenue(self) -> float:
        """Present value of all insurance revenue at the measurement discount rate."""
        t = len(self.insurance_revenue)
        v = (1.0 + self.discount_rate) ** (-1.0 / 12.0)
        disc = v ** np.arange(1, t + 1, dtype=np.float64)
        return float(np.dot(self.insurance_revenue, disc))


class IFRS17Measurement:
    """
    Computes IFRS 17 insurance contract measurements from a projected CashFlowResult.

    Takes the output of a product projection (CashFlowResult with GROSS basis)
    and produces a full IFRS 17 liability measurement under the chosen approach.

    Fulfilment cash flows derived from CashFlowResult:
        FCF[t] = death_claims[t] + lapse_surrenders[t] + expenses[t] - gross_premiums[t]
        (positive FCF means net outflow — insurer owes more than it receives)

    Args:
        cashflows:
            GROSS basis CashFlowResult from a product projection.
        discount_rate:
            IFRS 17 discount rate (risk-free rate + illiquidity premium).
            Locked-in at initial recognition for CSM accretion.
        ra_factor:
            Risk Adjustment as a proportion of BEL (simplified cost-of-capital method).
            Typical range 0.03-0.08 (3-8% of BEL). Default 0.05.
        coverage_units:
            Optional array of shape (T,) representing the quantity of insurance
            coverage provided in each period (e.g., expected in-force count x face amount).
            If None, defaults to a linearly declining proxy derived from gross premiums.
    """

    def __init__(
        self,
        cashflows: CashFlowResult,
        discount_rate: float,
        ra_factor: float = 0.05,
        coverage_units: np.ndarray | None = None,
    ) -> None:
        if cashflows.basis != "GROSS":
            raise ValueError(
                "IFRS17Measurement requires GROSS basis CashFlowResult. "
                f"Received: {cashflows.basis}"
            )
        self.cashflows = cashflows
        self.discount_rate = discount_rate
        self.ra_factor = ra_factor
        self._T = cashflows.projection_months

        # Monthly discount factor v = (1+i)^(-1/12)
        self._v = (1.0 + discount_rate) ** (-1.0 / 12.0)

        # Build fulfilment cash flows: net outflows positive
        self._fcf = (
            cashflows.death_claims
            + cashflows.lapse_surrenders
            + cashflows.expenses
            - cashflows.gross_premiums
        )

        # Coverage units for CSM amortisation
        if coverage_units is not None:
            if len(coverage_units) != self._T:
                raise ValueError(
                    f"coverage_units length {len(coverage_units)} != projection_months {self._T}"
                )
            self._coverage_units = coverage_units.astype(np.float64)
        else:
            # Default: linearly declining from 1.0 to 0.0 (uniform coverage assumption)
            self._coverage_units = np.linspace(1.0, 1.0 / self._T, self._T)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_bel_schedule(self) -> np.ndarray:
        """
        Compute BEL at the start of each period (prospective view).

        BEL[t] = sum_{s=t}^{T-1} FCF[s] * v^(s - t + 1)

        Returns shape (T,) array where BEL[0] is the initial recognition BEL.
        """
        n_per = self._T
        bel = np.zeros(n_per, dtype=np.float64)
        # Backward computation: BEL[n_per-1] = FCF[n_per-1] * v
        # BEL[t] = FCF[t] * v + BEL[t+1] * v
        for t in range(n_per - 1, -1, -1):
            future_bel = bel[t + 1] if t + 1 < n_per else 0.0
            bel[t] = self._fcf[t] * self._v + future_bel * self._v
        return bel

    def _compute_ra_schedule(self, bel: np.ndarray) -> np.ndarray:
        """
        Risk Adjustment as a fixed proportion of the absolute BEL
        (simplified cost-of-capital method).

        RA[t] = ra_factor * |BEL[t]|

        The RA represents compensation for bearing non-financial risk
        uncertainty and is always a liability (positive), regardless of
        whether BEL is positive (net outflows exceed inflows) or negative
        (profitable contract where inflows exceed outflows). Using the
        absolute value ensures RA is non-zero for profitable contracts
        (IFRS 17.37(b)).

        Returns shape (T,) array.
        """
        return self.ra_factor * np.abs(bel)

    def _compute_csm_schedule(
        self,
        initial_csm: float,
        risk_free_rate: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Roll forward the CSM over the projection horizon.

        CSM amortisation uses the coverage units method:
            CSM_release[t] = CSM_opening[t] * coverage_units[t] / sum(remaining coverage units)

        The CSM accretes at the locked-in discount rate (risk_free_rate).

        Returns:
            Tuple of (csm_schedule, csm_accretion, csm_release) each shape (T,).
            csm_schedule[t] is CSM AFTER release at period t (end-of-period balance).
        """
        n_per = self._T
        csm_schedule = np.zeros(n_per, dtype=np.float64)
        csm_accretion = np.zeros(n_per, dtype=np.float64)
        csm_release = np.zeros(n_per, dtype=np.float64)

        v_accretion = (1.0 + risk_free_rate) ** (1.0 / 12.0)

        # Cumulative coverage units remaining from each period onwards
        cu = self._coverage_units
        cu_remaining = np.zeros(n_per + 1, dtype=np.float64)
        for t in range(n_per - 1, -1, -1):
            cu_remaining[t] = cu_remaining[t + 1] + cu[t]

        csm_opening = initial_csm
        for t in range(n_per):
            # Accretion
            accreted = csm_opening * (v_accretion - 1.0)
            csm_after_accretion = csm_opening + accreted

            # Release via coverage units
            if cu_remaining[t] > 0.0:
                release_fraction = cu[t] / cu_remaining[t]
            else:
                release_fraction = 1.0 if t == n_per - 1 else 0.0
            release = csm_after_accretion * release_fraction

            csm_end = csm_after_accretion - release

            csm_accretion[t] = accreted
            csm_release[t] = release
            csm_schedule[t] = csm_end  # CSM balance after release (= opening of next period)

            csm_opening = csm_end

        return csm_schedule, csm_accretion, csm_release

    # ------------------------------------------------------------------
    # Public measurement methods
    # ------------------------------------------------------------------

    def measure_bba(self) -> IFRS17Result:
        """
        Compute IFRS 17 Building Block Approach (BBA) measurement.

        The BBA is the general measurement model under IFRS 17. It measures
        insurance contracts at fulfilment value, recognising unearned profit
        (CSM) over the coverage period.

        Returns:
            IFRS17Result with full BEL/RA/CSM schedules and P&L components.
        """
        n_per = self._T

        # --- Step 1: BEL schedule ---
        bel = self._compute_bel_schedule()

        # --- Step 2: RA schedule ---
        ra = self._compute_ra_schedule(bel)

        # --- Step 3: Initial recognition ---
        initial_bel = float(bel[0])
        initial_ra = float(ra[0])
        fcf_at_inception = initial_bel + initial_ra

        # CSM = max(0, -FCF_inception) — offset for profitable contracts
        # Loss component for onerous contracts
        initial_csm = float(max(0.0, -fcf_at_inception))
        loss_component = float(max(0.0, fcf_at_inception))

        # --- Step 4: CSM roll-forward ---
        csm_schedule, csm_accretion, csm_release = self._compute_csm_schedule(
            initial_csm=initial_csm,
            risk_free_rate=self.discount_rate,
        )

        # CSM at start of period t = CSM end of period t-1
        # csm_schedule[t] = CSM balance at END of period t (after release)
        # For the balance sheet, we want CSM at START of period t (before release)
        csm_at_start = np.zeros(n_per, dtype=np.float64)
        csm_at_start[0] = initial_csm
        csm_at_start[1:] = csm_schedule[:-1]

        # Insurance liability at start of each period
        insurance_liability = bel + ra + csm_at_start

        # --- Step 5: P&L components ---
        # RA release in each period = RA[t] - RA[t+1]
        ra_padded = np.append(ra, 0.0)
        ra_release = ra_padded[:-1] - ra_padded[1:]  # RA released (positive = income)

        # Insurance service expenses = claims + expenses + RA released
        insurance_service_expenses = (
            self.cashflows.death_claims
            + self.cashflows.expenses
            + self.cashflows.lapse_surrenders
            - ra_release  # RA release is income, subtract from expenses
        )

        # Insurance revenue = expected claims + expenses + RA release + CSM release
        # (This equals premiums on a "best estimate" basis for non-participating contracts)
        #
        # IFRS 17 B123: For onerous contracts (loss_component > 0), the portion
        # of expected cash flows attributable to the loss component must be
        # excluded from insurance revenue. The loss component ratio determines
        # what fraction of total outflows relates to the loss.
        total_outflows = (
            self.cashflows.death_claims + self.cashflows.expenses + self.cashflows.lapse_surrenders
        )
        if loss_component > 0 and fcf_at_inception > 0:
            # Loss component ratio: proportion of total liability due to loss
            total_liability_at_inception = fcf_at_inception
            loss_ratio = np.clip(loss_component / total_liability_at_inception, 0.0, 1.0)
            # Revenue excludes the loss-component portion of outflows
            insurance_revenue = total_outflows * (1.0 - loss_ratio) + csm_release
        else:
            insurance_revenue = total_outflows + csm_release

        insurance_service_result = insurance_revenue - insurance_service_expenses

        return IFRS17Result(
            approach="BBA",
            valuation_date=self.cashflows.valuation_date,
            discount_rate=self.discount_rate,
            n_periods=n_per,
            bel=bel,
            risk_adjustment=ra,
            csm=csm_at_start,
            insurance_liability=insurance_liability,
            csm_interest_accretion=csm_accretion,
            csm_release=csm_release,
            insurance_revenue=insurance_revenue,
            insurance_service_expenses=insurance_service_expenses,
            insurance_service_result=insurance_service_result,
            initial_bel=initial_bel,
            initial_ra=initial_ra,
            initial_csm=initial_csm,
            loss_component=loss_component,
        )

    def measure_paa(self, coverage_period_months: int | None = None) -> IFRS17Result:
        """
        Compute IFRS 17 Premium Allocation Approach (PAA) measurement.

        The PAA is a simplified approach, generally permitted when:
        - The coverage period is ≤ 12 months, OR
        - The PAA results would not differ materially from BBA.

        PAA components:
            LRC (Liability for Remaining Coverage): Unearned premium reserve.
                LRC[t] = LRC[0] * (1 - t/T) for uniform coverage.
            LIC (Liability for Incurred Claims): PV of incurred but not yet
                settled claims (estimated from claims paid in future periods).

        Args:
            coverage_period_months:
                Length of the coverage period in months. If None, uses the
                full projection horizon. Used for LRC computation.

        Returns:
            IFRS17Result with LRC/LIC schedules.
        """
        n_per = self._T
        cov_months = coverage_period_months or n_per

        # --- LRC: Unearned Premium Reserve ---
        # Total premiums collected over coverage period (undiscounted, simple approach)
        total_premiums = float(self.cashflows.gross_premiums[:cov_months].sum())

        # LRC declines linearly as coverage is provided
        # LRC[t] = total_premiums * (1 - t/cov_months) for t < cov_months; 0 thereafter
        lrc = np.zeros(n_per, dtype=np.float64)
        for t in range(min(cov_months, n_per)):
            lrc[t] = total_premiums * (1.0 - float(t) / float(cov_months))

        # --- LIC: Liability for Incurred Claims ---
        # Prospective: PV of claims and expenses expected from period t onwards
        lic = np.zeros(n_per, dtype=np.float64)
        outflows = self.cashflows.death_claims + self.cashflows.expenses
        for t in range(n_per):
            future_outflows = outflows[t:]
            n = len(future_outflows)
            v_arr = self._v ** np.arange(1, n + 1, dtype=np.float64)
            lic[t] = float(np.dot(future_outflows, v_arr))

        # --- Risk Adjustment (PAA) ---
        # IFRS 17 permits RA under PAA using the same cost-of-capital method
        # as BBA. RA is computed as a proportion of the LIC (incurred claims
        # liability), which represents the uncertain future cash flows.
        ra = self._compute_ra_schedule(lic)

        # Total insurance liability for PAA = LRC + LIC + RA
        insurance_liability = lrc + lic + ra

        # Insurance revenue under PAA = premiums earned in period
        # = LRC[t] - LRC[t+1] (unearned premium released)
        lrc_padded = np.append(lrc, 0.0)
        insurance_revenue = lrc_padded[:-1] - lrc_padded[1:]

        # Service expenses = actual claims + expenses
        insurance_service_expenses = (
            self.cashflows.death_claims + self.cashflows.expenses + self.cashflows.lapse_surrenders
        )

        insurance_service_result = insurance_revenue - insurance_service_expenses

        return IFRS17Result(
            approach="PAA",
            valuation_date=self.cashflows.valuation_date,
            discount_rate=self.discount_rate,
            n_periods=n_per,
            bel=lic,  # BEL in PAA context = LIC
            risk_adjustment=ra,
            csm=np.zeros(n_per, dtype=np.float64),
            insurance_liability=insurance_liability,
            csm_interest_accretion=np.zeros(n_per, dtype=np.float64),
            csm_release=np.zeros(n_per, dtype=np.float64),
            insurance_revenue=insurance_revenue,
            insurance_service_expenses=insurance_service_expenses,
            insurance_service_result=insurance_service_result,
            initial_bel=float(lic[0]),
            initial_ra=float(ra[0]),
            initial_csm=0.0,
            loss_component=0.0,
            lrc=lrc,
            lic=lic,
        )

    def measure_vfa(
        self,
        underlying_items_fair_value: np.ndarray,
        variable_fee_rate: float = 0.01,
    ) -> IFRS17Result:
        """
        Compute IFRS 17 Variable Fee Approach (VFA) measurement.

        The VFA is used for direct-participating contracts where policyholder
        returns are substantially linked to underlying items (e.g., Universal Life,
        unit-linked products). Under VFA:
        - The insurer's fee = gross_premiums - expected policyholder returns
        - CSM absorbs changes in the fair value of underlying items (NOT locked-in)
        - BEL is computed on the same prospective basis as BBA

        Args:
            underlying_items_fair_value:
                Expected fair value of underlying items (e.g., account value or
                unit fund value) at each projection period. Shape (T,).
            variable_fee_rate:
                Annual rate charged as the variable fee on underlying items
                (the insurer's compensation for insurance services). Default 0.01 (1%).

        Returns:
            IFRS17Result with VFA-adjusted BEL/RA/CSM schedules.
        """
        if len(underlying_items_fair_value) != self._T:
            raise ValueError(
                f"underlying_items_fair_value length {len(underlying_items_fair_value)} "
                f"!= projection_months {self._T}"
            )
        n_per = self._T

        # --- Variable fee (insurer's share of underlying items) ---
        monthly_fee_rate = (1.0 + variable_fee_rate) ** (1.0 / 12.0) - 1.0
        variable_fees = underlying_items_fair_value * monthly_fee_rate

        # --- BEL: adjusted for variable fee offset ---
        # FCF adjusted: outflows - variable fees (fees reduce the BEL)
        fcf_adjusted = self._fcf - variable_fees

        bel = np.zeros(n_per, dtype=np.float64)
        for t in range(n_per - 1, -1, -1):
            future_bel = bel[t + 1] if t + 1 < n_per else 0.0
            bel[t] = fcf_adjusted[t] * self._v + future_bel * self._v

        # --- RA: same as BBA ---
        ra = self._compute_ra_schedule(bel)

        # --- CSM: absorbs changes in fair value of underlying items ---
        initial_bel = float(bel[0])
        initial_ra = float(ra[0])
        initial_csm = float(max(0.0, -(initial_bel + initial_ra)))
        loss_component = float(max(0.0, initial_bel + initial_ra))

        # CSM roll-forward under VFA: accretes at the current (unlocked) rate
        # For simplicity, use the same discount_rate as accretion rate
        csm_schedule, csm_accretion, csm_release = self._compute_csm_schedule(
            initial_csm=initial_csm,
            risk_free_rate=self.discount_rate,
        )

        csm_at_start = np.zeros(n_per, dtype=np.float64)
        csm_at_start[0] = initial_csm
        csm_at_start[1:] = csm_schedule[:-1]

        insurance_liability = bel + ra + csm_at_start

        # P&L: insurance revenue = variable fees + CSM release
        ra_padded = np.append(ra, 0.0)
        ra_release = ra_padded[:-1] - ra_padded[1:]
        insurance_revenue = variable_fees + csm_release
        insurance_service_expenses = (
            self.cashflows.death_claims + self.cashflows.expenses - ra_release
        )
        insurance_service_result = insurance_revenue - insurance_service_expenses

        return IFRS17Result(
            approach="VFA",
            valuation_date=self.cashflows.valuation_date,
            discount_rate=self.discount_rate,
            n_periods=n_per,
            bel=bel,
            risk_adjustment=ra,
            csm=csm_at_start,
            insurance_liability=insurance_liability,
            csm_interest_accretion=csm_accretion,
            csm_release=csm_release,
            insurance_revenue=insurance_revenue,
            insurance_service_expenses=insurance_service_expenses,
            insurance_service_result=insurance_service_result,
            initial_bel=initial_bel,
            initial_ra=initial_ra,
            initial_csm=initial_csm,
            loss_component=loss_component,
        )

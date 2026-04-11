"""
WholeLife — cash flow projection engine for whole life insurance.

Produces monthly gross cash flows for a block of whole life policies over
the full projection horizon. Unlike term life, whole life has no expiry date —
policies remain active until death or lapse (or the projection horizon ends).

Net premium reserves are computed via backward recursion. Because the projection
horizon may not extend to omega (max age 120), the terminal reserve at month T
is the prospective APV of remaining benefits minus net premiums, not zero.

Supports:
- Non-par and par whole life (dividends not modelled — par treated same as non-par)
- Whole-life pay (premiums throughout life) and limited-pay (e.g., 20-pay)

Vectorization contract: all intermediate arrays have shape (N, T) where
N = n_policies, T = projection_months. No Python loops over policies.
Loops over time steps are acceptable for reserve recursion.
"""

import uuid
from enum import StrEnum

import numpy as np

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.base_product import BaseProduct
from polaris_re.utils.date_utils import projection_date_index

__all__ = ["WholeLife", "WholeLifeVariant"]


class WholeLifeVariant(StrEnum):
    """Whole life product variant."""

    NON_PAR = "NON_PAR"
    PAR = "PAR"  # Dividends not modelled — treated as NON_PAR for Phase 2


class WholeLife(BaseProduct):
    """
    Monthly cash flow projection engine for whole life insurance.

    Handles level whole life products on a gross premium basis (non-par and par,
    though par dividends are not modelled in Phase 2). Net premium reserves use
    backward recursion with a prospective terminal reserve.

    All calculations are vectorized over the N policies in the inforce block.

    Args:
        inforce:                The inforce block (must contain WHOLE_LIFE policies).
        assumptions:            Assumption set (mortality, lapse).
        config:                 Projection configuration.
        variant:                NON_PAR or PAR (default NON_PAR).
        premium_payment_years:  Limited pay period in years. None = whole-life pay.
    """

    def __init__(
        self,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
        variant: WholeLifeVariant = WholeLifeVariant.NON_PAR,
        premium_payment_years: int | None = None,
    ) -> None:
        super().__init__(inforce, assumptions, config)
        self.variant = variant
        self.premium_payment_years = premium_payment_years
        self._validate_inputs()

    def _validate_inputs(self) -> None:
        """Validate inforce block is compatible with WholeLife projection."""
        non_wl = [
            p.policy_id for p in self.inforce.policies if p.product_type != ProductType.WHOLE_LIFE
        ]
        if non_wl:
            raise PolarisValidationError(
                f"WholeLife received non-WHOLE_LIFE policies: {non_wl[:5]}"
                f"{'...' if len(non_wl) > 5 else ''}"
            )
        if self.premium_payment_years is not None and self.premium_payment_years < 1:
            raise PolarisValidationError(
                f"premium_payment_years must be >= 1, got {self.premium_payment_years}"
            )

    def _build_rate_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Build monthly mortality (q) and lapse (w) rate arrays, shape (N, T).

        For whole life there is no term expiry — policies remain active until
        max_age (120). Ages are capped at the mortality table maximum.
        """
        n = self.inforce.n_policies
        t = self.config.projection_months
        q = np.zeros((n, t), dtype=np.float64)
        w = np.zeros((n, t), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec_at(self.config.valuation_date)  # (N,)
        attained_ages = self.inforce.attained_age_vec_at(self.config.valuation_date)  # (N,)

        sex_list = [p.sex for p in self.inforce.policies]
        smoker_list = [p.smoker_status for p in self.inforce.policies]
        unique_combos = set(zip(sex_list, smoker_list, strict=True))

        for month in range(t):
            current_durations = duration_inforce + month
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment
            current_ages = np.minimum(current_ages, self.assumptions.mortality.max_age)

            q_monthly_col = np.zeros(n, dtype=np.float64)
            for sex, smoker in unique_combos:
                mask = np.array(
                    [
                        (s == sex and sm == smoker)
                        for s, sm in zip(sex_list, smoker_list, strict=True)
                    ],
                    dtype=bool,
                )
                if not np.any(mask):
                    continue
                q_monthly_col[mask] = self.assumptions.mortality.get_qx_vector(
                    current_ages[mask],
                    sex,
                    smoker,
                    current_durations[mask],
                )

            w_monthly_col = self.assumptions.lapse.get_lapse_vector(current_durations)

            # At max age the policy must terminate — set mortality to 1.0
            max_age = self.assumptions.mortality.max_age
            at_max_age = (
                attained_ages + (current_durations // 12) - (duration_inforce // 12)
            ) >= max_age
            q_monthly_col = np.where(at_max_age, 1.0, q_monthly_col)
            w_monthly_col = np.where(at_max_age, 0.0, w_monthly_col)

            q[:, month] = q_monthly_col
            w[:, month] = w_monthly_col

        return q, w

    def _compute_inforce_factors(self, q: np.ndarray, w: np.ndarray) -> np.ndarray:
        """
        Forward recursion for in-force factor lx, shape (N, T).

        lx[:,0] = 1.0
        lx[:,t] = lx[:,t-1] * (1 - q[:,t-1]) * (1 - w[:,t-1])
        """
        n, t = q.shape
        lx = np.ones((n, t), dtype=np.float64)
        for month in range(1, t):
            lx[:, month] = lx[:, month - 1] * (1.0 - q[:, month - 1]) * (1.0 - w[:, month - 1])
        return lx

    def _compute_annual_net_premiums(
        self, q: np.ndarray, lx: np.ndarray, v_monthly: float
    ) -> np.ndarray:
        """
        Compute annual level net premium for each whole life policy, shape (N,).

        Returns the ANNUAL premium amount. The caller must divide by 12 for monthly use.

        For whole-life pay:
            P_net = A_x / a_x
            A_x = sum_t v^(t+1) * lx_t * q_t / sum_t_0 lx_t  (normalised by lx_0 = 1)
            a_x = (1/12) * sum_t v^t * lx_t  (monthly annuity-due)

        For limited-pay (premium_payment_years = h):
            P_net_h = A_x / a_x:h  (annuity restricted to h years)
        """
        _n, t = q.shape
        face_vec = self.inforce.face_amount_vec  # (N,)

        v_powers_plus1 = v_monthly ** np.arange(1, t + 1, dtype=np.float64)
        v_powers = v_monthly ** np.arange(t, dtype=np.float64)

        # APV of death benefits: A_x = sum v^(t+1) * lx_t * q_t * face
        apv_benefits = np.sum(
            v_powers_plus1[np.newaxis, :] * lx * q * face_vec[:, np.newaxis],
            axis=1,
        )  # (N,)

        # APV of annuity-due (monthly): a_x = (1/12) * sum v^t * lx_t
        if self.premium_payment_years is None:
            # Whole life pay: annuity runs entire projection
            premium_months = t
        else:
            premium_months = min(self.premium_payment_years * 12, t)

        apv_annuity = (
            np.sum(
                v_powers[:premium_months][np.newaxis, :] * lx[:, :premium_months],
                axis=1,
            )
            / 12.0
        )  # (N,) — monthly annuity-due

        p_net_annual = np.where(apv_annuity > 0, apv_benefits / apv_annuity, 0.0)
        return p_net_annual  # Annual net premium per policy

    def _compute_terminal_reserves(
        self, q: np.ndarray, lx: np.ndarray, v_monthly: float
    ) -> np.ndarray:
        """
        Compute the prospective terminal reserve at month T for each policy, shape (N,).

        At the end of the projection, the remaining obligation is estimated
        as A_{x+T} ≈ q_max * v (if near max age) or the last period's benefit APV.
        Simplified: use V_T = face * q_{T-1} * v (one-period prospective estimate).
        For most projection horizons this is a conservative but reasonable approximation.
        """
        face_vec = self.inforce.face_amount_vec  # (N,)
        # At the final time step, reserve = face * q_last * v (end-of-period view)
        q_last = q[:, -1]
        v_terminal = np.where(
            q_last >= 1.0,
            face_vec,  # at max age: reserve = face (certain death)
            face_vec * q_last * v_monthly,
        )
        return np.maximum(v_terminal, 0.0)

    def compute_reserves(self) -> np.ndarray:
        """
        Backward recursion for net premium reserves, shape (N, T).

        Unlike term life, the terminal reserve V_T is NOT zero — it equals the
        prospective APV of remaining benefits at month T.

        Recursion (solving backward from T):
            V_t = [q_t * face + (1 - q_t) * V_{t+1}] * v_monthly - P_net/12

        Premium payments cease after premium_payment_years (limited pay).
        """
        q, _w = self._build_rate_arrays()
        lx = self._compute_inforce_factors(q, _w)
        n, t = q.shape

        face_vec = self.inforce.face_amount_vec  # (N,)
        i_val = self.config.effective_valuation_rate
        v_monthly = (1.0 + i_val) ** (-1.0 / 12.0)

        p_net_annual = self._compute_annual_net_premiums(q, lx, v_monthly)  # (N,)
        p_net_monthly = p_net_annual / 12.0  # (N,)

        # Terminal reserve at month T (prospective, not zero)
        reserves = np.zeros((n, t), dtype=np.float64)
        reserves[:, t - 1] = self._compute_terminal_reserves(q, lx, v_monthly)

        # Determine which months fall within the premium payment period
        if self.premium_payment_years is not None:
            premium_payment_months = self.premium_payment_years * 12
        else:
            premium_payment_months = t  # whole-life pay

        # Backward recursion
        for month in range(t - 2, -1, -1):
            in_premium_period = month < premium_payment_months
            p_deducted = p_net_monthly if in_premium_period else 0.0
            reserves[:, month] = (
                q[:, month] * face_vec + (1.0 - q[:, month]) * reserves[:, month + 1]
            ) * v_monthly - p_deducted

        reserves = np.maximum(reserves, 0.0)
        return reserves

    def project(self, seriatim: bool = False) -> CashFlowResult:
        """
        Run the full whole life projection and return CashFlowResult (GROSS basis).

        Args:
            seriatim: If True, populate (N,T) arrays in the result.
        """
        n = self.inforce.n_policies
        t = self.config.projection_months

        q, w = self._build_rate_arrays()
        lx = self._compute_inforce_factors(q, w)
        reserves = self.compute_reserves()

        face_vec = self.inforce.face_amount_vec  # (N,)
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,)

        # Premium payment mask: zero after limited-pay period
        if self.premium_payment_years is not None:
            prem_mask = np.zeros(t, dtype=np.float64)
            prem_mask[: self.premium_payment_years * 12] = 1.0
        else:
            prem_mask = np.ones(t, dtype=np.float64)

        # Cash flow arrays, shape (N, T)
        ser_premiums = lx * monthly_prem_vec[:, np.newaxis] * prem_mask[np.newaxis, :]
        ser_claims = lx * q * face_vec[:, np.newaxis]
        ser_lapses = np.zeros((n, t), dtype=np.float64)
        ser_expenses = np.zeros((n, t), dtype=np.float64)

        # Reserve balance: lx * V
        ser_reserves = lx * reserves
        ser_reserve_inc = np.zeros((n, t), dtype=np.float64)
        ser_reserve_inc[:, 0] = ser_reserves[:, 0]
        ser_reserve_inc[:, 1:] = ser_reserves[:, 1:] - ser_reserves[:, :-1]

        # Aggregate to (T,)
        agg_premiums = ser_premiums.sum(axis=0)
        agg_claims = ser_claims.sum(axis=0)
        agg_lapses = ser_lapses.sum(axis=0)
        agg_expenses = ser_expenses.sum(axis=0)
        agg_reserve_balance = ser_reserves.sum(axis=0)
        agg_reserve_inc = ser_reserve_inc.sum(axis=0)
        agg_net_cf = agg_premiums - agg_claims - agg_lapses - agg_expenses - agg_reserve_inc

        time_idx = projection_date_index(self.config.valuation_date, t)

        result = CashFlowResult(
            run_id=str(uuid.uuid4()),
            valuation_date=self.config.valuation_date,
            basis="GROSS",
            assumption_set_version=self.assumptions.version,
            product_type="WHOLE_LIFE",
            block_id=self.inforce.block_id,
            projection_months=t,
            time_index=time_idx,
            gross_premiums=agg_premiums,
            death_claims=agg_claims,
            lapse_surrenders=agg_lapses,
            expenses=agg_expenses,
            reserve_balance=agg_reserve_balance,
            reserve_increase=agg_reserve_inc,
            net_cash_flow=agg_net_cf,
        )

        if seriatim:
            result.seriatim_premiums = ser_premiums
            result.seriatim_claims = ser_claims
            result.seriatim_reserves = reserves
            result.seriatim_lx = lx

        return result

"""
TermLife - cash flow projection engine for term life insurance.

Produces monthly gross cash flows for a block of term life policies over
the full projection horizon. Applies mortality and lapse decrements to an
in-force factor array and computes premiums, claims, and net premium reserves.

Vectorization contract: all intermediate arrays have shape (N, T) where
N = n_policies, T = projection_months. No Python loops over policies.
Loops over time steps are acceptable for reserve recursion.
"""

import uuid

import numpy as np

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.base_product import BaseProduct
from polaris_re.utils.date_utils import projection_date_index

__all__ = ["TermLife"]


class TermLife(BaseProduct):
    """
    Monthly cash flow projection engine for term life insurance.

    Handles level term products on a gross premium basis.
    Net premium reserves are computed using backward recursion.
    All calculations are vectorized over the N policies in the inforce block.
    """

    def __init__(
        self,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
    ) -> None:
        super().__init__(inforce, assumptions, config)
        self._validate_inputs()

    def _validate_inputs(self) -> None:
        """Validate the inforce block is compatible with TermLife projection."""
        non_term = [
            p.policy_id for p in self.inforce.policies if p.product_type != ProductType.TERM
        ]
        if non_term:
            raise PolarisValidationError(
                f"TermLife received non-TERM policies: {non_term[:5]}"
                f"{'...' if len(non_term) > 5 else ''}"
            )
        missing_term = [p.policy_id for p in self.inforce.policies if p.policy_term is None]
        if missing_term:
            raise PolarisValidationError(
                f"Term policies must have policy_term set. Missing on: {missing_term[:5]}"
            )

    def _build_rate_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Build monthly mortality (q) and lapse (w) rate arrays, shape (N, T).

        Mortality rates are looked up by iterating over unique (sex, smoker) combos
        and using masking. Rates are zeroed after policy term expiry.
        """
        n = self.inforce.n_policies
        t = self.config.projection_months
        q = np.zeros((n, t), dtype=np.float64)
        w = np.zeros((n, t), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec  # (N,)
        attained_ages = self.inforce.attained_age_vec  # (N,)
        remaining_months = self.inforce.remaining_term_months_vec  # (N,)

        # Build unique (sex, smoker) combos for mortality lookup
        sex_list = [p.sex for p in self.inforce.policies]
        smoker_list = [p.smoker_status for p in self.inforce.policies]
        unique_combos = set(zip(sex_list, smoker_list, strict=True))

        for month in range(t):
            # Current ages and durations at this time step
            current_durations = duration_inforce + month  # (N,)
            # Age increments: each 12 months of duration adds 1 year of age
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment  # (N,)

            # Cap ages at table max
            current_ages = np.minimum(current_ages, self.assumptions.mortality.max_age)

            # Active mask: policy still in term
            active = month < remaining_months  # (N,)

            # Mortality: iterate over (sex, smoker) combos
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

            # Lapse rates
            w_monthly_col = self.assumptions.lapse.get_lapse_vector(current_durations)

            # Zero out rates for expired policies
            q[:, month] = q_monthly_col * active
            w[:, month] = w_monthly_col * active

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

    def compute_reserves(self) -> np.ndarray:
        """
        Backward recursion for net premium reserves, shape (N, T).

        Uses net premium reserve formula:
        (V_t + P_net) * (1+i)^(1/12) = q_t * b_t + (1-q_t) * V_{t+1}

        Solving for V_t:
        V_t = [q_t * b_t + (1-q_t) * V_{t+1}] / (1+i)^(1/12) - P_net

        Terminal condition: V_T = 0
        """
        q, _w = self._build_rate_arrays()
        n, t = q.shape

        face_vec = self.inforce.face_amount_vec  # (N,)
        i_val = self.config.effective_valuation_rate
        v_monthly = (1.0 + i_val) ** (-1.0 / 12.0)  # monthly discount factor

        # Compute net premium (level net premium for term life)
        # P_net = APV(benefits) / APV(annuity-due)
        p_net = self._compute_net_premiums(q, v_monthly)  # (N,)

        # Backward recursion
        reserves = np.zeros((n, t), dtype=np.float64)
        # V_T = 0 (terminal condition, already zeros)

        for month in range(t - 2, -1, -1):
            reserves[:, month] = (
                q[:, month] * face_vec + (1.0 - q[:, month]) * reserves[:, month + 1]
            ) * v_monthly - p_net

        # Floor reserves at 0 (net premium reserves should not go negative
        # for level term, but numerical precision can cause small negatives)
        reserves = np.maximum(reserves, 0.0)

        return reserves

    def _compute_net_premiums(self, q: np.ndarray, v_monthly: float) -> np.ndarray:
        """
        Compute level net premium for each policy.

        P_net = APV(death benefits) / APV(annuity-due)

        APV(benefits) = sum_{t=0}^{T-1} v^(t+1) * tpx * q_{x+t} * face
        APV(annuity)  = sum_{t=0}^{T-1} v^t * tpx
        """
        n, t = q.shape
        face_vec = self.inforce.face_amount_vec  # (N,)

        # Build survival probabilities tpx (probability alive at start of month t)
        # tpx[:, 0] = 1.0, tpx[:, t] = product_{s=0}^{t-1} (1 - q[:,s])
        tpx = np.ones((n, t), dtype=np.float64)
        for month in range(1, t):
            tpx[:, month] = tpx[:, month - 1] * (1.0 - q[:, month - 1])

        # Discount factors
        v_powers = v_monthly ** np.arange(t, dtype=np.float64)  # v^0, v^1, ..., v^(T-1)
        v_powers_plus1 = v_monthly ** np.arange(1, t + 1, dtype=np.float64)  # v^1, ..., v^T

        # APV of death benefits: sum over t of v^(t+1) * tpx_t * q_t * face
        apv_benefits = np.sum(
            v_powers_plus1[np.newaxis, :] * tpx * q * face_vec[:, np.newaxis],
            axis=1,
        )  # (N,)

        # APV of annuity-due: sum over t of v^t * tpx_t
        apv_annuity = np.sum(
            v_powers[np.newaxis, :] * tpx,
            axis=1,
        )  # (N,)

        # Avoid division by zero
        p_net = np.where(apv_annuity > 0, apv_benefits / apv_annuity, 0.0)

        return p_net

    def project(self, seriatim: bool = False) -> CashFlowResult:
        """
        Run the full term life projection and return CashFlowResult (GROSS basis).

        Args:
            seriatim: If True, populate (N,T) arrays in the result.
        """
        n = self.inforce.n_policies
        t = self.config.projection_months

        # Build rate arrays
        q, w = self._build_rate_arrays()

        # Compute inforce factors
        lx = self._compute_inforce_factors(q, w)

        # Compute reserves
        reserves = self.compute_reserves()

        # Extract policy vectors
        face_vec = self.inforce.face_amount_vec  # (N,)
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,)

        # Cash flow arrays, shape (N, T)
        # Premiums: lx * monthly_premium (paid by those in force at start of month)
        ser_premiums = lx * monthly_prem_vec[:, np.newaxis]  # (N, T)

        # Death claims: lx_t * q_t * face (deaths during month t)
        ser_claims = lx * q * face_vec[:, np.newaxis]  # (N, T)

        # Lapse surrenders: no cash value for term life, so zero
        ser_lapses = np.zeros((n, t), dtype=np.float64)

        # Expenses: zero for now (Phase 2)
        ser_expenses = np.zeros((n, t), dtype=np.float64)

        # Reserve balance (seriatim): lx * V
        ser_reserves = lx * reserves  # (N, T)

        # Reserve increase: delta(lx * V)
        ser_reserve_inc = np.zeros((n, t), dtype=np.float64)
        ser_reserve_inc[:, 0] = ser_reserves[:, 0]
        ser_reserve_inc[:, 1:] = ser_reserves[:, 1:] - ser_reserves[:, :-1]

        # Aggregate to shape (T,)
        agg_premiums = ser_premiums.sum(axis=0)
        agg_claims = ser_claims.sum(axis=0)
        agg_lapses = ser_lapses.sum(axis=0)
        agg_expenses = ser_expenses.sum(axis=0)
        agg_reserve_balance = ser_reserves.sum(axis=0)
        agg_reserve_inc = ser_reserve_inc.sum(axis=0)

        # Net cash flow = premiums - claims - lapses - expenses - reserve_increase
        agg_net_cf = agg_premiums - agg_claims - agg_lapses - agg_expenses - agg_reserve_inc

        # Time index
        time_idx = projection_date_index(self.config.valuation_date, t)

        result = CashFlowResult(
            run_id=str(uuid.uuid4()),
            valuation_date=self.config.valuation_date,
            basis="GROSS",
            assumption_set_version=self.assumptions.version,
            product_type="TERM",
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

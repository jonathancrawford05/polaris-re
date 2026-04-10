"""
UniversalLife — cash flow projection engine for universal life insurance.

UL products have a flexible premium structure with a separate account value (AV).
Each month:
  1. The credited interest is applied to the account value.
  2. A Cost of Insurance (COI) charge is deducted, based on the Net Amount at Risk.
  3. Premiums are added and expenses are deducted.

The AV roll-forward each month (beginning-of-month convention):
    AV_{t+1} = (AV_t + prem_t - expense_t) * (1 + credited_rate/12) - COI_t

where:
    COI_t = max(face - AV_t, 0) * q_{x+t} / (1 + credited_rate/12)

Policy terminates (lapse) when AV reaches 0 (no no-lapse guarantee).
Reserve (simplified) = account value.

Vectorization contract: all intermediate arrays shape (N, T). The AV
roll-forward loop over time steps is acceptable.
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

__all__ = ["UniversalLife"]


class UniversalLife(BaseProduct):
    """
    Monthly cash flow projection engine for universal life insurance.

    Each policy must have `account_value` and `credited_rate` set on the
    Policy object. The `annual_premium` field is used as the target premium
    paid each month (annual_premium / 12).

    Args:
        inforce:           The inforce block (must contain UNIVERSAL_LIFE policies).
        assumptions:       Assumption set (mortality, lapse).
        config:            Projection configuration.
        expense_per_month: Flat per-policy monthly expense ($). Default 0.
        expense_pct_prem:  Expense as percentage of monthly premium. Default 0.
        surrender_charge_vec: Per-policy surrender charge at t=0 ($), shape (N,).
                              Reduces linearly to 0 over 10 years. None = no charge.
    """

    def __init__(
        self,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
        expense_per_month: float = 0.0,
        expense_pct_prem: float = 0.0,
        surrender_charge_vec: np.ndarray | None = None,
    ) -> None:
        super().__init__(inforce, assumptions, config)
        self.expense_per_month = expense_per_month
        self.expense_pct_prem = expense_pct_prem
        self._surrender_charge_vec = surrender_charge_vec
        self._validate_inputs()

    def _validate_inputs(self) -> None:
        """Validate inforce block is compatible with UniversalLife projection."""
        non_ul = [
            p.policy_id
            for p in self.inforce.policies
            if p.product_type != ProductType.UNIVERSAL_LIFE
        ]
        if non_ul:
            raise PolarisValidationError(
                f"UniversalLife received non-UL policies: {non_ul[:5]}"
                f"{'...' if len(non_ul) > 5 else ''}"
            )
        missing_av = [p.policy_id for p in self.inforce.policies if p.account_value is None]
        if missing_av:
            raise PolarisValidationError(
                f"UL policies must have account_value set. Missing on: {missing_av[:5]}"
            )
        missing_rate = [p.policy_id for p in self.inforce.policies if p.credited_rate is None]
        if missing_rate:
            raise PolarisValidationError(
                f"UL policies must have credited_rate set. Missing on: {missing_rate[:5]}"
            )
        n = self.inforce.n_policies
        sc = self._surrender_charge_vec
        if sc is not None and sc.shape != (n,):
            raise PolarisValidationError(
                f"surrender_charge_vec shape must be ({n},), got {sc.shape}"
            )

    def _get_initial_account_values(self) -> np.ndarray:
        """Extract initial account values from policies, shape (N,)."""
        return np.array([p.account_value for p in self.inforce.policies], dtype=np.float64)

    def _get_credited_rates(self) -> np.ndarray:
        """Extract credited rates from policies, shape (N,)."""
        return np.array([p.credited_rate for p in self.inforce.policies], dtype=np.float64)

    def _build_mortality_arrays(self) -> np.ndarray:
        """
        Build monthly mortality rate array q, shape (N, T).

        UL uses mortality for COI calculation; lapses are driven by AV depletion.
        """
        n = self.inforce.n_policies
        t = self.config.projection_months
        q = np.zeros((n, t), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec_at(self.config.valuation_date)  # (N,)
        attained_ages = self.inforce.attained_age_vec_at(self.config.valuation_date)  # (N,)
        max_age = self.assumptions.mortality.max_age

        sex_list = [p.sex for p in self.inforce.policies]
        smoker_list = [p.smoker_status for p in self.inforce.policies]
        unique_combos = set(zip(sex_list, smoker_list, strict=True))

        for month in range(t):
            current_durations = duration_inforce + month
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = np.minimum(attained_ages + age_increment, max_age)

            q_col = np.zeros(n, dtype=np.float64)
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
                q_col[mask] = self.assumptions.mortality.get_qx_vector(
                    current_ages[mask], sex, smoker, current_durations[mask]
                )

            # At max age: certain death
            at_max = (
                attained_ages + (current_durations // 12) - (duration_inforce // 12)
            ) >= max_age
            q_col = np.where(at_max, 1.0, q_col)
            q[:, month] = q_col

        return q

    def _build_lapse_arrays(self) -> np.ndarray:
        """
        Build voluntary lapse rate array w, shape (N, T).

        UL lapses when AV depletes. In addition, voluntary lapses from the
        assumption set apply.
        """
        n = self.inforce.n_policies
        t = self.config.projection_months
        w = np.zeros((n, t), dtype=np.float64)
        duration_inforce = self.inforce.duration_inforce_vec_at(self.config.valuation_date)

        for month in range(t):
            current_durations = duration_inforce + month
            w[:, month] = self.assumptions.lapse.get_lapse_vector(current_durations)

        return w

    def _build_surrender_charges(self) -> np.ndarray:
        """
        Surrender charge schedule, shape (N, T).

        Charges reduce linearly from initial value to 0 over 10 years (120 months).
        """
        n = self.inforce.n_policies
        t = self.config.projection_months

        if self._surrender_charge_vec is None:
            return np.zeros((n, t), dtype=np.float64)

        schedule = np.zeros((n, t), dtype=np.float64)
        for m in range(t):
            # Linear rundown over 120 months
            factor = max(0.0, 1.0 - m / 120.0)
            schedule[:, m] = self._surrender_charge_vec * factor

        return schedule

    def _roll_forward_account_values(
        self,
        q: np.ndarray,
        w: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Roll forward account values and compute COI and lapse cash flows.

        Returns:
            av:           Account value array, shape (N, T+1), av[:,0] = initial AV
            coi:          COI charges, shape (N, T)
            active:       Boolean in-force mask, shape (N, T) (False after lapse/death)
            lapse_cv:     Lapse surrender cash value (benefit to policyholder), shape (N, T)
        """
        n = self.inforce.n_policies
        t = self.config.projection_months

        av = np.zeros((n, t + 1), dtype=np.float64)
        av[:, 0] = self._get_initial_account_values()

        credited_rates = self._get_credited_rates()  # (N,)
        monthly_credited = (1.0 + credited_rates) ** (1.0 / 12.0) - 1.0  # (N,)

        face_vec = self.inforce.face_amount_vec  # (N,)
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,) = annual/12
        surrender_charges = self._build_surrender_charges()  # (N, T)

        coi = np.zeros((n, t), dtype=np.float64)
        lapse_cv = np.zeros((n, t), dtype=np.float64)

        # lx: forward in-force factor (same as TermLife)
        lx = np.ones((n, t), dtype=np.float64)

        for m in range(t):
            current_av = av[:, m]

            # Per-policy expense
            expense_t = self.expense_per_month + monthly_prem_vec * self.expense_pct_prem

            # COI: based on NAR = max(face - AV, 0) at beginning of month
            nar_t = np.maximum(face_vec - current_av, 0.0)
            monthly_rate = 1.0 + monthly_credited  # accumulation factor
            # COI deducted at end of month (equivalent to beginning with accumulation)
            coi_t = nar_t * q[:, m] / monthly_rate  # per unit in-force
            coi[:, m] = coi_t * lx[:, m]

            # Voluntary lapse surrender value
            cash_value_t = np.maximum(current_av - surrender_charges[:, m], 0.0)
            lapse_cv[:, m] = cash_value_t * w[:, m] * lx[:, m]

            # AV roll-forward:
            # AV_{t+1} = (AV_t + prem - expense) * (1 + i/12) - COI
            new_av = (current_av + monthly_prem_vec - expense_t) * monthly_rate - coi_t
            new_av = np.maximum(new_av, 0.0)  # AV cannot go negative

            # Forced lapse: policies where AV dropped to 0
            forced_lapse = (current_av > 0.0) & (new_av <= 0.0)
            w_total = w[:, m] + forced_lapse.astype(np.float64)
            w_total = np.minimum(w_total, 1.0)

            av[:, m + 1] = new_av

            # Update lx for next month
            if m < t - 1:
                lx[:, m + 1] = lx[:, m] * (1.0 - q[:, m]) * (1.0 - w_total)

        return av[:, :t], coi, lx, lapse_cv

    def compute_reserves(self) -> np.ndarray:
        """
        For Universal Life, the reserve (simplified) equals the account value.

        Returns:
            Account value array, shape (N, T), dtype float64.
        """
        q = self._build_mortality_arrays()
        w = self._build_lapse_arrays()
        av, _coi, _lx, _lapse_cv = self._roll_forward_account_values(q, w)
        return av

    def project(self, seriatim: bool = False) -> CashFlowResult:
        """
        Run the full UL projection and return CashFlowResult (GROSS basis).

        Args:
            seriatim: If True, populate (N,T) arrays in the result.
        """
        n = self.inforce.n_policies
        t = self.config.projection_months

        q = self._build_mortality_arrays()
        w = self._build_lapse_arrays()

        av, _coi, lx, lapse_cv = self._roll_forward_account_values(q, w)

        face_vec = self.inforce.face_amount_vec  # (N,)
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,)

        # Premiums: target premium * lx
        ser_premiums = lx * monthly_prem_vec[:, np.newaxis]  # (N, T)

        # Death claims: face amount * q * lx
        ser_claims = lx * q * face_vec[:, np.newaxis]  # (N, T)

        # Lapse surrenders: already computed per-policy
        ser_lapses = lapse_cv  # (N, T)

        # Expenses: per-policy monthly
        expense_t = self.expense_per_month + monthly_prem_vec * self.expense_pct_prem
        ser_expenses = lx * expense_t[:, np.newaxis]  # (N, T)

        # Reserve balance = AV * lx
        ser_reserves = lx * av  # (N, T)

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
            product_type="UNIVERSAL_LIFE",
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
            result.seriatim_reserves = av
            result.seriatim_lx = lx

        return result

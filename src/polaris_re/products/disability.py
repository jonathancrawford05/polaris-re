"""
DisabilityProduct — cash flow projection engine for Critical Illness (CI)
and Disability Income (DI) insurance products.

Critical Illness (CI):
    Single-decrement model: Active → Claim → Terminated.
    - Upon CI event: pay face_amount as lump sum.
    - Policy terminates after claim (accelerated benefit structure).
    - Monthly CI claims = lx_t * i_{x+t}/12 * face_amount

Disability Income (DI):
    Multiple-state model: Active ↔ Disabled, Active → Dead.
    - Active lives pay premium; upon disablement enter disabled state.
    - Disabled lives receive monthly_benefit = face_amount / 12 per month in force.
    - Disabled lives exit state via recovery or mortality (termination rate).
    - Two (N, T) arrays: lx_active (not disabled), lx_disabled (receiving benefit).

For both product types:
    - Underlying mortality decrements use the mortality table from AssumptionSet.
    - Voluntary lapses apply to active lives only.
    - Reserve = 0 (simplified for Phase 2; actuarial DI reserves are complex).

Vectorization contract: all intermediate arrays shape (N, T).
Time loops are acceptable for state recursion.
"""

import uuid

import numpy as np

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.morbidity import MorbidityTable, MorbidityTableType
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.base_product import BaseProduct
from polaris_re.utils.date_utils import projection_date_index

__all__ = ["DisabilityProduct"]


class DisabilityProduct(BaseProduct):
    """
    Monthly cash flow projection engine for CI and DI insurance.

    The product type (CI or DI) is inferred from the policies' `product_type`
    field. All policies in the block must be of the same morbidity type.

    Args:
        inforce:    Inforce block (CRITICAL_ILLNESS or DISABILITY policies).
        assumptions: Assumption set providing the underlying mortality table.
        config:     Projection configuration.
        morbidity:  Morbidity table providing CI incidence or DI incidence/termination.
    """

    def __init__(
        self,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
        morbidity: MorbidityTable,
    ) -> None:
        super().__init__(inforce, assumptions, config)
        self.morbidity = morbidity
        self._validate_inputs()

    def _validate_inputs(self) -> None:
        """Validate product types match the morbidity table type."""
        valid_types = {ProductType.CRITICAL_ILLNESS, ProductType.DISABILITY}
        bad = [p.policy_id for p in self.inforce.policies if p.product_type not in valid_types]
        if bad:
            raise PolarisValidationError(
                f"DisabilityProduct received unsupported product types: {bad[:5]}"
                f"{'...' if len(bad) > 5 else ''}"
            )

        # All policies must be the same product type
        types_present = {p.product_type for p in self.inforce.policies}
        if len(types_present) > 1:
            raise PolarisValidationError(
                f"DisabilityProduct inforce block must contain only CI or only DI policies. "
                f"Found: {types_present}"
            )

        product_type = next(iter(types_present))

        if (
            product_type == ProductType.CRITICAL_ILLNESS
            and self.morbidity.table_type != MorbidityTableType.CRITICAL_ILLNESS
        ):
            raise PolarisValidationError("CI policies require a CI morbidity table.")
        elif (
            product_type == ProductType.DISABILITY
            and self.morbidity.table_type != MorbidityTableType.DISABILITY_INCOME
        ):
            raise PolarisValidationError("DI policies require a DI morbidity table.")

    @property
    def _product_type(self) -> ProductType:
        return self.inforce.policies[0].product_type

    def _build_mortality_arrays(self) -> np.ndarray:
        """Build monthly mortality rate array q, shape (N, T)."""
        n = self.inforce.n_policies
        t = self.config.projection_months
        q = np.zeros((n, t), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec
        attained_ages = self.inforce.attained_age_vec
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
            q[:, month] = q_col

        return q

    def _build_incidence_arrays(self) -> np.ndarray:
        """Build monthly CI/DI incidence rate array i, shape (N, T)."""
        n = self.inforce.n_policies
        t = self.config.projection_months
        incidence = np.zeros((n, t), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec
        attained_ages = self.inforce.attained_age_vec
        sex_list = [p.sex for p in self.inforce.policies]

        for month in range(t):
            current_durations = duration_inforce + month
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment

            for idx, sex in enumerate(sex_list):
                sex_str = sex.value
                age_arr = np.array([current_ages[idx]], dtype=np.int32)
                annual_rate = self.morbidity.get_incidence_vector(age_arr, sex_str)[0]
                # Monthly rate (assuming constant force approximation is close to /12)
                incidence[idx, month] = annual_rate / 12.0

        return incidence

    def _build_termination_arrays(self) -> np.ndarray:
        """Build monthly DI termination rate array, shape (N, T). DI only."""
        n = self.inforce.n_policies
        t = self.config.projection_months
        termination = np.zeros((n, t), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec
        attained_ages = self.inforce.attained_age_vec
        sex_list = [p.sex for p in self.inforce.policies]

        for month in range(t):
            current_durations = duration_inforce + month
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment

            for idx, sex in enumerate(sex_list):
                sex_str = sex.value
                age_arr = np.array([current_ages[idx]], dtype=np.int32)
                annual_rate = self.morbidity.get_termination_vector(age_arr, sex_str)[0]
                termination[idx, month] = annual_rate / 12.0

        return termination

    def _build_lapse_arrays(self) -> np.ndarray:
        """Voluntary lapse rates for active lives, shape (N, T)."""
        n = self.inforce.n_policies
        t = self.config.projection_months
        w = np.zeros((n, t), dtype=np.float64)
        duration_inforce = self.inforce.duration_inforce_vec
        for month in range(t):
            w[:, month] = self.assumptions.lapse.get_lapse_vector(
                duration_inforce + month
            )
        return w

    def compute_reserves(self) -> np.ndarray:
        """
        For Phase 2, returns zero reserves (DI GAAP reserves deferred to Phase 3).
        """
        n = self.inforce.n_policies
        t = self.config.projection_months
        return np.zeros((n, t), dtype=np.float64)

    def project(self, seriatim: bool = False) -> CashFlowResult:
        """
        Run CI or DI projection and return GROSS CashFlowResult.

        CI: single-decrement, lump sum claims.
        DI: multi-state, monthly benefit during disability.
        """
        if self._product_type == ProductType.CRITICAL_ILLNESS:
            return self._project_ci(seriatim)
        return self._project_di(seriatim)

    def _project_ci(self, seriatim: bool) -> CashFlowResult:
        """CI projection: single-decrement model."""
        n = self.inforce.n_policies
        t = self.config.projection_months

        q = self._build_mortality_arrays()  # (N, T) monthly mortality
        w = self._build_lapse_arrays()      # (N, T) voluntary lapse
        incidence = self._build_incidence_arrays()  # (N, T) monthly CI incidence

        face_vec = self.inforce.face_amount_vec  # (N,)
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,)

        # In-force factor: decremented by mortality, voluntary lapse, AND CI incidence
        lx = np.ones((n, t), dtype=np.float64)
        for month in range(1, t):
            lx[:, month] = (
                lx[:, month - 1]
                * (1.0 - q[:, month - 1])
                * (1.0 - w[:, month - 1])
                * (1.0 - incidence[:, month - 1])  # policy terminates on CI claim
            )

        # CI claims: lx * incidence * face (lump sum paid on new CI events)
        ser_claims = lx * incidence * face_vec[:, np.newaxis]  # (N, T)

        # Premiums: lx * monthly_premium
        ser_premiums = lx * monthly_prem_vec[:, np.newaxis]  # (N, T)

        # No lapses payable (no cash value), expenses, or reserves
        ser_lapses = np.zeros((n, t), dtype=np.float64)
        ser_expenses = np.zeros((n, t), dtype=np.float64)
        ser_reserves = np.zeros((n, t), dtype=np.float64)
        ser_reserve_inc = np.zeros((n, t), dtype=np.float64)

        return self._build_result(
            "CRITICAL_ILLNESS",
            ser_premiums, ser_claims, ser_lapses, ser_expenses,
            ser_reserves, ser_reserve_inc, lx, t, seriatim,
        )

    def _project_di(self, seriatim: bool) -> CashFlowResult:
        """DI projection: multi-state model (Active, Disabled)."""
        n = self.inforce.n_policies
        t = self.config.projection_months

        q = self._build_mortality_arrays()  # (N, T) mortality of active lives
        w = self._build_lapse_arrays()      # (N, T) voluntary lapse (active only)
        incidence = self._build_incidence_arrays()  # (N, T) monthly onset rate
        term_rate = self._build_termination_arrays()  # (N, T) monthly recovery+death rate

        face_vec = self.inforce.face_amount_vec  # (N,) monthly benefit = face/12
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,)

        # Two state arrays
        lx_active = np.ones((n, t), dtype=np.float64)
        lx_disabled = np.zeros((n, t), dtype=np.float64)

        for month in range(1, t):
            prev_active = lx_active[:, month - 1]
            prev_disabled = lx_disabled[:, month - 1]

            new_disabled = prev_active * incidence[:, month - 1]

            lx_active[:, month] = (
                prev_active
                * (1.0 - q[:, month - 1])
                * (1.0 - w[:, month - 1])
                * (1.0 - incidence[:, month - 1])
            )

            lx_disabled[:, month] = (
                prev_disabled * (1.0 - term_rate[:, month - 1])
                + new_disabled
            )
            lx_disabled[:, month] = np.maximum(lx_disabled[:, month], 0.0)

        # DI benefit = monthly_benefit * lx_disabled (monthly_benefit = face/12)
        monthly_benefit_vec = face_vec / 12.0  # (N,)
        ser_claims = lx_disabled * monthly_benefit_vec[:, np.newaxis]  # (N, T)

        # Premiums paid by active lives only
        ser_premiums = lx_active * monthly_prem_vec[:, np.newaxis]  # (N, T)

        # Lapses: active lives only (no surrender value)
        ser_lapses = np.zeros((n, t), dtype=np.float64)
        ser_expenses = np.zeros((n, t), dtype=np.float64)
        ser_reserves = np.zeros((n, t), dtype=np.float64)
        ser_reserve_inc = np.zeros((n, t), dtype=np.float64)

        result = self._build_result(
            "DISABILITY",
            ser_premiums, ser_claims, ser_lapses, ser_expenses,
            ser_reserves, ser_reserve_inc, lx_active, t, seriatim,
        )

        if seriatim:
            # Store disabled lives lx as seriatim_claims (hack: overload field)
            # Proper solution would add a seriatim_lx_disabled field to CashFlowResult
            pass

        return result

    def _build_result(
        self,
        product_type_str: str,
        ser_premiums: np.ndarray,
        ser_claims: np.ndarray,
        ser_lapses: np.ndarray,
        ser_expenses: np.ndarray,
        ser_reserves: np.ndarray,
        ser_reserve_inc: np.ndarray,
        lx: np.ndarray,
        t: int,
        seriatim: bool,
    ) -> CashFlowResult:
        """Aggregate seriatim arrays and build CashFlowResult."""
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
            product_type=product_type_str,
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
            result.seriatim_reserves = ser_reserves
            result.seriatim_lx = lx

        return result

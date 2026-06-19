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
from polaris_re.core.reserve_basis import ReserveBasis
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

    #: TermLife supports the net level premium reserve (default), the CRVM
    #: modified reserve, and the VM-20 simplified reserve. CRVM is implemented
    #: as Full Preliminary Term (FPT), which is exact CRVM for level term —
    #: renewal valuation premiums stay well below the 20-pay expense-allowance
    #: cap, so the cap never binds (ADR-088). VM20 is the simplified VM-20
    #: reserve ``max(NPR, DR)`` with the CRVM reserve as the net-premium-reserve
    #: floor and a deterministic gross-premium reserve (ADR-090). GAAP remains
    #: unimplemented and raises via the guard.
    _supported_reserve_bases = frozenset(
        {ReserveBasis.NET_PREMIUM, ReserveBasis.CRVM, ReserveBasis.VM20}
    )

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

        duration_inforce = self.inforce.duration_inforce_vec_at(self.config.valuation_date)  # (N,)
        attained_ages = self.inforce.attained_age_vec_at(self.config.valuation_date)  # (N,)
        remaining_months = self.inforce.remaining_term_months_vec  # (N,)

        # Per-policy substandard rating (ADR-042):
        # q_eff = q_base * multiplier + flat_extra / 1000 / 12, capped at 1.0.
        multiplier_vec = self.inforce.mortality_multiplier_vec  # (N,)
        flat_extra_monthly_vec = self.inforce.flat_extra_vec / 12000.0  # (N,) monthly

        # Build unique (sex, smoker) combos for mortality lookup
        sex_list = [p.sex for p in self.inforce.policies]
        smoker_list = [p.smoker_status for p in self.inforce.policies]
        unique_combos = set(zip(sex_list, smoker_list, strict=True))

        # Pre-compute improvement if available
        improvement = getattr(self.assumptions, "improvement", None)
        valuation_year = self.config.valuation_date.year

        for month in range(t):
            # Current ages and durations at this time step
            current_durations = duration_inforce + month  # (N,)
            # Age increments: each 12 months of duration adds 1 year of age
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment  # (N,)

            # Cap ages at table max
            current_ages = np.minimum(current_ages, self.assumptions.mortality.max_age)

            # Calendar year for this projection month (for improvement)
            cal_year = valuation_year + (month // 12)

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

            # Apply mortality improvement if configured
            if improvement is not None:
                # get_qx_vector returns monthly rates; convert back to annual,
                # apply improvement, then convert back to monthly
                q_annual_col = 1.0 - (1.0 - q_monthly_col) ** 12
                q_annual_improved = improvement.apply_improvement(
                    q_annual_col, current_ages, cal_year
                )
                from polaris_re.utils.interpolation import constant_force_interpolate_rates

                q_monthly_col = constant_force_interpolate_rates(
                    q_annual_improved, fraction=1.0 / 12.0
                )

            # Apply per-policy substandard rating (ADR-042). Must come after
            # improvement so multiplier scales the calendar-year-adjusted rate.
            q_monthly_col = np.minimum(q_monthly_col * multiplier_vec + flat_extra_monthly_vec, 1.0)

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
        Compute policy reserves, shape (N, T), on the configured basis.

        Dispatches on ``config.reserve_basis``:

        * ``NET_PREMIUM`` (default) — net level premium reserve.
        * ``CRVM`` — Commissioners Reserve Valuation Method, implemented as
          Full Preliminary Term (see :meth:`_compute_reserves_crvm`).
        * ``VM20`` — VM-20 simplified reserve ``max(NPR, DR)`` (see
          :meth:`_compute_reserves_vm20`).

        Unimplemented bases raise ``PolarisComputationError`` via the guard.
        """
        basis = self._check_reserve_basis()
        q, w = self._build_rate_arrays()
        i_val = self.config.effective_valuation_rate
        v_monthly = (1.0 + i_val) ** (-1.0 / 12.0)  # monthly discount factor

        if basis is ReserveBasis.CRVM:
            return self._compute_reserves_crvm(q, v_monthly)
        if basis is ReserveBasis.VM20:
            return self._compute_reserves_vm20(q, w, v_monthly)
        return self._compute_reserves_net_premium(q, v_monthly)

    def _compute_reserves_net_premium(self, q: np.ndarray, v_monthly: float) -> np.ndarray:
        """
        Backward recursion for net premium reserves, shape (N, T).

        Uses net premium reserve formula:
        (V_t + P_net) * (1+i)^(1/12) = q_t * b_t + (1-q_t) * V_{t+1}

        Solving for V_t:
        V_t = [q_t * b_t + (1-q_t) * V_{t+1}] / (1+i)^(1/12) - P_net

        Terminal condition: V_T = 0
        """
        n, t = q.shape
        face_vec = self.inforce.face_amount_vec  # (N,)

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

    def _compute_reserves_crvm(self, q: np.ndarray, v_monthly: float) -> np.ndarray:
        """
        Backward recursion for the CRVM modified reserve, shape (N, T).

        CRVM (Commissioners Reserve Valuation Method) grades in the first-year
        acquisition expense allowance by splitting the valuation net premium
        into a smaller first-year premium (alpha) and a level renewal premium
        (beta). For level term insurance the renewal valuation premium never
        exceeds the 20-pay expense-allowance cap, so CRVM coincides exactly
        with **Full Preliminary Term (FPT)**: the first policy year is valued
        as one-year term (alpha funds exactly the first year's mortality), and
        the renewal reserve from the end of year 1 onward is the net premium
        reserve of an otherwise-identical policy issued one year later.

        The recursion is identical to the net premium recursion but deducts
        alpha in the first 12 months and beta thereafter:

            V_t = [q_t * face + (1 - q_t) * V_{t+1}] * v - P_t
            P_t = alpha (months 0..11), beta (months 12..T-1)

        Consequences (used as closed-form checks in the tests):
        * ``0V = 0`` and the year-1 terminal reserve ``12V = 0`` (FPT).
        * From month 12 on, the reserve equals the net premium reserve of the
          one-year-later policy, so the CRVM reserve is below the net premium
          reserve during the early durations — exactly the expense allowance.

        Reserves are floored at 0 (the within-first-year preliminary-term
        reserve can dip slightly negative; a negative reserve is meaningless
        for the downstream NAR calculation).
        """
        n, t = q.shape
        face_vec = self.inforce.face_amount_vec  # (N,)

        alpha, beta = self._compute_crvm_modified_premiums(q, v_monthly)  # (N,), (N,)

        reserves = np.zeros((n, t), dtype=np.float64)
        # V_T = 0 (terminal condition, already zeros)
        for month in range(t - 2, -1, -1):
            p_month = alpha if month < 12 else beta  # (N,)
            reserves[:, month] = (
                q[:, month] * face_vec + (1.0 - q[:, month]) * reserves[:, month + 1]
            ) * v_monthly - p_month

        reserves = np.maximum(reserves, 0.0)
        return reserves

    def _compute_crvm_modified_premiums(
        self, q: np.ndarray, v_monthly: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        CRVM (Full Preliminary Term) modified valuation net premiums, shape (N,).

        Splits the policy into year 1 (months 0..11) and renewal (months
        12..T-1) and solves each segment on the equivalence principle:

            alpha = APV(year-1 benefits)   / APV(year-1 annuity-due)
            beta  = APV(renewal benefits)  / APV(renewal annuity-due)

        All APVs are taken as of issue using mortality-only survival ``tpx``
        (lapse does not enter a per-survivor valuation reserve), so that
        ``alpha * ad_year1 + beta * ad_renewal == APV(all benefits)`` and hence
        ``0V = 0``. Degenerate segments (no renewal exposure, e.g. a policy
        whose remaining term is under a year) yield a zero premium for that
        segment via the divide-by-zero guard.
        """
        n, t = q.shape
        face_vec = self.inforce.face_amount_vec  # (N,)

        # Mortality-only survival to the start of each month: tpx[:, 0] = 1.
        tpx = np.ones((n, t), dtype=np.float64)
        for month in range(1, t):
            tpx[:, month] = tpx[:, month - 1] * (1.0 - q[:, month - 1])

        v_powers = v_monthly ** np.arange(t, dtype=np.float64)  # v^0 .. v^(T-1)
        v_powers_plus1 = v_monthly ** np.arange(1, t + 1, dtype=np.float64)  # v^1 .. v^T

        benefit_pv = v_powers_plus1[np.newaxis, :] * tpx * q * face_vec[:, np.newaxis]  # (N, T)
        annuity_pv = v_powers[np.newaxis, :] * tpx  # (N, T)

        year1 = np.arange(t) < 12  # (T,) boolean split: first policy year vs renewal

        a_year1 = benefit_pv[:, year1].sum(axis=1)  # (N,)
        ad_year1 = annuity_pv[:, year1].sum(axis=1)  # (N,)
        a_renewal = benefit_pv[:, ~year1].sum(axis=1)  # (N,)
        ad_renewal = annuity_pv[:, ~year1].sum(axis=1)  # (N,)

        alpha = np.where(ad_year1 > 0.0, a_year1 / ad_year1, 0.0)
        beta = np.where(ad_renewal > 0.0, a_renewal / ad_renewal, 0.0)
        return alpha, beta

    def _compute_reserves_vm20(self, q: np.ndarray, w: np.ndarray, v_monthly: float) -> np.ndarray:
        """
        VM-20 simplified reserve, shape (N, T): ``max(NPR, DR)`` floored at 0.

        VM-20 (the US principle-based reserve, VM-20 of the NAIC Valuation
        Manual) sets the minimum reserve to the greatest of the Net Premium
        Reserve (NPR), the Deterministic Reserve (DR), and the Stochastic
        Reserve (SR). This simplified implementation covers the **deterministic
        path only** — ``max(NPR, DR)`` — which is the scope agreed for the
        reserve-basis epic (no stochastic scenarios; ADR-090, PLAN §3 Slice 3).

        * **NPR** is mapped to the CRVM reserve (:meth:`_compute_reserves_crvm`):
          a net-premium reserve with the first-year expense allowance graded in,
          which is the formulaic floor VM-20 prescribes for the NPR. The exact
          VM-20 NPR refinements (the term-specific mortality ``X`` factors, the
          2017 CSO valuation table, deficiency where gross < net) are a
          documented simplification — see ADR-090 "Out of scope".
        * **DR** is the deterministic gross-premium reserve
          (:meth:`_compute_deterministic_reserve`): the prospective present
          value of future benefits and maintenance expenses less future gross
          premiums, on best-estimate (mortality + lapse) decrements.

        The NPR is non-negative, so ``max(NPR, DR)`` is non-negative; the final
        ``maximum(..., 0.0)`` is a numerical-safety floor. For a well-priced
        block the gross premium exceeds the net premium, so DR < NPR and the
        formulaic floor governs (VM20 == CRVM); for an underpriced block the
        realistic DR can exceed the NPR floor and then drives the reserve — the
        deficiency signal a reinsurer relies on.
        """
        npr = self._compute_reserves_crvm(q, v_monthly)
        dr = self._compute_deterministic_reserve(q, w, v_monthly)
        return np.maximum(np.maximum(npr, dr), 0.0)

    def _compute_deterministic_reserve(
        self, q: np.ndarray, w: np.ndarray, v_monthly: float
    ) -> np.ndarray:
        """
        Deterministic gross-premium reserve, shape (N, T) (per in-force policy).

        Prospective present value, conditional on being in force at month ``t``,
        of future death benefits and maintenance expenses less future gross
        premiums, under **both** decrements (mortality ``q`` and lapse ``w``):

            DR_t = (E_t - G_t) + v * [ q_t * face
                                       + (1 - q_t) * (1 - w_t) * DR_{t+1} ]

        with terminal ``DR_T = 0``. Here ``G_t`` is the monthly gross premium and
        ``E_t`` the monthly expense (maintenance per in-force policy, plus the
        one-time acquisition cost in month 0 for genuine new business), both
        zeroed after term expiry — matching the cash flows :meth:`project`
        actually emits. Lapsing policies leave with no surrender value (term
        insurance has no cash value), so the only continuation value is for
        survivors of both decrements.

        The reserve is **not** floored here: a well-priced block has DR < 0 in
        the early durations (the policy is an asset), and that negative value is
        what makes the VM-20 ``max(NPR, DR)`` correctly defer to the NPR floor.
        """
        n, t = q.shape
        face_vec = self.inforce.face_amount_vec  # (N,)
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,)

        # Active mask: True while the policy term has not expired, shape (N, T).
        remaining_months = self.inforce.remaining_term_months_vec  # (N,)
        months = np.arange(t, dtype=np.int32)[np.newaxis, :]  # (1, T)
        active = months < remaining_months[:, np.newaxis]  # (N, T)

        # Gross premium per in-force policy (annuity-due timing), zeroed post-term.
        gross_prem = monthly_prem_vec[:, np.newaxis] * active  # (N, T)

        # Expenses per in-force policy: ongoing maintenance, plus the one-time
        # acquisition cost in month 0 for genuine new business (duration 0 at the
        # valuation date) — the same seasoning notion project() uses (ADR-074).
        maint_monthly = self.config.maintenance_cost_per_policy_per_year / 12.0
        expenses = np.zeros((n, t), dtype=np.float64)
        if maint_monthly > 0.0:
            expenses += maint_monthly * active
        acq_cost = self.config.acquisition_cost_per_policy
        if acq_cost > 0.0:
            new_biz_mask = (
                self.inforce.duration_inforce_vec_at(self.config.valuation_date) == 0
            )  # (N,)
            expenses[new_biz_mask, 0] += acq_cost

        # Backward recursion. next_dr carries DR_{t+1}; DR_T = 0.
        dr = np.zeros((n, t), dtype=np.float64)
        next_dr = np.zeros(n, dtype=np.float64)
        for month in range(t - 1, -1, -1):
            survive = (1.0 - q[:, month]) * (1.0 - w[:, month])  # (N,)
            dr[:, month] = (expenses[:, month] - gross_prem[:, month]) + v_monthly * (
                q[:, month] * face_vec + survive * next_dr
            )
            next_dr = dr[:, month]
        return dr

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

        # Active mask: True while the policy term has not expired, shape (N, T)
        remaining_months = self.inforce.remaining_term_months_vec  # (N,)
        months = np.arange(t, dtype=np.int32)[np.newaxis, :]  # (1, T)
        active = months < remaining_months[:, np.newaxis]  # (N, T)

        # Cash flow arrays, shape (N, T)
        # Premiums: lx * monthly_premium, zeroed after term expiry
        ser_premiums = lx * monthly_prem_vec[:, np.newaxis] * active  # (N, T)

        # Death claims: lx_t * q_t * face (deaths during month t)
        # q is already zeroed after term expiry in _build_rate_arrays
        ser_claims = lx * q * face_vec[:, np.newaxis]  # (N, T)

        # Lapse surrenders: term life has no cash surrender value, so no
        # direct cash outflow on lapse. The reserve release from lapses is
        # already captured in reserve_increase = delta(lx * V) since lx
        # incorporates lapse decrements. Setting lapse_surrenders to zero
        # preserves the NCF identity without double-counting.
        ser_lapses = np.zeros((n, t), dtype=np.float64)

        # Lapse count (informational, not part of NCF): expected lapse exits
        # lapse_count_t = sum_i [lx_i,t * w_i,t] — number of policies lapsing
        ser_lapse_count = lx * w  # (N, T)

        # Expenses: acquisition cost (month 0) + ongoing maintenance
        ser_expenses = np.zeros((n, t), dtype=np.float64)
        acq_cost = self.config.acquisition_cost_per_policy
        maint_cost_monthly = self.config.maintenance_cost_per_policy_per_year / 12.0
        if acq_cost > 0.0:
            # Acquisition cost only for genuine new business — zero months in
            # force at the projection valuation date. Derived from the dates,
            # matching the seasoning notion used by the rate lookups
            # (ADR-074), not the stored duration_inforce column.
            new_biz_mask = (
                self.inforce.duration_inforce_vec_at(self.config.valuation_date) == 0
            )  # (N,)
            ser_expenses[new_biz_mask, 0] += acq_cost
        if maint_cost_monthly > 0.0:
            ser_expenses += lx * maint_cost_monthly * active  # ongoing per in-force policy

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
        agg_lapse_count = ser_lapse_count.sum(axis=0)

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
            lapse_count=agg_lapse_count,
        )

        if seriatim:
            result.seriatim_premiums = ser_premiums
            result.seriatim_claims = ser_claims
            result.seriatim_reserves = reserves
            result.seriatim_lx = lx

        return result

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
from polaris_re.assumptions.mortality import MortalityTable
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import ProductType
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.products.base_product import BaseProduct
from polaris_re.utils.date_utils import projection_date_index

__all__ = ["WholeLife", "WholeLifeVariant"]

#: Below this premium-paying period (in years) the CRVM expense allowance under
#: Full Preliminary Term exceeds the 20-payment-whole-life cap, so FPT is no
#: longer exact CRVM. WholeLife only computes CRVM for whole-life pay and
#: limited-pay >= this many years; shorter pay periods raise (see ADR-089).
_CRVM_MIN_PAY_YEARS_FOR_FPT = 20


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

    #: WholeLife supports the net level premium reserve (default), the CRVM
    #: modified reserve, and the VM-20 simplified reserve. CRVM is implemented as
    #: Full Preliminary Term (FPT) with a **prospective valuation to omega** (max
    #: age), which both grades in the first-year expense allowance and closes the
    #: horizon-edge terminal-reserve artefact of the net-premium path (ADR-089).
    #: FPT is exact CRVM for whole-life pay and limited-pay >= 20 years; shorter
    #: pay periods (where the 20-pay expense-allowance cap binds) raise via the
    #: dispatch guard. VM20 is the simplified VM-20 reserve ``max(NPR, DR)`` with
    #: the CRVM reserve as the net-premium-reserve floor and a deterministic
    #: gross-premium reserve valued **to omega** (so the DR does not collapse at
    #: the projection horizon — the WL analogue of the finite-horizon Term DR;
    #: ADR-091). GAAP (FAS 60) is the net **level** premium benefit reserve on
    #: the locked-in best-estimate mortality plus PADs, valued prospectively to
    #: omega like CRVM/VM-20 so it does not collapse at the horizon edge
    #: (ADR-128, Reserve-Basis Exactness Slice 4).
    _supported_reserve_bases = frozenset(
        {ReserveBasis.NET_PREMIUM, ReserveBasis.CRVM, ReserveBasis.VM20, ReserveBasis.GAAP}
    )

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

        # Per-policy substandard rating (ADR-042):
        # q_eff = q_base * multiplier + flat_extra / 1000 / 12, capped at 1.0.
        multiplier_vec = self.inforce.mortality_multiplier_vec  # (N,)
        flat_extra_monthly_vec = self.inforce.flat_extra_vec / 12000.0  # (N,) monthly

        for month in range(t):
            current_durations = duration_inforce + month
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment
            current_ages = np.minimum(current_ages, self.assumptions.mortality.max_age)

            q_monthly_col = self._lookup_qx_column(
                self.assumptions.mortality, current_ages, current_durations
            )

            w_monthly_col = self.assumptions.lapse.get_lapse_vector(current_durations)

            # Apply per-policy substandard rating (ADR-042) before the max-age
            # override so that max-age certain-death still forces q = 1.0.
            q_monthly_col = np.minimum(q_monthly_col * multiplier_vec + flat_extra_monthly_vec, 1.0)

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
        Compute policy reserves, shape (N, T), on the configured basis.

        Dispatches on ``config.reserve_basis``:

        * ``NET_PREMIUM`` (default) — net level premium reserve via backward
          recursion from a one-period prospective terminal estimate. This is
          the historical path and is left byte-identical.
        * ``CRVM`` — Commissioners Reserve Valuation Method, implemented as Full
          Preliminary Term with a prospective valuation to omega (see
          :meth:`_compute_reserves_crvm`). The to-omega valuation closes the
          horizon-edge terminal-reserve artefact (ARCHITECTURE §4) that the
          net-premium recursion exhibits when the projection ends before omega.

        * ``VM20`` — VM-20 simplified reserve ``max(NPR, DR)`` (see
          :meth:`_compute_reserves_vm20`). NPR reuses the to-omega CRVM reserve;
          DR is the to-omega deterministic gross-premium reserve.
        * ``GAAP`` — US GAAP (FAS 60) net **level** premium benefit reserve on
          locked-in best-estimate assumptions plus PADs, valued prospectively to
          omega (see :meth:`_compute_reserves_gaap`).

        Unimplemented bases raise ``PolarisComputationError`` via the guard.
        """
        basis = self._check_reserve_basis()
        if basis is ReserveBasis.CRVM:
            return self._compute_reserves_crvm()
        if basis is ReserveBasis.VM20:
            return self._compute_reserves_vm20()
        if basis is ReserveBasis.GAAP:
            return self._compute_reserves_gaap()
        return self._compute_reserves_net_premium()

    def _compute_reserves_net_premium(self) -> np.ndarray:
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

    # --- GAAP (FAS 60 net level premium, prospective to omega) --------

    def _compute_reserves_gaap(self) -> np.ndarray:
        """
        US GAAP (FAS 60) net level premium benefit reserve, shape (N, T).

        FAS 60 (ASC 944) values a traditional (non-participating) life reserve
        as a **net level premium reserve on locked-in best-estimate assumptions
        plus explicit provisions for adverse deviation (PADs)**. The WholeLife
        implementation mirrors the Slice-3 TermLife GAAP basis
        (``TermLife._compute_reserves_gaap``, ADR-127) — a net premium reserve on
        a *margined* best estimate — but is valued **prospectively to omega**
        (like :meth:`_compute_reserves_crvm`), so it does **not** collapse at the
        projection horizon the way the net-premium one-period terminal estimate
        does. Concretely:

        * **Mortality** is the projection best-estimate valuation q built to omega
          on the *projection* mortality table (:meth:`_build_valuation_mortality`
          with ``table=None`` — the same per-(sex, smoker) lookup, per-policy
          substandard rating and max-age certain-death forcing as the projection,
          mortality-only) scaled by the mortality PAD ``config.gaap_mortality_pad``
          and capped at 1.0. Unlike the statutory bases (CRVM / VM-20 NPR), GAAP
          does **not** read ``assumptions.valuation_mortality`` — FAS 60 is a
          best-estimate + PAD basis, not a prescribed static statutory one
          (ADR-128; the guardrail in ``docs/PLAN_reserve_basis_exactness.md``).
        * **Interest** is the locked-in GAAP discount rate
          ``config.gaap_valuation_rate`` (= ``effective_valuation_rate`` less the
          interest PAD ``config.gaap_interest_margin``, floored at 0).
        * **Premium** is a single net **level** premium over the premium-paying
          window (the equivalence-principle premium, funding the to-omega
          benefit) — not the year-1/renewal split of CRVM's Full Preliminary
          Term. FAS 60 uses a level valuation premium; the FPT expense-allowance
          modification is a statutory (CRVM) device, not a GAAP one.

        With both PADs neutral (``gaap_mortality_pad == 1.0`` and
        ``gaap_interest_margin == 0.0``) this reduces to the locked-in
        best-estimate net level premium reserve valued to omega — the closed-form
        identity pinned in the tests. A positive mortality PAD or interest margin
        raises the accumulation-phase reserve (more conservative), as
        adverse-deviation margins must.

        Note: WholeLife does not model mortality improvement on any basis (it is
        not applied in ``_build_rate_arrays``), so — unlike TermLife GAAP — there
        is no improvement to lock in here; the best estimate is the projection
        table as looked up. The valuation-table independence is the operative
        guardrail.
        """
        n = self.inforce.n_policies
        t_proj = self.config.projection_months
        # Best estimate → projection table (NOT the prescribed statutory table);
        # its omega sets the to-omega valuation grid.
        t_val = self._valuation_months_to_omega(None)

        pad = self.config.gaap_mortality_pad
        i_gaap = self.config.gaap_valuation_rate
        v_monthly = (1.0 + i_gaap) ** (-1.0 / 12.0)

        q_be = self._build_valuation_mortality(t_val, None)  # (N, t_val), mortality-only
        q_val = np.minimum(q_be * pad, 1.0)  # apply mortality PAD; q=1.0 at omega stays 1.0
        face_vec = self.inforce.face_amount_vec  # (N,)

        # Premium-paying months per policy (whole-life pay runs to omega).
        if self.premium_payment_years is not None:
            premium_months = np.full(n, self.premium_payment_years * 12, dtype=np.int64)
        else:
            premium_months = np.full(n, t_val, dtype=np.int64)

        # Mortality-only survival and time-0 PV building blocks (as in CRVM).
        tpx = np.ones((n, t_val), dtype=np.float64)
        for month in range(1, t_val):
            tpx[:, month] = tpx[:, month - 1] * (1.0 - q_val[:, month - 1])

        v_powers = v_monthly ** np.arange(t_val, dtype=np.float64)  # (t_val,)
        v_powers_plus1 = v_monthly ** np.arange(1, t_val + 1, dtype=np.float64)

        benefit_pv = v_powers_plus1[np.newaxis, :] * tpx * q_val * face_vec[:, np.newaxis]  # (N,T)
        annuity_pv = v_powers[np.newaxis, :] * tpx  # (N, t_val)

        # Single net LEVEL premium over the premium-paying window (months
        # 0 .. premium_months-1): P = APV(benefits to omega) / APV(premium annuity).
        months = np.arange(t_val)
        prem_window = months[np.newaxis, :] < premium_months[:, np.newaxis]  # (N, t_val)
        apv_benefits = benefit_pv.sum(axis=1)  # (N,) benefits to omega
        apv_prem_annuity = (annuity_pv * prem_window).sum(axis=1)  # (N,)
        p_net = np.where(apv_prem_annuity > 0.0, apv_benefits / apv_prem_annuity, 0.0)  # (N,)
        p_s = np.where(prem_window, p_net[:, np.newaxis], 0.0)  # (N, t_val)

        # Prospective reserve: reverse-cumulative PV of (benefits - premiums),
        # brought to time t per survivor by dividing by v^t * tpx_t.
        future_benefits = np.cumsum(benefit_pv[:, ::-1], axis=1)[:, ::-1]  # sum_{s>=t} f_s
        future_premiums = np.cumsum((p_s * annuity_pv)[:, ::-1], axis=1)[
            :, ::-1
        ]  # sum_{s>=t} P g_s
        discount_to_t = v_powers[np.newaxis, :] * tpx  # v^t * tpx_t
        with np.errstate(divide="ignore", invalid="ignore"):
            reserves_val = np.where(
                discount_to_t > 0.0,
                (future_benefits - future_premiums) / discount_to_t,
                0.0,
            )

        reserves = np.maximum(reserves_val[:, :t_proj], 0.0)
        return reserves

    # --- CRVM (Full Preliminary Term, prospective to omega) -----------

    def _valuation_months_to_omega(self, max_age: int | None = None) -> int:
        """
        Number of monthly valuation steps needed to value every policy to omega.

        Whole-life reserves are prospective to the end of the mortality table
        (max age). The CRVM valuation grid must therefore run to omega for the
        *youngest* in-force policy, independent of the projection horizon. The
        result is floored at the projection horizon so the (N, T) reserve slice
        is always available. ``max_age`` selects the omega of the table being
        valued on (the prescribed statutory table for CRVM when
        ``assumptions.valuation_mortality`` is set, ADR-125); it defaults to
        the projection table's omega.
        """
        attained_ages = self.inforce.attained_age_vec_at(self.config.valuation_date)  # (N,)
        if max_age is None:
            max_age = self.assumptions.mortality.max_age
        youngest = int(attained_ages.min())
        # +1 year of margin so q is forced to 1.0 (certain death) and tpx -> 0
        # strictly inside the grid for every policy.
        months_to_omega = (max_age - youngest + 2) * 12
        return max(months_to_omega, self.config.projection_months)

    def _build_valuation_mortality(
        self, t_val: int, table: MortalityTable | None = None
    ) -> np.ndarray:
        """
        Monthly mortality-only rate array q for valuation, shape (N, t_val).

        Mirrors the mortality logic of :meth:`_build_rate_arrays` (per
        (sex, smoker) lookup, per-policy substandard rating, max-age forcing of
        q = 1.0) but (a) extends to ``t_val`` months — out to omega rather than
        the projection horizon — and (b) carries **no lapse**, because a
        per-survivor valuation reserve is mortality-only. Over the first
        ``projection_months`` columns it returns exactly the same q values as
        :meth:`_build_rate_arrays` (verified by a regression test).

        ``table`` selects the mortality table valued on — the prescribed
        statutory table for CRVM / the VM-20 NPR when
        ``assumptions.valuation_mortality`` is set (ADR-125). It defaults to
        the projection table (the historical behaviour, and always the choice
        for the VM-20 deterministic reserve, which is anticipated-experience).
        """
        if table is None:
            table = self.assumptions.mortality
        n = self.inforce.n_policies
        q = np.zeros((n, t_val), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec_at(self.config.valuation_date)  # (N,)
        attained_ages = self.inforce.attained_age_vec_at(self.config.valuation_date)  # (N,)

        multiplier_vec = self.inforce.mortality_multiplier_vec  # (N,)
        flat_extra_monthly_vec = self.inforce.flat_extra_vec / 12000.0  # (N,) monthly

        max_age = table.max_age

        for month in range(t_val):
            current_durations = duration_inforce + month
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment
            current_ages_capped = np.minimum(current_ages, max_age)

            q_monthly_col = self._lookup_qx_column(table, current_ages_capped, current_durations)
            q_monthly_col = np.minimum(q_monthly_col * multiplier_vec + flat_extra_monthly_vec, 1.0)

            # At/after max age the policy must terminate — certain death.
            at_max_age = current_ages >= max_age
            q_monthly_col = np.where(at_max_age, 1.0, q_monthly_col)

            q[:, month] = q_monthly_col

        return q

    def _compute_crvm_modified_premiums(
        self,
        q_val: np.ndarray,
        v_monthly: float,
        premium_months: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        CRVM (Full Preliminary Term) modified valuation net premiums, shape (N,).

        Splits each policy into year 1 (months 0..11) and renewal (months 12..)
        and solves each segment on the equivalence principle, valued to omega:

            alpha = APV(year-1 benefits)  / APV(year-1 annuity-due)
            beta  = APV(renewal benefits) / APV(renewal-premium annuity-due)

        Benefits run to omega; the renewal-premium annuity runs only over the
        premium-paying months (12 .. ``premium_months`` - 1), so limited-pay
        whole life concentrates beta over the pay period while still funding the
        full to-omega benefit. All APVs use mortality-only survival ``tpx`` so
        that ``alpha * ad_year1 + beta * ad_renewal == APV(all benefits)`` and
        hence the prospective reserve ``0V = 0`` (the FPT identity).
        """
        n, t_val = q_val.shape
        face_vec = self.inforce.face_amount_vec  # (N,)

        tpx = np.ones((n, t_val), dtype=np.float64)
        for month in range(1, t_val):
            tpx[:, month] = tpx[:, month - 1] * (1.0 - q_val[:, month - 1])

        v_powers = v_monthly ** np.arange(t_val, dtype=np.float64)  # v^0 .. v^(t_val-1)
        v_powers_plus1 = v_monthly ** np.arange(1, t_val + 1, dtype=np.float64)

        benefit_pv = v_powers_plus1[np.newaxis, :] * tpx * q_val * face_vec[:, np.newaxis]  # (N,T)
        annuity_pv = v_powers[np.newaxis, :] * tpx  # (N, t_val)

        months = np.arange(t_val)
        year1 = months < 12  # (t_val,)
        # Renewal-premium window is per policy (limited pay): months 12..prem-1.
        renewal_prem = (months[np.newaxis, :] >= 12) & (
            months[np.newaxis, :] < premium_months[:, np.newaxis]
        )  # (N, t_val)

        a_year1 = benefit_pv[:, year1].sum(axis=1)  # (N,)
        ad_year1 = annuity_pv[:, year1].sum(axis=1)  # (N,)
        a_renewal = benefit_pv[:, months >= 12].sum(axis=1)  # (N,) benefits to omega
        ad_renewal_prem = (annuity_pv * renewal_prem).sum(axis=1)  # (N,) premium annuity

        alpha = np.where(ad_year1 > 0.0, a_year1 / ad_year1, 0.0)
        beta = np.where(ad_renewal_prem > 0.0, a_renewal / ad_renewal_prem, 0.0)
        return alpha, beta

    def _compute_reserves_crvm(self) -> np.ndarray:
        """
        CRVM modified reserve via Full Preliminary Term, prospective to omega.

        The reserve at month t is the per-survivor present value of future
        benefits less future modified net premiums, both valued to omega:

            V_t = [ sum_{s>=t} f_s - sum_{s>=t} P_s * g_s ] / (v^t * tpx_t)

        where ``f_s`` is the time-0 PV of the death benefit in month s, ``g_s``
        the time-0 PV of a $1 survival annuity payment in month s, and the
        modified premium ``P_s`` is alpha in months 0..11 and beta over the
        renewal-premium window. Because the valuation always runs to omega the
        reserve increases monotonically toward the face amount — it does **not**
        collapse at the projection horizon the way the net-premium recursion's
        one-period terminal estimate does (the artefact this slice closes).

        FPT is exact CRVM only while the expense allowance stays within the
        20-payment-whole-life cap, which holds for whole-life pay and
        limited-pay >= 20 years. Shorter pay periods raise rather than ship a
        knowingly capped-but-uncapped reserve (ADR-089).
        """
        if (
            self.premium_payment_years is not None
            and self.premium_payment_years < _CRVM_MIN_PAY_YEARS_FOR_FPT
        ):
            raise PolarisComputationError(
                "CRVM for WholeLife is implemented as Full Preliminary Term, "
                f"which is exact only for premium-paying periods >= "
                f"{_CRVM_MIN_PAY_YEARS_FOR_FPT} years. For premium_payment_years="
                f"{self.premium_payment_years} the 20-payment-whole-life "
                "expense-allowance cap binds and is not yet implemented "
                "(see ADR-089 / docs/PLAN_reserve_basis.md). Use NET_PREMIUM or "
                "a pay period >= 20 years."
            )

        n = self.inforce.n_policies
        t_proj = self.config.projection_months
        # CRVM values on the prescribed statutory table when one is set
        # (ADR-125), including its omega; default is the projection table.
        stat_table = self.assumptions.valuation_mortality
        t_val = self._valuation_months_to_omega(None if stat_table is None else stat_table.max_age)

        i_val = self.config.effective_valuation_rate
        v_monthly = (1.0 + i_val) ** (-1.0 / 12.0)

        q_val = self._build_valuation_mortality(t_val, stat_table)  # (N, t_val)
        face_vec = self.inforce.face_amount_vec  # (N,)

        # Premium-paying months per policy (whole-life pay runs to omega).
        if self.premium_payment_years is not None:
            premium_months = np.full(n, self.premium_payment_years * 12, dtype=np.int64)
        else:
            premium_months = np.full(n, t_val, dtype=np.int64)

        alpha, beta = self._compute_crvm_modified_premiums(q_val, v_monthly, premium_months)

        # Mortality-only survival and time-0 PV building blocks.
        tpx = np.ones((n, t_val), dtype=np.float64)
        for month in range(1, t_val):
            tpx[:, month] = tpx[:, month - 1] * (1.0 - q_val[:, month - 1])

        v_powers = v_monthly ** np.arange(t_val, dtype=np.float64)  # (t_val,)
        v_powers_plus1 = v_monthly ** np.arange(1, t_val + 1, dtype=np.float64)

        f = v_powers_plus1[np.newaxis, :] * tpx * q_val * face_vec[:, np.newaxis]  # (N, t_val)
        g = v_powers[np.newaxis, :] * tpx  # (N, t_val)

        # Modified premium P_s per month: alpha (s<12), beta over the renewal
        # premium window, 0 once premiums cease (limited pay).
        months = np.arange(t_val)
        p_s = np.zeros((n, t_val), dtype=np.float64)
        p_s[:, months < 12] = alpha[:, np.newaxis]
        renewal_prem = (months[np.newaxis, :] >= 12) & (
            months[np.newaxis, :] < premium_months[:, np.newaxis]
        )
        p_s = np.where(renewal_prem, beta[:, np.newaxis], p_s)

        # Prospective reserve: reverse-cumulative PV of (benefits - premiums),
        # brought to time t per survivor by dividing by v^t * tpx_t.
        future_benefits = np.cumsum(f[:, ::-1], axis=1)[:, ::-1]  # sum_{s>=t} f_s
        future_premiums = np.cumsum((p_s * g)[:, ::-1], axis=1)[:, ::-1]  # sum_{s>=t} P_s g_s
        discount_to_t = v_powers[np.newaxis, :] * tpx  # v^t * tpx_t
        with np.errstate(divide="ignore", invalid="ignore"):
            reserves_val = np.where(
                discount_to_t > 0.0,
                (future_benefits - future_premiums) / discount_to_t,
                0.0,
            )

        reserves = np.maximum(reserves_val[:, :t_proj], 0.0)
        return reserves

    # --- VM-20 simplified (deterministic reserve / NPR floor, to omega) ----

    def _build_valuation_lapse(self, t_val: int) -> np.ndarray:
        """
        Monthly lapse rate array ``w`` for valuation, shape (N, t_val).

        Mirrors the lapse logic of :meth:`_build_rate_arrays` (duration-based
        lookup, lapse zeroed at/after max age) but extended to ``t_val`` months —
        out to omega rather than the projection horizon. The deterministic
        reserve (unlike the per-survivor CRVM/NPR reserve) is realised under
        **both** decrements, so it needs lapse over the full to-omega grid; over
        the first ``projection_months`` columns it returns exactly the same w
        values as :meth:`_build_rate_arrays` (verified by a regression test).
        """
        n = self.inforce.n_policies
        w = np.zeros((n, t_val), dtype=np.float64)

        duration_inforce = self.inforce.duration_inforce_vec_at(self.config.valuation_date)  # (N,)
        attained_ages = self.inforce.attained_age_vec_at(self.config.valuation_date)  # (N,)
        max_age = self.assumptions.mortality.max_age

        for month in range(t_val):
            current_durations = duration_inforce + month
            age_increment = (current_durations // 12) - (duration_inforce // 12)
            current_ages = attained_ages + age_increment
            w_col = self.assumptions.lapse.get_lapse_vector(current_durations)
            at_max_age = current_ages >= max_age
            w[:, month] = np.where(at_max_age, 0.0, w_col)

        return w

    def _compute_deterministic_reserve(
        self, q_val: np.ndarray, w_val: np.ndarray, v_monthly: float
    ) -> np.ndarray:
        """
        Deterministic gross-premium reserve, shape (N, T) (per in-force policy).

        The WL analogue of the TermLife DR (ADR-090), but valued **prospectively
        to omega** rather than over the finite projection horizon. Whole life has
        no expiry, so a DR computed over the truncated grid with terminal
        ``DR_T = 0`` would collapse at the horizon edge — the same artefact the
        to-omega CRVM valuation (ADR-089) closes. The valuation grid therefore
        runs to omega (:meth:`_valuation_months_to_omega`) and the result is
        sliced back to the projection horizon.

        Conditional on being in force at month ``t``, it is the present value of
        future death benefits and maintenance expenses less future gross
        premiums, under **both** decrements (mortality ``q`` and lapse ``w``):

            DR_t = (E_t - G_t) + v * [ q_t * face
                                       + (1 - q_t) * (1 - w_t) * DR_{t+1} ]

        with terminal ``DR_{omega} = 0`` (q is forced to 1 at max age, so the
        policy is certain to have died by the end of the to-omega grid). ``G_t``
        is the monthly gross premium (zeroed after the limited-pay period, if
        any); ``E_t`` is maintenance per in-force policy, plus the one-time
        acquisition cost in month 0 for genuine new business — matching the cash
        flows :meth:`project` emits. Whole life carries no surrender value here,
        so survivors of both decrements carry the only continuation value.

        The reserve is **not** floored: a well-priced block has DR < 0 in the
        early durations (the policy is an asset), which is what makes the VM-20
        ``max(NPR, DR)`` correctly defer to the NPR floor.
        """
        n, t_val = q_val.shape
        t_proj = self.config.projection_months
        face_vec = self.inforce.face_amount_vec  # (N,)
        monthly_prem_vec = self.inforce.monthly_premium_vec  # (N,)

        months = np.arange(t_val)
        if self.premium_payment_years is not None:
            prem_active = months < self.premium_payment_years * 12  # (t_val,)
        else:
            prem_active = np.ones(t_val, dtype=bool)
        gross_prem = monthly_prem_vec[:, np.newaxis] * prem_active[np.newaxis, :]  # (N, t_val)

        # Expenses per in-force policy: ongoing maintenance to omega, plus the
        # one-time acquisition cost in month 0 for genuine new business (duration
        # 0 at the valuation date) — the same seasoning notion project() uses.
        maint_monthly = self.config.maintenance_cost_per_policy_per_year / 12.0
        expenses = np.zeros((n, t_val), dtype=np.float64)
        if maint_monthly > 0.0:
            expenses += maint_monthly
        acq_cost = self.config.acquisition_cost_per_policy
        if acq_cost > 0.0:
            new_biz_mask = (
                self.inforce.duration_inforce_vec_at(self.config.valuation_date) == 0
            )  # (N,)
            expenses[new_biz_mask, 0] += acq_cost

        # Backward recursion to omega; next_dr carries DR_{t+1}, terminal 0.
        dr = np.zeros((n, t_val), dtype=np.float64)
        next_dr = np.zeros(n, dtype=np.float64)
        for month in range(t_val - 1, -1, -1):
            survive = (1.0 - q_val[:, month]) * (1.0 - w_val[:, month])  # (N,)
            dr[:, month] = (expenses[:, month] - gross_prem[:, month]) + v_monthly * (
                q_val[:, month] * face_vec + survive * next_dr
            )
            next_dr = dr[:, month]

        return dr[:, :t_proj]

    def _compute_reserves_vm20(self) -> np.ndarray:
        """
        VM-20 simplified reserve, shape (N, T): ``max(NPR, DR)`` floored at 0.

        The deterministic path of the US principle-based reserve (no stochastic
        scenarios; PLAN §2). Both components are valued **to omega**:

        * **NPR** is the to-omega CRVM reserve (:meth:`_compute_reserves_crvm`):
          a net-premium reserve with the first-year expense allowance graded in.
          It raises for short limited-pay (< 20 years) via the CRVM guard, so
          VM-20 inherits that limitation. It values on
          ``assumptions.valuation_mortality`` when a prescribed statutory table
          is set (ADR-125).
        * **DR** is the to-omega deterministic gross-premium reserve
          (:meth:`_compute_deterministic_reserve`). It is
          anticipated-experience by definition, so it always values on the
          projection (best-estimate) table, never the prescribed one.

        The NPR grades monotonically toward face (ADR-089), so VM-20 — being at
        least the NPR — does **not** collapse at the projection horizon. For a
        well-priced block the gross premium exceeds the net premium, so DR < NPR
        and the formulaic floor governs (VM20 == CRVM); for an underpriced block
        the realistic DR can exceed the NPR floor and then drives the reserve —
        the deficiency signal a reinsurer relies on.
        """
        npr = self._compute_reserves_crvm()  # raises for short limited-pay
        t_val = self._valuation_months_to_omega()
        i_val = self.config.effective_valuation_rate
        v_monthly = (1.0 + i_val) ** (-1.0 / 12.0)
        q_val = self._build_valuation_mortality(t_val)
        w_val = self._build_valuation_lapse(t_val)
        dr = self._compute_deterministic_reserve(q_val, w_val, v_monthly)
        reserves: np.ndarray = np.maximum(np.maximum(npr, dr), 0.0)
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
        ser_lapse_count = lx * w  # (N, T)

        # Expenses: acquisition cost (month 0) + ongoing maintenance scaled by lx.
        # Whole life has no term expiry, so maintenance applies for the full
        # projection horizon — in-force weighting is handled by lx.
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
            ser_expenses += lx * maint_cost_monthly

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
        agg_lapse_count = ser_lapse_count.sum(axis=0)
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
            lapse_count=agg_lapse_count,
        )

        if seriatim:
            result.seriatim_premiums = ser_premiums
            result.seriatim_claims = ser_claims
            result.seriatim_reserves = reserves
            result.seriatim_lx = lx

        return result

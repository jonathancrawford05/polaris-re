"""
YRTTreaty - Yearly Renewable Term reinsurance treaty engine.

The most common individual life reinsurance structure in North America.
The reinsurer assumes mortality risk only (not lapse or investment risk).

Treaty Mechanics:
-----------------
1. NAR_t = face_amount - reserve_t (Net Amount at Risk)
2. ceded_prem_t = NAR_t * yrt_rate / 1000 * cession_pct (per $1000 NAR)
3. ceded_claim_t = gross_claim_t * cession_pct
4. Reserves stay fully with the cedant (not transferred).

YRT premiums can be billed two ways:

* **Flat rate** (legacy MVP path): ``flat_yrt_rate_per_1000`` is a single
  annual rate per $1,000 NAR. Aggregate in-force face at each time step is
  approximated using the premium runoff ratio.

* **Tabular rate** (Slice 2, ADR-051): ``yrt_rate_table`` is a
  ``YRTRateTable`` indexed by (age, sex, smoker, duration_years). When
  set, ``apply()`` requires an ``InforceBlock`` and computes per-policy
  ceded premiums; if ``gross.seriatim_lx`` and ``gross.seriatim_reserves``
  are populated, NAR is taken per-policy from those arrays. Otherwise
  the engine falls back to a face-weighted average rate applied to the
  aggregate-runoff NAR (the same approximation as the flat path, but with
  rates that drift upward as the block ages).

The two pricing fields are mutually exclusive: setting both raises
``PolarisValidationError`` at construction (PR #36 reviewer guidance —
silent table-wins could mask a copy-paste error in deal config).
"""

from typing import TYPE_CHECKING, Self

import numpy as np
from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.reinsurance.base_treaty import BaseTreaty
from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

if TYPE_CHECKING:
    from polaris_re.core.inforce import InforceBlock

__all__ = ["YRTTreaty"]


class YRTTreaty(PolarisBaseModel, BaseTreaty):
    """
    Yearly Renewable Term reinsurance treaty.

    Transfers mortality risk to the reinsurer via YRT premiums based on
    Net Amount at Risk. Reserves and lapse risk remain with the cedant.
    """

    cession_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Proportion of each policy ceded (e.g. 0.50 = 50%).",
    )
    total_face_amount: float = Field(
        gt=0,
        description=(
            "Total initial in-force face amount for the block ($). "
            "Used to compute aggregate NAR = face * inforce_ratio - reserves."
        ),
    )
    retention_limit: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Maximum face amount retained per policy ($). "
            "Excess above this limit is automatically ceded. "
            "If None, cession_pct applies to full face amount."
        ),
    )
    flat_yrt_rate_per_1000: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Simplified flat annual YRT rate per $1,000 NAR. "
            "Mutually exclusive with `yrt_rate_table`."
        ),
    )
    yrt_rate_table: YRTRateTable | None = Field(
        default=None,
        description=(
            "Tabular YRT rate schedule indexed by (age, sex, smoker, "
            "duration_years). When set, `apply()` requires an InforceBlock "
            "and prefers per-policy seriatim NAR. Mutually exclusive with "
            "`flat_yrt_rate_per_1000`."
        ),
    )
    treaty_name: str | None = Field(default=None, description="Optional treaty identifier.")

    @model_validator(mode="after")
    def _validate_rate_source_exclusive(self) -> Self:
        if self.flat_yrt_rate_per_1000 is not None and self.yrt_rate_table is not None:
            raise PolarisValidationError(
                "YRTTreaty: `flat_yrt_rate_per_1000` and `yrt_rate_table` are "
                "mutually exclusive — set exactly one (or neither, for a "
                "claims-only cession). Both were provided."
            )
        return self

    def apply(
        self,
        gross: CashFlowResult,
        inforce: "InforceBlock | None" = None,
    ) -> tuple[CashFlowResult, CashFlowResult]:
        """
        Apply YRT treaty to gross cash flows.

        Args:
            gross:   GROSS basis CashFlowResult with reserve_balance populated.
            inforce: Optional InforceBlock for policy-level cession overrides.
                     When provided, face-weighted average cession is used
                     instead of treaty-level cession_pct. Required when
                     `yrt_rate_table` is set.

        Returns:
            (net, ceded) CashFlowResult tuple.
        """
        if len(gross.reserve_balance) == 0:
            raise PolarisComputationError(
                "YRT treaty requires reserve_balance in gross CashFlowResult."
            )

        c = self._resolve_cession(self.cession_pct, inforce)

        # Ceded claims: proportional to gross (face-weighted scalar).
        ceded_claims = gross.death_claims * c
        net_claims = gross.death_claims * (1.0 - c)

        # YRT premiums: dispatch on rate source.
        if self.yrt_rate_table is not None:
            if inforce is None:
                raise PolarisComputationError(
                    "YRT treaty with `yrt_rate_table` requires an InforceBlock "
                    "argument for policy-level (age, sex, smoker, duration) "
                    "rate lookups."
                )
            ceded_yrt_premiums, nar = self._compute_tabular_premiums(gross, inforce, c)
        elif self.flat_yrt_rate_per_1000 is not None:
            ceded_yrt_premiums, nar = self._compute_flat_premiums(gross, c)
        else:
            # No rate source: ceded premiums are zero (claims-only cession).
            ceded_yrt_premiums = np.zeros_like(gross.gross_premiums)
            nar = None

        # Net premiums: gross premiums minus YRT ceded premiums
        # In YRT, the cedant keeps gross premiums but pays YRT premiums to reinsurer
        ceded_premiums = ceded_yrt_premiums
        net_premiums = gross.gross_premiums - ceded_premiums

        # Reserves: NOT transferred in YRT
        net_reserve_balance = gross.reserve_balance.copy()
        ceded_reserve_balance = np.zeros_like(gross.reserve_balance)
        net_reserve_inc = gross.reserve_increase.copy()
        ceded_reserve_inc = np.zeros_like(gross.reserve_increase)

        # Expenses: stay with cedant
        net_expenses = gross.expenses.copy()
        ceded_expenses = np.zeros_like(gross.expenses)

        # Lapse surrenders: stay with cedant (no cash values for term)
        net_lapses = gross.lapse_surrenders.copy()
        ceded_lapses = np.zeros_like(gross.lapse_surrenders)

        # Net cash flows
        net_ncf = net_premiums - net_claims - net_lapses - net_expenses - net_reserve_inc
        ceded_ncf = (
            ceded_premiums - ceded_claims - ceded_lapses - ceded_expenses - ceded_reserve_inc
        )

        net = CashFlowResult(
            run_id=gross.run_id,
            valuation_date=gross.valuation_date,
            basis="NET",
            assumption_set_version=gross.assumption_set_version,
            product_type=gross.product_type,
            block_id=gross.block_id,
            projection_months=gross.projection_months,
            time_index=gross.time_index,
            gross_premiums=net_premiums,
            death_claims=net_claims,
            lapse_surrenders=net_lapses,
            expenses=net_expenses,
            reserve_balance=net_reserve_balance,
            reserve_increase=net_reserve_inc,
            net_cash_flow=net_ncf,
        )

        ceded = CashFlowResult(
            run_id=gross.run_id,
            valuation_date=gross.valuation_date,
            basis="CEDED",
            assumption_set_version=gross.assumption_set_version,
            product_type=gross.product_type,
            block_id=gross.block_id,
            projection_months=gross.projection_months,
            time_index=gross.time_index,
            gross_premiums=ceded_premiums,
            death_claims=ceded_claims,
            lapse_surrenders=ceded_lapses,
            expenses=ceded_expenses,
            reserve_balance=ceded_reserve_balance,
            reserve_increase=ceded_reserve_inc,
            net_cash_flow=ceded_ncf,
            nar=nar,
            yrt_premiums=ceded_yrt_premiums,
        )

        return net, ceded

    # ------------------------------------------------------------------
    # Premium computation — flat-rate (legacy)
    # ------------------------------------------------------------------

    def _compute_flat_premiums(
        self, gross: CashFlowResult, c: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Aggregate flat-rate ceded YRT premiums + NAR series, shape (T,)."""
        assert self.flat_yrt_rate_per_1000 is not None
        # Approximate in-force face at each time step using premium runoff
        initial_premium = gross.gross_premiums[0]
        if initial_premium > 0:
            inforce_ratio = gross.gross_premiums / initial_premium
        else:
            inforce_ratio = np.ones_like(gross.gross_premiums)

        total_face_t = self.total_face_amount * inforce_ratio
        nar = np.maximum(total_face_t - gross.reserve_balance, 0.0)
        monthly_rate_per_dollar = self.flat_yrt_rate_per_1000 / 12.0 / 1000.0
        ceded_yrt_premiums = nar * monthly_rate_per_dollar * c
        return ceded_yrt_premiums, nar

    # ------------------------------------------------------------------
    # Premium computation — tabular (ADR-051)
    # ------------------------------------------------------------------

    def _compute_tabular_premiums(
        self,
        gross: CashFlowResult,
        inforce: "InforceBlock",
        c_aggregate: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Tabular YRT ceded premiums and NAR series, shape (T,).

        Prefers the per-policy seriatim path when ``gross.seriatim_lx`` and
        ``gross.seriatim_reserves`` are populated. Falls back to a face-
        weighted-average-rate approximation against aggregate-runoff NAR
        when seriatim arrays are absent.
        """
        assert self.yrt_rate_table is not None
        t = len(gross.gross_premiums)
        n = inforce.n_policies

        # Per-policy table-lookup inputs (constant across t for sex/smoker;
        # vary with t for ages and duration_years).
        face_vec = inforce.face_amount_vec  # (N,) float64
        attained_age_vec = inforce.attained_age_vec_at(gross.valuation_date)  # (N,) int32
        duration_inforce_vec = inforce.duration_inforce_vec_at(gross.valuation_date)  # (N,) int32
        sex_list: list[Sex] = [p.sex for p in inforce.policies]
        smoker_list: list[SmokerStatus] = [p.smoker_status for p in inforce.policies]

        # Pre-compute the per-policy rate matrix R[i, t] (annual $/1000) by
        # iterating once per (sex, smoker) cohort. The (cohort, T) ages and
        # durations are built fully vectorised — no Python loop over months.
        rates_per_1000 = np.zeros((n, t), dtype=np.float64)
        months = np.arange(t, dtype=np.int32)  # (T,)
        unique_combos = set(zip(sex_list, smoker_list, strict=True))
        for sex, smoker in unique_combos:
            cohort_mask = np.array(
                [s == sex and sm == smoker for s, sm in zip(sex_list, smoker_list, strict=True)],
                dtype=bool,
            )
            if not np.any(cohort_mask):
                continue
            cohort_attained_age_vec = attained_age_vec[cohort_mask]  # (N_c,)
            cohort_dur_inforce = duration_inforce_vec[cohort_mask]  # (N_c,)
            n_c = int(cohort_mask.sum())

            # Total months in force at each projection step: shape (N_c, T).
            total_dur_months_2d = cohort_dur_inforce[:, np.newaxis] + months[np.newaxis, :]
            # Age increment vs valuation: each completed year of duration adds
            # one year of age. Subtract the duration_inforce contribution so
            # month 0 of a brand-new policy keeps the base attained age.
            age_increment_2d = (total_dur_months_2d // 12) - (
                cohort_dur_inforce[:, np.newaxis] // 12
            )
            ages_2d = (cohort_attained_age_vec[:, np.newaxis] + age_increment_2d).astype(np.int32)
            # Clamp ages to the table range to avoid lookup errors at the
            # tail of long projections — the rate-table top age is the
            # natural extrapolation cap. Must happen before .ravel() because
            # YRTRateTableArray.get_rate_vector raises on out-of-range ages.
            ages_2d = np.clip(
                ages_2d,
                self.yrt_rate_table.min_age,
                self.yrt_rate_table.max_age,
            )
            durs_2d = (total_dur_months_2d // 12).astype(np.int32)
            cohort_rates = self.yrt_rate_table.get_rate_vector(
                ages_2d.ravel(), sex, smoker, durs_2d.ravel()
            ).reshape(n_c, t)
            rates_per_1000[cohort_mask] = cohort_rates

        monthly_rate_per_dollar = rates_per_1000 / 12.0 / 1000.0  # (N, T)

        if gross.seriatim_lx is not None and gross.seriatim_reserves is not None:
            return self._tabular_premiums_seriatim(
                gross, inforce, face_vec, monthly_rate_per_dollar
            )
        return self._tabular_premiums_aggregate(
            gross, face_vec, monthly_rate_per_dollar, c_aggregate
        )

    def _tabular_premiums_seriatim(
        self,
        gross: CashFlowResult,
        inforce: "InforceBlock",
        face_vec: np.ndarray,
        monthly_rate_per_dollar: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Per-policy NAR * rate * cession, summed across policies."""
        assert gross.seriatim_lx is not None
        assert gross.seriatim_reserves is not None

        lx = gross.seriatim_lx  # (N, T)
        v_per_policy = gross.seriatim_reserves  # (N, T) — raw V (not lx-weighted)
        # Per-policy NAR at time t = face - V (floored at 0); the in-force
        # weighting via lx is applied separately so a fully-lapsed policy
        # contributes nothing.
        nar_per_policy = np.maximum(face_vec[:, np.newaxis] - v_per_policy, 0.0)
        # Effective per-policy cession (treaty default if policy override absent).
        eff_cession = inforce.effective_cession_vec(self.cession_pct)  # (N,)
        ceded_per_policy = (
            lx * nar_per_policy * monthly_rate_per_dollar * eff_cession[:, np.newaxis]
        )
        ceded_yrt_premiums = ceded_per_policy.sum(axis=0)
        # Aggregate NAR series for reporting parity with the flat path:
        # in-force-weighted NAR (so it lines up with what the rates were
        # applied to).
        nar_series = (lx * nar_per_policy).sum(axis=0)
        return ceded_yrt_premiums, nar_series

    def _tabular_premiums_aggregate(
        self,
        gross: CashFlowResult,
        face_vec: np.ndarray,
        monthly_rate_per_dollar: np.ndarray,
        c_aggregate: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Face-weighted average rate applied to aggregate-runoff NAR.

        Used when seriatim arrays are absent. Loses per-policy lx weighting
        but preserves the headline aging behaviour at the cohort level.
        """
        # Aggregate runoff (same approximation as the flat path).
        initial_premium = gross.gross_premiums[0]
        if initial_premium > 0:
            inforce_ratio = gross.gross_premiums / initial_premium
        else:
            inforce_ratio = np.ones_like(gross.gross_premiums)
        total_face_t = self.total_face_amount * inforce_ratio
        nar = np.maximum(total_face_t - gross.reserve_balance, 0.0)

        # Face-weighted avg per-dollar monthly rate at each t.
        total_face = face_vec.sum()
        if total_face <= 0:
            avg_rate_t = np.zeros_like(gross.gross_premiums)
        else:
            avg_rate_t = (face_vec[:, np.newaxis] * monthly_rate_per_dollar).sum(
                axis=0
            ) / total_face
        ceded_yrt_premiums = nar * avg_rate_t * c_aggregate
        return ceded_yrt_premiums, nar

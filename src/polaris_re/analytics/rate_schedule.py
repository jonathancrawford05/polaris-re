"""
YRT Rate Schedule Generator — solve for YRT rates per $1,000 NAR that
achieve a target IRR across an age/sex/smoker/duration grid.

This produces the actual deliverable reinsurers send to cedants: a table
of rates by age, sex, smoker status, and policy term, rather than just
an IRR number.

Algorithm:
    For each (issue_age, sex, smoker, policy_term) combination:
    1. Create a single-policy InforceBlock
    2. Project via TermLife
    3. Binary search (brentq) for the flat YRT rate per $1,000 NAR
       that makes IRR = target_irr
"""

import numpy as np
import polars as pl
from scipy.optimize import brentq

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray

__all__ = ["YRTRateSchedule"]


class YRTRateSchedule:
    """
    Solve for YRT rates per $1,000 that achieve a target IRR.

    For each combination in the specified grid, runs the full pricing
    pipeline (projection → treaty → profit test) and uses root-finding
    to determine the rate that exactly hits the target IRR.
    """

    def __init__(
        self,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
        target_irr: float = 0.10,
        reference_face: float = 1_000_000.0,
        reference_premium_rate: float = 5.0,
        cession_pct: float = 1.0,
    ) -> None:
        """
        Args:
            assumptions:             Assumptions for projection.
            config:                  Projection configuration.
            target_irr:              Target annual IRR (e.g. 0.10 = 10%).
            reference_face:          Face amount for synthetic single policy ($).
            reference_premium_rate:  Gross annual premium per $1,000 face.
            cession_pct:             Cession percentage for YRT treaty.
        """
        self.assumptions = assumptions
        self.config = config
        self.target_irr = target_irr
        self.reference_face = reference_face
        self.reference_premium_rate = reference_premium_rate
        self.cession_pct = cession_pct

    def _make_policy(
        self,
        issue_age: int,
        sex: Sex,
        smoker_status: SmokerStatus,
        policy_term: int,
    ) -> Policy:
        """Create a synthetic single policy for rate solving."""
        premium = self.reference_face / 1_000 * self.reference_premium_rate
        return Policy(
            policy_id=f"RATE_{issue_age}_{sex.value}_{smoker_status.value}_{policy_term}",
            issue_age=issue_age,
            attained_age=issue_age,
            sex=sex,
            smoker_status=smoker_status,
            underwriting_class="STANDARD",
            face_amount=self.reference_face,
            annual_premium=premium,
            product_type=ProductType.TERM,
            policy_term=policy_term,
            duration_inforce=0,
            reinsurance_cession_pct=self.cession_pct,
            issue_date=self.config.valuation_date,
            valuation_date=self.config.valuation_date,
        )

    @staticmethod
    def _reinsurer_view(ceded: CashFlowResult) -> CashFlowResult:
        """Re-label CEDED cash flows as GROSS so ProfitTester accepts them.

        The ceded CashFlowResult already contains the reinsurer's cash flows
        (YRT premiums received, claims paid).  ProfitTester rejects CEDED
        basis, so we wrap it as GROSS — conceptually this *is* the reinsurer's
        gross business.
        """
        return CashFlowResult(
            run_id=ceded.run_id,
            valuation_date=ceded.valuation_date,
            basis="GROSS",
            assumption_set_version=ceded.assumption_set_version,
            product_type=ceded.product_type,
            block_id=ceded.block_id,
            projection_months=ceded.projection_months,
            time_index=ceded.time_index,
            gross_premiums=ceded.gross_premiums,
            death_claims=ceded.death_claims,
            lapse_surrenders=ceded.lapse_surrenders,
            expenses=ceded.expenses,
            reserve_balance=ceded.reserve_balance,
            reserve_increase=ceded.reserve_increase,
            net_cash_flow=ceded.net_cash_flow,
        )

    def _compute_irr_for_rate(
        self,
        gross: CashFlowResult,
        yrt_rate: float,
    ) -> float | None:
        """Compute reinsurer IRR for a given flat YRT rate per $1,000."""
        from polaris_re.analytics.profit_test import ProfitTester

        treaty = YRTTreaty(
            cession_pct=self.cession_pct,
            total_face_amount=self.reference_face,
            flat_yrt_rate_per_1000=yrt_rate,
        )
        _net, ceded = treaty.apply(gross)
        reinsurer = self._reinsurer_view(ceded)

        try:
            tester = ProfitTester(reinsurer, hurdle_rate=self.target_irr)
            result = tester.run()
            return result.irr
        except Exception:
            return None

    def _solve_rate(
        self,
        gross: CashFlowResult,
        lower: float = 0.01,
        upper: float = 50.0,
    ) -> float | None:
        """
        Binary search for the YRT rate that achieves the target IRR.

        Uses the NPV function directly: find rate where NPV(target_irr) = 0.

        Args:
            gross: GROSS basis cash flows for the single policy.
            lower: Lower bound for rate search (per $1,000).
            upper: Upper bound for rate search (per $1,000).

        Returns:
            Solved rate per $1,000, or None if no solution found.
        """
        from polaris_re.analytics.profit_test import ProfitTester

        def npv_at_rate(rate: float) -> float:
            treaty = YRTTreaty(
                cession_pct=self.cession_pct,
                total_face_amount=self.reference_face,
                flat_yrt_rate_per_1000=rate,
            )
            _net, ceded = treaty.apply(gross)
            reinsurer = self._reinsurer_view(ceded)
            tester = ProfitTester(reinsurer, hurdle_rate=self.target_irr)
            result = tester.run()
            return result.pv_profits

        try:
            # Check that the function changes sign in the bracket
            f_low = npv_at_rate(lower)
            f_high = npv_at_rate(upper)

            if f_low * f_high > 0:
                # No sign change — try expanding the bracket
                if f_low > 0 and f_high > 0:
                    # Both positive: rate is above upper bound; extend upper
                    upper *= 5
                    f_high = npv_at_rate(upper)
                elif f_low < 0 and f_high < 0:
                    # Both negative: rate is below lower bound; reduce lower
                    lower /= 10
                    f_low = npv_at_rate(lower)

                if f_low * f_high > 0:
                    return None

            solved_rate = brentq(npv_at_rate, lower, upper, xtol=1e-6, maxiter=100)
            return float(solved_rate)
        except (ValueError, RuntimeError):
            return None

    def generate(
        self,
        ages: list[int] | None = None,
        sexes: list[Sex] | None = None,
        smoker_statuses: list[SmokerStatus] | None = None,
        policy_term: int = 20,
    ) -> pl.DataFrame:
        """
        Generate a YRT rate schedule for the specified grid.

        Args:
            ages:             List of issue ages (default: 25-65 step 5).
            sexes:            List of Sex values (default: [MALE, FEMALE]).
            smoker_statuses:  List of SmokerStatus (default: [NON_SMOKER, SMOKER]).
            policy_term:      Policy term in years (default: 20).

        Returns:
            Polars DataFrame with columns:
            issue_age, sex, smoker_status, policy_term, rate_per_1000, irr
        """
        if ages is None:
            ages = list(range(25, 66, 5))
        if sexes is None:
            sexes = [Sex.MALE, Sex.FEMALE]
        if smoker_statuses is None:
            smoker_statuses = [SmokerStatus.NON_SMOKER, SmokerStatus.SMOKER]

        rows: list[dict[str, object]] = []

        for age in ages:
            for sex in sexes:
                for smoker in smoker_statuses:
                    policy = self._make_policy(age, sex, smoker, policy_term)
                    inforce = InforceBlock(policies=[policy])
                    engine = TermLife(inforce, self.assumptions, self.config)
                    gross = engine.project()

                    solved_rate = self._solve_rate(gross)

                    # Verify IRR
                    irr = None
                    if solved_rate is not None:
                        irr_val = self._compute_irr_for_rate(gross, solved_rate)
                        irr = irr_val

                    rows.append(
                        {
                            "issue_age": age,
                            "sex": sex.value,
                            "smoker_status": smoker.value,
                            "policy_term": policy_term,
                            "rate_per_1000": solved_rate
                            if solved_rate is not None
                            else float("nan"),
                            "irr": irr if irr is not None else float("nan"),
                        }
                    )

        return pl.DataFrame(rows)

    def generate_table(
        self,
        ages: list[int] | None = None,
        sexes: list[Sex] | None = None,
        smoker_statuses: list[SmokerStatus] | None = None,
        policy_term: int = 20,
        select_period_years: int = 0,
    ) -> YRTRateTable:
        """
        Solve a per-(age, sex, smoker) flat YRT rate grid and pack it into a
        ``YRTRateTable`` consumable by ``YRTTreaty``.

        Each (sex, smoker) cell of the resulting table is a 2-D array of
        shape ``(n_ages, select_period_years + 1)``. The same per-issue-age
        flat rate fills every duration column in that age's row — i.e. this
        helper produces a step-flat-by-age schedule, not a per-duration
        schedule. Slice 3's CSV ingest is the place where externally-quoted
        rates with true select-period rate variation will live; this method
        is the closed-loop sanity check that a generated table flows back
        through ``YRTTreaty.apply()`` and reproduces the target IRR per cell.

        Default axis grid: ages 25..85 step 5; both sexes; both smoker
        statuses; select_period_years=0 (single ultimate column).

        Args:
            ages:                Issue ages (default: 25..85 step 5).
            sexes:               Sex values (default: [MALE, FEMALE]).
            smoker_statuses:     Smoker statuses (default: [NON_SMOKER, SMOKER]).
            policy_term:         Policy term in years used by the synthetic
                                 single-policy projection (default: 20).
            select_period_years: Number of select columns in the output
                                 table (rates are repeated across columns).

        Returns:
            A populated ``YRTRateTable``.

        Raises:
            PolarisComputationError: If no cells could be solved (rate solver
                returned None for every grid cell).
        """
        if ages is None:
            ages = list(range(25, 86, 5))
        if sexes is None:
            sexes = [Sex.MALE, Sex.FEMALE]
        if smoker_statuses is None:
            smoker_statuses = [SmokerStatus.NON_SMOKER, SmokerStatus.SMOKER]

        sorted_ages = sorted(ages)
        min_age = sorted_ages[0]
        max_age = sorted_ages[-1]
        n_ages = max_age - min_age + 1
        n_cols = select_period_years + 1

        # Build per-(sex, smoker) rate matrices.
        per_cohort: dict[tuple[Sex, SmokerStatus], np.ndarray] = {
            (sex, smoker): np.full((n_ages, n_cols), np.nan, dtype=np.float64)
            for sex in sexes
            for smoker in smoker_statuses
        }

        any_solved = False
        for age in sorted_ages:
            for sex in sexes:
                for smoker in smoker_statuses:
                    policy = self._make_policy(age, sex, smoker, policy_term)
                    inforce = InforceBlock(policies=[policy])
                    engine = TermLife(inforce, self.assumptions, self.config)
                    gross = engine.project()
                    solved = self._solve_rate(gross)
                    if solved is None:
                        continue
                    any_solved = True
                    per_cohort[(sex, smoker)][age - min_age, :] = solved

        if not any_solved:
            raise PolarisComputationError(
                "YRTRateSchedule.generate_table: rate solver returned None "
                "for every grid cell — check assumptions, target_irr, and "
                "the search bracket in _solve_rate()."
            )

        # Forward-fill unsolved (and unrequested) age rows from the nearest
        # solved row below, then back-fill from the row above. NaNs that
        # remain in cohorts where no cell was solved get the global mean —
        # if even that is NaN, raise.
        all_solved_values: list[float] = []
        for matrix in per_cohort.values():
            mask = ~np.isnan(matrix[:, 0])
            if mask.any():
                all_solved_values.extend(matrix[mask, 0].tolist())
        global_mean = float(np.mean(all_solved_values)) if all_solved_values else float("nan")

        cohort_arrays: dict[tuple[Sex, SmokerStatus], YRTRateTableArray] = {}
        for (sex, smoker), matrix in per_cohort.items():
            col0 = matrix[:, 0].copy()
            # Forward-fill
            last = np.nan
            for i in range(n_ages):
                if np.isnan(col0[i]):
                    col0[i] = last
                else:
                    last = col0[i]
            # Back-fill remaining leading NaNs
            last = np.nan
            for i in range(n_ages - 1, -1, -1):
                if np.isnan(col0[i]):
                    col0[i] = last
                else:
                    last = col0[i]
            # Anything still NaN: use the global mean
            col0 = np.where(np.isnan(col0), global_mean, col0)
            filled = np.broadcast_to(col0[:, np.newaxis], (n_ages, n_cols)).copy()
            cohort_arrays[(sex, smoker)] = YRTRateTableArray(
                rates=filled,
                min_age=min_age,
                max_age=max_age,
                select_period=select_period_years,
            )

        return YRTRateTable.from_arrays(
            table_name=f"generated_term{policy_term}_irr{int(self.target_irr * 100)}",
            arrays=cohort_arrays,
        )

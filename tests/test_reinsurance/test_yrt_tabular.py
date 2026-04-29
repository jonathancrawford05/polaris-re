"""
YRT treaty tests for the tabular rate-table consumption path (Slice 2 of 3).

These tests cover the new ``yrt_rate_table`` field on ``YRTTreaty`` and the
per-policy seriatim consumption logic in ``apply()``.

Invariants verified:
  - Constant-rate table reproduces the flat-rate path within float tolerance.
  - Aging block: ceded premiums rise monotonically when rates rise with age.
  - net + ceded == gross for premiums and claims under tabular rates.
  - Backward-compat: flat-rate path is byte-identical when the table is absent.
  - Mutual exclusion: setting both ``flat_yrt_rate_per_1000`` and
    ``yrt_rate_table`` raises ``PolarisValidationError`` at construction.
  - ``inforce=None`` with tabular rates raises a clear error.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance import YRTRateTable, YRTRateTableArray, YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"

# Constant-rate table value used to compare against the flat-rate path.
CONSTANT_RATE_PER_1000 = 2.5


def _make_assumptions() -> AssumptionSet:
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(mortality=mortality, lapse=lapse, version="test-tabular")


def _make_block(policies: list[Policy]) -> InforceBlock:
    return InforceBlock(policies=policies)


def _make_policy(
    policy_id: str = "P1",
    issue_age: int = 40,
    sex: Sex = Sex.MALE,
    smoker: SmokerStatus = SmokerStatus.NON_SMOKER,
    face: float = 1_000_000.0,
    annual_premium: float = 12_000.0,
    cession_pct: float = 0.5,
) -> Policy:
    return Policy(
        policy_id=policy_id,
        issue_age=issue_age,
        attained_age=issue_age,
        sex=sex,
        smoker_status=smoker,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=annual_premium,
        product_type=ProductType.TERM,
        policy_term=20,
        duration_inforce=0,
        reinsurance_cession_pct=cession_pct,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


def _make_constant_table(
    rate_per_1000: float = CONSTANT_RATE_PER_1000,
    min_age: int = 18,
    max_age: int = 90,
    select_period: int = 25,
) -> YRTRateTable:
    """A flat table that should produce ceded premiums equal to the flat-rate path."""
    n_ages = max_age - min_age + 1
    n_cols = select_period + 1
    rates = np.full((n_ages, n_cols), rate_per_1000, dtype=np.float64)
    arr = YRTRateTableArray(
        rates=rates, min_age=min_age, max_age=max_age, select_period=select_period
    )
    return YRTRateTable.from_arrays(
        table_name="constant",
        arrays={(Sex.MALE, SmokerStatus.NON_SMOKER): arr},
    )


def _make_aging_table(
    base_rate: float = 1.0,
    age_slope: float = 0.20,
    duration_slope: float = 0.0,
    min_age: int = 18,
    max_age: int = 90,
    select_period: int = 25,
) -> YRTRateTable:
    """Synthetic age-progressing table: rate rises strictly with attained age."""
    n_ages = max_age - min_age + 1
    n_cols = select_period + 1
    rates = np.zeros((n_ages, n_cols), dtype=np.float64)
    for i in range(n_ages):
        for j in range(n_cols):
            rates[i, j] = base_rate + age_slope * i + duration_slope * j
    arr = YRTRateTableArray(
        rates=rates, min_age=min_age, max_age=max_age, select_period=select_period
    )
    return YRTRateTable.from_arrays(
        table_name="aging",
        arrays={(Sex.MALE, SmokerStatus.NON_SMOKER): arr},
    )


@pytest.fixture()
def assumptions() -> AssumptionSet:
    return _make_assumptions()


@pytest.fixture()
def config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.05,
    )


@pytest.fixture()
def block() -> InforceBlock:
    return _make_block([_make_policy()])


@pytest.fixture()
def gross(block, assumptions, config):
    return TermLife(block, assumptions, config).project(seriatim=True)


@pytest.fixture()
def gross_aggregate(block, assumptions, config):
    """Gross result without seriatim arrays — forces the aggregate-runoff fallback."""
    return TermLife(block, assumptions, config).project(seriatim=False)


# ----------------------------------------------------------------------
# Validation: mutual exclusion + missing inforce
# ----------------------------------------------------------------------


class TestYRTTreatyValidation:
    def test_both_flat_and_table_raises(self) -> None:
        """Setting both flat_yrt_rate_per_1000 and yrt_rate_table is rejected."""
        table = _make_constant_table()
        with pytest.raises(PolarisValidationError, match="mutually exclusive"):
            YRTTreaty(
                cession_pct=0.5,
                total_face_amount=1_000_000.0,
                flat_yrt_rate_per_1000=2.5,
                yrt_rate_table=table,
            )

    def test_table_only_constructs(self) -> None:
        """Tabular-only construction is valid."""
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=_make_constant_table(),
        )
        assert treaty.yrt_rate_table is not None
        assert treaty.flat_yrt_rate_per_1000 is None

    def test_flat_only_constructs(self) -> None:
        """Flat-only construction is valid (backward compat)."""
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.5,
        )
        assert treaty.flat_yrt_rate_per_1000 == 2.5
        assert treaty.yrt_rate_table is None

    def test_neither_constructs(self) -> None:
        """Neither rate set is allowed — yields zero ceded premiums (backward compat)."""
        treaty = YRTTreaty(cession_pct=0.5, total_face_amount=1_000_000.0)
        assert treaty.yrt_rate_table is None
        assert treaty.flat_yrt_rate_per_1000 is None

    def test_table_without_inforce_raises(self, gross) -> None:
        """apply() with a table but no inforce must raise a clear error."""
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=_make_constant_table(),
        )
        with pytest.raises(PolarisComputationError, match=r"(?i)inforce"):
            treaty.apply(gross, inforce=None)


# ----------------------------------------------------------------------
# Backward compatibility: flat-rate path is unchanged
# ----------------------------------------------------------------------


class TestFlatPathUnchanged:
    def test_flat_rate_output_unchanged(self, gross, block) -> None:
        """A pre-existing flat-rate call produces the same output regardless of inforce arg."""
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.5,
        )
        # No inforce supplied (legacy path)
        net_a, ceded_a = treaty.apply(gross)
        # Inforce supplied (Slice 2 should not change flat-path output)
        net_b, ceded_b = treaty.apply(gross, inforce=block)
        np.testing.assert_allclose(ceded_a.gross_premiums, ceded_b.gross_premiums, rtol=1e-12)
        np.testing.assert_allclose(net_a.gross_premiums, net_b.gross_premiums, rtol=1e-12)


# ----------------------------------------------------------------------
# Closed-form: constant-rate table matches the flat-rate path
# ----------------------------------------------------------------------


class TestConstantTableMatchesFlat:
    def test_ceded_premiums_match_flat(self, gross, block) -> None:
        """A flat YRT rate table ($2.5/$1000) yields the same per-policy ceded
        premium series as the flat-rate path within float tolerance."""
        flat_treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=CONSTANT_RATE_PER_1000,
        )
        tabular_treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=_make_constant_table(),
        )
        _net_f, ceded_flat = flat_treaty.apply(gross)
        _net_t, ceded_tab = tabular_treaty.apply(gross, inforce=block)
        # Tolerance is loose: aggregate-runoff vs seriatim-runoff differ slightly,
        # but for a single-policy block the runoff factor is identical so they
        # should match very tightly.
        np.testing.assert_allclose(ceded_tab.gross_premiums, ceded_flat.gross_premiums, rtol=1e-6)

    def test_ncf_additivity_preserved(self, gross, block) -> None:
        """Tabular path preserves net + ceded == gross for premiums and claims."""
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=_make_constant_table(),
        )
        net, ceded = treaty.apply(gross, inforce=block)
        treaty.verify_additivity(gross, net, ceded)


# ----------------------------------------------------------------------
# Aging: ceded premiums rise with attained age under an aging table
# ----------------------------------------------------------------------


class TestAgingBlockRisesWithAge:
    """Verify the PRODUCT_DIRECTION concern is fixed: aging rates must
    increase total ceded premium relative to a same-starting-rate flat table.

    We hold the year-1 rate equal between the flat-counterfactual and the
    aging table, then assert the aging table collects strictly more total
    premium because rates climb with attained age.
    """

    def test_aging_collects_more_premium_than_flat_year1_rate(self, gross, block) -> None:
        # Issue age 40, table min_age 18, base_rate 1.0, age_slope 0.5.
        # Year-1 rate at age 40 = 1.0 + 0.5 * (40 - 18) = 12.0 per $1000.
        flat_year1_rate = 1.0 + 0.5 * (40 - 18)

        flat_table = YRTRateTable.from_arrays(
            table_name="flat-counterfactual",
            arrays={
                (Sex.MALE, SmokerStatus.NON_SMOKER): YRTRateTableArray(
                    rates=np.full((73, 26), flat_year1_rate, dtype=np.float64),
                    min_age=18,
                    max_age=90,
                    select_period=25,
                )
            },
        )
        aging_table = _make_aging_table(base_rate=1.0, age_slope=0.5)

        flat_treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=flat_table,
        )
        aging_treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=aging_table,
        )

        _n_f, ceded_flat = flat_treaty.apply(gross, inforce=block)
        _n_a, ceded_aging = aging_treaty.apply(gross, inforce=block)

        total_flat = float(ceded_flat.gross_premiums.sum())
        total_aging = float(ceded_aging.gross_premiums.sum())
        assert total_aging > total_flat, (
            f"Aging table should collect more total ceded premium than flat "
            f"counterfactual at the same starting rate. "
            f"aging={total_aging:.2f}, flat={total_flat:.2f}"
        )

    def test_implied_per_dollar_rate_rises_with_age(self, gross, block) -> None:
        """The implied annual rate per $1,000 NAR (back-solved from
        aggregate ceded premium / NAR) must rise across early policy years.
        This isolates the rate component from the lx runoff effect.
        """
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=_make_aging_table(base_rate=1.0, age_slope=0.5),
        )
        _net, ceded = treaty.apply(gross, inforce=block)
        # Implied annual rate per $1,000 NAR at month t:
        #   prem_t = NAR_t * (R_t / 12 / 1000) * cession
        # So R_t = prem_t * 12 * 1000 / (NAR_t * cession)
        nar = ceded.nar
        assert nar is not None
        valid = (nar > 0) & (ceded.gross_premiums > 0)
        implied = np.zeros_like(ceded.gross_premiums)
        implied[valid] = ceded.gross_premiums[valid] * 12.0 * 1000.0 / (nar[valid] * 0.5)
        # Look at the implied rate at policy-year boundaries (month 0, 12, 24...)
        ann_rate = np.array([implied[12 * y] for y in range(10) if valid[12 * y]])
        diffs = np.diff(ann_rate)
        assert np.all(diffs > 0), (
            f"Expected strictly rising implied annual rate over first 10 years; "
            f"got rates={ann_rate}, diffs={diffs}"
        )


# ----------------------------------------------------------------------
# Seriatim path vs aggregate fallback
# ----------------------------------------------------------------------


class TestSeriatimVsAggregateFallback:
    def test_aggregate_fallback_used_when_no_seriatim(self, gross_aggregate, block) -> None:
        """When gross has no seriatim arrays, the aggregate-runoff approximation
        is used and ceded premiums are non-zero and finite."""
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=_make_constant_table(),
        )
        _net, ceded = treaty.apply(gross_aggregate, inforce=block)
        assert np.all(np.isfinite(ceded.gross_premiums))
        assert ceded.gross_premiums[0] > 0
        # NCF additivity must still hold on the fallback path.
        treaty.verify_additivity(gross_aggregate, _net, ceded)

    def test_aggregate_fallback_constant_rate_matches_flat(self, gross_aggregate, block) -> None:
        """Aggregate fallback with a constant table reproduces the flat-rate
        path. The face-weighted avg rate collapses to the constant rate, and
        the aggregate-runoff NAR basis is identical to the flat path — so
        ceded premium series must agree within float tolerance.

        This is the closed-form anchor for `_tabular_premiums_aggregate`,
        symmetric to `TestConstantTableMatchesFlat` for the seriatim path.
        """
        flat_treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=CONSTANT_RATE_PER_1000,
        )
        tab_treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            yrt_rate_table=_make_constant_table(),
        )
        _nf, ceded_flat = flat_treaty.apply(gross_aggregate)
        _nt, ceded_tab = tab_treaty.apply(gross_aggregate, inforce=block)
        np.testing.assert_allclose(
            ceded_tab.gross_premiums,
            ceded_flat.gross_premiums,
            rtol=1e-5,
            err_msg=("Aggregate fallback: constant-rate table should match the flat-rate path"),
        )


# ----------------------------------------------------------------------
# Multi-policy block with mixed (sex, smoker)
# ----------------------------------------------------------------------


class TestMultiPolicyMixedCohort:
    def _mixed_block(self) -> InforceBlock:
        return _make_block(
            [
                _make_policy(
                    "MALE_NS",
                    issue_age=40,
                    sex=Sex.MALE,
                    smoker=SmokerStatus.NON_SMOKER,
                    face=500_000.0,
                ),
                _make_policy(
                    "MALE_S", issue_age=45, sex=Sex.MALE, smoker=SmokerStatus.SMOKER, face=500_000.0
                ),
            ]
        )

    def test_smoker_fallback_to_aggregate(self, config) -> None:
        """When the YRT rate table only has UNKNOWN smoker rates, smoker
        policies fall back to the aggregate (UNKNOWN) row via _resolve_key().
        """
        block = self._mixed_block()
        # Build a mortality table with UNKNOWN smoker so the projection
        # accepts both NS and S policies — this isolates the YRT rate-table
        # smoker fallback from the mortality fallback.
        table_array = load_mortality_csv(
            FIXTURES / "synthetic_select_ultimate.csv",
            select_period=3,
            min_age=18,
            max_age=60,
        )
        mortality_agg = MortalityTable.from_table_array(
            source=MortalityTableSource.SOA_VBT_2015,
            table_name="Synthetic-agg",
            table_array=table_array,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.UNKNOWN,
        )
        lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
        assumptions_agg = AssumptionSet(
            mortality=mortality_agg, lapse=lapse, version="test-tabular-agg"
        )
        # YRT rate table keyed only on UNKNOWN smoker for males.
        n_ages = 90 - 18 + 1
        rates = np.full((n_ages, 26), 3.0, dtype=np.float64)
        arr_m = YRTRateTableArray(rates=rates, min_age=18, max_age=90, select_period=25)
        table = YRTRateTable.from_arrays(
            table_name="agg-only",
            arrays={(Sex.MALE, SmokerStatus.UNKNOWN): arr_m},
        )
        treaty = YRTTreaty(
            cession_pct=0.5,
            total_face_amount=block.total_face_amount(),
            yrt_rate_table=table,
        )
        engine = TermLife(block, assumptions_agg, config)
        gross = engine.project(seriatim=True)
        _net, ceded = treaty.apply(gross, inforce=block)
        # Ceded premiums must be finite and non-zero — the smoker fallback
        # to UNKNOWN is what makes this run at all.
        assert np.all(np.isfinite(ceded.gross_premiums))
        assert ceded.gross_premiums[0] > 0

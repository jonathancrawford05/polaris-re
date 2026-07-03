"""
Statutory valuation mortality table for CRVM / VM-20 (epic slice 1, ADR-125).

``AssumptionSet.valuation_mortality`` lets the statutory bases (CRVM, and the
NPR floor inside VM-20) value on a *prescribed* table (e.g. 2001 CSO) distinct
from the projection best-estimate mortality. The tests pin the contract five
independent ways:

1. Default ``None`` leaves every basis byte-identical (same code path).
2. Same-table consistency: with no improvement configured, setting the slot to
   the projection table itself reproduces the baseline CRVM reserve exactly —
   the statutory-q builder mirrors the projection mortality lookup.
3. The statutory q is static: a configured improvement scale moves the
   projection-q CRVM but never the valuation-table CRVM.
4. VM-20 composition: only the NPR floor moves to the prescribed table; the
   deterministic reserve stays best-estimate, so
   ``VM20 = max(NPR_statutory, DR_best_estimate)``.
5. A uniformly conservative (scaled-up) valuation table raises the
   mid-duration CRVM reserve, and an independent numpy FPT recomputation fed
   the independently-built statutory q reproduces the engine reserve.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.improvement import MortalityImprovement
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.products.term_life import TermLife
from polaris_re.products.whole_life import WholeLife
from polaris_re.utils.table_io import MortalityTableArray, load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_table(scale: float = 1.0) -> MortalityTable:
    """Synthetic select-ultimate table, optionally scaled (conservative > 1)."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    if scale != 1.0:
        table_array = MortalityTableArray(
            rates=np.minimum(table_array.rates * scale, 1.0),
            min_age=table_array.min_age,
            max_age=table_array.max_age,
            select_period=table_array.select_period,
            source_file=table_array.source_file,
        )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name=f"Synthetic Test x{scale}",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


def _assumptions(
    valuation_mortality: MortalityTable | None = None,
    improvement: MortalityImprovement | None = None,
) -> AssumptionSet:
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(
        mortality=_load_table(),
        lapse=lapse,
        improvement=improvement,
        valuation_mortality=valuation_mortality,
        version="test-v1",
    )


def _config(basis: ReserveBasis, horizon_years: int = 20) -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=horizon_years,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
        reserve_basis=basis,
    )


def _policy(product_type: ProductType, policy_term: int | None, **overrides) -> Policy:
    kw: dict = dict(
        policy_id="P1",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=1_000_000.0,
        annual_premium=12_000.0,
        product_type=product_type,
        policy_term=policy_term,
        duration_inforce=0,
        reinsurance_cession_pct=0.5,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )
    kw.update(overrides)
    return Policy(**kw)


def _term_block(**overrides) -> InforceBlock:
    return InforceBlock(policies=[_policy(ProductType.TERM, 20, **overrides)])


def _wl_block(**overrides) -> InforceBlock:
    overrides.setdefault("annual_premium", 25_000.0)
    return InforceBlock(policies=[_policy(ProductType.WHOLE_LIFE, None, **overrides)])


class TestAssumptionSetContract:
    def test_default_is_none(self):
        assumptions = _assumptions()
        assert assumptions.valuation_mortality is None

    def test_accepts_distinct_table(self):
        assumptions = _assumptions(valuation_mortality=_load_table(scale=1.5))
        assert assumptions.valuation_mortality is not None
        assert assumptions.valuation_mortality.table_name == "Synthetic Test x1.5"


class TestTermStatutoryValuation:
    def test_crvm_same_table_matches_baseline(self):
        """No improvement: slot = projection table reproduces baseline CRVM."""
        block = _term_block()
        config = _config(ReserveBasis.CRVM)
        baseline = TermLife(block, _assumptions(), config).compute_reserves()
        with_slot = TermLife(
            block, _assumptions(valuation_mortality=_load_table()), config
        ).compute_reserves()
        np.testing.assert_allclose(with_slot, baseline, rtol=1e-12)

    def test_crvm_conservative_table_raises_mid_duration_reserve(self):
        block = _term_block()
        config = _config(ReserveBasis.CRVM)
        baseline = TermLife(block, _assumptions(), config).compute_reserves()
        conservative = TermLife(
            block, _assumptions(valuation_mortality=_load_table(scale=1.5)), config
        ).compute_reserves()
        # FPT forces 0V = 12V = 0 on both bases; compare mid-term durations.
        mid = slice(36, 180)
        assert np.all(conservative[:, mid] >= baseline[:, mid] - 1e-9)
        assert conservative[:, 120].sum() > baseline[:, 120].sum()

    def test_statutory_q_ignores_improvement_scale(self):
        """The valuation-table CRVM is static: improvement moves only the
        projection-q CRVM."""
        block = _term_block()
        config = _config(ReserveBasis.CRVM)
        improvement = MortalityImprovement.scale_aa(base_year=2025)

        no_improvement_baseline = TermLife(block, _assumptions(), config).compute_reserves()
        improved_projection = TermLife(
            block, _assumptions(improvement=improvement), config
        ).compute_reserves()
        stat_with_improvement = TermLife(
            block,
            _assumptions(valuation_mortality=_load_table(), improvement=improvement),
            config,
        ).compute_reserves()

        # Improvement changes the projection-q CRVM ...
        assert not np.allclose(improved_projection, no_improvement_baseline)
        # ... but the statutory valuation q never sees it.
        np.testing.assert_allclose(stat_with_improvement, no_improvement_baseline, rtol=1e-12)

    def test_net_premium_basis_ignores_slot(self):
        block = _term_block()
        config = _config(ReserveBasis.NET_PREMIUM)
        baseline = TermLife(block, _assumptions(), config).compute_reserves()
        with_slot = TermLife(
            block, _assumptions(valuation_mortality=_load_table(scale=1.5)), config
        ).compute_reserves()
        np.testing.assert_allclose(with_slot, baseline, rtol=1e-12)

    def test_vm20_dr_stays_best_estimate(self):
        """VM20 with a prescribed table == max(NPR on that table, best-estimate DR)."""
        block = _term_block()
        config = _config(ReserveBasis.VM20)
        stat_table = _load_table(scale=1.5)

        product = TermLife(block, _assumptions(valuation_mortality=stat_table), config)
        vm20 = product.compute_reserves()

        q, w = product._build_rate_arrays()
        v_monthly = (1.0 + config.effective_valuation_rate) ** (-1.0 / 12.0)
        npr_stat = product._compute_reserves_crvm(product._valuation_q(q), v_monthly)
        dr_best_estimate = product._compute_deterministic_reserve(q, w, v_monthly)
        expected = np.maximum(np.maximum(npr_stat, dr_best_estimate), 0.0)
        np.testing.assert_allclose(vm20, expected, rtol=1e-12)

        # And the DR really came from the projection q: recomputing VM20 without
        # the slot must differ only through the NPR floor.
        baseline_product = TermLife(block, _assumptions(), config)
        npr_baseline = baseline_product._compute_reserves_crvm(q, v_monthly)
        assert not np.allclose(npr_stat, npr_baseline)

    def test_crvm_statutory_q_independent_recompute(self):
        """Engine CRVM on the prescribed table == independent FPT fed an
        independently-built statutory q (rating applied, no improvement)."""
        multiplier = 2.0
        flat_extra = 5.0
        block = _term_block(mortality_multiplier=multiplier, flat_extra_per_1000=flat_extra)
        config = _config(ReserveBasis.CRVM)
        stat_table = _load_table(scale=1.5)

        product = TermLife(block, _assumptions(valuation_mortality=stat_table), config)
        engine = product.compute_reserves()

        # Independent statutory q: valuation-table lookup month by month.
        t = config.projection_months
        ages0 = block.attained_age_vec_at(config.valuation_date)
        dur0 = block.duration_inforce_vec_at(config.valuation_date)
        remaining = block.remaining_term_months_vec
        q = np.zeros((1, t), dtype=np.float64)
        for month in range(t):
            durations = dur0 + month
            ages = ages0 + (durations // 12) - (dur0 // 12)
            ages = np.minimum(ages, stat_table.max_age)
            q_col = stat_table.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durations)
            q_col = np.minimum(q_col * multiplier + flat_extra / 12000.0, 1.0)
            q[:, month] = q_col * (month < remaining)

        face = block.face_amount_vec
        v_monthly = (1.0 + config.effective_valuation_rate) ** (-1.0 / 12.0)
        tpx = np.ones((1, t), dtype=np.float64)
        for m in range(1, t):
            tpx[:, m] = tpx[:, m - 1] * (1.0 - q[:, m - 1])
        v_pow = v_monthly ** np.arange(t, dtype=np.float64)
        v_pow1 = v_monthly ** np.arange(1, t + 1, dtype=np.float64)
        benefit_pv = v_pow1[None, :] * tpx * q * face[:, None]
        annuity_pv = v_pow[None, :] * tpx
        yr1 = np.arange(t) < 12
        alpha = benefit_pv[:, yr1].sum(1) / annuity_pv[:, yr1].sum(1)
        beta = benefit_pv[:, ~yr1].sum(1) / annuity_pv[:, ~yr1].sum(1)
        expected = np.zeros((1, t), dtype=np.float64)
        for m in range(t - 2, -1, -1):
            p = alpha if m < 12 else beta
            expected[:, m] = (q[:, m] * face + (1.0 - q[:, m]) * expected[:, m + 1]) * v_monthly - p
        expected = np.maximum(expected, 0.0)

        np.testing.assert_allclose(engine, expected, rtol=1e-10)


class TestWholeLifeStatutoryValuation:
    def test_crvm_same_table_matches_baseline(self):
        block = _wl_block()
        config = _config(ReserveBasis.CRVM)
        baseline = WholeLife(block, _assumptions(), config).compute_reserves()
        with_slot = WholeLife(
            block, _assumptions(valuation_mortality=_load_table()), config
        ).compute_reserves()
        np.testing.assert_allclose(with_slot, baseline, rtol=1e-12)

    def test_crvm_conservative_table_raises_early_duration_reserve(self):
        """Conservatism front-loads the WL reserve build. Late durations are
        deliberately not asserted: both bases grade to face at omega, and the
        higher-q basis also carries a higher renewal valuation premium, so the
        conservative reserve can sit slightly *below* baseline near omega —
        the two curves cross (empirically around month 147 on this block)."""
        block = _wl_block()
        config = _config(ReserveBasis.CRVM)
        baseline = WholeLife(block, _assumptions(), config).compute_reserves()
        conservative = WholeLife(
            block, _assumptions(valuation_mortality=_load_table(scale=1.5)), config
        ).compute_reserves()
        early = slice(24, 121)
        assert np.all(conservative[:, early] >= baseline[:, early] - 1e-9)
        assert conservative[:, 60].sum() > baseline[:, 60].sum()

    def test_omega_grid_follows_valuation_table_max_age(self):
        block = _wl_block()
        config = _config(ReserveBasis.CRVM)
        product = WholeLife(block, _assumptions(), config)
        # Youngest insured is 40; synthetic table omega is 60.
        assert product._valuation_months_to_omega() == (60 - 40 + 2) * 12
        assert product._valuation_months_to_omega(max_age=70) == (70 - 40 + 2) * 12

    def test_vm20_dr_stays_best_estimate(self):
        block = _wl_block()
        config = _config(ReserveBasis.VM20)
        stat_table = _load_table(scale=1.5)

        product = WholeLife(block, _assumptions(valuation_mortality=stat_table), config)
        vm20 = product.compute_reserves()

        npr_stat = product._compute_reserves_crvm()
        t_val = product._valuation_months_to_omega()
        v_monthly = (1.0 + config.effective_valuation_rate) ** (-1.0 / 12.0)
        q_best = product._build_valuation_mortality(t_val)
        w_best = product._build_valuation_lapse(t_val)
        dr_best_estimate = product._compute_deterministic_reserve(q_best, w_best, v_monthly)
        expected = np.maximum(np.maximum(npr_stat, dr_best_estimate), 0.0)
        np.testing.assert_allclose(vm20, expected, rtol=1e-12)

        baseline_npr = WholeLife(block, _assumptions(), config)._compute_reserves_crvm()
        assert not np.allclose(npr_stat, baseline_npr)

    def test_net_premium_basis_ignores_slot(self):
        block = _wl_block()
        config = _config(ReserveBasis.NET_PREMIUM)
        baseline = WholeLife(block, _assumptions(), config).compute_reserves()
        with_slot = WholeLife(
            block, _assumptions(valuation_mortality=_load_table(scale=1.5)), config
        ).compute_reserves()
        np.testing.assert_allclose(with_slot, baseline, rtol=1e-12)


class TestProjectionUnchanged:
    """The slot only moves reserves — projected decrements stay best-estimate."""

    @pytest.mark.parametrize("basis", [ReserveBasis.CRVM, ReserveBasis.VM20])
    def test_term_claims_and_premiums_unchanged(self, basis: ReserveBasis):
        block = _term_block()
        config = _config(basis)
        baseline = TermLife(block, _assumptions(), config).project()
        with_slot = TermLife(
            block, _assumptions(valuation_mortality=_load_table(scale=1.5)), config
        ).project()
        np.testing.assert_allclose(with_slot.death_claims, baseline.death_claims, rtol=1e-12)
        np.testing.assert_allclose(with_slot.gross_premiums, baseline.gross_premiums, rtol=1e-12)
        assert not np.allclose(with_slot.reserve_balance, baseline.reserve_balance)

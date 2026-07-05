"""
Closed-form and guardrail tests for WholeLife mortality improvement.

WholeLife must honour a configured ``AssumptionSet.improvement`` scale on its
**best-estimate** bases — the projection cash flows, GAAP (FAS 60), and the
VM-20 *deterministic* reserve — exactly as ``TermLife._build_rate_arrays``
already does (Reserve-Basis Correctness epic, Slice 1). It must **not** apply
improvement to the **prescribed statutory** bases (CRVM, VM-20 NPR valued on
``assumptions.valuation_mortality``), which stay static by the ADR-125 design
boundary.

Before this slice ``WholeLife._build_rate_arrays`` never read
``AssumptionSet.improvement``, so every WL basis silently ignored a configured
improvement scale (the reproduced bug). These tests pin the corrected
behaviour:

1. A Scale AA improvement lowers best-estimate q, so projected claims, GAAP,
   and the VM-20 deterministic reserve all move DOWN.
2. CRVM and the VM-20 NPR on a prescribed statutory table are UNCHANGED by an
   improvement scale (statutory static rule preserved), and CRVM without a
   prescribed table also stays static.
3. The best-estimate valuation q built with improvement matches the projection
   q over the horizon (the invariant the VM-20 DR relies on).
4. Independent recomputation: the engine's improved best-estimate monthly q
   equals a hand-built numpy improvement application.
5. Byte-identity: with no improvement configured the ``apply_improvement`` flag
   is a no-op on every path.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.improvement import MortalityImprovement
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import (
    MortalityTable,
    MortalityTableSource,
)
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.products.whole_life import WholeLife
from polaris_re.utils.interpolation import constant_force_interpolate_rates
from polaris_re.utils.table_io import load_mortality_csv

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
        from polaris_re.assumptions.mortality import MortalityTableArray

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
    *,
    improvement: MortalityImprovement | None = None,
    valuation_mortality: MortalityTable | None = None,
) -> AssumptionSet:
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(
        mortality=_load_table(),
        lapse=lapse,
        improvement=improvement,
        valuation_mortality=valuation_mortality,
        version="test-v1",
    )


def _config(basis: ReserveBasis = ReserveBasis.GAAP) -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=30,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
        reserve_basis=basis,
    )


def _wl_block(**overrides) -> InforceBlock:
    kw: dict = dict(
        policy_id="W1",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=500_000.0,
        annual_premium=8_000.0,
        product_type=ProductType.WHOLE_LIFE,
        duration_inforce=0,
        reinsurance_cession_pct=0.5,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )
    kw.update(overrides)
    return InforceBlock(policies=[Policy(**kw)])


def _scale_aa() -> MortalityImprovement:
    return MortalityImprovement.scale_aa(base_year=2025)


# --------------------------------------------------------------------------
# 1. Best-estimate bases move DOWN under a Scale AA improvement.
# --------------------------------------------------------------------------


def test_projection_claims_fall_under_improvement() -> None:
    """Projected death claims decrease when a Scale AA improvement is configured."""
    block = _wl_block()
    no_impr = WholeLife(block, _assumptions(), _config()).project()
    with_impr = WholeLife(block, _assumptions(improvement=_scale_aa()), _config()).project()
    assert with_impr.death_claims.sum() < no_impr.death_claims.sum()


def test_gaap_reflects_improvement() -> None:
    """WL GAAP (a best-estimate + PAD basis) falls under a Scale AA improvement.

    The WL analogue of the TermLife 'GAAP reflects improvement' guardrail — the
    test that could not exist before this slice because WL ignored improvement.
    """
    block = _wl_block()
    no_impr = WholeLife(block, _assumptions(), _config(ReserveBasis.GAAP)).compute_reserves()
    with_impr = WholeLife(
        block, _assumptions(improvement=_scale_aa()), _config(ReserveBasis.GAAP)
    ).compute_reserves()
    # Improvement lowers best-estimate q, so the mid-duration benefit reserve falls.
    assert with_impr[:, 120].sum() < no_impr[:, 120].sum()


def test_net_premium_reflects_improvement() -> None:
    """NET_PREMIUM (a best-estimate reserve via _build_rate_arrays) falls too."""
    block = _wl_block()
    no_impr = WholeLife(block, _assumptions(), _config(ReserveBasis.NET_PREMIUM)).compute_reserves()
    with_impr = WholeLife(
        block, _assumptions(improvement=_scale_aa()), _config(ReserveBasis.NET_PREMIUM)
    ).compute_reserves()
    assert with_impr[:, 120].sum() < no_impr[:, 120].sum()


def test_vm20_deterministic_reserve_reflects_improvement() -> None:
    """The VM-20 deterministic-reserve best-estimate q reflects improvement.

    The DR values on the best-estimate table, so its mortality array must move
    under a Scale AA improvement. Exercised at the ``_build_valuation_mortality``
    seam with the DR's ``apply_improvement=True`` semantics.
    """
    block = _wl_block()
    eng_no = WholeLife(block, _assumptions(), _config(ReserveBasis.VM20))
    eng_impr = WholeLife(block, _assumptions(improvement=_scale_aa()), _config(ReserveBasis.VM20))
    t_val = eng_no.config.projection_months  # any common window > select period
    q_no = eng_no._build_valuation_mortality(t_val, None, apply_improvement=True)
    q_impr = eng_impr._build_valuation_mortality(t_val, None, apply_improvement=True)
    # Beyond the base year, improvement strictly lowers best-estimate q.
    assert q_impr[:, 60:].sum() < q_no[:, 60:].sum()


# --------------------------------------------------------------------------
# 2. Prescribed statutory bases stay STATIC under improvement.
# --------------------------------------------------------------------------


def test_crvm_static_under_improvement_with_prescribed_table() -> None:
    """CRVM valued on a prescribed statutory table is unchanged by improvement."""
    block = _wl_block()
    val_table = _load_table(scale=1.5)
    no_impr = WholeLife(
        block, _assumptions(valuation_mortality=val_table), _config(ReserveBasis.CRVM)
    ).compute_reserves()
    with_impr = WholeLife(
        block,
        _assumptions(improvement=_scale_aa(), valuation_mortality=val_table),
        _config(ReserveBasis.CRVM),
    ).compute_reserves()
    np.testing.assert_allclose(with_impr, no_impr, rtol=0.0, atol=0.0)


def test_crvm_static_under_improvement_without_prescribed_table() -> None:
    """CRVM without a prescribed table falls back to the projection table but
    still stays STATIC — improvement is a best-estimate property, and CRVM is a
    prescribed statutory basis (ADR-125)."""
    block = _wl_block()
    no_impr = WholeLife(block, _assumptions(), _config(ReserveBasis.CRVM)).compute_reserves()
    with_impr = WholeLife(
        block, _assumptions(improvement=_scale_aa()), _config(ReserveBasis.CRVM)
    ).compute_reserves()
    np.testing.assert_allclose(with_impr, no_impr, rtol=0.0, atol=0.0)


def test_vm20_npr_component_static_under_improvement() -> None:
    """The VM-20 NPR floor (= CRVM) on a prescribed table is static under
    improvement; only the DR half is best-estimate."""
    block = _wl_block()
    val_table = _load_table(scale=1.5)
    eng_no = WholeLife(
        block, _assumptions(valuation_mortality=val_table), _config(ReserveBasis.VM20)
    )
    eng_impr = WholeLife(
        block,
        _assumptions(improvement=_scale_aa(), valuation_mortality=val_table),
        _config(ReserveBasis.VM20),
    )
    npr_no = eng_no._compute_reserves_crvm()
    npr_impr = eng_impr._compute_reserves_crvm()
    np.testing.assert_allclose(npr_impr, npr_no, rtol=0.0, atol=0.0)


# --------------------------------------------------------------------------
# 3 & 4. Correctness of the improvement application.
# --------------------------------------------------------------------------


def test_best_estimate_valuation_q_matches_projection_over_horizon() -> None:
    """With improvement configured, the best-estimate valuation q
    (apply_improvement=True) equals the projection q over the horizon — the
    invariant the VM-20 deterministic reserve relies on."""
    block = _wl_block()
    eng = WholeLife(block, _assumptions(improvement=_scale_aa()), _config(ReserveBasis.VM20))
    t_proj = eng.config.projection_months
    q_proj, _w = eng._build_rate_arrays()
    q_val = eng._build_valuation_mortality(
        eng._valuation_months_to_omega(), None, apply_improvement=True
    )
    np.testing.assert_array_equal(q_val[:, :t_proj], q_proj)


def test_independent_improvement_recomputation() -> None:
    """The engine's improved best-estimate monthly q equals a hand-built numpy
    Scale AA application (mirror of the TermLife improvement test)."""
    block = _wl_block()
    impr = _scale_aa()
    asm = _assumptions(improvement=impr)
    eng = WholeLife(block, asm, _config())
    q_eng, _w = eng._build_rate_arrays()

    # Hand recomputation for the single policy, mortality only, no rating.
    mort = asm.mortality
    duration0 = eng.inforce.duration_inforce_vec_at(eng.config.valuation_date)  # (1,)
    age0 = eng.inforce.attained_age_vec_at(eng.config.valuation_date)  # (1,)
    t = eng.config.projection_months
    val_year = eng.config.valuation_date.year
    expected = np.zeros(t, dtype=np.float64)
    for month in range(t):
        cur_dur = duration0 + month
        age_inc = (cur_dur // 12) - (duration0 // 12)
        ages = np.minimum(age0 + age_inc, mort.max_age)
        cal_year = val_year + (month // 12)
        q_monthly = eng._lookup_qx_column(mort, ages, cur_dur)
        q_annual = 1.0 - (1.0 - q_monthly) ** 12
        q_annual_impr = impr.apply_improvement(q_annual, ages, cal_year)
        q_monthly_impr = constant_force_interpolate_rates(q_annual_impr, fraction=1.0 / 12.0)
        # max-age certain death forcing (block never reaches omega here, but mirror)
        at_max = (age0 + age_inc) >= mort.max_age
        expected[month] = np.where(at_max, 1.0, q_monthly_impr)[0]

    np.testing.assert_allclose(q_eng[0], expected, rtol=0.0, atol=1e-15)


# --------------------------------------------------------------------------
# 5. Byte-identity: no improvement → apply_improvement flag is a no-op.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("apply_improvement", [False, True])
def test_no_improvement_configured_is_noop(apply_improvement: bool) -> None:
    """With improvement=None, the apply_improvement flag has no effect and the
    valuation q equals the projection q — the byte-identity guarantee."""
    block = _wl_block()
    eng = WholeLife(block, _assumptions(), _config(ReserveBasis.VM20))
    t_proj = eng.config.projection_months
    q_proj, _w = eng._build_rate_arrays()
    q_val = eng._build_valuation_mortality(
        eng._valuation_months_to_omega(), None, apply_improvement=apply_improvement
    )
    np.testing.assert_array_equal(q_val[:, :t_proj], q_proj)

"""
Closed-form and structural verification of the WholeLife CRVM reserve (slice 2b).

CRVM is implemented as Full Preliminary Term (FPT) with a **prospective
valuation to omega**, so it (a) grades in the first-year expense allowance and
(b) closes the horizon-edge terminal-reserve artefact of the net-premium path
(ADR-089). The tests pin the reserve several independent ways:

1. The FPT structural identities hold per survivor: ``0V = 0`` and the
   first-year terminal reserve ``12V = 0``.
2. The CRVM reserve is monotonically increasing toward the face amount over the
   projection horizon — it does **not** collapse near the horizon the way the
   net-premium one-period terminal estimate does (the artefact).
3. The first-year CRVM reserve is below the net-premium reserve (the expense
   allowance graded in).
4. The reserve converges to the face amount at omega.
5. A YRT integration test confirms switching the basis to CRVM moves the Net
   Amount at Risk (and the ceded premium), with no treaty-layer change.
6. Limited-pay whole life with a pay period under 20 years raises (the 20-pay
   expense-allowance cap is not yet implemented).
7. The default NET_PREMIUM path is byte-identical to a plain compute_reserves().
"""

import os
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_assumption_set,
    load_inforce,
)
from polaris_re.products.whole_life import WholeLife
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"

GOLDEN_CSV = Path("data/qa/golden_inforce.csv")
_MORTALITY_DIR = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
_HAS_SOA_TABLES = (_MORTALITY_DIR / "soa_vbt_2015_male_ns.csv").exists()
requires_soa_tables = pytest.mark.skipif(
    not _HAS_SOA_TABLES,
    reason=f"SOA VBT 2015 tables not found at {_MORTALITY_DIR}",
)


@pytest.fixture()
def assumption_set() -> AssumptionSet:
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic WL CRVM Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.04, 2: 0.03, "ultimate": 0.02})
    return AssumptionSet(mortality=mortality, lapse=lapse, version="wl-crvm-v1")


def _config(basis: ReserveBasis | None = None, horizon: int = 20) -> ProjectionConfig:
    kwargs: dict = {
        "valuation_date": date(2025, 1, 1),
        "projection_horizon_years": horizon,
        "discount_rate": 0.04,
    }
    if basis is not None:
        kwargs["reserve_basis"] = basis
    return ProjectionConfig(**kwargs)


def _wl_policy(
    policy_id: str = "WL_001",
    issue_age: int = 40,
    face: float = 500_000.0,
) -> Policy:
    return Policy(
        policy_id=policy_id,
        issue_age=issue_age,
        attained_age=issue_age,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=8_000.0,
        product_type=ProductType.WHOLE_LIFE,
        policy_term=None,
        duration_inforce=0,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


@pytest.fixture()
def single_block() -> InforceBlock:
    return InforceBlock(policies=[_wl_policy()], block_id="WL_CRVM_BLOCK")


# --------------------------------------------------------------------------
# 1. FPT structural identities: 0V = 0 and 12V = 0 (per survivor).
# --------------------------------------------------------------------------


def test_crvm_fpt_zero_reserves_year_one(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    wl = WholeLife(single_block, assumption_set, _config(ReserveBasis.CRVM))
    reserves = wl.compute_reserves()  # (N, T)
    # 0V = 0 (issue) and 12V = 0 (end of first policy year) under FPT.
    np.testing.assert_allclose(reserves[:, 0], 0.0, atol=1.0)
    np.testing.assert_allclose(reserves[:, 12], 0.0, atol=1.0)


# --------------------------------------------------------------------------
# 2. The artefact: net-premium reserve collapses near the horizon; CRVM does
#    not. CRVM is monotonically increasing over the projection horizon.
# --------------------------------------------------------------------------


def test_crvm_does_not_collapse_at_horizon(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    # Net-premium reserve: the one-period terminal estimate drags the late
    # durations down — the reserve is much lower at the horizon than mid-term.
    np_reserves = WholeLife(single_block, assumption_set, _config()).compute_reserves()[0]
    crvm = WholeLife(single_block, assumption_set, _config(ReserveBasis.CRVM)).compute_reserves()[0]

    mid = 10 * 12  # year 10
    end = np_reserves.shape[0] - 1  # final month

    # Net-premium path exhibits the collapse: terminal << mid-term.
    assert np_reserves[end] < 0.2 * np_reserves[mid]

    # CRVM does NOT collapse: terminal reserve exceeds the mid-term reserve.
    assert crvm[end] > crvm[mid]

    # CRVM increases monotonically (allowing tiny float noise) over the horizon.
    diffs = np.diff(crvm)
    assert np.all(diffs >= -1.0)


# --------------------------------------------------------------------------
# 3. Expense allowance graded in: first-year CRVM reserve < net-premium reserve.
# --------------------------------------------------------------------------


def test_crvm_below_net_premium_first_year(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    np_reserves = WholeLife(single_block, assumption_set, _config()).compute_reserves()[0]
    crvm = WholeLife(single_block, assumption_set, _config(ReserveBasis.CRVM)).compute_reserves()[0]
    # End of policy year 1: CRVM (FPT => 12V = 0) is strictly below net premium.
    assert crvm[12] < np_reserves[12]
    # And CRVM never exceeds the (uncollapsed, early-duration) net premium reserve.
    assert crvm[6] <= np_reserves[6] + 1.0


# --------------------------------------------------------------------------
# 4. Reserve converges to the face amount at omega.
# --------------------------------------------------------------------------


def test_crvm_converges_to_face_at_omega(assumption_set: AssumptionSet) -> None:
    # Issue at 40; max table age 60 -> 20 years to omega. Project the full span.
    block = InforceBlock(policies=[_wl_policy(face=500_000.0)], block_id="B")
    wl = WholeLife(block, assumption_set, _config(ReserveBasis.CRVM, horizon=20))
    reserves = wl.compute_reserves()[0]
    # By the final month (attained age ~60 = omega) the reserve approaches face.
    assert reserves[-1] > 0.9 * 500_000.0


# --------------------------------------------------------------------------
# 5. YRT integration: switching basis moves the NAR and the ceded premium.
# --------------------------------------------------------------------------


def test_crvm_basis_changes_yrt_ceded_premium(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    treaty = YRTTreaty(
        cession_pct=0.5,
        total_face_amount=500_000.0,
        flat_yrt_rate_per_1000=2.0,
        treaty_name="CRVM-NAR-test",
    )

    gross_np = WholeLife(single_block, assumption_set, _config()).project()
    gross_crvm = WholeLife(single_block, assumption_set, _config(ReserveBasis.CRVM)).project()

    _, ceded_np = treaty.apply(gross_np)
    _, ceded_crvm = treaty.apply(gross_crvm)

    # CRVM lowers the early-duration reserve (expense allowance) -> higher NAR
    # -> higher ceded YRT premium early on. The total ceded premium differs.
    assert not np.allclose(ceded_np.gross_premiums, ceded_crvm.gross_premiums)


# --------------------------------------------------------------------------
# 6. Limited-pay < 20 years raises (20-pay cap not implemented).
# --------------------------------------------------------------------------


def test_crvm_short_limited_pay_raises(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    wl = WholeLife(
        single_block,
        assumption_set,
        _config(ReserveBasis.CRVM),
        premium_payment_years=10,
    )
    with pytest.raises(PolarisComputationError, match="Full Preliminary Term"):
        wl.compute_reserves()


def test_crvm_limited_pay_20_years_ok(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    wl = WholeLife(
        single_block,
        assumption_set,
        _config(ReserveBasis.CRVM),
        premium_payment_years=20,
    )
    reserves = wl.compute_reserves()
    assert reserves.shape == (1, 240)
    np.testing.assert_allclose(reserves[:, 0], 0.0, atol=1.0)


# --------------------------------------------------------------------------
# 7. Default NET_PREMIUM path unchanged; valuation mortality matches the
#    projection mortality over the projection horizon.
# --------------------------------------------------------------------------


def test_net_premium_default_unchanged(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    default_reserves = WholeLife(single_block, assumption_set, _config()).compute_reserves()
    explicit_reserves = WholeLife(
        single_block, assumption_set, _config(ReserveBasis.NET_PREMIUM)
    ).compute_reserves()
    np.testing.assert_array_equal(default_reserves, explicit_reserves)


def test_valuation_mortality_matches_projection_over_horizon(
    assumption_set: AssumptionSet, single_block: InforceBlock
) -> None:
    wl = WholeLife(single_block, assumption_set, _config(ReserveBasis.CRVM))
    t_proj = wl.config.projection_months
    q_proj, _w = wl._build_rate_arrays()
    q_val = wl._build_valuation_mortality(wl._valuation_months_to_omega())
    np.testing.assert_array_equal(q_val[:, :t_proj], q_proj)


# --------------------------------------------------------------------------
# Named acceptance test (PLAN §"Folded-in acceptance test"): the whole-life
# terminal-reserve artefact ($7.18M -> $56k, yr10 -> yr20) on the golden WL
# block. The net-premium reserve collapses at the horizon; CRVM (prospective
# to omega) closes it.
# --------------------------------------------------------------------------


def _golden_wl_setup() -> tuple[InforceBlock, AssumptionSet]:
    inforce = load_inforce(csv_path=GOLDEN_CSV)
    wl_block = inforce.filter_by_product(ProductType.WHOLE_LIFE)
    inputs = PipelineInputs(
        mortality=MortalityConfig(source="SOA_VBT_2015", multiplier=1.0),
        lapse=LapseConfig(),
        deal=DealConfig(product_type="WHOLE_LIFE"),
    )
    return wl_block, build_assumption_set(inputs)


def _golden_wl_config(basis: ReserveBasis) -> ProjectionConfig:
    # Mirrors the golden WL valuation: 20-year horizon, 6% discount.
    return ProjectionConfig(
        valuation_date=date(2026, 4, 1),
        projection_horizon_years=20,
        discount_rate=0.06,
        reserve_basis=basis,
    )


@requires_soa_tables
def test_golden_wl_terminal_reserve_artefact_closed() -> None:
    """The documented $7.18M (yr10) -> $56k (yr20) net-premium collapse, closed."""
    wl_block, assumptions = _golden_wl_setup()

    np_balance = (
        WholeLife(wl_block, assumptions, _golden_wl_config(ReserveBasis.NET_PREMIUM))
        .project()
        .reserve_balance
    )
    crvm_balance = (
        WholeLife(wl_block, assumptions, _golden_wl_config(ReserveBasis.CRVM))
        .project()
        .reserve_balance
    )

    yr10, yr20 = 10 * 12 - 1, 20 * 12 - 1

    # Pin the documented artefact on the net-premium path (the status quo this
    # slice does NOT change): ~$7.18M at year 10 collapsing to ~$56k at year 20.
    np.testing.assert_allclose(np_balance[yr10], 7_171_356.0, rtol=0.02)
    np.testing.assert_allclose(np_balance[yr20], 56_433.0, rtol=0.05)
    assert np_balance[yr20] < 0.02 * np_balance[yr10]  # the collapse

    # CRVM closes it: the year-20 aggregate reserve is materially higher
    # (>20x the collapsed net-premium balance) because the per-survivor reserve
    # keeps grading toward face rather than collapsing at the horizon.
    assert crvm_balance[yr20] > 20.0 * np_balance[yr20]


@requires_soa_tables
def test_golden_wl_crvm_per_survivor_reserve_monotone() -> None:
    """Per-survivor CRVM reserve on the golden WL block does not collapse."""
    wl_block, assumptions = _golden_wl_setup()
    # Per-survivor reserve aggregate (no lx weighting) isolates the artefact
    # from ordinary survivorship decline.
    crvm = WholeLife(wl_block, assumptions, _golden_wl_config(ReserveBasis.CRVM)).compute_reserves()
    agg = crvm.sum(axis=0)
    yr10, yr20 = 10 * 12 - 1, 20 * 12 - 1
    # The reserve at the horizon exceeds the mid-term reserve (no collapse).
    assert agg[yr20] > agg[yr10]

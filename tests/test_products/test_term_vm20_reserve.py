"""
Closed-form and structural verification of the TermLife VM-20 simplified reserve
(slice 3a of the reserve-basis epic, ADR-090).

VM-20 simplified is ``max(NPR, DR)`` floored at 0, the *deterministic* path of
the US principle-based reserve (no stochastic scenarios in scope):

* **NPR** is mapped to the CRVM reserve (the formulaic net-premium floor with
  the first-year expense allowance graded in).
* **DR** is the deterministic gross-premium reserve: the prospective present
  value of future death benefits and maintenance expenses less future gross
  premiums, on best-estimate (mortality + lapse) decrements.

The DR is pinned closed-form three ways: an independent forward prospective-PV
sum reproduces the backward recursion; expenses raise it monotonically; and the
``max(NPR, DR)`` semantics are exercised in both regimes — a well-priced block
where the NPR floor governs (VM20 == CRVM in the building durations) and an
underpriced block where the realistic DR drives the reserve above the floor (the
deficiency signal). A YRT integration test confirms a higher VM-20 reserve
lowers the Net Amount at Risk and the ceded premium, with no treaty-layer change.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"


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
        table_name="Synthetic Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(mortality=mortality, lapse=lapse, version="test-v1")


def _config(
    basis: ReserveBasis | None = None,
    acq: float = 0.0,
    maint: float = 0.0,
) -> ProjectionConfig:
    kw: dict = dict(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
        acquisition_cost_per_policy=acq,
        maintenance_cost_per_policy_per_year=maint,
    )
    if basis is not None:
        kw["reserve_basis"] = basis
    return ProjectionConfig(**kw)


def _term_block(annual_premium: float = 12_000.0) -> InforceBlock:
    return InforceBlock(
        policies=[
            Policy(
                policy_id="T1",
                issue_age=40,
                attained_age=40,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=1_000_000.0,
                annual_premium=annual_premium,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=0.5,
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            )
        ]
    )


def _independent_dr(
    q: np.ndarray,
    w: np.ndarray,
    face: np.ndarray,
    gross_prem: np.ndarray,
    expenses: np.ndarray,
    v_monthly: float,
) -> np.ndarray:
    """Fully independent forward prospective-PV of the deterministic reserve.

    DR_t = sum_{s>=t} ptau(t->s) * [ v^(s-t)*(E_s - G_s) + v^(s-t+1)*q_s*face ]

    where ptau(t->s) is in-force survival under both decrements. This is a
    different code path from the engine's backward recursion.
    """
    n, t = q.shape
    dr = np.zeros((n, t), dtype=np.float64)
    for ti in range(t):
        total = np.zeros(n, dtype=np.float64)
        surv = np.ones(n, dtype=np.float64)  # ptau(ti -> s)
        for s in range(ti, t):
            total += surv * (
                (v_monthly ** (s - ti)) * (expenses[:, s] - gross_prem[:, s])
                + (v_monthly ** (s - ti + 1)) * q[:, s] * face
            )
            surv = surv * (1.0 - q[:, s]) * (1.0 - w[:, s])
        dr[:, ti] = total
    return dr


def _expense_premium_arrays(engine: TermLife) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruct the (G, E) arrays the DR consumes, for the independent check."""
    n = engine.inforce.n_policies
    t = engine.config.projection_months
    rem = engine.inforce.remaining_term_months_vec
    active = np.arange(t, dtype=np.int32)[np.newaxis, :] < rem[:, np.newaxis]
    gross = engine.inforce.monthly_premium_vec[:, np.newaxis] * active
    maint = engine.config.maintenance_cost_per_policy_per_year / 12.0
    expenses = np.zeros((n, t), dtype=np.float64)
    if maint > 0.0:
        expenses += maint * active
    acq = engine.config.acquisition_cost_per_policy
    if acq > 0.0:
        new_biz = engine.inforce.duration_inforce_vec_at(engine.config.valuation_date) == 0
        expenses[new_biz, 0] += acq
    return gross, expenses


class TestDeterministicReserve:
    def test_matches_independent_forward_pv(self, assumption_set: AssumptionSet):
        """Backward recursion == independent forward prospective-PV sum,
        with maintenance + acquisition expenses and lapse all switched on."""
        engine = TermLife(
            _term_block(), assumption_set, _config(ReserveBasis.VM20, acq=300.0, maint=120.0)
        )
        q, w = engine._build_rate_arrays()
        v = (1.0 + engine.config.effective_valuation_rate) ** (-1.0 / 12.0)
        dr = engine._compute_deterministic_reserve(q, w, v)
        gross, expenses = _expense_premium_arrays(engine)
        expected = _independent_dr(q, w, engine.inforce.face_amount_vec, gross, expenses, v)
        np.testing.assert_allclose(dr, expected, rtol=1e-10, atol=1e-6)

    def test_higher_maintenance_raises_dr(self, assumption_set: AssumptionSet):
        """DR is monotone non-decreasing in the maintenance expense load."""
        v = (1.0 + 0.035) ** (-1.0 / 12.0)
        e_lo = TermLife(_term_block(), assumption_set, _config(ReserveBasis.VM20, maint=0.0))
        e_hi = TermLife(_term_block(), assumption_set, _config(ReserveBasis.VM20, maint=240.0))
        q, w = e_lo._build_rate_arrays()  # rates do not depend on expense
        dr_lo = e_lo._compute_deterministic_reserve(q, w, v)
        dr_hi = e_hi._compute_deterministic_reserve(q, w, v)
        assert np.all(dr_hi >= dr_lo - 1e-9)
        assert dr_hi[0, 12] > dr_lo[0, 12]


class TestVM20Semantics:
    def _reserves(self, aset: AssumptionSet, premium: float):
        npr = TermLife(_term_block(premium), aset, _config(ReserveBasis.CRVM)).compute_reserves()
        vm20 = TermLife(_term_block(premium), aset, _config(ReserveBasis.VM20)).compute_reserves()
        engine = TermLife(_term_block(premium), aset, _config(ReserveBasis.VM20))
        q, w = engine._build_rate_arrays()
        v = (1.0 + 0.035) ** (-1.0 / 12.0)
        dr = engine._compute_deterministic_reserve(q, w, v)
        return npr, dr, vm20

    def test_vm20_equals_max_npr_dr(self, assumption_set: AssumptionSet):
        """VM20 == max(NPR_crvm, DR) elementwise, floored at 0."""
        npr, dr, vm20 = self._reserves(assumption_set, 12_000.0)
        expected = np.maximum(np.maximum(npr, dr), 0.0)
        np.testing.assert_allclose(vm20, expected, rtol=1e-12, atol=1e-9)

    def test_vm20_at_least_npr_floor(self, assumption_set: AssumptionSet):
        """VM20 is never below the NPR (CRVM) floor, and never negative."""
        npr, _dr, vm20 = self._reserves(assumption_set, 12_000.0)
        assert np.all(vm20 >= npr - 1e-9)
        assert np.all(vm20 >= -1e-9)

    def test_well_priced_floor_governs(self, assumption_set: AssumptionSet):
        """A well-priced block: the realistic DR sits below the NPR floor while
        the reserve is building, so VM20 coincides with the CRVM floor there."""
        npr, dr, vm20 = self._reserves(assumption_set, 12_000.0)
        building = slice(12, 200)  # exclude the final-months run-off
        assert np.all(dr[0, building] < npr[0, building])
        np.testing.assert_allclose(vm20[0, building], npr[0, building], rtol=1e-12, atol=1e-9)

    def test_underpriced_dr_governs(self, assumption_set: AssumptionSet):
        """An underpriced block: the realistic DR exceeds the NPR floor across
        the durations, so VM20 follows the DR — the deficiency signal."""
        npr, dr, vm20 = self._reserves(assumption_set, 600.0)
        building = slice(12, 200)
        assert np.all(dr[0, building] > npr[0, building] + 1.0)
        np.testing.assert_allclose(vm20[0, building], dr[0, building], rtol=1e-12, atol=1e-9)
        # And the deficiency lifts the reserve strictly above the formulaic floor.
        assert vm20[0, 120] > npr[0, 120] + 1.0


class TestVM20DefaultUnchanged:
    def test_net_premium_default_byte_identical(self, assumption_set: AssumptionSet):
        """The VM-20 code path must not perturb the default NET_PREMIUM reserve."""
        implicit = TermLife(_term_block(), assumption_set, _config()).compute_reserves()
        explicit = TermLife(
            _term_block(), assumption_set, _config(ReserveBasis.NET_PREMIUM)
        ).compute_reserves()
        np.testing.assert_array_equal(implicit, explicit)


class TestVM20YRTIntegration:
    """A higher VM-20 reserve lowers the Net Amount at Risk, so the ceded YRT
    premium falls — with no change to the treaty layer."""

    def _yrt(self) -> YRTTreaty:
        return YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.0,
        )

    def test_underpriced_vm20_lowers_ceded_premium(self, assumption_set: AssumptionSet):
        block = _term_block(600.0)  # underpriced -> DR-driven VM-20 above net premium
        gross_np = TermLife(block, assumption_set, _config(ReserveBasis.NET_PREMIUM)).project()
        gross_vm20 = TermLife(block, assumption_set, _config(ReserveBasis.VM20)).project()

        # VM-20 reserve_balance exceeds the net-premium reserve for this block.
        assert np.all(gross_vm20.reserve_balance >= gross_np.reserve_balance - 1e-6)
        assert gross_vm20.reserve_balance[120] > gross_np.reserve_balance[120] + 1.0

        _net_np, ceded_np = self._yrt().apply(gross_np)
        _net_vm20, ceded_vm20 = self._yrt().apply(gross_vm20)

        # Higher reserve -> lower NAR -> lower ceded YRT premium mid-term.
        assert ceded_vm20.nar[120] < ceded_np.nar[120]
        assert ceded_vm20.yrt_premiums[120] < ceded_np.yrt_premiums[120]

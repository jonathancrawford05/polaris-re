"""
Closed-form and structural verification of the WholeLife VM-20 simplified reserve
(slice 3b of the reserve-basis epic, ADR-091).

VM-20 simplified is ``max(NPR, DR)`` floored at 0, the *deterministic* path of
the US principle-based reserve (no stochastic scenarios in scope). For whole
life both components are valued **prospectively to omega** (max age), the WL
analogue of the TermLife finite-horizon DR (ADR-090):

* **NPR** is the to-omega CRVM reserve (ADR-089): a net-premium reserve with the
  first-year expense allowance graded in. It grades monotonically toward face
  rather than collapsing at the projection horizon.
* **DR** is the to-omega deterministic gross-premium reserve: the prospective
  present value of future death benefits and maintenance expenses less future
  gross premiums, on best-estimate (mortality + lapse) decrements, valued to
  omega so it does not collapse at the horizon edge.

The DR is pinned closed-form: an independent forward prospective-PV sum (to
omega) reproduces the engine's backward recursion, and the ``max(NPR, DR)``
semantics are exercised in both regimes — a well-priced block where the NPR
floor governs (VM20 == CRVM) and an underpriced block where the realistic DR
drives the reserve above the floor (the deficiency signal). A YRT integration
test confirms a higher VM-20 reserve lowers the Net Amount at Risk and the ceded
premium, with no treaty-layer change.
"""

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
from polaris_re.products.whole_life import WholeLife
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
        table_name="Synthetic WL VM20 Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.04, 2: 0.03, "ultimate": 0.02})
    return AssumptionSet(mortality=mortality, lapse=lapse, version="wl-vm20-v1")


# A well-priced WL block (gross >> net) so the DR sits below the NPR floor; an
# underpriced block (gross < net) so the realistic DR drives the reserve above it.
WELL_PRICED_PREMIUM = 20_000.0
UNDERPRICED_PREMIUM = 8_000.0


def _config(
    basis: ReserveBasis | None = None,
    acq: float = 0.0,
    maint: float = 0.0,
    horizon: int = 20,
) -> ProjectionConfig:
    kw: dict = dict(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=horizon,
        discount_rate=0.04,
        acquisition_cost_per_policy=acq,
        maintenance_cost_per_policy_per_year=maint,
    )
    if basis is not None:
        kw["reserve_basis"] = basis
    return ProjectionConfig(**kw)


def _wl_policy(annual_premium: float, face: float = 500_000.0) -> Policy:
    return Policy(
        policy_id="WL_001",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=annual_premium,
        product_type=ProductType.WHOLE_LIFE,
        policy_term=None,
        duration_inforce=0,
        reinsurance_cession_pct=0.5,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )


def _wl_block(annual_premium: float, face: float = 500_000.0) -> InforceBlock:
    return InforceBlock(policies=[_wl_policy(annual_premium, face)], block_id="WL_VM20_BLOCK")


def _independent_dr(
    q_val: np.ndarray,
    w_val: np.ndarray,
    face: np.ndarray,
    gross_prem: np.ndarray,
    expenses: np.ndarray,
    v_monthly: float,
) -> np.ndarray:
    """Fully independent forward prospective-PV of the deterministic reserve.

    DR_t = sum_{s>=t} ptau(t->s) * [ v^(s-t)*(E_s - G_s) + v^(s-t+1)*q_s*face ]

    over the to-omega valuation grid, where ptau(t->s) is in-force survival under
    both decrements. This is a different code path from the engine's backward
    recursion.
    """
    n, t = q_val.shape
    dr = np.zeros((n, t), dtype=np.float64)
    for ti in range(t):
        total = np.zeros(n, dtype=np.float64)
        surv = np.ones(n, dtype=np.float64)  # ptau(ti -> s)
        for s in range(ti, t):
            total += surv * (
                (v_monthly ** (s - ti)) * (expenses[:, s] - gross_prem[:, s])
                + (v_monthly ** (s - ti + 1)) * q_val[:, s] * face
            )
            surv = surv * (1.0 - q_val[:, s]) * (1.0 - w_val[:, s])
        dr[:, ti] = total
    return dr


def _expense_premium_arrays(engine: WholeLife, t_val: int) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruct the (G, E) to-omega arrays the WL DR consumes."""
    n = engine.inforce.n_policies
    months = np.arange(t_val)
    if engine.premium_payment_years is not None:
        prem_active = months < engine.premium_payment_years * 12
    else:
        prem_active = np.ones(t_val, dtype=bool)
    gross = engine.inforce.monthly_premium_vec[:, np.newaxis] * prem_active[np.newaxis, :]
    maint = engine.config.maintenance_cost_per_policy_per_year / 12.0
    expenses = np.zeros((n, t_val), dtype=np.float64)
    if maint > 0.0:
        expenses += maint
    acq = engine.config.acquisition_cost_per_policy
    if acq > 0.0:
        new_biz = engine.inforce.duration_inforce_vec_at(engine.config.valuation_date) == 0
        expenses[new_biz, 0] += acq
    return gross, expenses


class TestDeterministicReserve:
    def test_matches_independent_forward_pv(self, assumption_set: AssumptionSet):
        """Backward to-omega recursion == independent forward prospective-PV sum,
        with maintenance + acquisition expenses and lapse all switched on."""
        engine = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM),
            assumption_set,
            _config(ReserveBasis.VM20, acq=400.0, maint=180.0),
        )
        t_val = engine._valuation_months_to_omega()
        v = (1.0 + engine.config.effective_valuation_rate) ** (-1.0 / 12.0)
        q_val = engine._build_valuation_mortality(t_val)
        w_val = engine._build_valuation_lapse(t_val)
        dr = engine._compute_deterministic_reserve(q_val, w_val, v)  # (N, t_proj)

        gross, expenses = _expense_premium_arrays(engine, t_val)
        expected_full = _independent_dr(
            q_val, w_val, engine.inforce.face_amount_vec, gross, expenses, v
        )
        t_proj = engine.config.projection_months
        np.testing.assert_allclose(dr, expected_full[:, :t_proj], rtol=1e-9, atol=1e-5)

    def test_higher_maintenance_raises_dr(self, assumption_set: AssumptionSet):
        """DR is monotone non-decreasing in the maintenance expense load."""
        e_lo = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config(ReserveBasis.VM20, maint=0.0)
        )
        e_hi = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config(ReserveBasis.VM20, maint=360.0)
        )
        v = (1.0 + e_lo.config.effective_valuation_rate) ** (-1.0 / 12.0)
        t_val = e_lo._valuation_months_to_omega()
        q_val = e_lo._build_valuation_mortality(t_val)
        w_val = e_lo._build_valuation_lapse(t_val)
        dr_lo = e_lo._compute_deterministic_reserve(q_val, w_val, v)
        dr_hi = e_hi._compute_deterministic_reserve(q_val, w_val, v)
        assert np.all(dr_hi >= dr_lo - 1e-9)
        assert dr_hi[0, 12] > dr_lo[0, 12]

    def test_dr_does_not_collapse_at_horizon(self, assumption_set: AssumptionSet):
        """The to-omega DR keeps building toward face — it does not collapse at
        the projection horizon the way a finite-horizon WL DR would."""
        engine = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config(ReserveBasis.VM20)
        )
        v = (1.0 + engine.config.effective_valuation_rate) ** (-1.0 / 12.0)
        t_val = engine._valuation_months_to_omega()
        q_val = engine._build_valuation_mortality(t_val)
        w_val = engine._build_valuation_lapse(t_val)
        dr = engine._compute_deterministic_reserve(q_val, w_val, v)[0]
        mid, end = 10 * 12, dr.shape[0] - 1
        assert dr[end] > dr[mid]  # grading toward face, not collapsing


class TestVM20Semantics:
    def _reserves(self, aset: AssumptionSet, premium: float):
        npr = WholeLife(_wl_block(premium), aset, _config(ReserveBasis.CRVM)).compute_reserves()
        vm20 = WholeLife(_wl_block(premium), aset, _config(ReserveBasis.VM20)).compute_reserves()
        engine = WholeLife(_wl_block(premium), aset, _config(ReserveBasis.VM20))
        v = (1.0 + engine.config.effective_valuation_rate) ** (-1.0 / 12.0)
        t_val = engine._valuation_months_to_omega()
        q_val = engine._build_valuation_mortality(t_val)
        w_val = engine._build_valuation_lapse(t_val)
        dr = engine._compute_deterministic_reserve(q_val, w_val, v)
        return npr, dr, vm20

    def test_vm20_equals_max_npr_dr(self, assumption_set: AssumptionSet):
        """VM20 == max(NPR_crvm, DR) elementwise, floored at 0."""
        npr, dr, vm20 = self._reserves(assumption_set, UNDERPRICED_PREMIUM)
        expected = np.maximum(np.maximum(npr, dr), 0.0)
        np.testing.assert_allclose(vm20, expected, rtol=1e-12, atol=1e-9)

    def test_vm20_at_least_npr_floor(self, assumption_set: AssumptionSet):
        """VM20 is never below the NPR (CRVM) floor, and never negative."""
        npr, _dr, vm20 = self._reserves(assumption_set, WELL_PRICED_PREMIUM)
        assert np.all(vm20 >= npr - 1e-9)
        assert np.all(vm20 >= -1e-9)

    def test_well_priced_floor_governs(self, assumption_set: AssumptionSet):
        """A well-priced block: the realistic DR sits below the NPR floor while
        the reserve is building, so VM20 coincides with the CRVM floor there."""
        npr, dr, vm20 = self._reserves(assumption_set, WELL_PRICED_PREMIUM)
        building = slice(12, 200)
        assert np.all(dr[0, building] < npr[0, building])
        np.testing.assert_allclose(vm20[0, building], npr[0, building], rtol=1e-12, atol=1e-9)

    def test_underpriced_dr_governs(self, assumption_set: AssumptionSet):
        """An underpriced block: the realistic DR exceeds the NPR floor across
        the durations, so VM20 follows the DR — the deficiency signal."""
        npr, dr, vm20 = self._reserves(assumption_set, UNDERPRICED_PREMIUM)
        building = slice(12, 200)
        assert np.all(dr[0, building] > npr[0, building] + 1.0)
        np.testing.assert_allclose(vm20[0, building], dr[0, building], rtol=1e-12, atol=1e-9)
        assert vm20[0, 120] > npr[0, 120] + 1.0


class TestVM20NoCollapse:
    """VM20 (>= the to-omega NPR) does not collapse at the projection horizon —
    the WL terminal-reserve artefact the epic closes."""

    def test_vm20_grades_toward_face(self, assumption_set: AssumptionSet):
        # Net-premium reserve collapses at the horizon (one-period terminal est.).
        np_res = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config()
        ).compute_reserves()[0]
        vm20 = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config(ReserveBasis.VM20)
        ).compute_reserves()[0]
        mid, end = 10 * 12, np_res.shape[0] - 1
        assert np_res[end] < 0.2 * np_res[mid]  # net premium collapses
        assert vm20[end] > vm20[mid]  # VM20 does not


class TestVM20DefaultUnchanged:
    def test_net_premium_default_byte_identical(self, assumption_set: AssumptionSet):
        """The VM-20 code path must not perturb the default NET_PREMIUM reserve."""
        implicit = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config()
        ).compute_reserves()
        explicit = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config(ReserveBasis.NET_PREMIUM)
        ).compute_reserves()
        np.testing.assert_array_equal(implicit, explicit)

    def test_valuation_lapse_matches_projection_over_horizon(self, assumption_set: AssumptionSet):
        """The to-omega lapse array matches _build_rate_arrays over the horizon."""
        engine = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM), assumption_set, _config(ReserveBasis.VM20)
        )
        t_proj = engine.config.projection_months
        _q, w_proj = engine._build_rate_arrays()
        w_val = engine._build_valuation_lapse(engine._valuation_months_to_omega())
        np.testing.assert_array_equal(w_val[:, :t_proj], w_proj)


class TestVM20LimitedPay:
    def test_vm20_short_limited_pay_raises(self, assumption_set: AssumptionSet):
        """VM-20 inherits the CRVM 20-pay guard (NPR uses the CRVM reserve)."""
        wl = WholeLife(
            _wl_block(WELL_PRICED_PREMIUM),
            assumption_set,
            _config(ReserveBasis.VM20),
            premium_payment_years=10,
        )
        with pytest.raises(PolarisComputationError, match="Full Preliminary Term"):
            wl.compute_reserves()


class TestVM20YRTIntegration:
    """A higher VM-20 reserve lowers the Net Amount at Risk, so the ceded YRT
    premium falls — with no change to the treaty layer."""

    def _yrt(self) -> YRTTreaty:
        return YRTTreaty(
            cession_pct=0.5,
            total_face_amount=500_000.0,
            flat_yrt_rate_per_1000=2.0,
        )

    def test_underpriced_vm20_lowers_ceded_premium(self, assumption_set: AssumptionSet):
        block = _wl_block(UNDERPRICED_PREMIUM)  # DR-driven VM-20 above net premium
        gross_np = WholeLife(block, assumption_set, _config(ReserveBasis.NET_PREMIUM)).project()
        gross_vm20 = WholeLife(block, assumption_set, _config(ReserveBasis.VM20)).project()

        # VM-20 reserve_balance exceeds the net-premium reserve mid-term.
        assert gross_vm20.reserve_balance[120] > gross_np.reserve_balance[120] + 1.0

        _net_np, ceded_np = self._yrt().apply(gross_np)
        _net_vm20, ceded_vm20 = self._yrt().apply(gross_vm20)

        # Higher reserve -> lower NAR -> lower ceded YRT premium mid-term.
        assert ceded_vm20.nar[120] < ceded_np.nar[120]
        assert ceded_vm20.yrt_premiums[120] < ceded_np.yrt_premiums[120]

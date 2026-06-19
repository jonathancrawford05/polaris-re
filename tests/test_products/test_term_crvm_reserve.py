"""
Closed-form and structural verification of the TermLife CRVM reserve (slice 2a).

CRVM is implemented as Full Preliminary Term (FPT); for level term the renewal
valuation premium never reaches the 20-pay expense-allowance cap, so FPT is
exact CRVM (ADR-088). The tests pin the reserve three independent ways:

1. The modified premiums (alpha, beta) satisfy the equivalence principle —
   ``alpha * a-due_year1 + beta * a-due_renewal == APV(all benefits)`` — which
   is the defining CRVM property and forces ``0V = 0``.
2. The FPT structural identities hold: ``0V = 0`` and the first-year terminal
   reserve ``12V = 0``; the CRVM reserve never exceeds the net premium reserve.
3. The engine's recursion reproduces a fully independent numpy reimplementation
   of the same modified-premium recursion.

A YRT integration test confirms that switching the basis to CRVM lowers the
early-duration reserve and therefore raises the Net Amount at Risk (and the
ceded YRT premium), with no treaty-layer change.
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


def _config(basis: ReserveBasis | None = None) -> ProjectionConfig:
    kw: dict = dict(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
    )
    if basis is not None:
        kw["reserve_basis"] = basis
    return ProjectionConfig(**kw)


def _term_block() -> InforceBlock:
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
                annual_premium=12_000.0,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=0.5,
                issue_date=date(2025, 1, 1),
                valuation_date=date(2025, 1, 1),
            )
        ]
    )


def _independent_crvm(q: np.ndarray, face: np.ndarray, v_monthly: float):
    """Fully independent numpy reimplementation of the CRVM/FPT reserve.

    Returns (alpha, beta, a_total, reserves) so the test can check the
    equivalence principle and the recursion separately from the engine.
    """
    n, t = q.shape
    tpx = np.ones((n, t), dtype=np.float64)
    for m in range(1, t):
        tpx[:, m] = tpx[:, m - 1] * (1.0 - q[:, m - 1])
    v_pow = v_monthly ** np.arange(t, dtype=np.float64)
    v_pow1 = v_monthly ** np.arange(1, t + 1, dtype=np.float64)
    benefit_pv = v_pow1[None, :] * tpx * q * face[:, None]
    annuity_pv = v_pow[None, :] * tpx
    yr1 = np.arange(t) < 12
    a1, ad1 = benefit_pv[:, yr1].sum(1), annuity_pv[:, yr1].sum(1)
    ar, adr = benefit_pv[:, ~yr1].sum(1), annuity_pv[:, ~yr1].sum(1)
    alpha = np.where(ad1 > 0, a1 / ad1, 0.0)
    beta = np.where(adr > 0, ar / adr, 0.0)
    a_total = benefit_pv.sum(1)

    reserves = np.zeros((n, t), dtype=np.float64)
    for m in range(t - 2, -1, -1):
        p = alpha if m < 12 else beta
        reserves[:, m] = (q[:, m] * face + (1.0 - q[:, m]) * reserves[:, m + 1]) * v_monthly - p
    reserves = np.maximum(reserves, 0.0)
    return alpha, beta, a_total, reserves


class TestCRVMTermReserve:
    def _engine(self, assumption_set: AssumptionSet, basis: ReserveBasis) -> TermLife:
        return TermLife(_term_block(), assumption_set, _config(basis))

    def test_equivalence_principle(self, assumption_set: AssumptionSet):
        """alpha*ad_year1 + beta*ad_renewal == APV(all benefits) (forces 0V=0)."""
        engine = self._engine(assumption_set, ReserveBasis.CRVM)
        q, _w = engine._build_rate_arrays()
        v = (1.0 + engine.config.effective_valuation_rate) ** (-1.0 / 12.0)
        face = engine.inforce.face_amount_vec

        n, t = q.shape
        tpx = np.ones((n, t))
        for m in range(1, t):
            tpx[:, m] = tpx[:, m - 1] * (1.0 - q[:, m - 1])
        v_pow = v ** np.arange(t)
        annuity_pv = v_pow[None, :] * tpx
        yr1 = np.arange(t) < 12
        ad1 = annuity_pv[:, yr1].sum(1)
        adr = annuity_pv[:, ~yr1].sum(1)

        alpha, beta = engine._compute_crvm_modified_premiums(q, v)
        _, _, a_total, _ = _independent_crvm(q, face, v)
        np.testing.assert_allclose(alpha * ad1 + beta * adr, a_total, rtol=1e-10, atol=1e-6)

    def test_zero_at_issue_and_year1_terminal(self, assumption_set: AssumptionSet):
        """FPT: 0V = 0 and the first-year terminal reserve 12V = 0."""
        crvm = self._engine(assumption_set, ReserveBasis.CRVM).compute_reserves()
        assert crvm[0, 0] == pytest.approx(0.0, abs=1e-3)
        assert crvm[0, 12] == pytest.approx(0.0, abs=1e-3)

    def test_crvm_never_exceeds_net_premium(self, assumption_set: AssumptionSet):
        """CRVM reserve <= net premium reserve everywhere; strictly < mid-term."""
        crvm = self._engine(assumption_set, ReserveBasis.CRVM).compute_reserves()
        netp = self._engine(assumption_set, ReserveBasis.NET_PREMIUM).compute_reserves()
        assert np.all(crvm <= netp + 1e-6)
        # The expense allowance makes CRVM strictly lower while the reserve is
        # building (e.g. end of year 5).
        assert crvm[0, 60] < netp[0, 60] - 1.0

    def test_matches_independent_recursion(self, assumption_set: AssumptionSet):
        """Engine recursion reproduces an independent numpy reimplementation."""
        engine = self._engine(assumption_set, ReserveBasis.CRVM)
        q, _w = engine._build_rate_arrays()
        v = (1.0 + engine.config.effective_valuation_rate) ** (-1.0 / 12.0)
        _, _, _, expected = _independent_crvm(q, engine.inforce.face_amount_vec, v)
        np.testing.assert_allclose(engine.compute_reserves(), expected, rtol=1e-12, atol=1e-9)

    def test_default_basis_unchanged_by_crvm_code(self, assumption_set: AssumptionSet):
        """NET_PREMIUM path is byte-identical to the historical reserve."""
        implicit = TermLife(_term_block(), assumption_set, _config()).compute_reserves()
        explicit = self._engine(assumption_set, ReserveBasis.NET_PREMIUM).compute_reserves()
        np.testing.assert_array_equal(implicit, explicit)


class TestCRVMRaisesNAR:
    """Switching to CRVM lowers the early reserve, so YRT NAR (and the ceded
    premium) rises — with no change to the treaty layer."""

    def _yrt(self) -> YRTTreaty:
        return YRTTreaty(
            cession_pct=0.5,
            total_face_amount=1_000_000.0,
            flat_yrt_rate_per_1000=2.0,
        )

    def test_crvm_increases_ceded_yrt_premium(self, assumption_set: AssumptionSet):
        block = _term_block()
        gross_np = TermLife(block, assumption_set, _config(ReserveBasis.NET_PREMIUM)).project()
        gross_crvm = TermLife(block, assumption_set, _config(ReserveBasis.CRVM)).project()

        # CRVM reserve_balance is at or below the net-premium reserve.
        assert np.all(gross_crvm.reserve_balance <= gross_np.reserve_balance + 1e-6)

        _net_np, ceded_np = self._yrt().apply(gross_np)
        _net_crvm, ceded_crvm = self._yrt().apply(gross_crvm)

        # Lower reserve -> higher NAR -> higher ceded YRT premium in the
        # early durations where the expense allowance is still graded in.
        assert ceded_crvm.nar[24] > ceded_np.nar[24]
        assert ceded_crvm.yrt_premiums[24] > ceded_np.yrt_premiums[24]

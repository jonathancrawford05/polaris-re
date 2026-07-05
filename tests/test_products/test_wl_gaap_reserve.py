"""
Closed-form and property tests for the WholeLife GAAP (FAS 60) reserve.

GAAP (FAS 60) is the net-premium benefit reserve on locked-in **best-estimate**
assumptions plus explicit provisions for adverse deviation (PADs). For WholeLife
it is a net **level** premium reserve valued **prospectively to omega** (like the
CRVM/VM-20 paths, so it does not collapse at the projection horizon), on a
*margined* best-estimate basis:

* mortality PAD — a multiplicative margin on the projection best-estimate q
  (``config.gaap_mortality_pad``), capped at 1.0, and
* interest PAD — an absolute haircut to the valuation rate
  (``config.gaap_interest_margin``).

Key contract points pinned here (ADR-128, Reserve-Basis Exactness Slice 4):

1. Closed form — neutral PADs (multiplier 1.0, margin 0.0) reproduce an
   independent numpy recomputation of the net-level-premium-to-omega reserve on
   the projection best-estimate mortality (a **different** reserve formulation —
   backward recursion vs the engine's reverse-cumulative-PV — so they agree to
   ~2e-9, checked at 1e-8). Unlike TermLife, GAAP does NOT equal WL NET_PREMIUM:
   the net-premium path uses the horizon-truncated backward recursion with a
   one-period terminal estimate, whereas GAAP values to omega — the same artefact
   the CRVM path closes.
2. A positive mortality PAD or interest margin raises the accumulation-phase
   reserve; the reserve is monotonic non-decreasing in the mortality PAD.
3. A formulation-independent equivalence-principle identity: the reserve at issue
   (a new-issue policy) is zero, ``V_0 = APV(benefits) - P·APV(annuity) = 0``.
4. GUARDRAIL: WL GAAP does **not** read ``assumptions.valuation_mortality`` — it
   is a best-estimate + PAD basis, not a prescribed static statutory basis. (WL
   does not model mortality improvement on any basis, so the improvement half of
   the TermLife guardrail does not apply here; the valuation-table independence
   is the operative property.)
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import (
    MortalityTable,
    MortalityTableArray,
    MortalityTableSource,
)
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.products.whole_life import WholeLife
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


def _assumptions(valuation_mortality: MortalityTable | None = None) -> AssumptionSet:
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    return AssumptionSet(
        mortality=_load_table(),
        lapse=lapse,
        valuation_mortality=valuation_mortality,
        version="test-v1",
    )


def _config(
    basis: ReserveBasis = ReserveBasis.GAAP,
    *,
    gaap_mortality_pad: float = 1.0,
    gaap_interest_margin: float = 0.0,
) -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=20,
        discount_rate=0.05,
        valuation_interest_rate=0.035,
        reserve_basis=basis,
        gaap_mortality_pad=gaap_mortality_pad,
        gaap_interest_margin=gaap_interest_margin,
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


def _recompute_net_level_to_omega(
    engine: WholeLife, *, pad: float, margin: float, premium_payment_years: int | None
) -> np.ndarray:
    """Independent numpy recomputation of the FAS 60 WL net level premium reserve.

    Net level premium reserve, valued prospectively to omega on the PAD-adjusted
    best-estimate mortality; sliced back to the projection horizon and floored.

    Deliberately a **different numerical formulation** than the engine: the engine
    computes the reserve by a reverse-cumulative-PV (`np.cumsum` on the reversed
    per-month PV arrays), whereas this recomputes it by the per-survivor
    **backward recursion** ``V_t = (q_t*face + (1-q_t)*V_{t+1})*v - P_t`` with
    terminal ``V_omega = 0``. The two are algebraically identical but accumulate
    floating-point error along different paths (they agree to ~2e-9, not machine
    epsilon), so this catches a shared *conceptual* error, not merely a
    transcription slip of the same expression (addresses PR #127 review P2). The
    net level premium ``P`` is the equivalence-principle definition — there is
    only one — so that half is necessarily shared.
    """
    t_val = engine._valuation_months_to_omega(None)
    n = engine.inforce.n_policies
    t_proj = engine.config.projection_months
    face = engine.inforce.face_amount_vec

    q_be = engine._build_valuation_mortality(t_val, None)
    q_val = np.minimum(q_be * pad, 1.0)
    i_gaap = max(0.035 - margin, 0.0)
    v = (1.0 + i_gaap) ** (-1.0 / 12.0)

    prem_months = (premium_payment_years * 12) if premium_payment_years is not None else t_val

    # Net level premium P = APV(benefits to omega) / APV(premium annuity-due).
    tpx = np.ones((n, t_val))
    for m in range(1, t_val):
        tpx[:, m] = tpx[:, m - 1] * (1.0 - q_val[:, m - 1])
    v_pow = v ** np.arange(t_val)
    v_pow1 = v ** np.arange(1, t_val + 1)
    benefit_pv = v_pow1[None, :] * tpx * q_val * face[:, None]  # (N, t_val)
    annuity_pv = v_pow[None, :] * tpx  # (N, t_val)
    prem_window = np.arange(t_val)[None, :] < prem_months
    apv_ben = benefit_pv.sum(axis=1)
    apv_ann = (annuity_pv * prem_window).sum(axis=1)
    p_net = np.where(apv_ann > 0.0, apv_ben / apv_ann, 0.0)  # (N,)

    # INDEPENDENT reserve formulation: per-survivor backward recursion to omega.
    reserves = np.zeros((n, t_val + 1))  # column t_val is the terminal V_omega = 0
    for t in range(t_val - 1, -1, -1):
        p_t = np.where(t < prem_months, p_net, 0.0)
        reserves[:, t] = (q_val[:, t] * face + (1.0 - q_val[:, t]) * reserves[:, t + 1]) * v - p_t
    return np.maximum(reserves[:, :t_proj], 0.0)


class TestGaapSupported:
    def test_gaap_is_supported_and_does_not_raise(self):
        engine = WholeLife(_wl_block(), _assumptions(), _config(ReserveBasis.GAAP))
        reserves = engine.compute_reserves()
        assert reserves.shape == (1, 240)
        assert reserves.max() > 0.0

    def test_gaap_supported_for_limited_pay(self):
        engine = WholeLife(
            _wl_block(),
            _assumptions(),
            _config(ReserveBasis.GAAP),
            premium_payment_years=20,
        )
        reserves = engine.compute_reserves()
        assert reserves.shape == (1, 240)
        assert reserves.max() > 0.0


class TestClosedFormRecomputation:
    """Independent numpy recomputation of the FAS 60 WL net level premium reserve.

    The recomputation uses a different reserve formulation than the engine
    (backward recursion vs the engine's reverse-cumulative-PV), so the two agree
    to ~2e-9 rather than machine epsilon — the ``atol=1e-8`` reflects that genuine
    independence (a shared reverse-cumsum would agree to 1e-9). See
    :func:`_recompute_net_level_to_omega`.
    """

    def test_neutral_pad_closed_form(self):
        block = _wl_block()
        engine = WholeLife(block, _assumptions(), _config(ReserveBasis.GAAP))
        got = engine.compute_reserves()
        expected = _recompute_net_level_to_omega(
            engine, pad=1.0, margin=0.0, premium_payment_years=None
        )
        np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-8)

    def test_padded_basis_closed_form(self):
        block = _wl_block()
        pad, margin = 1.15, 0.0075
        engine = WholeLife(
            block,
            _assumptions(),
            _config(ReserveBasis.GAAP, gaap_mortality_pad=pad, gaap_interest_margin=margin),
        )
        got = engine.compute_reserves()
        expected = _recompute_net_level_to_omega(
            engine, pad=pad, margin=margin, premium_payment_years=None
        )
        np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-8)

    def test_limited_pay_closed_form(self):
        block = _wl_block()
        engine = WholeLife(
            block, _assumptions(), _config(ReserveBasis.GAAP), premium_payment_years=20
        )
        got = engine.compute_reserves()
        expected = _recompute_net_level_to_omega(
            engine, pad=1.0, margin=0.0, premium_payment_years=20
        )
        np.testing.assert_allclose(got, expected, rtol=0.0, atol=1e-8)


class TestEquivalencePrincipleIdentity:
    """A truly formulation-independent check: the reserve at issue is zero.

    For a new-issue policy (duration 0 at the valuation date) the net level
    premium is set by the equivalence principle, so the prospective reserve at
    issue ``V_0 = APV(benefits) - P·APV(premium annuity) = 0`` exactly. This
    identity does not depend on the reserve *formulation* at all (neither the
    engine's reverse-cumsum nor the test's backward recursion), so it catches a
    conceptual error the mutually-consistent recomputation cannot.
    """

    def test_reserve_zero_at_issue_neutral(self):
        engine = WholeLife(_wl_block(), _assumptions(), _config(ReserveBasis.GAAP))
        reserves = engine.compute_reserves()
        np.testing.assert_allclose(reserves[:, 0], 0.0, rtol=0.0, atol=1e-6)

    @pytest.mark.parametrize("pad,margin", [(1.10, 0.0), (1.0, 0.01), (1.15, 0.0075)])
    def test_reserve_zero_at_issue_with_pads(self, pad: float, margin: float):
        # The equivalence identity holds on whatever (margined) basis the premium
        # is solved on, so V_0 = 0 regardless of the PADs.
        engine = WholeLife(
            _wl_block(),
            _assumptions(),
            _config(ReserveBasis.GAAP, gaap_mortality_pad=pad, gaap_interest_margin=margin),
        )
        reserves = engine.compute_reserves()
        np.testing.assert_allclose(reserves[:, 0], 0.0, rtol=0.0, atol=1e-6)


class TestNotEqualNetPremium:
    """GAAP (to omega) differs from WL NET_PREMIUM (horizon-truncated recursion)."""

    def test_gaap_differs_from_net_premium(self):
        block = _wl_block()
        assumptions = _assumptions()
        gaap = WholeLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        net = WholeLife(block, assumptions, _config(ReserveBasis.NET_PREMIUM)).compute_reserves()
        # The to-omega GAAP reserve does not collapse at the horizon edge the way
        # the net-premium one-period terminal estimate does, so the late-duration
        # reserves differ materially.
        assert abs(gaap[:, 200].sum() - net[:, 200].sum()) > 1.0


class TestPadDirection:
    """Adverse-deviation margins raise the accumulation-phase reserve."""

    def test_mortality_pad_raises_reserve(self):
        # A higher mortality PAD raises the reserve through the early/mid
        # accumulation phase. As in the TermLife GAAP interest-margin test, the
        # sign can flip in the late run-off durations (the higher net level
        # premium pulls the tail down), so the unambiguous property is over the
        # early/mid durations, checked here.
        block = _wl_block()
        assumptions = _assumptions()
        base = WholeLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        padded = WholeLife(
            block, assumptions, _config(ReserveBasis.GAAP, gaap_mortality_pad=1.10)
        ).compute_reserves()
        accumulation = slice(12, 132)
        assert np.all(padded[:, accumulation] >= base[:, accumulation] - 1e-9)
        assert padded[:, 120].sum() > base[:, 120].sum()

    def test_interest_margin_raises_reserve(self):
        # A lower locked-in discount rate raises the reserve through the
        # accumulation phase (the reserve builds toward the face amount).
        block = _wl_block()
        assumptions = _assumptions()
        base = WholeLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        padded = WholeLife(
            block, assumptions, _config(ReserveBasis.GAAP, gaap_interest_margin=0.01)
        ).compute_reserves()
        assert padded[:, 60].sum() > base[:, 60].sum()
        assert padded[:, 120].sum() > base[:, 120].sum()

    @pytest.mark.parametrize("pad", [1.0, 1.05, 1.10, 1.25])
    def test_reserve_monotonic_in_mortality_pad(self, pad: float):
        block = _wl_block()
        assumptions = _assumptions()
        neutral = WholeLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        padded = WholeLife(
            block, assumptions, _config(ReserveBasis.GAAP, gaap_mortality_pad=pad)
        ).compute_reserves()
        assert padded[:, 120].sum() >= neutral[:, 120].sum() - 1e-9


class TestGuardrails:
    """GAAP is a best-estimate + PAD basis, not a prescribed static one."""

    def test_gaap_ignores_valuation_mortality(self):
        # A wildly different prescribed valuation table must NOT move WL GAAP —
        # GAAP never reads assumptions.valuation_mortality.
        block = _wl_block()
        without = WholeLife(block, _assumptions(), _config(ReserveBasis.GAAP)).compute_reserves()
        with_slot = WholeLife(
            block,
            _assumptions(valuation_mortality=_load_table(scale=2.0)),
            _config(ReserveBasis.GAAP),
        ).compute_reserves()
        np.testing.assert_allclose(with_slot, without, rtol=0.0, atol=0.0)

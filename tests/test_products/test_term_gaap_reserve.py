"""
Closed-form and property tests for the TermLife GAAP (FAS 60) reserve.

GAAP (FAS 60) is the net-premium benefit reserve on locked-in **best-estimate**
assumptions plus explicit provisions for adverse deviation (PADs):

* mortality PAD — a multiplicative margin on the projection best-estimate q
  (``config.gaap_mortality_pad``), and
* interest PAD — an absolute haircut to the valuation rate
  (``config.gaap_interest_margin``).

Key contract points pinned here (ADR-127, Reserve-Basis Exactness Slice 3):

1. Neutral PADs (multiplier 1.0, margin 0.0) reduce GAAP **exactly** to the
   locked-in best-estimate NET_PREMIUM reserve — the closed-form identity.
2. A positive mortality PAD or interest margin raises the reserve.
3. An independent numpy recomputation of the FAS 60 net premium reserve on the
   PAD-adjusted basis reproduces the engine reserve to 1e-10.
4. GUARDRAIL: GAAP does **not** read ``assumptions.valuation_mortality`` and
   does **not** suppress mortality improvement (it is a best-estimate + PAD
   basis, not a prescribed static statutory basis).
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
    MortalityTableArray,
    MortalityTableSource,
)
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.products.term_life import TermLife
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


def _term_block(**overrides) -> InforceBlock:
    kw: dict = dict(
        policy_id="P1",
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
    kw.update(overrides)
    return InforceBlock(policies=[Policy(**kw)])


class TestGaapSupported:
    def test_gaap_is_supported_and_does_not_raise(self):
        engine = TermLife(_term_block(), _assumptions(), _config(ReserveBasis.GAAP))
        reserves = engine.compute_reserves()
        assert reserves.shape == (1, 240)
        assert reserves.max() > 0.0


class TestNeutralPadIdentity:
    """Neutral PADs collapse GAAP onto the locked-in best-estimate NPR."""

    def test_neutral_pad_equals_net_premium(self):
        block = _term_block()
        assumptions = _assumptions()
        gaap = TermLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        net = TermLife(block, assumptions, _config(ReserveBasis.NET_PREMIUM)).compute_reserves()
        np.testing.assert_allclose(gaap, net, rtol=0.0, atol=1e-9)

    def test_neutral_pad_identity_holds_with_improvement(self):
        # Improvement flows into the best estimate on BOTH bases, so the neutral
        # identity still holds when a Scale AA improvement is configured.
        block = _term_block()
        assumptions = _assumptions(improvement=MortalityImprovement.scale_aa(base_year=2025))
        gaap = TermLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        net = TermLife(block, assumptions, _config(ReserveBasis.NET_PREMIUM)).compute_reserves()
        np.testing.assert_allclose(gaap, net, rtol=0.0, atol=1e-9)


class TestPadDirection:
    """Adverse-deviation margins raise the reserve."""

    def test_mortality_pad_raises_reserve(self):
        block = _term_block()
        assumptions = _assumptions()
        base = TermLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        padded = TermLife(
            block, assumptions, _config(ReserveBasis.GAAP, gaap_mortality_pad=1.10)
        ).compute_reserves()
        mid = slice(24, 216)
        assert np.all(padded[:, mid] >= base[:, mid] - 1e-9)
        assert padded[:, 120].sum() > base[:, 120].sum()

    def test_interest_margin_raises_reserve(self):
        # A lower locked-in discount rate raises the reserve through the
        # accumulation phase. The sign can flip in the late run-off durations
        # (the higher net premium pulls the tail down), so the unambiguous
        # property is over the early/mid durations, checked here.
        block = _term_block()
        assumptions = _assumptions()
        base = TermLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        padded = TermLife(
            block, assumptions, _config(ReserveBasis.GAAP, gaap_interest_margin=0.01)
        ).compute_reserves()
        accumulation = slice(6, 132)
        assert np.all(padded[:, accumulation] >= base[:, accumulation] - 1e-9)
        assert padded[:, 60].sum() > base[:, 60].sum()

    @pytest.mark.parametrize("pad", [1.0, 1.05, 1.10, 1.25])
    def test_reserve_monotonic_in_mortality_pad(self, pad: float):
        block = _term_block()
        assumptions = _assumptions()
        neutral = TermLife(block, assumptions, _config(ReserveBasis.GAAP)).compute_reserves()
        padded = TermLife(
            block, assumptions, _config(ReserveBasis.GAAP, gaap_mortality_pad=pad)
        ).compute_reserves()
        assert padded[:, 120].sum() >= neutral[:, 120].sum() - 1e-9


class TestClosedFormRecomputation:
    """Independent numpy recomputation of the FAS 60 net premium reserve."""

    def test_independent_recomputation(self):
        block = _term_block()
        assumptions = _assumptions()
        pad, margin = 1.15, 0.0075
        config = _config(ReserveBasis.GAAP, gaap_mortality_pad=pad, gaap_interest_margin=margin)
        engine = TermLife(block, assumptions, config)
        engine_reserves = engine.compute_reserves()

        # Rebuild the PAD-adjusted basis independently.
        q_proj, _ = engine._build_rate_arrays()
        q_gaap = np.minimum(q_proj * pad, 1.0)
        i_gaap = 0.035 - margin
        v = (1.0 + i_gaap) ** (-1.0 / 12.0)
        n, t = q_gaap.shape
        face = 1_000_000.0

        # Net premium on the PAD basis: APV(benefits) / APV(annuity-due).
        tpx = np.ones((n, t))
        for m in range(1, t):
            tpx[:, m] = tpx[:, m - 1] * (1.0 - q_gaap[:, m - 1])
        v_pow = v ** np.arange(t)
        v_pow1 = v ** np.arange(1, t + 1)
        apv_ben = (v_pow1[None, :] * tpx * q_gaap * face).sum(axis=1)
        apv_ann = (v_pow[None, :] * tpx).sum(axis=1)
        p_net = apv_ben / apv_ann

        # Backward net premium recursion, terminal V_T = 0, floored at 0.
        expected = np.zeros((n, t))
        for m in range(t - 2, -1, -1):
            expected[:, m] = (
                q_gaap[:, m] * face + (1.0 - q_gaap[:, m]) * expected[:, m + 1]
            ) * v - p_net
        expected = np.maximum(expected, 0.0)

        np.testing.assert_allclose(engine_reserves, expected, rtol=0.0, atol=1e-10)


class TestGuardrails:
    """GAAP is a best-estimate + PAD basis, not a prescribed static one."""

    def test_gaap_ignores_valuation_mortality(self):
        # A wildly different prescribed valuation table must NOT move GAAP —
        # GAAP never reads assumptions.valuation_mortality.
        block = _term_block()
        without = TermLife(block, _assumptions(), _config(ReserveBasis.GAAP)).compute_reserves()
        with_slot = TermLife(
            block,
            _assumptions(valuation_mortality=_load_table(scale=2.0)),
            _config(ReserveBasis.GAAP),
        ).compute_reserves()
        np.testing.assert_allclose(with_slot, without, rtol=0.0, atol=0.0)

    def test_gaap_reflects_mortality_improvement(self):
        # Improvement lowers the best-estimate q, so GAAP (unlike a static
        # statutory basis) must move when a Scale AA improvement is configured.
        block = _term_block()
        no_impr = TermLife(block, _assumptions(), _config(ReserveBasis.GAAP)).compute_reserves()
        with_impr = TermLife(
            block,
            _assumptions(improvement=MortalityImprovement.scale_aa(base_year=2025)),
            _config(ReserveBasis.GAAP),
        ).compute_reserves()
        # Improvement reduces mortality, so the mid-duration benefit reserve falls.
        assert with_impr[:, 120].sum() < no_impr[:, 120].sum()

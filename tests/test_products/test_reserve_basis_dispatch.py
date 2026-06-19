"""
Tests for reserve-basis dispatch in the product engines (slice 1).

The default (NET_PREMIUM) basis must leave reserve output byte-identical to
the historical behaviour, and any not-yet-implemented basis must raise
PolarisComputationError rather than silently returning a net-premium reserve
mislabelled as CRVM / VM20 / GAAP.
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
from polaris_re.products.term_life import TermLife
from polaris_re.products.whole_life import WholeLife
from polaris_re.utils.table_io import load_mortality_csv

FIXTURES = Path(__file__).parent.parent / "fixtures"

# Bases still unimplemented per product. CRVM landed for TermLife in slice 2a
# (ADR-088) and for WholeLife in slice 2b (ADR-089). VM-20 simplified landed for
# TermLife in slice 3a (ADR-090); WholeLife VM-20 (the to-omega DR) is deferred
# to slice 3b, so WholeLife still raises on VM20. GAAP is unimplemented on both.
TERM_UNIMPLEMENTED_BASES = [ReserveBasis.GAAP]
WL_UNIMPLEMENTED_BASES = [ReserveBasis.VM20, ReserveBasis.GAAP]


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
        projection_horizon_years=10,
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


def _wl_block() -> InforceBlock:
    return InforceBlock(
        policies=[
            Policy(
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
        ]
    )


class TestDefaultBasisUnchanged:
    """NET_PREMIUM (default) must reproduce the historical reserve exactly."""

    def test_term_default_matches_explicit_net_premium(self, assumption_set: AssumptionSet):
        block = _term_block()
        implicit = TermLife(block, assumption_set, _config()).compute_reserves()
        explicit = TermLife(
            block, assumption_set, _config(ReserveBasis.NET_PREMIUM)
        ).compute_reserves()
        np.testing.assert_allclose(implicit, explicit, rtol=0.0, atol=0.0)
        # Sanity: the default path still produces a real (non-trivial) reserve.
        assert implicit.shape == (1, 120)
        assert implicit.max() > 0.0

    def test_whole_life_default_matches_explicit_net_premium(self, assumption_set: AssumptionSet):
        block = _wl_block()
        implicit = WholeLife(block, assumption_set, _config()).compute_reserves()
        explicit = WholeLife(
            block, assumption_set, _config(ReserveBasis.NET_PREMIUM)
        ).compute_reserves()
        np.testing.assert_allclose(implicit, explicit, rtol=0.0, atol=0.0)


class TestUnimplementedBasisRaises:
    """Selecting an unimplemented basis must raise, never silently fall back."""

    @pytest.mark.parametrize("basis", TERM_UNIMPLEMENTED_BASES)
    def test_term_raises(self, assumption_set: AssumptionSet, basis: ReserveBasis):
        engine = TermLife(_term_block(), assumption_set, _config(basis))
        with pytest.raises(PolarisComputationError, match="not yet implemented"):
            engine.compute_reserves()

    @pytest.mark.parametrize("basis", WL_UNIMPLEMENTED_BASES)
    def test_whole_life_raises(self, assumption_set: AssumptionSet, basis: ReserveBasis):
        engine = WholeLife(_wl_block(), assumption_set, _config(basis))
        with pytest.raises(PolarisComputationError, match="not yet implemented"):
            engine.compute_reserves()

    def test_error_message_names_supported_basis(self, assumption_set: AssumptionSet):
        # GAAP is still unimplemented for TermLife; the error names the
        # supported bases (which now include CRVM and VM20).
        engine = TermLife(_term_block(), assumption_set, _config(ReserveBasis.GAAP))
        with pytest.raises(PolarisComputationError, match="NET_PREMIUM"):
            engine.compute_reserves()

"""
Tests for `polaris_re.core.pipeline.derive_capital_nar` (ADR-049, Slice 3).

The helper feeds NAR vectors into `LICATCapital.required_capital` for
the cedant- and reinsurer-view profit tests at the CLI / API / dashboard
call sites. It mirrors the inforce-ratio approximation that
`YRTTreaty.apply` already uses, so capital NAR matches the YRT path
without changing the `CashFlowResult` contract.
"""

from datetime import date

import numpy as np
import pytest

from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.pipeline import derive_capital_nar


def _gross_with_runoff(
    n: int = 24,
    initial_premium: float = 1000.0,
    runoff_per_step: float = 10.0,
    reserve: float = 0.0,
) -> CashFlowResult:
    """Build a GROSS CashFlowResult with linearly declining premiums."""
    prems = np.maximum(initial_premium - runoff_per_step * np.arange(n), 0.0)
    return CashFlowResult(
        run_id="test-nar",
        valuation_date=date(2025, 1, 1),
        basis="GROSS",
        assumption_set_version="test-v1",
        product_type="TERM",
        projection_months=n,
        time_index=np.arange("2025-01", n + 1, dtype="datetime64[M]")[:n],
        gross_premiums=prems.astype(np.float64),
        death_claims=np.zeros(n, dtype=np.float64),
        lapse_surrenders=np.zeros(n, dtype=np.float64),
        expenses=np.zeros(n, dtype=np.float64),
        reserve_balance=np.full(n, reserve, dtype=np.float64),
        reserve_increase=np.zeros(n, dtype=np.float64),
        net_cash_flow=np.zeros(n, dtype=np.float64),
    )


class TestDeriveCapitalNarBasics:
    def test_initial_nar_equals_face_minus_reserve_when_no_treaty(self) -> None:
        gross = _gross_with_runoff(n=12, reserve=200_000.0)
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=gross.reserve_balance,
            face_amount_total=1_000_000.0,
        )
        # face_share = 1.0 (no treaty); inforce_ratio[0] = 1.0
        np.testing.assert_allclose(nar[0], 1_000_000.0 - 200_000.0)

    def test_returns_float64_shape_t(self) -> None:
        gross = _gross_with_runoff(n=18)
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=gross.reserve_balance,
            face_amount_total=500_000.0,
        )
        assert nar.shape == (18,)
        assert nar.dtype == np.float64

    def test_floor_at_zero_when_reserve_exceeds_face(self) -> None:
        gross = _gross_with_runoff(n=6, reserve=2_000_000.0)
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=gross.reserve_balance,
            face_amount_total=1_000_000.0,
        )
        np.testing.assert_array_equal(nar, np.zeros(6))

    def test_zero_initial_premium_uses_unit_inforce_ratio(self) -> None:
        # When initial gross premium is zero the helper falls back to
        # ones(T) so capital is non-zero on degenerate but valid runs.
        gross = _gross_with_runoff(n=4, initial_premium=0.0, runoff_per_step=0.0)
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=gross.reserve_balance,
            face_amount_total=750_000.0,
        )
        np.testing.assert_allclose(nar, np.full(4, 750_000.0))

    def test_empty_projection_returns_empty_vector(self) -> None:
        gross = _gross_with_runoff(n=0)
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.array([], dtype=np.float64),
            face_amount_total=1_000_000.0,
        )
        assert nar.shape == (0,)
        assert nar.dtype == np.float64


class TestDeriveCapitalNarInforceRatio:
    def test_runoff_scales_face_in_force(self) -> None:
        # Linear runoff: premium drops 10 per step from 1000 → ratio = 1, 0.99, ...
        gross = _gross_with_runoff(n=5, initial_premium=1000.0, runoff_per_step=100.0)
        # ratios = [1.0, 0.9, 0.8, 0.7, 0.6]
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(5, dtype=np.float64),
            face_amount_total=1_000_000.0,
        )
        np.testing.assert_allclose(
            nar, np.array([1_000_000.0, 900_000.0, 800_000.0, 700_000.0, 600_000.0])
        )


class TestDeriveCapitalNarCessionAware:
    """Cedant vs reinsurer face-share scaling (CONTINUATION reviewer guidance)."""

    def test_cedant_face_share_complement_of_cession(self) -> None:
        gross = _gross_with_runoff(n=12, runoff_per_step=0.0)  # constant ratio = 1.0
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(12, dtype=np.float64),
            face_amount_total=1_000_000.0,
            cession_pct=0.30,
            is_reinsurer=False,
        )
        # Cedant retains (1 - 0.30) = 0.70 of face → 700,000 NAR per period
        np.testing.assert_allclose(nar, np.full(12, 700_000.0))

    def test_reinsurer_face_share_equals_cession(self) -> None:
        gross = _gross_with_runoff(n=12, runoff_per_step=0.0)
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(12, dtype=np.float64),
            face_amount_total=1_000_000.0,
            cession_pct=0.30,
            is_reinsurer=True,
        )
        np.testing.assert_allclose(nar, np.full(12, 300_000.0))

    def test_cedant_plus_reinsurer_nar_equals_total_when_reserves_zero(self) -> None:
        gross = _gross_with_runoff(n=8, initial_premium=1000.0, runoff_per_step=50.0)
        cedant_nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(8, dtype=np.float64),
            face_amount_total=2_000_000.0,
            cession_pct=0.40,
            is_reinsurer=False,
        )
        reinsurer_nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(8, dtype=np.float64),
            face_amount_total=2_000_000.0,
            cession_pct=0.40,
            is_reinsurer=True,
        )
        full_nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(8, dtype=np.float64),
            face_amount_total=2_000_000.0,
        )
        np.testing.assert_allclose(cedant_nar + reinsurer_nar, full_nar)

    @pytest.mark.parametrize("cession", [0.0, 0.10, 0.50, 0.90, 1.0])
    def test_cession_zero_means_reinsurer_zero_nar(self, cession: float) -> None:
        gross = _gross_with_runoff(n=6, runoff_per_step=0.0)
        cedant_nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(6, dtype=np.float64),
            face_amount_total=1_000_000.0,
            cession_pct=cession,
            is_reinsurer=False,
        )
        reinsurer_nar = derive_capital_nar(
            gross=gross,
            reserve_balance=np.zeros(6, dtype=np.float64),
            face_amount_total=1_000_000.0,
            cession_pct=cession,
            is_reinsurer=True,
        )
        np.testing.assert_allclose(cedant_nar, np.full(6, 1_000_000.0 * (1.0 - cession)))
        np.testing.assert_allclose(reinsurer_nar, np.full(6, 1_000_000.0 * cession))


class TestDeriveCapitalNarReserveSubtraction:
    def test_reserves_subtract_per_period(self) -> None:
        gross = _gross_with_runoff(n=4, runoff_per_step=0.0)
        reserves = np.array([100_000.0, 200_000.0, 300_000.0, 400_000.0], dtype=np.float64)
        nar = derive_capital_nar(
            gross=gross,
            reserve_balance=reserves,
            face_amount_total=1_000_000.0,
        )
        np.testing.assert_allclose(nar, np.array([900_000.0, 800_000.0, 700_000.0, 600_000.0]))

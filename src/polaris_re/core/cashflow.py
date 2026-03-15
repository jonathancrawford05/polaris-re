"""
CashFlowResult — the canonical output structure of any projection run.

Carries aggregated (and optionally seriatim) cash flow arrays across the
projection time horizon, along with metadata for auditability.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np

__all__ = ["CashFlowResult"]


@dataclass
class CashFlowResult:
    """
    Output of a projection run, representing all cash flows over the projection horizon.

    All cash flow arrays have shape (T,) where T = projection_months.
    Values are in dollars, expressed as of each monthly period.

    Basis:
        GROSS  — direct business, before reinsurance
        CEDED  — cash flows transferred to reinsurer
        NET    — GROSS minus CEDED; what the cedant retains

    Invariant: net + ceded == gross for all cash flow lines.
    """

    # --- Metadata ---
    run_id: str
    valuation_date: date
    basis: Literal["GROSS", "CEDED", "NET"]
    assumption_set_version: str
    product_type: str
    block_id: str | None = None

    # --- Time dimension ---
    projection_months: int = 0
    time_index: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[M]"))

    # --- Aggregate cash flow arrays, shape (T,) ---
    gross_premiums: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    death_claims: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    lapse_surrenders: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    expenses: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    reserve_balance: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    reserve_increase: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))

    # net_cash_flow = gross_premiums - death_claims - lapse_surrenders - expenses - reserve_increase
    net_cash_flow: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))

    # --- Optional seriatim arrays, shape (N, T) — populated when seriatim=True ---
    seriatim_premiums: np.ndarray | None = None
    seriatim_claims: np.ndarray | None = None
    seriatim_reserves: np.ndarray | None = None
    seriatim_lx: np.ndarray | None = None  # in-force factors

    # --- Reinsurance-specific ---
    nar: np.ndarray | None = None  # Net Amount at Risk, shape (T,)
    yrt_premiums: np.ndarray | None = None  # YRT ceded premiums, shape (T,)

    def __post_init__(self) -> None:
        """Validate array shape consistency after construction."""
        arrays = [
            ("gross_premiums", self.gross_premiums),
            ("death_claims", self.death_claims),
            ("lapse_surrenders", self.lapse_surrenders),
            ("expenses", self.expenses),
            ("net_cash_flow", self.net_cash_flow),
        ]
        lengths = {name: len(arr) for name, arr in arrays if len(arr) > 0}
        unique_lengths = set(lengths.values())
        if len(unique_lengths) > 1:
            raise ValueError(f"CashFlowResult arrays have inconsistent lengths: {lengths}")

    # ------------------------------------------------------------------
    # Summary metrics
    # ------------------------------------------------------------------

    def pv_net_cash_flow(self, discount_rate: float) -> float:
        """Present value of net cash flows at the given annual discount rate."""
        n_periods = len(self.net_cash_flow)
        v = (1.0 + discount_rate) ** (-1.0 / 12.0)
        discount_factors = v ** np.arange(1, n_periods + 1)
        return float(np.dot(self.net_cash_flow, discount_factors))

    def pv_premiums(self, discount_rate: float) -> float:
        """Present value of gross premiums at the given annual discount rate."""
        n_periods = len(self.gross_premiums)
        v = (1.0 + discount_rate) ** (-1.0 / 12.0)
        discount_factors = v ** np.arange(1, n_periods + 1)
        return float(np.dot(self.gross_premiums, discount_factors))

    def loss_ratio(self) -> float:
        """Total claims / total premiums (undiscounted). Returns 0.0 if no premiums."""
        total_premiums = float(self.gross_premiums.sum())
        if total_premiums == 0.0:
            return 0.0
        return float(self.death_claims.sum()) / total_premiums

    def cumulative_net_cash_flow(self) -> np.ndarray:
        """Cumulative sum of net cash flows over the projection horizon, shape (T,)."""
        return np.cumsum(self.net_cash_flow)

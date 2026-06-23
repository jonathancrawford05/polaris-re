"""
Shared capital-model protocols and helpers (ADR-098).

This module defines the jurisdiction-agnostic contract that every regulatory
capital calculator in Polaris RE satisfies, so that downstream consumers
(`ProfitTester.run_with_capital`, portfolio capital roll-ups, CLI / API
surfaces) can work with any standard — Canadian **LICAT**, US **RBC**, EU
**Solvency II** — through one interface.

Two structural `Protocol`s capture the contract `LICATCapital` /
`CapitalResult` already established (ADR-047 / ADR-048):

- :class:`CapitalModel` — a calculator with
  ``required_capital(cashflows, nar=None) -> CapitalSchedule``.
- :class:`CapitalSchedule` — the required-capital schedule it returns, carrying
  a per-month capital array plus the present-value / strain helpers used by the
  return-on-capital metric.

Both are structural (PEP 544) — a class satisfies them by shape, not by
inheritance — so the pre-existing `LICATCapital` and `CapitalResult` conform
without modification, and new siblings (`RBCCapital`, `SolvencyIICapital`) only
need to match the same shape.

The two free helpers (`discount_stream`, `strain_of`) factor out the discounting
and period-over-period-change arithmetic shared by every `CapitalSchedule`
implementation, so new modules do not re-derive it. They are deliberately small
and dependency-free.

Sign convention (shared by all implementations): required capital is a positive,
time-varying scalar the reinsurer holds against retained business. It is NOT
discounted at the hurdle rate — the time-value adjustment lives in the
return-on-capital metric (`ProfitTester.run_with_capital`).
"""

from typing import Literal, Protocol, runtime_checkable

import numpy as np

from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.policy import ProductType

type CapitalModelId = Literal["licat", "rbc", "solvency2"]
"""The jurisdiction ids the CLI / API selector accepts (ADR-101)."""

SUPPORTED_CAPITAL_MODELS: tuple[CapitalModelId, ...] = ("licat", "rbc", "solvency2")
"""Registry of selectable regulatory-capital jurisdictions.

``licat`` is the default (Canada, ADR-047/048); ``rbc`` is US NAIC RBC
(ADR-098) and ``solvency2`` is the EU SCR (ADR-100). Every entry resolves to a
calculator satisfying :class:`CapitalModel` via :func:`capital_model_for`.
"""

CAPITAL_MODEL_LABELS: dict[CapitalModelId, str] = {
    "licat": "LICAT (Canada)",
    "rbc": "US RBC",
    "solvency2": "EU Solvency II",
}
"""Human-readable jurisdiction labels for the presentation surfaces (ADR-102).

Shared by the dashboard capital tiles and the Excel capital-block header so the
displayed standard always matches the calculator that ran. Keyed by the same
:data:`SUPPORTED_CAPITAL_MODELS` ids, so a fourth jurisdiction is labelled in
exactly one place.
"""


def capital_model_label(model_id: str | None) -> str:
    """Return the display label for a jurisdiction id (ADR-102).

    Falls back to ``"LICAT (Canada)"`` for ``None`` because every capital
    schedule produced before the cross-jurisdiction epoch (pre-ADR-098) was
    LICAT, so an un-tagged historical export is LICAT by construction. An
    unrecognised id is returned upper-cased rather than raising — labels are a
    display concern, not a validation boundary.
    """
    if model_id is None:
        return CAPITAL_MODEL_LABELS["licat"]
    normalized = model_id.strip().lower()
    return CAPITAL_MODEL_LABELS.get(normalized, model_id.upper())  # type: ignore[arg-type]


__all__ = [
    "CAPITAL_MODEL_LABELS",
    "SUPPORTED_CAPITAL_MODELS",
    "CapitalModel",
    "CapitalModelId",
    "CapitalSchedule",
    "capital_model_for",
    "capital_model_label",
    "discount_stream",
    "strain_of",
]


def capital_model_for(model_id: str, product_type: ProductType) -> "CapitalModel":
    """Resolve a jurisdiction id to a per-product regulatory-capital calculator.

    The single registry behind the CLI ``--capital`` flag and the API
    ``capital_model`` field (ADR-101), so both surfaces stay in lock-step and a
    new jurisdiction is added in exactly one place. The id is normalised
    (stripped, lower-cased) before lookup.

    Imports of the concrete calculators are deferred to call time because
    ``rbc`` / ``capital`` / ``solvency2`` import this module for `discount_stream`
    / `strain_of` — a module-level import here would be circular.

    Args:
        model_id: One of :data:`SUPPORTED_CAPITAL_MODELS` (case-insensitive).
        product_type: Drives the per-product factor defaults via the
            calculator's ``for_product`` constructor.

    Returns:
        A calculator (`LICATCapital` / `RBCCapital` / `SolvencyIICapital`)
        satisfying :class:`CapitalModel`.

    Raises:
        ValueError: If ``model_id`` is not a supported jurisdiction. The message
            lists the supported ids so callers can surface it verbatim.
    """
    normalized = model_id.strip().lower()
    if normalized == "licat":
        from polaris_re.analytics.capital import LICATCapital

        return LICATCapital.for_product(product_type)
    if normalized == "rbc":
        from polaris_re.analytics.rbc import RBCCapital

        return RBCCapital.for_product(product_type)
    if normalized == "solvency2":
        from polaris_re.analytics.solvency2 import SolvencyIICapital

        return SolvencyIICapital.for_product(product_type)
    supported = ", ".join(SUPPORTED_CAPITAL_MODELS)
    raise ValueError(f"Unknown capital model {model_id!r}. Supported: {supported}.")


def discount_stream(stream: np.ndarray, discount_rate: float) -> float:
    """
    Present value of a monthly stream at a flat annual rate, discounting each
    period-`t` value by ``v ** t`` with ``v = (1 + rate) ** (-1/12)`` and
    ``t = 1 … n`` (end-of-period convention).

    Shared by every `CapitalSchedule.pv_capital` / `pv_capital_strain`.
    """
    n = len(stream)
    if n == 0:
        return 0.0
    v = (1.0 + discount_rate) ** (-1.0 / 12.0)
    discount_factors = v ** np.arange(1, n + 1, dtype=np.float64)
    return float(np.dot(np.asarray(stream, dtype=np.float64), discount_factors))


def strain_of(capital_by_period: np.ndarray) -> np.ndarray:
    """
    Period-over-period change in a required-capital stream, shape ``(T,)``.

    ``strain_t = capital_t - capital_{t-1}`` with ``capital_{-1} = 0``. Positive
    strain is capital injected at period ``t``; negative strain is capital
    released. Does NOT include the terminal release of the residual balance —
    that adjustment lives in `ProfitTester.run_with_capital`.
    """
    n = len(capital_by_period)
    if n == 0:
        return np.array([], dtype=np.float64)
    cap = np.asarray(capital_by_period, dtype=np.float64)
    strain = np.empty(n, dtype=np.float64)
    strain[0] = cap[0]
    if n > 1:
        strain[1:] = cap[1:] - cap[:-1]
    return strain


@runtime_checkable
class CapitalSchedule(Protocol):
    """
    Required-capital schedule contract returned by a :class:`CapitalModel`.

    A schedule carries the per-month capital array (`capital_by_period`, shape
    ``(T,)``, dollars) plus the scalar summaries and present-value / strain
    helpers that return-on-capital depends on. `CapitalResult` (LICAT) and
    `RBCResult` (US RBC) both satisfy this structurally.
    """

    projection_months: int
    capital_by_period: np.ndarray
    initial_capital: float
    peak_capital: float

    def pv_capital(self, discount_rate: float) -> float:
        """PV of the capital STOCK at a flat annual rate."""
        ...

    def capital_strain(self) -> np.ndarray:
        """Period-over-period change in required capital, shape ``(T,)``."""
        ...

    def pv_capital_strain(self, discount_rate: float) -> float:
        """PV of the capital STRAIN at a flat annual rate."""
        ...


@runtime_checkable
class CapitalModel(Protocol):
    """
    Regulatory-capital calculator contract.

    A capital model maps a (GROSS or NET) `CashFlowResult` — optionally with an
    explicit NAR override — to a :class:`CapitalSchedule`. `LICATCapital`,
    `RBCCapital`, and (Slice 3) `SolvencyIICapital` all satisfy this.
    """

    def required_capital(
        self, cashflows: CashFlowResult, nar: np.ndarray | None = None
    ) -> CapitalSchedule:
        """Compute the required-capital schedule over the projection horizon."""
        ...

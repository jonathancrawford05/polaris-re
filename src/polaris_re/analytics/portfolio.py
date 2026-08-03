"""
Portfolio aggregation — multi-deal runner for reinsurer-level risk metrics.

A reinsurer never prices a single treaty in isolation. The ``Portfolio``
class holds a collection of independent reinsurance deals — each an inforce
block, assumption set, projection config, and proportional treaty — and
aggregates their projected cash flows into a single reinsurer-level view.

Each deal is projected independently via the product dispatch engine, the
treaty is applied, and the *ceded* cash flow (the reinsurer's assumed
position) is profit-tested. ``Portfolio.run()`` returns a ``PortfolioResult``
carrying the aggregate net cash flow, total PV profits, total IRR, a per-deal
breakdown, and concentration metrics by cedant, product type, and treaty type.

Aggregation is exact: the aggregate net cash flow is the month-by-month sum
of the per-deal reinsurer cash flows (deals with a shorter horizon contribute
zero beyond their last month), so ``total_pv_profits`` equals the sum of the
per-deal PV profits.

The book is editable after construction (ADR-178). ``remove_deal`` /
``replace_deal`` / ``clear_deals`` mutate in place, ``without_deal`` returns a
filtered copy, and ``deal_ids`` / ``get_deal`` / ``len()`` / ``in`` inspect it —
so the natural portfolio what-if ("what does the book look like without
DEAL_C?", "re-quote DEAL_B at 40% cession") no longer requires rebuilding the
portfolio from its source objects. Edits are validated by the same rules as
``add_deal``, and an unknown deal id raises rather than silently no-opping.

Repeated runs can reuse per-deal projections via the **opt-in** result cache
``Portfolio(..., cache=True)`` (ADR-179), keyed ``(deal_id, hurdle_rate)`` and
invalidated per deal by each of the four mutation verbs. It is opt-in because a
``Deal`` holds mutable projection inputs: enabling it asserts "these deals are
frozen for the duration". Numbers are unchanged either way — the cache only
decides whether a projection is recomputed or reused.

Deals are independent until the aggregation sum, so a run can also fan the
per-deal projections out across threads: ``run(..., max_workers=N)`` (ADR-180),
forwarded by ``run_with_capital`` and ``run_scenarios``. ``None`` (the default)
keeps the serial path exactly as it was. The fan-out is one task per deal and
the results are collected in deal order, so the order-sensitive aggregation sum
— and therefore every number a run produces — is bit-identical to the serial
path at any worker count.

Scope: proportional treaties only — YRT, coinsurance, modco — each exposing
a ``cession_pct``. Stop-loss and other non-proportional structures are out
of scope. Policy-level cession overrides are not applied; the treaty-level
``cession_pct`` governs every deal. Each deal's inforce block must contain a
single product type.

Time alignment (ADR-061). ``run`` takes an ``align`` mode:

- ``align="strict"`` (default) sums cash flows by month index and requires
  every deal to share a valuation date — mixed inception dates would be out
  of phase, so they are rejected. In this mode the aggregate PV equals the
  sum of the per-deal PVs.
- ``align="calendar"`` places each deal on a common monthly calendar grid
  keyed off the earliest valuation date, so a real reinsurer book with
  treaties inception-dated across years aggregates correctly. Because PV
  discounts from the common origin, a deal inception-dated ``o`` months late
  contributes ``v**o`` times its standalone PV: the aggregate ``total_pv_profits``
  is the portfolio NPV as of the common origin, which is NOT the naive sum
  of per-deal PVs once inception dates differ.
"""

import dataclasses
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal

import numpy as np

from polaris_re.analytics.capital_base import CapitalModel
from polaris_re.analytics.profit_test import ProfitTester, ProfitTestResult
from polaris_re.analytics.scenario import ScenarioAdjustment, apply_scenario_to_assumptions
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.pipeline import ceded_to_reinsurer_view
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty
from polaris_re.utils.date_utils import months_between

type AlignMode = Literal["strict", "calendar"]
type ConcentrationBasis = Literal["ceded_face", "ceded_nar_peak", "pv_premium"]

CONCENTRATION_BASES: Final[tuple[ConcentrationBasis, ...]] = (
    "ceded_face",
    "ceded_nar_peak",
    "pv_premium",
)

__all__ = [
    "CONCENTRATION_BASES",
    "AlignMode",
    "CacheStats",
    "ConcentrationBasis",
    "Deal",
    "DealResult",
    "Portfolio",
    "PortfolioResult",
    "PortfolioResultWithCapital",
    "PortfolioScenarioResult",
]


# ---------------------------------------------------------------------------
# Deal — one validated reinsurance deal inside a portfolio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Deal:
    """A single reinsurance deal held by a ``Portfolio``.

    Built and validated by :func:`_build_deal`, the single choke point behind
    both ``Portfolio.add_deal`` and ``Portfolio.replace_deal`` (ADR-178) —
    callers do not instantiate this directly. ``product_type``,
    ``treaty_type``, and ``cession_pct`` are cached at construction time (the
    latter validated non-``None`` by ``_build_deal``) for the per-deal
    breakdown and concentration metrics.
    """

    deal_id: str
    cedant: str
    inforce: InforceBlock
    assumptions: AssumptionSet
    config: ProjectionConfig
    treaty: BaseTreaty
    product_type: str
    treaty_type: str
    cession_pct: float


@dataclass(frozen=True)
class CacheStats:
    """Snapshot of a portfolio's per-deal result cache (ADR-179).

    Returned by :meth:`Portfolio.cache_stats`. ``hits`` and ``misses`` are
    **lifetime** counters for the instance — :meth:`Portfolio.clear_cache` and
    the mutation verbs drop entries (lowering ``size``) but never rewind the
    counters, so a caller can tell "the cache was never used" from "the cache
    was used and then invalidated". On a portfolio built without ``cache=True``
    every field is zero and ``enabled`` is ``False``.
    """

    enabled: bool
    hits: int
    misses: int
    size: int


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DealResult:
    """Per-deal contribution to a portfolio, from the reinsurer's view.

    ``profit_test`` is the reinsurer-perspective profit test (the ceded
    cash flow re-viewed as NET). ``net_cash_flow`` is that same reinsurer
    cash flow vector, shape ``(T_deal,)``. ``ceded_nar`` is the ceded Net
    Amount at Risk, shape ``(T_deal,)`` — zeros when the treaty exposes no
    NAR vector (coinsurance / modco).

    ``valuation_date`` carries the deal's own valuation date (the projection
    start). ``grid_offset`` is the deal's whole-month offset onto the
    portfolio's common calendar grid: 0 under ``align="strict"`` and under
    ``align="calendar"`` for the earliest-dated deal, positive for later
    deals. Together they let JSON consumers reconstruct calendar placement
    without re-deriving dates (ADR-061).
    """

    deal_id: str
    cedant: str
    product_type: str
    treaty_type: str
    n_policies: int
    face_amount: float
    ceded_face: float
    profit_test: ProfitTestResult
    net_cash_flow: np.ndarray
    ceded_nar: np.ndarray
    valuation_date: date | None = None
    grid_offset: int = 0


@dataclass(frozen=True)
class PortfolioResult:
    """Aggregate reinsurer-level result across every deal in a portfolio.

    Monetary values in dollars; rates as decimals. ``total_pv_profits``,
    ``total_irr``, ``breakeven_year``, and ``profit_margin`` are computed by
    a ``ProfitTester`` run on the aggregate cash flow, so they inherit the
    standard reporting guardrails (ADR-041).

    ``aggregate_cash_flow`` carries the full reinsurer-side cash flow
    (premiums, claims, expenses, reserves, NCF) as the month-by-month sum
    across every deal's reinsurer view, padded with zeros for deals with a
    shorter horizon. Use this for loss-ratio reporting, portfolio-level
    capital, and any downstream consumer that needs more than NCF.

    Concentration dictionaries map a category label to its share of total
    ceded face (shares sum to 1.0). ``hhi`` carries the Herfindahl-Hirschman
    index for each dimension ("cedant", "product", "treaty") — the sum of
    squared shares, ranging from ``1/k`` (perfectly diversified across ``k``
    categories) to ``1.0`` (fully concentrated).

    ``concentration_by_basis`` exposes the same per-dimension shares under
    multiple weight bases — ``ceded_face`` (the static face-weighted view that
    matches the flat fields above), ``ceded_nar_peak`` (each deal weighted by
    its peak ceded NAR — risk exposure), and ``pv_premium`` (revenue
    exposure, taken from each deal's reinsurer-view profit test). Shape is
    ``{basis: {dimension: {label: share}}}`` with each label-share dict
    summing to 1.0. ``hhi_by_basis`` carries the matching Herfindahl indices
    as ``{basis: {dimension: hhi}}``. The ``ceded_face`` basis reproduces the
    flat ``concentration_by_*`` / ``hhi`` fields bit-for-bit so the two
    surfaces never drift (ADR-069).
    """

    n_deals: int
    hurdle_rate: float
    projection_months: int
    aggregate_cash_flow: CashFlowResult
    aggregate_net_cash_flow: np.ndarray
    aggregate_ceded_nar: np.ndarray
    total_pv_profits: float
    total_irr: float | None
    breakeven_year: int | None
    profit_margin: float | None
    total_undiscounted_profit: float
    total_face_amount: float
    total_ceded_face: float
    peak_ceded_nar: float
    deal_results: list[DealResult]
    concentration_by_cedant: dict[str, float]
    concentration_by_product: dict[str, float]
    concentration_by_treaty: dict[str, float]
    hhi: dict[str, float]
    concentration_by_basis: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    hhi_by_basis: dict[str, dict[str, float]] = field(default_factory=dict)

    def concentration_by_dimension(self) -> dict[str, dict[str, dict[str, float]]]:
        """Return the dimension-outer transpose of ``concentration_by_basis``.

        Shape: ``{dimension: {basis: {label: share}}}`` — the
        ``concentration[dimension][weight_basis]`` access pattern originally
        proposed in PRODUCT_DIRECTION_2026-05-23. Useful when a downstream
        consumer holds the dimension fixed and flips weight basis (e.g. a
        dashboard control comparing cedant concentration under face / NAR /
        PV weights). The returned mapping is freshly constructed but the
        inner share dicts are returned by reference — no storage is
        duplicated (ADR-073).
        """
        return _transpose_basis_outer(self.concentration_by_basis)

    def hhi_by_dimension(self) -> dict[str, dict[str, float]]:
        """Return the dimension-outer transpose of ``hhi_by_basis``.

        Shape: ``{dimension: {basis: hhi}}``. The dual of
        :meth:`concentration_by_dimension` for the Herfindahl indices.
        """
        return _transpose_basis_outer(self.hhi_by_basis)

    def to_dict(self) -> dict[str, object]:
        """Flatten the result into a JSON-serialisable plain dict.

        Numpy arrays become lists, the per-deal breakdown becomes a list of
        plain dicts (each with a nested ``profit_test`` block carrying the
        ``ProfitTestResult`` fields), and the three ``concentration_by_*``
        dimensions are grouped under a single ``concentration`` key for
        ergonomic access by dimension. The shape matches what the CLI
        ``polaris portfolio`` command and the ``POST /api/v1/portfolio`` API
        endpoint emit.

        ``grid_origin`` (ISO date) is the common monthly grid origin —
        identical to every deal's valuation date under ``align="strict"``,
        the earliest deal's valuation date under ``align="calendar"``. Each
        per-deal block carries its own ``valuation_date`` and
        ``grid_offset`` (months from origin) so JSON consumers can
        reconstruct placement without re-deriving dates (ADR-061).
        """
        cf = self.aggregate_cash_flow
        return {
            "n_deals": self.n_deals,
            "hurdle_rate": self.hurdle_rate,
            "projection_months": self.projection_months,
            "grid_origin": cf.valuation_date.isoformat(),
            "total_pv_profits": self.total_pv_profits,
            "total_irr": self.total_irr,
            "breakeven_year": self.breakeven_year,
            "profit_margin": self.profit_margin,
            "total_undiscounted_profit": self.total_undiscounted_profit,
            "total_face_amount": self.total_face_amount,
            "total_ceded_face": self.total_ceded_face,
            "peak_ceded_nar": self.peak_ceded_nar,
            "aggregate_net_cash_flow": self.aggregate_net_cash_flow.tolist(),
            "aggregate_ceded_nar": self.aggregate_ceded_nar.tolist(),
            "aggregate_cash_flow": {
                "gross_premiums": cf.gross_premiums.tolist(),
                "death_claims": cf.death_claims.tolist(),
                "lapse_surrenders": cf.lapse_surrenders.tolist(),
                "expenses": cf.expenses.tolist(),
                "reserve_balance": cf.reserve_balance.tolist(),
                "reserve_increase": cf.reserve_increase.tolist(),
                "net_cash_flow": cf.net_cash_flow.tolist(),
            },
            "deals": [_deal_result_to_dict(dr) for dr in self.deal_results],
            "concentration": {
                "cedant": dict(self.concentration_by_cedant),
                "product": dict(self.concentration_by_product),
                "treaty": dict(self.concentration_by_treaty),
            },
            "hhi": dict(self.hhi),
            "concentration_by_basis": {
                basis: {dim: dict(shares) for dim, shares in dims.items()}
                for basis, dims in self.concentration_by_basis.items()
            },
            "hhi_by_basis": {basis: dict(dims) for basis, dims in self.hhi_by_basis.items()},
        }


@dataclass(frozen=True)
class PortfolioResultWithCapital(PortfolioResult):
    """``PortfolioResult`` augmented with aggregate LICAT capital metrics.

    Built by :meth:`Portfolio.run_with_capital`. Every ``PortfolioResult``
    field is preserved unchanged (the joint result IS a ``PortfolioResult``
    for any consumer of the base contract). Additional fields:

    - ``initial_capital``: required capital at projection month 0 on the
      aggregate cash flow + aggregate ceded NAR.
    - ``peak_capital``: maximum required capital across the projection.
    - ``pv_capital``: PV of the capital STOCK at the hurdle rate — default
      RoC denominator per ADR-048.
    - ``pv_capital_strain``: PV of the capital STRAIN (period-over-period
      increases) at the hurdle rate.
    - ``return_on_capital``: ``total_pv_profits / pv_capital``. ``None`` when
      ``pv_capital <= 0`` (e.g. zero-factor capital model on a coinsurance-
      only portfolio).
    - ``capital_adjusted_irr``: IRR of ``aggregate_net_cash_flow - strain``
      with terminal release of residual capital at month ``T-1``.
    - ``capital_by_period``: full ``(T,)`` aggregate capital schedule.

    The schedule comes from a single ``CapitalModel.required_capital`` call
    on the aggregate ``CashFlowResult`` with the aggregate ceded NAR.
    Because the calculator's components are linear in ``reserve_balance``
    and ``NAR``, and the aggregate is a per-month sum, this is identical to
    summing per-deal capital schedules when the same factors are applied
    to every deal — see ``test_capital_linearity_matches_sum_of_per_deal_capital``.
    """

    initial_capital: float = 0.0
    peak_capital: float = 0.0
    pv_capital: float = 0.0
    pv_capital_strain: float = 0.0
    return_on_capital: float | None = None
    capital_adjusted_irr: float | None = None
    capital_by_period: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))

    def to_dict(self) -> dict[str, object]:
        """Flatten the joint result into a JSON-serialisable plain dict.

        Returns every key from ``PortfolioResult.to_dict()`` plus a new
        top-level ``capital`` block with the aggregate capital metrics.
        """
        out = super().to_dict()
        out["capital"] = {
            "initial_capital": self.initial_capital,
            "peak_capital": self.peak_capital,
            "pv_capital": self.pv_capital,
            "pv_capital_strain": self.pv_capital_strain,
            "return_on_capital": self.return_on_capital,
            "capital_adjusted_irr": self.capital_adjusted_irr,
            "capital_by_period": self.capital_by_period.tolist(),
        }
        return out


@dataclass(frozen=True)
class PortfolioScenarioResult:
    """Aggregate portfolio results across a list of stress scenarios.

    Produced by :meth:`Portfolio.run_scenarios`. Each entry in
    ``scenarios`` is a ``(name, PortfolioResult)`` pair where ``name`` is
    the originating ``ScenarioAdjustment.name`` and ``PortfolioResult`` is
    the full aggregate result for that scenario — the same shape as
    :meth:`Portfolio.run` returns, just with the scenario's mortality /
    lapse multipliers applied uniformly to every deal in the book
    ("correlated" stress, ADR-064). The list order matches the order in
    which scenarios were supplied so callers can index by position.

    Helpers mirror :class:`~polaris_re.analytics.scenario.ScenarioResult`:
    ``base_case``, ``worst_case``, and ``irr_range`` operate on the
    aggregate portfolio metrics rather than a single-deal profit test.
    """

    scenarios: list[tuple[str, PortfolioResult]] = field(default_factory=list)

    def base_case(self) -> PortfolioResult | None:
        """The ``BASE`` scenario's aggregate result, if present."""
        for name, result in self.scenarios:
            if name == "BASE":
                return result
        return None

    def worst_case(self) -> tuple[str, PortfolioResult] | None:
        """The scenario with the lowest aggregate ``total_irr``.

        Scenarios whose aggregate IRR is ``None`` (suppressed by the
        standard reporting guardrails) are skipped. Returns ``None`` when
        no scenario has a comparable IRR.
        """
        valid: list[tuple[str, PortfolioResult, float]] = [
            (n, r, r.total_irr) for n, r in self.scenarios if r.total_irr is not None
        ]
        if not valid:
            return None
        name, result, _irr = min(valid, key=lambda item: item[2])
        return (name, result)

    def irr_range(self) -> tuple[float | None, float | None]:
        """``(min IRR, max IRR)`` across scenarios with valid aggregate IRRs."""
        irrs = [r.total_irr for _, r in self.scenarios if r.total_irr is not None]
        return (min(irrs), max(irrs)) if irrs else (None, None)

    def to_dict(self) -> dict[str, object]:
        """Flatten the result into a JSON-serialisable plain dict.

        Each scenario block carries the scenario name and the full nested
        ``PortfolioResult.to_dict()`` output, so downstream consumers
        (CLI / API / dashboard) see the same shape they consume from a
        single-portfolio run, plus the scenario label.
        """
        return {
            "scenarios": [
                {"name": name, "result": result.to_dict()} for name, result in self.scenarios
            ],
        }


def _deal_result_to_dict(dr: DealResult) -> dict[str, object]:
    """Flatten a ``DealResult`` into a JSON-serialisable plain dict.

    The nested ``profit_test`` block carries the standard ``ProfitTestResult``
    fields (``pv_profits``, ``irr``, etc.). ``profit_by_year`` is converted
    to a plain list. The ceded NAR vector is converted to a list too.
    """
    return {
        "deal_id": dr.deal_id,
        "cedant": dr.cedant,
        "product_type": dr.product_type,
        "treaty_type": dr.treaty_type,
        "n_policies": dr.n_policies,
        "face_amount": dr.face_amount,
        "ceded_face": dr.ceded_face,
        "valuation_date": dr.valuation_date.isoformat() if dr.valuation_date else None,
        "grid_offset": dr.grid_offset,
        "profit_test": {
            "hurdle_rate": dr.profit_test.hurdle_rate,
            "pv_profits": dr.profit_test.pv_profits,
            "pv_premiums": dr.profit_test.pv_premiums,
            "profit_margin": dr.profit_test.profit_margin,
            "irr": dr.profit_test.irr,
            "breakeven_year": dr.profit_test.breakeven_year,
            "total_undiscounted_profit": dr.profit_test.total_undiscounted_profit,
            "profit_by_year": dr.profit_test.profit_by_year.tolist(),
        },
        "net_cash_flow": dr.net_cash_flow.tolist(),
        "ceded_nar": dr.ceded_nar.tolist(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _id_summary(deal_ids: tuple[str, ...], *, limit: int = 10) -> str:
    """Render a deal-id list for an error message, truncated on large books."""
    if not deal_ids:
        return "no deals"
    shown = ", ".join(repr(deal_id) for deal_id in deal_ids[:limit])
    if len(deal_ids) > limit:
        return f"{shown}, ... ({len(deal_ids)} deals)"
    return shown


def _build_deal(
    *,
    deal_id: str,
    cedant: str,
    inforce: InforceBlock,
    assumptions: AssumptionSet,
    config: ProjectionConfig,
    treaty: BaseTreaty,
) -> Deal:
    """Validate one deal's inputs and build the frozen :class:`Deal`.

    The single validation choke point shared by ``Portfolio.add_deal`` and
    ``Portfolio.replace_deal``, so a replacement can never smuggle in a
    multi-product block or a non-proportional treaty that ``add_deal`` would
    have rejected. Deal-id **uniqueness** is deliberately not checked here:
    it is a portfolio-level invariant that means different things to the two
    callers (``add_deal`` rejects an existing id; ``replace_deal`` requires
    one).

    Raises:
        PolarisValidationError: On a multi-product inforce block, or a
            treaty without a ``cession_pct``.
    """
    product_types = inforce.product_types
    if len(product_types) != 1:
        present = sorted(pt.value for pt in product_types)
        raise PolarisValidationError(
            f"Deal {deal_id!r} inforce block must contain exactly one product type; "
            f"got {present}. Split mixed blocks into one deal per product."
        )

    cession = getattr(treaty, "cession_pct", None)
    if cession is None:
        raise PolarisValidationError(
            f"Deal {deal_id!r}: Portfolio supports proportional treaties only "
            f"(the treaty must expose `cession_pct`); got {type(treaty).__name__}."
        )

    return Deal(
        deal_id=deal_id,
        cedant=cedant,
        inforce=inforce,
        assumptions=assumptions,
        config=config,
        treaty=treaty,
        product_type=next(iter(product_types)).value,
        treaty_type=_treaty_label(treaty),
        cession_pct=float(cession),
    )


def _validate_max_workers(max_workers: int | None) -> None:
    """Reject anything that is not ``None`` or a positive plain ``int``.

    Validated up front, before any deal is projected, so a typo costs nothing.
    ``bool`` is rejected explicitly even though it is an ``int`` subclass:
    ``max_workers=True`` would silently mean "one worker", which is never what
    a caller passing a flag intended.
    """
    if max_workers is None:
        return
    if isinstance(max_workers, bool) or not isinstance(max_workers, int):
        raise PolarisValidationError(
            f"max_workers must be None or a positive int, got {max_workers!r} "
            f"({type(max_workers).__name__})."
        )
    if max_workers < 1:
        raise PolarisValidationError(f"max_workers must be >= 1 when supplied, got {max_workers}.")


def _treaty_label(treaty: BaseTreaty) -> str:
    """Return a clean treaty-type label, e.g. ``YRTTreaty`` -> ``YRT``."""
    name = type(treaty).__name__
    return name[: -len("Treaty")] if name.endswith("Treaty") else name


def _place(arr: np.ndarray, offset: int, length: int) -> np.ndarray:
    """Place a 1-D array onto a zero-filled grid of ``length`` months at ``offset``.

    Generalises a trailing zero-pad to a leading calendar offset:
    ``_place(arr, 0, length)`` is a plain zero-pad (the strict-mode case);
    a positive ``offset`` shifts the array forward on the common grid for
    calendar-aligned aggregation of deals with different inception dates.

    **The fresh allocation is load-bearing, not an implementation detail**
    (ADR-179). Short-circuiting to ``return arr`` when
    ``offset == 0 and len(arr) == length`` is a tempting and otherwise harmless
    micro-optimisation — but with ``cache=True`` the input may be a *cached*
    per-deal array, and any caller-side in-place accumulation on the returned
    value would then write straight into a cache entry. Always allocate.
    """
    out = np.zeros(length, dtype=np.float64)
    out[offset : offset + len(arr)] = arr
    return out


def _concentration(pairs: list[tuple[str, float]]) -> dict[str, float]:
    """Aggregate ``(label, weight)`` pairs into label -> share-of-total.

    Shares sum to 1.0. When the total weight is zero (degenerate — e.g.
    every cession is 0%), each distinct label gets an equal share so the
    dimension is still well-defined.
    """
    grouped: dict[str, float] = {}
    for label, weight in pairs:
        grouped[label] = grouped.get(label, 0.0) + weight
    total = sum(grouped.values())
    if total > 0.0:
        return {label: weight / total for label, weight in grouped.items()}
    n = len(grouped)
    return {label: 1.0 / n for label in grouped} if n else {}


def _herfindahl(shares: dict[str, float]) -> float:
    """Herfindahl-Hirschman index — sum of squared shares."""
    return float(sum(share * share for share in shares.values()))


def _deal_weight(deal_result: DealResult, basis: ConcentrationBasis) -> float:
    """Return the weight a single deal contributes under ``basis`` (ADR-069).

    - ``ceded_face`` is the static face-weighted view used by the flat
      ``concentration_by_*`` fields — exposure as of the projection start.
    - ``ceded_nar_peak`` is the peak ceded NAR across the projection;
      proportional treaties without a NAR vector (coinsurance, modco) report
      zero, matching their on-statement risk exposure.
    - ``pv_premium`` is the reinsurer-view present value of premiums from the
      deal's own profit test, capturing revenue exposure consistently with
      the per-deal hurdle rate.
    """
    if basis == "ceded_face":
        return float(deal_result.ceded_face)
    if basis == "ceded_nar_peak":
        nar = deal_result.ceded_nar
        return float(nar.max()) if nar.size > 0 else 0.0
    if basis == "pv_premium":
        return float(deal_result.profit_test.pv_premiums)
    raise PolarisValidationError(f"Unknown concentration basis: {basis!r}.")


def _transpose_basis_outer[V](
    by_basis: dict[str, dict[str, V]],
) -> dict[str, dict[str, V]]:
    """Swap the outer two keys of a ``{basis: {dimension: V}}`` mapping.

    Returns a fresh ``{dimension: {basis: V}}`` mapping; the inner ``V``
    values are returned by reference, so for nested-dict ``V`` no storage
    is duplicated. Used to produce the dimension-outer view of
    ``concentration_by_basis`` / ``hhi_by_basis`` without holding a
    second copy of the values on ``PortfolioResult`` (ADR-073).
    """
    out: dict[str, dict[str, V]] = {}
    for basis, dims in by_basis.items():
        for dimension, value in dims.items():
            out.setdefault(dimension, {})[basis] = value
    return out


def _concentration_for_basis(
    deal_results: list[DealResult],
    basis: ConcentrationBasis,
) -> dict[str, dict[str, float]]:
    """Compute share-of-total per dimension under one weight basis.

    Returns ``{dimension: {label: share}}`` for the cedant / product / treaty
    dimensions. Delegates to :func:`_concentration`, which handles the
    zero-total degenerate case by assigning equal shares.
    """
    weights = [(dr, _deal_weight(dr, basis)) for dr in deal_results]
    return {
        "cedant": _concentration([(dr.cedant, w) for dr, w in weights]),
        "product": _concentration([(dr.product_type, w) for dr, w in weights]),
        "treaty": _concentration([(dr.treaty_type, w) for dr, w in weights]),
    }


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class Portfolio:
    """Builder + runner for a multi-deal reinsurance portfolio.

    Deals are added via the chainable :meth:`add_deal` builder, then
    :meth:`run` projects every deal, applies its treaty, and aggregates the
    reinsurer-side cash flows into a :class:`PortfolioResult`.

    The book is inspectable and editable after construction (ADR-178):
    :attr:`deal_ids` / :meth:`get_deal` / ``len(portfolio)`` /
    ``deal_id in portfolio`` read it, while :meth:`remove_deal`,
    :meth:`replace_deal`, and :meth:`clear_deals` edit it in place and
    :meth:`without_deal` returns a filtered copy. Every edit is validated by
    the same rules as :meth:`add_deal`, and an unknown deal id always raises
    rather than silently no-opping.

    With ``cache=True`` the per-deal projection behind each run is memoised on
    the instance and reused by later runs at the same hurdle rate (ADR-179) —
    see :attr:`cache_enabled`, :meth:`cache_stats`, and :meth:`clear_cache`.

    A single run can also spread its per-deal projections across threads via
    ``run(..., max_workers=N)`` (ADR-180), forwarded by :meth:`run_with_capital`
    and :meth:`run_scenarios`. The default (``None``) is the serial path, and
    every worker count produces bit-identical numbers. The two features compose:
    the fan-out is one task per deal, so on a cold cache each key is computed
    exactly once and the miss count still equals the number of projections.

    Args:
        name: Identifier for the portfolio, used as the aggregate run id.
        cache: Opt into per-deal result caching. ``False`` (default) projects
            every deal on every run, exactly as before. Results are identical
            either way — the flag only decides whether a projection is
            recomputed or reused.

            The cache is keyed ``(deal_id, hurdle_rate)``, so it rests on one
            invariant: **within this instance, a ``deal_id`` denotes exactly
            one set of projection inputs for as long as its cached entries
            live.** Two thirds of that are enforced, one third is the caller's
            to assert:

            - *Unique at a point in time* — enforced: :meth:`add_deal` rejects
              a duplicate id, :meth:`replace_deal` requires an existing one.
            - *Stable across changes the portfolio can see* — enforced: all
              four mutation verbs evict what they invalidate, so re-using an
              id for different terms via ``remove_deal`` + ``add_deal``, or
              via ``replace_deal``, is safe.
            - *Stable across changes it cannot see* — **asserted by passing
              ``True``**: mutating a deal's ``InforceBlock`` /
              ``AssumptionSet`` / ``ProjectionConfig`` / ``BaseTreaty`` **in
              place** changes what the id means without the portfolio ever
              hearing about it, and the stale entry survives. Go through
              :meth:`replace_deal`, or call :meth:`clear_cache` afterwards.

            Nothing here requires an id to be stable *beyond* this instance:
            the cache is per-``Portfolio``, never shared or persisted, so ids
            need not agree across objects, processes, or CLI invocations.
    """

    def __init__(self, name: str = "portfolio", *, cache: bool = False) -> None:
        self.name = name
        self._deals: list[Deal] = []
        self._cache_enabled = cache
        self._deal_cache: dict[tuple[str, float], tuple[DealResult, CashFlowResult]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        # Guards the cache dict and its two counters, never a projection
        # (ADR-180). Per instance — a ``without_deal`` / ``_with_scenario``
        # copy builds its own, so the two portfolios never contend.
        self._cache_lock = threading.Lock()

    @property
    def n_deals(self) -> int:
        """Number of deals currently in the portfolio."""
        return len(self._deals)

    @property
    def deals(self) -> tuple[Deal, ...]:
        """Immutable view of the deals added so far."""
        return tuple(self._deals)

    def __len__(self) -> int:
        """Number of deals currently in the portfolio (same as :attr:`n_deals`)."""
        return len(self._deals)

    def __contains__(self, deal_id: object) -> bool:
        """``deal_id in portfolio`` — membership by deal id.

        A non-string operand is simply absent (``False``) rather than an
        error, matching the container protocol's convention.
        """
        return any(deal.deal_id == deal_id for deal in self._deals)

    @property
    def deal_ids(self) -> tuple[str, ...]:
        """Deal ids in insertion order — the order of the per-deal breakdown."""
        return tuple(deal.deal_id for deal in self._deals)

    @property
    def cache_enabled(self) -> bool:
        """Whether per-deal result caching is on (set at construction, ADR-179)."""
        return self._cache_enabled

    def cache_stats(self) -> CacheStats:
        """Return a :class:`CacheStats` snapshot of the per-deal result cache.

        The observability surface for the cache: a caller confirms it is
        working by watching ``hits`` rise while ``size`` stays flat, with no
        recourse to wall-clock timing.
        """
        with self._cache_lock:
            return CacheStats(
                enabled=self._cache_enabled,
                hits=self._cache_hits,
                misses=self._cache_misses,
                size=len(self._deal_cache),
            )

    def clear_cache(self) -> "Portfolio":
        """Drop every cached per-deal result, in place.

        The escape hatch for the two stalenesses the portfolio cannot detect,
        which are symmetric — mutated **inputs** and mutated **outputs**:

        - a caller who mutated a deal's ``InforceBlock`` / ``AssumptionSet`` /
          ``ProjectionConfig`` / treaty **in place** rather than going through
          :meth:`replace_deal`; or
        - a caller who wrote into an array handed back by a previous
          :meth:`run` — cached results are live, not copies (see
          :meth:`_run_deal`). This is the likelier of the two to happen by
          accident, since post-processing ``deal_results`` needs no private
          attribute.

        Lifetime ``hits`` / ``misses`` counters are
        deliberately not rewound (see :class:`CacheStats`). A no-op on a
        portfolio built without ``cache=True``.

        Returns:
            ``self``, to allow chained calls.
        """
        with self._cache_lock:
            self._deal_cache.clear()
        return self

    def _evict_deal(self, deal_id: str) -> None:
        """Drop every cached entry belonging to ``deal_id`` (all hurdle rates).

        Eviction is per deal, not portfolio-wide, because ``_run_deal``'s
        result depends only on the deal itself and the hurdle rate — adding or
        dropping a *different* deal cannot change it (the aggregation, which
        does depend on the whole book, is recomputed on every run). That is
        what keeps an incrementally built book from re-projecting everything
        on each ``add_deal``.
        """
        with self._cache_lock:
            for key in [key for key in self._deal_cache if key[0] == deal_id]:
                del self._deal_cache[key]

    def get_deal(self, deal_id: str) -> Deal:
        """Return the validated :class:`Deal` registered under ``deal_id``.

        Args:
            deal_id: Identifier supplied to :meth:`add_deal`.

        Returns:
            The frozen :class:`Deal`, including the metadata cached at
            construction time (``product_type``, ``treaty_type``,
            ``cession_pct``).

        Raises:
            PolarisValidationError: If no deal carries that id.
        """
        return self._deals[self._index_of(deal_id)]

    def add_deal(
        self,
        *,
        deal_id: str,
        cedant: str,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
        treaty: BaseTreaty,
    ) -> "Portfolio":
        """Add one reinsurance deal to the portfolio.

        Args:
            deal_id: Unique identifier for the deal within the portfolio.
            cedant: Ceding company name — the concentration grouping key.
            inforce: Single-product inforce block being reinsured.
            assumptions: Assumption set for the projection.
            config: Projection config (horizon, discount rate, expenses).
            treaty: Proportional treaty exposing a ``cession_pct``.

        Returns:
            ``self``, to allow chained ``add_deal(...).add_deal(...)`` calls.

        Raises:
            PolarisValidationError: On a duplicate ``deal_id``, a
                multi-product inforce block, or a treaty without a
                ``cession_pct`` (non-proportional structures are out of
                scope for this slice).
        """
        if deal_id in self:
            raise PolarisValidationError(
                f"Duplicate deal_id {deal_id!r} — deal ids must be unique within a portfolio."
            )
        deal = _build_deal(
            deal_id=deal_id,
            cedant=cedant,
            inforce=inforce,
            assumptions=assumptions,
            config=config,
            treaty=treaty,
        )
        # Built before the mutation, so a validation failure leaves both the
        # book and the cache untouched. The eviction is belt-and-braces: the
        # duplicate check above means no live entry can carry this id, but it
        # holds the invariant "a cached entry always describes a deal the book
        # currently holds" without depending on that reasoning (ADR-179).
        self._evict_deal(deal_id)
        self._deals.append(deal)
        return self

    def remove_deal(self, deal_id: str) -> "Portfolio":
        """Remove one deal from the portfolio, in place.

        The surviving deals keep their relative order, so the per-deal
        breakdown and the calendar grid offsets of the remaining deals are
        unchanged. An unknown id is an error, never a silent no-op — in a
        what-if flow a silently ignored removal produces a wrong answer that
        looks right.

        Args:
            deal_id: Identifier of the deal to drop.

        Returns:
            ``self``, to allow chained calls.

        Raises:
            PolarisValidationError: If no deal carries that id.
        """
        del self._deals[self._index_of(deal_id)]
        self._evict_deal(deal_id)
        return self

    def replace_deal(
        self,
        *,
        deal_id: str,
        cedant: str,
        inforce: InforceBlock,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
        treaty: BaseTreaty,
    ) -> "Portfolio":
        """Replace the deal registered under ``deal_id``, in place.

        The replacement is validated exactly as :meth:`add_deal` validates a
        new deal (single-product block, proportional treaty) and keeps the
        original's **position**, so re-quoting one deal does not reorder the
        per-deal breakdown. This is the "same deal, different terms" verb:
        re-price DEAL_B at a different cession, or under a revised inforce
        extract, without rebuilding the portfolio.

        Args:
            deal_id: Identifier of the deal being replaced; the replacement
                keeps this id.
            cedant: Ceding company name for the replacement.
            inforce: Single-product inforce block for the replacement.
            assumptions: Assumption set for the replacement.
            config: Projection config for the replacement.
            treaty: Proportional treaty exposing a ``cession_pct``.

        Returns:
            ``self``, to allow chained calls.

        Raises:
            PolarisValidationError: If no deal carries that id, or if the
                replacement fails the :meth:`add_deal` validation rules.
        """
        index = self._index_of(deal_id)
        # Build (and validate) before mutating anything, so a rejected
        # replacement leaves both the deal and its cached result in place.
        deal = _build_deal(
            deal_id=deal_id,
            cedant=cedant,
            inforce=inforce,
            assumptions=assumptions,
            config=config,
            treaty=treaty,
        )
        self._deals[index] = deal
        self._evict_deal(deal_id)
        return self

    def clear_deals(self) -> "Portfolio":
        """Drop every deal, in place, leaving an empty portfolio.

        Returns:
            ``self``, to allow chained ``clear_deals().add_deal(...)`` calls.
        """
        self._deals.clear()
        with self._cache_lock:
            self._deal_cache.clear()
        return self

    def without_deal(self, *deal_ids: str, name: str | None = None) -> "Portfolio":
        """Return a **new** portfolio holding every deal except the named ones.

        The what-if primitive — "what does the book look like without
        DEAL_C?" The receiver is not mutated; the copy shares the same
        :class:`Deal` objects (which are frozen), so no projection input is
        duplicated. Mirrors the copy-don't-mutate pattern
        :meth:`run_scenarios` already uses internally.

        Args:
            *deal_ids: One or more ids to exclude. Every id must be present,
                and each must be named exactly once.
            name: Name for the returned portfolio. Defaults to the
                receiver's name; pass a distinct name when both results are
                reported side by side, since the name drives the aggregate
                ``run_id``.

        Returns:
            A new :class:`Portfolio` with the remaining deals in their
            original order. Excluding every deal yields an empty portfolio
            (legal to build; :meth:`run` rejects it).

        Raises:
            PolarisValidationError: If no ids are supplied, if an id is
                repeated, or if any id is not present in the portfolio.
        """
        if not deal_ids:
            raise PolarisValidationError(
                "without_deal requires at least one deal_id to exclude; got none."
            )

        excluded: set[str] = set()
        repeated: list[str] = []
        for deal_id in deal_ids:
            if deal_id in excluded:
                repeated.append(deal_id)
            excluded.add(deal_id)
        # A repeated id is well-defined (the deal is excluded either way) but
        # it means the caller's id list is not what they think it is — the
        # same class of mistake as a typo, so it is rejected on the same
        # principle rather than absorbed silently.
        if repeated:
            raise PolarisValidationError(
                f"without_deal received repeated deal_id(s) {_id_summary(tuple(repeated))} — "
                f"name each deal to exclude exactly once."
            )

        # Validate every id up front so a typo fails loudly rather than
        # silently returning a partially filtered portfolio.
        for deal_id in deal_ids:
            self._index_of(deal_id)

        copy = Portfolio(name=self.name if name is None else name, cache=self._cache_enabled)
        copy._deals.extend(deal for deal in self._deals if deal.deal_id not in excluded)
        # Carry over the surviving deals' cached results (ADR-179). This is
        # sound because the copy holds the *same frozen* Deal objects under the
        # same ids, so a cached (deal_id, hurdle_rate) entry describes exactly
        # the projection the copy would perform — and it is what makes the
        # leave-one-out loop over a whole book cost one projection per deal
        # instead of one per deal per iteration. The dict is fresh — never the
        # parent's by reference — so membership and eviction diverge from here.
        # The cached *values* do not: parent and copy hand out the same ndarray
        # objects for every surviving deal, so a caller writing into an array
        # obtained from either one changes what the other's next run()
        # aggregates. See `_run_deal` — this is that same by-reference contract
        # reached by a second path, and the leave-one-out sweep is exactly where
        # a caller holds N result objects at once and is most likely to
        # post-process them.
        if self._cache_enabled:
            survivors = {deal.deal_id for deal in copy._deals}
            with self._cache_lock:
                carried = {
                    key: value for key, value in self._deal_cache.items() if key[0] in survivors
                }
            copy._deal_cache.update(carried)
        return copy

    def _index_of(self, deal_id: str) -> int:
        """Return the position of ``deal_id``, or raise if it is not present."""
        for index, deal in enumerate(self._deals):
            if deal.deal_id == deal_id:
                return index
        raise PolarisValidationError(
            f"Unknown deal_id {deal_id!r} — portfolio {self.name!r} holds "
            f"{_id_summary(self.deal_ids)}."
        )

    def run(
        self,
        hurdle_rate: float,
        *,
        align: AlignMode = "strict",
        max_workers: int | None = None,
    ) -> PortfolioResult:
        """Project and aggregate every deal in the portfolio.

        Args:
            hurdle_rate: Annual hurdle rate applied uniformly to every deal
                and to the aggregate profit test (e.g. 0.10 for 10%).
            align: Time-alignment mode (ADR-061). ``"strict"`` (default) sums
                cash flows by month index and requires every deal to share a
                valuation date. ``"calendar"`` places each deal on a common
                monthly grid keyed off the earliest valuation date, so deals
                with different inception dates aggregate correctly — at the
                cost that ``total_pv_profits`` (the portfolio NPV as of the
                common origin) no longer equals the naive sum of per-deal PVs.
            max_workers: Thread-pool width for the per-deal projections
                (ADR-180). ``None`` (default) and ``1`` run the deals serially
                on the calling thread, exactly as before; ``N > 1`` fans them
                out over at most ``min(N, n_deals)`` threads. **Results are
                bit-identical at any worker count** — the deals are independent
                until the aggregation, which is fed in deal order regardless.

                **Two rules, both measured** (ADR-180, on a 4-core Linux
                container and an Apple Silicon MacBook Air; regenerate for your
                own hardware with ``scripts/bench_portfolio_parallel.py``):

                1. **Match the worker count to *performance* cores, not total
                   cores.** Measured on a 10-core Air (4 performance + 6
                   efficiency), a 16-deal x 20k-policy book ran **1.77x at 4
                   workers** — the P-core count — but only 1.35x at 8 and 1.23x
                   at 16, with ample work available. The 6 efficiency cores
                   contributed nothing; passing ``hw.ncpu`` (10) there would
                   give back roughly a third of the gain. Find yours with
                   ``sysctl -n hw.perflevel0.logicalcpu`` on macOS.
                2. **Only on books whose per-deal blocks are large.** With small
                   deals the fan-out goes *negative*: 8 deals x 5k policies
                   peaked at 2 workers (1.30x) and dropped to 0.94x at 4 and
                   0.70x at 8 on the Air — and to 0.59x / 0.48x on the 4-core
                   container.

                The ceiling is ~1.8x because a per-deal projection is only
                partly GIL-free: the engines' month-by-month reserve and
                in-force recursions are Python loops around comparatively small
                per-step NumPy calls, so threads overlap the array work but
                contend on everything between the steps. Larger blocks lengthen
                each C section per GIL handoff, which is exactly why block size
                decides the sign. The default is serial because no worker count
                is right for every book.

        Returns:
            A :class:`PortfolioResult` with aggregate cash flows, total
            profitability metrics, the per-deal breakdown, and concentration
            metrics. ``aggregate_cash_flow.valuation_date`` is the grid origin
            (the earliest deal valuation date under ``"calendar"``).

        Raises:
            PolarisValidationError: If the portfolio is empty, ``hurdle_rate``
                is not greater than -1, ``max_workers`` is neither ``None`` nor
                a positive plain ``int``, ``align`` is not a recognised mode,
                the deals do not share a valuation date under ``"strict"``, or
                their valuation dates fall on different days-of-month under
                ``"calendar"``.
        """
        if not self._deals:
            raise PolarisValidationError("Cannot run an empty portfolio — add at least one deal.")
        if hurdle_rate <= -1.0:
            raise PolarisValidationError(f"hurdle_rate must be > -1, got {hurdle_rate}.")
        _validate_max_workers(max_workers)

        origin, offsets = self._grid_offsets(align)

        projected = self._project_all(hurdle_rate, max_workers)

        deal_results: list[DealResult] = []
        reinsurer_views: list[CashFlowResult] = []
        for (deal_result, reinsurer_view), offset in zip(projected, offsets, strict=True):
            # ``replace`` stamps the grid offset onto a *copy*, so a cached
            # result is never mutated by the run that reads it (ADR-179).
            deal_results.append(dataclasses.replace(deal_result, grid_offset=offset))
            reinsurer_views.append(reinsurer_view)

        t_max = max(
            offset + view.projection_months
            for offset, view in zip(offsets, reinsurer_views, strict=True)
        )

        aggregate_arrays = {
            field_name: np.sum(
                [
                    _place(getattr(view, field_name), offset, t_max)
                    for offset, view in zip(offsets, reinsurer_views, strict=True)
                ],
                axis=0,
            )
            for field_name in (
                "gross_premiums",
                "death_claims",
                "lapse_surrenders",
                "expenses",
                "reserve_balance",
                "reserve_increase",
                "net_cash_flow",
            )
        }
        aggregate_nar = np.sum(
            [
                _place(deal_result.ceded_nar, offset, t_max)
                for offset, deal_result in zip(offsets, deal_results, strict=True)
            ],
            axis=0,
        )

        aggregate_cf = CashFlowResult(
            run_id=f"portfolio-{self.name}",
            valuation_date=origin,
            basis="NET",
            assumption_set_version="portfolio-aggregate",
            product_type="PORTFOLIO",
            block_id=self.name,
            projection_months=t_max,
            **aggregate_arrays,
        )
        aggregate_test = ProfitTester(aggregate_cf, hurdle_rate).run()

        total_face = sum(deal_result.face_amount for deal_result in deal_results)
        total_ceded_face = sum(deal_result.ceded_face for deal_result in deal_results)

        # Weighted concentration variants — face / NAR-peak / PV-premium.
        # The ``ceded_face`` basis IS the flat concentration view (ADR-069).
        concentration_by_basis: dict[str, dict[str, dict[str, float]]] = {
            basis: _concentration_for_basis(deal_results, basis) for basis in CONCENTRATION_BASES
        }
        hhi_by_basis: dict[str, dict[str, float]] = {
            basis: {dim: _herfindahl(shares) for dim, shares in dims.items()}
            for basis, dims in concentration_by_basis.items()
        }
        concentration_by_cedant = concentration_by_basis["ceded_face"]["cedant"]
        concentration_by_product = concentration_by_basis["ceded_face"]["product"]
        concentration_by_treaty = concentration_by_basis["ceded_face"]["treaty"]

        return PortfolioResult(
            n_deals=len(deal_results),
            hurdle_rate=hurdle_rate,
            projection_months=t_max,
            aggregate_cash_flow=aggregate_cf,
            aggregate_net_cash_flow=aggregate_arrays["net_cash_flow"],
            aggregate_ceded_nar=aggregate_nar,
            total_pv_profits=aggregate_test.pv_profits,
            total_irr=aggregate_test.irr,
            breakeven_year=aggregate_test.breakeven_year,
            profit_margin=aggregate_test.profit_margin,
            total_undiscounted_profit=aggregate_test.total_undiscounted_profit,
            total_face_amount=total_face,
            total_ceded_face=total_ceded_face,
            peak_ceded_nar=float(aggregate_nar.max()) if t_max > 0 else 0.0,
            deal_results=deal_results,
            concentration_by_cedant=concentration_by_cedant,
            concentration_by_product=concentration_by_product,
            concentration_by_treaty=concentration_by_treaty,
            hhi=hhi_by_basis["ceded_face"],
            concentration_by_basis=concentration_by_basis,
            hhi_by_basis=hhi_by_basis,
        )

    def run_with_capital(
        self,
        hurdle_rate: float,
        capital_model: CapitalModel,
        *,
        align: AlignMode = "strict",
        max_workers: int | None = None,
    ) -> PortfolioResultWithCapital:
        """Project, aggregate, and roll a single capital call onto the
        portfolio.

        Wraps :meth:`run` and joins the aggregate ``CashFlowResult`` and
        aggregate ceded NAR with a single ``CapitalModel.required_capital``
        call. Accepts any ``CapitalModel`` — Canadian ``LICATCapital``, US
        ``RBCCapital``, or (Slice 3) ``SolvencyIICapital`` — since the body
        uses only the ``CapitalSchedule`` surface (ADR-099). The result carries
        every ``PortfolioResult`` field plus portfolio-level capital metrics and
        return-on-capital — see :class:`PortfolioResultWithCapital`.

        Args:
            hurdle_rate: Annual hurdle rate applied uniformly to every deal,
                the aggregate profit test, and the PV-capital denominator.
            capital_model: An instantiated ``CapitalModel`` (e.g. built via
                ``LICATCapital.for_product(product_type)`` or
                ``RBCCapital.for_product(product_type)``). The same factor
                set is applied to the entire portfolio — for a heterogeneous
                book, supply a model whose factors reflect the blended
                exposure.
            align: Time-alignment mode forwarded to :meth:`run` (ADR-061).
            max_workers: Per-deal projection thread-pool width, forwarded to
                :meth:`run` (ADR-180). The single capital call is portfolio-level
                and unaffected; results are bit-identical at any worker count.

        Returns:
            A :class:`PortfolioResultWithCapital` with aggregate cash flows,
            profitability metrics, per-deal breakdown, concentration metrics,
            and aggregate capital metrics.

        Raises:
            PolarisValidationError: Conditions identical to :meth:`run`
                (empty portfolio, invalid hurdle rate, invalid ``align`` mode,
                invalid ``max_workers``, mismatched valuation dates).
        """
        base = self.run(hurdle_rate, align=align, max_workers=max_workers)

        # Single LICAT call at the portfolio level. The aggregate
        # CashFlowResult carries reserve_balance (C-1 / C-3 inputs); the
        # aggregate ceded NAR is the C-2 input. With linear factor models,
        # this equals the month-by-month sum of per-deal capital schedules
        # (see test_capital_linearity_matches_sum_of_per_deal_capital).
        capital = capital_model.required_capital(
            base.aggregate_cash_flow, nar=base.aggregate_ceded_nar
        )

        pv_capital = capital.pv_capital(hurdle_rate)
        pv_capital_strain = capital.pv_capital_strain(hurdle_rate)

        # RoC denominator is pv_capital (stock) per ADR-048. Suppress when
        # the stock is non-positive — the ratio is not meaningful for
        # zero-factor models or coinsurance-only books with no NAR.
        return_on_capital: float | None = (
            base.total_pv_profits / pv_capital if pv_capital > 0.0 else None
        )

        # Capital-adjusted IRR: IRR of distributable cash flow,
        # net_cash_flow_t - strain_t with a terminal release of residual
        # capital at month T-1. Mirrors ProfitTester.run_with_capital so
        # the two metrics are comparable at the deal and portfolio levels.
        ncf = base.aggregate_net_cash_flow
        strain = capital.capital_strain()
        n = len(ncf)
        if n == 0 or len(strain) != n:
            distributable = ncf.copy()
        else:
            distributable = ncf - strain
            distributable[-1] += float(capital.capital_by_period[-1])

        capital_adjusted_irr: float | None = None
        if n > 0:
            # Reuse the deal-level IRR solver to keep the suppression rules
            # consistent with the standalone profit test (ADR-041).
            capital_adjusted_irr = ProfitTester(base.aggregate_cash_flow, hurdle_rate)._solve_irr(
                distributable
            )

        # Shallow-copy every base PortfolioResult field by name so this
        # constructor does not need a parallel update if PortfolioResult
        # gains a field. A shallow `fields()` splat (not `dataclasses.asdict`,
        # which would recurse into the nested CashFlowResult / DealResult
        # dataclasses and numpy arrays and convert them to dicts) preserves
        # the nested types and references.
        base_fields = {f.name: getattr(base, f.name) for f in dataclasses.fields(base)}
        return PortfolioResultWithCapital(
            **base_fields,
            initial_capital=capital.initial_capital,
            peak_capital=capital.peak_capital,
            pv_capital=pv_capital,
            pv_capital_strain=pv_capital_strain,
            return_on_capital=return_on_capital,
            capital_adjusted_irr=capital_adjusted_irr,
            capital_by_period=capital.capital_by_period.copy(),
        )

    def run_scenarios(
        self,
        hurdle_rate: float,
        scenarios: list[ScenarioAdjustment] | None = None,
        *,
        align: AlignMode = "strict",
        max_workers: int | None = None,
    ) -> PortfolioScenarioResult:
        """Project the portfolio under each scenario and return the
        aggregate result per scenario (ADR-064).

        Each scenario's multiplicative mortality and lapse adjustments are
        applied uniformly to every deal — i.e. the same shock is assumed
        across every cedant simultaneously ("correlated" stress). The
        treaty, projection config, inforce block, and ``cession_pct`` of
        each deal are unchanged. For every scenario the portfolio is
        re-projected end-to-end and the same aggregation that
        :meth:`run` performs is applied, so each entry of the returned
        :class:`PortfolioScenarioResult` is a full :class:`PortfolioResult`
        with concentration metrics, per-deal breakdown, and the aggregate
        ``CashFlowResult``.

        Args:
            hurdle_rate: Annual hurdle rate applied uniformly to every
                scenario's aggregate profit test (matches the
                :meth:`run` convention).
            scenarios: Scenarios to run. ``None`` (default) runs
                ``ScenarioRunner.standard_stress_scenarios()`` — BASE plus
                five standard mortality / lapse stresses.
            align: Time-alignment mode forwarded to :meth:`run` for every
                scenario (ADR-061). ``"strict"`` (default) requires a shared
                valuation date across deals; ``"calendar"`` aligns deals on
                a common monthly grid.
            max_workers: Per-deal projection thread-pool width, forwarded to
                each scenario's :meth:`run` (ADR-180). The **scenarios**
                themselves stay sequential: parallelising them too would
                multiply peak memory by the scenario count and nest pools, and
                each scenario portfolio holds its own deals, so the fan-out
                stays one task per deal. Results are bit-identical at any
                worker count.

        Returns:
            A :class:`PortfolioScenarioResult` with one entry per scenario
            in the order they were supplied (default-order matches
            ``standard_stress_scenarios()``).

        Raises:
            PolarisValidationError: If the portfolio is empty,
                ``hurdle_rate`` is not greater than -1, ``align`` is not a
                recognised mode, ``max_workers`` is invalid (every :meth:`run`
                failure mode applies), or ``scenarios`` is an empty list (the
                empty case is rejected up front rather than silently returning
                an empty result).
        """
        from polaris_re.analytics.scenario import ScenarioRunner

        _validate_max_workers(max_workers)
        if scenarios is None:
            scenarios = ScenarioRunner.standard_stress_scenarios()
        if not scenarios:
            raise PolarisValidationError(
                "Portfolio.run_scenarios: scenarios list is empty. "
                "Pass at least one ScenarioAdjustment, or pass scenarios=None "
                "for the standard stress set."
            )

        results: list[tuple[str, PortfolioResult]] = []
        for scenario in scenarios:
            scenario_portfolio = self._with_scenario(scenario)
            scenario_result = scenario_portfolio.run(
                hurdle_rate, align=align, max_workers=max_workers
            )
            results.append((scenario.name, scenario_result))

        return PortfolioScenarioResult(scenarios=results)

    def _with_scenario(self, scenario: ScenarioAdjustment) -> "Portfolio":
        """Return a new ``Portfolio`` with every deal's assumptions
        adjusted by ``scenario`` and every other field copied through.

        ``Deal`` is frozen, so the scenario is applied by building a fresh
        ``Portfolio`` whose deals share the original inforce blocks,
        treaties, configs, and ``cession_pct`` but carry a scaled
        :class:`AssumptionSet`. The original portfolio is not mutated.
        """
        # The cache setting carries over but the entries deliberately do NOT
        # (ADR-179): a stressed deal keeps its deal_id while carrying scaled
        # assumptions, so the parent's entries would silently mask the stress
        # — the one case where the (deal_id, hurdle_rate) key would collide
        # with a genuinely different projection.
        scenario_portfolio = Portfolio(
            name=f"{self.name}_{scenario.name}", cache=self._cache_enabled
        )
        for deal in self._deals:
            scenario_portfolio._deals.append(
                dataclasses.replace(
                    deal,
                    assumptions=apply_scenario_to_assumptions(deal.assumptions, scenario),
                )
            )
        return scenario_portfolio

    # ------------------------------------------------------------------
    # Internal — calendar grid alignment
    # ------------------------------------------------------------------

    def _grid_offsets(self, align: AlignMode) -> tuple[date, list[int]]:
        """Resolve the common grid origin and each deal's month offset onto it.

        ``"strict"`` requires a shared valuation date (offsets are all zero).
        ``"calendar"`` keys the grid off the earliest valuation date and
        returns each deal's whole-month offset from it; it requires a common
        day-of-month so the monthly grids line up exactly. The returned
        offsets are aligned with ``self._deals`` order.
        """
        valuation_dates = [deal.config.valuation_date for deal in self._deals]
        distinct = set(valuation_dates)

        if align == "strict":
            # Aggregation sums cash flows by month index, so month 0 must be
            # the same calendar month for every deal. Reject mixed valuation
            # dates rather than silently producing an out-of-phase aggregate.
            if len(distinct) > 1:
                raise PolarisValidationError(
                    "All deals in a portfolio must share the same valuation date when "
                    "align='strict' — aggregation sums cash flows by month index, which "
                    "is only actuarially valid on a common calendar grid. Pass "
                    "align='calendar' to aggregate deals with different inception dates. "
                    f"Got: {sorted(d.isoformat() for d in distinct)}."
                )
            return valuation_dates[0], [0] * len(valuation_dates)

        if align == "calendar":
            if len({d.day for d in distinct}) > 1:
                raise PolarisValidationError(
                    "Calendar-aligned aggregation requires every deal's valuation date "
                    "to fall on the same day-of-month so the monthly grids line up; got "
                    f"days {sorted({d.day for d in distinct})}. Align inception dates to a "
                    "common day-of-month (typically the first) before aggregating."
                )
            origin = min(valuation_dates)
            return origin, [months_between(origin, d) for d in valuation_dates]

        raise PolarisValidationError(f"align must be 'strict' or 'calendar', got {align!r}.")

    # ------------------------------------------------------------------
    # Internal — single-deal projection
    # ------------------------------------------------------------------

    def _run_deal(self, deal: Deal, hurdle_rate: float) -> tuple[DealResult, CashFlowResult]:
        """Return one deal's reinsurer-side result + cash flow, cached if enabled.

        Memoised on ``(deal_id, hurdle_rate)`` when the portfolio was built
        with ``cache=True`` (ADR-179). ``align`` is deliberately **not** part
        of the key: the returned ``DealResult`` always carries
        ``grid_offset=0`` and :meth:`run` stamps the real offset onto a
        ``dataclasses.replace`` copy, so one entry serves both alignment modes
        and the cached value is never mutated by a run.

        Cached results are returned **live and writeable**, not copied: two
        runs of a caching portfolio — and a portfolio and its
        :meth:`without_deal` copy — hand out ``DealResult``s backed by the
        *same* numpy arrays. Every consumer inside this module treats them as
        read-only (the aggregation allocates via ``_place`` / ``np.sum`` and
        never writes through), but **the caller is outside that guarantee**:
        writing into an array obtained from a previous ``run()`` corrupts every
        later run of the portfolio, silently, because the aggregation re-reads
        the mutated buffer. Uncached, the same mistake damages only the one
        result object, since the next run re-projects; caching widens the blast
        radius from one result to all subsequent runs. Treat anything a run
        hands back as read-only, prefer out-of-place operations
        (``ncf * 2`` over ``ncf *= 2``), and call :meth:`clear_cache` to
        recover if it happens. Handing out copies instead was rejected on cost
        grounds — see ADR-179 alternative (f).
        """
        if not self._cache_enabled:
            return self._project_deal(deal, hurdle_rate)

        key = (deal.deal_id, hurdle_rate)
        # The lock covers the lookup, the counters, and the write-back — never
        # the projection (ADR-180). ``+=`` on an int attribute is a
        # read-modify-write across several bytecodes, so once :meth:`run` can
        # call this from a thread pool the counters need real mutual exclusion
        # to stay exact; a lock held across ``_project_deal`` would instead
        # serialise the very work the fan-out exists to overlap. The cost of
        # not holding it there is that two threads missing on the *same* key
        # would both project — unreachable under the one-task-per-deal fan-out
        # this class performs, and harmless if some future caller creates it
        # (the values are equal; only the miss count overstates the work).
        with self._cache_lock:
            cached = self._deal_cache.get(key)
            if cached is not None:
                self._cache_hits += 1
                return cached
            self._cache_misses += 1

        computed = self._project_deal(deal, hurdle_rate)
        with self._cache_lock:
            self._deal_cache[key] = computed
        return computed

    def _project_all(
        self, hurdle_rate: float, max_workers: int | None
    ) -> list[tuple[DealResult, CashFlowResult]]:
        """Project every deal, serially or across a thread pool, in deal order.

        Returns one ``(DealResult, CashFlowResult)`` pair per deal, positionally
        aligned with ``self._deals``. The parallel path fans out **one task per
        deal** and collects by input position (``Executor.map``), never by
        completion order, so the order-sensitive aggregation sum downstream is
        bit-identical to the serial path. One task per deal is also what keeps
        each cache key touched exactly once, so no single-flight guard is
        needed (ADR-179 / ADR-180).

        Threads rather than processes: the payload is NumPy-heavy and the large
        ``(N x T)`` ufuncs release the GIL, whereas a process pool would have to
        pickle every ``InforceBlock`` / ``MortalityTable`` per deal.

        The serial path is taken whenever it is the equivalent-or-better choice
        — ``max_workers is None`` (the default), one requested worker, or fewer
        than two deals — so those callers never pay for a pool.
        """
        if max_workers is None or max_workers == 1 or len(self._deals) < 2:
            return [self._run_deal(deal, hurdle_rate) for deal in self._deals]

        workers = min(max_workers, len(self._deals))
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix=f"polaris-portfolio-{self.name}"
        ) as pool:
            # ``map`` yields in input order and re-raises the first task's
            # exception on iteration; ``list`` forces both inside the pool's
            # context so a failing deal surfaces rather than yielding a
            # silently partial book.
            return list(pool.map(lambda deal: self._run_deal(deal, hurdle_rate), self._deals))

    def _project_deal(self, deal: Deal, hurdle_rate: float) -> tuple[DealResult, CashFlowResult]:
        """Project one deal and return its reinsurer-side result + cash flow."""
        engine = get_product_engine(
            inforce=deal.inforce,
            assumptions=deal.assumptions,
            config=deal.config,
        )
        gross = engine.project()
        _net, ceded = deal.treaty.apply(gross)

        # The reinsurer's position is the ceded cash flow, re-labelled NET so
        # ProfitTester accepts it (CEDED basis is rejected by design).
        reinsurer_view = ceded_to_reinsurer_view(ceded)
        profit_test = ProfitTester(reinsurer_view, hurdle_rate).run()

        face = deal.inforce.total_face_amount()
        ceded_face = face * deal.cession_pct

        if ceded.nar is None:
            ceded_nar = np.zeros(ceded.projection_months, dtype=np.float64)
        else:
            ceded_nar = np.asarray(ceded.nar, dtype=np.float64)

        deal_result = DealResult(
            deal_id=deal.deal_id,
            cedant=deal.cedant,
            product_type=deal.product_type,
            treaty_type=deal.treaty_type,
            n_policies=deal.inforce.n_policies,
            face_amount=face,
            ceded_face=ceded_face,
            profit_test=profit_test,
            net_cash_flow=np.asarray(reinsurer_view.net_cash_flow, dtype=np.float64),
            ceded_nar=ceded_nar,
            valuation_date=deal.config.valuation_date,
            grid_offset=0,
        )
        return deal_result, reinsurer_view

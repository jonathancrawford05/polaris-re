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
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np

from polaris_re.analytics.capital import LICATCapital
from polaris_re.analytics.profit_test import ProfitTester, ProfitTestResult
from polaris_re.analytics.scenario import ScenarioAdjustment, apply_scenario_to_assumptions
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import ceded_to_reinsurer_view
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty
from polaris_re.utils.date_utils import months_between

type AlignMode = Literal["strict", "calendar"]

__all__ = [
    "AlignMode",
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

    Constructed and validated by ``Portfolio.add_deal`` — callers do not
    instantiate this directly. ``product_type``, ``treaty_type``, and
    ``cession_pct`` are cached at construction time (the latter validated
    non-``None`` by ``add_deal``) for the per-deal breakdown and
    concentration metrics.
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

    The schedule comes from a single ``LICATCapital.required_capital`` call
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
        valid = [(n, r) for n, r in self.scenarios if r.total_irr is not None]
        if not valid:
            return None
        return min(valid, key=lambda item: item[1].total_irr)  # type: ignore[arg-type, return-value]

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


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class Portfolio:
    """Builder + runner for a multi-deal reinsurance portfolio.

    Deals are added via the chainable :meth:`add_deal` builder, then
    :meth:`run` projects every deal, applies its treaty, and aggregates the
    reinsurer-side cash flows into a :class:`PortfolioResult`.

    Args:
        name: Identifier for the portfolio, used as the aggregate run id.
    """

    def __init__(self, name: str = "portfolio") -> None:
        self.name = name
        self._deals: list[Deal] = []

    @property
    def n_deals(self) -> int:
        """Number of deals currently in the portfolio."""
        return len(self._deals)

    @property
    def deals(self) -> tuple[Deal, ...]:
        """Immutable view of the deals added so far."""
        return tuple(self._deals)

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
        if any(deal.deal_id == deal_id for deal in self._deals):
            raise PolarisValidationError(
                f"Duplicate deal_id {deal_id!r} — deal ids must be unique within a portfolio."
            )

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

        self._deals.append(
            Deal(
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
        )
        return self

    def run(self, hurdle_rate: float, *, align: AlignMode = "strict") -> PortfolioResult:
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

        Returns:
            A :class:`PortfolioResult` with aggregate cash flows, total
            profitability metrics, the per-deal breakdown, and concentration
            metrics. ``aggregate_cash_flow.valuation_date`` is the grid origin
            (the earliest deal valuation date under ``"calendar"``).

        Raises:
            PolarisValidationError: If the portfolio is empty, ``hurdle_rate``
                is not greater than -1, ``align`` is not a recognised mode,
                the deals do not share a valuation date under ``"strict"``, or
                their valuation dates fall on different days-of-month under
                ``"calendar"``.
        """
        if not self._deals:
            raise PolarisValidationError("Cannot run an empty portfolio — add at least one deal.")
        if hurdle_rate <= -1.0:
            raise PolarisValidationError(f"hurdle_rate must be > -1, got {hurdle_rate}.")

        origin, offsets = self._grid_offsets(align)

        deal_results: list[DealResult] = []
        reinsurer_views: list[CashFlowResult] = []
        for deal, offset in zip(self._deals, offsets, strict=True):
            deal_result, reinsurer_view = self._run_deal(deal, hurdle_rate)
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

        concentration_by_cedant = _concentration(
            [(dr.cedant, dr.ceded_face) for dr in deal_results]
        )
        concentration_by_product = _concentration(
            [(dr.product_type, dr.ceded_face) for dr in deal_results]
        )
        concentration_by_treaty = _concentration(
            [(dr.treaty_type, dr.ceded_face) for dr in deal_results]
        )

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
            hhi={
                "cedant": _herfindahl(concentration_by_cedant),
                "product": _herfindahl(concentration_by_product),
                "treaty": _herfindahl(concentration_by_treaty),
            },
        )

    def run_with_capital(
        self,
        hurdle_rate: float,
        capital_model: LICATCapital,
        *,
        align: AlignMode = "strict",
    ) -> PortfolioResultWithCapital:
        """Project, aggregate, and roll a single LICAT capital call onto the
        portfolio.

        Wraps :meth:`run` and joins the aggregate ``CashFlowResult`` and
        aggregate ceded NAR with a single ``LICATCapital.required_capital``
        call. The result carries every ``PortfolioResult`` field plus
        portfolio-level capital metrics and return-on-capital — see
        :class:`PortfolioResultWithCapital`.

        Args:
            hurdle_rate: Annual hurdle rate applied uniformly to every deal,
                the aggregate profit test, and the PV-capital denominator.
            capital_model: An instantiated ``LICATCapital`` (e.g. built via
                ``LICATCapital.for_product(product_type)``). The same factor
                set is applied to the entire portfolio — for a heterogeneous
                book, supply a model whose factors reflect the blended
                exposure.
            align: Time-alignment mode forwarded to :meth:`run` (ADR-061).

        Returns:
            A :class:`PortfolioResultWithCapital` with aggregate cash flows,
            profitability metrics, per-deal breakdown, concentration metrics,
            and aggregate capital metrics.

        Raises:
            PolarisValidationError: Conditions identical to :meth:`run`
                (empty portfolio, invalid hurdle rate, invalid ``align`` mode,
                mismatched valuation dates).
        """
        base = self.run(hurdle_rate, align=align)

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

        Returns:
            A :class:`PortfolioScenarioResult` with one entry per scenario
            in the order they were supplied (default-order matches
            ``standard_stress_scenarios()``).

        Raises:
            PolarisValidationError: If the portfolio is empty,
                ``hurdle_rate`` is not greater than -1, ``align`` is not a
                recognised mode (every :meth:`run` failure mode applies),
                or ``scenarios`` is an empty list (the empty case is
                rejected up front rather than silently returning an empty
                result).
        """
        from polaris_re.analytics.scenario import ScenarioRunner

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
            scenario_result = scenario_portfolio.run(hurdle_rate, align=align)
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
        scenario_portfolio = Portfolio(name=f"{self.name}_{scenario.name}")
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

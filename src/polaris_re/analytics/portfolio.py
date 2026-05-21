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

Scope (Slice 1 of Milestone 5.2): proportional treaties only — YRT,
coinsurance, modco — each exposing a ``cession_pct``. Stop-loss and other
non-proportional structures are out of scope. Policy-level cession overrides
are not applied; the treaty-level ``cession_pct`` governs every deal. Each
deal's inforce block must contain a single product type.
"""

from dataclasses import dataclass

import numpy as np

from polaris_re.analytics.profit_test import ProfitTester, ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import ceded_to_reinsurer_view
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["Deal", "DealResult", "Portfolio", "PortfolioResult"]


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


@dataclass(frozen=True)
class PortfolioResult:
    """Aggregate reinsurer-level result across every deal in a portfolio.

    Monetary values in dollars; rates as decimals. ``total_pv_profits``,
    ``total_irr``, ``breakeven_year``, and ``profit_margin`` are computed by
    a ``ProfitTester`` run on the aggregate cash flow, so they inherit the
    standard reporting guardrails (ADR-041).

    Concentration dictionaries map a category label to its share of total
    ceded face (shares sum to 1.0). ``hhi`` carries the Herfindahl-Hirschman
    index for each dimension ("cedant", "product", "treaty") — the sum of
    squared shares, ranging from ``1/k`` (perfectly diversified across ``k``
    categories) to ``1.0`` (fully concentrated).
    """

    n_deals: int
    hurdle_rate: float
    projection_months: int
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _treaty_label(treaty: BaseTreaty) -> str:
    """Return a clean treaty-type label, e.g. ``YRTTreaty`` -> ``YRT``."""
    name = type(treaty).__name__
    return name[: -len("Treaty")] if name.endswith("Treaty") else name


def _pad(arr: np.ndarray, length: int) -> np.ndarray:
    """Zero-pad a 1-D array to ``length`` months (no-op when already sized)."""
    out = np.zeros(length, dtype=np.float64)
    out[: len(arr)] = arr
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

    def run(self, hurdle_rate: float) -> PortfolioResult:
        """Project and aggregate every deal in the portfolio.

        Args:
            hurdle_rate: Annual hurdle rate applied uniformly to every deal
                and to the aggregate profit test (e.g. 0.10 for 10%).

        Returns:
            A :class:`PortfolioResult` with aggregate cash flows, total
            profitability metrics, the per-deal breakdown, and concentration
            metrics.

        Raises:
            PolarisValidationError: If the portfolio is empty or
                ``hurdle_rate`` is not greater than -1.
        """
        if not self._deals:
            raise PolarisValidationError("Cannot run an empty portfolio — add at least one deal.")
        if hurdle_rate <= -1.0:
            raise PolarisValidationError(f"hurdle_rate must be > -1, got {hurdle_rate}.")

        deal_results: list[DealResult] = []
        reinsurer_views: list[CashFlowResult] = []
        for deal in self._deals:
            deal_result, reinsurer_view = self._run_deal(deal, hurdle_rate)
            deal_results.append(deal_result)
            reinsurer_views.append(reinsurer_view)

        t_max = max(view.projection_months for view in reinsurer_views)

        aggregate_ncf = np.sum(
            [_pad(view.net_cash_flow, t_max) for view in reinsurer_views], axis=0
        )
        aggregate_premiums = np.sum(
            [_pad(view.gross_premiums, t_max) for view in reinsurer_views], axis=0
        )
        aggregate_nar = np.sum(
            [_pad(deal_result.ceded_nar, t_max) for deal_result in deal_results], axis=0
        )

        aggregate_cf = CashFlowResult(
            run_id=f"portfolio-{self.name}",
            valuation_date=self._deals[0].config.valuation_date,
            basis="NET",
            assumption_set_version="portfolio-aggregate",
            product_type="PORTFOLIO",
            block_id=self.name,
            projection_months=t_max,
            gross_premiums=aggregate_premiums,
            net_cash_flow=aggregate_ncf,
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
            aggregate_net_cash_flow=aggregate_ncf,
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
        )
        return deal_result, reinsurer_view

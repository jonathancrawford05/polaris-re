"""
EU Solvency II SCR module — simplified factor-based v1 (ADR-100, Epic 3 Slice 3).

Implements the Solvency II **standard formula** Solvency Capital Requirement
(SCR) for a life reinsurance book, the EU sibling of the Canadian LICAT
(`analytics/capital.py`) and US NAIC RBC (`analytics/rbc.py`) modules. Like both
of those it is a **factor-based committee-stage** calculator: each risk
sub-module is ``factor * exposure`` at every projection month, with conservative,
documented, per-product default factors the caller can override. The full
shock-based / asset-model calibration is deferred to the Asset/ALM epic (CVR
Tier C, after the Tier-A epics).

## Structure (standard-formula modular SCR)

The standard formula builds the SCR bottom-up through two correlation-matrix
aggregations:

1. **Life underwriting** sub-modules — mortality, lapse, catastrophe — are
   aggregated by the life-risk correlation matrix into a single
   life-underwriting SCR.
2. The **top-level** modules — market, counterparty default, life underwriting —
   are aggregated by the top-level correlation matrix into the **Basic SCR
   (BSCR)**.
3. **Operational risk** adds linearly outside the BSCR matrix (no
   diversification credit), giving ``SCR = BSCR + Op``.

The defining operation in both aggregations is the quadratic-form square root::

    SCR_agg = sqrt( sum_ij  Corr_ij * SCR_i * SCR_j )

i.e. ``sqrt(rᵀ · Corr · r)`` for the component vector ``r``. This is the EU
analogue of the NAIC covariance square root, generalised from a single
asset/insurance pair to a full correlation matrix.

## Exposures and factors

| Sub-module          | Exposure | Default? | Note |
|---------------------|----------|----------|------|
| Mortality           | **NAR**  | per-product | biometric shock on capital-at-risk |
| Lapse               | reserve  | per-product | mass-lapse strain on reserves |
| Catastrophe         | **NAR**  | per-product | the 1.5‰ life-CAT shock on capital-at-risk |
| Market              | reserve  | uniform  | spread / interest / equity on backing assets |
| Counterparty default| reserve  | uniform  | reinsurance / cash counterparty exposure |
| Operational         | reserve  | 0 (stub) | additive, outside BSCR |

The **catastrophe** default (``0.0015`` of NAR) is the citable standard-formula
life-catastrophe shock: an absolute +0.15% (1.5 per mille) one-year increase in
mortality applied to the capital-at-risk. The remaining factors are conservative
committee-stage placeholders pending the shock-based asset / ALM calibration,
exactly as the LICAT and RBC defaults are.

## Correlation matrices

`LIFE_CORRELATION` (mortality, lapse, catastrophe) and `TOP_LEVEL_CORRELATION`
(market, counterparty, life) are the standard-formula matrices from **Commission
Delegated Regulation (EU) 2015/35, Annex IV**. The top-level market / default /
life entries are all 0.25; within life, mortality-lapse is 0, mortality-CAT and
lapse-CAT are 0.25.

## Risk margin (cost-of-capital)

`SolvencyIIResult.risk_margin` applies the standard cost-of-capital method:
``RM = CoC * PV(future SCR)`` with the regulatory ``CoC = 6%`` and the projected
SCR stream discounted at the supplied rate. This is the monthly committee-stage
analogue of the standard-formula risk margin.

Sign convention (shared with LICAT / RBC): required capital is a positive,
time-varying scalar held against retained business; it is NOT discounted at the
hurdle rate — the time-value adjustment lives in the return-on-capital metric.
See ADR-100 in `docs/DECISIONS.md` for the Delegated-Regulation vintage and the
factor approximations used as defaults.
"""

from dataclasses import dataclass, field

import numpy as np
from pydantic import Field

from polaris_re.analytics.capital_base import discount_stream, strain_of
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.policy import ProductType

__all__ = [
    "LIFE_CORRELATION",
    "TOP_LEVEL_CORRELATION",
    "SolvencyIICapital",
    "SolvencyIIFactors",
    "SolvencyIIResult",
]


# ----------------------------------------------------------------------
# Standard-formula correlation matrices (Delegated Regulation 2015/35 Annex IV)
# ----------------------------------------------------------------------
# Life underwriting sub-modules, order (mortality, lapse, catastrophe):
#   mortality-lapse 0.00, mortality-cat 0.25, lapse-cat 0.25.
LIFE_CORRELATION: np.ndarray = np.array(
    [
        [1.00, 0.00, 0.25],
        [0.00, 1.00, 0.25],
        [0.25, 0.25, 1.00],
    ],
    dtype=np.float64,
)

# Top-level modules, order (market, counterparty default, life underwriting):
# all pairwise correlations are 0.25 in the standard formula.
TOP_LEVEL_CORRELATION: np.ndarray = np.array(
    [
        [1.00, 0.25, 0.25],
        [0.25, 1.00, 0.25],
        [0.25, 0.25, 1.00],
    ],
    dtype=np.float64,
)


# ----------------------------------------------------------------------
# Per-product default factors
# ----------------------------------------------------------------------
# Mortality (x NAR): biometric capital-at-risk shock. Non-zero for life
# products; ANNUITY carries longevity (out of scope), not mortality, risk → 0.
_MORTALITY_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.0020,
    ProductType.WHOLE_LIFE: 0.0020,
    ProductType.UNIVERSAL_LIFE: 0.0020,
    ProductType.DISABILITY: 0.0020,
    ProductType.CRITICAL_ILLNESS: 0.0020,
    ProductType.ANNUITY: 0.0,
}

# Lapse (x reserve): mass-lapse strain on reserves. Highest for surrender-rich
# permanent / annuity business, lowest for protection riders.
_LAPSE_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.0040,
    ProductType.WHOLE_LIFE: 0.0030,
    ProductType.UNIVERSAL_LIFE: 0.0040,
    ProductType.DISABILITY: 0.0020,
    ProductType.CRITICAL_ILLNESS: 0.0020,
    ProductType.ANNUITY: 0.0060,
}

# Catastrophe (x NAR): the standard-formula life-CAT shock, +1.5 per mille of
# capital-at-risk for one year. Zero for ANNUITY (no death-benefit NAR).
_CAT_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.0015,
    ProductType.WHOLE_LIFE: 0.0015,
    ProductType.UNIVERSAL_LIFE: 0.0015,
    ProductType.DISABILITY: 0.0015,
    ProductType.CRITICAL_ILLNESS: 0.0015,
    ProductType.ANNUITY: 0.0,
}

# Market and counterparty default factors are uniform across products (they are
# properties of the backing-asset / reinsurance arrangements, not the liability).
_MARKET_DEFAULT: float = 0.0050
_COUNTERPARTY_DEFAULT: float = 0.0010

# Regulatory cost-of-capital rate for the risk margin (standard formula).
_COST_OF_CAPITAL: float = 0.06


def _correlation_aggregate(components: list[np.ndarray], corr: np.ndarray) -> np.ndarray:
    """
    Standard-formula correlation aggregation ``sqrt(rᵀ · Corr · r)`` broadcast
    across the time dimension.

    Args:
        components: list of ``k`` per-period arrays, each shape ``(T,)``.
        corr: ``(k, k)`` symmetric correlation matrix.

    Returns:
        ``(T,)`` array of aggregated SCR, one value per projection month.

    The quadratic form is evaluated per period via an einsum over the component
    index, so there is no per-policy or per-period Python loop. A tiny negative
    quadratic value from float round-off is clamped to zero before the square
    root.
    """
    stacked = np.vstack(components) if components else np.empty((0, 0), dtype=np.float64)
    quad = np.einsum("ij,it,jt->t", corr, stacked, stacked)
    return np.sqrt(np.maximum(quad, 0.0))


class SolvencyIIFactors(PolarisBaseModel):
    """
    Solvency II standard-formula SCR sub-module factors.

    Defaults are committee-stage approximations. A bare `SolvencyIIFactors()`
    carries the mortality / lapse / catastrophe / market / counterparty factors
    non-zero and the operational factor as a zero stub; use
    :meth:`SolvencyIICapital.for_product` to populate the per-product schedule.

    `mortality_factor` and `catastrophe_factor` apply to NAR; `lapse_factor`,
    `market_factor`, `counterparty_factor`, and `operational_factor` apply to
    reserve_balance.
    """

    mortality_factor: float = Field(
        default=0.0020,
        ge=0.0,
        le=1.0,
        description=(
            "Life mortality-risk factor (x NAR). Committee-stage proxy for the "
            "standard-formula permanent mortality shock on capital-at-risk."
        ),
    )
    lapse_factor: float = Field(
        default=0.0040,
        ge=0.0,
        le=1.0,
        description=(
            "Life lapse-risk factor (x reserve). Committee-stage proxy for the "
            "standard-formula mass-lapse strain on reserves."
        ),
    )
    catastrophe_factor: float = Field(
        default=0.0015,
        ge=0.0,
        le=1.0,
        description=(
            "Life catastrophe-risk factor (x NAR). The standard-formula life-CAT "
            "shock: +1.5 per mille of capital-at-risk for one year."
        ),
    )
    market_factor: float = Field(
        default=0.0050,
        ge=0.0,
        le=1.0,
        description=(
            "Market-risk factor (x reserve). Committee-stage proxy for spread / "
            "interest / equity risk on the assets backing reserves."
        ),
    )
    counterparty_factor: float = Field(
        default=0.0010,
        ge=0.0,
        le=1.0,
        description=(
            "Counterparty-default-risk factor (x reserve). Committee-stage proxy "
            "for reinsurance / cash counterparty exposure."
        ),
    )
    operational_factor: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Operational-risk factor (x reserve). Adds linearly outside the BSCR "
            "correlation matrix. Zero stub by default."
        ),
    )


@dataclass
class SolvencyIIResult:
    """
    Solvency II SCR schedule produced by `SolvencyIICapital.required_capital`.

    All component arrays have shape ``(T,)`` (dollars per month). The life
    sub-modules (`mortality_component`, `lapse_component`, `catastrophe_component`)
    aggregate via the life correlation matrix into `life_underwriting_component`;
    that, with `market_component` and `counterparty_component`, aggregates via the
    top-level matrix into `bscr_component`. `capital_by_period` is the SCR
    (= BSCR + operational), the held-capital basis.

    Satisfies the `CapitalSchedule` protocol (ADR-098).
    """

    projection_months: int
    mortality_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    lapse_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    catastrophe_component: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    life_underwriting_component: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    market_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    counterparty_component: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    operational_component: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    bscr_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    capital_by_period: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    initial_capital: float = 0.0
    peak_capital: float = 0.0

    def pv_capital(self, discount_rate: float) -> float:
        """PV of the SCR capital STOCK at a flat annual rate."""
        return discount_stream(self.capital_by_period, discount_rate)

    def capital_strain(self) -> np.ndarray:
        """Period-over-period change in required capital, shape ``(T,)``."""
        return strain_of(self.capital_by_period)

    def pv_capital_strain(self, discount_rate: float) -> float:
        """PV of the capital STRAIN at a flat annual rate."""
        return discount_stream(self.capital_strain(), discount_rate)

    def risk_margin(self, discount_rate: float, coc: float = _COST_OF_CAPITAL) -> float:
        """
        Cost-of-capital risk margin ``RM = CoC * PV(future SCR)``.

        Applies the standard cost-of-capital method: the projected SCR stream is
        discounted at `discount_rate` and scaled by the cost-of-capital rate
        `coc` (regulatory default 6%). This is the monthly committee-stage
        analogue of the standard-formula risk margin.
        """
        return coc * discount_stream(self.capital_by_period, discount_rate)


class SolvencyIICapital(PolarisBaseModel):
    """
    Factor-based Solvency II standard-formula SCR calculator.

    Required capital at each projection month is the standard-formula SCR: the
    life-underwriting sub-modules are correlation-aggregated, then combined with
    market and counterparty risk through the top-level correlation matrix to give
    the BSCR, with operational risk added outside the matrix (see module
    docstring). `for_product` selects standard-formula-order factor
    approximations per product type.
    """

    factors: SolvencyIIFactors = Field(default_factory=SolvencyIIFactors)

    @classmethod
    def for_product(cls, product_type: ProductType) -> "SolvencyIICapital":
        """
        Construct a calculator pre-populated with the mortality / lapse /
        catastrophe default factors for the given product type, plus the uniform
        market / counterparty factors. The operational factor remains a zero stub
        (Asset/ALM epic populates it).
        """
        mortality = _MORTALITY_DEFAULT_BY_PRODUCT.get(product_type, 0.0020)
        lapse = _LAPSE_DEFAULT_BY_PRODUCT.get(product_type, 0.0040)
        catastrophe = _CAT_DEFAULT_BY_PRODUCT.get(product_type, 0.0015)
        return cls(
            factors=SolvencyIIFactors(
                mortality_factor=mortality,
                lapse_factor=lapse,
                catastrophe_factor=catastrophe,
                market_factor=_MARKET_DEFAULT,
                counterparty_factor=_COUNTERPARTY_DEFAULT,
            )
        )

    def required_capital(
        self,
        cashflows: CashFlowResult,
        nar: np.ndarray | None = None,
    ) -> SolvencyIIResult:
        """
        Compute the Solvency II standard-formula SCR schedule over the horizon.

        Args:
            cashflows: GROSS or NET basis CashFlowResult. CEDED is rejected —
                capital is held against retained business, not ceded.
            nar: Optional NAR vector of shape ``(T,)`` overriding `cashflows.nar`.
                If neither is supplied, raises.

        Returns:
            SolvencyIIResult with the life sub-module components, the
            correlation-aggregated life-underwriting SCR and BSCR, and the SCR
            (`capital_by_period`).
        """
        if cashflows.basis == "CEDED":
            raise ValueError(
                "SolvencyIICapital does not accept CEDED basis CashFlowResult. "
                "Capital is held against retained business — pass NET or GROSS."
            )

        n = cashflows.projection_months
        nar_vec = self._resolve_nar(cashflows, nar, n)
        reserve_vec = np.asarray(cashflows.reserve_balance, dtype=np.float64)
        f = self.factors

        mortality = f.mortality_factor * nar_vec
        lapse = f.lapse_factor * reserve_vec
        catastrophe = f.catastrophe_factor * nar_vec
        market = f.market_factor * reserve_vec
        counterparty = f.counterparty_factor * reserve_vec
        operational = f.operational_factor * reserve_vec

        # 1. Life underwriting sub-modules → life SCR (life correlation matrix).
        life_uw = _correlation_aggregate([mortality, lapse, catastrophe], LIFE_CORRELATION)
        # 2. Top-level modules → BSCR (top-level correlation matrix).
        bscr = _correlation_aggregate([market, counterparty, life_uw], TOP_LEVEL_CORRELATION)
        # 3. Operational risk adds linearly outside the BSCR matrix.
        scr = bscr + operational

        initial = float(scr[0]) if n > 0 else 0.0
        peak = float(scr.max()) if n > 0 else 0.0

        return SolvencyIIResult(
            projection_months=n,
            mortality_component=mortality.astype(np.float64),
            lapse_component=lapse.astype(np.float64),
            catastrophe_component=catastrophe.astype(np.float64),
            life_underwriting_component=life_uw.astype(np.float64),
            market_component=market.astype(np.float64),
            counterparty_component=counterparty.astype(np.float64),
            operational_component=operational.astype(np.float64),
            bscr_component=bscr.astype(np.float64),
            capital_by_period=scr.astype(np.float64),
            initial_capital=initial,
            peak_capital=peak,
        )

    @staticmethod
    def _resolve_nar(
        cashflows: CashFlowResult, nar_override: np.ndarray | None, n: int
    ) -> np.ndarray:
        if nar_override is not None:
            if len(nar_override) != n:
                raise PolarisComputationError(
                    f"NAR override length {len(nar_override)} does not match projection length {n}."
                )
            return np.asarray(nar_override, dtype=np.float64)
        if cashflows.nar is None:
            raise PolarisComputationError(
                "SolvencyIICapital.required_capital requires NAR. Pass `nar=` "
                "explicitly or use a CashFlowResult that already has `nar` "
                "populated (e.g. post-YRTTreaty)."
            )
        return np.asarray(cashflows.nar, dtype=np.float64)

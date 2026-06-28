"""
analytics/alm.py — Asset-liability management: duration-gap analysis.

This is Slice 4 of the Asset / ALM epic (Tier-C C0, ARCHITECTURE Milestone
5.4). Slices 1-3 built the asset side — a ``Bond`` / ``AssetPortfolio`` with
cash-flow projection, pricing, book yield, investment income, and Macaulay /
modified duration / convexity (``core/asset.py``) — and drove the Modco
treaty's modco interest from the asset book yield. This module closes the loop
on the *analysis* side: it measures the interest-rate sensitivity of the
**liability** and reports the **duration gap** between the assets backing a
block of ceded reserves and the obligations those assets fund.

A reinsurer pricing a Modco or coinsurance deal needs to know not just what the
backing assets earn (Slice 3) but how their interest-rate sensitivity compares
to the liability — a positive duration gap means the assets re-price faster
than the liability when rates move, a negative gap the reverse. This is the
foundation of any embedded-value / ALM story.

This module is purely additive: nothing here is wired into the pricing path, so
all golden baselines are byte-identical. The CLI / API / dashboard / Excel
surfacing of the duration gap is a later sub-slice.

Discounting convention
----------------------
Every measure here discounts a cash-flow vector on the **same** effective-annual
monthly convention as ``CashFlowResult.pv_*`` and ``AssetPortfolio`` (Slice 2):
a cash flow at month ``t`` (1-indexed, end of month) is discounted by ``v ** t``
where ``v = (1 + annual_yield) ** (-1 / 12)``, and time is expressed in **years**
(``τ = t / 12``) so the textbook duration formulas hold against the
effective-annual yield ``y``. Discounting both the asset and liability sides at a
single common flat valuation yield isolates the *timing* mismatch (the duration
gap) from any yield difference — consistent with the epic's flat-yield scope
(``docs/PLAN_asset_alm.md`` §5).
"""

import numpy as np
from pydantic import Field

from polaris_re.core.asset import AssetPortfolio
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "DurationGapResult",
    "DurationMeasures",
    "duration_gap",
    "duration_measures",
    "liability_cash_flows",
    "reserve_liability_cash_flows",
]


class DurationMeasures(PolarisBaseModel):
    """
    Present value and duration of a single cash-flow stream at a valuation yield.

    The Macaulay duration is the PV-weighted average time to the cash flows (in
    **years**); the modified duration is the price sensitivity
    ``-(1 / P) dP/dy`` under the effective-annual yield convention
    (``Macaulay / (1 + y)``).
    """

    present_value: float = Field(
        description="Present value of the cash-flow stream at the valuation yield, in dollars.",
    )
    macaulay_duration: float = Field(
        description="PV-weighted average time to the cash flows, in years.",
    )
    modified_duration: float = Field(
        description="Price sensitivity -(1/P) dP/dy = Macaulay / (1 + y), in years.",
    )


class DurationGapResult(PolarisBaseModel):
    """
    Asset-liability duration gap on a block of assets and the liability they fund.

    Both sides are measured at a single common ``valuation_yield`` so the gap
    reflects the timing mismatch alone. The ``duration_gap`` is the modified
    duration of the assets minus that of the liability (years): positive when
    the assets are longer (re-price faster as rates fall), negative when the
    liability is longer. The ``dollar_duration_gap`` scales each modified
    duration by its market value / present value, giving the net change in
    surplus per unit change in yield (the hedgeable quantity).
    """

    valuation_yield: float = Field(
        description="Common effective-annual yield at which both sides are discounted.",
    )

    asset_market_value: float = Field(description="Asset portfolio market value, in dollars.")
    asset_macaulay_duration: float = Field(description="Asset Macaulay duration, in years.")
    asset_modified_duration: float = Field(description="Asset modified duration, in years.")

    liability_present_value: float = Field(
        description="Present value of the liability cash flows, in dollars.",
    )
    liability_macaulay_duration: float = Field(
        description="Liability Macaulay duration, in years.",
    )
    liability_modified_duration: float = Field(
        description="Liability modified duration, in years.",
    )

    duration_gap: float = Field(
        description=(
            "Asset modified duration minus liability modified duration, in years. "
            "Positive => assets longer than the liability."
        ),
    )
    dollar_duration_asset: float = Field(
        description="Asset modified duration * asset market value (dollar duration).",
    )
    dollar_duration_liability: float = Field(
        description="Liability modified duration * liability present value (dollar duration).",
    )
    dollar_duration_gap: float = Field(
        description=(
            "Asset dollar duration minus liability dollar duration: the net change "
            "in surplus per unit change in yield."
        ),
    )


def duration_measures(cash_flows: np.ndarray, annual_yield: float) -> DurationMeasures:
    """
    Present value and Macaulay / modified duration of ``cash_flows`` at a yield.

    ``cash_flows[i]`` is the cash flow at month ``i + 1`` (1-indexed, end of
    month). Discounting matches the engine convention
    (``v = (1 + annual_yield) ** (-1 / 12)``, time in years ``τ = (i + 1) / 12``)
    so the result is on the same basis as ``AssetPortfolio`` and
    ``CashFlowResult.pv_*``:

        price            = Σ cf_t · (1 + y) ** (-τ_t)
        Macaulay (years) = Σ τ_t · cf_t · (1+y)^(-τ_t) / price
        modified (years) = Macaulay / (1 + y)

    Fed the aggregate cash-flow vector of an ``AssetPortfolio`` at the same
    yield, this reproduces that portfolio's ``macaulay_duration`` /
    ``modified_duration`` exactly (verified in tests) — it is the same closed
    form generalised to an arbitrary stream.

    Raises ``PolarisValidationError`` if ``cash_flows`` is not a non-empty 1-D
    vector, and ``PolarisComputationError`` if the present value is non-positive
    (duration is undefined for a stream that discounts to zero or a net inflow).
    """
    cf = np.asarray(cash_flows, dtype=np.float64)
    if cf.ndim != 1 or cf.shape[0] == 0:
        raise PolarisValidationError(
            f"cash_flows must be a non-empty 1-D vector, got shape {cf.shape}"
        )

    periods = np.arange(1, cf.shape[0] + 1, dtype=np.float64)
    v = (1.0 + annual_yield) ** (-1.0 / 12.0)
    pv = cf * v**periods
    years = periods / 12.0

    price = float(pv.sum())
    if price <= 0.0:
        raise PolarisComputationError(
            f"duration_measures: non-positive present value ({price}) at yield "
            f"{annual_yield}; duration is undefined."
        )

    macaulay = float((years * pv).sum() / price)
    modified = macaulay / (1.0 + annual_yield)
    return DurationMeasures(
        present_value=price,
        macaulay_duration=macaulay,
        modified_duration=modified,
    )


def liability_cash_flows(result: CashFlowResult) -> np.ndarray:
    """
    Net **gross-premium** benefit-outgo stream from a projection result.

    .. note::
       Superseded as the duration-gap liability by :func:`reserve_liability_cash_flows`
       (the reserve-backed Option-B stream) for the CLI / API surfaces. This
       function subtracts *gross* (loaded) premiums, so for a premium-paying /
       reserve-building block its present value can be non-positive (premiums
       dominate benefits in PV) and the liability duration is then undefined. It
       is retained as a benefit-outgo view and for run-off-shaped analysis.

    Returns ``death_claims + lapse_surrenders + expenses - gross_premiums`` as a
    ``(T,)`` float64 array — the net cash the backing assets have to pay out each
    month (benefits and expenses, less the premiums that arrive to offset them).
    This is the obligation stream whose present value the reserve is meant to
    cover, so its modified duration is the liability duration the assets should
    match.

    Sign convention: a positive entry is a net *outflow* (the asset book pays).
    Early durations of an inforce block can be net inflows (premiums exceed
    benefits) and so negative, but a block carrying a positive reserve discounts
    to a positive total present value, which is what ``duration_measures``
    requires. Reserve *movements* are deliberately excluded — they are an
    accounting transfer, not a cash obligation the assets fund.
    """
    return (
        np.asarray(result.death_claims, dtype=np.float64)
        + np.asarray(result.lapse_surrenders, dtype=np.float64)
        + np.asarray(result.expenses, dtype=np.float64)
        - np.asarray(result.gross_premiums, dtype=np.float64)
    )


def reserve_liability_cash_flows(
    result: CashFlowResult,
    reserve_valuation_rate: float,
) -> np.ndarray:
    """
    Reserve run-off (release) stream that the backing assets must fund.

    This is the **reserve-backed** liability stream (Option B, the convention the
    maintainer settled on 2026-06-27 — see ``docs/CONTINUATION_asset_alm.md``).
    Unlike :func:`liability_cash_flows`, which subtracts the *gross* (loaded)
    premiums and so produces a pricing/profit stream whose present value need not
    tie to anything, this stream is derived directly from the held reserve and
    has the defining property that **its present value at the reserve valuation
    rate equals the opening held reserve** (``result.reserve_balance[0]``). Its
    modified duration is therefore the interest-rate sensitivity of the reserve
    the assets back — the liability side of an asset-liability duration gap.

    Construction (the standard IFRS-17 / embedded-value "expected liability cash
    flow"). Let ``R_t = reserve_balance[t]`` be the in-force-weighted reserve held
    at the start of month ``t`` (``t = 0 .. T-1``; ``R_0`` is the opening reserve),
    and ``a = (1 + reserve_valuation_rate) ** (1/12)`` the engine's monthly
    accumulation factor at the reserve's own valuation interest rate. The cash the
    reserve fund throws off in month ``t+1`` — expected benefits and expenses less
    expected valuation (net) premiums on the valuation basis — is the reserve
    rolled forward with interest, less what is held back for the next month:

        L_t = R_t * a - R_{t+1}      (months 1 .. T-1)
        L_{T-1} = R_{T-1} * a        (final month: the last reserve runs off)

    Returned as a ``(T,)`` float64 array aligned to :func:`duration_measures`'s
    convention (``L_t`` is the cash flow at month ``t + 1``, discounted by
    ``v ** (t + 1)``). Discounting that stream at ``reserve_valuation_rate``
    telescopes exactly to ``R_0`` (verified in tests on every reserve basis):

        Σ_t v^(t+1) * L_t = R_0,    v = 1 / a

    Early entries can be **negative** (a building reserve receives more valuation
    premium than it pays in benefits — a net inflow), but a block carrying a
    positive opening reserve discounts to a positive total present value, which is
    what :func:`duration_measures` requires. The premium-paying / reserve-building
    blocks that the gross-premium :func:`liability_cash_flows` left undefined
    (e.g. a whole-life block) therefore now have a well-defined liability duration;
    the graceful skip becomes a true edge case (a non-positive opening reserve).

    The interest factor ``a`` uses the **reserve's** valuation rate, not the
    common ALM valuation yield: the stream is intrinsic to the held reserve, and
    only the subsequent duration *measurement* uses the common yield. Pass
    ``ProjectionConfig.effective_valuation_rate`` here.

    Raises ``PolarisValidationError`` if ``result.reserve_balance`` is not a
    non-empty 1-D vector (e.g. a result built without a reserve series).
    """
    reserves = np.asarray(result.reserve_balance, dtype=np.float64)
    if reserves.ndim != 1 or reserves.shape[0] == 0:
        raise PolarisValidationError(
            "reserve_liability_cash_flows requires a non-empty 1-D reserve_balance; "
            f"got shape {reserves.shape}. (A reserve-backed liability duration needs "
            "the held reserve series.)"
        )

    a = (1.0 + reserve_valuation_rate) ** (1.0 / 12.0)
    liability = np.empty_like(reserves)
    liability[:-1] = reserves[:-1] * a - reserves[1:]
    liability[-1] = reserves[-1] * a
    return liability


def duration_gap(
    portfolio: AssetPortfolio,
    liability_cash_flow_vector: np.ndarray,
    valuation_yield: float,
) -> DurationGapResult:
    """
    Duration-gap analysis of ``portfolio`` against a liability cash-flow stream.

    Both sides are discounted at the single common ``valuation_yield`` so the
    gap measures the timing mismatch alone. The asset measures come from the
    portfolio's own (tested) duration API; the liability measures come from
    :func:`duration_measures` on ``liability_cash_flow_vector`` (e.g. the output
    of :func:`liability_cash_flows`).

    The duration gap is ``asset_modified_duration - liability_modified_duration``
    (years); the dollar-duration gap scales each by its value
    (``modified_duration * value``) and differences them — the net change in
    surplus per unit change in yield. A perfectly immunised block (assets whose
    cash flows equal the liability's) has both gaps equal to zero.

    Raises ``PolarisComputationError`` (via the underlying measures) if either
    side has a non-positive present / market value at ``valuation_yield``.
    """
    asset_market_value = portfolio.market_value(valuation_yield)
    if asset_market_value <= 0.0:
        raise PolarisComputationError(
            f"duration_gap: non-positive asset market value ({asset_market_value}) "
            f"at yield {valuation_yield}; duration gap is undefined."
        )
    asset_macaulay = portfolio.macaulay_duration(valuation_yield)
    asset_modified = portfolio.modified_duration(valuation_yield)

    liability = duration_measures(liability_cash_flow_vector, valuation_yield)

    dollar_duration_asset = asset_modified * asset_market_value
    dollar_duration_liability = liability.modified_duration * liability.present_value

    return DurationGapResult(
        valuation_yield=valuation_yield,
        asset_market_value=asset_market_value,
        asset_macaulay_duration=asset_macaulay,
        asset_modified_duration=asset_modified,
        liability_present_value=liability.present_value,
        liability_macaulay_duration=liability.macaulay_duration,
        liability_modified_duration=liability.modified_duration,
        duration_gap=asset_modified - liability.modified_duration,
        dollar_duration_asset=dollar_duration_asset,
        dollar_duration_liability=dollar_duration_liability,
        dollar_duration_gap=dollar_duration_asset - dollar_duration_liability,
    )

# Continuation: Asset / ALM model

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier-C **C0** (the
fourth epic, after the three Tier-A epics); ROADMAP Milestone 5.4.
**Status:** IN PROGRESS
**Total slices:** 4
**Estimated total scope:** ~20 dev-days (4 sessions, one slice each)
**Plan:** `docs/PLAN_asset_alm.md` (read-only spec)

## Overall Goal

Give Polaris RE an asset side. Model a portfolio of fixed-income instruments
(coupon + principal cash flows, pricing), compute the investment income and
duration/convexity those assets carry, drive the Modco treaty's modco interest
from an `AssetPortfolio` book yield instead of a flat rate, and report an
asset-liability duration gap on the net reinsurer position. This upgrades Modco
from "approximate" (fixed credited rate) to "correct" and is the foundation of
any embedded-value / ALM analytics.

## Decomposition

### Slice 1: Bond cash-flow model + `AssetPortfolio`
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-g36zmo (environment-designated)
- **PR:** #107 (merged)
- **What was done:** Added `core/asset.py` with `Bond` (single fixed-income
  instrument on the monthly grid — `cash_flow_vector(months)`,
  `price(annual_yield)`) and `AssetPortfolio` (non-empty bond list with
  aggregate cash flow / market value / book value / face). Exported from
  `polaris_re.core`. 34 closed-form/validation tests. ADR-108.
- **Key decisions:**
  - Bond pricing uses the **engine's** effective-annual monthly discounting
    (`v = (1+y)^(-1/12)`, cash flow at month t discounted by `v^t`) so a bond
    PV and a `CashFlowResult` PV are comparable — Slices 3/4 depend on this.
  - `coupon_frequency` must divide 12 (1/2/3/4/6/12) so coupons land on integer
    months of the projection grid.
  - `book_value` is an optional raw input; `carrying_value` resolves it to par
    when unset. Keep this distinction — Slice 2's book yield reads
    `carrying_value`.
  - Purely additive: nothing wired into pricing, goldens byte-identical.

### Slice 2: Investment income + duration / convexity
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-hecrn1 (environment-designated)
- **PR:** #108 (merged)
- **What was done:** Extended `AssetPortfolio` with `book_yield()` (gross
  effective-annual IRR of carrying value vs cash flows via `brentq`, `None` on
  no sign change, a flat scalar), `investment_income(reserve_vector,
  annual_yield=None)` (= `reserve · y / 12`, the modco-interest stream Slice 3
  needs; raises `PolarisComputationError` when no yield and book yield is
  `None`), and `macaulay_duration` / `modified_duration` / `convexity` (time in
  **years**, textbook closed forms under the effective-annual yield). 17 new
  closed-form/property tests. ADR-109.
- **Key decisions:**
  - Risk measures discount the aggregate cash-flow vector on the engine
    convention (`v=(1+y)^(-1/12)`) but express time in **years** (`τ=t/12`), so
    Macaulay = `Σ τ·PV/ΣPV`, modified = `Macaulay/(1+y)`, convexity =
    `Σ τ(τ+1)PV/(P(1+y)²)`. Zero-bond reductions: duration `=N`, convexity
    `=N(N+1)/(1+y)²`.
  - `book_yield()` reuses the `ProfitTester` `brentq` bracket `[-0.99, 100.0]`
    and its None-on-no-sign-change guard. It equates the discounted cash flows
    to the **carrying value** (`book_value`), so a par book recovers the coupon.
  - Slice 3 should call `book_yield()` once and pass the scalar (with the flat
    `modco_interest_rate` as the fallback default) into the modco-interest
    calc — Option A precedence.
  - Purely additive: nothing wired into pricing, goldens byte-identical.

### Slice 3: Modco integration
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-sf8u5j (environment-designated)
- **PR:** #109 (this PR)
- **What was done:** `ModcoTreaty.apply()` gained an optional
  `asset_portfolio: AssetPortfolio | None = None`. A new private helper
  `_resolve_modco_rate()` returns the effective annual rate the existing
  modco-interest line multiplies by: the portfolio's `book_yield()` when an
  `AssetPortfolio` is supplied (**Option A precedence**), with the flat
  `modco_interest_rate` as the fallback whenever the book yield is unrecoverable
  (`None`), and unchanged when no portfolio is passed (byte-identical default).
  6 new closed-form / additivity tests. ADR-110.
- **Key decisions:**
  - Resolve to a **scalar rate** and reuse the existing modco-interest
    arithmetic rather than calling `investment_income()` directly — the
    no-portfolio path then multiplies by `self.modco_interest_rate` with
    identical arithmetic (byte-identical goldens), and the flat rate can serve
    as the fallback that `investment_income()`'s raise-on-`None` would forbid.
    The two expressions are numerically equal on the asset path.
  - The three PLAN §5 decisions (gross flat book yield, deterministic
    reinvestment, Option A precedence) are now recorded as binding in ADR-110.
  - NCF additivity is independent of the rate source — `modco_interest` cancels
    between net and ceded sides regardless of how `modco_rate` resolves.

### Slice 4: ALM analytics + surfacing

Slice 4 proved too large for one session (a new analytics module **plus** five
presentation surfaces + a notebook), so it was re-decomposed into **4a** (the
analytics core) and **4b** (surfacing), mirroring how Epic 3's Slice 4c split
into 4c-1 / 4c-2.

#### Slice 4a: `analytics/alm.py` duration-gap core
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-v2s976 (environment-designated)
- **PR:** #110 (this PR)
- **What was done:** Added `analytics/alm.py` with `duration_measures(cash_flows,
  yield)` (PV + Macaulay / modified duration of any stream, on the engine
  discounting convention — the same closed form the asset duration methods use,
  generalised), `liability_cash_flows(result)` (net benefit-outgo stream
  `claims + lapses + expenses - premiums` from a `CashFlowResult`), and
  `duration_gap(portfolio, liability_cfs, valuation_yield) -> DurationGapResult`
  (asset vs liability Macaulay / modified duration, the duration gap, and the
  dollar-duration gap, both sides measured at one common flat yield). Exported
  from `polaris_re.analytics`. 21 closed-form tests. ADR-111.
- **Key decisions:**
  - **Single common valuation yield** for both sides — isolates the timing
    mismatch (the gap) from any yield difference; matches the epic's flat-yield
    scope (PLAN §5). A caller wanting the asset's own book yield passes
    `portfolio.book_yield()` as `valuation_yield`.
  - Asset measures come from the portfolio's own (tested) duration API; the
    liability side uses the generic `duration_measures` — one closed form, not
    two, locked by a consistency test.
  - The modified-duration gap anchors the headline (first-order hedgeable
    sensitivity); Macaulay is reported alongside.
  - Purely additive: nothing wired into pricing, goldens byte-identical.

#### Slice 4b: ALM surfacing + validation notebook

Slice 4b is five surfaces (CLI / API / dashboard / Excel) plus a notebook, each
needing an asset-portfolio input threaded through its config/request — too much
for one session. Re-decomposed into surface-sized sub-slices (mirroring how
Epic 3's Slice 4c split into 4c-1 / 4c-2a / 4c-2b / 4c-2c). The config-schema
decision is load-bearing (the API and dashboard mirror it), so the CLI machine
surface ships first ("config model first, then consumers").

##### Slice 4b-1: CLI asset-portfolio input + duration-gap output
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-lu9ugs (environment-designated)
- **PR:** (this PR)
- **What was done:** `DealConfig` gained `asset_portfolio: AssetPortfolio | None`
  and `alm_valuation_yield: float | None` (both default `None` → byte-identical
  existing configs). The CLI parses `deal.asset_portfolio` (the `AssetPortfolio`
  JSON shape, Pydantic-validated) and `deal.alm_valuation_yield` from the nested
  config; `_price_single_cohort` computes `duration_gap(portfolio,
  liability_cash_flows(net), yield)` per cohort when a portfolio is supplied,
  defaulting the common valuation yield to the deal `discount_rate`. The result
  is emitted as a per-cohort `alm_duration_gap` JSON key (mirrored at the top
  level for a single-cohort run) and rendered as a Rich console table. 12 tests.
  ADR-112.
- **Key decisions:**
  - **Purely additive, never aborts pricing.** A cohort whose net benefit-outgo
    discounts to a non-positive PV at the valuation yield (premium-paying /
    reserve-building blocks — the golden WHOLE_LIFE cohort does this even at 6%)
    has an undefined liability duration; `PolarisComputationError` is caught per
    cohort, the block is skipped with a warning, and pricing continues.
  - Default valuation yield = deal `discount_rate` (single common yield isolates
    the timing mismatch, per ADR-111); explicit `alm_valuation_yield` overrides.
  - Liability stream = the **net** (post-treaty) cohort's `liability_cash_flows`
    (ADR-111 documented default).

##### Slice 4b-2: API asset-portfolio input + duration-gap output
- **Status:** NEXT
- **Depends on:** Slice 4b-1 merged
- **Scope:** mirror 4b-1 on the REST `/api/v1/price` surface — `PriceRequest`
  gains an `asset_portfolio` + `alm_valuation_yield`; `PriceResponse` gains the
  duration-gap block. Reuse the CLI's compute path / config-schema shape so the
  CLI↔API parity tests cover it. Resolve the **canonical liability stream**
  question here with maintainer input (see below).

##### Slice 4b-3: dashboard + Excel presentation surfaces
- **Status:** PLANNED
- **Depends on:** Slice 4b-2 merged
- **Scope:** asset-portfolio input widget + duration-gap display on the
  dashboard, and an ALM block on the Excel deal-pricing export.
- **Carry-forward (PR #111 review P2):** thread the two new `DealConfig` fields
  (`asset_portfolio`, `alm_valuation_yield`) through `DealConfig.to_dict()` when
  this slice adds the dashboard widget. 4b-1 deliberately left them out of
  `to_dict()` (consistent with the `yrt_rate_table_*` precedent — `to_dict`
  backs the dashboard `DEFAULTS` / CLI↔Streamlit parity surface, not a full
  serialisation), which is correct until the dashboard actually consumes them.

##### Slice 4b-4: ALM validation notebook
- **Status:** PLANNED
- **Depends on:** Slice 4b-3 merged
- **Scope:** an end-to-end ALM validation notebook (duration gap on the golden
  block + a worked closed-form reconciliation).

- **Open design (surfaced concretely by 4b-1; resolve in 4b-2):** the canonical
  mapping from a priced deal to "the" liability cash-flow stream. The net
  benefit-outgo default (`liability_cash_flows`) has a **non-positive PV for
  premium-paying / reserve-building blocks** (the golden WHOLE_LIFE cohort), so
  its duration gap is undefined and 4b-1 skips it. A reserve-runoff or
  reinsurer-side liability stream would likely be defined; confirm the convention
  with the maintainer when wiring the API.

## Context for Next Session

- Discounting convention is the load-bearing decision: **match the engine**
  (`v=(1+y)^(-1/12)`). Do not switch to nominal/bond-market compounding, or
  bond PVs stop reconciling with `CashFlowResult` PVs and the par-bond closed
  form breaks.
- The bond list is the asset analogue of the policy list — aggregate into
  `(T,)` arrays, don't loop per-instrument in any hot path (the small per-bond
  loop in `cash_flow_vector` is over the bond list, not the time grid, and is
  fine).
- Slice 2's `book_yield` is the IRR of `carrying_value` vs the cash-flow
  vector; reuse the profit tester's `brentq` pattern and its None-on-no-sign-
  change guard.

## Open Questions (for human) — ALL RESOLVED (maintainer, 2026-06-26)

- **Book yield definition (Slice 2) — RESOLVED.** `book_yield()` is the **gross**
  IRR of carrying value vs cash flows, a **scalar held flat**. Net-of-spread and
  time-varying amortising earned rates are NICE-TO-HAVE follow-ups (harvested to
  PRODUCT_DIRECTION), not this epic.
- **Reinvestment yield (Slice 2/3) — RESOLVED.** Epic 4 is deterministic: the
  book yield **is** the (flat) reinvestment yield. Stochastic reinvestment
  (Hull-White / CIR via `analytics/stochastic.py`, ROADMAP 5.4) is out of scope
  and already harvested as a NICE-TO-HAVE follow-up.
- **Modco precedence (Slice 3) — RESOLVED (Option A).** When both an
  `AssetPortfolio` and a flat `modco_interest_rate` are supplied, the asset book
  yield takes precedence and the flat rate is the fallback. NCF additivity holds
  regardless of the rate source (`modco_interest` cancels between sides). To be
  recorded in an ADR when Slice 3 lands.

No open questions remain for the human; Slice 2 can proceed on these decisions.

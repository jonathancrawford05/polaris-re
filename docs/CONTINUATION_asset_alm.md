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
- **PR:** #107 (draft)
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
- **PR:** #108 (draft)
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
- **Status:** NEXT
- **Depends on:** Slice 2 merged
- **Scope:** `ModcoTreaty.apply()` accepts an optional `AssetPortfolio`; modco
  interest is driven by the asset **book yield** on the notional ceded reserve
  when supplied (**Option A precedence**), else the flat `modco_interest_rate`
  (default, byte-identical). Preserve the NCF additivity proof (ARCHITECTURE
  §5). New ADR recording the three resolved decisions. Closed-form + additivity
  tests.

### Slice 4: ALM analytics + surfacing
- **Status:** PLANNED
- **Depends on:** Slice 3 merged
- **Scope:** `analytics/alm.py` duration-gap analysis on the net reinsurer
  position (asset vs liability duration, dollar-duration mismatch). Surface on
  CLI / API / dashboard / Excel + validation notebook. This is the only slice
  that may move goldens, and only when an asset portfolio is supplied — document
  any regenerated baseline.

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

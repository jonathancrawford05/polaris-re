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
- **PR:** (this draft)
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
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:** `src/polaris_re/core/asset.py` (extend
  `AssetPortfolio`), `tests/test_core/test_asset.py`, `docs/DECISIONS.md`
  (new ADR), `docs/PLAN_asset_alm.md` + this file (status).
- **Tests to add:** duration of a zero = its term; modified duration =
  Macaulay/(1+y); a textbook convexity value; investment income on a flat book
  yield = `reserve · yield / 12`.
- **Acceptance criteria:**
  - `AssetPortfolio.investment_income(reserve_vector, ...)` returns monthly
    income consistent with the book yield.
  - `book_yield()` (IRR of carrying value vs cash flows, via
    `scipy.optimize.brentq` with a sign-change guard), `macaulay_duration`,
    `modified_duration`, `convexity` all closed-form tested.
  - Goldens byte-identical (still additive).

### Slice 3: Modco integration
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
- **Scope:** `ModcoTreaty.apply()` accepts an optional `AssetPortfolio`; modco
  interest is driven by the asset book yield / investment income on the
  notional ceded reserve when supplied, else the flat `modco_interest_rate`
  (default, byte-identical). Preserve the NCF additivity proof (ARCHITECTURE
  §5). New ADR for the precedence rule. Closed-form + additivity tests.

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

## Open Questions (for human)

- **Reinvestment yield (Slice 2/3).** When asset cash flows arrive before the
  liability needs them, a reinvestment assumption is required. Slices 1–2 treat
  the book yield as the (flat) reinvestment yield. Stochastic reinvestment
  (Hull-White / CIR via `analytics/stochastic.py`, ROADMAP 5.4) is deliberately
  out of scope for this epic and harvested as a follow-up — confirm that's the
  intended boundary.
- **Modco precedence (Slice 3).** Proposed: when both an `AssetPortfolio` and a
  flat `modco_interest_rate` are supplied, the asset book yield takes precedence
  and the flat rate is the fallback. Confirm before Slice 3.

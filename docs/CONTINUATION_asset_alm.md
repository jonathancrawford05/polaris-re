# Continuation: Asset / ALM model

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier-C **C0** (the
fourth epic, after the three Tier-A epics); ROADMAP Milestone 5.4.
**Status:** COMPLETE (all slices DONE — epic closed 2026-06-29, Slice 4b-4 / ADR-117)
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

##### Slice 4b-2a: reserve-backed liability stream + CLI rewire
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-q0t5sj (environment-designated)
- **PR:** (this PR)
- **What was done:** Implemented the maintainer-resolved **Option B** liability
  as a **reserve run-off (release) stream** — new
  `reserve_liability_cash_flows(result, reserve_valuation_rate)` in
  `analytics/alm.py`. With `R_t = reserve_balance[t]` (opening reserve `R_0`) and
  `a = (1 + reserve_valuation_rate)^(1/12)`: `L_t = R_t·a − R_{t+1}` (and
  `L_{T-1} = R_{T-1}·a`). Discounted at the reserve valuation rate this
  **telescopes exactly to `R_0`**, so PV ties to the held reserve. The CLI's
  `_price_single_cohort` now measures the gap against
  `reserve_liability_cash_flows(net, effective_valuation_rate)`. Both golden
  cohorts (TERM + WHOLE_LIFE) carry a positive reserve, so both now carry a
  block — the 4b-1 WHOLE_LIFE skip is resolved. ADR-113. 12 new analytics tests
  + the CLI tests updated.
- **Key decisions:**
  - **Basis-agnostic via the reserve series, not per-basis premiums.** The
    telescoping identity is purely algebraic, so it holds for NET_PREMIUM / CRVM
    / VM20 / GAAP from the held `reserve_balance` alone — no valuation-premium
    reconstruction, no product-engine change. End-to-end test confirms
    `PV(run-off) == reserve_balance[0]` on NET_PREMIUM / CRVM / VM20 at a reserve
    rate (3.5%) distinct from the discount rate (5%).
  - **Stream uses the reserve's valuation rate; duration uses the common yield.**
    `a` comes from `effective_valuation_rate`; `duration_measures` then discounts
    the fixed stream at the common ALM yield (ADR-111/112 default = `discount_rate`).
  - **Net side this slice.** The gap is measured on the retained (`net`) reserve —
    correct for the golden YRT path (YRT cedes no reserve, so `net` carries the
    full reserve). The explicit dual ceded (reinsurer-view, headline) + cedant
    block is 4b-2b with the API.
  - `liability_cash_flows` (the gross-premium stream) is retained as a
    benefit-outgo view; superseded only as the duration-gap liability.

##### Slice 4b-2b: reinsurer/cedant dual gap + API surface
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-b4y4g1 (environment-designated)
- **PR:** (this PR)
- **What was done:** Added `DualDurationGap` (reinsurer + cedant
  `DurationGapResult | None`, with `is_empty` / `headline` helpers) and
  `dual_duration_gap(portfolio, net_result, ceded_result, valuation_yield,
  reserve_valuation_rate)` to `analytics/alm.py`. It builds the reserve-backed
  run-off (ADR-113) from **each** side's `reserve_balance` and measures the same
  portfolio against both — the **reinsurer-view (ceded reserve)** is the headline,
  the **cedant-view (net reserve)** the secondary. Each side is computed
  independently and is `None` when its reserve is non-positive at the yield (YRT
  cedes no reserve → reinsurer side `None`; cedant carries the gap). The CLI's
  `CohortResult.alm_duration_gap` became a `DualDurationGap`; the JSON shape is now
  `{reinsurer, cedant}` (a new, non-golden output → goldens byte-identical), and
  the Rich renderer prints the reinsurer table first then the cedant. The REST
  `/api/v1/price` surface gained `asset_portfolio` + `alm_valuation_yield` on the
  request and `alm_duration_gap` on the response, reusing the **same**
  `dual_duration_gap` compute path (CLI↔API parity). ADR-114. New tests:
  `tests/test_analytics/test_alm.py` (dual-gap closed forms / None-side cases),
  `tests/test_cli_alm.py` (dual shape, YRT reinsurer-null, coinsurance both
  sides), `tests/test_api/test_main.py::TestPriceAlmDurationGap`.
- **Key decisions:**
  - **Same portfolio, two liabilities.** The supplied asset portfolio is measured
    against both the ceded and the retained reserve liability; the asset side is
    identical across the two, only the liability differs. Distinct cedant-held vs
    reinsurer-held asset portfolios are out of scope.
  - **Reinsurer-view is the headline; YRT reinsurer side is `None`.** For YRT the
    ceded reserve is ~0, so the reinsurer-side liability PV is non-positive and
    that side is `None`. `headline` falls back to the cedant side.
  - **CLI JSON shape decision:** a `{reinsurer, cedant}` pair under
    `alm_duration_gap` (not a flat headline + sibling) — both sides are
    first-class and either can be `None`.
  - **One common valuation yield (ADR-111) retained.** A per-side yield (asset
    book yield on the reinsurer side, discount rate on the cedant side) is a
    possible future refinement, harvested as NICE-TO-HAVE.

##### Slice 4b-3: dashboard + Excel presentation surfaces

Two distinct surfaces (interactive Streamlit dashboard + the machine-style Excel
committee packet). Consistent with how Slice 4b kept splitting into surface-sized
sub-slices (4b-1 CLI, 4b-2a/2b liability+API), this is split into **4b-3a** (the
Excel surface — self-contained, fully testable) and **4b-3b** (the dashboard
widget, which also carries the PR-#111 `to_dict()` carry-forward). The Excel
surface ships first.

###### Slice 4b-3a: ALM duration-gap sheet on the deal-pricing Excel workbook
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-j93iao (environment-designated)
- **PR:** (this PR)
- **What was done:** `DealPricingExport` gained an optional `alm_duration_gap:
  DualDurationGap | None = None`; the CLI's `_cohort_to_deal_pricing_export`
  threads `cohort.alm_duration_gap` onto it. `write_deal_pricing_excel` appends an
  "ALM Duration Gap" sheet (`_write_alm_duration_gap_sheet` / `_write_alm_gap_block`)
  when a non-empty dual gap is supplied: the reinsurer-view (ceded reserve —
  headline) block first, then the cedant-view (retained reserve) block, each side
  omitted when `None`, mirroring the CLI Rich `_render_alm_duration_gap` layout and
  labels exactly. Purely additive — no asset portfolio → no sheet → byte-identical
  workbooks. ADR-115. 9 writer tests + 3 end-to-end CLI `--excel-out` tests.
- **Key decisions:**
  - **Reuse `DualDurationGap`, no new export DTO.** The CLI already computes the
    dual gap per cohort; the writer only renders. One field, one translation site.
  - **Sheet appended last, gated on `not is_empty`.** Keeps every existing sheet's
    order and every pre-ADR-115 workbook byte-identical.
  - **YRT path renders the cedant side only** (ceded reserve ~0 → reinsurer side
    `None`), exactly as the console does.

###### Slice 4b-3b: dashboard asset-portfolio input + duration-gap display
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-8vngcl (environment-designated)
- **PR:** (this PR)
- **Depends on:** Slice 4b-3a merged (PR #114, on main)
- **What was done:** The Streamlit **Deal Pricing** page gains an optional
  "Asset-Liability Duration Gap" expander: an `AssetPortfolio` JSON text area
  (same `{"bonds": [...]}` shape as the CLI `deal.asset_portfolio` config) and an
  ALM valuation-yield input (0 → deal `discount_rate`). `_run_pricing_for_cohort`
  gained `asset_portfolio` / `alm_valuation_yield` params and, when a portfolio is
  supplied, calls the **same** `dual_duration_gap(... net, ceded ...,
  config.effective_valuation_rate)` path the CLI/API use; the result is stored on
  a new `CohortPricingData.alm_duration_gap` field and rendered by
  `_render_alm_duration_gap` (reinsurer-view headline first, then cedant-view; a
  `None` side omitted), mirroring the CLI Rich layout/labels. Purely additive — no
  pasted portfolio → no gap block → byte-identical page. The **PR-#111
  carry-forward** is discharged: `DealConfig.to_dict()` now carries
  `asset_portfolio` / `alm_valuation_yield` (default `None`). ADR-116. 7 tests
  driving `_run_pricing_for_cohort` directly.
- **Key decisions:**
  - **Wire, don't reimplement.** A test asserts the dashboard gap is
    byte-identical to a direct `dual_duration_gap` call on the cohort's own
    net/ceded results — the page only surfaces the analytics.
  - **Invalid JSON → no asset side, never aborts.** A bad payload shows an error
    and is treated as "no portfolio"; the block is omitted and pricing proceeds.
  - **Per-run input.** The asset side is a per-run JSON paste (not a persisted
    file-upload widget like the YRT rate table); a saved-portfolio affordance is a
    possible follow-up.

##### Slice 4b-4: ALM validation notebook
- **Status:** DONE
- **Branch:** claude/awesome-bardeen-gdhqzd (environment-designated)
- **PR:** (this PR)
- **Depends on:** Slice 4b-3b merged (PR #115, on main)
- **What was done:** Added `notebooks/04_alm_duration_gap.ipynb` — the epic's
  end-to-end validation notebook. It builds a seasoned whole-life block, cedes
  50% on **coinsurance** (so both `DualDurationGap` sides are defined — more
  illustrative than the golden YRT path, whose reinsurer side is `None`), sizes a
  backing bond portfolio to the ceded reserve, and reports the dual gap via the
  **same** `dual_duration_gap` path the four surfaces use. It then reconciles four
  closed forms: (1) the reserve run-off telescopes to the opening reserve
  (ADR-113); (2) zero-coupon Macaulay = `N` yr, modified = `N/(1+y)`, convexity =
  `N(N+1)/(1+y)²`; (3) `duration_measures` on the portfolio's own cash flows
  reproduces the portfolio API exactly (wire-not-reimplement); (4) a perfectly
  matched block has an exactly-zero gap. A closing section demonstrates
  immunisation (lengthening the assets shrinks the reinsurer-side gap ~10×, from
  −8.93 to −0.87 yr). A pytest guard
  (`tests/test_notebooks/test_alm_duration_gap_notebook.py`) execs the notebook's
  code cells, so the embedded reconciliations run in CI. ADR-117. Purely additive
  — no `src/` change, goldens byte-identical.
- **Key decisions:**
  - **Self-contained synthetic Gompertz mortality** (`q_x = 0.0004·1.09^(x-18)`)
    rather than a converted SOA/CIA table: flat mortality builds essentially no
    whole-life reserve (level net premium funds a constant hazard), and a data-file
    dependency would couple the notebook to the standing SOA-conversion failure.
    Matches the self-contained pattern of notebooks 01–03.
  - **The notebook is its own test.** `nbclient`/`nbconvert` are not project deps,
    so the guard reads the `.ipynb` with `nbformat` and `exec`s its (magic-free)
    code cells in one namespace — reproducing a kernel run. The closed-form checks
    live in the cells as `assert` / `assert_allclose`, so notebook drift fails CI.
  - **Coinsurance, not the golden YRT block.** The plan said "duration gap on the
    golden block"; a coinsurance cession was chosen instead so both reinsurer and
    cedant sides are defined (the golden config is YRT → reinsurer side `None`),
    giving a fuller validation. The closed-form reconciliations are
    block-independent (algebraic), so this strengthens rather than weakens the
    validation.

## Canonical liability cash-flow stream — RESOLVED (maintainer, 2026-06-27)

Surfaced concretely by 4b-1: the 4b-1 liability stream (`liability_cash_flows` =
`death_claims + lapse_surrenders + expenses − gross_premiums`, measured on the
cedant-retained `net` result) has a **non-positive PV for premium-paying /
reserve-building blocks** (the golden WHOLE_LIFE cohort, even at 6%), because it
subtracts **gross** (loaded, actual-charged) premiums — a pricing/profit stream,
not the valuation liability. So 4b-1's duration gap is defined only for
run-off-shaped blocks (TERM) and is gracefully skipped otherwise. The maintainer
settled the convention (2026-06-27); **4b-2 implements it**:

1. **Both sides, reinsurer-view is the headline.** Compute the duration gap on
   both the **ceded (reinsurer-view)** and the cedant-retained (`net`) liability;
   the **reinsurer-side** gap is the focus/headline (Polaris is a reinsurer tool;
   the epic goal is "the net reinsurer position" — the reinsurer's assets back
   the **ceded** reserves). 4b-1's net-only placeholder is superseded.
2. **Option B — reserve-backed liability (net valuation premiums).** The
   liability stream is benefits + expenses − **net / valuation** premiums (NOT
   gross premiums), so its present value ties to the **reserve**. This makes the
   duration defined for any block carrying a positive reserve; the graceful skip
   becomes a true edge case rather than the common path.
3. **Follow the deal's reserve basis.** Derive the liability on the deal's
   selected `reserve_basis` (NET_PREMIUM / CRVM / VM20 / GAAP) — the assets back
   the **held** reserve, so the duration must reflect the held basis.
4. **Common valuation yield default unchanged.** Both sides stay discounted at
   one common yield, defaulting to the deal `discount_rate` (isolates the timing
   mismatch); the explicit `alm_valuation_yield` override is retained.

**Implementation note for 4b-2.** This redefines the liability stream in
`analytics/alm.py` — `liability_cash_flows` (or a successor that takes the
valuation/net-premium stream and a side selector) is an **analytics-contract
change**, not just an API surface. Because it changes what 4b-1's CLI emits (the
`alm_duration_gap` block is a *new*, non-golden output, so revising it is
permitted and should be documented), 4b-2 updates the CLI call site too. Given
the scope (redefine the stream + reserve-basis-aware + both sides + closed-form
tests + the API surface + CLI rewire), 4b-2 may itself warrant a split — e.g.
**4b-2a** = reserve-backed liability stream in `analytics/alm.py` (+ CLI rewire,
closed-form tests: PV(liability) == reserve on each basis) and **4b-2b** = the
REST `/api/v1/price` surface mirroring it. The 4b-2 session decides the split
once it has read the reserve/net-premium plumbing.

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

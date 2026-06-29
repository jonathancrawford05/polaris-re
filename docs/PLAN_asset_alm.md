# Plan — Asset / ALM model (Epic 4 / Tier-C C0)

> **Audience.** A new Claude Code session that will carry this epic across
> several daily-dev runs. Read this document fully before writing code, then
> read CLAUDE.md, ARCHITECTURE.md (§4 "Reserve Calculation", §5 "Modco
> Treaty"), and DECISIONS.md. This plan is the read-only spec; the running log
> lives in `docs/CONTINUATION_asset_alm.md`, the per-session
> `docs/DEV_SESSION_LOG_*` files, and the ADRs.
>
> **Status.** 🔄 IN PROGRESS — Slices 1–3 shipped (Slice 1: bond cash-flow
> model + `AssetPortfolio`, ADR-108; Slice 2: book yield, investment income,
> duration / convexity, ADR-109; Slice 3: asset-driven modco interest,
> ADR-110). Slice 4 (ALM analytics + surfacing) was re-decomposed into **4a**
> (the `analytics/alm.py` duration-gap core, ADR-111 — SHIPPED) and **4b** (the
> CLI/API/dashboard/Excel surfacing + validation notebook). 4b itself proved
> too large for one session (five surfaces + a notebook), so it is further
> re-decomposed into **4b-1** (CLI input + duration-gap output, ADR-112 —
> SHIPPED), **4b-2a** (reserve-backed Option-B liability stream + CLI rewire,
> ADR-113 — SHIPPED), **4b-2b** (reinsurer/cedant dual gap + API surface,
> ADR-114 — SHIPPED), **4b-3a** (Excel ALM sheet, ADR-115 — SHIPPED), **4b-3b**
> (dashboard ALM input + display, ADR-116 — SHIPPED), and **4b-4**
> (validation notebook — NEXT). No prior
> asset/ALM code existed before this epic.
> Running log: `docs/CONTINUATION_asset_alm.md`.
>
> **Source.** `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-C item
> **C0** (★★★★☆ value, ~20 dev-days, 4 phases) and ROADMAP Milestone 5.4
> "Asset / ALM Model". Scheduled as the **fourth epic**, after the three
> Tier-A credibility/market-access epics (A1 reserve-basis, A2 IFRS 17
> movement, A3 cross-jurisdiction capital), all of which shipped by
> 2026-06-26. Per the review §4: "Run it as a fourth epic once the three
> credibility/market-access gaps are closed."

---

## 1. Goal

Give Polaris RE an asset side. Today the engine is liability-only: Modco
prices the modco interest on a single flat `modco_interest_rate`, there is no
investment-income model, and no duration/convexity or asset-liability
duration-gap analysis exists. A reinsurer pricing a Modco or coinsurance deal
needs to know what the assets backing the ceded reserves actually earn and how
their interest-rate sensitivity compares to the liability — that is the
difference between an *approximate* and a *correct* Modco economic result, and
it is the foundation of any embedded-value or ALM story.

When complete the engine can:

- Model a portfolio of fixed-income instruments (bonds): project their
  coupon + principal cash flows on the monthly grid, and price them at a yield.
- Compute the investment income those assets throw off against a reserve
  balance, and the portfolio's Macaulay / modified duration and convexity.
- Drive the Modco treaty's modco interest from an `AssetPortfolio`'s book
  yield instead of a flat rate (optional; the flat-rate path stays the
  default and byte-identical).
- Report an asset-liability **duration gap** on the net reinsurer position.

## 2. Why this work, and what it does NOT do

**Why.** Modco profitability depends on the return on the assets backing the
ceded reserves; without an asset model that return is a single hand-set
number. The review ranks the Asset/ALM model the top *post-Tier-A* big rock —
high value, but deliberately scheduled after the three credibility epics
because Modco is usable on a fixed credited rate today.

**Does NOT.**

- It does **not** introduce stochastic interest-rate generators
  (Hull-White / CIR). ROADMAP 5.4 lists integration with `analytics/stochastic.py`
  for reinvestment yields; that is a *follow-up*, not in this epic's core
  scope. Slice 1–4 work on a flat / book yield. Stochastic reinvestment is a
  harvested follow-up.
- It does **not** change any default pricing number. The Modco flat-rate path
  stays the default; goldens are byte-identical until the final surfacing
  slice, and even then only when an `AssetPortfolio` is explicitly supplied.
- It does **not** model equities, mortgages, or other non-fixed-income asset
  classes. Bonds (coupon + principal) only in this epic.
- It does **not** add asset default / credit-migration modelling (that is the
  C-1 capital component's domain, already in `analytics/capital.py`).

## 3. Decomposition (4 slices)

Each slice leaves all tests green, is independently mergeable, has its own
closed-form tests, and keeps the goldens byte-identical until the final
surfacing slice.

### Slice 1 — Bond cash-flow model + `AssetPortfolio`  ✅ SHIPPED
- `core/asset.py`: `Bond` (`PolarisBaseModel`) — a single fixed-income
  instrument valued on the monthly grid (`face_value`, `coupon_rate`,
  `coupon_frequency`, `term_months`, optional `book_value`).
  - `Bond.cash_flow_vector(months)` → `(months,)` float64 coupon + principal.
  - `Bond.price(annual_yield)` → PV at the engine's effective-annual monthly
    discounting (`v = (1+y)^(-1/12)`, matching `CashFlowResult.pv_*`).
- `AssetPortfolio` (`PolarisBaseModel`) holding a list of `Bond`s with
  `cash_flow_vector(months)`, `market_value(annual_yield)`, `book_value`,
  `total_face_value`.
- **Closed-form tests**: par bond (coupon = yield, annual-pay) prices to par;
  zero-coupon price = `face·(1+y)^(-N/12)`; coupon timing on the monthly grid;
  portfolio aggregation = sum of constituents; field validation
  (`coupon_frequency` must divide 12, positive face/term).
- Exported from `polaris_re.core`. ADR-108. Goldens byte-identical (new
  module, nothing wired into pricing).

### Slice 2 — Investment income + duration / convexity  ✅ SHIPPED
- `AssetPortfolio.investment_income(reserve_vector, ...)` → monthly investment
  income on the asset book yield (the number Modco needs).
- `AssetPortfolio.book_yield()` — **gross** IRR of carrying value vs cash flows,
  via `scipy.optimize.brentq` with a sign-change guard (returns `None` when no
  sign change); a **scalar held flat** (see §5). Plus `macaulay_duration(yield)`,
  `modified_duration(yield)`, `convexity(yield)`.
- **Closed-form tests**: duration of a zero = its term; modified duration =
  Macaulay/(1+y); a textbook convexity value; investment income on a flat
  book yield = `reserve · yield / 12`; `book_yield()` of a par book recovers the
  coupon yield.
- Still additive → goldens byte-identical.

### Slice 3 — Modco integration  ✅ SHIPPED
- `reinsurance/modco.py`: `ModcoTreaty.apply()` accepts an optional
  `AssetPortfolio`; when supplied the modco interest is driven by the asset
  **book yield** (Option A precedence, §5) on the (notional) ceded reserve
  rather than the flat `modco_interest_rate`. Default `None` preserves the
  current flat path exactly → goldens byte-identical.
- **Tests**: asset-driven modco interest closed-form vs a worked example;
  NCF additivity (net + ceded = gross) still holds; default (no-portfolio) path
  unchanged.
- ADR recording all three resolved decisions (§5): gross-flat book yield,
  deterministic reinvestment, Option-A precedence.

### Slice 4 — ALM analytics + surfacing

Re-decomposed into 4a (core) + 4b (surfacing) — the new module plus five
surfaces + a notebook is more than one session (same split as Epic 3's 4c).

#### Slice 4a — `analytics/alm.py` duration-gap core  ✅ SHIPPED
- `analytics/alm.py`: `duration_measures` (PV + Macaulay / modified duration of
  any cash-flow stream), `liability_cash_flows` (net benefit outgo from a
  `CashFlowResult`), and `duration_gap` → `DurationGapResult` (asset vs
  liability duration, duration gap, dollar-duration gap; both sides at one
  common flat valuation yield).
- **Closed-form tests**: bullet duration `= N/12` years; modified `=
  Macaulay/(1+y)`; reproduces the `AssetPortfolio` duration API; matched block
  → zero gap; gap sign tracks relative term; non-positive PV raises.
- ADR-111. Additive → goldens byte-identical.

#### Slice 4b — surfacing + validation notebook
- Surface the asset/ALM block on CLI / API / dashboard / Excel as appropriate,
  plus a validation notebook.
- This is the slice that *can* move goldens — and only for runs that supply an
  asset portfolio. Document any regenerated baselines with the reason.
- Re-decomposed into surface-sized sub-slices (five surfaces + a notebook is
  more than one session, same split as Epic 3's 4c):
  - **4b-1 — CLI input + duration-gap output ✅ SHIPPED (ADR-112).** Optional
    `deal.asset_portfolio` + `deal.alm_valuation_yield` config input; per-cohort
    `alm_duration_gap` JSON key + Rich table. Purely additive (default `None` →
    byte-identical goldens); a cohort with a non-positive liability PV is
    skipped, never aborting the run. Surfaced the open canonical-liability-stream
    question concretely (golden WHOLE_LIFE skipped at 6%).
  - **4b-2a — reserve-backed Option-B liability stream + CLI rewire ✅ SHIPPED
    (ADR-113).** `reserve_liability_cash_flows` derives the liability as the
    reserve run-off (release) stream, so PV ties to the held reserve;
    basis-agnostic (the telescoping identity holds for NET_PREMIUM / CRVM / VM20 /
    GAAP from `reserve_balance` alone). CLI gap rewired onto it on the retained
    (`net`) reserve. Both golden cohorts now carry a block (the 4b-1 WHOLE_LIFE
    skip resolved); the skip is now a non-positive-opening-reserve edge case.
  - **4b-2b — reinsurer/cedant dual gap + API surface ✅ SHIPPED (ADR-114).**
    `DualDurationGap` + `dual_duration_gap` measure the same portfolio against both
    the ceded (reinsurer-view, headline) and cedant-retained reserve liabilities;
    YRT reinsurer side is `None` (ceded reserve ~0). CLI `alm_duration_gap` is now
    a `{reinsurer, cedant}` block; `/api/v1/price` gained `asset_portfolio` +
    `alm_valuation_yield` (request) and `alm_duration_gap` (response), reusing the
    CLI compute path for parity.
  - **4b-3 — dashboard + Excel presentation surfaces.** Two surfaces; split
    surface-sized (same pattern as 4b-1/4b-2):
    - **4b-3a — ALM duration-gap sheet on the deal-pricing Excel workbook ✅
      SHIPPED (ADR-115).** `DealPricingExport.alm_duration_gap`; the CLI threads
      `cohort.alm_duration_gap` onto it; `write_deal_pricing_excel` appends an
      "ALM Duration Gap" sheet (reinsurer-view headline first, then cedant-view,
      each side omitted when `None`) mirroring the CLI Rich block. Additive — no
      asset portfolio → no sheet → byte-identical workbooks.
    - **4b-3b — dashboard asset-portfolio input + duration-gap display ✅
      SHIPPED (ADR-116).** The Streamlit Deal Pricing page gains an optional
      `AssetPortfolio` JSON input + ALM valuation-yield, computes the gap via the
      same `dual_duration_gap` path (stored on `CohortPricingData.alm_duration_gap`,
      rendered reinsurer-headline-first by `_render_alm_duration_gap`), and
      discharges the PR-#111 `DealConfig.to_dict()` carry-forward (both ALM fields
      now in `to_dict`). Additive — no pasted portfolio → byte-identical page.
  - **4b-4 — ALM validation notebook (NEXT).**

## 4. Key constraints (from CLAUDE.md / ARCHITECTURE.md)

- Vectorised: cash-flow vectors and income are `(T,)` numpy with explicit
  `float64`; no per-instrument Python loops in hot paths beyond the small bond
  list (the bond list is analogous to the policy list — aggregate into arrays).
- Every actuarial / financial formula gets a closed-form verification test.
- No `Optional` / `List`; Python 3.12 typing. `float64` for monetary arrays,
  `int32` for counts/terms where stored as arrays.
- Discounting MUST match the engine convention (`v = (1+y)^(-1/12)`,
  cash flow at month t discounted by `v^t`, 1-indexed end-of-month) so a bond
  PV and a `CashFlowResult` PV are on the same basis.
- Modco integration (Slice 3) keeps the flat-rate default byte-identical and
  preserves the NCF additivity proof in ARCHITECTURE §5.
- Do not hardcode yields in product/treaty code — they flow in via the
  `AssetPortfolio` / treaty config (CLAUDE.md §10 "Never hardcode assumptions").

## 5. Resolved design decisions (maintainer-confirmed 2026-06-26)

These were the epic's open design questions; all three are now settled. They
are recorded here as the binding spec and will be captured in an ADR when
Slice 3 lands.

- **Book yield definition (Slice 2) — RESOLVED.** `book_yield()` is the **gross**
  IRR of carrying value vs the projected asset cash flows, solved with
  `scipy.optimize.brentq` (the profit tester's solver) behind a sign-change
  guard (return `None` when no sign change, as `ProfitTester.irr` does). It is a
  **scalar held flat** over the horizon — not a weighted-average-coupon proxy and
  not (yet) a time-varying amortising earned rate. *Future refinements
  (follow-ups, not this epic):* a **net-of-spread** earned rate (net down for an
  investment-expense / default margin — kept distinct from the C-1 capital
  component so asset-default risk is not double-counted) and a **time-varying**
  earned rate recomputed as the portfolio amortises. Both are harvested to
  PRODUCT_DIRECTION as NICE-TO-HAVE.
- **Reinvestment (Slice 2/3) — RESOLVED.** Epic 4 is deterministic: the book
  yield **is** the (flat) reinvestment yield, so asset cash flows arriving before
  the liability needs them roll forward at the book yield, self-consistently.
  Stochastic reinvestment (Hull-White / CIR via `analytics/stochastic.py`) is an
  explicit out-of-scope follow-up (see §2), already harvested as NICE-TO-HAVE.
- **Modco precedence (Slice 3) — RESOLVED (Option A).** When both an
  `AssetPortfolio` and a flat `modco_interest_rate` are supplied, the **asset
  book yield takes precedence** and the flat rate is the fallback. Omitting the
  portfolio leaves the flat-rate path exactly as today → goldens byte-identical.
  NCF additivity (ARCHITECTURE §5) holds regardless of the rate source, since
  `modco_interest` cancels between the net and ceded sides. Recorded in an ADR
  when Slice 3 lands.
- **Canonical liability cash-flow stream (Slice 4b) — RESOLVED (maintainer,
  2026-06-27).** Slice 4b-1 surfaced that its placeholder liability stream
  (benefits + expenses − **gross** premiums, on the cedant-retained side) has a
  non-positive PV for premium-paying / reserve-building blocks (golden
  WHOLE_LIFE), so its duration gap is undefined and skipped. The resolved
  convention, implemented in Slice 4b-2: (1) compute the gap on **both** sides
  with the **ceded (reinsurer-view)** side as the headline (Polaris is a
  reinsurer tool; the reinsurer's assets back the ceded reserves); (2) **Option
  B** — the liability is benefits + expenses − **net / valuation** premiums, so
  its PV ties to the **reserve**; (3) derive it on the deal's **`reserve_basis`**
  (NET_PREMIUM / CRVM / VM20 / GAAP); (4) keep the single common valuation yield
  defaulting to `discount_rate`. Recorded in ADR-112; running plan in
  `docs/CONTINUATION_asset_alm.md`. **Status:** the `analytics/alm.py`
  contract change split into **4b-2a — SHIPPED (ADR-113):**
  `reserve_liability_cash_flows`, the reserve run-off (release) stream whose PV
  ties to the held reserve. The implementation realises Option B via the
  **reserve-runoff identity** rather than reconstructing net/valuation premiums
  per basis: the stream is `L_t = R_t·a − R_{t+1}` from `reserve_balance` alone,
  which telescopes to the opening reserve for *any* reserve series — so it is
  basis-agnostic (point 3 holds without per-basis premium logic). 4b-2a rewired
  the CLI gap onto it on the cedant-retained (`net`) reserve; the **dual
  reinsurer/cedant headline (point 1) + the API surface are 4b-2b (NEXT).**

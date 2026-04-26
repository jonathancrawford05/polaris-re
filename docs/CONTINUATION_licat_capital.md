# Continuation: LICAT Regulatory Capital and Return-on-Capital

**Source:** PRODUCT_DIRECTION_2026-04-19.md — BLOCKER (item #5 in
Recommended Next Sprint, "LICAT regulatory capital (Milestone 5.1
kick-off)")
**Status:** IN PROGRESS
**Total slices:** 3
**Estimated total scope:** ~4 dev-days

## Overall Goal

Give Polaris RE a regulatory-capital module so reinsurer deal evaluation
can report **return-on-required-capital (RoC)**, not just IRR vs hurdle.
A pricing actuary cannot defend a deal at committee on IRR alone — the
question "what RoC does this generate, and is it above our 8-12%
cost-of-capital?" is the gating quantitative test for treaty
acceptance. The feature adds a `LICATCapital` calculator that produces a
required-capital schedule from a `CashFlowResult`, extends `ProfitTester`
with `run_with_capital(capital_model)` that joins capital and profit into
a `ProfitResultWithCapital`, and surfaces the result via the CLI flag
`polaris price --capital licat`, the `/api/v1/price` endpoint, and the
deal-pricing Excel workbook.

## Decomposition

### Slice 1: Standalone `LICATCapital` calculator + factor model
- **Status:** DONE (this session)
- **Branch:** `claude/blissful-volta-1rFMe`
- **PR:** (draft; opened by this session)
- **What was done:**
  - Added `src/polaris_re/analytics/capital.py` with three public
    symbols: `LICATFactors` (Pydantic frozen — `c2_mortality_factor`,
    `c1_asset_default`, `c3_interest_rate`), `CapitalResult`
    (dataclass holding c1/c2/c3 component arrays + aggregate +
    initial/peak scalars + `pv_capital(rate)`), and `LICATCapital`
    (factor-based calculator with `for_product(ProductType)` factory
    and `required_capital(cashflows, nar=None)` method).
  - Default C-2 factors per product type calibrated to approximate
    the OSFI 2024 LICAT mortality shock for an individual life book:
    TERM 0.15, WHOLE_LIFE 0.10, UL 0.08, DI 0.05, CI 0.05, ANNUITY
    0.03. C-1 and C-3 are zero stubs.
  - NAR resolution: explicit `nar=` override → `cashflows.nar` (set
    by YRT treaty) → `PolarisComputationError`. CEDED basis rejected.
  - `analytics/__init__.py` re-exports the three new symbols and
    keeps `__all__` alphabetical.
  - ADR-047 added to `docs/DECISIONS.md`.
  - 31 tests added: factor validation (4), product-type defaults (7
    parametrised + 1), closed-form C-2 formula (6), NAR resolution
    (4), basis acceptance (3), `CapitalResult` shape/dtype/pv (4),
    OSFI factor verification (2), module exports (1). Full suite is
    now 757 non-slow (up from 726); QA suite 33/33; ruff format and
    check both clean.
- **Acceptance criteria:**
  - Factor model is hand-verifiable: `c2 = factor × NAR` for known
    inputs (TERM 1M NAR @ 0.15 = 150K; WL 2M NAR @ 0.10 = 200K). ✅
  - Per-product defaults exposed via `for_product(...)`. ✅
  - C-1 and C-3 stubs return zero arrays. ✅
  - NAR sourced from `cashflows.nar` or explicit override. ✅
  - CEDED basis rejected. ✅
  - Existing 726 non-slow tests still pass; QA suite 33/33; golden
    baselines unchanged because the new module is not yet wired into
    any pricing path. ✅
  - ADR-047 written. ✅
- **Key decisions that affect later slices:**
  - **Capital is held against retained business.** GROSS and NET
    accepted; CEDED rejected. When wiring into ProfitTester (Slice
    2), the `run_with_capital` call sites should pass NET (post-
    treaty) cashflows for the cedant view and the reinsurer-view
    cash flows (CEDED relabelled via `ceded_to_reinsurer_view`) for
    the reinsurer.
  - **NAR from CashFlowResult.nar is the canonical source.** YRT
    treaty already populates this. Slice 2 must decide what to do
    for non-YRT (gross / coinsurance / modco / stop-loss) runs:
    either derive NAR = face_in_force - reserve_balance (which
    requires adding `face_in_force` to CashFlowResult — a contract
    change that warrants the CLAUDE.md guard rail) OR pass an
    explicit `nar=` from the InforceBlock at the ProfitTester
    `run_with_capital` call site. Default in Slice 2 should be the
    explicit-pass route to avoid the contract change on this slice.
  - **Capital is NOT discounted at the hurdle rate inside the
    calculator.** The capital schedule is a stock value; time-value
    adjustments live in the RoC metric (Slice 2). Slice 2 must
    document whether RoC denominator is `pv_capital` (stock) or
    PV(capital strain) (incremental); industry practice varies, and
    the choice is one of the open questions for Slice 2.
  - **The factor-based model is a v1 placeholder.** The roadmap
    notes a shock-based mortality stress (OSFI 2024 LICAT
    mortality risk component) as the eventual implementation. The
    `LICATCapital` interface is intentionally narrow so a v2 shock
    engine can replace the factor formula without rewriting Slice 2
    or Slice 3 integrations.

### Slice 2: ProfitTester integration — `run_with_capital`
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create / modify:**
  - `src/polaris_re/analytics/profit_test.py` — add
    `ProfitResultWithCapital` dataclass extending `ProfitTestResult`
    with `peak_capital`, `pv_capital`, `return_on_capital`,
    `capital_adjusted_irr`. Add `ProfitTester.run_with_capital(
    capital_model: LICATCapital, *, nar: np.ndarray | None = None)
    -> ProfitResultWithCapital`. Existing `run()` unchanged.
  - `tests/test_analytics/test_profit_test.py` — extend with
    `TestProfitTesterWithCapital` covering RoC formula closed-form
    (PV profits / PV capital), capital-adjusted IRR shape, NAR
    explicit pass-through, no-NAR fallback raises with a clear
    message.
- **Tests to add (estimated 8-10):**
  - RoC = pv_profits / pv_capital for a known cash flow + capital
    schedule.
  - Doubling capital factor halves RoC (sensitivity).
  - `nar=` argument is plumbed correctly into `LICATCapital`.
  - `ProfitTestResult` fields are preserved (backward compatibility:
    callers that already use `run()` see no change).
  - Capital-adjusted IRR: deals where RoC < hurdle should not be
    flagged as profitable even if vanilla IRR > hurdle.
- **Acceptance criteria:**
  - `ProfitTester.run_with_capital(LICATCapital.for_product(TERM))`
    returns a `ProfitResultWithCapital` with non-None `peak_capital`,
    `pv_capital`, and `return_on_capital`.
  - Closed-form RoC test passes within float tolerance.
  - Existing `ProfitTester.run()` callers unaffected (regression
    guard: full suite still green without changes).
  - Golden baselines unchanged (the new code path is opt-in).

### Slice 3: CLI / API / Excel surfacing
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
- **Scope:**
  - `src/polaris_re/cli.py` — `polaris price --capital licat` flag.
    When present, each cohort's `cedant` and `reinsurer` profit
    results gain `peak_capital` / `pv_capital` /
    `return_on_capital` fields in the JSON output.
  - `src/polaris_re/api/main.py` — extend `PriceRequest` with an
    optional `capital_model: Literal["licat"] | None`; extend
    `PriceResponse` with `return_on_capital`.
  - `src/polaris_re/utils/excel_output.py` — extend the Summary
    sheet of `write_deal_pricing_export` to emit the RoC and Peak
    Capital rows when capital metrics are present in the
    `DealPricingExport`.
  - `src/polaris_re/dashboard/views/pricing.py` — RoC tile beside
    the existing IRR tile.
  - Tests covering CLI flag, API field round-trip, Excel cell
    placement, and dashboard render.
- **Acceptance criteria:**
  - `polaris price --inforce ... --config ... --capital licat -o
    out.json` produces JSON with `return_on_capital` populated for
    each cohort.
  - `POST /api/v1/price` with `capital_model="licat"` returns
    `return_on_capital`.
  - `polaris price --capital licat --excel-out deal.xlsx` Summary
    sheet shows the new rows.
  - Golden baselines unchanged when `--capital` is not supplied.

## Context for Next Session

- The Slice-1 calculator is **completely standalone** — it does not
  import `ProfitTester` or `pipeline`. Slice 2's `run_with_capital`
  is the integration boundary. Keep `LICATCapital` itself free of
  ProfitTester imports so a future shock-based v2 can replace the
  factor formula without rippling through the integration code.
- `CashFlowResult.nar` is currently populated **only by
  `YRTTreaty.apply` when `flat_yrt_rate_per_1000` is set** (see
  `src/polaris_re/reinsurance/yrt.py:117`). For non-YRT runs it is
  `None`. The Slice-1 calculator forces the caller to handle this
  via either an explicit `nar=` override or by ensuring the
  CashFlowResult comes from a YRT treaty. Slice 2 should pass NAR
  derived from the InforceBlock (`(inforce.face_amount_vec * lx).sum
  (axis=0)`) when the CashFlowResult lacks `nar`. The InforceBlock
  is in scope at `run_with_capital` call sites, so this is
  straightforward.
- The factor model treats C-2 as `factor × NAR`. For products with
  no NAR (e.g. annuities), the "NAR" passed in should be the
  reserve balance or a similar exposure measure — but the
  factor would then need to be re-calibrated. Defer the annuity
  case to a Phase-5.4-era shock-based engine; flag in PR if the
  reviewer asks.
- `pv_capital(rate)` discounts the entire capital STOCK at each
  monthly step. For RoC computation (Slice 2), pricing actuaries
  often prefer PV of capital STRAIN (period-over-period increases,
  representing the cost of capital tied up incrementally). Slice 2
  needs to add `CapitalResult.pv_capital_strain(rate)` or compute
  it inline; the choice between stock and strain is one of the
  open questions for Slice 2 — capture the rationale in ADR-048.
- The `LICATFactors` Pydantic model uses `Field(default=...)`; the
  `LICATCapital` factory pattern (`for_product`) returns frozen
  instances. Slice 3 CLI parsing should construct via the factory,
  not by passing factor floats directly, to keep the OSFI-defaults
  story consistent in the audit trail.

## Open Questions (for human)

1. **RoC denominator: stock (pv_capital) or strain (pv_capital_strain)?**
   Industry practice splits — Phase 5.1 of the roadmap doesn't
   prescribe. Slice 2 will default to **stock** (pv_capital with
   discount rate = hurdle rate) because it is the simpler, more
   widely cited definition. If the deal committee prefers strain,
   Slice 2 will add a parameter; document in ADR-048 either way.
2. **Should Slice 2 introduce `face_amount_in_force` on
   `CashFlowResult`?** **RESOLVED — NO** (PR #33 reviewer confirmed
   2026-04-25): do NOT expand the `CashFlowResult` contract for a
   stock variable in this phase. Slice 2 derives NAR at the
   `run_with_capital` call site from the InforceBlock (in scope) and
   passes it via the existing `nar=` override on
   `LICATCapital.required_capital`.
3. **C-1 and C-3 components.** Slice 1 stubs them at zero. Phase 5.4
   (asset / ALM model) will populate C-1 properly. C-3 needs
   integration with the stochastic-rate engine. For deal-committee
   credibility before Phase 5.4 lands, do we need an interim C-3
   factor (e.g., 1% of reserves) so the capital number isn't visibly
   incomplete? Default: leave at zero with a clear "not modelled"
   note in the PR description and the Excel Assumptions sheet.
4. **Lapse-risk and morbidity-risk components.** LICAT 2024 has
   separate factors for these. Slice 1 omits them. Adding them is a
   straight extension of the factor model — propose a Phase 5.1.b
   ADR after Slice 3 ships, since it doesn't change the ProfitTester
   integration surface.

## Resolved (PR #33 review, 2026-04-25)

- **Default C-2 factors per product type are accepted.** TERM 0.15,
  WL 0.10, UL 0.08, DI 0.05, CI 0.05, ANN 0.03 ship as the OSFI-aligned
  defaults; Slice 3 CLI / API surface uses these via
  `LICATCapital.for_product(...)`.
- **CEDED basis rejection is confirmed as a deliberate guardrail**,
  matching the ADR-039 pattern: cedant capital runs on NET; reinsurer
  capital runs on `ceded_to_reinsurer_view(ceded)` (which is GROSS-
  labelled). The CEDED rejection in `LICATCapital.required_capital`
  stays, and Slice 2's `run_with_capital` call sites must follow
  this convention.
- **No `face_amount_in_force` on `CashFlowResult`.** Open Q2 above is
  closed. Slice 2 derives NAR from the InforceBlock at the
  `run_with_capital` call site and passes it via `nar=`.

When all slices are DONE, update Status to COMPLETE.

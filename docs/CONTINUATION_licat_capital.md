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
- **Status:** DONE (this session, 2026-04-26)
- **Branch:** `claude/blissful-volta-CdNBB`
- **PR:** (draft; opened by this session)
- **What was done:**
  - Added `ProfitResultWithCapital` dataclass to
    `src/polaris_re/analytics/profit_test.py`, extending
    `ProfitTestResult` with `initial_capital`, `peak_capital`,
    `pv_capital`, `pv_capital_strain`, `return_on_capital`,
    `capital_adjusted_irr`, and `capital_by_period`.
  - Added `ProfitTester.run_with_capital(capital_model, *, nar=None)`
    which calls `self.run()`, then runs the capital model on
    `self.cashflows`, and joins the two into a
    `ProfitResultWithCapital`. RoC denominator is `pv_capital`
    (stock at the hurdle rate) per ADR-048; `pv_capital_strain` is
    surfaced for callers that prefer the incremental view.
  - Refactored IRR computation into a shared `_solve_irr(profits)`
    helper that mirrors the ADR-041 sign-change suppression and
    large-magnitude guard rail. `run()` continues to inline the
    same logic for backward-compat byte equality on the existing
    fields.
  - Capital-adjusted IRR uses distributable cash flow
    `net_cash_flow_t - strain_t` with terminal release of
    `capital[T-1]` at month T-1. Sum of strain telescopes to zero
    so the undiscounted profit total is unchanged.
  - Added `CapitalResult.capital_strain()` and
    `CapitalResult.pv_capital_strain(rate)` to
    `src/polaris_re/analytics/capital.py`. Strain is
    `capital_t - capital_{t-1}` with `capital_{-1} = 0` (no
    terminal release inside the calculator — `ProfitTester` adds
    it for the IRR computation).
  - `analytics/__init__.py` re-exports `ProfitResultWithCapital`;
    `__all__` re-sorted.
  - ADR-048 added to `docs/DECISIONS.md`.
  - 14 tests added in
    `tests/test_analytics/test_profit_test.py`:
    `TestProfitTesterWithCapital` (12) and
    `TestPvCapitalStrainClosedForm` (2). Full suite is now 771
    non-slow (up from 757); QA suite 33/33; ruff format and check
    both clean. Golden baselines unchanged because the new code
    path is opt-in.
- **Acceptance criteria:**
  - `ProfitTester.run_with_capital(LICATCapital.for_product(TERM))`
    returns `ProfitResultWithCapital` with non-None
    `peak_capital`, `pv_capital`, `return_on_capital`. ✅
  - Closed-form RoC test passes within float tolerance
    (`pv_profits / pv_capital` matches direct computation). ✅
  - Existing `ProfitTester.run()` callers unaffected (full suite
    still green; backward-compat field-preservation test
    explicit). ✅
  - Doubling C-2 factor halves RoC (sensitivity). ✅
  - Explicit `nar=` argument forwards to `LICATCapital`. ✅
  - Missing NAR raises a clear `PolarisComputationError`. ✅
  - Capital-adjusted IRR < vanilla IRR for a strained deal. ✅
  - `pv_capital_strain` for flat capital equals `K × v`. ✅
  - Golden baselines unchanged. ✅
  - `ProfitResultWithCapital` exported via
    `polaris_re.analytics`. ✅
- **Key decisions that affect Slice 3:**
  - **RoC denominator = stock (`pv_capital`).** Slice 3 should
    surface `return_on_capital` (the stock-based RoC) as the
    headline number on CLI / API / Excel. The strain measure is
    available on `ProfitResultWithCapital.pv_capital_strain` if a
    secondary tile is desired.
  - **`run_with_capital` is opt-in.** Slice 3 must add the
    `--capital licat` CLI flag and the `capital_model` API field
    that gates the call. Existing pipeline paths remain on
    `tester.run()` until the flag is set.
  - **NAR is sourced at the call site.** For coinsurance / modco /
    no-treaty runs the `CashFlowResult.nar` is None; Slice 3 must
    derive NAR from the InforceBlock at the call site (e.g.
    `(inforce.face_amount_vec * lx_vec).sum(axis=0)` or a
    cession-aware equivalent) and pass it via `nar=`. For YRT runs
    the existing `cashflows.nar` populated by `YRTTreaty.apply`
    flows through automatically.
  - **`ProfitResultWithCapital` preserves all
    `ProfitTestResult` fields.** Slice 3's CLI / API / Excel
    serialisation can branch on `isinstance(result,
    ProfitResultWithCapital)` to decide whether to emit the
    capital block, with no changes to existing serialisation
    code.

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
    `DealPricingExport`. Per PR #34 reviewer: also surface
    `pv_capital_strain` as a secondary advisory metric on the
    Excel workbook (primary RoC denominator stays stock).
  - `src/polaris_re/dashboard/views/pricing.py` — RoC tile beside
    the existing IRR tile.
  - Tests covering CLI flag, API field round-trip, Excel cell
    placement, and dashboard render.
- **NAR-derivation formula at the call site (PR #34 reviewer
  guidance, 2026-04-26):** at each Slice-3 call site that builds
  the `nar=` kwarg, compute

      nar_t = max((face_amount_vec * lx_vec).sum(axis=0) - reserve_t, 0.0)

  where `lx_vec` is the in-force factor matrix from the projection.
  For coinsurance / modco NET runs, scale the face term by
  `(1 - cession_pct)` so the retained NAR matches the NET cashflow
  basis:

      nar_t_net = max(((1 - cession_pct) * face_amount_vec * lx_vec).sum(axis=0)
                      - reserve_t, 0.0)

  Both are one-line changes at the call site; the `LICATCapital`
  module itself is unchanged. YRT runs continue to use
  `cashflows.nar` (already populated by `YRTTreaty.apply`) and skip
  the explicit derivation.
- **Acceptance criteria:**
  - `polaris price --inforce ... --config ... --capital licat -o
    out.json` produces JSON with `return_on_capital` populated for
    each cohort.
  - `POST /api/v1/price` with `capital_model="licat"` returns
    `return_on_capital`.
  - `polaris price --capital licat --excel-out deal.xlsx` Summary
    sheet shows the new rows (RoC, Peak Capital, advisory
    pv_capital_strain).
  - Coinsurance/modco NET runs use the cession-aware NAR formula
    above; YRT runs use `cashflows.nar` unchanged.
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
   **RESOLVED — Stock** (Slice 2 / ADR-048, 2026-04-26): default
   `return_on_capital = pv_profits / pv_capital`, where `pv_capital`
   discounts capital balances at the hurdle rate. The strain
   measure is exposed on `ProfitResultWithCapital.pv_capital_strain`
   and `CapitalResult.pv_capital_strain(rate)` for callers that
   prefer it; a future ADR can flip the default if firm policy
   evolves.
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

## Resolved (PR #34 review, 2026-04-26)

- **RoC denominator stays PV(capital STOCK).** Reviewer confirmed the
  default matches firm reporting convention. Slice 3 may surface
  `pv_capital_strain` as an advisory metric on the Excel workbook;
  the primary RoC denominator does not change.
- **Capital-adjusted IRR construction confirmed.** The
  distributable-cash-flow-with-terminal-release formulation
  (`net_cash_flow_t - strain_t` plus terminal release of
  `capital[T-1]`) is the correct approach. The frictional
  cost-of-capital alternative
  (`net_cash_flow_t - capital_t × hurdle / 12`) introduces hurdle-rate
  circularity and is inappropriate for a deal-level IRR metric. The
  CONTINUATION note about that variant stays for future reference but
  no implementation work is planned.
- **Slice 3 NAR-derivation formula** — see the formula block in the
  Slice 3 section above. Two amendments to the original
  `(face × lx).sum()` plan: (1) subtract `reserve_balance` and floor
  at zero; (2) scale face by `(1 − cession_pct)` for coinsurance/modco
  NET runs so the retained NAR matches the NET cashflow basis. Both
  are one-line changes at the call site; the `LICATCapital` module
  itself is unchanged.

When all slices are DONE, update Status to COMPLETE.

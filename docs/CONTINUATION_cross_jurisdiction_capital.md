# Continuation: Cross-jurisdiction regulatory capital (US RBC + Solvency II)

**Source:** PRODUCT_DIRECTION_2026-06-18.md — IMPORTANT (Tier-A A3); plan in
`docs/PLAN_cross_jurisdiction_capital.md`; selected per
`COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier-A A3.
**Status:** IN PROGRESS
**Total slices:** 4
**Estimated total scope:** ~15 dev-days (US RBC ~8 d, Solvency II SCR ~7 d)

## Overall Goal

Add the US (NAIC RBC) and EU (Solvency II SCR) regulatory capital standards as
siblings of the existing Canadian `LICATCapital`, all three plugging into a
shared `CapitalModel` protocol so `ProfitTester.run_with_capital` and every
downstream return-on-capital surface can quote a deal under whichever
jurisdiction the cedant files. This closes the market-access gap that today
limits return-on-capital pricing to Canadian deals.

## Decomposition

### Slice 1: US RBC core module + `CapitalModel` protocol
- **Status:** DONE
- **Branch:** `claude/awesome-bardeen-kp19mp` (environment-designated)
- **PR:** #92 (draft)
- **What was done:** Added `analytics/capital_base.py` (`CapitalModel` /
  `CapitalSchedule` structural protocols + `discount_stream` / `strain_of`
  helpers) and `analytics/rbc.py` (`RBCFactors`, `RBCResult`, `RBCCapital`)
  implementing the NAIC Life RBC C-0…C-4 component model with the covariance
  square-root aggregation, ACL/CAL, and `rbc_ratio`. `for_product` factor
  defaults (C-1o / C-2 / C-3a non-zero). 33 closed-form tests. ADR-098.
- **Key decisions:**
  - The shared protocols are **structural** — the pre-existing `LICATCapital` /
    `CapitalResult` conform without modification (locked by `isinstance` tests).
  - `capital_by_period` is the **Company Action Level** (covariance result);
    ACL (= ½ CAL) is exposed separately as the RBC-ratio denominator.
  - Factors are committee-stage approximations (NAIC C-2 first-tier 0.00150,
    C-3 Phase I categories, IG bond C-1o 1.0%), documented and overridable.
  - Goldens byte-identical (new modules, nothing wired into the pricing path).

### Slice 2: RBC ↔ ProfitTester integration + RBC ratio
- **Status:** DONE
- **Branch:** `claude/awesome-bardeen-pedp9i` (environment-designated)
- **PR:** #98 (draft)
- **What was done:** Widened BOTH return-on-capital entry points —
  `ProfitTester.run_with_capital` (single deal) and `Portfolio.run_with_capital`
  (aggregate book) — from the concrete `LICATCapital` / `CapitalResult`
  annotations to the `CapitalModel` / `CapitalSchedule` protocols, re-pointing
  imports to `analytics.capital_base`. Type-only: neither body changed (both
  already used only the `CapitalSchedule` surface). `RBCCapital` now drives
  RoC / capital-strain / capital-adjusted-IRR for deals and portfolios. ADR-099.
- **Key decisions:**
  - **`ProfitResultWithCapital` left unchanged.** RBC's `authorized_control_level`
    and `rbc_ratio(tac)` (= TAC / ACL₀) live on the `RBCResult` the model returns,
    reachable via `capital_model.required_capital(cf)`. The RBC ratio needs an
    external TAC input `ProfitTester` does not hold, so a result-level RBC-ratio
    surface is deferred to Slice 4 (where a TAC / target-multiple input lands).
    Keeps the jurisdiction-agnostic result from accreting RBC-specific fields and
    keeps goldens byte-identical.
  - The **portfolio** path was pulled into this slice (identical one-line protocol
    widening) so RBC drives both RoC entry points consistently — not left as a
    second hard-typed seam.
- **Tests:** `TestProfitTesterWithRBCCapital` (7 — protocol conformance,
  RoC/strain/IRR populated, covariance-root RoC closed form, RBC-ratio TAC/ACL
  closed form, LICAT/RBC share the RoC formula, zero-factor→None RoC, LICAT
  schedule byte-for-byte unchanged) + `test_accepts_rbc_capital_model` on the
  portfolio path. Full fast suite 1569 passed; QA golden suite 72 green.

### Slice 3: Solvency II SCR module
- **Status:** DONE
- **Branch:** `claude/awesome-bardeen-ed43mz` (environment-designated)
- **PR:** #99 (draft)
- **What was done:** Added `analytics/solvency2.py` — `SolvencyIIFactors`,
  `SolvencyIIResult`, `SolvencyIICapital` — implementing the Solvency II
  standard-formula SCR: life-underwriting sub-modules (mortality / lapse /
  catastrophe) correlation-aggregated into a life SCR, then combined with market
  and counterparty risk through the top-level correlation matrix into the BSCR,
  with operational risk added linearly outside the matrix (`SCR = BSCR + Op`).
  Both aggregations use the standard-formula quadratic-form square root
  `sqrt(rᵀ·Corr·r)`, vectorised per period via `einsum`. Correlation matrices
  (`LIFE_CORRELATION`, `TOP_LEVEL_CORRELATION`) are the Delegated Regulation (EU)
  2015/35 Annex IV values in documented constants. Cost-of-capital risk margin
  (`risk_margin`, CoC 6%). 34 closed-form tests. ADR-100. Goldens byte-identical.
- **Key decisions:**
  - **Two correlation matrices, not one covariance pair** — the genuine
    structural difference from RBC. Aggregation generalised to a full matrix via
    `_correlation_aggregate` (einsum over the component index, no per-period
    loop).
  - **Catastrophe default (0.0015 of NAR) is the citable standard-formula
    life-CAT shock** (+1.5‰ of capital-at-risk for one year); the other factors
    are conservative committee-stage placeholders, overridable, exactly as
    LICAT/RBC.
  - **Operational risk adds outside the BSCR matrix** (no diversification
    credit), mirroring RBC's C-0/C-4a outside-the-root convention.
  - Only mortality / lapse / catastrophe life sub-modules + market +
    counterparty are modelled; longevity / expense / revision / disability and
    the health / non-life top-level modules are out of scope (filed follow-up).

### Slice 4: Surface the jurisdiction selector
The planned single Slice 4 (CLI + API + Excel + dashboard + notebook + ratio
surface) proved LARGE once selected, so it was re-decomposed into 4a (machine
surfaces, shipped) and 4b (presentation surfaces + ratio, planned). Each is an
independently mergeable, fully tested PR — per the routine's allowance for a
slice that proves larger than expected.

#### Slice 4a: CLI + API jurisdiction selector  ✅ DONE
- **Status:** DONE
- **Branch:** `claude/awesome-bardeen-e4ana9` (environment-designated)
- **PR:** #100 (draft)
- **What was done:** Added a single shared registry in
  `analytics/capital_base.py` — `SUPPORTED_CAPITAL_MODELS`, the `CapitalModelId`
  literal alias, and `capital_model_for(model_id, product_type) -> CapitalModel`
  (lazy calculator imports to avoid the `capital_base` ↔ `rbc`/`capital`/
  `solvency2` circular import). Routed BOTH machine surfaces through it: the CLI
  `--capital` flag (validation widened to the registry; `_run_profit_tests`
  resolves via the factory) and the API `capital_model` field (type widened from
  `Literal["licat"]` to `CapitalModelId`; price handler resolves via the
  factory). The capital output block is already jurisdiction-agnostic, so RBC /
  Solvency II render through the same JSON / console path. ADR-101.
- **Key decisions:**
  - **One registry, two surfaces** — a fourth jurisdiction is added in exactly
    one place (`capital_base.py`), and CLI/API can never drift apart.
  - The two pre-existing rejection tests (CLI exit-1, API 422) used `solvency2`
    as the *unknown* value; now that it is valid they move to `bogus`. This is
    the documented surface-contract flip the prior slice flagged.
  - Goldens byte-identical: only `--capital rbc` / `--capital solvency2` (was an
    error) move; default and `--capital licat` paths untouched.
- **Tests:** `test_capital_base.py` (13 — registry/protocol/normalisation/unknown);
  CLI parametrised `rbc`/`solvency2` JSON + three-way distinct-peak-capital;
  API parametrised `rbc`/`solvency2` acceptance; both rejection tests re-pointed
  to `bogus`. Fast suite 1616 passed; QA golden suite 72 green.

Slice 4b (the planned Excel / dashboard / notebook + result-level ratio bundle)
proved LARGE once selected — four surfaces, one of them a contract change needing
a new external input — so it was re-decomposed into 4b (presentation surfaces,
shipped) and 4c (result-level ratio + validation notebook, planned). Each is an
independently mergeable, fully tested PR, per the routine's allowance for a slice
that proves larger than expected.

#### Slice 4b: Dashboard + Excel jurisdiction surfacing  ✅ DONE
- **Status:** DONE
- **Branch:** `claude/awesome-bardeen-k05fxu` (environment-designated)
- **PR:** #101 (draft)
- **What was done:** Routed the two *presentation* surfaces through the same
  `capital_model_for` registry 4a established. Dashboard: the "Compute LICAT
  capital + RoC" checkbox became a "Regulatory capital basis (RoC)" selectbox
  (None / LICAT / US RBC / EU Solvency II); `_run_pricing_for_cohort`'s
  hard-coded `== "licat"` branch widened to `is not None` resolving via
  `capital_model_for` (LICAT path byte-identical); the chosen id rides on
  `CohortPricingData` and the cedant / reinsurer capital tiles caption the live
  jurisdiction. Excel: `DealPricingExport` gained a `capital_model_id` field
  (default `None` → byte-identical) and the Summary capital block gained a
  "Regulatory Capital — {label}" header; the CLI threads its `--capital` id onto
  the export. A shared `CAPITAL_MODEL_LABELS` + `capital_model_label` helper in
  `capital_base.py` is the single labelling site (mirrors the factory). ADR-102.
- **Key decisions:**
  - **Presentation surfaces split from the ratio.** 4b ships the dashboard +
    Excel surfacing (no new inputs, fully pytest-testable); the result-level
    ratio surface — which needs an external own-funds / TAC input the RoC entry
    points do not hold — moves to 4c with that input, alongside the notebook.
  - **Labels live on the registry, not the surfaces** (`CAPITAL_MODEL_LABELS` in
    `capital_base.py`), so dashboard and Excel cannot drift; `None` defaults to
    LICAT because every pre-ADR-098 capital schedule was LICAT.
  - Goldens byte-identical: default (no-capital) dashboard run and Excel workbook
    unchanged; LICAT capital path byte-identical; only the new header row / live
    label move, and only for capital runs.
- **Tests:** `test_pricing_capital_jurisdiction.py` (6 — each jurisdiction yields
  capital, None yields a plain result, three-way distinct peak capital);
  `test_capital_base.py` label-map class (every id labelled, known/normalised/None/
  unknown); `test_excel_output.py::TestCapitalJurisdictionHeader` (5 — header text
  per jurisdiction, position above Peak Capital, None→LICAT, absent when no
  capital). Full fast suite 1634 passed; QA golden suite green.

Slice 4c (the planned result-level ratio surface + three-standard validation
notebook) proved LARGE once detailed — a contract change to the capital protocol
+ result, threaded through four consumers, plus a notebook — so it was
re-decomposed into 4c-1 (the result-level ratio core, data model first, shipped)
and 4c-2 (CLI + API + Excel + dashboard inputs + validation notebook, planned).
Each is an independently mergeable, fully tested PR, per the routine's allowance
for a slice that proves larger than expected.

#### Slice 4c-1: Result-level capital-ratio core  ✅ DONE
- **Status:** DONE
- **Branch:** `claude/awesome-bardeen-bsrsuk` (environment-designated)
- **PR:** #102 (draft)
- **What was done:** Added the jurisdiction-agnostic solvency ratio as a
  `CapitalSchedule.capital_ratio(available_capital)` protocol method, implemented
  on all three result classes with the denominator encapsulated per jurisdiction
  — `CapitalResult` (LICAT) and `SolvencyIIResult` over `capital_by_period[0]`
  (required capital / SCR), `RBCResult` over `authorized_control_level[0]` (ACL =
  ½ CAL). `RBCResult.rbc_ratio` became a thin alias of `capital_ratio`.
  `ProfitTester.run_with_capital` gained an optional `available_capital: float |
  None = None` keyword that, when supplied, computes the ratio via
  `capital.capital_ratio(...)` and surfaces it on the two new
  `ProfitResultWithCapital` fields `available_capital` / `capital_ratio` (both
  default None → byte-identical otherwise). ADR-103.
- **Key decisions:**
  - **A protocol method, not a `ratio_denominator` attribute.** The numerator
    (available capital) is uniform; the denominator is the real jurisdictional
    difference (ACL = ½ held capital for RBC, held capital itself for LICAT /
    SCR). Encapsulating the whole ratio behind one method keeps "RBC divides by
    half" out of the consumer.
  - **`rbc_ratio` retained as an alias** so existing callers/tests are
    unaffected; the protocol surface is the new general entry point.
  - Goldens byte-identical: no consumer supplies `available_capital` yet — that
    is 4c-2. The contract change (protocol + result) is additive and
    backward-compatible.
- **Tests:** `test_profit_test.py::TestRunWithCapitalRatio` (6 — ratio None when
  omitted; LICAT / RBC / Solvency II closed forms; supplying the input disturbs
  no RoC/base field; zero-capital model raises); per-result closed forms +
  zero-denominator raises in `test_capital.py::TestCapitalResult`,
  `test_rbc.py::TestRBCResultHelpers`, `test_solvency2.py::TestSolvencyRatio`
  (6 across the three). Fast suite 1646 passed; QA golden suite 72 green.

Slice 4c-2 (the planned ratio surfacing across CLI/API/Excel/dashboard + the
validation notebook) proved LARGE once detailed — five surfaces, two of them
presentation rebuilds (an Excel ratio row, a dashboard number-input + tile) and
a notebook — so it was re-decomposed into 4c-2a (CLI + API machine surfaces,
shipped), 4c-2b (Excel ratio row + dashboard input/tile, planned) and 4c-2c
(validation notebook, planned), mirroring the 4a/4b machine-then-presentation
split. Each is an independently mergeable, fully tested PR, per the routine's
allowance for a slice that proves larger than expected.

#### Slice 4c-2a: CLI + API available-capital numerator  ✅ DONE
- **Status:** DONE
- **Branch:** `claude/awesome-bardeen-yqv16z` (environment-designated)
- **PR:** #103 (draft)
- **What was done:** Threaded the `available_capital` numerator through the two
  machine surfaces. CLI: a `--available-capital FLOAT` flag (validated to require
  `--capital` and be positive — either misuse exits 1) threaded through
  `_price_single_cohort` → `_run_profit_tests` → both sides'
  `run_with_capital(..., available_capital=)`; the JSON capital block gains the
  echoed `available_capital` + `capital_ratio` and the Rich capital table gains a
  "Solvency Ratio" row. API: an `available_capital` request field (`gt=0`, with a
  `model_validator` rejecting it 422 without `capital_model`) threaded into both
  `run_with_capital` calls; the response gains `available_capital`, `capital_ratio`
  (cedant) and `reinsurer_capital_ratio` (reinsurer). The same numerator is
  applied to both perspectives, each dividing by its own required capital. ADR-104.
- **Key decisions:**
  - **Same numerator, both sides.** The numerator (held available capital) is one
    supplied figure; each perspective divides by its own required-capital
    denominator, so the two ratios differ and are individually meaningful —
    symmetric with how peak/RoC are already surfaced for both sides, and requires
    no assumption about splitting capital between the parties. A per-side numerator
    is a later refinement, not a correctness gap.
  - **Eager validation over silent ignore.** `--available-capital` without
    `--capital` (CLI) or `available_capital` without `capital_model` (API) is
    rejected, not silently dropped — a ratio has no denominator without a model.
  - Goldens byte-identical: the flag/field default to None → ratio null; the
    golden run passes no `--capital`.
- **Tests:** `test_cli.py::TestPriceCommandAvailableCapital` (6); `test_main.py`
  (5 new in the capital block). Affected modules 298 passed; QA golden suite 72
  green.

#### Slice 4c-2b: Excel ratio row + dashboard input/tile  PLANNED
- **Status:** NEXT
- **Depends on:** Slice 4c-2a merged
- **Scope:** Render the `capital_ratio` on the Excel capital block (a ratio row
  under the 4b "Regulatory Capital — {label}" header) and the dashboard (a
  number-input for available capital + a ratio tile), threading the numerator
  through `DealPricingExport` and `CohortPricingData`. May rebaseline only the
  capital-surface goldens for non-default runs; the default path stays
  byte-identical. The held-capital-basis question (a configurable target
  *multiple* of ACL as an alternative numerator form) is the natural companion
  to the dashboard input here.

#### Slice 4c-2c: Three-standard validation notebook  PLANNED
- **Status:** PLANNED
- **Depends on:** Slice 4c-2b merged
- **Scope:** A notebook comparing LICAT / RBC / Solvency II on the golden block,
  demonstrating the required-capital schedules, the RoC, and the new solvency
  ratio side by side.

## Context for Next Session

- **Slice 4c-2b is next** (Excel ratio row + dashboard input/tile). Slice 4c-2a
  (this session) shipped the **machine surfaces**: the CLI `--available-capital`
  flag and the API `available_capital` field, both threaded into
  `run_with_capital(..., available_capital=)` and surfacing `capital_ratio` (and
  the echoed `available_capital`) on the cedant and reinsurer views. The
  remaining gap is the **presentation surfaces**: render `result.capital_ratio`
  on the Excel capital block (a ratio row under the 4b "Regulatory Capital —
  {label}" header) and the dashboard (a number-input for available capital + a
  ratio tile), threading the numerator through `DealPricingExport` and
  `CohortPricingData`. Then the validation notebook is 4c-2c.
- **The ratio computation and the machine plumbing are done** — 4c-2b only has to
  (a) collect the `available_capital` input on the dashboard, (b) thread it onto
  `DealPricingExport` (the CLI already passes `--capital`'s id onto the export, so
  add the numerator the same way), and (c) display `result.capital_ratio` already
  on `ProfitResultWithCapital`. No further analytics work. The
  `DealPricingExport.capital_model_id` field and the `CAPITAL_MODEL_LABELS` /
  `capital_model_label()` helper (4b) are the hooks the ratio row / tile attach
  to; the held-capital-basis open question is the natural companion to the
  dashboard input.
- **CLI/API threading reference (4c-2a).** The CLI numerator flows
  `price_cmd(--available-capital)` → `_price_single_cohort(available_capital=)` →
  `_run_profit_tests(available_capital=)` → both `run_with_capital` calls;
  emitted via `_profit_test_to_dict` (`capital_ratio` / `available_capital` keys)
  and `_append_capital_rows` ("Solvency Ratio" row). The API field is
  `PriceRequest.available_capital` (validated by
  `_available_capital_requires_capital_model`), emitted via `_capital_block` and
  the `capital_ratio` / `reinsurer_capital_ratio` response fields. The dashboard
  pricing view (`dashboard/views/pricing.py`) is the analogous seam for 4c-2b.
- The shared label map and `capital_model_label()` helper live in
  `analytics/capital_base.py` next to `capital_model_for` — extend them in one
  place. `_CAPITAL_MODEL_CHOICES` (dashboard) and the Excel header both read them.

### Historical context (Slices 1–4a)
- Slices 1–3 give all three calculators (`LICATCapital`, `RBCCapital`,
  `SolvencyIICapital`), each satisfying `CapitalModel` / `CapitalSchedule`, and
  both RoC entry points already take the protocol. Slice 4a was pure machine
  surfacing: a CLI `--capital {licat,rbc,solvency2}` selector (default `licat`
  → byte-identical), the API `capital_model` field (currently a 2-value literal;
  the existing tests assert `solvency2` is rejected — Slice 4 must add it and
  flip those two tests to expect acceptance), the Excel capital-sheet
  jurisdiction label + ratio, the dashboard selector, and the three-standard
  validation notebook. Wiring is a small dict `{"licat": ..., "rbc": ...,
  "solvency2": SolvencyIICapital.for_product}`.
- **Heads-up for Slice 4 (existing-test flip):**
  `tests/test_analytics/test_cli.py::test_capital_invalid_value_exits_non_zero`
  and `tests/test_api/test_main.py::test_price_capital_model_invalid_value_returns_422`
  currently use `solvency2` as the *unknown* value. Slice 4 changes the surface,
  so those two tests must be updated to a still-unknown id (e.g. `"bogus"`) and
  new acceptance tests added for `rbc` / `solvency2`. This is the one place
  Slice 4 legitimately edits existing assertions (the surface contract changed).
- Slice 2 (PR #98) widened both `ProfitTester.run_with_capital` and
  `Portfolio.run_with_capital` to the `CapitalModel` protocol, so the next
  jurisdiction only needs to satisfy `CapitalModel` / `CapitalSchedule` to plug
  into RoC for free — no further integration work in profit_test / portfolio.
- `RBCResult` deliberately mirrors `CapitalResult`'s helper surface so it is a
  drop-in for the RoC machinery; the extra `authorized_control_level` /
  `rbc_ratio` are additive.
- The result-level RBC-ratio / solvency-ratio surface was **deferred to Slice 4**
  (it needs an external TAC / target-multiple input that the RoC entry points do
  not hold). Slice 4 should introduce that input alongside the CLI/API selector.
- Solvency II (Slice 3) introduces a genuinely different aggregation
  (correlation matrix, not a single covariance pair) — keep the matrices in a
  documented constant and cite the Delegated Regulation vintage in ADR-100.

## Open Questions (for human)

- **Held-capital basis.** Slice 1 fixes the RBC held basis at Company Action
  Level (= 2× ACL). Reinsurers commonly hold a *target multiple* of ACL
  (300–400%). Should the held-capital basis be a configurable multiple of ACL
  (surfaced in Slice 2/4) rather than fixed at CAL? Not blocking Slice 1/2.
- **Factor calibration sign-off.** The NAIC-order committee factors (C-2
  0.00150 of NAR, C-3 Phase I categories, C-1o 1.0%) are approximations pending
  the Asset/ALM epic. Confirm they are acceptable for committee-stage screening,
  as the LICAT factors were.

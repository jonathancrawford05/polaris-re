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
- **PR:** (this slice)
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
- **PR:** (this slice)
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

#### Slice 4b: Excel / dashboard / notebook + result-level ratio surface
- **Status:** NEXT
- **Depends on:** Slice 4a merged
- **Scope:** Excel capital-sheet jurisdiction label + ratio; dashboard
  `--capital {licat,rbc,solvency2}` selector; three-standard validation notebook
  on the golden block; the result-level solvency/RBC-ratio surface (own-funds /
  TAC input ÷ SCR / ACL) deferred from Slices 2–3 because it needs an external
  own-funds / target-multiple input the RoC entry points do not hold. ADR-102.

## Context for Next Session

- Slices 1–3 give all three calculators (`LICATCapital`, `RBCCapital`,
  `SolvencyIICapital`), each satisfying `CapitalModel` / `CapitalSchedule`, and
  both RoC entry points already take the protocol. **Slice 4 is now pure
  surfacing**: a CLI `--capital {licat,rbc,solvency2}` selector (default `licat`
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

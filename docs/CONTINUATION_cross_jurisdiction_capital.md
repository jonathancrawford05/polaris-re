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
- **Status:** NEXT
- **Depends on:** Slice 2 merged (PR #98)
- **Scope:** `analytics/solvency2.py` — modular SCR (life underwriting:
  mortality / lapse / catastrophe; market; counterparty), correlation-matrix
  BSCR aggregation `sqrt(rᵀ·Corr·r)`, cost-of-capital risk margin. Satisfies
  `CapitalModel` / `CapitalSchedule`. Closed-form correlation-aggregation test.
  ADR-100. Goldens byte-identical.

### Slice 4: Surface the jurisdiction selector
- **Status:** PLANNED
- **Depends on:** Slice 3 merged
- **Scope:** CLI `polaris price --capital {licat,rbc,solvency2}` (default
  `licat` → byte-identical); API `capital_model` field; Excel capital-sheet
  jurisdiction label + ratio; dashboard selector; three-standard validation
  notebook on the golden block. The surfacing slice — outputs move only for
  runs that explicitly request a non-LICAT jurisdiction. ADR-101.

## Context for Next Session

- Slice 2 is merged-pending (PR #98): both `ProfitTester.run_with_capital` and
  `Portfolio.run_with_capital` now take the `CapitalModel` protocol, so the next
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

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
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:** `analytics/profit_test.py` (widen
  `run_with_capital`'s `capital_model` param from the concrete `LICATCapital`
  to the `CapitalModel` protocol — signature widening only); possibly a
  `ProfitResultWithCapital`-level RBC-ratio surface; `tests/test_analytics/`.
- **Tests to add:** `run_with_capital` yields identical metrics for a
  `LICATCapital` as today (regression); a parallel test drives it with an
  `RBCCapital`; RBC-ratio closed form (TAC / ACL).
- **Acceptance criteria:**
  - `run_with_capital(RBCCapital.for_product(...))` returns RoC / strain / IRR.
  - LICAT path metrics unchanged → goldens byte-identical.
  - ADR-099.

### Slice 3: Solvency II SCR module
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
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

- The shared `CapitalModel` / `CapitalSchedule` protocols are the integration
  seam. Slice 2 is a **signature widening** of `run_with_capital` — the body
  already only uses the `CapitalSchedule` surface (`required_capital`,
  `capital_by_period`, `pv_capital`, `capital_strain`), so widening the type
  hint and re-pointing the import is the bulk of the change. Verify by running
  the existing LICAT RoC tests unchanged.
- `RBCResult` deliberately mirrors `CapitalResult`'s helper surface so it is a
  drop-in for the RoC machinery; the extra `authorized_control_level` /
  `rbc_ratio` are additive.
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

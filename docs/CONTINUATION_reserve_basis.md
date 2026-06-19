# Continuation: Reserve-basis matching (Epic 1 / Tier-A A1)

**Source:** COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md — Tier A, item A1
(also PRODUCT_DIRECTION_2026-04-19 IMPORTANT "reserve-basis matching").
**Plan:** docs/PLAN_reserve_basis.md
**Status:** IN PROGRESS
**Total slices:** 4
**Estimated total scope:** ~10 dev-days

## Overall Goal

Let a reinsurer reproduce the cedant's reserve on the cedant's own basis
(NET_PREMIUM / CRVM / VM-20 simplified / GAAP) via a single `reserve_basis`
selector on `ProjectionConfig`. The reserve drives YRT NAR, coinsurance/modco
reserve transfer, and the profit signature, so reproducing the cedant's basis
is the biggest remaining credibility gap (per the 2026-06-18 review). The
whole-life terminal-reserve artefact is folded in as a named acceptance test
(Slice 2).

## Decomposition

### Slice 1: ReserveBasis enum + plumbing
- **Status:** DONE
- **Branch:** claude/epic-euler-uiauq2
- **PR:** (this session's draft)
- **What was done:** Added `ReserveBasis` StrEnum (`core/reserve_basis.py`,
  exported from `polaris_re.core`); added `ProjectionConfig.reserve_basis`
  (default NET_PREMIUM); added `BaseProduct._supported_reserve_bases` +
  `_check_reserve_basis()` dispatch guard, called from every product's
  `compute_reserves()`. Non-default bases raise `PolarisComputationError`
  rather than silently returning a net-premium reserve. ADR-087.
- **Key decisions:**
  - Non-default bases **raise** (no silent fallback) so a run can never
    report a reserve on a basis the engine did not compute.
  - The guard lives on `BaseProduct` via a `_supported_reserve_bases`
    frozenset that concrete engines widen as bases land. Term / WL / UL / DI
    all currently support only NET_PREMIUM.
  - Default path is byte-identical — no golden rebaseline.

### Slice 2: CRVM concrete basis (Term + WL)
- **Status:** NEXT
- **Depends on:** Slice 1 merged.
- **Files to create/modify:** `products/term_life.py`, `products/whole_life.py`
  (CRVM recursion + widen `_supported_reserve_bases`); likely
  `assumptions/assumption_set.py` and/or `core/projection.py` for the
  valuation mortality table (controlled core-contract change → ADR + default
  preserving backward compat); `docs/DECISIONS.md`.
- **Tests to add:** closed-form CRVM reserve vs a worked textbook example;
  the WL terminal-reserve acceptance test; default NET_PREMIUM still
  byte-identical.
- **Acceptance criteria:**
  - CRVM reserve matches a cited worked example within closed-form tolerance.
  - CRVM first-year reserve < NET_PREMIUM first-year reserve (expense
    allowance graded in).
  - WL terminal-reserve artefact ($7.18M→$56k) is closed or materially
    improved on the golden WL block, with the improvement explained.
  - NET_PREMIUM default unchanged (goldens byte-identical).

### Slice 3: VM-20 simplified (deterministic reserve / NPR floor)
- **Status:** PLANNED
- **Depends on:** Slice 2 merged.
- **Scope:** deterministic reserve = max(NPR, modelled reserve) on prescribed
  valuation assumptions; NPR floor only, no stochastic scenarios. Closed-form
  test vs a worked simplified-PBR example.

### Slice 4: Surface the basis selector
- **Status:** PLANNED
- **Depends on:** Slice 3 merged.
- **Scope:** CLI `--reserve-basis`, API request schema, Excel reserve-sheet
  label, validation notebook comparing profit signature across bases. This is
  the only slice that may move goldens — and only for non-default basis runs;
  document any rebaseline.

## Context for Next Session

- The dispatch hook is `BaseProduct._check_reserve_basis()` — it returns the
  active basis so Slice 2 can branch on it inside `compute_reserves()`. The
  cleanest pattern: keep the existing net-premium body, add a
  `_compute_reserves_crvm()` private method, and dispatch on the returned
  basis. Widen `_supported_reserve_bases` on the engine when you add a basis.
- The **valuation mortality table** question is the one real design decision
  in Slice 2 (see PLAN §5). CRVM uses 2001 CSO, which is distinct from the
  best-estimate projection table. Adding a `valuation_mortality` slot to
  `AssumptionSet` (defaulting to the projection table) is the leading option;
  it is a controlled core-contract change → ADR + backward-compat default +
  flag in the PR per the guardrails.
- Treaty layer needs **no** changes: YRT NAR and coinsurance reserve transfer
  both consume `compute_reserves()` output, so basis selection reprices them
  automatically. Add an integration test in Slice 2 confirming a CRVM basis
  changes the YRT ceded premium (NAR moves).
- UL (reserve = account value) and DI (reserve = 0) deliberately only support
  NET_PREMIUM. Extending them to statutory bases is out of scope for this epic
  — leave the guard raising.

## Open Questions (for human)

- Confirm the intended VM-20 scope is the **deterministic reserve / NPR floor
  only** (no stochastic scenario reserve). The PLAN assumes so; stochastic
  VM-20 would be its own multi-session epic.
- Which worked CRVM example should be the closed-form anchor? (A cited
  textbook level-premium whole-life CRVM reserve is the plan's default.)

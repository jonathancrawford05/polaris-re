# Dev Session Log — 2026-06-19 (reserve-basis epic, slice 3b)

## Item Selected
- **Source:** CONTINUATION_reserve_basis.md (active Epic A1 — Reserve-basis
  matching) — next unchecked slice.
- **Priority:** IMPORTANT (Tier-A epic, top-ranked in
  COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md).
- **Title:** VM-20 simplified reserve for WholeLife (to-omega `max(NPR, DR)`).
- **Slice:** 3b of 5 (slices 1, 2a, 2b, 3a complete).
- **Branch:** claude/epic-euler-5z2pj2 (environment-designated).

## Selection Rationale
Step 5 found CONTINUATION_reserve_basis IN PROGRESS; slice 3a (PR #84) is merged
into main, so I continued the Epic on the designated branch with the next
unchecked slice (3b, WholeLife VM-20). The ACTIVE EPIC track (step 5b) mandates
advancing the Epic before any fallback pick — no fallback considered. No other
CONTINUATION was an IN PROGRESS draft to defer.

## Decomposition Plan (multi-session)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | ReserveBasis enum + dispatch guard | ✅ Done | #81 |
| 2a | TermLife CRVM (FPT) | ✅ Done | #82 |
| 2b | WholeLife CRVM + terminal-reserve artefact | ✅ Done | #83 |
| 3a | TermLife VM-20 simplified (`max(NPR, DR)`) | ✅ Done | #84 |
| 3b | WholeLife VM-20 (to-omega DR) | ✅ Done | (this draft) |
| 4 | Surface basis selector (CLI/API/Excel/notebook) | ⏳ Next | — |

## What Was Done
Implemented the VM-20 simplified reserve for `WholeLife` as `max(NPR, DR)` floored
at 0 — the **deterministic** path of the US principle-based reserve (no stochastic
scenarios, per PLAN §2). It is the WL analogue of the TermLife slice 3a (ADR-090),
but both components are valued **prospectively to omega** because whole life is
prospective beyond the projection horizon. **NPR** reuses the to-omega WL CRVM
reserve (`_compute_reserves_crvm`, ADR-089), which already grades monotonically
toward face. **DR** is a new to-omega deterministic gross-premium reserve
(`_compute_deterministic_reserve`): the per-in-force prospective PV of future
death benefits + maintenance expenses − future gross premiums, under **both**
decrements, via the backward recursion
`DR_t = (E_t − G_t) + v·[q_t·face + (1−q_t)(1−w_t)·DR_{t+1}]` valued on the
to-omega grid (`_valuation_months_to_omega`) and sliced to the projection horizon,
so it grades toward face rather than collapsing at the horizon edge — the artefact
ADR-089 solved for the WL CRVM. Lapse over the to-omega grid is supplied by a new
`_build_valuation_lapse` (mortality reuses the existing `_build_valuation_mortality`).
`compute_reserves()` dispatches VM20 to `_compute_reserves_vm20()`. ADR-091.

Per routine step 7b I **reproduced the premise first**: selecting
`reserve_basis=VM20` on a WholeLife block raised `PolarisComputationError`
(unimplemented; supported bases CRVM, NET_PREMIUM), and the to-omega CRVM (NPR)
reserve grades toward face (≈$191k yr10 → ≈$493k yr20 on the probe block) rather
than collapsing — confirming the floor the VM-20 `max` builds on. I then verified
the two operating regimes with the engine: a well-priced block ($20k premium) has
DR < NPR across the building durations, so VM20 coincides with the CRVM floor
there; an underpriced block ($8k premium) has DR above the NPR floor (yr10
DR≈$231k vs NPR≈$191k), so VM20 follows the realistic DR — the deficiency signal.

The NPR := CRVM mapping is the "simplified" in "VM-20 simplified" (carried from
ADR-090); the exact VM-20 NPR refinements remain promoted follow-ups. Short
limited-pay WL (< 20 years) still raises via the inherited CRVM 20-pay guard. The
NET_PREMIUM default path is left byte-identical (the epic's golden constraint).

## Files Changed
- `src/polaris_re/products/whole_life.py` — `_supported_reserve_bases` widened to
  include VM20; `compute_reserves()` dispatches VM20; `_compute_reserves_vm20()`,
  `_compute_deterministic_reserve()`, `_build_valuation_lapse()` added.
- `tests/test_products/test_whole_life_vm20_reserve.py` — new (12 tests).
- `tests/test_products/test_reserve_basis_dispatch.py` — WL no longer raises on
  VM20 (removed from `WL_UNIMPLEMENTED_BASES`); only GAAP remains unimplemented.
- `docs/DECISIONS.md` — ADR-091.
- `docs/CONTINUATION_reserve_basis.md` — Slice 3b DONE; Slice 4 NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — struck through the Slice-3b follow-up
  as SHIPPED (PR for slice 3b).

## Tests Added
- `tests/test_products/test_whole_life_vm20_reserve.py` (12 tests):
  - **Independent forward prospective-PV** (to omega) reproduces the engine's
    backward DR recursion with lapse + acquisition + maintenance all on — the
    closed-form anchor.
  - DR monotone non-decreasing in the maintenance load.
  - DR does not collapse at the horizon (grades toward face on the to-omega grid).
  - `VM20 == max(NPR_crvm, DR)` elementwise; VM20 ≥ NPR floor; VM20 ≥ 0.
  - **Well-priced regime** ($20k): DR < NPR → VM20 == CRVM in the building
    durations.
  - **Underpriced regime** ($8k): DR > NPR → VM20 == DR (deficiency lifts the
    reserve strictly above the floor).
  - VM20 grades toward face while NET_PREMIUM collapses (no-collapse vs the
    artefact).
  - NET_PREMIUM default byte-identical.
  - To-omega lapse array matches `_build_rate_arrays` over the projection horizon.
  - Short limited-pay (< 20 years) raises via the inherited CRVM guard.
  - YRT integration: a higher VM-20 reserve lowers the NAR and the ceded YRT
    premium, with no treaty-layer change.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| VM-20 simplified = `max(NPR, DR)` implemented for WholeLife | ✅ | `_compute_reserves_vm20`; `test_vm20_equals_max_npr_dr` |
| DR valued to omega (no horizon collapse) | ✅ | `test_dr_does_not_collapse_at_horizon`, `test_vm20_grades_toward_face` |
| DR verified closed-form against an independent computation | ✅ | Independent to-omega forward prospective-PV; `test_matches_independent_forward_pv` |
| NPR floor governs well-priced; DR governs underpriced | ✅ | `test_well_priced_floor_governs`, `test_underpriced_dr_governs` |
| Treaty reprices on basis switch (NAR moves) | ✅ | `test_underpriced_vm20_lowers_ceded_premium` |
| NET_PREMIUM default unchanged (goldens byte-identical) | ✅ | QA suite passed; CLI golden price OK; `test_net_premium_default_byte_identical` |

## Open Questions / Follow-ups
- VM-20 across both Phase-1 life products (Term + WL) is now complete. The
  remaining reserve-basis slice is **Slice 4** — surface the basis selector
  (CLI `--reserve-basis`, API request schema, Excel reserve-sheet label,
  validation notebook comparing the profit signature across bases). It is the
  only slice that may move goldens (and only for non-default basis runs).
- All ADR-091 "Out of scope" items (VM-20 stochastic reserve; exact VM-20 NPR
  refinements / NPR := CRVM; broader DR expense components; the 2001 CSO
  valuation table; the 20-pay expense-allowance cap for short-pay WL) are
  **already promoted** in PRODUCT_DIRECTION_2026-06-18's "Promoted Follow-ups"
  (carried from ADR-088/089/090). No new harvest items this session.

## Parked Polish
None. (All ADR-091 out-of-scope items are 1st-order follow-ups already promoted
in a prior session; no new 3rd-order-or-deeper items surfaced.)

## Impact on Golden Baselines
None. The default NET_PREMIUM path is untouched and byte-identical (QA golden
suite passed; CLI golden price ran clean). VM20 is opt-in (`reserve_basis=VM20`)
and is not exercised by any golden. No rebaseline.

## Baseline Note
`make test` baseline this session: **1433 passed, 0 failures, 83 deselected** —
matches the recorded slice-3a post-change baseline; no new/changed failures.
(The convert-soa-tables step left the 4 CIA tables MISSING, as in prior sessions;
the SOA VBT / 2001 CSO tables converted OK, and the suite has no CIA-dependent
failures.) Post-change: **1444 passed, 83 deselected** (+12 new WholeLife VM-20
tests, −1 dispatch parametrize case: `test_whole_life_raises[VM20]` removed
because VM20 is now supported for WholeLife, mirroring the 2a/2b/3a updates — not
an assertion weakened to pass). mypy not run locally per routine (CI's job; ~207
inherited baseline errors).

# Dev Session Log — 2026-06-19 (reserve-basis epic, slice 3a)

## Item Selected
- **Source:** CONTINUATION_reserve_basis.md (active Epic A1 — Reserve-basis
  matching) — next unchecked slice.
- **Priority:** IMPORTANT (Tier-A epic, top-ranked in
  COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md).
- **Title:** VM-20 simplified reserve for TermLife (`max(NPR, DR)`).
- **Slice:** 3a of 5 (slices 1, 2a, 2b complete).
- **Branch:** claude/epic-euler-5adps2 (environment-designated).

## Selection Rationale
Step 5 found CONTINUATION_reserve_basis IN PROGRESS; slice 2b (PR #83) is merged
into main, so I continued the Epic on the designated branch with the next
unchecked slice (Slice 3, VM-20 simplified). The ACTIVE EPIC track (step 5b)
mandates advancing the Epic before any fallback pick — no fallback considered.
No other CONTINUATION was an IN PROGRESS draft to defer. Per the 2a/2b
precedent, Slice 3 is split into 3a (Term) + 3b (WL) because the WL
deterministic reserve is prospective beyond the projection horizon (the same
to-omega problem ADR-089 solved); Term's finite horizon makes its DR exact, so
3a ships cleanly and correctly this session.

## Decomposition Plan (multi-session)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | ReserveBasis enum + dispatch guard | ✅ Done | #81 |
| 2a | TermLife CRVM (FPT) | ✅ Done | #82 |
| 2b | WholeLife CRVM + terminal-reserve artefact | ✅ Done | #83 |
| 3a | TermLife VM-20 simplified (`max(NPR, DR)`) | ✅ Done | (this draft) |
| 3b | WholeLife VM-20 (to-omega DR) | ⏳ Next | — |
| 4 | Surface basis selector (CLI/API/Excel/notebook) | 🔲 Planned | — |

## What Was Done
Implemented the VM-20 simplified reserve for `TermLife` as `max(NPR, DR)` floored
at 0 — the **deterministic** path of the US principle-based reserve (no
stochastic scenarios, per PLAN §2). **NPR** is mapped to the CRVM reserve
(`_compute_reserves_crvm` from 2a): a net-premium reserve with the first-year
expense allowance graded in, which is the formulaic floor VM-20 prescribes for
the NPR. **DR** is a new deterministic gross-premium reserve
(`_compute_deterministic_reserve`): the per-in-force prospective present value of
future death benefits and maintenance expenses less future gross premiums, under
**both** decrements (mortality + lapse), via the backward recursion
`DR_t = (E_t − G_t) + v·[q_t·face + (1−q_t)(1−w_t)·DR_{t+1}]`, terminal
`DR_T = 0`. The expense/premium arrays mirror exactly what `project()` emits
(gross premium and maintenance per in-force policy, plus the one-time acquisition
cost in month 0 for genuine new business, all zeroed after term expiry).
`compute_reserves()` now captures the lapse array `w` and dispatches VM20 to
`_compute_reserves_vm20(q, w, v)`. ADR-090.

Per routine step 7b I **reproduced the premise first**: selecting
`reserve_basis=VM20` on a TermLife block raised `PolarisComputationError`
(unimplemented), and the net-level-premium reserve sits above CRVM everywhere
(the expense allowance) — confirming the floor relationships the VM-20 `max`
relies on. I then verified the two operating regimes with the engine: a
well-priced block ($12k premium) has DR < NPR while the reserve builds, so VM20
coincides with the CRVM floor there; an underpriced block ($600 premium) has DR
well above the NPR floor across the durations (yr10 ≈ $107k vs CRVM ≈ $50k), so
VM20 follows the realistic DR — the deficiency signal a reinsurer relies on.

The NPR := CRVM mapping is the "simplified" in "VM-20 simplified": the exact
VM-20 NPR refinements (term `X` factors, deficiency, the prescribed valuation
table) are documented and promoted as follow-ups rather than half-wired. The DR
is exact for term over its finite horizon. The NET_PREMIUM default path is left
byte-identical (the epic's golden constraint).

## Files Changed
- `src/polaris_re/products/term_life.py` — `_supported_reserve_bases` widened to
  include VM20; `compute_reserves()` captures `w` and dispatches VM20;
  `_compute_reserves_vm20()` and `_compute_deterministic_reserve()` added.
- `tests/test_products/test_term_vm20_reserve.py` — new (8 tests).
- `tests/test_products/test_reserve_basis_dispatch.py` — Term no longer raises on
  VM20 (removed from `TERM_UNIMPLEMENTED_BASES`); the error-message test now uses
  GAAP (still unimplemented for Term).
- `docs/DECISIONS.md` — ADR-090.
- `docs/CONTINUATION_reserve_basis.md` — Slice 3 split into 3a (DONE) + 3b (NEXT).
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — 4 harvested follow-ups (Slice 3b WL
  VM-20, exact NPR refinements, stochastic reserve, broader DR expenses).

## Tests Added
- `tests/test_products/test_term_vm20_reserve.py` (8 tests):
  - **Independent forward prospective-PV** sum reproduces the engine's backward
    DR recursion (with lapse + acquisition + maintenance all on) — the closed-form
    anchor.
  - DR is monotone non-decreasing in the maintenance expense load.
  - `VM20 == max(NPR_crvm, DR)` elementwise; VM20 ≥ NPR floor; VM20 ≥ 0.
  - **Well-priced regime**: DR < NPR in the building durations → VM20 == CRVM
    there.
  - **Underpriced regime**: DR > NPR across the durations → VM20 == DR (the
    deficiency lifts the reserve strictly above the formulaic floor).
  - NET_PREMIUM default byte-identical.
  - YRT integration: a higher VM-20 reserve lowers the NAR and the ceded YRT
    premium, with no treaty-layer change.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| VM-20 simplified = `max(NPR, DR)` implemented for TermLife | ✅ | `_compute_reserves_vm20`; `test_vm20_equals_max_npr_dr` |
| DR verified closed-form against an independent computation | ✅ | Independent forward prospective-PV sum; `test_matches_independent_forward_pv` |
| NPR floor governs well-priced; DR governs underpriced | ✅ | `test_well_priced_floor_governs`, `test_underpriced_dr_governs` |
| Treaty reprices on basis switch (NAR moves) | ✅ | `test_underpriced_vm20_lowers_ceded_premium` |
| NET_PREMIUM default unchanged (goldens byte-identical) | ✅ | QA suite 72 passed; CLI golden price OK; `test_net_premium_default_byte_identical` |

## Open Questions / Follow-ups
- WholeLife VM-20 (Slice 3b) needs the to-omega DR (reuse ADR-089 machinery) so
  it does not collapse at the horizon. Promoted IMPORTANT.
- NPR := CRVM is a simplification; exact VM-20 NPR (term `X` factors, deficiency,
  prescribed valuation table) deferred. The valuation-table piece overlaps the
  already-promoted "2001 CSO valuation table" IMPORTANT item; the X-factor /
  deficiency refinement promoted NICE-TO-HAVE.
- VM-20 stochastic reserve (SR) is its own epic (explicitly out of scope).
  Promoted NICE-TO-HAVE.
- The DR models maintenance + acquisition expenses only; commissions / premium
  tax need expense assumptions the engine does not yet model. Promoted
  NICE-TO-HAVE.

## Parked Polish
None. (All harvested items are 1st-order follow-ups of the originally-planned
VM-20 feature.)

## Impact on Golden Baselines
None. The default NET_PREMIUM path is untouched and byte-identical (QA golden
suite 72 passed; CLI golden price ran clean). VM20 is opt-in
(`reserve_basis=VM20`) and is not exercised by any golden. No rebaseline.

## Baseline Note
`make test` baseline this session: **1426 passed, 0 failures, 83 deselected** —
matches the recorded slice-2b post-change baseline; no new/changed failures.
(The convert-soa-tables step left the 4 CIA tables MISSING, as in prior sessions;
the SOA VBT / 2001 CSO tables converted OK, and the suite has no CIA-dependent
failures.) Post-change: **1433 passed, 83 deselected** (+8 new Term VM-20 tests,
−1 dispatch parametrize case: `test_term_raises[VM20]` removed because VM20 is
now supported for TermLife, mirroring the 2a/2b updates — not an assertion
weakened to pass). mypy not run locally per routine (CI's job; ~207 inherited
baseline errors).

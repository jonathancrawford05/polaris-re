# Dev Session Log — 2026-06-19 (Reserve-basis Slice 2a)

## Item Selected
- **Source:** CONTINUATION_reserve_basis.md (Epic 1 / Tier-A A1) — the active
  Epic. Slice 1 (ADR-087, PR #81) is merged; this session advances the next
  unchecked slice.
- **Priority:** Tier A (highest-value epic; #1 credibility gap)
- **Title:** Reserve-basis matching — Slice 2a: CRVM concrete basis for TermLife
- **Slice:** 2a of 5 (Slice 2 split into 2a Term + 2b WL this session)
- **Branch:** `claude/epic-euler-807ipt` (environment-designated)

## Selection Rationale
Routine step 5 found the reserve-basis CONTINUATION IN PROGRESS with Slice 1
DONE and merged; step 5c/5b mandate advancing the active Epic's next slice
before any fallback pick. No open PRs (slice 1's #81 is merged), so the next
slice is unblocked. No fallback work was considered — the guardrail forbids it
while the Epic can advance.

**Why Slice 2 was decomposed into 2a + 2b.** Planned Slice 2 covered CRVM for
Term **and** WL plus the WL terminal-reserve acceptance test. Implementing the
WL pieces *correctly* entangles two separate hard problems — a prospective WL
terminal reserve to omega (the $7.18M→$56k artefact) and the 20-pay
expense-allowance cap — both of which the truncated projection horizon makes
non-trivial. Per CLAUDE.md ("actuarial correctness above all"; "if uncertain,
document and TODO, do not guess") and the routine's "decompose, don't defer",
Term CRVM ships cleanly as 2a and the WL work becomes a focused 2b. Term is the
exact case where Full Preliminary Term *is* CRVM (no cap, no omega), so it is
fully correct and verifiable in one session.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | `ReserveBasis` enum + `ProjectionConfig` field + dispatch guard | ✅ Done | #81 |
| 2a | CRVM (Full Preliminary Term) for **TermLife** | ✅ Done | (this draft) |
| 2b | CRVM for **WholeLife** + terminal-reserve artefact + valuation table + 20-pay cap | ⏳ Next | — |
| 3 | VM-20 simplified (deterministic / NPR floor) | 🔲 Planned | — |
| 4 | Surface selector on CLI / API / Excel / notebook | 🔲 Planned | — |

## Verify Premise (routine step 7b)
With `reserve_basis=CRVM`, `TermLife.compute_reserves()` raised
`PolarisComputationError` via the slice-1 guard (the existing `test_term_raises`
parametrization), and the net-premium reserve was positive in early durations —
confirming the engine could not yet produce a CRVM reserve and that a distinct
(lower early) CRVM reserve is observable. Premise holds.

## What Was Done
Implemented CRVM for `TermLife` as **Full Preliminary Term (FPT)**. The
valuation net premium is split into a first-year `alpha` and a level renewal
`beta`, each solved on the equivalence principle over its segment (months 0–11
vs 12–T−1); the existing backward recursion then deducts `alpha` in the first 12
months and `beta` thereafter. Because `alpha·ä_year1 + beta·ä_renewal` equals
the APV of all benefits, the issue reserve `0V = 0`; FPT additionally yields a
zero first-year terminal reserve (`12V = 0`) and, from month 12, the net premium
reserve of the policy issued one year later — so CRVM sits at or below the net
premium reserve in every duration, grading in the first-year acquisition expense
allowance. For level term the renewal premium never reaches the 20-pay cap, so
FPT is *exact* CRVM; no cap arithmetic is needed.

`TermLife._supported_reserve_bases` now includes CRVM and `compute_reserves()`
dispatches on the basis (the NET_PREMIUM body was extracted unchanged into
`_compute_reserves_net_premium()`, keeping the default byte-identical). CRVM
values on the projection (best-estimate) mortality for now; the distinct
statutory valuation table (2001 CSO) is deferred to 2b rather than shipping a
half-wired core-contract change. ADR-088 records the decision and the deferrals.

The treaty layer needed no change: switching to CRVM lowers the early reserve,
raising the YRT Net Amount at Risk and the ceded premium automatically — covered
by an integration test.

## Files Changed
- `src/polaris_re/products/term_life.py`
- `tests/test_products/test_term_crvm_reserve.py` (new)
- `tests/test_products/test_reserve_basis_dispatch.py` (Term no longer raises on CRVM)
- `docs/DECISIONS.md` (ADR-088)
- `docs/CONTINUATION_reserve_basis.md` (Slice 2 → 2a/2b)
- `docs/PRODUCT_DIRECTION_2026-06-18.md` (harvested follow-ups)

## Tests Added
- `test_term_crvm_reserve.py`:
  - `test_equivalence_principle` — `alpha·ä_year1 + beta·ä_renewal == APV(benefits)` (analytic).
  - `test_zero_at_issue_and_year1_terminal` — FPT `0V = 0`, `12V = 0`.
  - `test_crvm_never_exceeds_net_premium` — CRVM ≤ NET_PREMIUM everywhere, strict mid-term.
  - `test_matches_independent_recursion` — engine reproduces an independent numpy reimplementation (rtol 1e-12).
  - `test_default_basis_unchanged_by_crvm_code` — NET_PREMIUM byte-identical.
  - `TestCRVMRaisesNAR::test_crvm_increases_ceded_yrt_premium` — CRVM raises YRT NAR + ceded premium.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| CRVM reserve verified vs closed-form / independent path | ✅ | equivalence principle + independent recursion (rtol 1e-12) + FPT identities |
| CRVM first-year reserve < NET_PREMIUM (expense allowance graded in) | ✅ | `12V=0`; CRVM ≤ NP everywhere, strict at month 60 |
| Treaty reprices (YRT NAR moves) with no treaty change | ✅ | integration test on ceded premium + NAR |
| NET_PREMIUM default unchanged (goldens byte-identical) | ✅ | QA golden suite 72 passed; no rebaseline |
| ADR recorded | ✅ | ADR-088 |
| WL CRVM + terminal-reserve artefact | ⏳ | deferred to Slice 2b (see Open Questions) |

## Open Questions / Follow-ups
- **WL CRVM + prospective terminal reserve (Slice 2b).** The $7.18M→$56k
  artefact is a horizon-truncation issue in `_compute_terminal_reserves`; a
  proper prospective WL reserve to omega (using a valuation table) is the fix.
  Owned by 2b.
- **Statutory valuation mortality table (2001 CSO).** CRVM here values on the
  projection table. Wiring a distinct `valuation_mortality` slot on
  `AssumptionSet` (with the select/improvement questions it raises) is a
  controlled core-contract change owned by 2b.
- **20-pay expense-allowance cap.** Not needed for level term (never binds);
  required for short-pay/high-premium WL. Owned by 2b; flag a TODO if the
  truncated horizon prevents a reliable cap.

## Parked Polish
None. (No 3rd-order follow-ups surfaced this session.)

## Impact on Golden Baselines
None. Default basis is NET_PREMIUM and its recursion body is unchanged; the QA
golden suite (72 tests, incl. `price` CLI goldens) passes. No rebaseline.

## Baseline Note
`make test` baseline this session: **1411 passed, 0 failures, 83 deselected**
(matches the slice-1 log's post-change target). CIA tables MISSING from the
pymort conversion as usual; SOA tables converted, no SOA failures — no new or
changed failures vs baseline. Post-change: **1416 passed, 83 deselected** (+6
new CRVM tests, −1 from the dispatch test re-parametrization as Term now
supports CRVM).

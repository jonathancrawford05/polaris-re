# Dev Session Log — 2026-07-05

## Item Selected
- **Source:** CONTINUATION_reserve_basis_correctness.md / PLAN_reserve_basis_correctness.md — the **CHECKPOINT** step (after Slice 1, before Slice 2)
- **Priority:** Process step (gates the active epic's Slices 2–3) — mandated by the epic plan and by routine step 6 (30-day / post-slice viability regeneration)
- **Title:** Regenerate COMMERCIAL_VIABILITY_REVIEW; re-anchor the active epic
- **Slice:** Checkpoint (between Slice 1 DONE and Slice 2 PLANNED) — the session's sole deliverable per routine step 6 ("Regenerating the review is a substantial analytical task — if doing it AND shipping a slice would blow the wall-clock guardrail, make the regeneration the session's deliverable and log that the slice is deferred")
- **Branch:** `claude/loving-gauss-o37i85`

## Selection Rationale
Step 5 found no *other* IN-PROGRESS CONTINUATION to continue; the active epic
is `Reserve-Basis Correctness & Interest Exactness` (step 5b). Its Slice 1
(WholeLife mortality-improvement bug) is DONE and merged (PR #128, ADR-129,
at HEAD `4c9d423`). The next unchecked item in the epic is the **CHECKPOINT**:
regenerate the commercial-viability ranking to confirm interest-exactness
(Slices 2–3) is still the highest-value continuation before committing to it,
or redirect the epic to a productization theme. Per routine step 6, the
regeneration is itself a substantial analytical deliverable and Slice 2 is
deferred to the next run.

## Decomposition Plan (active epic status)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | WholeLife mortality-improvement on best-estimate bases | ✅ Done | #128 |
| CHECKPOINT | Regenerate COMMERCIAL_VIABILITY_REVIEW; re-anchor | ✅ Done (this session) | (this PR) |
| 2 | Prescribed statutory valuation-interest helper — engine | ⏸ Deprioritized → NICE-TO-HAVE (pending maintainer redirect go/no-go) | — |
| 3 | Surface valuation-interest on the deal path + docs | ⏸ Deprioritized (depends on Slice 2) | — |

## What Was Done
Regenerated the commercial-viability review as
`docs/COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md`. Re-reviewed the last 10
merged PRs (#119–#128) and found they are **disciplined epic slices**, not
polish — confirming the 2026-06-18 routine change (the always-on Epic track)
worked and the slice-level polish spiral is resolved. Catalogued the state of
every 2026-06-18 Tier-A/C0/B3 item and found the **entire modeling roadmap is
now complete**: A1 reserve-basis matching, A2 IFRS 17 movement, A3
cross-jurisdiction capital (US RBC + EU Solvency II), C0 Asset/ALM, and B3
expense-allowance have all shipped; ROADMAP Phases 1–5 are ✅ COMPLETE; ADRs
current through ADR-129; 2,001 unit tests green.

The checkpoint question — does interest-exactness (Slices 2–3) still rank
first? — resolves **no**. The *correctness* half of the current epic (the
WholeLife improvement bug) shipped in Slice 1; the remaining *exactness* half
(penny-exact CRVM/VM-20 valuation interest) is ★★★☆☆ polish on a capability
that already works directionally. With the modeling roadmap done, the frontier
has moved to **trust-and-deployment**: a validation & benchmark pack (A1′),
production hardening (A2′, ROADMAP 6.2), and cedant-ingestion robustness (A3′)
now out-rank it. The review recommends **demoting Slices 2–3 to a NICE-TO-HAVE
follow-up and constituting a productization/credibility epic next**, and —
because the CONTINUATION explicitly reserved this redirect for a human — the
final go/no-go is surfaced for the maintainer (review §7). The CONTINUATION
and PLAN record the checkpoint outcome; the interest-exactness Slices 2–3
remain fully planned and intact so the next session can ship Slice 2 unchanged
if the maintainer declines the redirect.

This is a **docs-only** session (no source or test changes); goldens and the
test suite are untouched.

## Files Changed
- `docs/COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` — new (regenerated review + checkpoint verdict)
- `docs/CONTINUATION_reserve_basis_correctness.md` — CHECKPOINT status → DONE with outcome; Slice 2 → DEPRIORITIZED (pending maintainer decision)
- `docs/PLAN_reserve_basis_correctness.md` — CHECKPOINT status → DONE with outcome
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — marked the checkpoint-regeneration follow-up RESOLVED; harvested the interest-exactness demotion (NICE-TO-HAVE) and the productization-epic direction item (IMPORTANT)

## Tests Added
None (docs-only). Baseline `make test`: **2,001 passed, 2 skipped, 110 deselected, 0 failures** (prior session log baseline: 1,990 passed — the +11 are Slice 1's `test_wl_improvement.py`; no new/changed failures, tolerance-aware check passes).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Regenerate COMMERCIAL_VIABILITY_REVIEW (re-review last ~10 PRs + docs, re-rank catalogue) | ✅ | `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md` |
| Confirm-or-redirect interest-exactness (Slices 2–3) | ✅ | Verdict: REDIRECT recommended; demote to NICE-TO-HAVE |
| Record checkpoint outcome in PLAN/CONTINUATION | ✅ | Both updated; Slice 2 marked DEPRIORITIZED |
| Preserve Slices 2–3 for revival / maintainer override | ✅ | PLAN/CONTINUATION intact; ships unchanged if redirect declined |
| Exactly one active epic maintained | ✅ | Epic stays IN PROGRESS (open-but-deprioritised) until maintainer decides / next epic constituted |

## Open Questions / Follow-ups
- **For Jonathan (redirect go/no-go — reserved in the CONTINUATION):** accept
  the review's recommendation to **redirect** the active epic from
  interest-exactness to a productization/credibility epic (lead A1′ validation
  & benchmark pack; fallback A2′ production hardening)? If you'd rather finish
  interest-exactness first, the next session ships Slice 2 unchanged.
- If redirect is accepted, next session runs a **scoping pass** on A1′ —
  confirm which authoritative references are obtainable and executable in CI
  (published VM-20 reserve decks, SOA illustrative values, closed-form textbook
  cases; AXIS/Prophet side-by-side only where a reference output exists) — and
  writes `PLAN_validation_benchmark.md` + slice 1. Fall back to A2′ (ROADMAP
  6.2, no external dependency) if A1′ is reference-blocked.
- The 2026-06-18 "Sprint 0" quick wins **B1** (capital surfaces →
  `for_product_interim`) and **B2** (100K–500K scale benchmark) remain
  unshipped — the cleanest between-epic fallback picks.

## Parked Polish
None this session. (The interest-exactness demotion is a 2nd-order follow-up
of the checkpoint and was promoted as NICE-TO-HAVE, not parked; the
productization-epic item is a 1st-order direction item from the regenerated
review — both within the step-17 auto-promotion cap.)

## Impact on Golden Baselines
None — docs-only session; no source, tests, or golden configs touched.

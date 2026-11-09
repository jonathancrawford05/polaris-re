# Dev Session Log — 2026-11-09

## Item Selected
- **Source:** Routine step 5b (empty Epic slot: every IN PROGRESS continuation is
  owned by the mgcv Parity routine or parked) plus step 6 (the latest
  `COMMERCIAL_VIABILITY_REVIEW` is 117 days old, above the ~30-day regeneration
  trigger).
- **Priority:** N/A. This is strategic direction-setting, not a PRODUCT_DIRECTION
  item.
- **Title:** Regenerate `COMMERCIAL_VIABILITY_REVIEW`: re-rank the pricing-engine
  catalogue and name daily-dev's next Tier-A epic.
- **Slice:** complete (single deliverable).
- **Branch:** `claude/amazing-faraday-kkgm3w` (the designated remote-session
  branch, used under the step-8 environment override), cut from `main` at
  `25f34d0` (after #282).
- **Mode:** maintenance mode (Epic slot empty), as the 2026-08-16 amendment
  (Change 4) directs.

## Selection Rationale
- **Step 5:** `CONTINUATION_gam_dashboard.md` is IN PROGRESS and its S1 is open as
  PR #283, but it is owned by `ROUTINE_MGCV_PARITY.md`. So are
  `mgcv_parity_engine`, `mgcv_capability_ladder` and `gam_real_data_readiness`.
  `penalized_mi_surface` is superseded and routed there, and
  `reserve_basis_correctness` is PARKED. Every other continuation is COMPLETE.
- **Step 5b(a):** the externally-owned epics are excluded, which leaves the Epic
  slot EMPTY.
- **Step 5b(b):** start the top unstarted Tier-A item from the latest review. But
  the latest review (2026-07-15) has no unstarted Tier-A item: A4′ shipped, and
  the MCP server Phase-7 epic shipped after it.
- **Step 6:** the review is more than 30 days old, so it must be regenerated
  before the next epic is selected. A 117-day re-rank and a slice in one session
  would exceed the wall-clock guardrail, so **the regeneration is the deliverable**
  and A5′ slice 1 is deferred to the next run. This follows the 2026-07-15
  precedent.
- **Skipped:** any Tier-B/C pick (B5 WL artefact, B6 rate limit, B7 6.3 gate). The
  fallback gate does not apply while the selection inputs themselves are stale.
- **Skipped:** the GAM dashboard S1, which the mgcv routine owns and already has
  open as PR #283.

## Premise Verified (step 7b)
- **Ownership:** each IN PROGRESS continuation's header and the pointer in
  `ROUTINE_MGCV_PARITY.md` (line 25) name the mgcv routine.
- **Throughput claim:** the GitHub PR list shows #184–#282 are GAM/mgcv work,
  apart from cross-cutting verification PRs (#200, #208, #236) and #281
  (maintainer UX). #183 (2026-08-04) is the last pricing-engine feature.
- **B5 premise, re-checked in code:** `products/whole_life.py:270-290` still
  documents NET_PREMIUM as using the one-period terminal estimate, left
  byte-identical. Only CRVM, VM-20 and GAAP value to omega.
- **A5′ "never started":** `grep -ri "RunStore|run_record|run_history|sqlite" src/`
  finds nothing. The CLI's "audit trail" comments refer to echoing inputs within
  one run's JSON.

## What Was Done
Wrote `docs/COMMERCIAL_VIABILITY_REVIEW_2026-11-09.md`. It reviews #273–#282
(plus #283 open). Its central finding is that the mgcv/GAM track has taken 100%
of merged throughput for about 97 days. The cause is that two routine texts
disagree about whether daily-dev yields its slot (§7 Q1).

The review re-ranks the pricing-engine catalogue, excluding the GAM items, which
their own routine owns. It names **A5′ Deal and run persistence with an audit
trail** as daily-dev's next Tier-A epic, for four reasons:
- it is the most-felt missing layer;
- it has no open actuarial questions;
- it has zero file contention with the mgcv routine;
- it builds on the existing provenance and versioning patterns.

The review also gives A5′ a 4-slice outline. It ranks B5 (the WL NET_PREMIUM
terminal-reserve artefact, IMPORTANT #2), then B7 (the ROADMAP 6.3 gate), then B6
(shared rate limit) as between-slice quick wins. It surfaces three maintainer
decisions.

No code changed.

## Files Changed
- `docs/COMMERCIAL_VIABILITY_REVIEW_2026-11-09.md` (new)
- `docs/DEV_SESSION_LOG_2026-11-09_viability_review_regen.md` (this log)

## Tests Added
None (docs only).

## Acceptance Criteria
| Criterion | Status | Notes |
|---|---|---|
| Review regenerated (it was more than 30 days old) | ✅ | 2026-11-09 |
| Last 10 PRs reviewed | ✅ | #273–#282, plus #283 open |
| Catalogue re-ranked by value × effort | ✅ | Tiers A–D; GAM items excluded as externally owned |
| Next daily-dev Tier-A epic named, with a slice outline | ✅ | A5′, §6 |
| Ledger healing (step 4b) | ✅ | No PRODUCT_DIRECTION entry matches #279, #281 or #282, so nothing to strike |

## Open Questions / Follow-ups
1. **(Maintainer) Should the two routines run in parallel?** Review §7 Q1. The
   recommendation is yes, with `ROUTINE_MGCV_PARITY.md` §Budget amended to match.
2. **(Maintainer) The A6′ stochastic ESG calibration basis.** Review §7 Q2.
3. **(Maintainer) Close IMPORTANT #11 (ADR-141) as moot under ADR-264?** Review
   §7 Q3.
4. **Next session:** write `PLAN_run_persistence.md`, open its CONTINUATION, and
   ship A5′ slice 1, unless the maintainer answers Q1 with "keep yielding".

## Parked Polish
None.

## Harvest (step 17)
No new work items were promoted. A5′/A6′/A7′ are the 2026-07-24 file's own
Phase-7 candidates, ranked here. B5–B7 and C5–C9 are existing ledger entries.
Q1–Q3 are decisions, not work items. No ADR was added this session. Since
nothing was harvested, no new `PRODUCT_DIRECTION` file was created; the review's
§8 records what that regeneration must carry.

## Comparisons / provenance
No comparison was produced. All figures (PR counts, day counts) come from
`git log` or the GitHub PR list.

## Baseline
See "Baseline result" below. The prior recorded baseline (the PR #282 review, at
the PR head with mortality tables converted) was **4238 passed, 27 skipped, 147
deselected, 0 failed**.

## Impact on Golden Baselines
None. No source change.

## Perf History
No row: nothing under `src/polaris_re/` changed (ADR-177 amendment 1).

# Dev Session Log — 2026-08-04 (park the recursion epic; start real-data GAM diligence)

## Item Selected
- **Source:** `docs/PRODUCT_DIRECTION_2026-07-24.md` — "Real-data diligence run
  for the experience GAM", reclassified **NICE-TO-HAVE → IMPORTANT** on maintainer
  direction 2026-08-03. Epic-start under routine step 5b: the
  `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` Tier-A ladder is **exhausted** (A4′
  shipped), so there was no unstarted Tier-A item to draw from.
- **Priority:** IMPORTANT (epic start).
- **Title:** Real-data diligence for the experience GAM (HMD + SOA-ILEC).
- **Slice:** epic constitution + the loader work that unblocks it. Slice 1 is NEXT.
- **Branch:** `claude/gam-realdata-5zhsw3` (environment-designated; the step-8
  environment override takes precedence over the `feat/auto-*` default).
- **PR:** #184. Split out of #183 on maintainer direction — see below.

## Selection Rationale

This session was hand-directed throughout rather than autonomously selected, so
the rationale is a record of decisions taken with the maintainer rather than a
step-6 ranking.

**The recursion epic was constituted and parked on the same day.** It was created
to fill the step-5b gap (no active Epic, Tier-A ladder exhausted) from ADR-180's
diagnosis that the engines' month-by-month Python loops cap the parallel gain.
Answering a maintainer question about floating-point tolerances produced the
measurement that undercut it — see `MEASUREMENT_engine_recursion_prework.md`. The
failure was one of **process, not estimate**: the routine's own step-11b
discipline (quantify before acting) was applied to the implementation plan but
never to the epic's *premise*. Had it been, the 5.2 s figure for a 320k-policy
book would have ended it before the plan was written.

**The successor epic answers the same gap against the product thesis.** A4′
shipped fifteen slices of tensor-GAM machinery, all validated on synthetic data
with an injected surface — which proves the implementation recovers a surface it
was handed, not that it recovers real improvement from real experience. CLAUDE.md
§1 names "no native ML integration" as the incumbents' defining weakness.

**PR split (maintainer-directed).** #183 was rewritten to contain only the
parallel-execution work; this branch carries the pivot. The boundary was clean
(`207b344`), with only `PRODUCT_DIRECTION_2026-07-24.md` overlapping.

## Baseline

`make test` at session start (on merged `main`, after #183):
**2928 passed, 3 skipped, 125 deselected**, 0 failures. Matches #183's recorded
end state. No NEW or CHANGED failures → PROCEEDED. The 3 skips are the standing
absent-CIA-2014-table skips.

End state: **2939 passed, 3 skipped**. Next session's expected baseline is
**2939 passed, 3 skipped**.

## What Was Done

**Parked the recursion epic with its own evidence.** `lx` vectorises
**bit-identically** via an interleaved `cumprod` (verified at N = 6, 5,000 and
20,000) for **zero speed-up** — 165.2 ms vs 167.1 ms at N=20,000, because the
loop is array-work-bound and Python overhead is ~1% of it. And the premise
underneath was never tested: a 320k-policy book already prices in 5.2 s. One of
four loops was measured, so the falsification is **partial** and recorded as such.

**Incidental finding, filed IMPORTANT (step 11b).** Patching the naive `lx` into
the engine — verified to execute, and to perturb the array by 1.9e-15 — left
**all five golden digests bit-identical**. The golden block is 6 policies per
cohort: too small to detect a last-ulp change. "Goldens byte-identical" is
therefore *necessary but insufficient* for a numerical rewrite, and a change of
that class would pass CI today while altering the engine.

**Constituted the GAM real-data epic** with what the fit could *fail* to
reproduce named in advance (PLAN §2) — the post-2010 US slowdown,
cross-population agreement, insured-vs-population divergence, and agreement with
SOA's own expected deaths. A slice reporting a failure is a successful slice.

**Loader work — every defect found by running it, not reading it.** See ADR-181.
The maintainer downloaded the real 2012-2019 release (~12 GB, 30 columns) and
each step surfaced something: tab-delimited (unreadable), eager read (would
exhaust RAM), `Gender`→`Sex` rename, and — from a query run to answer an
unrelated question — `Preferred_Class` conflating class-2-of-2 with
class-2-of-4.

**Routine-hygiene fix.** `CONTINUATION_reserve_basis_correctness` read
`IN PROGRESS — but DEPRIORITISED / parked` for four weeks; four sessions treated
it as parked *by convention* while step 5b matches on the literal string. Once
#183 closed `portfolio_execution` it became the only match, and an autonomous
session would have resumed it. Status now reads `PARKED`; exactly one CONTINUATION
is `IN PROGRESS`.

## Files Changed

- `src/polaris_re/analytics/experience_loaders.py` — `separator` + misparse guard;
  lazy/streaming scan; `ILEC_2012_19_COLUMN_MAP`; `include_expected`; `uw_class`
  composition; `ILEC_UW_CLASS_COUNT_TARGET` exported.
- `tests/test_analytics/test_experience_loaders.py` — 21 new tests.
- `docs/DECISIONS.md` — **ADR-181**.
- `docs/PLAN_experience_gam_realdata.md`, `docs/CONTINUATION_experience_gam_realdata.md` — new epic.
- `docs/PLAN_engine_recursion_vectorisation.md`, `docs/CONTINUATION_engine_recursion_vectorisation.md` — PARKED.
- `docs/MEASUREMENT_engine_recursion_prework.md` — the measurement that parked it.
- `docs/RUNBOOK_experience_data_acquisition.md` — acquisition + §2d.
- `docs/CONTINUATION_reserve_basis_correctness.md` — status wording.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — downgrade + two new IMPORTANT items.
- `.gitignore`, `perf/history.jsonl`.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| Epic artefacts present (PLAN + CONTINUATION IN PROGRESS, slice 1 NEXT) | ✅ | |
| Exactly one `IN PROGRESS` CONTINUATION | ✅ | Verified on `**Status:**` lines |
| Recursion epic parked with evidence, not deleted | ✅ | `MEASUREMENT_engine_recursion_prework.md` |
| Real 2012-2019 release loadable | ✅ | 9,714,592 cells; 9.8 per 1,000 crude |
| Goldens byte-identical | ✅ | Nothing in `products/` moves |
| ADR for the loader contract change | ✅ | ADR-181 |

## Perf History

Row appended for the branch HEAD. **Position reversed on review.** The PR
originally omitted it, arguing a row pinned to a docs-plus-loader commit is noise
for a projection-hot-path detector. The review pointed out this diverges from
ADR-177 without amending it, and the counter-argument is better than the original:
a row on **unchanged engine code is a control observation**, and #183's row came
in ~2.4x elevated on suspected runner noise. A control point is exactly what
distinguishes noise from drift once the series reaches the 6 rows the detector
needs. Cheaper to append than to amend an accepted ADR.

Creep verdict: `insufficient_data` (log below `2 * window`).

## PR #184 review round

Automated review **approved** — zero P0, zero test failures, goldens green. Four
[P1]s and four [P2]s; all addressed in-PR.

**[P1-1] was a real bug I introduced, and worse than the one it fixed.** Polars
string concat with a null operand yields null, so a numbered class with a null
`Number_of_Pfd_Classes` became `uw_class = null` and *every* such row grouped
together — pooling classes 1 and 2 outright, silently. Reproduced independently
before fixing (classes 1 and 2 merged into one null cell with 300.0 exposure).
Fixed by degrading a missing count to `"1ofNA"` / `"2ofNA"`: distinct, and
visibly unqualified.

**[P1-2] a vacuous test, correctly called.** The backward-compatibility assertion
used `"uw_class" not in cells.columns or <always-true>`, and the fixture had no
`Preferred Class` column, so both disjuncts were trivially satisfied. The
guarantee it claimed to check was untested. Fixture now carries the column and
the assertion compares actual values.

**[P2-1] the streaming fallback swallowed execution errors.** `except TypeError`
around the real `collect` cannot distinguish an unsupported `engine=` kwarg from
a genuine `TypeError` during query execution, and the retry's own exceptions
escaped unwrapped. Now probes engine support once on a trivial plan.

**[P2-2]** `ILEC_UW_CLASS_COUNT_TARGET` exported — a caller writing a map for
another vintage had no supported way to opt into the composition.

**[P2-3]** ADR-181 added. **[P2-4]** PR-body test counts corrected.

## Open Questions / Follow-ups

1. **`uw_class` dtype is inconsistent across paths** — Int64 from the reader on
   the uncomposed path (all-numeric class column), always Utf8 on the composed
   one. Cosmetic today; a join-key hazard if a future consumer keys on it across
   vintages. Filed in ADR-181's out-of-scope, not fixed here.
2. **Goldens cannot detect a last-ulp engine perturbation** (above). IMPORTANT.
3. **The parked recursion epic rests on a partial falsification** — one of four
   loops. Revival needs a profile *and* a workload where latency blocks someone.
4. **`mgcv` oracle (ADR-151) still unexecuted** — maintainer's to run, and
   real-data fitting is when it earns its keep.

## Parked Polish

**None.** Every item above is 1st-order — a follow-up of this session's own
planned scope or of a review finding on it. Nothing reached 2nd order, so the
step-17 cap did not bite.

## Impact on Golden Baselines

**None.** Nothing in `products/` moves; `tests/qa/` untouched in the diff and
green on all five configs. The `perf/history.jsonl` append is diagnostic data,
not a golden change.

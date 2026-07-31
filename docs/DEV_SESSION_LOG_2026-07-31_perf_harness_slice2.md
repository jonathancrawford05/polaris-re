# Dev Session Log — 2026-07-31

## Item Selected
- **Source:** `docs/CONTINUATION_perf_harness.md` — the in-progress perf epic
  (IMPORTANT #9 in `PRODUCT_DIRECTION_2026-07-24`), **Slice 2**.
- **Priority:** IMPORTANT (active in-flight epic; advanced before any fallback pick).
- **Title:** Head-vs-main same-job driver + `perf.json` diff.
- **Slice:** 2 of 3 (+1 optional Slice 4 = IMPORTANT #10).
- **Branch:** `claude/loving-gauss-rkb3qg` (environment-designated).

## Selection Rationale
Step 5 found three IN PROGRESS CONTINUATIONs: `perf_harness`,
`expense_allowance_duration`, and `reserve_basis_correctness` (explicitly parked /
deprioritised). The MCP Phase-7 epic closed in the prior session
(`CONTINUATION_mcp_server` COMPLETE), and the CVR-2026-07-15 recommended epic
(A4′ experience-monitoring / GAM) is already COMPLETE — so there is no *unstarted*
Tier-A epic, and the routine advances an in-flight epic (step 5/5b) before any
fallback.

Between the two live epics, `expense_allowance_duration`'s **mandatory** scope was
already complete (Slice 2 / PR #169 merged; only an optional 2nd-order polish
Slice 3 remained, already promoted as NICE-TO-HAVE) — so it had no advanceable
slice and was closed as COMPLETE during ledger healing. `perf_harness` **did** have
an advanceable next slice: Slice 1 (PR #171) **merged to main** (commit `68c3ce7`),
unblocking Slice 2, which is substantive mandatory work. Per the ACTIVE-EPIC
guardrail (advance the epic before any fallback), Slice 2 is this session's
deliverable. No Tier-B/C/D fallback was picked.

**Ledger healing (step 4b).** Two PRs recorded as unmerged drafts had merged since
their session logs: **PR #169** (expense duration Slice 2, `f9fc7aa`) and **PR #171**
(perf Slice 1, `68c3ce7`). Healed `CONTINUATION_expense_allowance_duration`
(Slice 2 draft → MERGED; Status IN PROGRESS → COMPLETE, its backlog already
promoted as PD #3's NICE-TO-HAVE). `CONTINUATION_perf_harness` already recorded
#171 correctly.

**Premise verification (step 7b).** Reproduced the gap before writing code:
Slice 1 emits a per-branch `PerfReport` / `perf.json` but has **no** way to
*compare* two branches — there was no `diff_reports`, no `PerfDiff`, and no runner
that checks out `origin/main`. Confirmed by grepping the Slice-1 module (only
`PerfProbe`/`PerfReport`/`run_perf_probe`) and `scripts/` (no `perfbench.py`). The
premise holds: Slice 2 is genuinely unbuilt.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Deterministic perf-probe core | ✅ Done | #171 (merged) |
| 2 | Head-vs-main driver + `perf.json` diff | ✅ Done | _this PR (draft)_ |
| 3 | CI perf job (closes IMPORTANT #9) | ⏳ Next | — |
| 4 | `perf/history.jsonl` creep log (opt / #10) | 🔲 Planned | — |

## What Was Done
Extended `analytics/perf_harness.py` with the diff layer:
`diff_reports(head, main, *, band=1.5, mib_alert_delta=4)` returning a `PerfDiff`
verdict built from per-probe `ProbeDiff`s. Probes match by name; a probe on only
one branch, or any deterministic-metric mismatch (`n_policies` / `projection_months`
/ `n_cells` / `output_fingerprint`), is a **hard delta** (`has_hard_delta` — the
single gate boolean). The best-of-k wall-time **ratio** (head/main; `None` when
main is 0) and the `peak_mib` **delta** are **advisory-only** alerts
(`has_wall_time_alert` / `has_peak_mib_alert`) that never set the hard delta,
enforcing the maintainer rule (deterministic metrics gate; wall-time only informs)
structurally. `to_diff_dict()` renders the verdict first, then per-probe detail.

Added `scripts/perfbench.py`: a git-worktree head-vs-main runner. It probes the
current worktree and a `git worktree add --detach` checkout of `--ref` (default
`origin/main`) by executing the **same** self-contained Slice-1-only probe snippet
as a subprocess in each tree — `sys.path.insert(0, "src")` + `cwd=worktree` selects
that branch's engine over any editable install while sharing the current
interpreter's deps (the `scripts/scale_benchmark.py` trick). It writes a `perf.json`
payload (`ref` + verdict-first `diff` + both `to_perf_dict()` reports) and exits
non-zero **iff** the diff has a hard delta — the gate Slice 3's CI job consumes.
Verified end-to-end against `origin/main`: identical fingerprints (engine
unchanged), wall-time ratio ~1.1×, `peak_mib` Δ 0, no hard delta, exit 0; the
`.perfbench_main_worktree` checkout is cleaned up in a `finally`.

`diff_reports` is unit-tested synthetically (16 fast tests, no engine / no git) in
`tests/test_analytics/test_perf_diff.py`, following Slice 1's
`test_perf_harness_units.py` split (fast unit vs `perf`+`slow` engine). ADR-175
records the design; PD #9 and the PLAN/CONTINUATION were advanced to Slice 3 NEXT.

## Files Changed
- `src/polaris_re/analytics/perf_harness.py` — `ProbeDiff` / `PerfDiff` models +
  `diff_reports(...)`; `__all__` extended.
- `src/polaris_re/analytics/__init__.py` — export `PerfDiff` / `ProbeDiff` /
  `diff_reports`.
- `scripts/perfbench.py` — new git-worktree head-vs-main runner (`perf.json`,
  hard-delta exit code).
- `docs/DECISIONS.md` — ADR-175.
- `docs/PLAN_perf_harness.md` — status → Slices 1+2 shipped; Slice 3 NEXT.
- `docs/CONTINUATION_perf_harness.md` — Slice 2 DONE; Slice 3 NEXT + CI wiring note.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — PD #9 updated (Slice 2 shipped); harvest
  subsection (perfbench CLI NICE-TO-HAVE + band/MiB maintainer decisions).
- `docs/CONTINUATION_expense_allowance_duration.md` — ledger-healed (#169 merged;
  COMPLETE).

## Tests Added
- `tests/test_analytics/test_perf_diff.py` (new, +16, fast/`not slow`): identical
  reports → no delta/alert (ratio ≈ 1.0); fingerprint / cell-count mismatches +
  head-only / main-only probes → hard delta; wall-time ratio above / inside / at
  the band and zero-main → advisory-only (never hard); `peak_mib` delta above /
  within threshold + head-uses-less → advisory-only; `to_diff_dict` verdict-first
  shape; `band` / `mib_alert_delta` validation raises `PolarisValidationError`.
- The git-worktree runner is exercised by running `scripts/perfbench.py`
  (head-vs-`origin/main`), not a unit test — per the PLAN (keep unit tests
  synthetic).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| `diff_reports` computes per-metric head/main ratios | ✅ | best-of-k wall-time ratio + `peak_mib` delta + exact deterministic compare |
| Structural mismatch = hard delta; wall-time outside band = advisory (never hard) | ✅ | `has_hard_delta` vs `has_wall_time_alert`/`has_peak_mib_alert`; pinned by 16 tests incl. the boundary + zero-main cases |
| `perf.json` carries both reports + verdict, deterministic-first | ✅ | payload = `ref` + verdict-first `diff` + both `to_perf_dict()` reports |
| Runner benchmarks head vs `origin/main` in one invocation | ✅ | `scripts/perfbench.py` git-worktree; verified end-to-end, exit 0, worktree cleaned |
| Goldens byte-identical | ✅ | `polaris price` flat: cedant $3,513,563 / reinsurer $45,386; `tests/qa/` 94 passed |
| Quality gate (ruff format+check, fast suite, qa) | ✅ | ruff clean (`src/ tests/` + `scripts/perfbench.py`); qa 94; fast suite green |

## Open Questions / Follow-ups
- **Wall-time alert band + `peak_mib` alert delta are policy choices.** Defaults
  `band=1.5×` and `mib_alert_delta=4 MiB` are surfaced now; the maintainer should
  confirm them before Slice 3 gates CI (as alerts, never hard gates). Flagged in
  `CONTINUATION_perf_harness` Open Questions.
- **Optional `polaris perfbench` CLI subcommand.** Runner shipped script-first
  (B2 precedent). Harvested NICE-TO-HAVE (ADR-175 Out of scope, 1st-order).
- **Slice 3 (CI perf job) is NEXT** and depends on this Slice 2 merging; it only
  needs to run `scripts/perfbench.py` on one runner and gate on its exit status.

## Parked Polish
None. ADR-175's out-of-scope items are the epic's own tracked Slices 3/4 (in the
CONTINUATION and PD #9/#10) plus one 1st-order NICE-TO-HAVE (perfbench CLI),
harvested normally — nothing reached 3rd-order.

## Impact on Golden Baselines
None. Purely additive — new diff models + a `scripts/` runner; no `src/` pricing
code changed. `polaris price` on `golden_config_flat.json` is byte-identical
(cedant PV $3,513,563, reinsurer PV $45,386); `tests/qa/` 94 passed.

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2758 passed, 3 skipped, 124 deselected**, 0 failures (tolerance-aware; SOA VBT /
CSO tables OK, the 4 CIA-2014 tables MISSING → the 3 skips are the standing
baseline). The prior log (`DEV_SESSION_LOG_2026-07-31_mcp_server_slice4`) recorded
2733 at *its* start; the +25 is that session's own added tests now on `main`
(#177) — no NEW or CHANGED failure, so the session PROCEEDED. This slice adds 16
fast unit tests (the diff layer).

# Continuation: Performance Harness with Head-vs-Main Baseline

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — IMPORTANT #9 (+ #10); the
deterministic companion to the IMPORTANT #8 smoke gate. *Source: maintainer
discussion 2026-07-12 (CI perf/smoke thread), 1st-order.*
**Status:** IN PROGRESS
**Total slices:** 3 (+1 optional follow-on = IMPORTANT #10)
**Estimated total scope:** ~3 dev-days
**Plan:** `docs/PLAN_perf_harness.md` (read-only spec)

## Overall Goal

Time the engine's hot paths on a fixed synthetic block, capture deterministic
structural metrics alongside informational wall-clock timing, and benchmark the
current worktree against `origin/main` in the same CI job so machine noise
cancels in the head/main ratio. Deterministic metrics + the ratio gate/alert;
raw wall-time only informs (maintainer rule, 2026-07-12). Unblocks the per-merge
`perf/history.jsonl` creep log (IMPORTANT #10).

## Decomposition

### Slice 1: Deterministic perf-probe core
- **Status:** DONE
- **Branch:** `claude/loving-gauss-ixouzo`
- **PR:** #_(this session's draft)_
- **What was done:** Added `analytics/perf_harness.py` — `PerfProbe` (one
  hot-path measurement row) + `PerfReport` (container with `to_perf_dict()` /
  `to_json()` emitting the `perf.json` shape), and `run_perf_probe(...)` timing
  a mapping of named hot-path callables (default: the production
  `get_product_engine(...).project()` path) on a `build_homogeneous_block`
  fixed block. Per probe it captures the exactly-deterministic
  `n_policies` / `projection_months` / `n_cells`, an `output_fingerprint`
  (blake2b over the rounded core `CashFlowResult` arrays), the MiB-rounded
  `tracemalloc` peak (`peak_mib`), and best-of-k timing (`best_of_k_seconds`
  + raw `samples_seconds`, informational). New `tests/perf/` package with
  reproducibility + arithmetic-invariant + validation tests, tagged `perf` and
  `slow`. Registered the `perf` marker; `make perf` target; ADR-169.
- **Key decisions:** (1) Gate-safe metrics are the exactly-deterministic counts
  + MiB-rounded peak + fingerprint; raw bytes/ms never gate (evidence in the
  PLAN §2 table). (2) Best-of-k **min**, not mean (first-call/GC outlier). (3)
  Reuse B2's `build_homogeneous_block` — no new block builder, no test-data
  file, so no Dockerfile/`.dockerignore` change. (4) `PerfProbe.deterministic_metrics()`
  exposes exactly the fields a future CI gate (Slice 3) may read.

### Slice 2: Head-vs-main same-job driver + `perf.json` diff
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:** `scripts/perfbench.py` (git-worktree head/main
  runner); optionally a `polaris perfbench` CLI subcommand; extend
  `analytics/perf_harness.py` with a `diff_reports(head, main, *, band)` →
  verdict model.
- **Tests to add:** `tests/perf/test_perf_diff.py` — the ratio arithmetic and
  the gate/alert classification (structural mismatch = hard delta; wall-time
  ratio outside band = advisory), on two synthesized reports (no real git
  checkout in the unit test).
- **Acceptance criteria:**
  - Given two `PerfReport`s, `diff_reports` computes per-metric head/main ratios.
  - A structural-metric mismatch is flagged as a hard delta; a wall-time ratio
    outside the band is an advisory alert (never a hard delta).
  - `perf.json` payload carries both reports + the verdict, deterministic-first.

### Slice 3: CI perf job (closes IMPORTANT #9)
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
- **Scope:** A CI job (needs `lint`) running the Slice-2 head-vs-main harness on
  one runner, uploading `perf.json`, gating on structural deltas and alerting
  (non-blocking) on the wall-time ratio. README/QUICKSTART note.

### Slice 4 (optional / IMPORTANT #10): per-merge `perf/history.jsonl` + creep
- **Status:** PLANNED (may be constituted as its own epic once #9 closes)
- **Scope:** append-only deterministic-first row per merge to main + creep
  detection; NICE-TO-HAVE tail (#62 pr-review perf comment, #63 backfill).

## Context for Next Session

- **The evidence for the design lives in `PLAN_perf_harness.md` §2** — a probe
  run showed wall-time has ~2× local jitter (informational only), `tracemalloc`
  peak is stable only at MiB granularity (~0.005% byte jitter → gate at MiB),
  and counts/fingerprint are exact. Do not gate on absolute ms or raw bytes.
- **B2 (`analytics/scale_benchmark.py`, ADR-161)** is the sibling harness; reuse
  `build_homogeneous_block`. B2 measures *scaling shape* across sizes; this
  measures *head-vs-main drift* at a fixed size — complementary, not duplicative.
- **The `perf` marker is also `slow`** so the fast matrix and Docker job skip it;
  Slice 3's CI job selects `-m perf` on its own runner (mirroring the smoke job).
- Slice 2's git-worktree checkout of `origin/main` is the one non-trivial piece;
  keep the *unit* tests synthetic (two hand-built reports) so they need no git.

## Open Questions (for human)

- **Surface as `polaris perfbench`?** Slice 2 could expose the runner as a CLI
  subcommand or leave it a `scripts/` tool (as B2 did — `scripts/scale_benchmark.py`,
  deliberately not a `polaris` subcommand). Defer to the maintainer's B2
  precedent (script-first) unless a CLI surface is requested.
- **Wall-time alert band.** The head/main ratio alert threshold (default
  proposal 1.5×) is a policy choice; confirm before Slice 3 gates CI on it
  (as an alert, never a hard gate).

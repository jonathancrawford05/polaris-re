# Continuation: Performance Harness with Head-vs-Main Baseline

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — IMPORTANT #9 (+ #10); the
deterministic companion to the IMPORTANT #8 smoke gate. *Source: maintainer
discussion 2026-07-12 (CI perf/smoke thread), 1st-order.*
**Status:** COMPLETE — mandatory scope (Slices 1–3) shipped; IMPORTANT #9 closed.
The optional Slice 4 (`perf/history.jsonl` creep log = IMPORTANT #10) is carried
forward in `PRODUCT_DIRECTION_2026-07-24.md` and may be constituted as its own
epic; it is not a blocker on this CONTINUATION.
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
- **PR:** #171
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
- **Status:** DONE
- **Branch:** `claude/loving-gauss-rkb3qg` (environment-designated)
- **PR:** #178 (**MERGED** 2026-08-01, commit `750a6a7`)
- **ADR:** ADR-175
- **What was done:** Extended `analytics/perf_harness.py` with the diff layer —
  `ProbeDiff` (one head-vs-main probe comparison) + `PerfDiff` (the verdict
  container) and `diff_reports(head, main, *, band=1.5, mib_alert_delta=4)`.
  Probes are matched by name; a probe present on only one branch, or any
  deterministic-metric mismatch (counts / `output_fingerprint`), is a **hard
  delta** (`PerfDiff.has_hard_delta` — the single boolean a gate reads). The
  best-of-k wall-time **ratio** (head/main; `None` if main is 0) and the
  `peak_mib` **delta** are advisory-only alerts (`has_wall_time_alert` /
  `has_peak_mib_alert`) that never contribute to the hard delta — enforcing the
  maintainer rule structurally. `PerfDiff.to_diff_dict()` renders the verdict
  first, then per-probe detail. Added `scripts/perfbench.py`: a git-worktree
  runner that probes the current worktree and a `--detach` checkout of `--ref`
  (default `origin/main`) by executing the **same** self-contained Slice-1-only
  probe snippet as a subprocess in each tree (`sys.path.insert(0, "src")` +
  `cwd=worktree` selects that branch's engine, sharing the current
  interpreter's deps), diffs them, writes a `perf.json` payload
  (`ref` + verdict-first `diff` + both `to_perf_dict()` reports), and exits
  non-zero **iff** there is a hard delta (the gate Slice 3 wires into CI).
- **Key decisions:** (1) `diff_reports` unit-tested synthetically in
  `tests/test_analytics/test_perf_diff.py` (16 fast, no engine / no git —
  following Slice 1's `test_perf_harness_units.py` convention); the git-worktree
  path is exercised by running the script, not a unit test (per the PLAN). (2)
  `peak_mib` alert is an **absolute** MiB delta (default `> 4`), not a ratio —
  an extra `N×T` float64 array (~6 MiB on the default block) clears it while the
  ±1 MiB rounding jitter does not; a ratio band would miss a real leak on a
  small base. (3) The probe snippet uses the committed
  `tests/fixtures/synthetic_select_ultimate.csv` (present on both branches; the
  generated `data/` tables are not, so they can't cross a worktree) and
  redirects setup stdout so only the report JSON reaches the parent. (4)
  Symmetric measurement: head is probed via the same subprocess mechanism as
  main, so startup/GC conditions match.

### Slice 3: CI perf job (closes IMPORTANT #9)
- **Status:** DONE
- **Branch:** `claude/loving-gauss-7h7smy` (environment-designated)
- **PR:** (this PR — draft)
- **ADR:** ADR-176
- **Depends on:** Slice 2 merged ✅ (#178, `750a6a7`)
- **What was done:** Added the `perf` job to `.github/workflows/ci.yml`,
  mirroring the `smoke` job (`needs: lint`, one `ubuntu-latest` runner, no
  matrix). It is **PR-only** (`if: github.event_name == 'pull_request'` — on a
  push to main, head and `origin/main` are the same commit), checks out with
  `fetch-depth: 0`, explicitly materializes the baseline
  (`git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main`), then
  runs `uv run python scripts/perfbench.py --ref origin/main --no-fetch
  -o perf.json`. The job's **non-zero exit gates the merge** (a structural hard
  delta only); the wall-time / peak-MiB alerts are printed but never fail it. It
  uploads `perf.json` (`if: always()`, 7-day retention). No `convert_soa_tables`
  step — the probe uses the committed synthetic fixture, so the job is fast and
  offline-safe; no Dockerfile/`.dockerignore` change (no data file added). Wiring
  pinned by `tests/test_ci/test_workflow_perf_job.py` (10 structural tests).
  README + QUICKSTART note added. Verified locally: `perfbench.py --ref
  origin/main` on this branch → identical fingerprints, ratio ~1.05×, no hard
  delta, exit 0 (this PR touches only CI + tests + docs, so the engine is
  identical head-vs-main and the new gate is green).
- **Key decisions:** (1) PR-only, to avoid a no-op self-compare + fetch race on
  main pushes. (2) Explicit refspec fetch + `--no-fetch` rather than trusting the
  checkout action's default refspec to produce `origin/main`. (3) Never fail on
  the wall-time alert (the group rule) — only the structural exit code gates.

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
  **DONE:** `diff_reports` is unit-tested synthetically; `scripts/perfbench.py`
  drives the real worktree checkout and exits non-zero on a hard delta.
- **Slice 3 wiring (NEXT):** the CI job needs only to `git fetch` + run
  `uv run python scripts/perfbench.py --ref origin/main -o perf.json` on one
  runner, upload `perf.json`, and let the job's exit status gate (non-zero =
  structural hard delta). The wall-time / MiB alerts are already advisory in the
  payload; surface them in the job log / a PR comment without failing the job.
  Mirror the `smoke` job's `needs: lint` + single-runner shape. `perfbench.py`
  fetches `origin/*` refs by default (skip with `--no-fetch`).

## Open Questions (for human)

- **Surface as `polaris perfbench`?** Slice 2 could expose the runner as a CLI
  subcommand or leave it a `scripts/` tool (as B2 did — `scripts/scale_benchmark.py`,
  deliberately not a `polaris` subcommand). Defer to the maintainer's B2
  precedent (script-first) unless a CLI surface is requested.
- **Wall-time alert band + `peak_mib` alert delta — CONFIRMED (maintainer,
  2026-07-31).** The head/main wall-time ratio alert threshold (`band=1.5×`) and
  the peak-memory alert threshold (`mib_alert_delta=4 MiB`) were the policy
  choices surfaced by Slice 2. The maintainer **approved both defaults** on
  PR #178; Slice 3 wires them into CI as-is (both **alert only**, never a hard
  gate — only structural deltas gate). No further human input owed on the
  thresholds; `diff_reports`' defaults stand.

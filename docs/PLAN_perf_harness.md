# Plan — Performance harness with head-vs-main baseline (IMPORTANT #9 → #10)

> **Audience.** A future Claude Code session (or human) that will build the
> performance-regression harness. Read this document fully before writing code,
> then read CLAUDE.md (§5 conventions, the ADR-074 wall-clock guardrail),
> `analytics/scale_benchmark.py` (ADR-161 — the B2 timing harness this reuses),
> and the CI perf/smoke group context in `PRODUCT_DIRECTION_2026-07-24.md`
> (IMPORTANT #8/#9/#10, the maintainer-discussion 2026-07-12 group). This plan
> is the read-only spec, not the running log; the running log is
> `docs/CONTINUATION_perf_harness.md`.
>
> **Status.** ✅ COMPLETE (mandatory scope) — Slices 1 + 2 + 3 shipped. Slice 3
> (the CI `perf` job, ADR-176, PR #179 on `claude/loving-gauss-7h7smy`) runs
> `scripts/perfbench.py --ref origin/main --no-fetch` on one PR-only runner and
> gates the merge on its non-zero exit (a structural hard delta), uploading
> `perf.json` and surfacing the wall-time / MiB alerts non-blocking in the job
> log. The two advisory thresholds — wall-time `band=1.5×` and
> `mib_alert_delta=4 MiB` — were **confirmed by the maintainer (2026-07-31,
> PR #178)** and wired in as-is (alert only, never a hard gate). The optional
> Slice 4 (`perf/history.jsonl` creep log = IMPORTANT #10) may be constituted as
> its own epic; see `CONTINUATION_perf_harness.md`.
>
> **Provenance.** IMPORTANT #9 (+ #10) in `docs/PRODUCT_DIRECTION_2026-07-24.md`,
> the *deterministic companion* to the pass/fail CI smoke gate shipped as
> IMPORTANT #8 (ADR-168, PR #170). *Source: maintainer discussion 2026-07-12
> (CI perf/smoke thread), 1st-order.*

---

## 1. Goal

A performance-regression harness that times the engine's hot paths on a **fixed
synthetic block**, captures **deterministic structural metrics** alongside
**informational wall-clock timing**, and — across later slices — benchmarks the
current worktree ("head") against `origin/main` **in the same CI job** so the
2–3× run-to-run machine noise cancels in the head/main **ratio**. The ratio and
the deterministic metrics are the gate/alert signals; raw wall-time only
informs. A per-merge append-only history log (`perf/history.jsonl`) with creep
detection (IMPORTANT #10) is the follow-on that this harness unblocks.

This closes the gap the B2 scale benchmark (ADR-161) does **not**: B2 publishes a
static committed timing *table* and one `@pytest.mark.slow` scaling-shape test
(4× block < 6× time); it has no per-run head-vs-main comparison, emits no
machine-readable `perf.json`, and cannot catch slow multi-month creep. IMPORTANT
#8 (smoke) proves the entry points *boot*; this proves they have not gotten
*slower*.

## 2. The non-negotiable design rule (maintainer, 2026-07-12)

> **Deterministic / noise-normalized metrics may gate or alert; raw wall-time
> only informs.** GitHub runners vary 2–3× run-to-run, so any gate on absolute
> latency is an alert-fatigue generator.

This rule drives every decision below. Evidence gathered while scoping Slice 1
(a 3 000-policy × 240-month TERM projection, repeated in-process):

| Signal | Observed | Role |
|--------|----------|------|
| Wall-clock (single) | 651 ms first call, then ~290–320 ms | **informational only** — 2× local jitter |
| Wall-clock (best-of-k min) | ~290 ms, stable | informational, but the *stable* estimator |
| `tracemalloc` peak (bytes) | 70 022 484 → 70 018 996 (stable after warmup) | ~0.005% jitter → **not byte-safe to gate** |
| `tracemalloc` peak (MiB-rounded) | 67 MiB every run incl. first | **deterministic at MiB granularity** → gate-safe |
| `n_cells = N × T`, `projection_months` | exact | **exactly deterministic** → gate-safe |
| Output fingerprint (rounded array sums) | exact | **exactly deterministic** → gate-safe (doubles as a correctness tripwire) |

So: gate/alert on the exactly-deterministic counts + the MiB-rounded peak + the
output fingerprint, and on the head/main **ratio** of wall-time (band, not
threshold); never gate on an absolute millisecond number.

## 3. Decomposition (Pattern B — new module, then integration)

Each slice leaves the suite green, is independently mergeable, and is
byte-identical on the goldens (the harness never touches the pricing path).

### Slice 1 — Deterministic perf-probe core (NEXT → shipped this session)
`analytics/perf_harness.py`: `PerfProbe` (one hot-path row) + `PerfReport`
(container, mirroring `ScaleBenchmarkRow`/`ScaleBenchmarkReport`), and
`run_perf_probe(...)` which times a mapping of named hot-path callables (default:
the full production `project()` path) on a `build_homogeneous_block` fixed block,
capturing per probe: `n_policies`, `projection_months`, `n_cells`,
`output_fingerprint` (deterministic digest of the core `CashFlowResult` arrays),
`peak_mib` (MiB-rounded `tracemalloc` peak), and `best_of_k_seconds` + the raw
`samples_seconds` (informational). `PerfReport.to_perf_dict()` / `to_json()`
emit the `perf.json` payload shape. `tests/perf/test_perf_harness.py` verifies:
(a) the harness runs and reports one row per probe; (b) the **deterministic
metrics are byte-reproducible across two independent runs** (the gating
property — the closed-form-style verification); (c) timings are present and
non-negative and `best_of_k <= min(samples)` (arithmetic invariant); (d) input
validation. Register a `perf` pytest marker; tests tagged `perf` **and** `slow`
(they run the engine) so the fast matrix / Docker job skip them. Additive only —
no `src/` pricing change, goldens byte-identical. **ADR-169.** No CI job, no
head-vs-main comparison yet.

### Slice 2 — Head-vs-main same-job driver + `perf.json` diff
A runner (`scripts/perfbench.py`, optionally surfaced as `polaris perfbench`)
that runs the probe on the current worktree and on a `git worktree` checkout of
`origin/main`, computes the noise-cancelling **ratio** per metric, and writes
`perf.json` with a per-metric verdict: a structural-metric mismatch (counts /
fingerprint / MiB-peak) is a **hard delta**; a wall-time ratio outside a
configurable band (e.g. head > 1.5× main best-of-k) is an **advisory alert**.
Deterministic-first ordering so the report reads gate-signals before wall-time.

### Slice 3 — CI perf job (closes IMPORTANT #9) ✅ SHIPPED (ADR-176)
A CI `perf` job (needs `lint`, like the smoke job) that runs the Slice-2
head-vs-main harness on one runner, uploads `perf.json` as an artifact, **gates**
on structural-metric deltas and **alerts** (non-blocking) on the wall-time ratio,
honoring the group rule. QUICKSTART/README note on reading `perf.json`. Wired
PR-only (`if: github.event_name == 'pull_request'` — head == origin/main on a
main push), `fetch-depth: 0` + an explicit `+refs/heads/main:refs/remotes/origin/main`
fetch so the worktree checkout resolves, then `perfbench.py --no-fetch`. Structural
wiring pinned by `tests/test_ci/test_workflow_perf_job.py` (10 tests). No
`convert_soa_tables` step (the probe uses the committed synthetic fixture).

### Slice 4 (optional / follow-on epic = IMPORTANT #10)
Per-merge append-only `perf/history.jsonl` (one deterministic-first row per
merge to main) + creep detection over the series, plus the NICE-TO-HAVE tail
(pr-review perf verdict comment #62; one-off backfill #63). Depends on Slices
1–3 on main. May be constituted as its own epic when #9 closes.

## 4. Design anchors (carry across slices)

- **Reuse B2.** `build_homogeneous_block` and the `get_product_engine(...).project()`
  production path from `analytics/scale_benchmark.py`; do not re-invent block
  construction. The perf harness is a sibling diagnostic module, off the import
  hot path.
- **Pin dates (ADR-074).** Every fixture and default passes an explicit
  `valuation_date`; never `date.today()`. `build_homogeneous_block` already
  requires a caller-pinned `valuation_date`.
- **Best-of-k, not mean.** Timing uses the minimum over `k` samples — the stable
  estimator (the mean is dragged by the first-call/GC outlier).
- **Deterministic metrics gate; wall-time informs.** Enforced structurally: the
  `PerfProbe` marks which fields are deterministic; the CI job (Slice 3) reads
  only those for its gate.
- **Structural fingerprint = correctness tripwire, not a golden.** The
  fingerprint's job is to prove the *same computation* ran head and main so a
  timing delta is apples-to-apples; it is deliberately coarse (rounded sums), not
  a replacement for `tests/qa/` goldens.
- **No new heavy deps.** `time.perf_counter`, `tracemalloc`, `gc`, `hashlib`,
  `resource` — all stdlib. No profiler dependency.
- **Docker/data trap (#61/#66).** No test-referenced data files are added
  (the block is generated in-process), so no Dockerfile COPY / `.dockerignore`
  change is required. Re-check if a later slice commits a fixture.

## 5. Out of scope (for the whole epic unless a slice names it)

- Absolute-latency SLOs / gating on milliseconds (violates the group rule).
- Profiling / flame-graph capture; per-line attribution.
- Product engines beyond TERM in the default probe (the NICE-TO-HAVE
  "benchmark engines beyond TermLife", ADR-161, is a separate follow-up; the
  harness accepts a caller-supplied engine so it is not blocked).
- Multi-worker / concurrency load testing (that is C6, Phase-6.3, distinct).

## 6. Acceptance criteria (epic)

- [x] `perf.json` machine-readable payload emitted for the engine hot paths (S1 shape; S2 populates head/main).
- [x] Deterministic structural metrics reproducible run-to-run and used as the gate (S1 proves reproducibility; S3 gates).
- [x] Head-vs-main noise-cancelling ratio computed in a single job (S2).
- [x] CI job gates on structural deltas, alerts (non-blocking) on wall-time ratio (S3, ADR-176).
- [x] Goldens byte-identical throughout (harness never touches the pricing path).

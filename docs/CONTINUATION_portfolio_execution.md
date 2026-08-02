# Continuation: Portfolio execution — lifecycle, caching, parallel run

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — re-ranked catalogue **Tier C, C4**
("Parallel portfolio execution + caching + `remove_deal`", ★★★☆☆, ~2 d)
**Plan:** `docs/PLAN_portfolio_execution.md`
**Status:** COMPLETE (all 3 slices shipped — #181 / #182 / Slice 3 this session;
refinement backlog and the one surviving open question promoted to
`PRODUCT_DIRECTION_2026-07-24.md` "Harvested 2026-08-02 (portfolio parallel
execution — ADR-180; C4 Slice 3 — CLOSES C4)" before this transition, per routine
step 17/18)
**Total slices:** 3
**Estimated total scope:** ~2 dev-days

## Overall Goal

Turn `analytics/portfolio.py::Portfolio` from a write-once builder into a book a
reinsurer can actually work with: edit it (drop / re-quote a deal, ask the
what-if without rebuilding from source), re-run it cheaply (per-deal result
caching with correct invalidation), and run it fast on a large book (parallel
per-deal projection). Every slice keeps results byte-identical — this is an
execution / ergonomics epic, not a modelling change.

## Decomposition

### Slice 1: Deal lifecycle API (`remove_deal` and friends)
- **Status:** DONE
- **Branch:** `claude/quirky-ramanujan-25chda` (environment-designated)
- **PR:** #181
- **ADR:** 178
- **What was done:** Added the read surface (`__len__`, `__contains__`,
  `deal_ids`, `get_deal`), the mutating verbs (`remove_deal`,
  `replace_deal` — position-preserving, `clear_deals`), and the non-mutating
  what-if copy `without_deal(*deal_ids, name=None)`. The single-product-block and
  proportional-treaty validation moved into a module-level `_build_deal` choke
  point shared by `add_deal` and `replace_deal`. Unknown ids raise
  `PolarisValidationError` everywhere — never a silent no-op (a repeated id in
  `without_deal` is rejected on the same principle). 41 new tests;
  `run()` and the aggregation untouched, goldens byte-identical.
- **Key decisions (affect later slices):**
  - Mutation is now a **named, interceptable operation** on exactly four verbs
    (`add_deal`, `remove_deal`, `replace_deal`, `clear_deals`). Slice 2's cache
    invalidation hooks these four and nothing else — do not add a fifth mutation
    path without an invalidation hook.
  - `_deals` stays private; `without_deal` builds the copy by appending to the
    new instance's `_deals` (same pattern as `_with_scenario`). A copy shares the
    frozen `Deal` objects — Slice 2 must therefore NOT let a copy inherit the
    parent's cache dict by reference.
  - `replace_deal` preserves position deliberately (see ADR-178 alternative (d)).
    Slice 3's parallel collection is index-based, so position stability matters.

### Slice 2: Per-deal result caching
- **Status:** DONE
- **Branch:** `claude/quirky-ramanujan-xa6fr5` (environment-designated)
- **PR:** #182
- **ADR:** 179
- **What was done:** Memoised `_run_deal(deal, hurdle_rate)` on the instance,
  **opt-in** via `Portfolio(name=..., cache=True)` (the open question below is
  now resolved in favour of the constructor). The projection body moved
  unchanged to `_project_deal`; `_run_deal` is the memoisation wrapper, so the
  cache is one choke point. All four Slice-1 mutation verbs invalidate — **per
  deal**, not book-wide — and both `add_deal` and `replace_deal` now build and
  validate the `Deal` *before* mutating, so a rejected edit leaves the cache
  intact. `without_deal` carries the surviving entries over **by value** (same
  frozen `Deal`s, same ids → the entry describes exactly the projection the copy
  would perform), which collapses a leave-one-out sweep from `N x (N-1)`
  projections to `N`; `_with_scenario` deliberately starts **empty**.
  `clear_cache()` is the escape hatch for in-place input mutation and
  `cache_stats() -> CacheStats(enabled, hits, misses, size)` is the timing-free
  observability surface. 34 new tests; cached and uncached runs bit-identical,
  goldens untouched.
- **Key decisions (affect later slices):**
  - The cache is a plain `dict[tuple[str, float], tuple[DealResult,
    CashFlowResult]]` on the instance with **no locking**. Two threads missing
    on the same key would both project — harmless to correctness (the values are
    equal) but it wastes exactly what the cache saves and breaks the
    `cache_stats()` miss count as a proxy for work done.

    **Measured on this branch (PR #182 review round), because the exposure
    depends entirely on the fan-out shape:**

    | fan-out shape | 4 workers | 8 workers | ideal |
    |---|---|---|---|
    | **A** — one task per deal inside one `run()` (*the planned shape*) | 3 misses | 3 misses | 3 |
    | **B** — concurrent `run()` calls sharing one cold portfolio | 7 misses | 11 misses | 3 |

    Shape **A** — what Slice 3 actually plans — touches each key exactly once,
    so there is **no duplicate-miss problem to solve** and no need for a
    resolve-hits-then-fan-out-misses structure; adding one would be complexity
    without a defect. The duplicate work is real only in shape **B**, which is a
    *different* scenario: several callers sharing one `Portfolio` concurrently.
    If Slice 3 (or a service layer) ever enables that, the fix is per-key
    locking or a single-flight guard, not a change to the intra-run fan-out.
    The review round reported 14 misses at 8 workers as if it applied to the
    planned shape; re-running both shapes separately shows it belongs to B.
    Threaded execution was **bit-identical to serial at 2, 4 and 8 workers** in
    both shapes.
  - **The no-locking argument assumes the GIL.** `self._cache_hits += 1` is a
    read-modify-write across several bytecodes, and the `_deal_cache` write-back
    is a dict mutation; both are effectively atomic only because CPython's
    switch interval makes the window vanishing. Attempting to force a lost
    update failed — **6000 contended all-hit lookups at 128 workers lost zero**
    — so this is a non-issue today and needs no code. It stops being
    theoretical on a **free-threaded build (3.13t+)**, where both lose their
    implicit atomicity. `pyproject.toml` targets 3.12+, so this is written down
    rather than acted on; whoever evaluates a free-threaded runtime should find
    the assumption stated instead of rediscovering it. Even then the failure
    mode is an undercounted hit rate (`cache_stats()` is observability only),
    not a wrong price.
  - **Cached results are handed out live and writeable** — the same ndarray
    objects across runs, and shared between a portfolio and its `without_deal`
    copy. Safe in-module (`_place` always allocates; nothing writes through),
    but a *caller* who writes into a returned array corrupts every later run:
    measured, the aggregate PV moved 27,089.56 → 37,248.14 silently. Nothing
    in-tree does this (the dashboard reads scalars only) and `clear_cache()`
    recovers. Slice 3 must not introduce any write-through path, and the
    `_place` allocation must stay unconditional (a guard comment now says so at
    the function itself).
  - `align` is *not* part of the key. `_run_deal` returns `grid_offset=0` and
    `run` stamps the real offset onto a `dataclasses.replace` copy, so the
    cached value is never mutated by a run. Slice 3's index-ordered collection
    must keep doing the `replace` on its own copy, not in place.
- **Acceptance criteria:** all met — see the session log's table.

### Slice 3: Parallel execution
- **Status:** DONE
- **Branch:** `claude/quirky-ramanujan-5zhsw3` (environment-designated)
- **PR:** #183
- **ADR:** 180
- **What was done:** `run(..., max_workers: int | None = None)`, forwarded by
  `run_with_capital` and `run_scenarios` (the *scenarios* stay sequential; only
  the per-deal projections fan out). `None` and `1` — and a book of fewer than
  two deals — take the serial path, and no `ThreadPoolExecutor` is constructed
  there at all (a test asserts it by making the constructor raise). The fan-out
  is one task per deal collected by input position (`Executor.map`), so the
  order-sensitive aggregation sum is bit-identical at any worker count and each
  cache key is still touched exactly once, keeping ADR-179's no-single-flight
  decision valid rather than quietly invalidating it. `max_workers` is validated
  before any projection (`bool` rejected explicitly). The cache dict and its two
  counters are now lock-guarded — never a projection — because this slice turns
  concurrent `_run_deal` from a hypothetical into a shipped path. 34 new tests;
  goldens byte-identical.
- **The measurement gate came back below the bar, and the claim was not made.**
  `scripts/bench_portfolio_parallel.py` (committed) times a **cold** portfolio
  (fresh `cache=False` per sample) with the harness's best-of-k minimum and
  proves bit-identical aggregates before reporting any ratio. On the 4-core
  runner: **1.29x** at 4 workers on 4 deals x 20k policies, but **1.19x / 0.59x /
  0.48x** at 2 / 4 / 8 workers on 8 deals x 5k — i.e. *slower than serial* where
  per-deal blocks are small. Reproduced across independent invocations. Cause:
  the projection is GIL-bound by the engines' `for month in range(t)` recursions,
  so larger `N` (longer C sections per handoff) scales and smaller `N` regresses.
  The knob therefore ships **off by default with the negative numbers in its own
  docstring**, no speed-up is claimed anywhere in the docs, and the disposition
  is flagged for the maintainer (see Open Questions).
- **Original scope (for the record):** `run(..., max_workers: int | None = None)`; `None` keeps today's
  serial path as the default; `>1` runs `_run_deal` through a
  `ThreadPoolExecutor`, collecting **by deal index** so the order-sensitive
  aggregation sum stays bit-identical. Threads not processes (NumPy releases the
  GIL in the large `(N × T)` ufuncs; a process pool would pickle every
  `InforceBlock` / `MortalityTable`).
  **Measurement gate:** publish a real speed-up measured through
  `analytics/perf_harness.py` on a multi-deal portfolio, or ship the measurement
  and *not* the parallel claim.
- **Acceptance criteria:**
  - `max_workers=4` equals the serial result under `assert_array_equal` (exact,
    not `allclose`); deal order preserved; invalid `max_workers` rejected.
  - **The benchmark runs a COLD portfolio** (`cache=False`, or `cache=True` on
    its first `run`). This is easy to satisfy accidentally in the wrong
    direction: a warm cache makes a re-run free to parallelise and would show an
    arbitrarily good speed-up that measures nothing. State in the ADR which was
    measured.
  - The fan-out keeps **one task per deal**, so each cache key is touched
    exactly once — verified at 2/4/8 workers to cost exactly `n_deals`
    projections on a cold cache (see Slice 2's key decisions). If the shape ever
    changes to one where several tasks can share a key, add a single-flight
    guard *and* a duplicate-projection regression test.
  - Goldens byte-identical; the serial path stays the default.

## Context for Next Session

- The premise was reproduced before any code (routine step 7b): `dir(Portfolio)`
  exposed exactly `add_deal / deals / n_deals / name / run / run_scenarios /
  run_with_capital` — no removal, replacement, or lookup verb existed.
- Slice 1's tests were confirmed **red** (39 failed) with the implementation
  stashed and **green** (39 passed) with it applied.
- Slice 2's premise was reproduced the same way, with a counter at the
  `get_product_engine` boundary on a three-deal book: `run` / re-`run` /
  `run_with_capital` / `without_deal(...).run` cost **3 / 3 / 3 / 2** engine
  builds where 3 in total would do. Its tests were confirmed red (collection
  fails on the missing `CacheStats` export) and green 34/34 with the
  implementation applied. (28 test functions, expanding to 34 collected via the
  two `parametrize`d sweeps — confirmed by the suite total moving 2845 → 2879.
  An earlier "36" here was the `pytest -k Cache` count, which case-insensitively
  sweeps in two pre-existing lifecycle tests; corrected per PR #182 review [P2].)
- **Slice 3 starts from a warm cache, and that changes the measurement.** With
  `cache=True` a re-run costs nothing to parallelise, so the honest benchmark is
  a **cold** portfolio (`cache=False`, or `cache=True` on its first `run`) over a
  book big enough that per-deal projection dominates. Do not measure a second
  run of a caching portfolio and report the speed-up as parallelism.
- Slice 3 must decide how the two features compose: the simplest correct shape is
  to resolve cache hits serially first, fan out only the misses, and write the
  results back under the existing per-deal eviction contract.
- The three `Portfolio` surfaces (CLI `polaris portfolio run`,
  `POST /api/v1/portfolio`, the Streamlit portfolio page) all construct a fresh
  `Portfolio` per request. None of them is touched by this epic, and none needs
  to be for Slices 2–3 — but that is also why *surfacing* incremental what-if is
  explicitly out of scope (it needs a session/state design first).
- Considered and rejected for Slice 1: a `marginal_contribution()` analytic built
  on `without_deal`. The leave-one-out loop is now a two-liner (a test
  demonstrates the exact identity), but a real attribution surface — marginal PV,
  marginal capital, marginal concentration — is its own feature with its own ADR,
  and folding it in would have made this slice a modelling change instead of an
  ergonomics one.

## Open Questions (for human)

- ~~**Slice 2 cache opt-in shape.**~~ **RESOLVED** in ADR-179 decision point 1:
  constructor-level `Portfolio(name=..., cache=True)`. The assertion the caller
  makes ("these deals' inputs are frozen for as long as I hold this portfolio")
  is a property of how the portfolio is *held*, not of one run, and a per-call
  flag would let two runs of the same portfolio disagree about whether the deals
  are frozen. `run` / `run_with_capital` / `run_scenarios` signatures unchanged.
- **Slice 3 measurement threshold.** **STILL OPEN — now a concrete decision, and
  promoted to `PRODUCT_DIRECTION_2026-07-24.md` as IMPORTANT so it survives this
  CONTINUATION's close.** The measurement is in (ADR-180): peak **1.29x**, and
  **slower than serial** (0.48–0.59x) at 4/8 workers on small per-deal blocks, on
  a 4-core runner. That is below both thresholds this question floated, so on the
  plan's own terms it is the "ship the measurement, not the claim" branch — and no
  claim is made. Slice 3 reported and recommended rather than deciding: the knob
  was **kept**, off by default, for one reason only — a 4-core measurement is a
  thin basis for deleting a feature that may pay on a 32-core workstation, and
  `scripts/bench_portfolio_parallel.py` is the instrument for re-measuring there.
  Removing the parameter is a small self-contained revert if you prefer the
  stricter reading; the benchmark and the ADR are worth keeping either way.

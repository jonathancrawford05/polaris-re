# Continuation: Portfolio execution — lifecycle, caching, parallel run

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — re-ranked catalogue **Tier C, C4**
("Parallel portfolio execution + caching + `remove_deal`", ★★★☆☆, ~2 d)
**Plan:** `docs/PLAN_portfolio_execution.md`
**Status:** IN PROGRESS
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
    CashFlowResult]]` on the instance with **no locking**. Slice 3 must either
    pre-populate it before the fan-out or guard it: two threads missing on the
    same key would both project (harmless to correctness — the values are
    equal — but it wastes exactly what the cache saves, and it would break the
    `cache_stats()` miss count as a proxy for work done).
  - `align` is *not* part of the key. `_run_deal` returns `grid_offset=0` and
    `run` stamps the real offset onto a `dataclasses.replace` copy, so the
    cached value is never mutated by a run. Slice 3's index-ordered collection
    must keep doing the `replace` on its own copy, not in place.
  - Cached results are handed out **by reference** — two runs share the same
    numpy arrays. Nothing in the module writes through them (`_place` /
    `np.sum` build new arrays); Slice 3 must preserve that, since a threaded
    path writing into a per-deal array would now corrupt a cached entry.
- **Acceptance criteria:** all met — see the session log's table.

### Slice 3: Parallel execution
- **Status:** NEXT
- **Depends on:** Slice 2 merged
- **Scope:** `run(..., max_workers: int | None = None)`; `None` keeps today's
  serial path as the default; `>1` runs `_run_deal` through a
  `ThreadPoolExecutor`, collecting **by deal index** so the order-sensitive
  aggregation sum stays bit-identical. Threads not processes (NumPy releases the
  GIL in the large `(N × T)` ufuncs; a process pool would pickle every
  `InforceBlock` / `MortalityTable`).
  **Measurement gate:** publish a real speed-up measured through
  `analytics/perf_harness.py` on a multi-deal portfolio, or ship the measurement
  and *not* the parallel claim.

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
- **Slice 3 measurement threshold.** If threaded execution turns out to give only
  a marginal speed-up on a realistic book, the honest outcome is to ship the
  measurement and drop the `max_workers` knob. What speed-up is worth the extra
  API surface — 1.5×? 2×? Absent guidance, Slice 3 will report the measured
  number and recommend, not decide unilaterally.

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
  `PolarisValidationError` everywhere — never a silent no-op. 39 new tests;
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
- **Status:** NEXT
- **Depends on:** Slice 1 merged
- **Files to create/modify:** `src/polaris_re/analytics/portfolio.py`,
  `tests/test_analytics/test_portfolio.py`, `docs/DECISIONS.md` (ADR-179)
- **Scope:** Memoise `_run_deal(deal, hurdle_rate)` on the instance, keyed
  `(deal_id, hurdle_rate)`; invalidate from all four mutation verbs; **opt-in**
  (the ADR decides `Portfolio(cache=True)` vs `run(use_cache=True)`) because
  `Deal` holds mutable projection inputs a caller could change behind the
  portfolio's back; `_with_scenario` must start with an empty cache (its deals
  carry scaled assumptions under the *same* deal ids).
- **Tests to add:** cached vs uncached byte-identical (`assert_array_equal`);
  one invalidation regression test per mutation verb; a repeat run performs zero
  extra `project()` calls (assert with a call counter, never a timing);
  `run_scenarios` unaffected; `run` then `run_with_capital` reuses the cache.
- **Acceptance criteria:**
  - A cached run and an uncached run produce identical `PortfolioResult` numbers.
  - Mutating between two runs yields the post-mutation answer, per verb.
  - A second `run(h)` at the same hurdle rate calls `project()` zero times.
  - Goldens byte-identical; caching off by default.

### Slice 3: Parallel execution
- **Status:** PLANNED
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

- **Slice 2 cache opt-in shape.** `Portfolio(name=..., cache=True)` (portfolio-wide
  policy, set once) vs `run(..., use_cache=True)` (per-call). Leaning
  constructor-level: the "these deals are frozen for the duration" assertion is a
  property of how the caller holds the portfolio, not of one run. Will be decided
  in ADR-179 unless the maintainer prefers otherwise.
- **Slice 3 measurement threshold.** If threaded execution turns out to give only
  a marginal speed-up on a realistic book, the honest outcome is to ship the
  measurement and drop the `max_workers` knob. What speed-up is worth the extra
  API surface — 1.5×? 2×? Absent guidance, Slice 3 will report the measured
  number and recommend, not decide unilaterally.

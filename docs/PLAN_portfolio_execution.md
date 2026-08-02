# Plan: Portfolio execution — deal lifecycle, result caching, parallel run

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — re-ranked catalogue **Tier C, C4**
("Parallel portfolio execution + caching + `remove_deal`", ★★★☆☆, ~2 d), backed by
`COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §4.
**Classification:** MEDIUM (3 slices) — three distinct capabilities on one module,
each independently mergeable.
**Status:** slice 1 shipped; see `docs/CONTINUATION_portfolio_execution.md`.

---

## 1. Why

`analytics/portfolio.py::Portfolio` is a **write-once builder**: `add_deal` is the
only verb. Once a deal is in the portfolio it cannot be removed, replaced, or even
looked up by id — `deals` is an immutable tuple view and `_deals` is private. Three
consequences, which are exactly the three halves of catalogue item C4:

1. **No incremental what-if.** "What does the book look like without DEAL_C?" or
   "re-quote DEAL_B at 40% cession" forces the caller to rebuild the whole
   portfolio from the source objects — re-parsing the deal file on the CLI path,
   re-uploading on the dashboard path. This is the single most natural portfolio
   question a reinsurer asks and today it has no API.
2. **No caching.** Every `run()` / `run_with_capital()` / `run_scenarios()` call
   re-projects every deal from scratch. Two `run()` calls at different hurdle
   rates, or a `run()` followed by `run_with_capital()`, pay the full projection
   cost twice even though nothing about the deals changed.
3. **Serial execution.** `run()` loops `self._deals` one at a time. Deals are
   *completely independent* until the aggregation sum — an embarrassingly parallel
   shape that the loop does not exploit.

(1) is the prerequisite for (2): a cache is only safe if every mutation path is
known, so the mutation API must exist and be the single choke point before results
are memoised. (3) is independent of both.

## 2. Non-negotiable constraints

- **Byte-identical results.** None of the three slices may change a single number.
  Every slice keeps `tests/qa/` goldens byte-identical; the parallel slice must
  produce bit-for-bit the same aggregate as the serial path (deal order preserved
  in the aggregation sum, which is float-order-sensitive).
- **No core-contract change.** `Deal`, `DealResult`, `PortfolioResult`,
  `CashFlowResult` are untouched. Everything is additive on `Portfolio`.
- **Mutation must be explicit.** No method silently no-ops on an unknown deal id —
  a silent no-op in a what-if flow produces a *wrong answer that looks right*.
  Unknown id → `PolarisValidationError`.
- **No perf claim without a measurement.** Slice 3 ships a number produced by the
  committed perf harness or it does not ship the claim.

## 3. Slices

Each slice leaves the suite green, the goldens byte-identical, and is mergeable
on its own.

### Slice 1 — Deal lifecycle API (`remove_deal` and friends) ✅

Builder-level only; `run()` and its aggregation are untouched.

- `__len__`, `__contains__`, `deal_ids`, `get_deal` — read/lookup surface.
- `remove_deal(deal_id)` — mutating, chainable, raises on unknown id.
- `replace_deal(...)` — mutating, **position-preserving**, same validation as
  `add_deal` (so a replacement cannot smuggle in a multi-product block or a
  non-proportional treaty).
- `clear_deals()` — mutating, chainable.
- `without_deal(*deal_ids, name=None)` — **non-mutating** copy, the what-if
  primitive (mirrors the existing `_with_scenario` copy pattern).
- Validation extracted to one `_build_deal` choke point shared by `add_deal` and
  `replace_deal`, so the two can never drift.

Acceptance: a portfolio built with 3 deals then `remove_deal("b")` produces an
aggregate that is *identical* to a portfolio built with only the other two, and
`total_pv_profits` equals the closed-form sum of the two survivors' PVs.

### Slice 2 — Per-deal result caching

- Memoise `_run_deal(deal, hurdle_rate)` keyed on `(deal_id, hurdle_rate)`, held
  on the `Portfolio` instance.
- **Every** Slice-1 mutation verb (`add_deal`, `remove_deal`, `replace_deal`,
  `clear_deals`) invalidates — that is the reason Slice 1 comes first.
- **Opt-in**, not default (`Portfolio(..., cache=True)` or `run(use_cache=True)` —
  decide in the slice's ADR). Rationale: `Deal` holds *mutable* objects
  (`InforceBlock`, `AssumptionSet`, `ProjectionConfig`, `BaseTreaty`); a caller
  who mutates an assumption in place behind the portfolio's back would get a
  stale result from an always-on cache. Opt-in makes the caller's "these deals
  are frozen for the duration" assertion explicit.
- `_with_scenario` must **not** inherit the parent's cache (its deals carry
  scaled assumptions under the same deal ids — the one case where the key would
  collide with a genuinely different projection).
- Acceptance: cached and uncached runs are byte-identical; a mutation between two
  runs yields the post-mutation answer (a cache-invalidation regression test per
  verb); a repeat run performs zero additional `project()` calls (asserted with a
  call counter, not a timing).

### Slice 3 — Parallel execution

- `run(..., max_workers: int | None = None)`; `None` = today's serial path
  (default unchanged), `>1` = `ThreadPoolExecutor` over `_run_deal`.
- Results collected **by deal index**, never by completion order, so the
  aggregation sum keeps its order and stays bit-identical.
- Threads (not processes) because the payload is NumPy-heavy — the GIL is
  released inside the large `(N × T)` ufunc calls, and a process pool would have
  to pickle every `InforceBlock` / `MortalityTable`.
- **Measurement gate:** the slice must publish a real speed-up measured through
  `analytics/perf_harness.py` on a multi-deal portfolio. If threads do not
  measurably help, the honest outcome is to ship the measurement and *not* the
  parallel claim — record that in the ADR rather than shipping a knob that does
  nothing.
- Acceptance: `max_workers=4` result equals the serial result under
  `assert_array_equal` (exact, not `allclose`); order preserved; invalid
  `max_workers` rejected; a `@pytest.mark.slow` timing test.

## 4. Out of scope for the whole epic

- Surfacing any of this on the CLI / REST / dashboard (the portfolio surfaces
  build a fresh `Portfolio` per request; incremental what-if over a *session* is
  a separate design question).
- Process-based parallelism and any distributed execution.
- Persisting a cache across processes.
- Non-proportional treaties in a portfolio (a standing `Portfolio` limitation,
  unrelated to C4).

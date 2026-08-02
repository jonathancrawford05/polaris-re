# Dev Session Log — 2026-08-02 (portfolio per-deal result cache)

## Item Selected
- **Source:** `docs/CONTINUATION_portfolio_execution.md` (IN PROGRESS) — the
  CONTINUATION **is** the work selection under routine step 5, so steps 5b and 6
  were skipped. Backing catalogue entry: `PRODUCT_DIRECTION_2026-07-24.md`
  re-ranked catalogue **Tier C, item C4** ("Parallel portfolio execution +
  caching + `remove_deal`", ★★★☆☆, ~2 d).
- **Priority:** Tier-C epic, slice 2 (see Selection Rationale).
- **Title:** Portfolio per-deal result caching — opt-in `Portfolio(cache=True)`.
- **Slice:** 2 of 3.
- **Branch:** `claude/quirky-ramanujan-xa6fr5` (environment-designated; the
  environment override in routine step 8 takes precedence over the `feat/auto-*`
  default).

## Selection Rationale

**Step 5 found a live continuation, so nothing else was considered.**
`docs/CONTINUATION_portfolio_execution.md` is IN PROGRESS with Slice 2 marked
NEXT and "depends on: Slice 1 merged". Slice 1's PR **#181 is merged** (merge
commit `a160246` on `origin/main`, 2026-08-02T19:36Z) and there are **no open
PRs**, so the step-5 draft rule does not bite: the session continues on a new
branch from `main`. Per step 5c that decides the work — steps 5b (active epic)
and 6 (fallback selection) were correctly skipped, and no Tier-B/C/D fallback
was picked alongside.

The other IN PROGRESS continuation, `reserve_basis_correctness`, remains
explicitly *deprioritised / parked* and is not the active epic, exactly as the
prior two sessions recorded.

**Review staleness re-checked.** `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is
**18 days** old on 2026-08-02 — inside the ~30-day regeneration trigger, so no
regeneration is due. (Verified again rather than inherited; the 2026-08-01 log's
">30 days" claim was an arithmetic error corrected on 2026-08-02.)

**Ledger healing (step 4b).** One PR merged since the last session log: **#181**.
Its `PRODUCT_DIRECTION_2026-07-24` C4 entry already carried "Slice 1 SHIPPED"
from the authoring session but not the merge; it now records **MERGED to main
`a160246`** in the house style, plus Slice 2. No entry was deleted.

**PRUNE (step 6 sanity step).** Scanned the latest PRODUCT_DIRECTION for entries
whose acceptance criteria are already satisfied on `main`. Nothing new to close:
the 2026-08-02 sessions already struck through IMPORTANT #10 (PR #180) and
annotated the auto-append item as *narrowed, not closed*. No item was pruned by
inspection this session.

## Verify Premise (step 7b)

Reproduced with a counter at the `get_product_engine` boundary on a three-deal
book, before writing any code:

```
public surface: [... 'run', 'run_scenarios', 'run_with_capital', 'without_deal']
has cache kwarg: False
run(0.10) #1                           -> 3 engine builds
run(0.10) #2, identical inputs         -> 3 engine builds
run_with_capital(0.10) after run(0.10) -> 3 engine builds
without_deal('C').run(0.10)            -> 2 engine builds
PV identical across the two runs: True
```

11 projections where 3 would do, and the two `run(0.10)` calls returned an
identical PV — i.e. the recomputation is provably pure waste. The premise holds
exactly as `PLAN_portfolio_execution.md` §1(2) states; **no correction to the
entry was needed.**

Red-green was verified explicitly: with the implementation stashed the new
suite is red (collection fails on the missing `CacheStats` export); with it
applied, 34/34 pass.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Deal lifecycle API — `remove_deal` / `replace_deal` / `clear_deals` / `without_deal` + lookup surface | ✅ Done | #181 (merged) |
| 2 | Per-deal result caching keyed `(deal_id, hurdle_rate)`, invalidated by all four mutation verbs, opt-in | ✅ Done | #182 |
| 3 | Parallel per-deal execution (`max_workers`, thread pool, index-ordered collection) behind a measurement gate | ⏳ Next | — |

## What Was Done

Added an **opt-in** per-deal result cache to `analytics/portfolio.py::Portfolio`
(ADR-179). `Portfolio(name=..., cache=True)` memoises `_run_deal` on the
instance keyed `(deal_id, hurdle_rate)`; the projection body moved unchanged into
a new `_project_deal` so `_run_deal` is purely the memoisation wrapper and there
is exactly one place the cache can be consulted or filled. Caching is off by
default and the numbers are bit-identical either way — the flag only decides
whether a projection is recomputed or reused.

Two design points carry the weight. First, **invalidation is per deal, not
book-wide.** `_run_deal`'s result depends only on the deal and the hurdle rate,
so adding or dropping a *different* deal cannot change it, and the aggregation —
which does depend on the whole book — is recomputed on every run regardless.
Book-wide invalidation would be correct but would make an incrementally built
book re-project everything on each `add_deal`, which is the flow both the CLI and
the API use. All four Slice-1 mutation verbs hook in (`add_deal`'s eviction is
belt-and-braces: the duplicate check means no live entry can carry that id, but
evicting anyway holds the invariant "a cached entry always describes a deal the
book currently holds" by construction rather than by argument, and closes the
remove-then-re-add-with-different-terms trap outright). `add_deal` and
`replace_deal` now build and validate the `Deal` *before* mutating anything, so a
rejected edit leaves the book **and** the cache untouched.

Second, **the two copy helpers deliberately differ**, because their deals do. A
`without_deal` copy holds the *same frozen `Deal` objects* under the same ids, so
a cached `(deal_id, hurdle_rate)` entry describes exactly the projection the copy
would perform — carrying the surviving entries over by value is sound, and it is
what collapses a leave-one-out sweep over an `N`-deal book from `N × (N-1)`
projections to `N` (a test asserts the whole sweep costs **zero** re-projections
while still recovering each deal's PV contribution). A `_with_scenario` copy
holds deals with the same ids but **scaled assumptions** — the one case where the
key would collide with a genuinely different projection — so it starts empty; a
test asserts every stressed scenario still moves off BASE. Neither copy shares
the parent's dict object. Rounding it out: `clear_cache()` is the escape hatch
for the one staleness the portfolio cannot detect (an input mutated in place
rather than through `replace_deal`), and `cache_stats() ->
CacheStats(enabled, hits, misses, size)` is the observability surface that lets a
caller confirm the cache is working **without a wall-clock timing**, consistent
with the group's standing "deterministic metrics may gate, raw wall-time only
informs" rule.

`run` / `run_with_capital` / `run_scenarios` keep their signatures, the
aggregation is untouched, and both user-facing construction sites
(`cli.py:3154`, `api/main.py:863`) pass `name=` by keyword, so nothing moves for
them. Slice 3's constraints are recorded in the CONTINUATION: the cache dict has
no locking (two threads can both miss on one key — wasteful, not incorrect),
`align` must stay out of the key, and cached arrays are handed out by reference
so a threaded path must not write through them.

## Files Changed
- `src/polaris_re/analytics/portfolio.py` — `CacheStats`; `cache` constructor
  kwarg; `cache_enabled` / `cache_stats()` / `clear_cache()` / `_evict_deal`;
  invalidation in the four mutation verbs; cache-aware `_run_deal` +
  extracted `_project_deal`; cache handling in `without_deal` and
  `_with_scenario`; module + class docstrings.
- `tests/test_analytics/test_portfolio.py` — 34 new tests across five classes,
  plus two shared helpers (`_count_engine_builds`,
  `_assert_portfolio_results_identical`) and a `cache=` parameter on the
  existing `_three_deal_portfolio` builder.
- `docs/DECISIONS.md` — **ADR-179**.
- `ARCHITECTURE.md` — Portfolio Aggregation paragraph.
- `docs/PLAN_portfolio_execution.md` — Slice 2 marked shipped; the opt-in-shape
  question recorded as resolved.
- `docs/CONTINUATION_portfolio_execution.md` — Slice 2 DONE with its key
  decisions for Slice 3; Slice 3 promoted to NEXT; the cache-shape Open
  Question struck through as RESOLVED; Slice-3 measurement guidance added.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — C4 entry updated (PR #181 **MERGED**
  ledger healing + Slice 2 shipped); 2026-08-02 Slice-2 harvest section.
- `perf/history.jsonl` — one appended row (ADR-177 / routine step 14b).

## Tests Added

`tests/test_analytics/test_portfolio.py` (+34):
- `TestPortfolioCacheDefaults` (4) — cache off by default; **the premise itself
  as a regression test** (two runs of a default portfolio build 6 engines for 3
  deals); a disabled portfolio records no stats; `clear_cache()` is a chainable
  no-op when disabled.
- `TestPortfolioCacheCorrectness` (11) — a cached run **bit-identical** to an
  uncached one on every aggregate array, every cash-flow component, every scalar
  and both concentration/HHI mappings (`assert_array_equal` and `==`, never
  `allclose`); `@pytest.mark.parametrize` over four hurdle rates; a second run
  building **zero** product engines; a new hurdle rate being a miss, with the two
  rates cached side by side and no cross-contamination;
  `run_with_capital` reusing what `run` cached and matching an uncached
  `run_with_capital` including `pv_capital` / `return_on_capital` /
  `capital_by_period`; `align="calendar"` served from the same entry with
  offsets `[0, 12]`; `clear_cache()` forcing re-projection to identical numbers.
- `TestPortfolioCacheInvalidation` (10) — one regression test per mutation verb
  plus a `@pytest.mark.parametrize` sweep over all four asserting the cached
  portfolio's post-mutation answer equals an uncached portfolio's;
  remove-then-re-add the same id with different terms (the staleness trap the
  key invites); replacement re-projecting **exactly one** deal; `add_deal`
  keeping the other entries; `clear_deals` emptying the cache; a rejected
  replacement leaving the cache intact.
- `TestPortfolioCacheCopies` (7) — flag inheritance both ways; a `without_deal`
  copy reusing the surviving entries at zero engine builds and *not* carrying the
  excluded deal's; no shared dict object (clearing the copy leaves the parent
  intact); nothing carried from an uncached parent; the leave-one-out sweep at
  **zero** re-projections still recovering each deal's PV contribution; scenario
  copies starting empty so `MORT_110` / `MORT_90` still move off BASE;
  `run_scenarios` leaving the parent's cache untouched.
- `TestPortfolioCacheStats` (2) — hits / misses / size across two runs and a
  second hurdle rate; `clear_cache()` dropping entries while keeping the
  lifetime counters.

## Acceptance Criteria

Taken from `CONTINUATION_portfolio_execution.md` Slice 2.

| Criterion | Status | Notes |
|-----------|--------|-------|
| A cached run and an uncached run produce identical `PortfolioResult` numbers | ✅ | `_assert_portfolio_results_identical` — `assert_array_equal` on 9 arrays + exact `==` on 6 scalars and both concentration mappings; parametrized over 4 hurdle rates |
| Mutating between two runs yields the post-mutation answer, per verb | ✅ | One test per verb + a parametrized sweep over all four against a freshly built portfolio |
| A second `run(h)` at the same hurdle rate calls `project()` zero times | ✅ | Counter at the `get_product_engine` boundary, never a timing |
| `run` then `run_with_capital` reuses the cache | ✅ | Zero engine builds; capital metrics match the uncached run |
| `run_scenarios` unaffected | ✅ | Every scenario bit-identical to the uncached run; stresses still move off BASE |
| `_with_scenario` starts with an empty cache | ✅ | Asserted behaviourally (stresses not masked) and by the parent's `size` staying 3 |
| A `without_deal` copy does not inherit the parent's cache **by reference** | ✅ | Own dict; clearing the copy leaves the parent at `size` 3 |
| Caching off by default | ✅ | `Portfolio().cache_enabled is False`; the 6-engine-builds premise test |
| Goldens byte-identical | ✅ | `tests/qa/` 94 passed; flat golden cedant PV $3,513,563 / reinsurer PV $45,386 |
| Quality gate (ruff format + check, fast suite, qa suite) | ✅ | ruff clean on `src/ tests/`; 2879 passed, 3 skipped (see Baseline) |

## Perf History

Row appended to `perf/history.jsonl` for this branch's feature-commit HEAD
(`30e73b6`): **yes** (initial PR open, step 14b), committed separately as
`4a9861e` so the row pins the feature commit rather than itself. The append was
exactly **+1 line**. Creep verdict: **`insufficient_data`** — the log now holds
**3** rows against the `2*window` (6) requirement, so `detect_creep` is a
deliberate no-op while the log fills (expected, per ADR-177; the one-off backfill
is NICE-TO-HAVE #63). No structural creep to surface.

## Open Questions / Follow-ups

- **Slice 3 must not measure a warm cache.** With `cache=True` a re-run costs
  nothing to parallelise, so the only honest benchmark for the parallel slice is
  a **cold** portfolio over a book large enough that per-deal projection
  dominates. The two features also have to compose: the simplest correct shape is
  to resolve cache hits serially, fan out only the misses, and write back under
  the existing per-deal eviction contract. Recorded in the CONTINUATION's
  "Context for Next Session" so the slice that must act on it reads it.
- **Slice 3 measurement threshold — still open (carried).** What multiple of
  speed-up justifies keeping a `max_workers` knob? Slice 3 will report and
  recommend, not decide unilaterally. Remains in the CONTINUATION's Open
  Questions.
- **The cache dict has no locking.** Two threads missing on the same key would
  both project — harmless to correctness (the values are equal) but it wastes
  exactly what the cache saves, and it would break `cache_stats().misses` as a
  proxy for work done. A Slice-3 constraint, recorded in the CONTINUATION under
  Slice 2's key decisions rather than promoted as a loose item.
- **Phase-7 frontier still unchosen.** Third consecutive maintenance-mode
  session. The C4 epic has one slice left, after which the routine again has no
  active Tier-A epic: `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §7 still lists only
  AXIS/Prophet reconciliation (REFERENCE-BLOCKED, needs a maintainer-supplied
  reference) and "a new Phase-7 frontier" (AWAITING MAINTAINER). This remains the
  single highest-value thing a human could resolve, and it becomes acute once
  Slice 3 merges. Note the review turns 30 days old on **2026-08-14**, at which
  point step 6 requires regeneration before the next epic is selected.

## Parked Polish

None reaching 3rd-order. ADR-179's two promoted out-of-scope items (bound the
cache; detect in-place input mutation) are **1st-order** — C4 is a planned
catalogue item and Slice 2 was planned scope — and were promoted normally as
NICE-TO-HAVE. Slice 3 is tracked in the CONTINUATION rather than promoted as a
loose item, per the established convention.

## Impact on Golden Baselines

None. Caching is off by default and, when on, changes only whether a projection
is recomputed — never its value; `run` / `run_with_capital` / `run_scenarios`
signatures and the aggregation are untouched, and both user-facing `Portfolio`
construction sites pass `name=` by keyword. `tests/qa/` green (94 passed) and the
`flat` golden config reproduces its committed baseline (cedant PV $3,513,563 /
reinsurer PV $45,386). The `perf/history.jsonl` append is diagnostic data, not a
golden change.

## Baseline

`make test` at session start: **2845 passed, 3 skipped, 125 deselected**, 0
failures. This matches the prior session log's recorded end state exactly
(2026-08-02 portfolio-lifecycle log: "the fast suite is expected at 2845 passed,
3 skipped"). Tolerance-aware check: no NEW or CHANGED failure → the session
PROCEEDED. The 3 skips are the standing absent-CIA-2014-table skips (step 2's
pymort conversion produces the 6 SOA/CSO tables; the 4 CIA 2014 tables are
unreachable from `pymort`).

End state after this slice: **2879 passed, 3 skipped, 125 deselected** (+34), and
`tests/qa/` **94 passed**. So the next session's expected baseline is
**2879 passed, 3 skipped**.

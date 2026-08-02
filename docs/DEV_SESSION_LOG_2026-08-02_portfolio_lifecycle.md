# Dev Session Log — 2026-08-02 (portfolio deal-lifecycle API)

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` — re-ranked catalogue **Tier C,
  item C4** ("Parallel portfolio execution + caching + `remove_deal`", ★★★☆☆,
  ~2 d), constituted this session as a 3-slice epic
  (`docs/PLAN_portfolio_execution.md` + `docs/CONTINUATION_portfolio_execution.md`).
- **Priority:** Tier-C fallback (gated — see Selection Rationale). No BLOCKER
  remains in the ledger.
- **Title:** Portfolio deal-lifecycle API — `remove_deal` / `replace_deal` /
  `without_deal` and the lookup surface.
- **Slice:** 1 of 3.
- **Branch:** `claude/quirky-ramanujan-25chda` (environment-designated; the
  environment override in routine step 8 takes precedence over the `feat/auto-*`
  default).

## Selection Rationale

**Maintenance mode, second consecutive session.** Step 5 found one IN PROGRESS
CONTINUATION (`reserve_basis_correctness`), explicitly *deprioritised / parked*
and not the active epic, so nothing was continued. Step 5b: there is still **no
startable Tier-A epic** — `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` §7 lists only
AXIS/Prophet reconciliation (REFERENCE-BLOCKED, needs a maintainer-supplied
reference) and "a new Phase-7 frontier" (AWAITING MAINTAINER, still unchosen as of
`PRODUCT_DIRECTION_2026-07-24` "Decision Surfaced"). The routine therefore falls
correctly to **gated Tier-B/C fallback** and **flags maintenance mode, not growth
mode**, as the review prescribes.

**Review is not stale.** `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is **18 days**
old on 2026-08-02 — inside the ~30-day regeneration trigger. (The 2026-08-01 log's
claim that it was ">30 days old" was an arithmetic error, already corrected in the
2026-08-02 harvest note; no regeneration is due. Re-verified this session.)

**Why C4.** `PRODUCT_DIRECTION_2026-07-24`'s own closing note names the next
fallback picks in value-per-day order: *"the deferred auto-append job (if
authorized), then Tier-C (C4 parallel portfolio / C6 load test)."* The auto-append
job is **not** available to take — it is blocked on maintainer authorization for a
bot commit to `main`, and the maintainer in fact decided the opposite way on
2026-08-02 (the daily-dev routine's own revision: append the row on every routine
PR, step 14b, precisely to avoid the privileged CI job). That leaves C4, the first
Tier-C entry. C6 (load test + K8s guide) was rejected as the alternative: a "100
concurrent requests < 2 s" gate is a wall-clock assertion in a shared CI sandbox —
the exact alert-fatigue shape the group's standing rule ("deterministic metrics
may gate; raw wall-time only informs", maintainer 2026-07-12) warns against — and
it is more infra than engine. C4 is engine-level, deterministic, and fully
testable by pytest.

**Why decompose rather than ship C4 whole.** C4 bundles three distinct
capabilities (~2 dev-days, 300–800 lines across the module + tests) → **MEDIUM**
by the step-6 size rule → PLAN + CONTINUATION + slice 1, per "DECOMPOSE, DON'T
DEFER". Slice ordering is a genuine dependency, not "smallest first": a per-deal
result cache (Slice 2) is only sound once **every** mutation path is a known
choke point, so the lifecycle API has to exist first. Parallel execution
(Slice 3) is independent of both and is sequenced last because it is the one
slice whose value claim needs a *measurement* to be honest.

## Verify Premise (step 7b)

Reproduced before writing any code:

```
>>> sorted(n for n in dir(Portfolio()) if not n.startswith('_'))
['add_deal', 'deals', 'n_deals', 'name', 'run', 'run_scenarios', 'run_with_capital']
>>> hasattr(p, 'remove_deal'), hasattr(p, 'get_deal')
(False, False)
>>> hasattr(Portfolio, '__len__'), hasattr(Portfolio, '__contains__')
(False, False)
```

The premise holds exactly as the catalogue states: `add_deal` is the only verb,
`_deals` is private, and `deals` is an immutable tuple view — so a deal cannot be
dropped, re-quoted, or looked up without rebuilding the whole portfolio from its
source objects. No correction to the entry was needed.

Red-green was also verified explicitly: with the implementation stashed, the 39
new tests fail 39/39; with it applied they pass 39/39.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Deal lifecycle API — `remove_deal` / `replace_deal` / `clear_deals` / `without_deal` + lookup surface | ✅ Done | #181 |
| 2 | Per-deal result caching keyed `(deal_id, hurdle_rate)`, invalidated by all four mutation verbs, opt-in | ⏳ Next | — |
| 3 | Parallel per-deal execution (`max_workers`, thread pool, index-ordered collection) behind a measurement gate | 🔲 Planned | — |

## What Was Done

Added a deal-lifecycle surface to `analytics/portfolio.py::Portfolio` (ADR-178).
The read half is `__len__`, `__contains__` (by deal id), the `deal_ids` property
(insertion order — the order of the per-deal breakdown), and `get_deal`. The
mutating half is `remove_deal`, `replace_deal`, and `clear_deals`, all chainable
like `add_deal`; `replace_deal` is **position-preserving**, so re-quoting one deal
does not silently reorder the per-deal breakdown or (under `align="calendar"`) the
grid-offset list — the reason it is not implemented as remove-then-add sugar.
Alongside them, `without_deal(*deal_ids, name=None)` returns a **new** portfolio
over the same frozen `Deal` objects, mirroring the copy-don't-mutate pattern
`_with_scenario` already uses for `run_scenarios`; that is the what-if primitive,
and a test asserts the identity it exists for — full-book PV minus ex-deal PV is
exactly that deal's PV contribution under strict alignment.

Two design choices carry the weight. First, **an unknown deal id always raises**;
nothing silently no-ops. A silently ignored `remove_deal("DEAL_C ")` returns the
*unmodified* book's numbers — a wrong answer that looks right, and one an actuary
has no way to spot in the output. `without_deal` accordingly validates every id
before filtering any, so a typo alongside valid ids fails loudly rather than
returning a partial filter; the error names the book's ids, truncated past ten so
a large portfolio does not print a wall of text. Second, the single-product-block
and proportional-treaty checks moved out of `add_deal` into a module-level
`_build_deal` **choke point** shared with `replace_deal`, so a replacement cannot
smuggle in a multi-product block or a stop-loss treaty that `add_deal` would have
rejected, and the two paths cannot drift. Deal-id uniqueness deliberately stays
with the callers — it means the opposite thing to each.

`run` / `run_with_capital` / `run_scenarios` and the aggregation are untouched, so
the change is purely additive and no number moves. The epic's remaining two
capabilities are planned in `docs/PLAN_portfolio_execution.md` and tracked in
`docs/CONTINUATION_portfolio_execution.md`, including the Slice-1 decisions that
constrain them (four named mutation verbs are the complete invalidation set for
Slice 2; a `without_deal` copy must not inherit the parent's cache by reference;
position stability matters to Slice 3's index-ordered collection).

## Files Changed
- `src/polaris_re/analytics/portfolio.py` — lifecycle API; `_build_deal` /
  `_id_summary` module helpers; module + class docstrings.
- `tests/test_analytics/test_portfolio.py` — 39 new tests across five classes.
- `docs/DECISIONS.md` — **ADR-178**.
- `ARCHITECTURE.md` — Portfolio Aggregation paragraph.
- `docs/PLAN_portfolio_execution.md` — **new** (3-slice decomposition of C4).
- `docs/CONTINUATION_portfolio_execution.md` — **new** (IN PROGRESS).
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — C4 annotated IN PROGRESS + Slice 1
  shipped; PR #180 recorded on the IMPORTANT #10 SHIPPED footer (ledger healing);
  status update on the auto-append IMPORTANT item; 2026-08-02 harvest section.
- `perf/history.jsonl` — one appended row (ADR-177 / routine step 14b).

## Tests Added

`tests/test_analytics/test_portfolio.py` (+39):
- `TestPortfolioInspection` (8) — `len` agrees with `n_deals`; empty portfolio;
  `deal_ids` insertion order; `in` for known/unknown; a non-string operand is
  `False`, not an error; `get_deal` returns the frozen deal with its cached
  `product_type` / `treaty_type` / `cession_pct`; unknown id raises; the error
  truncates a 12-deal book.
- `TestPortfolioRemoveDeal` (8) — chainable; drops only that deal and preserves
  order; unknown id raises **and leaves the book untouched**; remove-then-re-add
  the same id; remove-all then `run` raises the empty-portfolio error;
  **parametrized closed-form** (`@pytest.mark.parametrize` over which of three
  deals is dropped) that the resulting `total_pv_profits` equals the sum of the
  survivors' PVs; a bit-identical comparison (`assert_array_equal` on aggregate
  NCF and ceded NAR, plus PV / IRR / ceded face / concentration / HHI) against a
  portfolio freshly built without the dropped deal; concentration collapses to
  HHI 1.0 when the only other cedant's deal is removed.
- `TestPortfolioReplaceDeal` (8) — chainable; position preserved; cached treaty
  metadata refreshed (coinsurance → YRT); unknown id raises; multi-product block
  and non-proportional treaty both rejected with the original left in place;
  post-replacement run matches a freshly built portfolio; a cession-halving
  sensitivity check on ceded face.
- `TestPortfolioWithoutDeal` (11) — receiver not mutated; several ids at once;
  frozen `Deal` objects shared (identity); default and custom names, the latter
  reaching the aggregate `run_id` / `block_id`; unknown id alone and alongside
  valid ids both raise; zero ids rejected; excluding everything yields an empty
  portfolio; the copy matches the mutating removal; marginal-contribution
  identity.
- `TestPortfolioClearDeals` (2) — chainable and empties; clear-then-rebuild.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| A deal can be removed without rebuilding the portfolio | ✅ | `remove_deal` (in place) + `without_deal` (copy) |
| Removal result is identical to a portfolio never holding that deal | ✅ | `assert_array_equal` on aggregate NCF + ceded NAR; PV/IRR/HHI equal |
| Closed-form verification | ✅ | Parametrized: post-removal `total_pv_profits` == sum of survivors' PVs (rtol 1e-12) |
| Unknown deal id never silently no-ops | ✅ | Every verb raises `PolarisValidationError`; `without_deal` validates all ids before filtering |
| Replacement cannot bypass `add_deal` validation | ✅ | Shared `_build_deal` choke point; both rejection paths tested |
| Replacement preserves deal order | ✅ | `test_replace_deal_preserves_position` + breakdown order assertion |
| Goldens byte-identical | ✅ | Additive-only; `tests/qa/` green; flat golden cedant PV $3,513,563 / reinsurer PV $45,386 |
| Quality gate (ruff format + check, fast suite, qa suite) | ✅ | ruff clean on `src/ tests/`; suite green (see Baseline) |
| Slices 2–3 planned and independently mergeable | ✅ | `PLAN_portfolio_execution.md` + `CONTINUATION_portfolio_execution.md` |

## Perf History

Row appended to `perf/history.jsonl` for this branch's feature-commit HEAD: **yes**
(initial PR open, step 14b). Creep verdict: **`insufficient_data`** — the log holds
2 rows against a `2*window` requirement, so `detect_creep` is a deliberate no-op
while the log fills (expected, per ADR-177; the one-off backfill is NICE-TO-HAVE
#63). No structural creep to surface.

## Open Questions / Follow-ups

- **Slice 2 cache opt-in shape** — `Portfolio(cache=True)` (constructor-level
  policy) vs `run(use_cache=True)` (per-call). Leaning constructor-level: "these
  deals are frozen for the duration" is a property of how the caller holds the
  portfolio, not of one run. Will be decided in ADR-179 absent a maintainer
  preference. *(Recorded in the CONTINUATION Open Questions.)*
- **Slice 3 measurement threshold** — if threaded execution gives only a marginal
  speed-up on a realistic book, the honest outcome is to ship the measurement and
  drop the `max_workers` knob. What multiple justifies the extra API surface?
  Slice 3 will report and recommend, not decide unilaterally. *(Recorded in the
  CONTINUATION Open Questions.)*
- **The auto-append CI job (IMPORTANT) is now narrowed, not closed.** The
  maintainer's 2026-08-02 routine revision covers routine-authored merges via the
  per-PR row (step 14b), so what remains uncovered is a **human hotfix merged
  outside the routine**. Annotated in place in PRODUCT_DIRECTION rather than
  struck through, along with the two operational notes recorded with the decision
  (concurrent PRs will conflict on the append-only file; the append is
  initial-open-only).
- **Phase-7 frontier still unchosen.** Second consecutive maintenance-mode
  session. With C4 constituted, the routine now has an active epic again for the
  next two sessions — but that is a Tier-C epic, not a growth frontier. The
  strategic decision surfaced in `PRODUCT_DIRECTION_2026-07-24` remains open and
  is the single highest-value thing a human could resolve.

## Parked Polish

None reaching 3rd-order. ADR-178's three out-of-scope items are all 1st-order
follow-ups of the planned C4 item and were promoted normally; Slices 2–3 are
tracked in the CONTINUATION rather than promoted as loose items, per the
established convention.

## Impact on Golden Baselines

None. Purely additive — no existing method, signature, or number changed;
`run` and the aggregation are untouched. `tests/qa/` green and the `flat` golden
config reproduces its committed baseline (cedant PV $3,513,563 / reinsurer PV
$45,386). The `perf/history.jsonl` append is diagnostic data, not a golden change.

## Baseline

`make test`-equivalent (`pytest -m "not slow"`) at session start:
**2804 passed, 3 skipped, 125 deselected**, 0 failures. This matches the prior
session log's recorded end state exactly (2026-08-02 perf-history log: "the fast
suite is expected at 2804 passed, 3 skipped"). Tolerance-aware check: no NEW or
CHANGED failure → the session PROCEEDED. The 3 skips are the standing
absent-CIA-2014-table skips (step 2's pymort conversion produces the 6 SOA/CSO
tables; the 4 CIA 2014 tables are unreachable from `pymort`).

This slice adds 39 fast tests, so the fast suite is expected at
**2843 passed, 3 skipped**.

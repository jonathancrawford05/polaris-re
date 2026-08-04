# Dev Session Log — 2026-08-02 (portfolio parallel execution — C4 Slice 3, closes the epic)

## Item Selected
- **Source:** `docs/CONTINUATION_portfolio_execution.md` (IN PROGRESS) — the
  CONTINUATION **is** the work selection under routine step 5, so steps 5b and 6
  were skipped. Backing catalogue entry: `PRODUCT_DIRECTION_2026-07-24.md`
  re-ranked catalogue **Tier C, item C4** ("Parallel portfolio execution +
  caching + `remove_deal`", ★★★☆☆, ~2 d).
- **Priority:** Tier-C epic, slice 3 — the final slice.
- **Title:** Portfolio parallel execution — `run(max_workers=N)`.
- **Slice:** 3 of 3 (**closes epic C4**).
- **Branch:** `claude/quirky-ramanujan-5zhsw3` (environment-designated; the
  environment override in routine step 8 takes precedence over the `feat/auto-*`
  default).

## Selection Rationale

**Step 5 found a live continuation, so nothing else was considered.**
`docs/CONTINUATION_portfolio_execution.md` was IN PROGRESS with Slice 3 marked
NEXT and "depends on: Slice 2 merged". Slice 2's PR **#182 is merged** (merge
commit `39729fb` on `origin/main`, 2026-08-02T22:28Z) and there are **no open
PRs**, so the step-5 draft rule does not bite and the session continued on a new
branch from `main`. Per step 5c that decides the work — steps 5b (active epic)
and 6 (fallback selection) were correctly skipped, and no Tier-B/C/D fallback was
picked alongside.

The other IN PROGRESS continuation, `reserve_basis_correctness`, remains
explicitly *deprioritised / parked* and is not the active epic, exactly as the
prior three sessions recorded.

**Review staleness re-checked.** `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is
**18 days** old on 2026-08-02 — inside the ~30-day regeneration trigger, so no
regeneration is due. (Verified rather than inherited.)

**Ledger healing (step 4b).** One PR merged since the last session log: **#182**.
Its `PRODUCT_DIRECTION_2026-07-24` C4 entry carried "Slice 2 SHIPPED" from the
authoring session but not the merge; it now records **MERGED to main `39729fb`**
in the house style. No entry was deleted.

**PRUNE (step 6 sanity step).** The one entry whose acceptance criteria this
session satisfies is C4's Slice 3, struck through with a SHIPPED footer as part of
closing the epic (the entry now records all three slices plus the measurement
outcome). Nothing else in the latest PRODUCT_DIRECTION was verifiably shipped on
`main` but still open — no other item was pruned by inspection.

## Verify Premise (step 7b)

Reproduced before writing any code:

```
run signature:              (self, hurdle_rate, *, align='strict')
run_with_capital signature: (self, hurdle_rate, capital_model, *, align='strict')
run_scenarios signature:    (self, hurdle_rate, scenarios=None, *, align='strict')
ThreadPoolExecutor imported in module: False
```

No worker knob existed and every projection ran on the calling thread (a new test
pins that too: the serial path's projections all report the *calling* thread's
ident). The premise held exactly as `PLAN_portfolio_execution.md` states; **no
correction was needed**.

Tests were confirmed **red** first — 33 failed / 1 passed of the 34 new tests
against the unmodified engine (the one that passed is the premise-recording test
asserting the serial path uses the calling thread, which was already true) — and
**green 34/34** with the implementation applied.

## What Was Done

`Portfolio.run` gained `max_workers: int | None = None`, forwarded by
`run_with_capital` and `run_scenarios`. `None` (the default) and `1` — and any
book with fewer than two deals — take the *serial* path, not a one-worker pool;
a `ThreadPoolExecutor` is never even constructed there, which a test asserts by
monkeypatching the constructor to raise. Above that, the per-deal projections fan
out over `min(max_workers, n_deals)` threads via a new `_project_all` helper, one
task per deal, collected by **input position** (`Executor.map`). Collecting by
position rather than completion is what keeps the order-sensitive aggregation sum
— and therefore every number in the result, PV included — bit-identical to serial
at any worker count. It is also what keeps each cache key touched exactly once, so
ADR-179's explicit no-single-flight decision keeps holding rather than being
quietly invalidated by this slice. `max_workers` is validated before any deal is
projected (`None` or a positive plain `int`; `bool` rejected explicitly, since
`max_workers=True` would silently mean "one worker").

One deliberate change to a Slice-2 decision: **the cache dict and its two counters
are now lock-guarded** — never a projection. ADR-179 recorded no-locking as
resting on CPython's GIL making `self._cache_hits += 1` *effectively* atomic, and
noted the assumption would break on a free-threaded build. This slice is what
turns concurrent `_run_deal` from a hypothetical into a shipped, supported path,
so the counters get real mutual exclusion instead of an implicit guarantee. The
lock covers the lookup, the counter arithmetic, and the write-back only; holding
it across `_project_deal` would serialise exactly the work the fan-out exists to
overlap.

**The measurement gate came back below the bar, and the claim was not made.** The
slice's gate required publishing a real speed-up or shipping the measurement
without the parallel claim. `scripts/bench_portfolio_parallel.py` (new, committed)
times a **cold** portfolio — every sample builds a fresh `Portfolio(cache=False)`,
so no projection is ever reused, the failure mode the CONTINUATION warned about
twice — with the perf harness's best-of-k *minimum* estimator, and proves
bit-identical aggregates (`assert_array_equal`) before reporting any ratio. On the
4-core runner, 20-year monthly horizon, k=3:

| book | serial | 2 workers | 4 workers | 8 workers |
|---|---|---|---|---|
| 8 deals × 5,000 policies | 3.80 s | **1.19x** | **0.59x** | **0.48x** |
| 4 deals × 20,000 policies | 7.85 s | 1.07x | **1.29x** | — |

Both rows reproduced across independent invocations (the 8×5k row twice, within
2%). The peak is **1.29x** and one common configuration is **~2x slower than
serial**. Cause, diagnosed rather than guessed: a per-deal projection is not one
big GIL-releasing ufunc — `products/term_life.py` runs several
`for month in range(t)` recursions (in-force factor `lx`, net-premium reserve,
CRVM reserve), i.e. Python loops around comparatively small per-step NumPy calls
on `(N,)` arrays. Larger `N` lengthens each C section relative to the Python
overhead between them, which is precisely why 20k-policy deals scale and
5k-policy deals regress. The knob therefore ships **off by default with the
negative numbers in its own docstring**, nothing in the README or public docs
advertises portfolio parallelism, and the disposition question is handed to the
maintainer in ADR-180 rather than decided here (per the CONTINUATION's
"report and recommend, not decide unilaterally").

The harness's own `run_perf_probe` could not be used as the entry point: its
hot-path contract is engine-level (`Callable[[BaseProduct], CashFlowResult]`) and
a portfolio run does not fit it. The benchmark reuses the harness's *estimator
discipline* (best-of-k minimum, `gc.collect()` before the clock, block build
excluded from the measured window) and the shared
`scale_benchmark.build_homogeneous_block` builder instead — stated plainly in the
script docstring rather than papered over.

## Files Changed

- `src/polaris_re/analytics/portfolio.py` — `max_workers` on `run` /
  `run_with_capital` / `run_scenarios`; new `_project_all` fan-out and
  `_validate_max_workers`; `threading.Lock` around the cache dict and counters;
  module + class docstrings.
- `scripts/bench_portfolio_parallel.py` — **new**, the measurement gate.
- `tests/test_analytics/test_portfolio.py` — 34 new tests (+ `threading` import).
- `docs/DECISIONS.md` — **ADR-180**.
- `docs/CONTINUATION_portfolio_execution.md` — Slice 3 DONE, status **COMPLETE**.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — step-4b ledger heal (#182 merged), C4
  closed with a SHIPPED footer, and the step-17 harvest section.
- `perf/history.jsonl` — one appended row (ADR-177).

## Tests Added

All in `tests/test_analytics/test_portfolio.py`:

- `TestPortfolioParallelValidation` (6) — non-positive / non-integer / `bool`
  rejected; validation happens before any projection; the empty-portfolio error
  still wins.
- `TestPortfolioParallelDefault` (4) — the default and `max_workers=1` construct
  no pool; a single-deal book constructs no pool even at 8 workers; the serial
  path projects on the calling thread.
- `TestPortfolioParallelCorrectness` (12) — bit-identical to serial at 2/4/8
  workers; deal order preserved; a `threading.Barrier` proof that the fan-out is
  *actually* concurrent; workers capped at the deal count; calendar alignment
  bit-identical with the right grid offsets; a failing deal propagates rather than
  yielding a partial book.
- `TestPortfolioParallelWithCache` (7) — a cold parallel run projects each deal
  exactly once at 2/4/8 workers with an exact `CacheStats`; a warm parallel run
  projects nothing and counts every hit; cached-parallel is bit-identical to
  uncached-serial.
- `TestPortfolioParallelWrappers` (4) — `run_with_capital` / `run_scenarios`
  forward the knob and validate it.

No wall-clock assertion appears in any test. The plan asked for a
`@pytest.mark.slow` timing test; a timing assertion would contradict the harness's
standing rule that raw wall-time never gates, so the deterministic
`threading.Barrier` test carries that intent instead (if the fan-out ran the deals
one at a time, the barrier times out) and the actual speed-up ships through the
committed benchmark. Recorded in ADR-180.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `max_workers=4` equals serial under `assert_array_equal` (exact) | ✅ | Verified at 2/4/8, both alignment modes, cached and uncached |
| Deal order preserved | ✅ | Collected by input position; asserted directly |
| Invalid `max_workers` rejected | ✅ | 0 / negative / float / str / list / `bool`, before any projection |
| Benchmark runs a **COLD** portfolio | ✅ | Fresh `Portfolio(cache=False)` per sample; stated in the ADR |
| One task per deal — each cache key touched exactly once | ✅ | Exactly `n_deals` engine builds at 2/4/8 workers on a cold cache |
| Goldens byte-identical; serial stays the default | ✅ | `tests/qa/` 94 passed; flat golden reproduces PV $3,513,563 / $45,386 |
| Publish a real speed-up **or** ship the measurement without the claim | ✅ | Measurement shipped, claim **not** made — peak 1.29x, 0.48–0.59x regressions recorded |

## Baseline

`make test` at session start: **2879 passed, 3 skipped, 125 deselected**, 0
failures. This matches the prior session log's recorded expectation exactly
("the next session's expected baseline is 2879 passed, 3 skipped"). Tolerance-aware
check: no NEW or CHANGED failure → the session PROCEEDED. The 3 skips are the
standing absent-CIA-2014-table skips (step 2's `pymort` conversion produces the 6
SOA/CSO tables; the 4 CIA 2014 tables are unreachable from `pymort`).

End state after this slice: **2923 passed, 3 skipped, 125 deselected** (+44 — 34
engine tests plus 10 from the CLI addendum below), and `tests/qa/` **94 passed**.
So the next session's expected baseline is **2923 passed, 3 skipped**.

## Perf History

Row appended to `perf/history.jsonl` for branch HEAD `b82d0c8` — yes, exactly +1
line, committed separately so the row pins the feature commit rather than itself.
Creep verdict: **`insufficient_data`** — the log holds 4 rows and needs ≥ 6
(2 × window) per probe. Expected while the log is young; no action, and nothing to
raise under Open Questions.

## Addendum — CLI surfacing (same session, maintainer direction)

After PR #183 was opened, the maintainer directed that `max_workers` be wired
through the CLI and indicated a **lean toward adopting** the parallel feature,
with a many-core re-measurement to follow on their own hardware. That reverses
this session's own recommendation (the ADR argued for deciding the disposition
*before* surfacing), and the reversal is the maintainer's call — recorded as an
**amendment** to ADR-180 rather than by editing the decision, so the sequence
stays auditable: measurement first, surfacing decision second.

Shipped on the same branch:

- `polaris portfolio run --max-workers N` and `polaris portfolio scenarios
  --max-workers N`, serial by default. The scenarios command keeps scenarios
  sequential and fans out only the per-deal projections within each, matching
  `run_scenarios`'s own semantics.
- A CLI-level validation naming the **flag** (`--max-workers must be >= 1`), so a
  caller who typed a flag does not get the engine's parameter-named message —
  the pattern `--align` already uses.
- `--help` text that leads with the caveat rather than the mechanic, carrying the
  measured 1.29x / 0.59x / 0.48x figures inline. **A test asserts the word
  "slower" survives in the rendered help**, so removing the warning requires
  removing a test. A flag called `--max-workers` otherwise reads as
  "make it go faster", which the measurement says is often false.
- `docs/RUNBOOK_portfolio_parallel_measurement.md` — the procedure for generating
  the many-core half of the evidence: core-count discovery (with the Apple
  Silicon P/E-core split called out as a hypothesis to test), a quiet-machine
  checklist, three book shapes chosen to test the ADR's *actual* finding (that the
  sign of the effect depends on per-deal block size, not that threads are
  good/bad), a CLI end-to-end check, a fill-in results template destined for
  `docs/MEASUREMENT_portfolio_parallel_<hardware>.md`, and a troubleshooting
  table.

REST and the Streamlit page stay out of scope: per-request worker pools multiply
against a server's own concurrency, which is capacity planning rather than API
design — the asymmetry that makes the CLI the right first surface.

One cost accepted knowingly: surfacing the flag raises the price of removing the
knob later from "revert one engine change" to "deprecate a public CLI option".

10 further tests (suite 2913 → **2923**); goldens unchanged (flat golden still
$3,513,563 / $45,386). No second `perf/history.jsonl` row — step 14b appends one
row per PR, on the initial open only.

## CI round 1 — two self-inflicted failures, fixed

`Test (Python 3.12)` and `Test (Python 3.13)` came back red on PR #183: both
`--max-workers` `--help` tests, green locally. Not a code defect — a test bug,
and an instructive one.

Rich colourises an option name in **fragments**, emitting `-`, `-max`,
`-workers` as three separately-styled runs with escape codes between them, so
the literal `--max-workers` never appears contiguously in the raw output.
Whether that happens depends on whether Rich believes it is writing to a
terminal, which is exactly why the assertions passed in this container and
failed on the runner. Reproduced locally with `FORCE_COLOR=1`, then fixed by
routing the assertions through a new `_plain()` helper that strips escape codes
and collapses whitespace. These are the repo's first `--help` *content*
assertions, so the helper documents both hazards — colour fragmentation and
Rich's box wrapping/ellipsis — for whoever writes the next one.

Everything else was green on that run: Lint (Ruff + mypy), Smoke, Docker build &
test, and the head-vs-main Perf gate.

**DISCOVERY (step 11b) — filed, not fixed.** Running the file under
`FORCE_COLOR=1` also turns **three pre-existing tests** red for the identical
reason: `TestPortfolioRunConcentrationBasisFlag::test_nar_peak_basis_renders_nar_section_only`,
`::test_all_basis_renders_three_sections`, and
`TestPortfolioReportConcentrationBasisFlag::test_report_supports_all_basis`, all
asserting `'weighted by Peak Ceded NAR' in result.output`. They are **green on
CI today** because the repo's module-level Rich `Console` disables colour when
stdout is not a TTY, while Typer's help formatter colours regardless — so only
the help-rendering path was exposed. They are latent, not broken, and fixing
them is outside this PR's scope; promoted as NICE-TO-HAVE with the reproduction
command.

## Addendum 2 — the many-core measurement landed; knob KEPT

The maintainer ran `docs/RUNBOOK_portfolio_parallel_measurement.md` §3 on an Apple
Silicon MacBook Air. Full tables: `docs/MEASUREMENT_portfolio_parallel_macbook_air.md`;
folded into ADR-180 as amendment 2.

| shape | serial | 2w | 4w | 8w | 16w |
|---|---|---|---|---|---|
| A — 8 deals × 5k policies | 0.659 s | **1.30x** | 0.94x | 0.70x | — |
| B — 4 deals × 20k | 1.254 s | 1.56x | **1.57x** | — | — |
| C — 16 deals × 20k | 5.184 s | 1.63x | **1.77x** | 1.35x | 1.23x |

**Peak 1.77x**, every row bit-identical. That clears the 1.5x bar the CONTINUATION
floated (not 2x), so the disposition question closes as **KEEP** — the
maintainer's decision, on evidence rather than the inference this session
declined to make off a 4-core box.

Three things the data settled, and the first is a correction worth making
explicitly: **"sweet spot at 4" is only true for the large-block shapes.** Shape A
peaks at **2** workers and is *below serial* at 4 (0.94x). ADR-180's central
finding — that the sign flips with per-deal block size — reproduced on
independent hardware and a different OS, less violently than the container's
0.59x/0.48x but the same shape. Second, the curve bends at the **performance**-core
count rather than the total: 8 and 16 workers lose ground even on shape C, so
efficiency cores do not contribute to this workload. That was raised as a
hypothesis in the runbook and is now a documented rule. Third, oversubscription
degrades *gracefully* with more cores (1.35x/1.23x on shape C where the 4-core box
collapsed to 0.48x) — the mistake gets cheaper, not free.

Stated rather than buried: a MacBook Air is fanless, so part of the 8/16-worker
tail may be thermal rather than GIL/oversubscription. Best-of-k takes the minimum,
which mitigates but does not eliminate it. The 4-worker peak is faster *and* cooler
than the 8/16 runs, so the decision does not rest on the soft part.

**Code change: documentation only.** The `run` docstring and the `--max-workers`
help text now carry two measured rules — match performance cores, large per-deal
blocks only — replacing a bare "measure first" warning backed by a single negative
table. Default still serial, still bit-identical at every worker count, still
absent from REST and the dashboard. The ~1.8x ceiling is unchanged and is what a
GIL-bound workload looks like on 4 P-cores; the month-by-month recursions in
`products/term_life.py` remain the binding constraint and the larger win.

**Spec since captured, and it turns the hypothesis into a confirmation.**
`sysctl -n hw.ncpu hw.perflevel0.logicalcpu hw.perflevel1.logicalcpu` → **10 / 4 /
6**: ten logical cores, four performance, six efficiency. The peak sits at exactly
the P-core count on all three shapes while six cores sit idle, and the E-cores do
not merely fail to help — 8 workers scores 1.35x against 4 workers' 1.77x on shape
C with ample work available, so recruiting them *costs* throughput. That is the
concrete form of the rule now in the docstring and `--help`: a caller who read
"use your cores" and passed `hw.ncpu` (10) on this machine would give back roughly
a third of the gain. RAM was not recorded; no run showed memory pressure and shape
C's timings were internally consistent, so nothing suggests it mattered.

## PR #183 review round (2026-08-04)

Automated review **approved**: zero [P0], zero [P1], zero test failures. Three
[P2]s, all addressed in-PR:

- **PLAN/delivery divergence x2** — the un-delivered `@pytest.mark.slow` timing
  test and the non-use of `run_perf_probe`. Both were deliberate and already
  reasoned in ADR-180, but the PLAN's acceptance list still read as unmet.
  `PLAN_portfolio_execution.md` Slice 3 now carries a dated amendment recording
  both, so plan and shipped state agree on paper.
- **Undocumented benign race in `products/dispatch._ensure_registry()`** — a good
  catch, and verified rather than taken on trust. The fan-out means the registry
  can now first populate from a *worker* thread and two threads can race the
  guard. The body is three assignments of constant class objects, so a concurrent
  double-populate writes identical values; the imports are serialised by Python's
  import lock. Harmless, but it was the one piece of shared module state the new
  concurrent path touches and it carried no comment. Now documented at the
  function.

**On the raised perf row (`best_of_k_seconds` 0.1489 against ~0.06 for the prior
three).** The review flagged it as probable runner noise, gating nothing. That is
right, and the case is stronger than "probably noise":

- **This PR cannot have caused it.** The probe measures
  `get_product_engine(...).project()` — entirely inside `products/`. The diff
  touches `analytics/portfolio.py` and `cli.py` and nothing else in `src/`. There
  is no code path by which it could slow that probe.
- **The deterministic metrics are byte-identical across all four rows**:
  `output_fingerprint` `8331a13f7ce7...` and `peak_mib` 33, unchanged. Same
  computation, same allocation — only wall-clock moved, which is exactly the
  signature of a shared-runner artefact rather than a regression.

Recorded so that if the series stays elevated past 6 rows, the next reader knows
this row was examined and cleared on mechanism, not waved through.

## Open Questions / Follow-ups

1. **The `max_workers` knob's disposition is a maintainer decision, deliberately
   left open.** The measured peak (1.29x) is below both thresholds the
   CONTINUATION floated (1.5x / 2x) and one common shape is ~2x *slower* than
   serial, which on the plan's own terms is the "ship the measurement, not the
   claim" branch. The knob was kept, off by default, for one reason: **this is a
   4-core measurement**, and deleting a feature that may pay on a 32-core
   workstation on that basis would be over-fitting to the CI runner. If you
   prefer the stricter reading, removing the parameter is a small self-contained
   revert of the engine change in this PR; the benchmark and ADR-180 are worth
   keeping either way. Promoted to PRODUCT_DIRECTION as IMPORTANT.
2. **The real throughput bottleneck is in `products/`, not `analytics/`.**
   (DISCOVERY protocol, step 11b — quantified, filed, and *not* fixed in this PR.)
   The measurement's own explanation is that per-deal projection is GIL-bound by
   the engines' `for month in range(t)` recursions; that is why 20k-policy deals
   reach 1.29x while 5k-policy deals fall to 0.59x. Shortening or vectorising
   those loops would raise the **serial** number too — a strictly larger win than
   any fan-out. Promoted as IMPORTANT with the evidence.
3. **Epic C4 is now COMPLETE and none of it is reachable from a user-facing
   surface.** All three slices — lifecycle, cache, fan-out — are Python-API only,
   by the plan's own scope. The item that would convert the epic into user-visible
   value is incremental portfolio what-if over a *session* (dashboard "drop DEAL_C
   and re-price"), which needs a session/state design first. Promoted as IMPORTANT.
4. **No active Epic after this PR.** C4 was the active epic and it closes here, so
   the next session hits routine step 5b with no Epic active and must **start
   one** (write `PLAN_<feature>.md` + ship slice 1) from the latest
   `COMMERCIAL_VIABILITY_REVIEW`'s Tier-A table before considering any fallback
   pick. `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` turns 30 days old on
   **2026-08-14**, so a session after that date regenerates it first.

## Parked Polish

**None.** Every item harvested this session is 1st- or 2nd-order: the
knob-disposition and vectorise-the-recursions items are 1st-order (follow-ups of
C4's own planned scope and of ADR-180's measurement), as are the CLI/REST/dashboard
surfacing item, the session-state what-if item, and the marginal-contribution
analytic. The single 2nd-order item — re-measure the parallel curve on many-core
hardware — is a follow-up of the knob-disposition follow-up and was promoted as
NICE-TO-HAVE per the step-17 cap. Nothing reached 3rd order.

## Impact on Golden Baselines

**None.** The serial path is the default and is byte-for-byte the previous code
path; the parallel path is proven bit-identical to it by construction and by test.
`tests/qa/` 94 passed and the `flat` golden config reproduces its committed
baseline (cedant PV $3,513,563 / reinsurer PV $45,386). The `perf/history.jsonl`
append is diagnostic data, not a golden change.

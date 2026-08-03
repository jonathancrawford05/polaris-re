# Plan: engine recursion vectorisation — raise the serial projection number

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — "Vectorise the engines'
month-by-month recursions (the real throughput bottleneck)", **IMPORTANT**,
harvested from ADR-180 + the DISCOVERY-protocol finding in routine step 11b.
**Constituted:** 2026-08-03, on maintainer direction, as the next active Epic.
**Classification:** LARGE (4 slices) — cross-cutting, and the last slice touches
reserve arithmetic.
**Status:** slice 1 NEXT — see `docs/CONTINUATION_engine_recursion_vectorisation.md`.

---

## 1. Why

ADR-180 set out to make portfolio pricing faster by running deals in parallel.
It measured the ceiling instead. On a 10-core Apple Silicon machine the threaded
fan-out peaked at **1.77x with 4 workers and six cores idle**, because a per-deal
projection is not one big GIL-releasing ufunc: `products/term_life.py` runs
several `for month in range(t)` loops around comparatively small per-step NumPy
calls on `(N,)` arrays. Threads overlap the array work and contend on everything
between the steps.

That diagnosis is the whole case for this epic. Every month spent inside a Python
loop is a month that:

- **caps the parallel gain** (it is the GIL-held critical path), and
- **costs every caller**, including the ones that will never pass `max_workers` —
  CLI, REST, dashboard, notebooks, `tests/qa/`, and CI itself.

Shortening those loops raises the **serial** number. That is a strictly larger
win than any fan-out, it needs no new API, and there is no flag for anyone to
misuse. It is also the only route to a parallel speed-up above ~1.8x, because
until the GIL-held fraction shrinks, adding workers cannot help.

**The unmeasured part, and why slice 1 exists.** Nobody has attributed
`project()`'s runtime across those loops. "The recursions are the bottleneck" is
an inference from the *shape* of the parallel curve, not a profile. It is a good
inference and it is not a measurement. Slice 1 measures before anything is
rewritten — the same discipline ADR-180 applied to itself.

## 2. The four loops, and why they are not equally tractable

This is the crux of the decomposition. They look alike and they are not.

| # | Loop | Kind | Bit-identical rewrite? |
|---|---|---|---|
| 1 | `_build_rate_arrays` `for month in range(t)` | **Not a recursion** — per-month ages, durations, masks, rate lookups | **Yes**, in principle |
| 2 | `_compute_inforce_factors` `lx[:,m] = lx[:,m-1]*(1-q)*(1-w)` | Cumulative product | **Yes, but only with care** — see below |
| 3 | `_compute_reserves_net_premium` backward recursion | Linear recurrence `V_t = a_t·V_{t+1} + c_t` | **No** |
| 4 | `_compute_reserves_crvm` backward recursion | Same shape as (3) | **No** |

**(1) is free money.** It computes each month's ages, duration, active mask and
rates independently; nothing depends on the previous month. Broadcasting it to
`(N, T)` evaluates the *same expression per element*, so the result is
bit-identical — provided the rewrite does not reassociate any arithmetic.

**(2) is a trap dressed as free money.** `lx` looks like `np.cumprod`, and it
nearly is. But the current code computes `(lx[:,m-1] * (1-q)) * (1-w)` — two
multiplications per step — whereas `cumprod` over a precomputed `(1-q)*(1-w)`
computes `lx[:,m-1] * ((1-q)*(1-w))`. **Different association, different
rounding, different goldens.** The two differ in the last ulp per step and
compound over 240 steps. A rewrite that preserves the association (e.g. cumprod
over `(1-q)` and `(1-w)` as separate factors in the original order) stays
bit-identical; a naive one does not. This distinction is the acceptance
criterion for slice 3, not a footnote.

**(3) and (4) cannot be made bit-identical, and pretending otherwise is the
failure mode.** `V_t = (q_t·b + (1-q_t)·V_{t+1})·v − P` is a first-order linear
recurrence with varying coefficients. It has a closed form — a weighted
cumulative sum of the forcing terms — but that form sums the same quantities in a
completely different order, and it subtracts a level premium at every step, which
is exactly the setup for catastrophic cancellation to differ between
formulations. Any rewrite here **will** move the goldens, by a small amount, in
every product that uses reserves. That is a maintainer decision about tolerance,
not something to slip into a performance PR — so it is isolated in the final
slice and gated.

## 3. Non-negotiable constraints

- **Slices 1–3 keep `tests/qa/` goldens byte-identical.** No tolerance, no
  regeneration. If a rewrite cannot hold that, it is not in slices 1–3.
- **No API change.** This is entirely internal to `products/`. No new
  parameters, no new flags, no behavioural switches.
- **No perf claim without a measurement**, through the committed harness. Same
  rule ADR-180 held itself to; the same rule that produced this epic.
- **Correctness before speed, stated as an ordering:** a slice that is faster and
  differs in the last ulp is a *failed* slice in 1–3, not a partial success.

## 4. Slices

### Slice 1 — Attribute the runtime (measure, change nothing)

Extend the perf harness's hot-path map to break `project()` into named
sub-paths — rate-array build, in-force factors, reserves, cash-flow assembly —
and publish the split. `analytics/perf_harness.py` already anticipates this: its
`default_hot_paths()` docstring says later callers add finer sub-paths by passing
their own map, so this is the extension point working as designed rather than a
new mechanism.

Deliverable: a committed measurement showing what fraction of a projection each
loop actually owns, at two block sizes (the small/large split ADR-180 showed
matters). **Zero production-code change**; goldens untouched by construction.

This slice can also *falsify the epic*. If the recursions turn out to be a
minority of runtime, the honest outcome is to say so and stop — and that result
would be worth more than the rewrite.

### Slice 2 — Vectorise `_build_rate_arrays` (bit-identical)

The non-recursive loop, and the one with the best risk/reward. Broadcast the
per-month age/duration/mask/rate computation to `(N, T)`.

Acceptance: `tests/qa/` goldens **byte-identical**; a direct
`assert_array_equal` between the old and new rate arrays on a fixture block; the
harness shows the sub-path faster.

### Slice 3 — `lx` as a cumulative product (bit-identical, association-preserving)

Acceptance: as slice 2, plus an explicit test that pins the *association* —
demonstrating that the naive `cumprod((1-q)*(1-w))` formulation differs and the
shipped one does not. That test is the guard against a future "simplification"
silently moving every reserve in the book.

### Slice 4 — The reserve recurrences (GATED — goldens will move)

**Do not start this slice autonomously.** It requires a maintainer decision on
the record first:

1. Is a bit-level change to reserves acceptable in exchange for the speed-up?
2. If yes, what tolerance, and do the `tests/qa/` baselines get regenerated (with
   the drift quantified in the ADR)?
3. Does the answer differ by basis — NET_PREMIUM vs CRVM vs GAAP?

Absent that decision, slice 4's deliverable is the *analysis*: implement the
closed form behind a comparison harness, quantify the drift on the golden
configs, and present it. Shipping it is a separate call.

## 5. Out of scope

- Any change to `analytics/` — the portfolio fan-out is done (ADR-180) and is not
  what this epic is about.
- Numba / Cython / C extensions. The claim under test is that *NumPy
  broadcasting* removes these loops; adding a compiler is a different epic with a
  different dependency and packaging story.
- The other product engines (`whole_life`, `universal_life`, `annuity`) beyond
  whatever slices 2–3 touch incidentally. If the pattern generalises, that is a
  follow-on epic sized off slice 1's measurement, not a fifth slice bolted on
  here.
- Re-measuring the parallel curve. It will improve as a side effect; that is a
  consequence to report, not a goal to chase.

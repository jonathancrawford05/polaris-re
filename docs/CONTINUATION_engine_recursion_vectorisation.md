# Continuation: engine recursion vectorisation

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` — "Vectorise the engines'
month-by-month recursions (the real throughput bottleneck)", **IMPORTANT**
(harvested from ADR-180 + routine step 11b DISCOVERY)
**Plan:** `docs/PLAN_engine_recursion_vectorisation.md`
**Status:** **PARKED** — constituted 2026-08-03, parked the same day on the
maintainer's decision after pre-work measurement undercut the premise. Revive by
an explicit maintainer decision only. See
`docs/MEASUREMENT_engine_recursion_prework.md`.

> **Why this was parked before slice 1 ran.** The epic was built from an
> *inference* — ADR-180's parallel curve looked GIL-bound, so the month-loops were
> assumed to be the bottleneck. Answering a maintainer question about FP
> tolerances produced the measurement instead: the `lx` loop vectorises
> **bit-identically** (interleaved cumprod) for **zero speed-up** (165.2 ms vs
> 167.1 ms at N=20,000) because it is array-work-bound, not interpreter-bound.
> And the premise underneath was never tested: a 320,000-policy book already
> prices in **5.2 s**. Even a perfect result across all four loops saves ~2.6 s on
> a book nobody is waiting for. One of four loops was measured, so this is a
> partial falsification — but the burden of proof has flipped, and the honest
> disposition is to stop.
>
> **What would revive it:** a profile showing `_build_rate_arrays` or the reserve
> recursions own a large share of runtime, **and** a workload where projection
> latency actually blocks someone (Monte-Carlo UQ over thousands of scenarios is
> the plausible candidate). Absent both, this stays parked.

**Total slices:** 4 (never started; slice 4 was additionally gated on a goldens decision)
**Estimated total scope:** ~4–6 dev-days

## Overall Goal

Raise the **serial** projection number by removing the month-by-month Python
loops from the product engines. ADR-180 measured a 1.77x parallel ceiling on 4
performance cores with six cores idle, and diagnosed the cause: per-deal
projection is GIL-bound by `for month in range(t)` loops around small per-step
NumPy calls. Shortening those loops helps **every** caller — CLI, REST,
dashboard, notebooks, the test suite, CI — not only the ones that opt into
`max_workers`, and it is the only route past the current parallel ceiling.

## Why this was constituted, and why that reasoning did not survive

Constituted 2026-08-03 on maintainer direction. `COMMERCIAL_VIABILITY_REVIEW_2026-07-15`
nominated A4′ (experience GAM) as the next Tier-A epic; A4′ has since shipped
(`CONTINUATION_experience_gam.md` COMPLETE), so the review's Tier-A ladder is
**exhausted** and step 5b had no unstarted Tier-A item. This epic was written to
fill that gap.

The gap was real. **This was the wrong thing to fill it with**, and the failure
was one of process rather than estimate: the epic was built from an inference
about where runtime goes, and the routine's own step-11b discipline —
quantify before acting — was applied to the *implementation* plan but never to
the epic's **premise**. Had it been, the 5.2 s figure for a 320k-policy book
would have ended the discussion before the plan was written.

The successor epic is the real-data experience-GAM diligence run
(`docs/PLAN_experience_gam_realdata.md`), which addresses the same "no Tier-A row
left" gap against the product thesis rather than against an inferred bottleneck.

## Decomposition

See the PLAN for the full reasoning, particularly §2 — the four loops look alike
and are **not** equally tractable, which is what drives this ordering.

### Slice 1: Attribute the runtime (measure, change nothing)
- **Status:** NOT STARTED (epic parked)
- **Depends on:** nothing (PR #183 merged)
- **Files to create/modify:** a hot-path map extension for
  `analytics/perf_harness.py` consumers (the module's `default_hot_paths()`
  docstring already names this as the intended extension point); a committed
  measurement doc.
- **Tests to add:** coverage for the new hot-path map; no production behaviour to
  test because there is none.
- **Acceptance criteria:**
  - A committed measurement attributing `project()` runtime across rate-array
    build / in-force factors / reserves / cash-flow assembly, at **two** block
    sizes (ADR-180 showed block size changes the picture).
  - **Zero** production-code change; `tests/qa/` goldens untouched by
    construction.
  - The measurement is allowed to **falsify the epic**. If the recursions are a
    minority of runtime, say so, stop, and record it — that result is worth more
    than the rewrite.

### Slice 2: Vectorise `_build_rate_arrays` (bit-identical)
- **Status:** PLANNED
- **Depends on:** Slice 1 merged (its measurement sizes the prize)
- **Scope:** the one loop that is **not** a recursion — per-month ages,
  durations, active mask, rate lookups, all independent — broadcast to `(N, T)`.
- **Acceptance:** goldens **byte-identical**; `assert_array_equal` between old
  and new rate arrays on a fixture block; harness shows the sub-path faster.

### Slice 3: `lx` as a cumulative product (bit-identical, association-preserving)
- **Status:** PLANNED
- **Depends on:** Slice 2 merged
- **Scope:** `lx[:,m] = lx[:,m-1]*(1-q)*(1-w)` → a cumulative product **that
  preserves the multiplication association**. The naive
  `cumprod((1-q)*(1-w))` reassociates, differs in the last ulp per step, and
  compounds over 240 steps into moved goldens. See PLAN §2.
- **Acceptance:** goldens byte-identical, **plus** an explicit test pinning the
  association — demonstrating the naive formulation differs and the shipped one
  does not. That test is the guard against a future "simplification" silently
  moving every reserve in the book.

### Slice 4: The reserve recurrences (GATED — goldens WILL move)
- **Status:** BLOCKED — needs a maintainer decision before implementation
- **Depends on:** Slice 3 merged **and** the decision below
- **Scope:** `V_t = (q_t·b + (1-q_t)·V_{t+1})·v − P` is a first-order linear
  recurrence. Its closed form sums the same quantities in a different order and
  subtracts a level premium each step — the setup for cancellation to differ
  between formulations. Any rewrite moves reserve numbers slightly, in every
  product that uses them.
- **The decision required:** (a) is a bit-level reserve change acceptable for the
  speed-up? (b) if so, at what tolerance, and do `tests/qa/` baselines get
  regenerated with the drift quantified in an ADR? (c) does the answer differ by
  basis — NET_PREMIUM / CRVM / GAAP?
- **Absent that decision**, this slice's deliverable is the **analysis only**:
  implement the closed form behind a comparison harness, quantify the drift on
  the committed golden configs, and present it. Shipping is a separate call.

## Context for Next Session

- **Slice 1 is a measurement slice and that is deliberate.** "The recursions are
  the bottleneck" is currently an inference from the *shape* of ADR-180's
  parallel curve, not a profile. It is a good inference. It is not a measurement,
  and this epic exists because ADR-180 refused to make that substitution about
  its own claim.
- The loops live in `src/polaris_re/products/term_life.py`:
  `_build_rate_arrays` (~line 107), `_compute_inforce_factors` (~line 163),
  `_compute_reserves_net_premium` (~line 271), `_compute_reserves_crvm`
  (~line 355). There are two further `for month` loops in that file worth
  attributing in slice 1 before assuming their kind.
- **Do not reach for Numba/Cython.** The claim under test is that NumPy
  broadcasting removes these loops. Adding a compiler is a different epic with
  its own dependency and packaging story, and it would mask whether the
  broadcasting claim was even true.
- The parallel curve will improve as a side effect of this work. That is a
  consequence to report in the closing ADR, not a goal to chase — and re-running
  `scripts/bench_portfolio_parallel.py` afterwards is a cheap way to show it.

## Open Questions (for human)

- **Slice 4's goldens decision** (above). It does not block slices 1–3, so the
  epic can advance three slices before it is needed. Answering early would let
  slice 4 ship as a rewrite rather than as an analysis.
- **Scope beyond `term_life`.** `whole_life` / `universal_life` / `annuity`
  presumably carry the same loop shapes. Slice 1's measurement should say whether
  the pattern generalises; if it does, that is a follow-on epic sized off real
  numbers, not a fifth slice bolted onto this one.

# Measurement: engine recursion vectorisation — pre-work that parked the epic

**Date:** 2026-08-03
**Context:** `docs/PLAN_engine_recursion_vectorisation.md` was constituted on
2026-08-03 from ADR-180's diagnosis. This measurement was taken the same day, in
answer to a maintainer question about floating-point tolerances, **before any
production code was written** — and it undercut the epic's premise. The epic is
now PARKED. This document is why.

**Machine:** the 4-core Linux container; NumPy 2.x, Python 3.12; SOA VBT 2015
Male NS; 20-year monthly horizon.

---

## 1. Floating-point multiplication is not associative (the premise check)

The PLAN claimed that a naive `cumprod` rewrite of the `lx` recursion would move
goldens because it reassociates the multiply. Challenged on the grounds that
these are scalars, not matrix products — correct, they are elementwise scalar
operations, and that is exactly why it holds:

```
(a*b)*c = 0.9872938911481822
a*(b*c) = 0.9872938911481821     <- 1 ulp apart
```

`lx[:, m] = lx[:, m-1] * (1-q[:, m-1]) * (1-w[:, m-1])` is an independent scalar
chain per policy, ~480 multiplications long. Reassociating rounds differently at
every step.

## 2. Measured deviation of each candidate rewrite

Array level, 5,000 policies × 240 months:

| rewrite | max abs | max rel |
|---|---|---|
| `lx` naive `cumprod((1-q)(1-w))` | 2.4e-15 | 5.1e-15 |
| `lx` separate `cumprod(1-q)*cumprod(1-w)` | 1.6e-15 | 3.3e-15 |
| reserves closed form (cumprod/cumsum) | $8.9e-10 | 9.1e-12 |

End-to-end PV drift, by block size:

| N | `lx` naive | reserves closed form |
|---|---|---|
| 6 | 7.0e-16 | 9.8e-15 |
| 100 | 8.5e-15 | 4.1e-14 |
| 5,000 | 8.1e-15 | 4.3e-14 |
| 20,000 | **0.0** | 1.5e-14 |

**Drift is non-monotonic in N and data-dependent** — at N=20,000 the `lx` PV
drift was exactly zero while at 5,000 it was 8e-15. A single measurement cannot
safely set a tolerance. Had slice 4 gone ahead, the recommendation was **rtol
1e-10** on reserves and PV: roughly three orders of margin over the worst
observed 4.3e-14.

## 3. `lx` CAN be vectorised bit-identically — and it buys nothing

Interleaving `(1-q)` and `(1-w)` into an `(N, 2T)` array, taking `cumprod`, then
selecting every second element reproduces the shipped multiplication order
exactly:

| N | interleaved cumprod bit-identical? | naive cumprod bit-identical? |
|---|---|---|
| 6 | **yes** | no (max rel 1.2e-15) |
| 5,000 | **yes** | no (max rel 2.4e-15) |
| 20,000 | **yes** | no (max rel 2.4e-15) |

So the tolerance question was avoidable for `lx`. But:

```
N=20000 lx timing:  loop 165.2 ms   interleaved-cumprod 167.1 ms
```

**No speed-up. None.** At realistic block sizes the Python loop overhead is ~1%
of that time — 240 iterations at a few microseconds each against ~165 ms of array
work. The loop is **array-work-bound, not interpreter-bound**, so removing the
interpreter from it removes nothing.

## 4. The goldens would not have caught any of this

Patching the naive `lx` into the engine and running all five committed golden
configs: the patch **executed** (5 calls, verified with a counter) and genuinely
perturbed the array by 1.9e-15 — and **every golden digest came back
bit-identical**. Full float precision, no rounding in the digest.

The golden block is **6 policies per cohort**. That is too small to detect a
last-ulp engine perturbation. "Goldens byte-identical" is therefore a *necessary
but insufficient* acceptance criterion for any numerical rewrite, and this is
worth knowing independently of whether the recursion epic ever runs: a future
change of this class would pass CI while altering the engine.

**Standing recommendation:** any numerical-rewrite PR must additionally assert
array-level equality on a realistically-sized block (≥5,000 policies), not rely
on `tests/qa/`.

## 5. Verdict: PARK the epic

The epic's case was "the recursions are the bottleneck, so vectorising them
raises the serial number for every surface at once". Two things broke it:

1. **The one loop measured vectorises to zero gain**, bit-identically. That is
   one of four loops — `_build_rate_arrays` does materially more Python work per
   iteration (fancy-indexed table lookups, masking, improvement) and might still
   pay — so this is a *partial* falsification, not a proof. But the burden of
   proof has flipped.
2. **The premise was never that speed is a problem.** A 320,000-policy book
   prices in **5.2 s** serial, 2.9 s with 4 workers (ADR-180 amendment 2). Even a
   perfect outcome across all four loops turns 5.2 s into ~2.6 s on a book that
   already finishes faster than a reader can read the output. No customer is
   blocked; nothing on a competitive comparison turns on it.

Constituting the epic was an error of process, not just of estimate: it was built
from an *inference* about where time goes, and the routine's own step-11b
discipline — quantify before acting — should have been applied to the epic's
premise before writing the plan, not after. It is recorded rather than deleted so
this is not re-proposed from the same inference in six months.

**What would revive it:** a profile (the epic's own slice 1) showing
`_build_rate_arrays` or the reserve recursions own a large fraction of runtime
*and* a workload where projection latency actually blocks someone — Monte-Carlo
UQ over thousands of scenarios is the plausible candidate, since it multiplies
the per-projection cost by ~1000. Absent both, this stays parked.

## Reproduce

The measurement scripts were scratch, not committed — they are ~40 lines each and
the tables above are the record. To redo: patch `TermLife._compute_inforce_factors`
/ `._compute_reserves_net_premium` with the candidate formulations, run
`tests/qa/golden_runner.run_pricing` over `discover_golden_cases()`, and diff the
digests; time the loop against the interleaved cumprod with `timeit` at
N=20,000.

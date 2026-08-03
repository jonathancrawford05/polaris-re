# Measurement: portfolio parallel execution — MacBook Air (Apple Silicon)

**Date:** 2026-08-03
**Hardware:** MacBook Air, Apple Silicon. **Exact chip / core split / RAM: TO BE
CONFIRMED by the maintainer** — the numbers below are the maintainer's, but the
machine spec was not captured in the transcript and is *inferred*, not observed.
The curve's bend point (see "Reading") is consistent with **4 performance
cores**, which every M-series Air has; fill in the precise model with
`sysctl -n hw.ncpu hw.perflevel0.logicalcpu hw.perflevel1.logicalcpu`.
**Mortality basis:** SOA VBT 2015 Male NS (`Loaded soa_vbt_2015_male_ns.csv:
ages 18-95` — the real table, not the synthetic fallback)
**Command set:** `docs/RUNBOOK_portfolio_parallel_measurement.md` §3, k=3,
20-year monthly horizon
**Counterpart:** ADR-180's 4-core Linux container table

Every row on every shape reported `bit-identical: yes`. The script aborts
non-zero on any divergence, so all three clean exits are also a correctness
result.

## A — 8 deals × 5,000 policies (40,000 total)

| workers | best-of-k (s) | speed-up | bit-identical |
|---------|---------------|----------|---------------|
| serial  | 0.659 | 1.00x | yes |
| 1       | 0.663 | 0.99x | yes |
| **2**   | **0.506** | **1.30x** | yes |
| 4       | 0.705 | **0.94x** | yes |
| 8       | 0.940 | **0.70x** | yes |

## B — 4 deals × 20,000 policies (80,000 total)

| workers | best-of-k (s) | speed-up | bit-identical |
|---------|---------------|----------|---------------|
| serial  | 1.254 | 1.00x | yes |
| 1       | 1.262 | 0.99x | yes |
| 2       | 0.803 | 1.56x | yes |
| **4**   | **0.797** | **1.57x** | yes |

## C — 16 deals × 20,000 policies (320,000 total)

| workers | best-of-k (s) | speed-up | bit-identical |
|---------|---------------|----------|---------------|
| serial  | 5.184 | 1.00x | yes |
| 1       | 5.184 | 1.00x | yes |
| 2       | 3.185 | 1.63x | yes |
| **4**   | **2.926** | **1.77x** | yes |
| 8       | 3.835 | 1.35x | yes |
| 16      | 4.210 | 1.23x | yes |

## Reading

**Peak speed-up: 1.77x at 4 workers on shape C** (the 320k-policy book) — the
largest and most realistic of the three, and the only one where the serial run
takes long enough (5.2 s) for anyone to care.

**The small-deal regression reproduced — the sign still flips with per-deal block
size.** Shape A peaks at **2** workers and goes *below serial* at 4 (0.94x) and 8
(0.70x), exactly the effect the 4-core box showed, just far less violently
(0.59x / 0.48x there). This is the ADR's central finding confirmed on
independent hardware, and it is why "just set it to 4" is the wrong instruction:
on shape A, 4 workers is a slowdown.

**The curve bends at 4 on every shape, which is the performance-core count, not
the total core count.** The runbook flagged this as a hypothesis to test, and the
data supports it: 8 and 16 workers are consistently worse than 4 even on shape C,
where there is plenty of work to go round. Efficiency cores do not appear to
contribute usefully to this workload. The practical rule that falls out is
**match `max_workers` to performance cores**, not to `hw.ncpu`.

**Oversubscription degrades gracefully here, unlike on 4 cores.** On shape C, 8
and 16 workers still beat serial (1.35x, 1.23x) — they merely give back most of
the gain. On the 4-core container the equivalent overshoot went to 0.48x. More
cores makes the mistake cheaper, not free.

**`max_workers=1` measured 0.99–1.00x of serial on all three shapes.** That is
the serial short-circuit doing what it claims: `1` takes the same code path as
`None` and never constructs a pool.

**Absolute speed, for context:** this machine runs shape A's serial case in
0.659 s against the 4-core container's 3.80 s — roughly 5.8x faster on the same
work. Some of shape A's flatness here is simply that there is under a second of
work to spread.

### Confound worth stating

A MacBook Air is **fanless**. Sustained multi-core load throttles, so part of the
8- and 16-worker degradation on shape C may be thermal rather than
GIL/oversubscription. Best-of-k takes the *minimum*, which mitigates but does not
eliminate this — a later sample runs hotter than an earlier one. The 4-worker
peak is unaffected either way (it is faster *and* cooler than the 8/16 runs), so
the headline conclusion stands; the exact shape of the tail past 4 is the part to
treat as soft. Re-running shape C on an actively-cooled Mac (Pro/Max) would
settle it.

## Verdict on the ADR-180 open question

**Does this clear the bar the CONTINUATION floated (1.5x? 2x?)** — it clears
**1.5x** and does not reach **2x**. Peak 1.77x (shape C), 1.57x (shape B), and
still a regression on shape A past 2 workers.

**Keep `max_workers`, or remove it?** — **KEEP.** Recorded as the maintainer's
decision on 2026-08-03, on this evidence. The rationale that survives scrutiny is
narrow and worth stating precisely rather than rounding up to "parallel works":

- On a realistic large book (320k policies), 4 workers cuts a 5.2 s run to 2.9 s.
  That is a real, reproducible, bit-identical win on the shape a reinsurer
  actually prices.
- It is **not** a general-purpose accelerator. It is negative on small-deal books
  past 2 workers, and it caps out near the performance-core count regardless of
  how many cores are nominally available.
- So the knob stays **off by default**, and its documentation continues to lead
  with "measure first" — now with a concrete rule (match performance cores; large
  per-deal blocks only) instead of a bare warning.

The larger throughput win is unchanged by this result and is not about threads:
per-deal projection is GIL-bound by the month-by-month Python recursions in
`products/term_life.py`. A 1.77x ceiling on 4 P-cores is what a GIL-bound
workload looks like; shortening those loops raises the serial number for every
surface at once. Filed as IMPORTANT in `docs/PRODUCT_DIRECTION_2026-07-24.md`.

## Raw data

`/tmp/polaris-par/{A,B,C}.json` on the maintainer's machine (per-sample seconds,
not just the best-of-k minimum). Not committed — the tables above are the record;
re-generate with the runbook's §3 commands.

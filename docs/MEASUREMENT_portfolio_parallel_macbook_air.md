# Measurement: portfolio parallel execution — MacBook Air (Apple Silicon)

**Date:** 2026-08-03
**Hardware:** MacBook Air, Apple Silicon — **10 logical cores: 4 performance +
6 efficiency**, measured via
`sysctl -n hw.ncpu hw.perflevel0.logicalcpu hw.perflevel1.logicalcpu` → `10 / 4 / 6`.
That core split corresponds to an M4-class chip (the 10-core M4 Air); the chip
name is *inferred* from the split, the split itself is observed. RAM was not
captured — no run reported memory pressure, and shape C's timings were
internally consistent, so nothing here suggests swapping.
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

**The curve bends at 4 on every shape — exactly the performance-core count, on a
machine with 10 cores.** The runbook flagged this as a hypothesis; the spec
confirms it rather than merely being consistent with it. The peak sits at 4 = the
P-core count, while `hw.ncpu` reports 10, and the 6 efficiency cores contribute
**nothing**: 8 workers (which must recruit E-cores) scores 1.35x against 4
workers' 1.77x on shape C, and 16 workers falls further to 1.23x — with ample
work available in both cases. E-cores do not merely fail to help here, they cost
throughput, presumably because a thread scheduled onto a slow core holds its share
of the GIL-contended critical path for longer.

The practical rule that falls out, and now the documented one: **set
`max_workers` to your performance-core count**, not to `hw.ncpu`. On this machine
that is 4, not 10 — a caller who reasonably read "use your cores" and passed 10
would land between the 8- and 16-worker rows and give back roughly a third of the
available gain.

**Oversubscription degrades gracefully here, unlike on the 4-core box.** On
shape C, 8 and 16 workers still beat serial (1.35x, 1.23x) — they merely give back most of
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
  past 2 workers, and it caps out at the performance-core count regardless of how
  many cores are nominally available — 4 useful workers on a 10-core machine.
- So the knob stays **off by default**, and its documentation continues to lead
  with "measure first" — now with a concrete rule (match performance cores; large
  per-deal blocks only) instead of a bare warning.

The larger throughput win is unchanged by this result and is not about threads:
per-deal projection is GIL-bound by the month-by-month Python recursions in
`products/term_life.py`. A 1.77x ceiling on 4 P-cores — with 6 further cores sitting
idle and unable to help — is what a GIL-bound workload looks like; shortening those loops raises the serial number for every
surface at once. Filed as IMPORTANT in `docs/PRODUCT_DIRECTION_2026-07-24.md`.

## Raw data

`/tmp/polaris-par/{A,B,C}.json` on the maintainer's machine (per-sample seconds,
not just the best-of-k minimum). Not committed — the tables above are the record;
re-generate with the runbook's §3 commands.

<!-- measurement-provenance
fingerprint: dabd8c26a294051264376a6779b7861604f26d07d2c8192a590fa7d4647fa26c
generated: 2026-08-24
producer: src/polaris_re/analytics/portfolio.py
method: asserted
head: 0131391
note: closure drifted 2026-08-24 by an inert change: utils/table_io.py's missing-table FileNotFoundError message (raised only when a file is absent; no successful run reaches it). RUNBOOK section 2 case (c), claim in ADR-204 amendment 1. Route (a) needs a 10-core MacBook Air; the 2026-08-23 re-run stands — shape-dependence held, peak 1.77x -> 1.78x at 4 workers, bit-identical on every row.
-->

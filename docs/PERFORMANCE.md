# Performance & Scale

This page backs the README's *vectorized, no loops over policies* claim with a
reproducible timing table, and documents how to regenerate it. It is the
**timing** counterpart to `polaris benchmark` (which checks numerical
*correctness* against published actuarial references).

## The claim, and the evidence

Polaris RE projects an inforce block as `(N × T)` NumPy arrays — `N` policies ×
`T` monthly steps — with **no Python loop over policies**. The observable
consequence is *linear scaling*: projection wall-clock time grows in proportion
to the block size, and throughput (policies/second) stays within the same order
of magnitude from a thousand to half a million policies. An engine with a hidden
per-policy Python loop would instead degrade super-linearly.

## Committed timing table

Measured on a single core, projecting a deterministic synthetic TERM block
(SOA VBT 2015 Male NS mortality, duration-based lapse) over a **20-year monthly
horizon** (240 steps) at a 5% discount rate:

| Policies | Projection time | Policies / sec | Cell-updates / sec | Peak RSS |
|---------:|----------------:|---------------:|-------------------:|---------:|
| 1,000    | 0.06 s          | 17,344         | 4,162,568          | 171 MB   |
| 10,000   | 0.63 s          | 15,764         | 3,783,298          | 381 MB   |
| 100,000  | 11.35 s         | 8,809          | 2,114,208          | 2,144 MB |
| 500,000  | 66.21 s         | 7,552          | 1,812,489          | 10,132 MB |

Reading the table:

- **Time is near-linear in `N`.** From 100K to 500K (5× the policies) time grows
  ~5.8× — the signature of an `O(N)` engine, not an `O(N²)` one. (The modest
  throughput taper at large `N` is memory-bandwidth / cache pressure as the
  working set outgrows CPU cache, not per-policy Python overhead.)
- **Cell-updates/sec** = `N × T / seconds` is the raw array-update rate the
  vectorized kernels sustain.
- **Peak RSS** is the process high-water mark; it grows linearly with `N`
  because the `(N × T)` seriatim arrays dominate. Budget ~10 GB for 500K over a
  20-year horizon; a shorter horizon or smaller block scales it down
  proportionally.

*Absolute times are hardware-dependent — treat them as an order-of-magnitude
reference and the scaling shape (linear) as the portable property.*

## Regenerate it

```bash
# Default sizes (1K / 10K / 100K):
uv run python scripts/scale_benchmark.py

# Full published range (needs ~10 GB RAM for the 500K row):
uv run python scripts/scale_benchmark.py --sizes 1000 10000 100000 500000 \
    -o docs/PERFORMANCE_local.md

# Shorter horizon / different discount:
uv run python scripts/scale_benchmark.py --horizon-years 10 --discount-rate 0.06
```

The script prefers the real SOA VBT 2015 table under `data/mortality_tables/`
(run `scripts/convert_soa_tables.py` first); if it is absent it falls back to the
committed synthetic fixture so the harness still runs.

## Programmatic use

The harness is a first-class analytics component
(`polaris_re.analytics.scale_benchmark`), so you can drive it against any
`AssumptionSet` / `ProjectionConfig` and consume the structured result:

```python
from polaris_re.analytics import run_scale_benchmark

report = run_scale_benchmark([1_000, 10_000, 100_000], assumptions, config)
print(report.to_markdown())
for row in report.rows:
    print(row.n_policies, row.policies_per_second, row.peak_rss_mb)
```

Sizes must be strictly ascending — this makes the per-row peak-RSS attribution
exact, because `ru_maxrss` is a process high-water mark and each successively
larger run's peak *is* that size's peak.

See ADR-161 in [`docs/DECISIONS.md`](DECISIONS.md) for the design rationale.

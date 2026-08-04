# Runbook: measure the portfolio parallel curve on your own hardware

**Purpose:** produce the many-core half of ADR-180's measurement. Everything in
that ADR came off a **4-core Linux container**, which is a thin basis for judging
a feature whose whole premise is having cores to spare. This runbook is how you
generate the comparable numbers on a MacBook and get them into `docs/`.

**Time:** ~10 min setup (first run only), ~15–25 min of measuring.
**You need:** the repo cloned, `uv` installed, and to leave the laptop alone
while it runs.

---

## 0. How many cores do you have?

```bash
sysctl -n hw.ncpu              # total logical cores
sysctl -n hw.perflevel0.logicalcpu   # performance cores (Apple Silicon)
sysctl -n hw.perflevel1.logicalcpu   # efficiency cores (Apple Silicon)
```

Write these down — they go in the results table. On Apple Silicon the split
matters: an M-series chip with 8P+4E cores will not behave like 12 uniform cores,
and a worker count above the **performance**-core count is where you should
expect the curve to bend. That is a hypothesis to test, not a conclusion.

---

## 1. One-time setup

```bash
cd /path/to/polaris-re
git checkout claude/quirky-ramanujan-5zhsw3     # or main, once #183 is merged
uv sync --all-extras
uv run python scripts/convert_soa_tables.py --source pymort --output-dir data/mortality_tables
```

The table conversion is optional but preferred: the benchmark uses the real SOA
VBT 2015 male non-smoker table when it is present and silently falls back to the
committed synthetic fixture when it is not. Either is internally consistent — but
**record which one you used**, because the two are not comparable to each other.
The script prints it at startup (`Loaded soa_vbt_2015_male_ns.csv…`).

Sanity-check that the engine works before you spend 20 minutes timing it:

```bash
uv run python scripts/bench_portfolio_parallel.py --n-deals 2 --n-policies 500 --workers 2 --k 1
```

Should finish in seconds and print `bit-identical: yes` on both rows.

---

## 2. Quiet the machine

Wall-clock measurement is only as good as the idle around it. Before the real
runs:

- Quit Slack, Docker Desktop, Chrome, Spotlight-heavy apps, anything syncing.
- **Plug in the power adapter.** On battery, macOS will throttle sustained
  multi-core load and you will measure the power manager, not the code.
- Don't use the laptop while it runs. Don't let it sleep (`caffeinate -i` in
  front of the command if you want to be sure).
- Consider running the whole set twice and keeping the second — the first pass
  warms the page cache and the thermal state.

---

## 3. The measurement set

Three shapes. The point of running all three is that ADR-180's finding was not
"threads are good/bad" but "**it depends on per-deal block size**" — small deals
regressed, large deals gained. Confirming or refuting *that* on many cores is
worth more than one headline number.

Set `NW` to a worker list that spans your core count, e.g. for a 10-core M1 Pro:
`1 2 4 8 10 16`.

```bash
mkdir -p /tmp/polaris-par

# A — many small deals (the shape that REGRESSED on 4 cores: 0.59x at 4 workers)
uv run python scripts/bench_portfolio_parallel.py \
  --n-deals 8 --n-policies 5000 --workers 1 2 4 8 --k 3 \
  -o /tmp/polaris-par/A_8x5000.json

# B — fewer, larger deals (the shape that GAINED on 4 cores: 1.29x at 4 workers)
uv run python scripts/bench_portfolio_parallel.py \
  --n-deals 4 --n-policies 20000 --workers 1 2 4 --k 3 \
  -o /tmp/polaris-par/B_4x20000.json

# C — the many-core question: enough deals to actually saturate your cores
uv run python scripts/bench_portfolio_parallel.py \
  --n-deals 16 --n-policies 20000 --workers 1 2 4 8 16 --k 3 \
  -o /tmp/polaris-par/C_16x20000.json
```

**Watch memory on C.** 16 deals × 20k policies × 240 months is a large working
set, and every concurrent worker holds its own. If you see the beachball or
`memory_pressure` climbing, drop to `--n-deals 8` and say so in the results —
a run that swapped is not a measurement of anything.

The script prints a table and writes JSON. It aborts non-zero if any worker count
produced numbers differing from serial, so a clean exit is also a correctness
result worth recording.

---

## 4. What the output means

```
 max_workers |  best-of-k (s) |  speed-up | bit-identical
      serial |          3.799 |     1.00x | yes
           2 |          3.197 |     1.19x | yes
           4 |          6.414 |     0.59x | yes
```

- **serial** is `max_workers=None` — the shipped default path, not a one-worker
  pool. That's the honest baseline because it's what callers actually get.
- **best-of-k** is the *minimum* of k samples, not the mean. The mean is dragged
  by the first-call and GC outliers; the minimum is the stable estimator.
- **speed-up** is `serial / this` — above 1.00x is faster, below is slower.
- **bit-identical** must be `yes` on every row. If it is ever `no`, stop and file
  it — that is a correctness bug and far more important than any timing.

Every sample builds a **fresh cold** `Portfolio(cache=False)`, so no run is
reusing a previous projection. That's deliberate: a warm cache would make a
re-run free to parallelise and show a flattering ratio that measures nothing.

---

## 5. Also try the real CLI path

The benchmark measures `Portfolio.run` in isolation. The CLI additionally pays
config parsing, inforce CSV load, mortality-table load, and output rendering, so
its end-to-end speed-up will be **smaller** than the benchmark's — Amdahl, and
currently unmeasured. Worth one data point on a config of your own:

```bash
time uv run polaris portfolio run --config your_book.yaml -o /tmp/serial.json
time uv run polaris portfolio run --config your_book.yaml -o /tmp/par8.json --max-workers 8

# The outputs must be identical — this is the CLI-level correctness check:
diff /tmp/serial.json /tmp/par8.json && echo "IDENTICAL"
```

`--max-workers` exists on `polaris portfolio run` and `polaris portfolio
scenarios`. On the scenarios command the scenarios stay sequential and only the
per-deal projections within each fan out.

---

## 6. Capture the results

Copy this into `docs/MEASUREMENT_portfolio_parallel_<hardware>.md` and fill it in
(the JSON files under `/tmp/polaris-par/` have the raw samples if you want to
attach them):

```markdown
# Measurement: portfolio parallel execution — <e.g. MacBook Pro M3 Max>

**Date:** YYYY-MM-DD
**Hardware:** <chip>, <N> cores (<P> performance + <E> efficiency), <RAM> GB
**OS / Python:** macOS <version>, Python <version>
**Mortality basis:** SOA VBT 2015 male NS  |  synthetic fixture   <-- pick one
**Power:** plugged in / battery       **Machine otherwise idle:** yes / no
**Command set:** docs/RUNBOOK_portfolio_parallel_measurement.md §3, k=3

## A — 8 deals x 5,000 policies

| workers | best-of-k (s) | speed-up | bit-identical |
|---------|---------------|----------|---------------|
| serial  |               | 1.00x    | yes           |
| 2       |               |          |               |
| ...     |               |          |               |

## B — 4 deals x 20,000 policies
(same table)

## C — 16 deals x 20,000 policies
(same table)

## CLI end-to-end (§5, optional)
| run | wall clock | outputs identical |
|---|---|---|
| serial | | — |
| --max-workers N | | yes / no |

## Reading

- Peak speed-up: **__x** at __ workers on shape __.
- Did the small-deal regression reproduce? yes / no — __
- Where does the curve bend relative to core count? __
- Any row not bit-identical? (should be none) __

## Verdict on the ADR-180 open question

Does this clear the 1.5x / 2x bar the CONTINUATION floated? __
Keep `max_workers`, or remove it? __
```

---

## 7. Then what

- **If it clears the bar on many cores:** the numbers go into ADR-180 as an
  amendment (a second table beside the 4-core one), the `run` docstring and the
  `--max-workers` help text get rewritten around the real curve instead of the
  4-core caveat, and the knob's open question closes as *keep*.
- **If it doesn't:** that closes the question as *remove* on evidence rather than
  inference, and the revert is small and self-contained. The measurement itself
  is still worth committing — a documented negative result is what stops someone
  re-proposing this in six months.
- **Either way**, the larger win is unchanged and is not about threads: the
  per-deal projection is GIL-bound by the month-by-month Python recursions in
  `products/term_life.py` (in-force factor `lx`, net-premium reserve, CRVM
  reserve). Shortening or vectorising those raises the **serial** number for every
  surface at once. It's filed as IMPORTANT in
  `docs/PRODUCT_DIRECTION_2026-07-24.md`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Loaded soa_vbt_2015_male_ns.csv` missing from the output | Tables not converted — rerun step 1's `convert_soa_tables.py`. The fallback fixture is fine, just record it. |
| Wildly inconsistent samples between runs | Something else is using the CPU, or thermal throttling. Plug in, quit background apps, re-run. Compare `samples_seconds` in the JSON — spread tells you how noisy the box was. |
| Beachball / swapping on shape C | Working set too large. Drop `--n-deals` to 8 and note it. |
| A row reports `bit-identical: no` | **Stop and report it.** The script exits non-zero on this. It is a correctness defect, not a perf result. |
| Speed-up below 1.00x everywhere | A real result, not a mistake — record it. That is what the 4-core box showed on shape A. |

# Runbook: local ILEC attribution probe (ADR-260 amendment 1)

**Purpose.** Check on real cells what Stage A inferred from structure: (1) nothing is binned
(every covariate has at most 1000 unique values) and (2) `bam(discrete=TRUE)`'s gap from `gam` is
the algorithm, so `bam(discrete=FALSE)` and `bam(discrete=TRUE)` agree closely. Not blocking Stage B.
**Output is derived scalars only** (PLAN §3): sizes, times, `max|Δη|`, edf, iteration counts. No
coefficients, contrasts, rows or levels.

## Before you start
- Cells `T1_mid` (and optionally `S2_mid`) must exist under `$WORK`, i.e. `$WORK/T1_mid/cells.csv`
  and `spec.json`. They were written by your earlier R2/PR #270 runs. If you deleted `$WORK`,
  recreate them with `gam_real_data_trial.py run-cell` (runbook `RUNBOOK_gam_real_data_trial.md`
  §3, with `--repeats 1 --no-profile` to keep it short).
- Native R with `mgcv` and `jsonlite` (as for PR #270). Mains power. Record nothing else.
- Pull the branch: `git fetch origin claude/dreamy-galileo-ckoo7w && git checkout claude/dreamy-galileo-ckoo7w`.

## Run
```sh
cd polaris-re
export WORK="$HOME/polaris_trial_scratch"
export OPENBLAS_NUM_THREADS=1            # same for all three runs
scripts/bam_attribution_local.sh T1_mid  2>&1 | tee "$WORK/attribution_T1_mid.txt"
# optional, slower and memory-hungry (gam on S2_mid took ~390 s and ~9 GB in PR #270):
scripts/bam_attribution_local.sh S2_mid  2>&1 | tee "$WORK/attribution_S2_mid.txt"
```
Expected on `T1_mid`: `bam` ~0.5 s, `bam_nodisc` seconds to a minute, `gam` ~25 s (PR #270). It runs
`bam` first, then `bam_nodisc`, then `gam`, so a failure in the slow run keeps the earlier readings.

## What to send back
Paste the printed text of each run (it contains only scalars). The lines that matter:
- `unique values per covariate (sizes): [...]` all `<= 1000`  -> nothing binned, premise holds.
- `max |d eta| bam(discrete=FALSE) vs bam(discrete=TRUE)`: ~1e-6 to 1e-4 is consistent with the synthetic cell; **much larger than that means discretisation matters on real cells** and Stage A's finding 1 needs revisiting.
- `max |d eta| gam vs bam(discrete=FALSE)` close to the existing `gam` vs `bam` figure (0.0205 at T1_mid) -> the gap is the algorithm.
- `iterations:` for the two `bam` runs.

## Stop and report (do not retry blindly)
Any R error, a run that exceeds ~30 min, memory exhaustion (note which method), a `n_unique`
above 1000, or `max|Δη|` between the two `bam` runs above 1e-2.

## Afterwards
`rm -f "$WORK"/*/probe_*.json "$WORK"/*/probe_*.out "$WORK"/*/probe_*.time` (per-row output).
The pasted text is what gets recorded (as tier-L, real data, maintainer-run, with R/mgcv versions
the script prints).

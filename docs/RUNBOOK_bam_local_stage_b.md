# Runbook — Stage B local runs: Polaris `bam` vs `bam(discrete=TRUE)` on the real cells (tier L)

**For:** the maintainer / Claude Cowork on the reference MacBook. **Purpose** (ADR-260 amendments 4-5):
(1) the **gate check** — do the unchanged R2 gates hold on `T1_mid` / `S2_mid`-class cells where exact-REML
`gam` sits 1.9e-2..2.1e-2 from `bam` (gate 2e-2)? (2) `bam`'s **own seed noise floor** on real cells
(decides whether the padded frame is ever worth porting); (3) **time and memory** against the
10-minute ceiling, `mid` first, then `full`. **Output: derived scalars only** (PLAN §3). Per-row `eta`/`se`
stay in `$WORK/<cell>/*.json` scratch files that are never committed.

## STOP-AND-REPORT (do not work around)
1. Any command fails, or the R probe prints an error. 2. A fit exceeds ~30 min or the machine runs out of
memory (say which half: Polaris or R, and the cell). 3. The output file holds anything you did not expect:
do not edit it. 4. `all_gates_met` false, or `converged` false: **report, do not retry or tune.**

## What to expect (so a refusal is not a surprise)
| cell | expected |
|---|---|
| `T1`, `T2` | supported; the main readings |
| `T3c` (`select=TRUE`, factor-`by`) | supported; the shape R1 verified |
| `T3a`, `S2`, `S3` | **`status: refused`** — their design is structurally rank-deficient (ADR-256) and `bgam.fitd` pivots its Cholesky; the port does not (ADR-260 amendment 2). A refusal is a recorded result. This means **`S2_mid` cannot be read in this slice**; use `T3c` as the factor-`by` cell. |
| `T3b` | refused by `gam()` (ADR-258), skip |

## 0. Setup (once)
```bash
cd ~/polaris-re
git fetch origin claude/dreamy-galileo-l09zt5 && git checkout claude/dreamy-galileo-l09zt5 && git pull
uv sync --all-extras
export OPENBLAS_NUM_THREADS=1                      # same for every run below
export WORK="$HOME/polaris_trial_scratch"          # LOCAL ONLY; must already hold loader_cells.parquet
git rev-parse HEAD                                  # the output records it
Rscript -e 'cat(R.version.string, as.character(packageVersion("mgcv")), "\n")'
```
Mains power, Low Power Mode off, other heavy apps closed. **mgcv version matters**: the CI oracle is mgcv
1.9.4 / R 4.6.1. Native R with mgcv 1.9.4 is acceptable (label it; it is what the earlier local probes used);
if you want the pinned image instead, pass `--r-command` (step 3) — the image is `linux/amd64`, so on Apple
Silicon it runs emulated and **timings of the R half are then not comparable** (agreement numbers are).
If `$WORK/loader_cells.parquet` is missing, re-run `prepare` (`RUNBOOK_gam_real_data_trial.md` §3).

## 1. Write the cells (no fitting; seconds)
```bash
for CELL in "T1 mid" "T2 mid" "T3c mid"; do set -- $CELL
  uv run python scripts/gam_real_data_trial.py write-cell --work "$WORK" --formula $1 --granularity $2
done
```
(Later: `T1 full`, `T2 full`, `T3c full` — only after the `mid` results are back and sane.)

## 2. Optional baseline: exact-REML `gam` on the same cell (slow, memory-hungry; only for `mid`)
```bash
scripts/bam_attribution_local.sh T1_mid 2>&1 | tee "$WORK/attribution_T1_mid.txt"
```
If `$WORK/T1_mid/probe_gam.json` exists, step 3 adds `eta_max_abs_gam_vs_bam` automatically.

## 3. The Stage-B run, per cell (Polaris half then the R seed probe; ~minutes at `mid`)
```bash
uv run python scripts/bam_local_run.py --cell "$WORK/T1_mid" --repeats 3 \
  --chip "Apple M? , ?P+?E cores, ?? GB" 2>&1 | tee "$WORK/stageb_T1_mid.txt"
# same for T2_mid and T3c_mid
```
Options: `--skip-r` (Polaris timing/memory only; use this first at `full` to see whether Polaris fits at
all); `--seeds 1,2,3,4,5,6` (default); `--r-command 'docker run --rm -e OPENBLAS_NUM_THREADS=1 -v
"$WORK":"$WORK" -v "$PWD":"$PWD":ro IMAGE Rscript'` for the pinned image (paths must be identical inside and
outside the container, hence the same-path mounts).
The script fits Polaris (`gam(method="fREML", discrete=True)`, best of `--repeats`), then `bam(discrete=TRUE)`
at mgcv's seed 8547 and six others, and writes `$WORK/<cell>/bam_local.json` (checked against a whitelist).

## 4. What to send back (paste the printed `=== derived scalars ===` block of each cell)
The lines that decide things:
- `agreement_vs_default_seed.all_gates_met` and the four numbers (`eta_max_abs` < 2e-2, `edf_total_abs` < 1,
  `se_rel_max` < 2e-2, `eta_scaled_max` <= 0.1, flag > 0.01).
- `seed_noise_floor.bam_eta_spread` against `eta_max_abs`, and `spread_at_least_residual`. **This is the
  decision input** (maintainer rule, PR #273): spread >= residual means `bam` is only defined to about that
  precision and R's random stream is not ported; spread much smaller means the padded frame must be replicated.
- `polaris.best_seconds`, `polaris.peak_rss_mb`, `polaris.n_iterations`, `ceiling_met`
  (the 10-minute ceiling is on the Polaris fit only), `ratio_polaris_over_bam_default`.
- `mgcv.iterations_by_seed` (a seed that changes the iteration count is itself a finding).
- `gam_baseline.eta_max_abs_gam_vs_bam` if you ran step 2.

## 5. Then `full` (only if `mid` is sane)
`write-cell ... --granularity full`, then `bam_local_run.py --skip-r --repeats 1` **first** (does Polaris fit
and within the ceiling? what peak RSS? `bam` used 2.7 GB at `S2_full`; a Polaris path needing more is a
finding), then the full run without `--skip-r` if memory allows. Report a memory failure as a result.

## 6. Cleanup
`rm -f "$WORK"/*/bam_local_seeds.json "$WORK"/*/probe_*.json "$WORK"/*/probe_*.out "$WORK"/*/probe_*.time`
(per-row output). Keep `bam_local.json` only if you decide to commit it (`docs/measurements/`, DATA_LICENSING §5);
otherwise the pasted text is what gets recorded, labelled **tier L, real data, maintainer-run**, with the
R/mgcv versions and chip it prints.

## 7. T3c_mid design-conditioned diagnostic (ADR-260 amendment 8) — the next run
Why: Polaris-`bam` sits on the exact-REML optimum (7.3e-4) while `bam` is 1.19 away on every seed. This run
hands Polaris `bam`'s OWN design and compares the iteration trace, to say whether the difference is the
design (what `discrete=TRUE` builds) or the algorithm port. Scratch files (X is ~0.5 GB, never committed)
go to `$WORK/T3c_mid/design_probe/`; the printed output is scalars only.
```bash
cd ~/polaris-re && git pull
export OPENBLAS_NUM_THREADS=1
export WORK="$HOME/polaris_trial_scratch"
uv run python scripts/bam_local_design_run.py --cell "$WORK/T3c_mid" 2>&1 | tee "$WORK/design_T3c_mid.txt"
```
Takes a few minutes (it refits `bam` once per iteration, ~15 times, and rebuilds X column by column).
Paste the whole `=== derived scalars` block. Afterwards `rm -rf "$WORK/T3c_mid/design_probe"` (0.5 GB+).
Stop and report if R errors or memory runs out (say which half).

## 8. Re-run after ADR-260 amendment 9 (constraint from distinct covariate values)
```bash
cd ~/polaris-re && git pull
export OPENBLAS_NUM_THREADS=1
export WORK="$HOME/polaris_trial_scratch"
export CHIP="Apple M4, 4P+6E cores, 24 GB, macOS 27.0.1, AC power"
for C in T3c_mid T1_mid T2_mid T1_full; do
  uv run python scripts/bam_local_run.py --cell "$WORK/$C" --repeats 1 --chip "$CHIP" 2>&1 | tee "$WORK/stageb2_$C.txt"
done
```
Paste each `=== derived scalars` block (or just the `agreement_vs_default_seed`, `seed_noise_floor`,
`localisation` and `polaris` sections). What decides the next step: does Polaris now lie INSIDE `bam`'s seed
cloud on `T3c_mid` (`polaris_vs_other_seeds_max` below `bam_eta_spread`, and `eta_max_abs` of the same order)?
Optional, only if `T3c_mid` is still far: `uv run python scripts/bam_local_design_compare.py "$WORK/T3c_mid"`
(needs `design_probe/` from §7; rerun §7 if you removed it) pastes per-penalty design-difference scalars.

## 9. Re-score existing scratch files with the cloud statistics (about a minute per cell)
`bam_local_seeds.json` from an earlier run is reused (no R), Polaris is refitted, and the output gains
`seed_noise_floor.envelope_excess_max`, `n_rows_outside_envelope`, `eta_max_abs_vs_seed_median` and
`bam_seed_eta_max_abs_vs_seed_median`:
```bash
for C in T3c_mid T1_mid T2_mid; do
  uv run python scripts/bam_local_run.py --cell "$WORK/$C" --repeats 1 --chip "$CHIP" --reuse-seeds 2>&1 | tee "$WORK/stageb3_$C.txt"
done
```

## 10. Full-granularity runs, rank-deficient cells and a binomial cell (after ADR-260 amendment 12)
Memory is the risk: at `mid` Polaris peaks at 3-4.6 GB for 0.9M cells, so ~3.0M cells (`T2_full`, `T3c_full`)
may need 12-16 GB of a 24 GB machine. Run the Polaris half ALONE first (`--skip-r`), one cell at a time, and
nothing else open. A failure here is a result (paste the last 20 lines and the RSS), not something to retry.
```bash
cd ~/polaris-re && git pull
export OPENBLAS_NUM_THREADS=1
export WORK="$HOME/polaris_trial_scratch"
export CHIP="Apple M4, 4P+6E cores, 24 GB, macOS 27.0.1, AC power"
for F in T2 T3c; do
  uv run python scripts/gam_real_data_trial.py write-cell --work "$WORK" --formula $F --granularity full
  /usr/bin/time -l uv run python scripts/bam_local_run.py --cell "$WORK/${F}_full" --repeats 1 --skip-r --chip "$CHIP" 2>&1 | tee "$WORK/stageb_${F}_full_polaris.txt"
done
```
Paste the derived-scalars block and the `maximum resident set size` line of each. Only if a cell fitted and
memory stayed below ~14 GB, run its full comparison (R fits `bam` seven times; `bam` used 2.7 GB at `S2_full`):
```bash
uv run python scripts/bam_local_run.py --cell "$WORK/T2_full" --repeats 1 --chip "$CHIP" 2>&1 | tee "$WORK/stageb_T2_full.txt"
```
Rank-deficient cells (now fitted by pivoting; per-term edf is not identified, eta/edf_total/se are):
```bash
for F in T3a S2; do
  uv run python scripts/gam_real_data_trial.py write-cell --work "$WORK" --formula $F --granularity mid
  uv run python scripts/bam_local_run.py --cell "$WORK/${F}_mid" --repeats 1 --chip "$CHIP" 2>&1 | tee "$WORK/stageb_${F}_mid.txt"
done
```
Binomial (the trial's `S1`; `write-cell` refuses a granularity where deaths exceed exposure, which is itself a
result; try coarse, then mid):
```bash
for G in coarse mid; do
  uv run python scripts/gam_real_data_trial.py write-cell --work "$WORK" --formula S1 --granularity $G \
    && uv run python scripts/bam_local_run.py --cell "$WORK/S1_$G" --repeats 1 --chip "$CHIP" 2>&1 | tee "$WORK/stageb_S1_$G.txt"
done
```
Re-score `T1_full` with the cloud statistics (no R):
`uv run python scripts/bam_local_run.py --cell "$WORK/T1_full" --repeats 1 --chip "$CHIP" --reuse-seeds`.

## 11. S1 (binomial) with trials floored at deaths (ADR-260 amendment 15)
```bash
cd ~/polaris-re && git pull
for G in coarse mid; do
  uv run python scripts/gam_real_data_trial.py write-cell --work "$WORK" --formula S1 --granularity $G --floor-trials-at-deaths \
    && uv run python scripts/bam_local_run.py --cell "$WORK/S1_$G" --repeats 1 --chip "$CHIP" 2>&1 | tee "$WORK/stageb_S1_$G.txt"
done
```
`write-cell` prints how many cells were floored; the output carries `trials_floor` and `n_cells_floored`. Both engines
fit the same floored table, so this tests the engine, not the modelling choice.


# Runbook — the ILEC trial of the GAM fitter (Slice R2, tier L)

**For:** the maintainer (or Claude Cowork acting for them) on the reference MacBook. **Output:** ONE JSON
file of derived scalars. **Plan:** `PLAN_gam_real_data_readiness.md` §3; **ADR-259**.
The ILEC file, the cell files and every scratch file stay on this machine. Nothing but the output
file may leave it, and `real_data_trial.dumps` refuses to write anything else.

## STOP-AND-REPORT conditions (do not work around any of them)
1. Any command below fails or a data rule asserts (`data rule 1/2/3 failed`).
2. `check-window` shows a step in exposure share at 2018-2019 (a new submitting company). Report the
   *fact* (not the table) and let the maintainer pick the window (`--years 2012-2017` etc.).
3. The image architecture differs from the host's AND you cannot run Polaris in a container of
   the image's architecture: run anyway, but the ratio will be labelled non-comparable.
4. A result file contains anything you did not expect: do not edit it; report.

## 0. Inputs (set once)
```bash
export ORACLE_IMAGE=ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8
export OPENBLAS_NUM_THREADS=1
export ILEC="/path/to/ILEC_2012_19 - 20240429.txt"      # tab-delimited
export WORK="$HOME/polaris_trial_scratch"               # LOCAL ONLY; never inside the repo
git -C ~/polaris-re rev-parse HEAD                      # record; the output records it too
cd ~/polaris-re && uv sync --all-extras
```
Plug in mains power; Low Power Mode off; close other heavy apps.

## 1. Machine and image (fills the fairness record)
```bash
docker image inspect "$ORACLE_IMAGE" --format '{{.Architecture}}'   # amd64 or arm64
uname -m                                                            # host
```
Write `$WORK/machine.json` (all keys optional but please fill): chip, performance_cores,
efficiency_cores, ram_gb, os, docker_cpu_limit, docker_memory_gb, power_source ("AC"/"battery"),
low_power_mode ("on"/"off"). Strings must match `[A-Za-z0-9 ._-+()]`.
**Ratio fairness (PLAN R2):** the Polaris/`mgcv::gam` wall-time ratio is reported only for a
like-for-like pair — same environment kind AND same architecture. The pinned image is Linux
(`linux/amd64` today); on Apple Silicon it runs under emulation, which slows `mgcv` and flatters
the ratio. The script marks `ratio_comparable=false` unless `--polaris-env/--mgcv-env` and
`--polaris-arch/--mgcv-arch` agree. To get a comparable pair, run Polaris in a Linux container
of the same architecture and pass `--polaris-env container --polaris-arch linux/amd64`
(or whatever step 1 printed, prefixed `linux/`). If you do not, pass the truth and accept
`ratio_comparable=false`.

Duration is the numeric integer policy year 1..26 (26 = 26 and above), unbanded.

## 2. The 2018-2019 composition check (terminal only)
```bash
uv run python scripts/gam_real_data_trial.py check-window --ilec "$ILEC"
```
Do not paste or commit the table. See stop condition 2.

## 3. Run (restartable: finished cells are skipped; delete `$WORK/results/<cell>.json` to redo one)
```bash
uv run python scripts/gam_real_data_trial.py all --ilec "$ILEC" --work "$WORK" \
  --out "$WORK/gam_real_data_trial_result.json" \
  --digest "${ORACLE_IMAGE##*@}" --threads 1 --host-arch "$(uname -m)" \
  --machine-json "$WORK/machine.json" --repeats 3 --budget-s 300 \
  --polaris-env native --mgcv-env container --polaris-arch native --mgcv-arch linux/amd64 \
  --r-command 'docker run --rm -e OPENBLAS_NUM_THREADS=1 -v {work}:/work -v {repo}:/repo:ro '"$ORACLE_IMAGE"' Rscript' \
  --r-work /work --r-script /repo/scripts/gam_real_data_trial.R \
  --r-version "$(docker run --rm "$ORACLE_IMAGE" Rscript -e 'cat(R.version.string)')" \
  --mgcv-version "$(docker run --rm "$ORACLE_IMAGE" Rscript -e 'cat(as.character(packageVersion("mgcv")))')"
```
(Add `--years 2012-2017` if step 2 says so. Replace the `--*-arch`/`--*-env` values with the truth
from step 1. `--r-version` must match `R version X.Y.Z (YYYY-MM-DD)`, which is what `R.version.string` prints.)
**Expected runtime:** unknown by design (that is what the trial measures). The ceiling is 10
minutes for the Polaris fit; `mgcv::gam` may take far longer; a cell's `--budget-s` stops
repeating after that many seconds (so a slow fit is timed once; `repeats_used` records it).
Run one cell first to see: `... run-cell --formula T1 --granularity coarse ...` with the same
flags as above (`run-cell` takes `--work --formula --granularity` and the run options only).

## 4. Check, then hand over
```bash
python3 -c "import json;d=json.load(open('$WORK/gam_real_data_trial_result.json'));print(len(d['results']),'cells', d['oracle_image_digest'], d['polaris_commit'])"
```
Review the file by eye; it should read as sizes, timings and differences only. Then either commit
it as `docs/measurements/gam_real_data_trial_<date>.json` (DATA_LICENSING.md §5) or paste it to the
next session. Delete `$WORK` afterwards (it holds data-derived cell files and per-row `mgcv` output).

## 5. What the output means
- `status`: `fitted`; `refused` (Polaris `gam()` refuses the formula by name; T3 as written is
  expected to be refused, ADR-258/259 — `mgcv` is then not run); `not_run`; `failed`.
- Gates (all four must hold; none relaxed): `eta` < 2e-2, `|edf_total|` < 1, `Vp` `se` rel < 2e-2,
  `max |d eta| / se.fit_mgcv` <= 0.1 (flag above 0.01). `score_gap_at_mgcv_sp` > 0 means `mgcv`'s
  `sp` scores worse than Polaris's under Polaris's criterion; < 0 means the outer search stopped
  short (mechanism class iii). `n_coef_diff` != 0 means the two designs have different widths
  (mechanism class i; see ADR-259).
- Timing: `polaris.best_seconds` vs the 600 s ceiling; `ratio_polaris_over_mgcv` > 1.5 on T1-T3 at
  `full` triggers the `bam` investigation (Slice R3) — only when `ratio_comparable` is true.
- `peak_rss_mb` is this process's peak RSS (includes loading the cell file); the `mgcv` figure is
  R's heap high-water mark, a different quantity: do not compare them.

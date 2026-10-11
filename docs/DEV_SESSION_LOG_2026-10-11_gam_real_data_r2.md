# Session log — 2026-10-11 — real-data readiness Slice R2 (routine half): ILEC trial harness

**Branch:** `claude/dreamy-galileo-5zhyfi` (the environment-designated branch). **PR class:** `harness(mgcv-parity)` — the real-data comparison does not exist yet; the tier-3 rehearsal is INDEPENDENT but synthetic. Box vs repo: the box names no epic; the repo's pointer names `PLAN_gam_real_data_readiness.md`, R1 DONE → R2. No conflict. R2 ends **WAITING ON MAINTAINER RUN** (a legitimate stop condition, PLAN §3).

## Oracle Version
Tier 1 (scratch only): local apt R 4.3.3 / mgcv 1.9.1, `OPENBLAS_NUM_THREADS=1` (needed `apt-get update` first; same versions as the previous session). Tier 3 (every committed number): CI run **38143339633**, commit `0446c3c`, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, mgcv 1.9.4 / R 4.6.1. Tier 2 (docker daemon): not available. Tier L: not yet (the maintainer's run).

## Baseline (full suite, `pytest tests/ -m "not slow"`)
First run (with this session's new module wrongly placed in `analytics/`): 4084 passed, 6 failed, 22 skipped, 145 deselected (717 s). The 6th failure was mine (`test_analytics_never_imports_the_gam_facade`; module moved to `gam/`). The other 5 are the standing table-less failures (4 `tests/test_synthetic_block.py::TestCalibratedPremiums`, `test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface`) — identical to R1's log. Final run after the change: see the PR body (FINAL_COUNTS below).

## Gap Before
No trial harness, runbook or output contract existed; R2 was NOT STARTED. Provenance: no comparison existed. The real-data gap is unmeasured and stays so.

## Hypotheses Tried
1. **R2-H1 (tier 1):** the trial's T1/T2 agree with `mgcv` on ILEC-shaped (lattice, parallelogram-support) cells. **Disagreed** (eta 0.05-0.13, edf up to 3.2, positive score gap). Localised in three passes: ties alone do not do it (rectangular lattice agrees; continuous parallelogram agrees; integer parallelogram does); fixed-`sp` transplant inconclusive (sp scale conventions); mgcv 1.9.1 `gam.side()` cuts the `ti` block 60 → 49 columns (`mgcv:::gam.side` on the unabsorbed smooths).
2. **R2-H2 (tier 3):** the same on the pinned 1.9.4. **Not reproduced**: coef counts equal in 6 of 6; T1 agrees (both seeds); T2 seed 7001 misses with a negative score gap (class iii). The tier-1 `gam.side` finding is a version difference; no slice registered (ROUTINE nevers; ledger rows 1-2).
3. T3 as written is refused by `gam()` (deterministic; pre-decided handling).
Chain cap: class iii appears once here, no structural change owed; the T2 miss is a gauntlet case (PLAN §5 rule 3), not a new slice.

## Gap After
Harness, runbook, whitelist test, tier-3 rehearsal in CI. Rehearsal: 5/6 cells meet all four gates (T2 seed 7001: eta 3.1e-02, edf +1.00, scaled eta 0.45, score gap -0.148). Real-data gap: still unmeasured.

## Provenance
- eta, edf_total, `Vp` se.fit, per-smooth edf, `log10(sp)`, REML, scale: INDEPENDENT (Polaris `gam()` from formula + cells; `mgcv::gam` from the same string + cells; `fit_polaris` and the R companion take no output of the other side; `compare` consumes both and produces neither). Shared inputs (cells, offset, weights, factor level order) are the recipe.
- scaled-eta criterion: INDEPENDENT numerator, `mgcv`'s own `se.fit` as the unit.
- wall times, peak memory, iterations, phase split: MEASUREMENT (each engine against itself); the ratio is a timing reading, comparable only for a like-for-like environment/architecture pair.
- `score_gap_at_mgcv_sp`: MEASUREMENT of Polaris against its own criterion (mgcv's `sp` is only the evaluation point).
Declared in `real_data_trial.CLAIM`; the rehearsal report prints it via `evidence_markdown`.

## Definition of done (PLAN R2)
- Routine half: script, R companion, runbook, whitelist test: **MET** (`tests/test_gam/test_real_data_trial.py`, 25 tests incl. an end-to-end R run; runbook).
- Each formula/granularity meets the gates and the scaled criterion or is characterised: **NOT MET, because** the real-data run has not happened (WAITING ON MAINTAINER RUN); the synthetic rehearsal is 5 of 6.
- Timings/sizes committed as derived scalars: **NOT MET, because** same.
- Ratio against `mgcv::gam`, 10-minute ceiling: **NOT MET, because** same.

## Follow-ups
Q-R2g in the CONTINUATION (T3 refusal, granularity key sets, duration). Nothing opened and merely filed. Next session: if the maintainer's result file is recorded, read it and record R2; else stop (do not start R4).

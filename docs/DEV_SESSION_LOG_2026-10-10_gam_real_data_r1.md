# Session log — 2026-10-10 — real-data readiness Slice R1 (`select=TRUE` + factor-`by`)

**Branch:** `claude/dreamy-galileo-182700` (the environment-designated branch). **PR class:** `feat(mgcv-parity)` (INDEPENDENT comparisons; one construct disagrees). Box vs repo: the box named no epic; the repo's ACTIVE EPIC POINTER names `PLAN_gam_real_data_readiness.md`, CONTINUATION status "no slice started" → Slice R1. No conflict.

## Oracle Version
Tier 1 (scratch): local apt R 4.3.3 / mgcv 1.9.1, `OPENBLAS_NUM_THREADS=1`. Tier 3 (committed numbers): CI run **38081942434**, commit `ac78ec0`, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, mgcv 1.9.4 / R 4.6.1. Tier 2 (docker daemon) not available.

## Baseline (full suite, `pytest tests/ -m "not slow"`, on the committed code before the docs commit)
4084 passed, 5 failed, 22 skipped, 145 deselected (527 s). The 5 failures (4 in `tests/test_synthetic_block.py::TestCalibratedPremiums`, `tests/test_analytics/test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface`) fail identically on `main` @ `0333bea` in this table-less environment (re-run there: 4 failed / 1 failed). Not caused by this change.

## Gap Before
`gam(..., select=True)` with any factor-`by` smooth was refused (PolarisValidationError); 0 of 16 form x family cells measurable. Provenance: no comparison existed.

## Hypotheses Tried
1. R1-a: select makes the shared direction identified — HELD (closed form + every fit unpivoted).
2. R1-b: `mgcv` thread-stable on these cells — HELD (tier 3, 24 of 24 exactly equal).
3. R1-c: accepted forms agree inside ADR-221 — HELD (8/8 cells, 60/60 draws, tier 3).
4. R1-d: free-`sp` search fails on some blocks — TRUE for the bare-smooth-beside-`by` forms only. First measured as a single predict cell miss (`Vp` `se` 4.3e-02, `eta` 1.8e-02, tier 1); 15 draws x 4 forms x 2 families (tier 1 then tier 3) localised it to those two forms (8/60). Mechanism class iii; handled per R1-d (limitation + refusal by name). No start strategy, no tolerance change, no solver work.
Passes that moved the finding: single cell → draws → form split (three; chain cap not engaged).

## Gap After
Accepted forms: 0 misses in 68 fits (8 cells + 60 draws). Refused forms: 8 of 60 draws disagree (recorded). Tier 3, run above.

## Provenance
- eta, edf_total, per-smooth/per-term edf, `Vp`/`Vc` `se`, term structure, level order: INDEPENDENT (Polaris from formula string/ModelSpec + data; `mgcv` via `gam(as.formula(..), select=TRUE)` / `predict.gam` / `summary.gam`).
- `log10(sp)`: INDEPENDENT, reported, never gated.
- Score gap (Polaris criterion at `mgcv`'s sp minus at Polaris's sp): MEASUREMENT of Polaris against its own criterion (mgcv's sp only an evaluation point).
- Stability probe (threads 1 vs 4): MEASUREMENT of `mgcv` against itself; no Polaris side.
Declared in `FORMULA_CLAIM`, `PREDICT_CLAIM`, `SUMMARY_CLAIM` (unchanged) and the new `CLAIM` in `scripts/gam_select_bare_by_draws_compare.py`.

## Definition of done (PLAN R1)
- Refusal lifted for the two forms with four families: **MET** (formula/summary 8/8, draws 60/60, tier 3).
- Forms with the bare smooth: **NOT MET, because** 8 of 60 draws disagree; handled by R1-d (refused by name, limitation in guide §6/§7, ADR-258).
- Stability probe extended first: **MET** (24/24 equal, tier 3).
- Per-term edf and `Vc` gated only where R1-a and R1-b hold: **MET** (summary per-term edf gated; predict `Vc` gated, 2 cells).
- One Newton start, converge: **MET** on accepted forms (0 not converged).
- Goldens byte-identical: no `src/` pricing path touched; `tests/qa/` not changed (CI runs it). perf row: appended (ADR-177; the row's commit hash is a pre-squash local commit, see PR body).

## Follow-ups
Q-R1 in the CONTINUATION (the narrower reading of the refusal). Nothing opened and merely filed. Next: R2, once R1 is merged.

## Review follow-up (automated review of `356779b`)
- P0: cleared by the maintainer's Q-R1 answer (narrower refusal accepted).
- P1 fixed: the check is now an allowlist (a factor-`by` smooth must be the only smooth of its covariate under `select=TRUE`); two-`by` and numeric-`by`-beside-factor-`by` shapes are refused as unmeasured; tests added.
- P2 fixed: this log's perf line. Not changed: the perf row's hash (history is append-only; content valid); the draws probe's count is not a CI gate (the step is `continue-on-error`, so a gate would not turn CI red; the numbers are in the generated report); score-gap penalty order is implicitly checked by the 0.000 gap on every accepted row.

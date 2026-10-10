# Dev session log — 2026-10-10 — mgcv parity: Slice 10 (reproduce `mgcv`'s pivot) — a finding, not a rule

**Branch:** `claude/dreamy-galileo-2j6swv` (environment-designated; draft PR #264). **PR title class:** `harness(mgcv-parity)` — no Polaris-vs-`mgcv` comparison landed; the evidence is `mgcv` against itself. **Box vs repo:** the box names no epic; the repo's pointer (PLAN Slice 10) was followed; no conflict on fact. The first pass of this session stopped at step 1 because the compiled source was unreachable; the maintainer then allowed reading `cran/mgcv` and the slice continued (the earlier "blocked" ledger rows are marked superseded).
**Perf:** original slice: no row (docs/scripts only). After the Q13 follow-up `src/polaris_re/` changed (exceptions, gam_model, summary_conformance, gam/api), so one row was appended (ADR-177).

## Baseline
Code unchanged since the Slice 9 close. Full suite (`-m "not slow"`, R installed, no `-x`, this branch, code identical to `main`): **5 failed, 4070 passed, 22 skipped, 145 deselected** (726 s). The 5 failures are the standing environmental set (`test_loaded_ilec_feeds_tensor_mi_surface` + four `TestCalibratedPremiums`: no mortality tables here), the same as the Slice 9 log. Passed is +1 against that log's 4069, the test added by its review follow-up (`test_a_vc_refusal_is_waived_only_for_a_pivoted_fit`); this session added no test.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt, as expected) for the mechanism. Tier 3 (every committed number): CI run **38014547575** (commit `5d6a7ee`; earlier run 38014302311 for the eliminated-coordinate columns), oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, R 4.6.1 / mgcv 1.9.4. Source read: `cran/mgcv` 1.9-4.

## Gap Before / Gap After
Before (tier 3, run 37977750939): `Vc` refused for pivoted fits; per-term edf of `gaussian_factor_by_with_bare_smooth` off by 1.002. After: unchanged, and now explained — the reference itself moves by that amount (below). No Polaris number moved.

## Hypotheses Tried (ledger 2026-10-10)
1. `gam.side` / `fixDependence` is the mechanism: REFUTED (R code: by-level names are distinct, early return; no `del.index`).
2. Pivoting is in compiled `gdiPK`; reproducing its recipe in R gives the observed zero coordinate: HELD (tier 1, 27 of 30; misses are ties).
3. The smallest unpenalised-column norm picks the level: REFUTED (tier 1, 1 of 9 cells).
4. The candidates are distinguishable (a rule exists): REFUTED — 5-way exact tie, spread <= 2.4e-15 (tier 3).
5. The choice is stable across `OPENBLAS_NUM_THREADS` 1 vs 4 on the pinned image: REFUTED — differs in 15 of 24 draws (tier 3).
6. The pivot changes what `mgcv` reports: CONFIRMED — per-term edf by exactly 1.000, `Vc` `se` up to 3.9e-02; `edf_total`, `Vp` `se` identical (tier 3).
Per step 6, three passes moved the finding from "gap" to "mechanism" to "no rule". No tolerance widened, no constant tuned, no test changed, no start strategy or solver work (chain cap not engaged).

## Provenance
One comparison, no Polaris producer. Left: `mgcv` under `OPENBLAS_NUM_THREADS=1`; right: the same `mgcv` under `=4` (same script, data, image). Columns — eliminated T-basis coordinate, per-term edf, `Vc` `se`: MEASUREMENT (mgcv against itself); `edf_total`, `Vp` `se`: MEASUREMENT, found equal. NOT parity evidence, NOT echo/transport. The recipe reproduction (`predicted_equals_observed`) compares `mgcv`'s output with R code re-running `mgcv`'s own recipe: a mechanism check, not parity. The probe is a diagnostic step (`continue-on-error`) in `mgcv-conformance.yml`; it asserts nothing.

## Definition of done (PLAN Slice 10)
- Step 1 mechanism with function and lines: **MET** — `gdiPK`, `src/gdi.c` ~L1690-1950 (+ `totalPenaltySpace`, `gam.reparam`, `mgcv_qr`/`R_cond`), ADR-256.
- Step 2 oracle stability on the pinned image: **MET as a measurement; the answer is NOT stable** (15 of 24 differ). Per the PLAN: "if not stable, stop and report" — done.
- Step 3 implement the rule: **NOT MET, because** there is no rule (exact ties decided by rounding).
- Step 4 lift the `Vc` refusal / restore per-term edf as a gated column: **NOT MET, because** the reference does not reproduce itself on these quantities.
- Acceptance (per-term edf within ADR-253, `Vc` `se` within 2e-2, plus a new structure): **NOT MET and not meetable against this oracle**; `eta` / `edf_total` / `Vp` `se` stay where Slice 9 left them.
- Goldens byte-identical: MET — the original slice changed no `src/` or `tests/`; the Q13 follow-up changed `src/` and added tests but no golden (`tests/qa/` passes in CI).

## Follow-ups
Q13 in the CONTINUATION (recommended: stop gating per-term edf of pivoted fits; keep `Vc` refused). Nothing opened and merely filed. Not run: re-pointing the generated report text (`GAM_PARITY_REPORT.md` is generated; a change needs the Q13 answer and a re-dispatch).

## Follow-up (Q13 answered yes)
Per-term edf of pivoted fits is no longer gated and `PolarisRankDeficiencyWarning` is emitted at fit time (ADR-256 amendment 1). Tier 3 (run 38017135360): summary 17 of 17, per-term edf of the two rank-deficient cells printed "not gated". Perf row appended (src changed). Lint failure on the first push was the measurement-stamp check (five documents drifted by the closure change); re-stamped as ASSERTED with a note, because the change is additive and off the measured path (main had 5 ok). Suite baseline above was taken before this follow-up; the follow-up added two tests and changed no other test.

## Review follow-up (automated review of `8252af8`)
- P1 fixed: my edit had inserted the two probe JSON names into the ADR-190 step (a stray command that failed with exit 127 under `continue-on-error`, silently dropping the ADR-190 table); they now sit in the `upload-artifact` path list where they belong. Lesson: a text replace on a repeated token (`ks_formula_probe.json`) hit the first occurrence; the workflow's own step output should have been checked, not just the job conclusion.
- P1 fixed: PR body, ADR header and this log's header/DoD lines refreshed.
- P2 fixed: `warn_stacklevel` so `gam()` attributes the warning to its caller (test added). P2 tracked: regenerate `GAM_PARITY_REPORT.md` after merge.
- Baseline: the reviewer's serial local run was 4204 passed / 0 failed (mortality tables converted there); my earlier 5 failures were the table-less environment. Not a regression.

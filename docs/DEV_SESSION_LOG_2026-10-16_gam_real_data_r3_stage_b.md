# Session log — 2026-10-16 — real-data readiness Slice R3, Stage B (`bgam.fitd` port) — WIP

**Branch:** `claude/dreamy-galileo-l09zt5` (the environment-designated branch). **PR class:** `feat(mgcv-parity)` (lands an INDEPENDENT comparison) but **R3 is NOT done**: draft/WIP.
**Box vs repo:** consistent (pointer: PLAN real-data readiness, R3, Stage B as one scope).

## Oracle Version
Tier 1 (scratch): local apt R 4.3.3 / mgcv 1.9.1, `OPENBLAS_NUM_THREADS=1`; Docker has no daemon (tier 2 unavailable). Tier 3 (every committed number): CI run `38911780487`, digest `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, mgcv 1.9.4 / R 4.6.1. Tier-3 and tier-1 Stage-B numbers agree to the printed digits.

## Baseline (full suite, `pytest tests/ -m "not slow"`, no `-x`)
6 failed, 4154 passed, 22 skipped, 145 deselected (896 s). 5 failures are the known environmental ones (4 `TestCalibratedPremiums` and `test_loaded_ilec_feeds_tensor_mi_surface`: mortality CSVs not converted in this sandbox, identical to the previous log). The 6th, `test_analytics_never_imports_the_gam_facade`, was MINE (a docstring in `analytics/gam_model.py` named the `gam` package); fixed in the next commit and re-run green (8 passed). `tests/qa/`: 85 passed, 9 skipped, goldens untouched (nothing re-pointed; `fit_polaris_gam` unchanged). New file `test_bam_fitd.py`: 19 passed incl. the R-gated one.

## Gap Before
No Polaris `bam` fit existed. Provenance: no comparison. Reference-internal: exact-REML `gam` is 1.9e-2..2.1e-2 from `bam(discrete=TRUE)` on real cells (ADR-260), above the gate.

## Hypotheses Tried
1. **The algorithm alone closes the gap** (tier 1 NumPy prototype on `gam`'s design, 31,720-row cell): 2.8e-3 from `bam`, no better than `gam` (2.4e-3). **Refuted.**
2. **The same iteration fed `bam`'s own X,S** (X rebuilt via `Xbd`): iterations 13/13, eta 1.6e-6. **Confirmed**; so the residual is the design.
3. **Mechanism of the design difference** (tier 1, observed not replicated): `discrete.mf` pads to `max(nr)` rows (1000 when an offset column is continuous); constraint and `S.scale` from padded rows; `ti` margins reordered. Not tested by replication (needs R's `sample()` stream); put to the maintainer, recommended no.
4. Production port, tier 3: end-to-end gates met 4/4; discriminating cell 3.17e-3 vs `gam` 1.25e-2.
Chain cap: class (ii) criterion/algorithm, first slice of this port; no solver tuning, no start strategy (initial `sp` is `bam`'s own `initial.sp`).

## Gap After
End to end, tier 3, INDEPENDENT: all gates met on 4 synthetic cells; discriminating cell 3.17e-3 eta / 4.5e-2 edf / 6.4e-3 se vs the 2e-2 / 1 / 2e-2 gates. Real-data gap: unmeasured (maintainer run). Residual attributed to the design (decomposition: 3.17e-3 -> 6.5e-12 when handed `bam`'s design).

## Provenance
- **eta, edf_total, Vp se, iteration count, log(sp):** INDEPENDENT. Left `gam(method="fREML", discrete=True)` (signature: formula, DataFrame, family; no mgcv payload) -> `bam_fitd`; right `bam(fREML, discrete=TRUE)` on the same formula and data. Declared in `END_TO_END_CLAIM`.
- **gam vs bam eta:** REFERENCE_INTERNAL (mgcv vs mgcv).
- **Design-conditioned table (design, log(sp)/eta per iteration, edf, iterations):** ECHO. `bam_fitd` is handed `mgcv`'s X and S, so it FAILS the ADR-193 mechanical test; declared ECHO, headline "harness check, NOT parity", `require_parity_evidence` refuses it (tested). Value: isolates algorithm from design.
- Headlines come from `evidence_markdown`; the tables were quoted from the CI summary.

## Definition of done (CONTINUATION "R3 pick-up", Stage B)
- Stage B Polaris fit vs `bam(discrete=TRUE)` at the unchanged gates, synthetic cells in CI: **MET** (tier 3, run 38911780487; four cells).
- Checkpoint (i) accumulation vs `XWXd`/`XWyd`: **NOT MET as its own comparison, because** only covered indirectly through the iteration agreeing on `bam`'s design.
- Checkpoints (ii)/(iii): **MET as ECHO diagnostic** (not parity) plus the end-to-end INDEPENDENT trace-free comparison.
- Performance checkpoint / maintainer real-data `bam` at `full` within 10 minutes: **NOT MET, because** not run; accumulation does not compress duplicate rows.
- `fit_polaris`/`gam` accepts `discrete=TRUE, method="fREML"`, refusing the rest by name: **MET** (tests).
- R3 recorded DONE: **NOT MET**.

## Follow-ups
Registered, not filed: the padded-frame question is in ADR-260 amendment 4 and the CONTINUATION as a maintainer question with a release condition. Loose ends 3-5, 7 from the R2 list remain untouched. A binomial tier-3 cell and `reml_score` are next-session items inside R3.

## Perf
No `perf/history.jsonl` row appended: ADR-177 amendment 2 covers only `*_conformance.py` modules, and this PR touches `gam_model.py`/`gam_initial_sp.py`/`api.py`. However `fit_polaris_gam` is unchanged and no pricing path calls it; I judged the perf probe's import closure not to include `polaris_re.gam`, but did not verify mechanically. The reviewer should append the row if the check says so (ambiguous = append, per the routine).

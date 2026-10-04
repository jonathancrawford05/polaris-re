# Dev session log — 2026-10-04 — outer-solver slice 4a (the gauntlet, cases 1-3)

**Branch:** `claude/intelligent-hamilton-djosw5`. **PR title class:** `feat(mgcv-parity)` — every compared quantity is INDEPENDENT. **Perf:** no row (ADR-177 amendment 2: all touched `src/` files are `*_conformance.py`; `sys.modules` check on `perf_harness` returned `[]`).
**Registered-prompt vs ROUTINE file:** the box says the epic is at ADR-207 and to take the parity PLAN's next slice; the ROUTINE file's ACTIVE EPIC POINTER (ADR-241) names `PLAN_wood_outer_solver.md`, epic at ADR-244. ROUTINE file wins; the box is stale (maintainer edit).

## Baseline
`make test` with R installed: 3885 passed, 22 skipped, 5 failed — the same 5 standing failures as slice 3 (generated mortality tables absent). Slice 3's baseline unchanged.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt after `apt-get update`), `OPENBLAS_NUM_THREADS=1`, same as last session. Tier 2 unavailable. Tier 3: run 37204039328 on `51a88ce` (re-run on head `9db72ff`, run 37205724577: identical at every printed digit; `src/` unchanged between them), R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`.

## Gap Before
Gauntlet cases 1-3 had never been run as one table: Newton agreed on three cells (ADR-242) and `select=TRUE` had a tier-1-only pre-reading; L3/L4/L6 and fixed scale had no `outer=` pass-through, so were unmeasured under Newton.

## Hypotheses Tried
1. One Newton start meets ADR-221 on all nine rows. **HELD**, first measurement, tier 1 and tier 3 identical. No failures to record; no tolerance touched; no start strategy added.
(Bug found by my own test: the error-row placeholder `VerificationClaim` with no quantities is invalid — `evidence` is now optional on error rows.)

## Gap After
Nine of nine rows agree (eta 5.0e-08..5.7e-05, edf_total within 0.004, 5-20 fits), tier 3. Not closed: cases 4-5, blocking fixed-scale CI step, default flip (slice 4b).

## Provenance
Every column (eta, edf_total; log10(sp) and per-term edf declared, not gated) is INDEPENDENT: each case re-runs an existing fit/compare pair whose fit signature takes the recipe only (never mgcv's eta/coef/sp/edf). Left: `fit_polaris_gam(outer="newton")`, one `initial.spg` start. Right: `gam(method="REML")` (or fixed `scale`). Headline from `evidence_markdown` of each comparison's claim; gate `require_parity_evidence` runs in the script. No ECHO or TRANSPORT column.

## DoD (PLAN Slice 4, verbatim, with evidence)
- [x] gauntlet case 1, six free-scale cells, one start — MET: ADR-245, run 37204039328.
- [~] case 2, quasipoisson fixed scale=6 — comparison MET (ADR-245); **"CI step made blocking" NOT MET**: deferred to 4b (reviewable CI edit, not done blind).
- [x] case 3, `select=TRUE` N=7 reaches the 523.645 basin from one start — eta 5.671e-05, edf +0.0038, tier 3 (single fixture; "by construction" not claimed beyond it).
- [ ] case 4, 4-term HGAM — NOT MET, not run.
- [ ] case 5, both reproducibility axes — NOT MET, not run (thread axis: ADR-244 on `select=TRUE` only; seed has no operand).
- [ ] `epsilon_rel` / curvature-to-noise put to the maintainer — NOT MET.
- [ ] default flip; `[machine]` gauntlet table by one script via `evidence_markdown()` — script exists for cases 1-3; NOT MET overall.
- [x] goldens byte-identical — `pytest tests/qa/`: 85 passed, 9 skipped; no golden file changed (`git status` clean under `tests/qa/golden_outputs/`).
- [x] `[judgement]` reliability claim naming axes/cases/tolerance — ADR-245 "Not claimed" names them; no unqualified "reliable".

## Open / follow-ups
Slice 4b registered in the PLAN (NEXT). Read `log10(sp)` on `select=TRUE` before reliability wording. Level 4 DISAGREES (standing).

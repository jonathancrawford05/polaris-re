# Findings: where Polaris's Newton search departs from `mgcv` on `select=TRUE` + factor-`by`

**Purpose.** A handoff for whoever next works on the outer solver (`PLAN_wood_outer_solver.md` Slice 3b, or a maintainer decision to lift PLAN `PLAN_gam_real_data_readiness.md` §5 rule 4). It records what was measured, what was refuted, and how to re-measure, so none of it is repeated. Source: real-data readiness Slice R1, ADR-258, PR #266.

**Status of every number.** Tier 3 unless labelled: CI run **38102487555** (commit `5837d69`), oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, mgcv 1.9.4 / R 4.6.1. Tier-1 items (local R 4.3.3 / mgcv 1.9.1) are marked HYPOTHESIS.

## 1. The problem in one paragraph
Under `select=TRUE`, every smooth gets a null-space penalty. When two smooths of one covariate overlap in a direction (a bare `s(x)` beside `s(x, by=f)`, or `s(x, by=f)` beside `s(x, by=g)`), the data separate the four-or-more penalties sharing that direction only weakly. Polaris's Newton search and `mgcv`'s then end at different points of the same REML criterion in a minority of draws. The criterion itself matches `mgcv` (ADR-210, ADR-252): evaluated at the same `sp` the scores agree. The disagreement is in where the two searches end.

## 2. The measured surface (30 draws x gaussian/poisson per form; 15-draw sets 1-15 and 16-30 independent)
| form | agree | note |
|---|---:|---|
| `s(x,by=f)`, `f + s(x,by=f)` | 120 / 120 | accepted |
| `f + s(x,by=f) + s(x,by=w)` (numeric `w`) | 60 / 60 | accepted |
| `f + s(x,by=f) + ti(x,z)` | 59 / 60 | refused; the one miss is an equal-score flat ridge |
| bare `s(x)` beside `s(x,by=f)` (with/without `f`) | 103 / 120 | refused; gaussian 55/60, poisson 48/60 |
| `s(x,by=f)+s(x,by=g)` (with/without `f`,`g`) | 109 / 120 | refused; all 11 misses poisson (`two_by` 21/30, `main_two_by` 28/30) |
29 misses in 480 fits overall. Worst `eta` difference 0.285 (poisson `two_by`, draw 18); `mgcv`'s point scores up to 1.51 lower under Polaris's own criterion.

## 3. What was tried and refuted (do not repeat)
1. **A warning at the stop.** Indicators available at the stop (projected gradient / tolerance, function evaluations, number of penalties with log10(lambda) > 4, max log10(lambda)) do not separate the 29 misses from the 451 agreeing fits. Best AUC 0.71; catching 20 of 29 costs 161 of 451 false alarms. Not shipped.
2. **A tighter `conv_tol`.** 1e-7 / 1e-8 / 1e-9 bring 5 / 6 / 6 of 29 misses to `mgcv`'s `eta` and break 0 of 451. Of the 29: 16 score more than 0.01 above `mgcv`'s point at 1e-6 (11 of them still do at 1e-9, i.e. a different stationary point); 13 score the same as `mgcv`'s point (a flat ridge, which no criterion-based change resolves). At most 5 are early stops.
3. **The starting values (tier 1, HYPOTHESIS).** `mgcv` started from Polaris's start still lands on its usual `eta` in 24 of 29 missed draws. Polaris started from `mgcv`'s `initial.sp` reaches `mgcv`'s `eta` in 17 of 29, but perturbing Polaris's own start by N(0, 0.2) / N(0, 0.4) per entry reaches it in 48% / 55% of 87 starts, so `mgcv`'s start is not special. The search outcome is a basin lottery for Polaris, steadier for `mgcv`.
4. **Pre-existing, from earlier epics:** no new start strategy, multistart or best-of-N (ADR-241 rule 10); the exact Hessian and `mgcv`'s step constants are already in `gam_reml_newton.py`.

## 4. What is still open (the lever, if there is one)
Polaris's stop is `mgcv`'s gradient test, but `mgcv:::newton` (read on tier 1, 1.9.1) differs in three ways: it requires the Hessian not to be indefinite (`converged <- !indef`), it requires `|old.score - score| <= score.scale * conv.tol`, and it tolerates a gradient up to `5 * score.scale * conv.tol`; its `score.scale` is `|log(scale.est)| + |score|` (REML) where Polaris uses `1 + |score|`. It also works through `uconv.ind` (only unconverged directions enter the Newton step) and a steepest-descent fallback. None of these has been tested on the 29 misses as a block; item 2 above suggests the early-stop pieces cannot explain more than 5 of 29. The remaining candidates are in the **step logic** (how directions are dropped and the Hessian floored on a near-flat ridge). Reproducing `mgcv`'s step logic faithfully is the first thing to try, and it is solver work.

## 5. How to re-measure after any solver change
1. `Rscript scripts/gam_select_bare_by_draws_probe.R draws.json` (mgcv side; 480 fits; seeds fixed, `g`, `z`, `w` from separate streams so the first 60 draws are unchanged).
2. `uv run python scripts/gam_select_bare_by_draws_compare.py draws.json` (agreement by form).
3. `uv run python scripts/gam_select_stop_diagnostic.py draws.json` (misses, warning indicators, tolerance sweep, score vs `mgcv`'s point).
4. The same steps run in `mgcv-conformance.yml` (non-gating, `continue-on-error`); read the job summary, tier 3.

**Acceptance for lifting a refusal.** A form leaves the refusal list in `gam()` (`_refuse_select_with_bare_and_factor_by`, `src/polaris_re/gam/api.py`) when it has zero misses over the 30-draw tier-3 probe, the same standard as the accepted forms. The `ti` form is the nearest: one equal-score miss; it needs more draws or a tie-breaking rule, not a better optimum. Never lift a refusal by widening the 2e-2 `eta` gate or the `|edf|` < 1 gate.

## 6. Where this is recorded
ADR-258 (decisions and tier-3 tables), `CONFORMANCE_LEDGER.md` (rows dated 2026-10-10/11), `DEV_SESSION_LOG_2026-10-10_gam_real_data_r1.md`, `GAM_USER_GUIDE.md` §6-§7, `MGCV_FEATURE_COVERAGE.md`.

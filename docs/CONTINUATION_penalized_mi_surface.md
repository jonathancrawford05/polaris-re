# Continuation: a penalized tensor MI surface (P-splines, REML-selected λ)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` (2026-08-08c), promoted from the
spline-diagnostics epic.
**Plan:** `docs/PLAN_penalized_mi_surface.md`
**Predecessors:** ADR-182, **ADR-184 + amendments 1-3**
**Status:** **SLICES 1-3 DONE (2026-08-09)** — ADR-185, ADR-186, ADR-187 + amendments
1-2. Slice 4 is NEXT.
**Total slices:** **7** (1-6 autonomous, 7 one maintainer run) — **plan revised
2026-08-09**, see `PLAN_penalized_mi_surface.md` Revision 1.
**Estimated scope:** ~7-9 dev-days autonomous + one `mgcv` conformance run and one
ILEC/HMD re-run, both maintainer-side.

## Overall goal

Make model complexity data-driven instead of a hand choice. `df` currently sets
basis dimension *and* wiggliness with one integer, and two hand adjustments
(`year_df` 4→3, then `df==degree` 3→2) each moved a published ILEC finding with
nothing in the fit selecting them.

**Not the goal: fixing age 45.** ADR-184 amendment 2 showed that climb survives
removing a whole polynomial order. PLAN §1 rules the framing out in writing.

## Slices

1. ~~**Penalized fitter core at fixed λ**~~ **DONE** — `experience_gam_penalized.py`,
   15 tests, ADR-185. Both limits verified. **Two plan premises were falsified**,
   and slice 2 must start from the corrected ones (see below).
2. ~~**REML λ selection**~~ **DONE** — ADR-186. Deterministic grid, so Anchor 3 is
   resolved by construction. Anchor 4's EDF fix landed with it.
   Slice 1 sharpened that risk rather than reducing it: the penalised directions are
   exactly where the numerical noise lives, which is why the coefficient convergence
   criterion failed there.
3. ~~**Bayesian bands**~~ **DONE** — ADR-187. Anchor 2 came out **neither satisfied
   nor violated**; the band layer was extracted from three byte-identical copies
   rather than copied a fourth time. Coverage measured, and **the registered
   hypothesis was falsified** — the committed delta-method bands are calibrated.
4. **Selector robustness + an unconditional interval** — **NEXT** — fix the abort
   (score a non-converging grid point `+inf`), add the Kass-Steffey unconditional
   covariance, add Wood's `gamma` for parity. **Gated on Anchor 7**: the
   select-per-replicate coverage study must pass before anything is labelled a 95%
   band.
5. **`mgcv` conformance suite** — ship our design AND our penalties via `paraPen` so
   the model is identical and disagreement localises to our arithmetic. Five levels:
   fixed-λ coefficients, REML selection, `tr(F)`, unconditional `vcov`, `gamma`.
   Synthetic exchange file committed; HMD/ILEC exchange local-only, report committed.
6. **Harness integration** — `--penalized` off by default (Anchor 6), `edf` and λ
   reported (Anchor 4). Moved behind 4-5 deliberately.
7. **Real data** — against the four predictions PLAN §6 registers in advance.

## Context for the next session

- **Read PLAN Revision 1 first**, then §2 (now **eight** anchors — 7 and 8 are new
  and both gate slice 4) and §6 (the predictions).
- **Read PLAN §2 (the six anchors) and §6 (the predictions) before writing code.**
  §6 exists because the diagnostics epic's pre-registered table came back against
  its own hypothesis and was trustworthy for exactly that reason.
- **Anchor 1 is AMENDED — do not start from the version in PLAN §2.** λ=0
  reproduces `TensorMIModel` exactly only in the **`knots="clamped"`** scheme, which
  is oracle-testing only. The production scheme is `knots="uniform"`, where it
  deliberately does not hold, because **patsy cannot build a P-spline basis at
  all**: it always clamps boundary knots, and a difference penalty over a clamped
  basis does not annihilate linear trends (step spread 5.6e-01 against 8.9e-16 on an
  extended uniform sequence from scipy). Slice 1 found this the hard way — the
  λ→∞ limit kept a 3.0-point span instead of collapsing to constant MI.
- **IRLS converges on deviance, not on coefficients.** At a saturating λ the
  coefficients rattle at round-off in the penalised directions indefinitely while
  the deviance settles within 8 iterations. This matters for slice 2 because the
  optimiser will sit on top of exactly those directions.
- **The EDF reporting changes in slice 2 — do not build on slice 1's fields.**
  Slice 1's `edf_age` / `edf_year` are `tr(H) - tr(H|λⱼ=∞)`, which is well-defined
  (the first implementation was inert, and eleven tests passed over it because all
  asserted on `edf_total`) but **non-additive**: the two overlap and do not sum to
  `edf_total`, while their names invite exactly that addition. Per the amended
  Anchor 4, slice 2 replaces them with **`tr(F)` over the tensor block** as the
  headline per-term EDF — the quantity `mgcv` reports, and one that *closes*
  against the factor block — plus per-penalty **shrinkages**, renamed to say
  *dimensions removed* rather than implying *spent*.
  **The `mgcv`-consistency claim is adopted, not verified** (PLAN §7); nothing in
  this container can check it.
- **`fit_reml()` is the entry point, not `select_lambdas_reml()`.** Added in the
  #188 review round. Selection returns a bare `(λ_age, λ_year, score)` tuple and
  fitting is a separate call, so a caller that wires the two by hand gets a fit with
  `reml_score` and `lambda_grid_step` left `None` — which was the shipped defect.
  `fit_reml()` does both and populates them, and it is the fit slice 3 took `Vb`
  from. Use `select_lambdas_reml()` only when the search is wanted without the
  fit. Grid parameters (`coarse_step`, `refine_step`, `bounds`) are named on
  `fit_reml()` and reach the selector only — `**model_kwargs` goes to the model.
- **Grep the claim set before calling a fix done** (ADR-186 amendment 2). Slice 2's
  inert-fields defect was asserted in **five** places; the fix updated three, and
  round 2 found the other two still naming the wrong entry point. One `grep` for the
  claim costs seconds; two review rounds did not. **Slice 3 applied it** — and it
  caught a real one: the "consumed unchanged by the extractor" phrasing was already
  false for the *design* half before it could propagate (ADR-187 decision 1).
  Slice 4 inherits the same exposure: `--penalized`, the `edf` fields and the λ
  report will each be described in the CLI help, the report schema, the notebook and
  the ADR.
- **A test that compares against the constant the code hardcoded cannot fail.**
  `lambda_grid_step` was reported as `REFINE_STEP` regardless of the step swept, and
  the test asserted `== REFINE_STEP`. Both halves passed, together, wrongly. Slice 3
  avoided the analogue by comparing coverage against the *nominal* 0.95 rather than
  against whatever the band construction used. Slice 4's version of the trap: a
  report field asserted against the same constant that populated it.
- **The oracle already exists.** `TensorMIModel` at λ=0 is the correctness spec and
  it is already tested. Do not build a new one.
- **statsmodels cannot supply the tensor.** `GLMGam` + `BSplines` penalize but the
  smooths are additive-only (verified on 0.14.6). The Kronecker design and penalty
  are hand-built; the family and link can still come from statsmodels.
- **`k` is an upper bound, not a knob** (Anchor 5). ILEC's eight calendar years
  cannot support `k=10`; HMD's thirty years support 10-15.
- **A slice-7 run that contradicts the thesis is a successful run** (renumbered from
  slice 5 in Revision 1). The same applies to slice 5's conformance: an `mgcv` run
  that **refutes** `tr(F)` changes Anchor 4 and is a successful slice. Slice 3 is the
  standing proof: its registered hypothesis came back false and that was the result,
  not a setback.
- **BLOCKER for slice 4: `select_lambdas_reml` aborts on a non-converging grid
  corner.** ADR-187 finding 5. `log10 λ = (-1, 8)` fails IRLS on roughly one
  replicate in a hundred and takes the whole selection down with it, because a
  non-converging grid point raises rather than scoring as unusable. Slice 4 runs this
  selector on the 125k-cell book, where that is a failed production run. The fix is a
  design choice — score the point `+inf` and continue, damp the IRLS step, or raise
  the cap — and it belongs at the top of slice 4, not bolted into a review round.
- **REML λ selection is unstable across replicates — but the 5-decade figure is a
  fixture artifact (ADR-187 amendment 1).** On a truth that varies with age, λ_age's
  spread falls from **5.50 decades to 0.75**, and the RMSE spread from 2.1x to 1.13x.
  The age-flat fixture had nothing for the age penalty to identify. The instability is
  real at **~1 decade in age, ~2 in year**; the estimator is not as unstable as
  finding 2 first read. **A single global λ is rejected** — the evidence for it
  evaporated with the artifact, and `te()` in mgcv is *defined* by one λ per marginal,
  so a global λ moves away from the parity goal. Practical consequences for slice 4 — a reported λ is one draw, not
  a property of the book; a band shown beside a selected λ is **not** jointly
  calibrated with it, because `Vb` carries no smoothing-parameter uncertainty; and
  any single coverage figure quoted in a report is provisional.
- **Quote the direction of the coverage trade, not a point figure.** The penalized
  band is narrower (4.4x on a representable curve) and under-covers (87.1% against a
  nominal 95%) — but that 87.1% moved 5.5 points on a selection-seed change, so the
  decimals are not a stable quantity to publish. The 97.3%/8.3x null-space row is the
  flattering regime and must not be the one quoted (same refusal ADR-186 made of its
  40x). An earlier revision of this file said "2.4 points"; that number is withdrawn.
- **The weak end is OLD ages, not young.** Under misspecification both estimators
  fall to 76%/67% at age 80+, while young ages hold up. Slice 5's ILEC read should not
  import the age-45 framing into band interpretation. **Which of the two degrades
  worse is not resolved** — an earlier claim that the penalized fit degrades further
  was withdrawn when the selection seed changed it from 76.0% to 85.1%.
- **The unconditional coverage study is NOT delivered.** Select-per-replicate coverage
  — what a user of the shipped procedure actually gets — is the natural companion to
  ADR-187's conditional numbers and was blocked by the abort above. It is the obvious
  first thing to run once that is fixed.

## Open questions (for human)

- Single global λ per margin, or does slice 5 promote the adaptive-penalty epic?
- Does the `mgcv` cross-check (ADR-151) happen? It needs R and an R-equipped
  machine, and real-data penalized fitting is when it is worth most.
- Should the penalized path ever become the default? Not decidable before slice 5;
  flipping it means re-deriving every committed report, which carries its own
  `DATA_LICENSING.md` §5c implications.

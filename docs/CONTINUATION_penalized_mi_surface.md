# Continuation: a penalized tensor MI surface (P-splines, REML-selected λ)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` (2026-08-08c), promoted from the
spline-diagnostics epic.
**Plan:** `docs/PLAN_penalized_mi_surface.md`
**Predecessors:** ADR-182, **ADR-184 + amendments 1-3**
**Status:** **SLICES 1-4 DONE (2026-08-09)** — ADR-185, ADR-186, ADR-187 + amendments
1-2, **ADR-188**. Slice 5 (the `mgcv` conformance suite) is NEXT, and slice 4 made it
load-bearing rather than optional.
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
4. ~~**Selector robustness + an unconditional interval**~~ **DONE** — ADR-188, **PR #190**. All
   three pieces shipped. **The Anchor-7 gate was measured and does NOT pass**:
   unconditional coverage 0.8516 / 0.8581 against a floor of 0.9192, so **nothing in
   this project may be labelled a 95% band**. Kass-Steffey buys +3.2/+3.8 points of a
   ~13-point shortfall — right direction, quarter of the gap. Two further numbers a
   later slice must not repeat wrongly: selecting λ per replicate costs a *further* ~5
   points against ADR-187's conditional 0.8710, and the **unpenalized** delta band
   covers 10 points better (0.9586) at 4.4x the width on the identical truth and seeds.
5. **`mgcv` conformance suite** — **NEXT** — ship our design AND our penalties via `paraPen` so
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
  #188 review round. Selection returns a `LambdaSelection` and fitting is a separate
  call (it was a bare `(λ_age, λ_year, score)` tuple until slice 4 widened it — the
  point is unchanged), so a caller that wires the two by hand gets a fit with
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
- ~~**The unconditional coverage study is NOT delivered.**~~ **DELIVERED** (slice 4,
  `docs/MEASUREMENT_unconditional_coverage.md`) — and it failed the gate. See the
  slice-4 entry above for the three numbers, and ADR-188 for the reasoning.

### New in slice 4 — read before slice 5

- **Nothing may be called a 95% band.** Anchor 7's gate is measured and failed. Slice 6
  in particular must quote the measured rate and the direction, never the nominal
  level, and must print which covariance produced the interval
  (`PenalizedMIFit.band_is_unconditional` exists for exactly that).
- **Slice 5's level 4 is now the decisive check, not a completeness item.** The gate
  fails for one of two reasons with different remedies: our Kass-Steffey arithmetic is
  wrong, or the residual shortfall is shrinkage bias that no covariance can reach.
  `vcov(m)` vs `vcov(m, unconditional = TRUE)` separates them. If R time is short, run
  levels 1 and 4 first.
- **Do not tune to pass the gate.** `gamma`, a larger `k`, or moved bounds would each
  be choosing a number to make a measurement come out. The plan's own sequencing is the
  answer.
- **`select_lambdas_reml` returns `LambdaSelection`, not a 3-tuple.** Five call sites
  moved. `fit_reml` is still the entry point and now forwards `n_rejected_points` and
  `n_evaluated_points` onto the fit.
- **`gamma` is exactly inert at 1.0**, by construction — both `gamma`-dependent terms
  collapse to the pre-`gamma` expression. That is what lets slice 2's selection tests
  stand unchanged as a regression guard, and it is worth preserving.
- **`smoothing_uncertainty` refuses to degrade where the selector rejects.** A central
  difference needs both of its points; a Hessian built from whichever corners converged
  is a different quantity under the same name.
- **The fixture trap bit a third time.** Slice 4's first age-varying truth had a
  *linear* age gradient, which lies inside the age penalty's null space, so it
  reproduced the age-flat degeneracy under a different name (λ_age spread 5.50 decades
  vs 1.25 for the corrected quadratic). ADR-186 hit this with an unrepresentable truth,
  ADR-187 designed around it, slice 4 still built one wrong. It is now a **test** on the
  second difference rather than a habit. Check any new fixture against **both** the
  penalty null space and the basis.
- **ADR-187 amendment 1 is confirmed at 200 replicates**, not merely restated: λ_age's
  spread still falls four-fold once the truth has age structure, and a max-minus-min
  range over 200 draws is a much harder statistic than over 8.

## Open questions (for human)

- Single global λ per margin, or does slice 5 promote the adaptive-penalty epic?
- Does the `mgcv` cross-check (ADR-151) happen? It needs R and an R-equipped
  machine, and real-data penalized fitting is when it is worth most.
- Should the penalized path ever become the default? Not decidable before slice 5;
  flipping it means re-deriving every committed report, which carries its own
  `DATA_LICENSING.md` §5c implications.

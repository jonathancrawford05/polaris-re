# Continuation: a penalized tensor MI surface (P-splines, REML-selected λ)

**Source:** `PRODUCT_DIRECTION_2026-07-24.md` (2026-08-08c), promoted from the
spline-diagnostics epic.
**Plan:** `docs/PLAN_penalized_mi_surface.md`
**Predecessors:** ADR-182, **ADR-184 + amendments 1-3**
**Status:** **SLICES 1-5 DONE (2026-08-10)** — ADR-185, ADR-186, ADR-187 + amendments
1-2, ADR-188, **ADR-189**. Slice 5's suite is **BUILT AND COMMITTED; the R run has NOT
happened** — it is the maintainer's, one command, `docs/RUNBOOK_mgcv_conformance.md`.
Until it does, `tr(F)`, the Kass-Steffey covariance and `gamma` all remain *adopted, not
verified* (Anchor 8). Slice 6 (harness integration) is NEXT and is unblocked, with one
caveat recorded below.
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
5. ~~**`mgcv` conformance suite**~~ **BUILT (2026-08-10)** — ADR-189. Our design AND our
   penalties go to `mgcv` via `paraPen`, so the model is identical and disagreement
   localises to our arithmetic. Ten cells over three designs, five levels. Synthetic
   exchange **and** reference committed (the golden decision); HMD/ILEC exchange
   local-only, report committed. 45 tests, none needing R.
   **The R run has NOT happened.** Three quantities stay *adopted, not verified*.
6. **Harness integration** — **NEXT** — `--penalized` off by default (Anchor 6), `edf` and
   λ reported (Anchor 4). Moved behind 4-5 deliberately. **Unblocked, with a caveat:** it
   was sequenced behind conformance so the numbers reaching a human were verified first,
   and they are not yet. Slice 6 may proceed — but every `edf`/λ/band it surfaces must
   carry the *adopted, not verified* mark until the run happens, which is a reporting
   obligation on top of the Anchor-7 amendment's three.
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

## Maintainer decisions — 2026-08-09 (PR #190)

Two questions slice 4 raised were answered by the maintainer. Both are recorded in
`PLAN_penalized_mi_surface.md` (Anchor 7 amendment; slice 5 workflow) and repeated here
because this file is what the next session reads first.

1. **The band keeps being shown.** The failing gate does **not** pull it. What it
   forbids is the unqualified nominal label. While it is displayed, slice 6 owes three
   things: the **measured** coverage rather than the nominal, a **stated reason for the
   deviation** beside it, and the target kept live. The obligation ends when we either
   reach nominal or record a decision that it is not achievable or not worth pursuing —
   either of which is a result. Note this is a *narrowing*, not a relaxation: the
   pre-gate status quo displayed a band whose coverage nobody had measured.

2. **The R run happens after slice 5 is built**, as a batch. So slice 5's job is to make
   one run serve many iterations — **the mgcv reference for the synthetic case is
   COMMITTED**, turning it from a live oracle into a golden file the implementer can
   iterate against offline. Expected round trips: **two to three**, not one and not ten.
   Four build requirements and one guard are spelled out in PLAN slice 5; the two that
   would otherwise be discovered painfully are: **the exchange file must be TSV + JSON,
   not `.npz`** (R cannot read `.npz` without `reticulate`/`RcppCNPy`), and **the
   comparator must hash the exchange file** so nobody can iterate against a stale
   reference and declare parity with a file R never saw.

   The earlier "run levels 1 and 4 first if R time is short" recommendation is
   **superseded** — batching every level into one invocation removes the question.

### New in slice 4 — read before slice 5

- **Nothing may be called a 95% band.** Anchor 7's gate is measured and failed. Slice 6
  in particular must quote the measured rate and the direction, never the nominal
  level, and must print which covariance produced the interval
  (`PenalizedMIFit.band_is_unconditional` exists for exactly that).
- **Pin the lambda-vs-scale convention at slice 5 level 1.** The `gamma`-as-scale
  derivation is algebraically sound, but `log|XᵀWX + S|` is evaluated at the
  **unscaled** penalty, which fixes a particular convention for λ relative to φ. Inert
  at `gamma=1.0` and used nowhere today, so it has no consequence yet — and it is
  exactly the kind of convention an `mgcv` conformance run should nail down rather than
  leave implicit, since `sp` there multiplies the supplied `S` directly. Raised in the
  PR #190 review.
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

### New in slice 5 — read before slice 6

- **`Rscript scripts/mgcv_conformance.R` is the one thing waiting on a human.** Two
  commands, both in `docs/RUNBOOK_mgcv_conformance.md`. The output is committed as a golden
  and the implementer then iterates offline against it — zero further R runs while fixing
  arithmetic. Expected round trips: two to three.
- **The R-free guarantee is the thing to lean on until the run happens.**
  `penalized_score_infinity_norm` measures 2.19e-10 at worst across all ten committed
  cells, so the exported coefficients are the unique penalized MLE of the exported problem.
  Any level-1 disagreement will therefore be R's solver or a **convention** — never our
  fit. That narrows what the first run can possibly find, which is the point.
- **`scalePenalty` is the first thing to read on a level-1 disagreement.** The comparator
  surfaces `penalty_scaling` per cell and refuses a reference reporting rescaling left on.
  A non-trivial value there is a one-line R fix, not a re-derivation of our arithmetic —
  and it was NOT verifiable in this container, so it carries the same *adopted* mark as the
  three quantities the run is meant to settle.
- **Level 4 is two metrics and the second is weak by construction.** `mgcv` has no `Vc` at
  fixed `sp`, and at free `sp` the two sides select different λ. So the exact half is the
  conditional `Vb` at fixed λ; the correction is only checkable as an *inflation ratio*,
  which cannot separate a wrong Jacobian from a λ disagreement. **Read it only after level
  2 passes.** ADR-188's failing gate still needs level 4 to choose between "our arithmetic"
  and "shrinkage bias", and this is as sharp as level 4 gets.
- **The synthetic fixture's shape is load-bearing, and a test says so.** A 2-year age step
  saturates both penalties at the bound with `edf_total` exactly 4.000 (the bilinear null
  space), which would make level 2 vacuous. The fixture is narrowed in *range* instead.
  This is the fourth time this epic has met the degenerate-fixture trap — check any new
  fixture against **both** the penalty null space and the basis, every time.
- **Two free-`sp` tolerances are PROVISIONAL** — 0.5 decades on `log10 sp`, 1.0 on `edf`.
  Reasoned from the grid resolution and the shallow profile, not measured against R. The
  first run is what firms them, and **the answer is not to widen them to pass** (ADR-188's
  refusal, restated).
- **The committed exchange is a golden with two staleness guards.** One re-hashes it; one
  regenerates it and compares. Re-exporting invalidates any committed `mgcv_reference.json`
  and the comparator's hash guard will say so — which is the intended behaviour, not a
  nuisance.
- **The exporter deliberately does not re-run the diligence ingest.** Real-data cases read a
  grouped-cells file. Duplicating `run_diligence`'s ~60 lines (which reach `_regroup` and
  `_filter_window`) would be a second ingest path to keep in step, untestable here.
  Harvested as a follow-up, not silently skipped.

## Open questions (for human)

- **Will the R run happen, and when?** This is now the epic's only external dependency and
  it gates the Anchor-8 conversion of three quantities plus the diagnosis of ADR-188's
  failing gate. One command, no data needed, `docs/RUNBOOK_mgcv_conformance.md`. Everything
  it needs is committed as of 2026-08-10.
- Single global λ per margin, or does the conformance run promote the adaptive-penalty epic?
- Should slice 6 wait for the run, or ship with the *adopted, not verified* mark? The plan
  sequenced 6 behind 5 so the numbers a human reads would be verified first; slice 5 is
  built but unrun, so that intent is only half met. Proceeding is defensible with the mark
  carried explicitly; waiting is also defensible. **A human decision, not the routine's.**
- Should the penalized path ever become the default? Not decidable before slice 5;
  flipping it means re-deriving every committed report, which carries its own
  `DATA_LICENSING.md` §5c implications.

# Dev Session Log — 2026-08-09 — penalized MI surface, slice 4

## Item Selected

- **Source:** `docs/CONTINUATION_penalized_mi_surface.md` (active epic, routine step 5)
- **Priority:** IMPORTANT (Tier-A epic, `PRODUCT_DIRECTION_2026-07-24.md`)
- **Title:** Selector robustness + an interval that does not condition on λ
- **Slice:** 4 of 7
- **Branch:** `claude/quirky-ramanujan-mgvwcy` (environment-designated; the routine's
  `feat/auto-*` default is overridden per step 8)
- **ADR:** ADR-188

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `a2a58d1`) | **3102 passed, 3 skipped, 125 deselected** — no standing failures |
| End state (`make test`) | **3128 passed, 3 skipped, 126 deselected** (+26 tests, +1 deselected `@slow`) |
| Module tests | 51 (was 34), plus 10 new on the study harness |
| `tests/qa/` goldens | **94 passed, untouched** |
| perf row | `peak_mib` 33 (Δ+0), no structural creep |

The four SOA-conversion failures the routine's baseline note anticipates did **not**
occur — `scripts/convert_soa_tables.py` reached pymort and converted 6/6 tables. The
CIA 2014 tables are reported MISSING by the validator, as they are on every run.

## Selection Rationale

Step 5 found `CONTINUATION_penalized_mi_surface.md` IN PROGRESS with slice 3 merged
(PR #189, `a2a58d1`), so slice 4 was the work — no step-5b epic start and no step-6
fallback pick. Slice 4 had a registered blocker (ADR-187 finding 5) and a written
three-piece scope, so nothing needed re-planning.

## Verify Premise (step 7b)

**The premise held exactly.** Reproduced before writing any code: on the quadratic
fixture at seed 1098, `log10 λ = (-1, 8)` raises `Penalized IRLS did not converge in
100 iterations (deviance 467.015)`, and `fit_reml` dies with it in 0.1 s. Both the
corner and the propagation are as ADR-187 recorded them.

## What Was Done

**Three pieces, in the plan's dependency order.** The abort became a scored rejection:
a non-converging grid point is worth `+inf`, because a λ whose own fit does not
converge is not a λ to select. The count and its denominator come back on
`LambdaSelection` and are forwarded onto the fit — a search that discarded half its
grid is a different object from one that discarded nothing, and slice 6 runs this on a
125k-cell book where nobody is watching the corner. Rejecting *every* point raises,
because the running best is seeded at the grid centre and a fix that only added the
`+inf` branch would have returned that centre as a fabricated selection.

**The Kass–Steffey unconditional covariance** (`Vb + J V_rho Jᵀ`) is computed by
central differences — nine penalized fits against the selector's ~200. The decision
worth recording is the variance cap: the Hessian is evaluated at a *grid* point, not a
stationary point, so it can go near-zero or negative, and rather than a numerical
`rcond` the cap comes from the selector's own contract — `select_lambdas_reml` cannot
return a λ outside its bounds, so `log λ`'s standard deviation cannot exceed half the
bound width. `n_floored` reports how often it bound, and it bound three times more
often on the age-flat truth (0.46 directions per fit) than the age-varying one (0.15),
which is identifiability showing up in the curvature exactly where it should.

**`gamma` enters as the scale parameter**, per mgcv's own documentation for the RE/ML
criteria, and is **exactly inert at 1.0** — both `gamma`-dependent terms collapse to
the pre-`gamma` expression. That is deliberate: it lets slice 2's eleven selection
tests stand unchanged as a regression guard rather than be re-baselined.

**Then the gate, and it does not pass.**

## The gate — measured at 200 replicates, FAILED

`scripts/unconditional_coverage_study.py`, λ selected on **every** replicate, both
bands from the same fits so the comparison is paired.
`docs/MEASUREMENT_unconditional_coverage.md` carries the report.

| truth | conditional | **unconditional** | floor |
|---|---:|---:|---:|
| age-flat | 0.8201 | **0.8516** | 0.9192 |
| age-varying | 0.8200 | **0.8581** | 0.9192 |

Three results:

1. **Kass–Steffey is directionally right and quantitatively insufficient.** +3.2 and
   +3.8 points against a ~13-point shortfall — about a quarter of the gap, at ~12%
   extra width. The plan called it "the piece most likely to move coverage back toward
   nominal"; it moved it a quarter of the way.
2. **Selecting λ per replicate costs a further ~5 points.** ADR-187's conditional
   0.8710 becomes **0.8201** for the *same band* once λ is re-selected. That is
   precisely what Anchor 7 was written to expose, and it means 87.1% was an
   **optimistic** figure conditioned on knowledge the user does not have.
3. **The unpenalized delta band covers 10 points better** — 0.9586 at 4.4x the width,
   identical truth and seeds. A statement about the *interval*, not the point estimate:
   it does not retract ADR-186's RMSE result, and jointly they say the penalized
   surface may be the better estimate inside an interval that is not yet honest
   about it.

**The failing gate does not license tuning.** `gamma`, a larger `k`, or moved bounds
would each be choosing a number to make a measurement come out. Slice 5's `mgcv` level
4 is the check that separates "our arithmetic is wrong" from "the residual is shrinkage
bias no covariance can reach" — which is why slice 5 is now load-bearing rather than a
completeness item.

## The fixture trap bit a third time — caught by measuring, not by review

The first version of the age-varying truth used a **linear** age gradient. A linear
function lies *inside* the second-difference penalty's null space along the age margin,
so λ_age → ∞ costs nothing and the "age-varying" fixture reproduced the age-flat
degeneracy under a different name. The study's two rows were one row measured twice.

The evidence is the λ spread, which is the diagnostic ADR-187 amendment 1 established:

| age-varying fixture | log10 λ_age spread over 200 replicates |
|---|---:|
| linear gradient (**withdrawn**) | 5.50 decades |
| quadratic profile (**shipped**) | **1.25** decades |
| age-flat, for reference | 5.00 decades |

Two things follow. **The correction confirms ADR-187 amendment 1 at 200 replicates
rather than 8**, which is the stronger claim — a max-minus-min range over 200 draws is
a far harder statistic, and λ_age's spread still falls four-fold once the truth has age
structure the penalty can see. And the check is now a **test** rather than a habit:
`test_the_age_varying_truth_leaves_the_age_penalty_null_space` asserts a non-zero
*second* difference, which the broken fixture fails and a "values differ across ages"
assertion would have passed.

ADR-186 hit this with a truth its basis could not resolve; ADR-187 designed its three
truths around exactly this distinction; slice 4 still built one wrong. Three epics, one
shape.

## Files Changed

| file | what |
|---|---|
| `src/polaris_re/analytics/experience_gam_penalized.py` | `LambdaSelection`, `SmoothingUncertainty`, `smoothing_uncertainty()`, `_fit_and_score()`, `gamma` in `reml_score`, rejection branch, four new `PenalizedMIFit` fields, `fit_reml(unconditional=, gamma=, log_step=)` |
| `scripts/unconditional_coverage_study.py` | **new** — the Anchor-7 gate study and its committed report |
| `docs/MEASUREMENT_unconditional_coverage.md` | **new** — the 200-replicate report |
| `tests/test_analytics/test_experience_gam_penalized.py` | 17 new tests; five `select_lambdas_reml` call sites moved to attribute access |
| `tests/test_analytics/test_unconditional_coverage_study.py` | **new** — 10 tests on the study harness |
| `docs/DECISIONS.md` | ADR-188 |
| `docs/PLAN_penalized_mi_surface.md` | slice 4 DONE with the gate verdict; slice 5 NEXT and re-scoped as decisive |
| `docs/CONTINUATION_penalized_mi_surface.md` | status, slice 4 close-out, "New in slice 4" context block |
| `docs/PRODUCT_DIRECTION_2026-07-24.md` | step-4b ledger heal (PR #189) + slice-4 harvest |
| `perf/history.jsonl` | +1 row (ADR-177) |

## Tests Added

**Selector robustness (4):** the seed-1098 rejection, both-sided so a future change
that made every corner converge fails rather than silently retiring the guard; the
count reaching the fit and being `None` for a hand-set λ; the reject-everything path
raising rather than returning the grid centre.

**`gamma` (4):** recorded on the fit; **bit-identical criterion at 1.0**; monotone
`edf` decline across 1.0/1.4/2.0/5.0 with a magnitude floor so a no-op cannot pass;
non-positive refused.

**Unconditional covariance (6):** PSD of the correction; **cell-wise** widening (not
mean widening — a sign error survives a mean); `V_rho` cross-checked against ADR-187's
independently-measured λ spread; refusal on a non-convergent corner, on λ≤0, and on a
non-positive step.

**Study harness (10):** both truths asserted against the penalty null space; seeded and
clock-free; the verdict function fed fabricated rows so its **failure** branch
executes; the reduction notice asserted present *and* absent; end-to-end
byte-identical repeat; plus the `@slow` gate test at 40 replicates.

## Acceptance Criteria

| Criterion (PLAN slice 4) | Status | Notes |
|---|---|---|
| `test_a_non_converging_grid_point_is_rejected_not_raised` | ✅ | seed 1098, rejection count exposed |
| `test_the_unconditional_band_is_wider_than_the_conditional_one` | ✅ | asserted cell-wise |
| `test_gamma_above_one_selects_a_smoother_fit` | ✅ | 5.836 → 4.000 `edf_tensor` |
| `test_unconditional_coverage_of_the_shipped_procedure` | ✅ | `@slow` at 40 reps; 200 in the report |
| **Anchor 7 gate: coverage measured and acceptable** | ⚠️ **measured, NOT acceptable** | 0.8516 / 0.8581 vs floor 0.9192. Published as it came out, per the criterion's own instruction — this is the anchor working, not the slice failing |
| Replicate count not silently reduced | ✅ | full 200; the report discloses any reduction and a test asserts both branches |

## Perf History

Row appended to `perf/history.jsonl` for `848eeeb` (branch HEAD at the feature commit),
committed separately as `bceab3a`. Exactly +1 line. Creep verdict:
`has_structural_creep: false`, `has_wall_time_creep: false` — `peak_mib` 33 → 33 (Δ+0),
wall-time recent/baseline 1.007×. **No structural creep to raise.**

## Open Questions / Follow-ups

1. **The gate fails and the remedy is not yet decidable.** Two candidate causes with
   different fixes: our Kass–Steffey arithmetic is wrong, or the residual is shrinkage
   bias no covariance can reach. Slice 5's level 4 separates them. **Maintainer input
   wanted on one thing only:** whether to run `mgcv` levels 1 and 4 ahead of the rest
   if R time is limited.
2. **Should the penalized band ever be shown to a user while it measures 10 points
   below the estimator it replaces?** Slice 6 puts these numbers in front of a reader.
   Anchor 6 keeps the unpenalized path alive, so the option exists in both directions,
   but the question is now sharper than when the plan deferred it.
3. **Nine extra fits per surface is cheap on a fixture and not obviously cheap on a
   125k-cell book.** An analytic Jacobian and Hessian would remove them. Promoted.
4. **The coverage study runs on injected truths only.** Whether these rates hold on
   real ILEC is unmeasured. Promoted.

## Parked Polish

None. Every follow-up above is 1st-order (a direct consequence of slice 4's own
deliverables or of ADR-188), so the step-17 order cap did not bind this session.

## Impact on Golden Baselines

**None.** `tests/qa/` 94 passed unmodified; the `polaris price` spot-check on
`golden_config_flat.json` returns `total_pv_profits_cedant` 3,513,563.42 and
`total_pv_profits_reinsurer` 45,386.44. Nothing in `products/`, `reinsurance/` or the
CLI was touched — the epic's byte-identical-goldens discipline holds through slice 4,
as it must until the surfacing slice. The `perf/history.jsonl` append is additive
diagnostic data and is not a golden change.

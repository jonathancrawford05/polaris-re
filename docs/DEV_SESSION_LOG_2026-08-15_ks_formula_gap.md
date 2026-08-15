# Dev Session Log — 2026-08-15

## Item Selected

- **Source:** maintainer direction — "go for it" on the level-4 BLOCKER
- **Priority:** BLOCKER (`PRODUCT_DIRECTION_2026-07-24.md`) — the standing bar on labelling
  anything a 95% band
- **Title:** The Kass-Steffey under-inflation — localised, and it is not where ADR-189 said
- **Branch:** `claude/quirky-ramanujan-ppo0sz`, restarted from `main` @ `5a3d51a`
  (its previous PR #192 is merged)

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `5a3d51a`) | **3175 passed, 3 skipped, 126 deselected** — no standing failures |
| End state | **3177 passed, 3 skipped, 126 deselected** — +2, both new |
| `tests/qa/` goldens | untouched, not regenerated |
| Oracle | **tier 1**, local apt R 4.3.3 / mgcv 1.9.1 — see "On tiers" |

## Gap Before

Level 4 `rel_unconditional_inflation_diff`, reproduced locally before touching anything:

| cell | ours | mgcv | rel. diff | tol |
|---|---:|---:|---:|---:|
| `l2-free-sp` | 1.1109x | 1.7392x | −0.3613 **FAIL** | 0.25 |
| `l2-free-sp-factors` | 1.1591x | 1.4863x | −0.2201 pass | 0.25 |
| `l2-free-sp-kb` | 1.2139x | 1.8670x | −0.3498 **FAIL** | 0.25 |

Matching the committed build-1 figures (1.11-1.21 vs 1.49-1.87) to four significant
figures. **That agreement is what licensed reading a tier-1 run at all**, and it was
checked first rather than assumed.

## Gap After

**Unchanged, and deliberately so.** Nothing was tuned. What changed is that the gap now has
a correct explanation instead of a wrong one.

## Hypotheses Tried

ADR-189 amendment 1 named three suspects. All three are refuted.

| # | hypothesis | test | verdict |
|---|---|---|---|
| 1 | the central-difference `log_step` is too coarse | 8x sweep, 0.144-1.151 natural log | **REFUTED** — inflation moves ~1.7%; converged |
| 2 | the eigenvalue floor binds and caps variance | eigenvalues of `H` on all three cells | **REFUTED** — 0.28-0.79 against a 7.5e-03 floor; `n_floored` 0 everywhere |
| 3 | an `ln(10)²` conversion error | code reading | **REFUTED** — `KS_LOG_STEP` converts once; never mixed |
| 4 | our `V_rho` is too small | substituted `mgcv`'s exact `outer.info$hess` at `mgcv`'s λ | **REFUTED** — 1.14 → 1.20 against 1.74 |
| 5 | **the formula is not `Vb + J V_rho Jᵀ`** | built `J V_rho Jᵀ` **entirely inside `mgcv`** | **CONFIRMED** |

Hypothesis 5's measurement — `mgcv`'s coefficients, `mgcv`'s `V_rho`, `mgcv`'s λ:

| cell | `mean diag(Vc - Vp)` | `mean diag(J V_rho Jᵀ)` | ratio | implied vs reported |
|---|---:|---:|---:|---|
| `l2-free-sp` | 1.99864e-04 | 4.90834e-05 | 4.07 | 1.1815 vs **1.7392** |
| `l2-free-sp-factors` | 7.70782e-05 | 2.43909e-05 | 3.16 | 1.1539 vs **1.4863** |
| `l2-free-sp-kb` | 3.29745e-04 | 9.28381e-05 | 3.55 | 1.2441 vs **1.8670** |

`J V_rho Jᵀ` computed wholly inside `mgcv` reproduces **our** answer. So the disagreement
survives every input being `mgcv`'s, which leaves only the formula. `mgcv:::Vb.corr` takes
`dw` — the derivative of the IRLS weights w.r.t. rho — which our fitter never forms.

## What Was Done

**No fix, because there is nothing here to fix.** The deliverable is the localisation, the
two tests that pin it, and a correctly re-scoped BLOCKER.

1. **ADR-190** — the finding, the refutations, and four decisions, including the licensing
   constraint and a prediction registered in advance.
2. **Two tests** — `test_the_correction_is_exactly_j_vrho_jt` (the arithmetic *is* the
   stated formula, recomputed independently) and
   `test_the_correction_is_converged_in_the_difference_step`.
3. **The docstring** in `smoothing_uncertainty` — the "three places to look" paragraph was
   actively misleading and is replaced with the measurements.
4. **The conformance path filter** now includes `experience_gam_penalized.py`. It did not,
   so a PR changing the fitter never ran the check that measures it — a gap this very
   session would have walked into.
5. **`PRODUCT_DIRECTION`** — BLOCKER re-scoped from "find the bug" to "implement Wood
   (2016)", original entry preserved.

## The process finding, which is the part I would keep

`test_the_hessian_standard_error_is_wide_but_finite` has asserted **`n_floored == 0`** on
the standard fixture since slice 3. The eigenvalue-floor hypothesis says that number should
be large. **The repository already contained the evidence against a hypothesis it carried
for five days** across an ADR, a docstring and a PRODUCT_DIRECTION entry — in a green test
nobody thought to consult, because the test was framed as being about a standard error and
the hypothesis was framed as being about coverage.

A claim in prose and an assertion in a test are the same claim. Only one of them is
checked. Before naming a suspect, grep the suite for a test that already speaks to it.

## On tiers — and why this is a legitimate tier-1 verdict

`ROUTINE_MGCV_PARITY.md` step 2, written four days ago, permits committing only tier-3
numbers. Every number here is **tier 1**. That rule exists for Stage-A comparisons at
~1e-15 where a different BLAS makes local output meaningless; this finding is a factor of
**3-4 against a tolerance of 0.25**, and mgcv 1.9.1 and 1.9.4 do not disagree about whether
`Vc - Vp` is four times `J V_rho Jᵀ`. The tier-1 run reproducing the committed build-1
figures to four significant figures is the check that licenses it. **Labelled tier 1
throughout rather than quietly promoted**, and CI on build 8 still gates every committed
metric unchanged.

## Files Changed

| file | what |
|---|---|
| `src/polaris_re/analytics/experience_gam_penalized.py` | docstring: the refutations replace the wrong suspects |
| `tests/test_analytics/test_experience_gam_penalized.py` | +2 tests pinning the arithmetic |
| `.github/workflows/mgcv-conformance.yml` | path filter now covers the module under test |
| `docs/DECISIONS.md` | **ADR-190** |
| `docs/PRODUCT_DIRECTION_2026-07-24.md` | BLOCKER re-scoped |
| `docs/DEV_SESSION_LOG_2026-08-15_ks_formula_gap.md` | this file |

## Acceptance Criteria

| Criterion | Status | Notes |
|---|---|---|
| The gap is measured before anything changes | ✅ | reproduced to 4 s.f. against build 1 |
| Each named hypothesis is tested, not argued | ✅ | five, with numbers |
| No tolerance widened, no constant tuned | ✅ | level 4 still DISAGREES, still non-blocking |
| The finding is pinned by tests | ✅ | 2 new, both passing |
| The BLOCKER is correctly scoped | ✅ | re-scoped, not closed |
| **The blocker is closed** | ❌ | it is a slice, not a fix — see below |

## Open Questions / Follow-ups

1. **Implement Wood, Pya & Säfken (2016)'s correction** — needs `dw/drho`, which the fitter
   does not compute. **BLOCKER**, re-scoped. **Re-derive from the paper: `mgcv` is GPL
   (>= 2), polaris-re is MIT.** 1st-order.
2. **The registered prediction** — a 3.2-4.1x larger correction should move ADR-188's
   coverage from 0.8516 / 0.8581 toward the 0.9192 floor. Check it when (1) lands; a miss
   means a second cause. 1st-order.
3. **Does the same formula gap affect the new engine?** Anything the parity engine reports
   as a band inherits this until (1) lands. Already carried in
   `CONTINUATION_mgcv_parity_engine.md`. 1st-order.
4. **Audit other prose claims against the test suite.** The floor hypothesis survived five
   days beside a green test asserting its negation. **2nd-order** — a consequence of the
   finding rather than of the BLOCKER. **NICE-TO-HAVE**, and **promoted into
   `PRODUCT_DIRECTION`** (PR #195 review [P1]: it was stated here and dropped there, and
   the ledger carried the *observation* without the *actionable item* — which is this
   session's own thesis turned on itself).

## Parked Polish

**None.** All four follow-ups are carried: #1 and #2 in the `PRODUCT_DIRECTION` RE-SCOPED
blockquote, #3 in `CONTINUATION_mgcv_parity_engine.md`, #4 as its own ledger entry.

## Impact on Golden Baselines

**None.** `tests/qa/` untouched and not regenerated; the only `src/` change is a docstring.

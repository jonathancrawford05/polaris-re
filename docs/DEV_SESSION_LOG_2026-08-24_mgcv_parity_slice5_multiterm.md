# Session log — 2026-08-24 — Slice 5's remaining scope: the first multi-term mgcv-native model

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5 — remaining scope (`docs/CONTINUATION_mgcv_parity_engine.md`). Both of
slice 5's named bases (`s(AttdAge, by=StudyYear_C)`, ADR-200; `ti(AttdAge, PolYear)`,
ADR-205) were already DONE at Stage A only. This session's scope, named explicitly by
the CONTINUATION as "what remains of slice 5", is the multi-term mgcv-native model
that lets Stage B (Anchor 2's `eta` criterion) run on either term for the first time.
**PR:** (this branch, `claude/zealous-mendel-x0e0ul`), draft.
**ADR:** ADR-206.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite`
  (`apt-get update` was needed first — the initial install attempt failed on stale
  package-index 404s from the base image; a plain `apt-get update` fixed it, no
  code implication). Versions recorded: **R 4.3.3 / mgcv 1.9.1** — matches the
  routine's expected apt versions exactly, no drift to flag.
- `OPENBLAS_NUM_THREADS=1` exported for the R invocations.
- `uv run pytest tests/ -m "not slow"` baseline: **3429 passed, 22 skipped, 126
  deselected, 5 failed.** The 5 failures are `FileNotFoundError` on
  `data/mortality_tables/*.csv` — the same environment-setup gap the 2026-08-23
  session's log already corrected and named (a missing
  `scripts/convert_soa_tables.py --source pymort` run, not a repository defect).
  Not re-run here: this routine's scope is the mgcv-parity epic, and none of this
  session's code touches mortality-table loading or any path those 5 tests
  exercise — confirmed by `data/mortality_tables/` not existing at all in this
  checkout, so the failure is present before any change and independent of it.
- `uv run pytest tests/qa/` — 85 passed, 9 skipped (same missing-data-file gap on
  4 of the 5 golden configs). `tests/qa/golden_outputs/` untouched by this
  session's diff.

## Gap Before

Ran the ten-cell conformance suite at tier 1 before changing anything
(`Rscript scripts/mgcv_conformance.R` then
`uv run python scripts/compare_mgcv_conformance.py`):

```
level 1: AGREES     level 2: AGREES     level 3: AGREES
level 4: DISAGREES  level 5: AGREES
```

Numbers matched `docs/CONFORMANCE_LEDGER.md`'s last-recorded state exactly (no
drift): `l2-free-sp` `max_abs_log10_sp_diff` 6.4525e-02,
`rel_unconditional_inflation_diff` -3.2209e-01 (FAIL, the known ADR-190 blocker),
`l5-gamma` both metrics PASS. Out of this session's scope (ADR-190's separate
`dw/drho` gap).

**Slice 5's own remaining gap, before this session:** zero prior Stage-B
measurement for either the `by` term or `ti()` — no multi-term mgcv-native model
existed at all, so neither term's basis had ever been exercised inside an actual
fit and compared on `eta`.

## Provenance gate (ADR-193), applied before writing code

**Claim sentence:** `polaris_re` assembles the three-term design
(`build_python_cr_term` for the reference `s(AttdAge,k=13,bs="cr")` term,
`build_python_cr_term(by=...)` for the MI term
`s(AttdAge,by=StudyYear_C,k=13,bs="cr")`, and `build_python_ti_term` for
`ti(AttdAge,PolYear,k=(13,6),bs="cr")`) from the shared recipe and fits it with
`gam_fit.penalized_irls_general` at a FIXED, externally-supplied `sp` (one per
block) under binomial/cloglog with `ExposCnt` weights; `mgcv` computes the
identical three-term model natively via `gam()` at the same fixed `sp`; compared
on `eta` at the training design.

Applying the mechanical test to `fit_multiterm_case`'s signature: it takes
`RMultiTermRecipe`, a `TypedDict` that structurally excludes `eta`/`coef` (the
same by-type enforcement PR #202 review [P1] established for
`gam_family_conformance.fit_family_case`, re-asserted here by
`test_fit_multiterm_case_signature_takes_no_r_fit_output`) — so it is an
independent producer, and a caller error passing `r_case["eta"]` inside the
function body would be a `mypy` error, not merely a convention.

## Hypotheses Tried

Only one hypothesis, one pass, one bug caught before it left the machine.

**Hypothesis:** `mgcv`'s own formula-order convention for
`y ~ s(AttdAge) + s(AttdAge,by=StudyYear_C) + ti(AttdAge,PolYear)` places an
intercept first, then each smooth term's own columns in formula order, and each
term's own penalty block(s) can be assembled by padding with zeros outside that
term's column range — the same convention `DesignExport.s_age`/`s_year` and
`gam_reml_optimize.penalized_fit_and_score`'s `penalty_blocks` already use.

**The one change:** wrote `assemble_multiterm_design` to build `X` by
`np.hstack([intercept, ref.design, by.design, ti.design])` and pad each of
`ti()`'s two penalty blocks at the tensor term's own column start.

**First run: `ValueError: could not broadcast input array from shape (60,60)
into shape (0,0)`.** The first draft treated `ti()`'s two penalty blocks as
occupying sequential, disjoint column ranges (`ti_start` then
`ti_start + width`), the same pattern the reference and by-term's single blocks
follow — wrong for `ti()` specifically: both of its penalty blocks (ADR-205)
apply to the *same* 60-column tensor design, two different penalties on one
term, not two terms' worth of columns. Fixed by padding both blocks at the
identical `ti_start` offset. A one-line fix, caught immediately by a shape
mismatch rather than a silent wrong answer — Anchor 1's "prove the harness"
discipline working at the unit level before any R round trip was spent.

**Result: agreed on the very next run**, no second hypothesis needed —
`max_abs_eta_diff=1.242e-10`. Diagnosed rather than left as a bare pass/fail:
`fit.n_iter=9` (clean IRLS convergence), `cond(XᵀWX+S)≈4972` (well-conditioned),
and the diff's distribution (median 4.3e-13, mean 1.6e-12, max 1.242e-10,
concentrated in a handful of rows rather than uniform) is consistent with
`gam_fit`'s shared `1e-10` relative-deviance IRLS convergence floor compounding
slightly more on an 86-column, four-penalty-block design than on the ~7-13-column
single-term cases every prior Stage-A/B slice measured — not with a defect in any
of the three basis producers, all three of which already carry their own
committed parity results (ADR-194, ADR-200, ADR-205).

## Gap After

Same tier-1 ten-cell suite re-run after the change: **identical to Gap Before** —
levels 1-3 AGREE, level 4 DISAGREES (ADR-190, unaffected), level 5 AGREES. No
regression, as expected (this session's module is additive and touches nothing
the ten-cell suite's own designs depend on).

Slice 5's own new gap: **closed on the first successful measurement** —
`max_abs_eta_diff=1.242e-10`, `agrees=True`, `n=900`, `p=86`.

## Oracle Version

R 4.3.3 / mgcv 1.9.1 (tier 1, local apt) for iteration and the fix above.
**Tier-3 confirmation, same session:** dispatched via CI `workflow_dispatch` on
commit `39c49bf` (`claude/zealous-mendel-x0e0ul`). Run
[32722872476](https://github.com/jonathancrawford05/polaris-re/actions/runs/32722872476),
both jobs `success`, R job ~36s + compare job ~40s.

- **Oracle:** R 4.6.1 / mgcv 1.9.4, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8) — confirmed from the R job's own `ORACLE_IMAGE` env line, same digest
  every measurement in this epic has used since ADR-189 amendment 2.
- **This session's row, read from job-log stdout (`get_job_logs`), not the
  job-summary artifact:** `| n | p | max abs eta diff | agrees |` →
  `| 900 | 86 | 1.242e-10 | True |` — **identical to the tier-1 reading at every
  printed digit**, the same cross-tier stability ADR-194 and ADR-205 each found
  on their own first-pass agreements.
- **Required levels 1-3 of the existing ten-cell suite:** `Required levels [1, 2,
  3] all agree.` printed directly in the job log — no regression from this
  session's workflow/probe additions. Level 4 unchanged (still DISAGREES,
  ADR-190), level 5 unchanged (still AGREES).

This closes slice 5's remaining Stage-B gap to well within tolerance, tier 1 and
tier 3 identical to the printed digit — the same shape of first-measurement
result as ADR-194 (slice 2), ADR-195 (slice 3), and ADR-205 (`ti()`'s own basis).
See ADR-206 and the `docs/CONFORMANCE_LEDGER.md` tier-3 row.

## Provenance

| comparison | left producer | right producer | provenance |
|---|---|---|---|
| `eta` (training design, `n=900`, `p=86`) | `gam_fit.penalized_irls_general` over a design assembled by `assemble_multiterm_design` from `gam_basis_cr`'s independently-verified `cr`/`by`/`ti` producers, via `gam_stage_a.build_python_cr_term`/`build_python_ti_term` | `mgcv::predict(m, type='link')` on a native `gam()` fit of the identical three-term formula at the same fixed `sp` | **INDEPENDENT** (`MULTITERM_CLAIM`) |
| `coef` (both sides, diagnostic only) | — | — | not compared (Anchor 2 — coefficients are never a Stage-B acceptance criterion; `mgcv` reparameterises) |
| the required ten-cell suite's levels 1-3 (unaffected, re-run for regression only) | Python's existing verified fitter/optimiser | `mgcv`, unchanged designs | INDEPENDENT (pre-existing claim, ADR-189/195/196/199 — re-confirmed, not re-established, by this session's dispatch) |

## What remains of slice 5

**Nothing — slice 5 is DONE, 2026-08-24 (ADR-206).** Both named bases (ADR-200,
ADR-205) and the multi-term Stage-B model this session builds close every line
`docs/CONTINUATION_mgcv_parity_engine.md` had open for this slice. Three things
this session explicitly does NOT claim, named in ADR-206 as separate follow-on
work rather than left implicit:

1. **Anchor 2's primary MI-contrast-on-a-grid metric.** This session compares
   `eta` at the training design (Anchor 2's secondary metric); the primary
   metric needs evaluating the by-term and reference bases at covariate values
   away from the training rows, which needs the same knot vector and
   identifiability-constraint transform re-applied at unseen `x` —
   `gam_basis_cr.py`'s own docstring already marks extrapolation *beyond* the
   knot range as unverified, and evaluation *inside* the range at new points is
   a related but distinct, still-open question.
2. **Slice 4 part B's search extended to N>2 blocks.** `assemble_multiterm_design`
   produces exactly the `(x, penalty_blocks)` shape `select_lambdas_continuous`
   consumes (4 blocks here), but nothing in this session calls it — direct,
   cheap follow-on work for a session that wants it.
3. **`sz` (slice 6).** Not part of this multi-term model; needs slice 6's own
   basis first.

## Quality gate

- `uv run ruff format src/polaris_re/analytics/gam_multiterm_conformance.py
  tests/test_analytics/test_gam_multiterm_conformance.py` — 1 file reformatted
  (the new module, on first write), test file unchanged.
- `uv run ruff check ... --fix` — 3 `E501`s (long docstring lines referencing
  other modules by dotted path) fixed by hand, not auto-fixable. Clean after.
- `uv run mypy src/polaris_re/analytics/gam_multiterm_conformance.py` — 0 errors.
- `uv run pytest tests/test_analytics/test_gam_multiterm_conformance.py -v` — 3
  passed, including the R-gated end-to-end test (R is installed this session).
- `uv run pytest tests/ -m "not slow"` — 3429 passed, 22 skipped, 126 deselected,
  5 failed — **identical failure set to the Setup baseline**, all 5 the
  pre-existing missing-mortality-CSV gap, none newly introduced. Net +3 tests
  over baseline (this session's own file); no other test count moved.
- `uv run pytest tests/qa/` — 85 passed, 9 skipped, identical to the Setup
  baseline. `tests/qa/golden_outputs/` byte-identical — `git status` shows no
  changes under `data/` or `tests/qa/`; this session never touches the fitter,
  any product/reinsurance module, or the CLI (Anchor 7).
- Ten-cell conformance suite re-run (tier 1) — see Gap After; identical before
  and after.
- `docs/CONFORMANCE_LEDGER.md` — two rows appended (tier 1 hypothesis, tier 3
  confirmation), same discipline every prior slice-2/3/5 row in the ledger
  follows.
- `docs/DECISIONS.md` — ADR-206 appended.
- `docs/PLAN_mgcv_parity_engine.md` and `docs/CONTINUATION_mgcv_parity_engine.md`
  — slice 5 updated from IN PROGRESS to DONE, the gap-audit table's two `by`/`ti`
  rows updated, backlog items 3/4/8 updated to name what ADR-206 unblocks versus
  what it does not claim.

## Perf history

One row appended for the PR's initial open (ADR-177), commit-pinned to `39c49bf`
— this session's actual code change. `output_fingerprint` (`8331a13f…`) unchanged
from every preceding row; `peak_mib` 33→33 (Δ0); wall-time ratio 1.235x, inside
the 1.25x band. `has_structural_creep: false` — confirming this session's diff
(a new analytics module, an R probe, a CI diagnostic step, docs) is behaviourally
inert for the `TermLife` engine `perfbench` probes, as expected: nothing here
touches `products/`, `reinsurance/` or the CLI.

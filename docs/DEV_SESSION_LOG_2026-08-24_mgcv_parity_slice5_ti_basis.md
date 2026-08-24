# Session log — 2026-08-24 — Slice 5, the `ti()` tensor interaction

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5 — `ti()` and the varying-coefficient MI term (`docs/PLAN_mgcv_parity_engine.md`
§3). The MI term's own basis (`s(AttdAge, by=StudyYear_C)`) was already DONE (ADR-200,
2026-08-22); this session's own scope is the slice's other named piece, `ti(AttdAge,
PolYear)`.
**PR:** #209 (`claude/zealous-mendel-oyim0j`), draft.
**ADR:** ADR-205.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite`.
  Versions recorded: **R 4.3.3 / mgcv 1.9.1** — matches the routine's expected apt
  versions exactly, no drift to flag.
- `OPENBLAS_NUM_THREADS=1` exported for the whole session.
- `make test` baseline: initially **3412 passed, 22 skipped, 5 failed** — the 5
  failures were `FileNotFoundError` on `data/mortality_tables/*.csv`, the same
  environment-setup gap the 2026-08-23 session's log corrected (a missing
  `scripts/convert_soa_tables.py --source pymort` run, not a repository defect).
  Ran that step; all 54 affected tests then passed. **Corrected baseline: 3417
  passed, 22 skipped, 0 failed** before any code change. `test_the_r_script_runs_
  end_to_end_and_agrees` (the R-gated test) PASSED, confirming the R install is
  wired correctly.

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
`l5-gamma` both metrics PASS. This is the standing state slice 5 inherits — level 4
is ADR-190's separate `dw/drho` gap, out of this session's scope.

**Slice 5's own remaining gap, before this session:** zero prior measurement for
`ti(AttdAge, PolYear)`. No Python producer existed for a two-margin tensor
interaction, and no R-side extraction case for one either — `gam_term_extract.R`'s
`extract_smooth_one` only ever handled a single covariate.

## Provenance gate (ADR-193), applied before writing code

**Claim sentence:** `gam_basis_cr.ti_basis` builds the `ti(x1, x2, bs="cr")`
tensor-interaction design (`design_X`) and its two penalty blocks (`penalty_S`)
from each margin's covariate locations and knot vector, following `mgcv`'s own
tensor-smooth construction; `mgcv` computes the same quantities via
`smoothCon(ti(x1, x2, bs="cr", k=(k1,k2)), absorb.cons=TRUE)`; compared on
`design_X`, `penalty_S` (both blocks) and `rank` (both blocks).

Applying the mechanical test to `build_python_ti_term`'s signature: it takes
`x1`, `x2` and `term` (the spec) — none of which is the R side's own output — so
it is an independent producer, structurally the same shape as `build_python_cr_term`.

## Hypotheses Tried

Only one hypothesis was needed, but it took two passes to get right — the second
pass is the actual finding this session produced.

**Pass 1 — the naive reading of `mgcv::ti`'s R source.** Read `mgcv::ti` → `mgcv::te`
→ `mgcv:::smooth.construct.tensor.smooth.spec` (via `deparse()` on the installed
tier-1 package) and hand-translated it: per-margin `smoothCon(absorb.cons=TRUE)`,
an `np=TRUE`-gated SVD reparameterization per 1-D margin (`ti()`'s own default),
per-margin eigenvalue-normalized penalty, row-wise Kronecker design/penalties. Wrote
a scratch R script (`verify_ti_construction.R`, not committed) replicating this by
hand and comparing against `smoothCon(ti(x1,x2,...))` directly. **Disagreed
badly**: `max abs X diff = 181.8`, `max abs S diff` 3.3–3.9 — not noise, a
different construction.

**Pass 2 — instrument the running constructor.** Rather than re-reading the source
and guessing again (CLAUDE.md/Anchor 8), used `assignInNamespace` to install a
modified copy of `smooth.construct.tensor.smooth.spec` that `assign()`s its
internal locals (`Xm`, `Sm`, `XP`, `object$margin`, `object$np`, `object$mc`, per-
margin `dim`/`noterp`) to the global environment mid-execution, then ran the real
`smoothCon(ti(...))` call through it. Found: `object$margin[[i]]$noterp` is
**non-NULL** for a `cr` margin (`smooth.construct.cr.smooth.spec` sets
`object$noterp <- TRUE`), and the tensor constructor's reparam loop is
`if (is.null(object$margin[[i]]$noterp)) { ...SVD reparam... } else XP[[i]] <-
NULL` — false for `cr`, so `XP[[i]] <- NULL` is a no-op assignment into an empty
list (`list()[[1]] <- NULL` does not create an element) and **the reparameterization
never runs for an all-`cr` tensor**. Removing that step from the hand-replica made
`X` agree exactly (`max abs diff = 0`); `S` still disagreed by a constant ratio per
block (8.06x on one case). A second instrumented run isolated this to `smoothCon`'s
own top-level `scale.penalty` step (`sm$S[[i]] <- sm$S[[i]] / maS`, `maS =
norm(sm$S[[i]])/norm(sm$X, "I")^2`) — already known from ADR-194's `cr` basis work,
but applied there only once, at the margin level; a tensor-product smooth is
itself a `smoothCon()` return value, so the rescaling fires a **second** time,
over the *full tensor* `X`/`S`, not the margin's. Adding that second rescale
(reusing `_r_norm_one`/`_r_norm_inf` from `gam_basis_cr.cr_basis`) closed the gap
to `4.44e-16` (float round-trip noise) on both `X` and both `S` blocks.

**Result: derivation confirmed by direct R measurement before any Python was
written** — `docs/CONFORMANCE_LEDGER.md`'s row for this session records the R-only
verification; `gam_basis_cr.ti_basis`/`gam_stage_a.build_python_ti_term` then
implement exactly the five-step construction that measurement pinned. No third
hypothesis was needed.

## Gap After

Same tier-1 ten-cell suite re-run after the change: **identical to Gap Before** —
levels 1-3 AGREE, level 4 DISAGREES (ADR-190, unaffected), level 5 AGREES. No
regression, as expected (slice 5's basis work does not touch the ten-cell suite's
own designs).

Slice 5's own new gap: **closed on first measurement** for `ti_basis`'s
`design_X`/`penalty_S`/`rank` (both blocks) — `ti-default-knots-k6-k5`:
`max_X_diff=1.549e-14`, `max_S_diff=(2.975e-14, 4.130e-14)`, `rank_diff=(0,0)`;
`ti-target-attdage-polyear` (the target formula's own `k=c(13,6)` knot vectors):
`max_X_diff=1.504e-14`, `max_S_diff=(4.974e-14, 3.908e-14)`, `rank_diff=(0,0)`.

## Oracle Version

R 4.3.3 / mgcv 1.9.1 (tier 1, local apt) for iteration and the derivation above.
**Tier-3 confirmation, same session:** dispatched via CI `workflow_dispatch` on
commit `c24d59d` (`claude/zealous-mendel-oyim0j`). Run
[32677470292](https://github.com/jonathancrawford05/polaris-re/actions/runs/32677470292),
both jobs `success`, ~75s end to end (R job ~40s, compare job ~30s).

- **Oracle:** R 4.6.1 / mgcv 1.9.4, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8) — confirmed from the R job's own `ORACLE_IMAGE` env line, same digest
  every measurement in this epic has used since ADR-189 amendment 2.
- **Slice 5's two new rows, read from job-log stdout (`get_job_logs`), not the
  job-summary artifact:**
  `ti-default-knots-k6-k5 | True | 1.549e-14 | 2.975e-14, 3.997e-14 | (0, 0)`
  (tier 1's second `S` diff was 4.130e-14 — last-bit consistent with the
  mgcv-version/BLAS difference the routine's tier discipline predicts);
  `ti-target-attdage-polyear | True | 1.504e-14 | 4.974e-14, 3.908e-14 | (0, 0)` —
  **identical to the tier-1 reading at every printed digit** on this case, the
  target formula's own knots.
- **Required levels 1-3 of the existing ten-cell suite:** `Required levels [1, 2,
  3] all agree.` printed directly in the job log — no regression from this
  session's workflow/extractor edits. Level 4 unchanged (still DISAGREES, ADR-190),
  level 5 unchanged (still AGREES).

This closes slice 5's `ti()` gap to float round-trip precision, tier 1 and tier 3
agreeing in order of magnitude (identical to the printed digit on the harder,
target-knots case) — the same shape of first-measurement result as ADR-194
(slice 2), ADR-200 (the by-basis) and ADR-199 (slice 4 part B). See ADR-205 and
the `docs/CONFORMANCE_LEDGER.md` tier-3 row.

## Provenance

| comparison | left producer | right producer | provenance |
|---|---|---|---|
| `design_X`, `penalty_S` (both blocks), `rank` (both blocks) — `ti-default-knots-k6-k5`, `ti-target-attdage-polyear` | `gam_basis_cr.ti_basis` (row-wise Kronecker of two constrained `cr` margins, normalized once per margin and once at the tensor level) via `build_python_ti_term` | `mgcv smoothCon(ti(x1, x2, bs='cr', k=(k1,k2)), absorb.cons=TRUE)$X`/`$S`/`$rank` | **INDEPENDENT** (`TI_BASIS_CLAIM`) |
| the R-side internal guard (`smoothCon(ti(...))` vs `lpmatrix`/`m$smooth[[1]]$S`/`$rank`, both cases) | entirely inside R (`extract_smooth_ti`) | entirely inside R | INDEPENDENT, inside R only (ADR-191's discipline, now re-exercised on a two-margin term) |
| `knots1`/`knots2` (recipe context, not compared by `TI_BASIS_CLAIM`) | `gam_term_extract.R` (`sm$margin[[i]]$xp`, mgcv's own default placement on the `ti-default-knots-k6-k5` case) | n/a — read by `build_python_ti_term`'s caller, never compared as a claimed quantity | not a comparison (shared recipe, ADR-193's mechanical-test exemption, same status as slice 2's supplied knots) |

## What remains of slice 5

Both of slice 5's named pieces (PLAN §3: `s(AttdAge, by=StudyYear_C)` and
`ti(AttdAge, PolYear)`) now have DONE Stage-A results (ADR-200, ADR-205). What
remains is Stage B: a multi-term mgcv-native model exercising both terms together
(and the rest of the target formula), which is the shared prerequisite for (a)
this slice's own Anchor-2 comparisons (the MI contrast, `η`) on either term, (b)
extending slice 4 part B's continuous search above N=2 blocks, and (c)
demonstrating Anchor 5's absolute/relative idiom end to end. Slice 5 is therefore
**still IN PROGRESS**, not DONE — this session closes its Stage-A half entirely,
not the slice.

## Quality gate

- `uv run ruff format src/ tests/` — clean.
- `uv run ruff check src/ tests/ --fix` — all checks passed (3 initial `E501`s
  fixed by hand, not auto-fixable).
- `uv run mypy src/polaris_re/analytics/gam_basis_cr.py
  src/polaris_re/analytics/gam_stage_a.py` — zero errors attributable to either
  changed file (confirmed by grepping the full-repo mypy output for the two
  filenames — every reported error belongs to a pre-existing file elsewhere in
  the import graph; CLAUDE.md's "mypy is CI's job — act only on errors your
  change newly introduces").
- `uv run pytest tests/ -m "not slow"` — **3449 passed**, 3 skipped (helm binary
  absent, an empty-parametrize-set skip — both pre-existing and unrelated), 0
  failed. Net +32 over the corrected 3417/0/0 baseline: 6 new `build_python_ti_term`
  tests + 1 R-gated ti-parity test in `test_gam_stage_a.py`, 2
  `sum_to_zero_null_space` tests + 6 `ti_basis` tests in `test_gam_basis_cr.py`,
  plus the pre-existing tests widened to tolerate the new R payload entries.
- `uv run pytest tests/qa/` — 94 passed. `tests/qa/golden_outputs/` byte-identical
  (`git status` empty on `data/`, `tests/qa/`) — this session never touched the
  fitter or any production model path.
- Ten-cell conformance suite re-run (tier 1) — see Gap After; identical before and
  after.
- `docs/CONFORMANCE_LEDGER.md` — two rows appended (tier 1 hypothesis, tier 3
  confirmation), matching the discipline every prior slice-2/5 row in the ledger
  follows.

## Perf history

One row appended for the PR's initial open (ADR-177), commit-pinned to `c24d59d`
— the diff's actual code change, before the two follow-up doc/review commits.
`output_fingerprint` (`8331a13f…`) unchanged from every preceding row, confirming
this session's diff — Stage-A basis layer, R extractor, docs — is behaviourally
inert for the `TermLife` engine `perfbench` probes.

**Creep verdict, measured (`uv run python scripts/perf_history.py
--check-only`), added here per PR #209 review [P2-3]:** `has_structural_creep:
false`, `has_wall_time_creep: false`, `has_config_drift: false` — a real verdict,
not `insufficient_data` (25 rows against a window of 3). `peak_mib` 33→33
(Δ0); wall-time ratio 1.235x, inside the 1.25x band.

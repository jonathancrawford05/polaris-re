# Session log — 2026-08-22 — Slice 5, the MI term's numeric-`by` basis

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5 — `ti()` and the varying-coefficient MI term (`docs/PLAN_mgcv_parity_engine.md`
§3, "ship the MI term first if they split"). Depends on slices 2 and 4, both DONE.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite`.
  Versions recorded: **R 4.3.3 / mgcv 1.9.1** — matches the routine's expected apt
  versions exactly, no drift to flag.
- `OPENBLAS_NUM_THREADS=1` exported for the whole session.
- `make test` baseline (`uv run pytest tests/ -m "not slow"`): **3319 passed, 22
  skipped, 5 failed.** The 5 failures are pre-existing and out of this routine's
  scope — missing committed data files (`data/mortality_tables/*.csv`,
  `test_experience_loaders`'s ILEC fixture), not code regressions; confirmed by
  `git log` on the affected test files (last touched days before this session) and
  by `FileNotFoundError` being the failure mode, not an assertion. `test_the_r_
  script_runs_end_to_end_and_agrees` (the R-gated test) PASSED, confirming the R
  install is wired correctly.

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
is ADR-190's separate `dw/drho` gap, out of this session's scope, and levels 1-3
remaining green is the regression check every later step in this session re-runs.

**Slice 5's own gap, before this session:** zero prior measurement. No Python
producer existed for a numeric-`by` `cr` smooth — the MI term's own basis,
`s(AttdAge, by = StudyYear_C)` — and no R-side extraction case for one either.

## Provenance gate (ADR-193), applied before writing code

**Claim sentence:** `gam_basis_cr.cr_basis` (+ row-scaling by the by-variable,
no identifiability constraint absorbed — see below) builds the numeric-`by` `cr`
basis (`design_X`, `penalty_S`) from the covariate locations, a knot vector, and
the by-variable values; `mgcv` computes the same quantities via
`smoothCon(s(x, by=z, bs="cr", k=k), absorb.cons=TRUE)`; compared on `design_X`,
`penalty_S`, and `rank`.

Applying the mechanical test to `build_python_cr_term`'s signature: it takes `x`,
`term` (the spec) and now `by` — none of which is the R side's own output — so it
remains an independent producer, same as slice 2. This reuses `CR_BASIS_CLAIM`
(same two producers, same claimed quantities); no new claim object was needed.

## Hypotheses Tried

**Hypothesis 1 (the only one this session needed):** a numeric-`by` `cr` smooth's
identifiability constraint. Before writing any Python, ran a direct R probe
(`/tmp/.../probe_by.R`, `probe_by2.R`, `probe_by3.R` — not committed, diagnostic
only) against local tier-1 R:

- `smoothCon(s(x, by=z, bs="cr", k=k), absorb.cons=TRUE)$C` has **0 rows** — no
  constraint is absorbed at all, unlike the no-`by` case's `colMeans(X)` row.
- `smoothCon(s(x, by=z, ...), absorb.cons=TRUE)$X` equals
  `z * smoothCon(s(x, ...), absorb.cons=FALSE)$X` exactly (max abs diff `0`) — the
  **unconstrained** k-column basis, each row scaled by `z`.
- The penalty `S` is identical between the by-case and the no-by unconstrained
  case (max abs diff `0`) — untouched by the by-scaling.
- Knots agree with the no-by case exactly (by-variable does not affect knot
  placement).

This matches `mgcv`'s own documented behaviour (`?s`, by argument): a numeric-`by`
smooth is not sum-to-zero constrained because `by * constant` need not be
collinear with the intercept. **The change:** implemented exactly this — one new
function `gam_basis_cr.by_scale_design` (row-scale an unconstrained design) and a
branch in `build_python_cr_term` that skips `absorb_sum_to_zero_constraint` when
`by` is supplied.

**Result: AGREES on first measurement**, tier 1 — see the ledger row. No second
hypothesis was needed this session.

## Gap After

Same tier-1 ten-cell suite re-run after the change: **identical to Gap Before** —
levels 1-3 AGREE, level 4 DISAGREES (ADR-190, unaffected), level 5 AGREES. No
regression, as expected (slice 5's basis work does not touch the ten-cell suite's
own designs).

Slice 5's own new gap: **closed on first measurement** for the `by`-scaled `cr`
basis's `design_X`/`penalty_S`/`rank` — `max_X_diff=2.176e-14`,
`max_S_diff=3.775e-15`, `rank_diff=(0,)`, both at rank 11 for k=13. Tier 1 only at
commit time; tier-3 CI dispatch is the next step (see below — this file is updated
with the tier-3 result once read).

## What remains of slice 5

This session shipped the numeric-`by` `cr` basis only — one of slice 5's two named
pieces (PLAN §3: `s(AttdAge, by=StudyYear_C)` and `ti(AttdAge, PolYear)`). Per the
PLAN's own "ship the MI term first if they must be split," this is deliberate: the
MI term is the cheap, well-conditioned, actually-wanted piece (13 coefficients);
`ti()` — tensor interaction with marginal main effects excluded — is unstarted and
is a materially different construction (needs its own row/column tensor-product
machinery and its own identifiability treatment), not attempted this session.
Slice 5 is therefore **IN PROGRESS**, not DONE: the by-scaled `cr` basis Stage-A
comparison is done; `ti()` and a multi-term fitted model exercising both together
remain.

## Oracle Version

R 4.3.3 / mgcv 1.9.1 (tier 1, local apt) for iteration. Tier-3 confirmation:
dispatched via CI `workflow_dispatch`, oracle `sha256:0d54c192…` (build 8) — same
digest every measurement in this epic has used since ADR-189 amendment 2. Run
number and result appended below once read.

## Provenance

| comparison | left producer | right producer | provenance |
|---|---|---|---|
| `design_X`, `penalty_S`, `rank` (by-term, `mi-term-attdage-by-k13`) | `gam_basis_cr.cr_basis` + `by_scale_design` (Wood's construction, row-scaled) | `mgcv smoothCon(s(x, by=z, bs='cr', k), absorb.cons=TRUE)$X`/`$S`/`$rank` | **INDEPENDENT** (`CR_BASIS_CLAIM`, reused unchanged from slice 2) |
| `knots` (same case) | `build_python_cr_term` (reads the shared `x` recipe, computes nothing knot-specific here since knots were supplied) | `mgcv smoothCon(...)$xp` | ECHO (supplied-knot case — neither side computes it independently, same as slice 2's 3 supplied-knot cases) |
| the R-side internal guard (`smoothCon` vs `lpmatrix`/`m$smooth[[1]]`, by-case) | entirely inside R | entirely inside R | INDEPENDENT, inside R only (ADR-191's existing standing check, now re-exercised on a by-term) |

## Quality gate

- `uv run ruff format src/ tests/` — 307 files unchanged (no reformatting needed).
- `uv run ruff check src/ tests/ --fix` — all checks passed.
- `uv run pytest tests/ -m "not slow"` — 3319 passed, 22 skipped, 5 failed (same 5
  pre-existing data-file failures as the baseline — no new failures, no count
  change elsewhere; the new by-case is exercised inside an existing test function's
  loop, not a new test).
- `uv run pytest tests/qa/` — 85 passed, 9 skipped. `tests/qa/golden_outputs/`
  byte-identical (`git status` empty on `data/`, `tests/qa/`) — this session never
  touched the fitter or any production model path.
- Ten-cell conformance suite re-run — see Gap After.

## Tier-3 confirmation

*(filled in after CI dispatch and read)*

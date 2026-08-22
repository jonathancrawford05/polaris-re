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
remains an independent producer, same as slice 2. Originally shipped reusing
`CR_BASIS_CLAIM`; PR #206 review [P1] found that claim's *published producer
strings* misdescribe the by-row (it names the constraint absorption the by-branch
skips), so the by-construction now carries its own `CR_BY_BASIS_CLAIM` — same three
quantities, same INDEPENDENT provenance, different producer strings. No measured
value changed.

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
| `design_X`, `penalty_S`, `rank` (by-term, `mi-term-attdage-by-k13`) | `gam_basis_cr.cr_basis` + `by_scale_design` (Wood's construction, row-scaled) | `mgcv smoothCon(s(x, by=z, bs='cr', k), absorb.cons=TRUE)$X`/`$S`/`$rank` | **INDEPENDENT** (`CR_BY_BASIS_CLAIM` — split out from `CR_BASIS_CLAIM` after PR #206 review [P1]) |
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
- `perf/history.jsonl`: one row appended (ADR-177, initial PR open only).
  `scripts/perf_history.py` flagged `creep: true` (ratio 1.43 on a 3-row-vs-3-row
  window). **Not a regression, and not this session's:** the `output_fingerprint`
  is `8331a13f` on this row and on all five preceding it — byte-identical
  behaviour — and this run's 0.0883s sits inside the existing spread of the last
  five rows (0.0631–0.1341s), which is shared-runner timing noise on a 3-row
  window. This session touched no `TermLife` projection code at all; the whole
  diff is the mgcv-parity Stage-A basis layer, its R extractor, and docs.

## Tier-3 confirmation

Dispatched `mgcv-conformance.yml` via `workflow_dispatch` on commit `08472b3`
(`claude/zealous-mendel-9e1awi`). Run
[32571764900](https://github.com/jonathancrawford05/polaris-re/actions/runs/32571764900),
both jobs `success`, ~76s end to end.

- **Oracle:** R 4.6.1 / mgcv 1.9.4, image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8) — confirmed from the R job's own `ORACLE_IMAGE` env line, same digest
  every measurement in this epic has used since ADR-189 amendment 2.
- **Slice 5's new row, read from job-log stdout (`get_job_logs`), not the
  job-summary artifact:** `mi-term-attdage-by-k13 | True | 2.176e-14 | 3.775e-15 |
  (0,) | True` — **identical to the tier-1 reading at every printed digit.**
- **Required levels 1-3 of the existing ten-cell suite:** the "Gate on levels
  1-3, annotate levels 4-5" step completed with conclusion `success` — no
  regression from this session's workflow/extractor edits.

This closes slice 5's own gap for the by-scaled `cr` basis to float round-trip
precision, tier 1 and tier 3 identical — the same shape of first-measurement
result as ADR-194 (slice 2), ADR-195 (slice 3) and ADR-199 (slice 4 part B).
See ADR-200 and the `docs/CONFORMANCE_LEDGER.md` tier-3 row.

## Review round — PR #206 (3× [P1], 1× [P2])

The automated review returned **approve** with four findings. Three accepted in
full, one partially; **no measured value changed**, and the corrected head was
re-confirmed at tier 3 (run
[32576263426](https://github.com/jonathancrawford05/polaris-re/actions/runs/32576263426),
same digest `sha256:0d54c192…`): by-row still `2.176e-14` / `3.775e-15` /
`(0,)`, slice 2's five rows unchanged, `Required levels [1, 2, 3] all agree.`

**[P1] The published legend misnamed the by-row's producers — accepted.** The
substantive finding of the round, and an ADR-193 issue rather than a cosmetic
one. Reusing `CR_BASIS_CLAIM` meant `evidence_markdown()` printed, verbatim above
a table containing `mi-term-attdage-by-k13`, four strings that misdescribe it:
`absorb_sum_to_zero_constraint` (skipped by that branch), a right producer without
`by=z`, a "Python-constrained penalty block" for `rank` (unconstrained here), and
"only the shared covariate `x`" (it also reads `by`). ADR-193's own failure mode
inverted — the ADR prose was accurate and the *derived* legend was the wrong part,
when deriving it was supposed to be what guaranteed it travelled correctly. Fixed
with a distinct `CR_BY_BASIS_CLAIM` and a split CI table (one legend per
construction). Classification unchanged: still three INDEPENDENT quantities.

**[P1] Zero coverage in the R-free suite — accepted.** The by-path's only test was
R-gated and `ci.yml` installs no R, so `by_scale_design`, the `build_python_cr_term`
by-branch and both new raises never executed in CI. Added 10 R-free tests following
`test_gam_basis_cr.py`'s existing pattern. **Verified by mutation rather than
assumed:** with R absent, a no-op `by_scale_design` now fails the suite; before this
it went green.

**[P1] New mypy error — accepted.** `gam_basis_cr.py:264` returned `Any` from a
concretely-typed function. Verified independently that `main`'s copy of the file is
clean and the PR added exactly this one error, so it is not inherited baseline noise
(the routine's "act only on errors your change newly introduces"). CI's mypy step is
`continue-on-error: true`, which is why lint went green over it. One-line `np.asarray`.

**[P2] `by = NULL` JSON shape — partially accepted, and the disagreement is
recorded rather than quietly dropped.** The reviewer is right that `list(by = NULL)`
**retains** the element (unlike `l$by <- NULL`), so the comment's word "dropped" was
wrong and is corrected. But the inferred consequence does not hold: the reviewer
reasoned from jsonlite's *default* `null = "list"` (which would emit `{}`), while
`write_json` here passes `null = "null"` explicitly — so the field emits as JSON
`null` and Python reads `None`. Measured twice, before and after the change. The
`list[float] | None` annotation is therefore the shape actually emitted, not an
assumption, and the comment now names the setting in force and what the default
would have done instead.

**One existing test assertion changed, deliberately and in the tightening
direction.** The R-gated parity test asserted `evidence is CR_BASIS_CLAIM` for
every case; it now asserts the claim matching each branch. This is strictly
stronger — the old form passed for the by-case only because it did not distinguish
the two claims — and it was required by the [P1] fix rather than a way around it.
Flagged explicitly because "never change an existing test assertion to make it
pass" is a standing rule of this routine and the exception should be visible, not
buried in a diff.

**Post-review quality gate:** `ruff format`/`check` clean · full suite **3329
passed** (+10 new tests), 22 skipped, same 5 pre-existing missing-data-file
failures and no new ones · `tests/qa/` 85 passed, goldens byte-identical ·
tier-1 conformance re-run unchanged.

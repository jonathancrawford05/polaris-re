# Session log — 2026-09-01 — Slice 7: `select = TRUE`'s double penalty (Stage A + a fixed-`sp` Stage B)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 7 — `docs/PLAN_mgcv_parity_engine.md`. The routine's "next unchecked
slice, no fallback picks" rule selects it: every basis PLAN §1 names now has
both Stage-A and Stage-B INDEPENDENT parity evidence (slices 1-6b), and slices
5e/5f closed the outer search's own robustness questions without leaving a
registered blocker.
**PR:** `claude/intelligent-hamilton-cjmsiu` (this session's designated branch).
**ADR:** ADR-217.

## Setup

- `uv sync --all-extras` — clean (4 new packages: `statsmodels`, `patsy`,
  `openpyxl`, `et-xmlfile`).
- Installed the local scratch oracle (tier 1): `apt-get install -y -qq
  r-base-core r-cran-mgcv r-cran-jsonlite` — first attempt failed on stale
  package-index 404s (the same recurring transient prior sessions record,
  e.g. the 2026-08-31 log); `apt-get update` fixed it. Versions recorded:
  **R 4.3.3 (2024-02-29) / mgcv 1.9-1** — matches the routine's expected apt
  versions, no drift to flag.
- Read `docs/ROUTINE_MGCV_PARITY.md` in full, `docs/VERIFICATION_STANDARD.md`,
  `docs/PLAN_mgcv_parity_engine.md` (Anchors 1, 2, 3, 4, 8, slice 7's own
  entry and its "known collision" note), `docs/CONTINUATION_mgcv_parity_engine.md`'s
  status block through slice 6b/ADR-216, `docs/CONFORMANCE_LEDGER.md`,
  CLAUDE.md, and DECISIONS.md ADR-189/190/191/192/193 plus the slice
  6/6b ADRs (215/216).

## `make test` baseline

Without R: `uv run pytest tests/ -m "not slow" -q` — **3505 passed, 5 failed,
33 skipped, 126 deselected.** The 5 failures are a pre-existing environment
gap (`FileNotFoundError: Mortality table CSV not found` — mortality tables
are generated, not committed, CLAUDE.md §11) unrelated to this epic; not
regenerated this session since nothing in this epic's scope touches that
path. With R installed:
`tests/test_analytics/test_experience_mgcv_conformance.py::test_the_r_script_runs_end_to_end_and_agrees`
flips SKIPPED → PASSED, matching `ROUTINE_MGCV_PARITY.md`'s own documented
delta exactly. Proceed, per the routine's own baseline rule.

## Gap Before

**No Python producer for `select = TRUE`'s extra penalty existed.**
`gam_model.assemble_model_design` had no `select` concept at all — every
term's penalty block count was fixed at whatever its basis producer
returned. `docs/PLAN_mgcv_parity_engine.md`'s gap-audit table read
`select = TRUE`: **Not started.** The claim sentence could not be filled in
— there was no left-hand producer to name.

**One prerequisite named in the PLAN itself**, filed by PR #212 round-2
review and left unfixed since 2026-08-25: `fit_polaris_gam`'s at-bound guard
raised `PolarisComputationError` unconditionally at either search bound, but
the upper bound (`log10(sp) -> +inf`, a term with no signal) is exactly what
`select = TRUE` is meant to produce — this slice would hit that raise head-on
unless fixed first.

**Tier and digest:** N/A — no prior measurement exists to state a "before"
number for.

## Hypotheses tried

1. **The guard fix, per the reviewer's own suggested shape.** Split the
   at-bound check: the LOWER bound still raises unconditionally (a
   conditioning defect regardless of `select`); the UPPER bound is reported
   on the fit (`PolarisGAMFit.at_bound`/`.at_bound_blocks`, new field) by
   default, with a new `strict=True` parameter for the one existing caller
   (`gam_model_conformance.fit_free_sp_case`) that wants a hard raise at
   either bound for conformance use. **Held on the first try** — two new
   R-free tests reproduce PR #212's own false-positive fixture (a `cr` term
   with `y` drawn independent of its covariate, which legitimately shrinks
   to the upper bound under a narrow search range): one asserts the default
   reports rather than raises, one asserts `strict=True` still raises.

2. **Is `select = TRUE`'s extra penalty one rule, or four (one per basis)?**
   Read `mgcv`'s own `gam(..., select=TRUE, fit=FALSE)$smooth[[i]]$S`
   structurally at tier 1 first — `fit=FALSE` is exact for this purpose (no
   fit needed, `S` never depends on `y`), so this was cheap. A single
   `s(x, bs="cr", k=13)` term showed `select=TRUE` appends exactly ONE extra
   `(k-1, k-1)` block. Hypothesis: that block is `U0 @ U0.T`, `U0` the
   eigenvectors of the term's OWN existing penalty below
   `numpy.linalg.matrix_rank`'s own tolerance. **Held, first try**, to
   `1.14e-12`. Tested next on a numeric-`by` term (1 existing block,
   unconstrained, null dimension 2), a `ti()` term (2 existing blocks) and
   an `sz` term (2 existing blocks) — same rule, same precision, every
   time, with the null space taken of the blocks' UNSCALED SUM rather than
   any one block alone (confirmed as the actual mechanism, not a matching
   coincidence, by an R-free unit test with two synthetic blocks whose
   individual null spaces differ but whose sum has a known, smaller one).
   **No per-basis branch was ever needed in the implementation.**

3. **A data-dependent trap, caught by re-running the harness-first
   discipline.** The first version of the Stage-A comparison drew an
   independent Python covariate sample per case rather than sharing the R
   probe's own sample. The plain `cr`/`ti` cases (whose constraint absorbs
   `mgcv`'s data-dependent `colMeans(X)`) then disagreed by ~0.02-0.05,
   while the `by`/`sz` cases (whose constraints do not depend on the data)
   agreed exactly — a real signal that the FIRST measurement's harness, not
   the rule, was wrong. Fixed by echoing the R probe's own `x` (and
   `by_var`/`x2`/`group`/`n_levels`) back in its JSON and reading it on the
   Python side, the same shared-recipe convention `build_python_cr_term`'s
   own `x` argument already documents. All six cases then agreed at float
   round-trip precision.

4. **Stage B: does the doubled/increased block count assemble correctly,
   and does the fit agree?** Wired `ModelSpec.select: bool = False` and
   `assemble_model_design`'s per-term append (skipping a term whose
   existing blocks are already full rank, never padding a zero block).
   Verified the block-count arithmetic R-free first
   (`test_assemble_model_design_appends_one_null_space_block_per_term_under_select`:
   2+2+3=7 for the three-term shape, not 1 extra block per existing
   penalty). Then confirmed — at tier 1, before writing the R probe's
   `sp=` call — that `mgcv`'s own `$smooth` list under `select=TRUE`
   reports the SAME per-smooth block counts (`2, 2, 3`) in the SAME
   formula order `assemble_model_design` already uses, so the flat `sp=`
   vector both sides assume is the identical convention. Built
   `scripts/gam_select_multiterm_probe.R` (the same recipe shape as
   `gam_multiterm_probe.R`, `select=TRUE`, `sp` of length 7) and
   `gam_select_multiterm_conformance.py`. **Agreed on the first
   measurement**, `max_abs_eta_diff=6.164e-11` — no further hypotheses
   needed.

No hypothesis failed this session — every one held on the first or second
try, the same shape most of this epic's basis-level Stage-A/B pairs have had
once the underlying construction was actually independently correct (ADR-194,
ADR-200, ADR-205, ADR-215, ADR-216 all read the same way).

## What was built

- `src/polaris_re/analytics/gam_select_penalty.py` (new): `null_space_penalty`
  — the general rule above, taking a term's own already-verified penalty
  block(s) and returning `(S_null, null_dim)` or `None` (already full rank,
  nothing to add). `SELECT_PENALTY_CLAIM` (INDEPENDENT on `S_null`),
  `RSelectPenaltyCase`, `compare_null_space_penalty`.
- `src/polaris_re/analytics/gam_term_spec.py`: `ModelSpec.select: bool =
  False` (new field, default preserves every earlier slice's behaviour
  unchanged).
- `src/polaris_re/analytics/gam_model.py`:
  - `assemble_model_design` now appends each term's own null-space penalty
    (via `null_space_penalty`) when `model.select` is `True`, updating
    `TermBlock.n_penalties` accordingly — no new column, only a new penalty
    over each term's existing columns.
  - `fit_polaris_gam`'s at-bound guard split (hypothesis 1 above): new
    `strict: bool = False` parameter; `PolarisGAMFit` gained
    `at_bound_blocks: tuple[str, ...]` (which term labels sit at the upper
    bound) and `at_bound`'s own meaning narrowed to "at the upper bound"
    (the lower bound now always raises before a `PolarisGAMFit` is
    returned).
- `src/polaris_re/analytics/gam_select_multiterm_conformance.py` (new):
  the Stage-B comparison — the SAME three-term model ADR-206 verified
  (`s(AttdAge)` + `s(AttdAge,by=StudyYear_C)` + `ti(AttdAge,PolYear)`),
  now with `ModelSpec.select=True` (7 blocks), fit at a FIXED,
  externally-supplied `sp`. `SELECT_MULTITERM_CLAIM` (INDEPENDENT on `eta`),
  `fit_select_multiterm_case`, `compare_select_multiterm_case`.
- `scripts/gam_select_penalty_probe.R` (new): six cases (`cr-ref-attdage-k13`,
  `cr-ref-polyear-k6`, `cr-by-mi-attdage-k13`, `ti-attdage-polyear`,
  `sz-facesize-attdage-k13`, `sz-facesize-polyear-k6`), each reading
  `gam(..., select=TRUE, fit=FALSE)$smooth[[1]]$S`/`$rank` — no fit, exact
  for this purpose (module header explains why).
- `scripts/gam_select_multiterm_probe.R` (new): the same three-term recipe
  shape as `gam_multiterm_probe.R`, fit natively with `select=TRUE` and a
  7-entry fixed `sp`.
- `.github/workflows/mgcv-conformance.yml`: two new job-1 fit steps
  (`continue-on-error`, diagnostic) and two new job-2 compare steps (same
  contract as every Stage-A/B pair in this workflow — printed to stdout
  from the start, ADR-194's methodology fix, never gated into
  `REQUIRED_LEVELS`), plus path filters and artifact-list entries for the
  four new files. **Not yet dispatched this session** — see "What remains."
- Tests: `tests/test_analytics/test_gam_select_penalty.py` (R-free
  algebraic-invariant tests for `null_space_penalty` — a known-rank
  synthetic projector test, a multi-block-combination test, a full-rank
  `None` test, three guard tests — plus the R-gated end-to-end six-case
  parity test), `tests/test_analytics/test_gam_select_multiterm_conformance.py`
  (R-free structural tests plus the R-gated end-to-end parity test, same
  shape as `test_gam_multiterm_sz_conformance.py`), `tests/test_analytics/test_gam_model.py`
  (two new at-bound-guard tests, two new `select=True` block-count tests).

## Measurement

Tier 1 (local apt R 4.3.3 / mgcv 1.9.1), first measurement, both stages:

**Stage A** — `max_abs_s_null_diff` per case, `SELECT_PENALTY_CLAIM`:

| case | null dim | max abs S_null diff | agrees |
|---|---:|---:|---|
| `cr-ref-attdage-k13` | 1 | 2.554e-12 | True |
| `cr-ref-polyear-k6` | 1 | 9.825e-15 | True |
| `cr-by-mi-attdage-k13` | 2 | 1.716e-12 | True |
| `ti-attdage-polyear` | 1 | 8.936e-12 | True |
| `sz-facesize-attdage-k13` | 2 | 1.899e-12 | True |
| `sz-facesize-polyear-k6` | 2 | 2.712e-14 | True |

**Stage B** — `max_abs_eta_diff`, `SELECT_MULTITERM_CLAIM`:

| n | p | n blocks | max abs eta diff | agrees |
|---:|---:|---:|---:|---|
| 900 | 86 | 7 | 6.164e-11 | True |

Same order of magnitude as ADR-206's own first multi-term reading
(`1.242e-10`) and ADR-216's `sz` Stage-B reading (`3.9e-12`) — no iteration
needed on either stage.

**Tier 3: NOT dispatched this session.** The new `mgcv-conformance.yml`
steps are written and included in this PR, ready for `workflow_dispatch` on
this branch or the PR's own CI run, but no run has completed as of this log.
This is stated explicitly per `ROUTINE_MGCV_PARITY.md`'s own rule — every
number above is TIER 1 and must not be read as settled outside this session
log.

## Gap After

**Slice 7's Stage A and a fixed-`sp` Stage B are DONE at tier 1.** The
`select = TRUE` double penalty is confirmed to be one basis-agnostic rule —
not four per-basis constructions — and it composes correctly with the
production `assemble_model_design` path (not a separate Stage-A-only
module, unlike `sz`'s own first landing in ADR-215). This closes the
`select = TRUE` row of `CONTINUATION_mgcv_parity_engine.md`'s gap-audit
table from "Not started" to "Stage A+B DONE, tier 1 only."

**What remains, named rather than attempted:**

1. **Tier-3 confirmation** — this session's own open item (see above).
2. **Free-`sp` selection under `select=True`.** Every case measured this
   session uses a FIXED, externally-supplied `sp`. Extending
   `select_lambdas_continuous`/`fit_polaris_gam`'s own outer search to the
   doubled/increased block count `select=True` produces is what would let
   a caller reproduce PLAN §1's own headline figures (13 → 21 smoothing
   parameters, edf 47.36 → 16.96) — not attempted this session, and it is
   the largest piece of what is left in this epic. The three-term shape
   measured here goes from 4 blocks (ADR-199's own tested range) to 7 —
   inside slice 5e/5f's own measured N=4-N=8 robustness range, but
   `select_lambdas_continuous` has never actually been POINTED at a
   `select=True`-shaped design.
3. **Combining `select=True` with the target's full eight-term structure**,
   including more than one `sz` term.

## Provenance (ADR-193)

**Stage A claim sentence:** `gam_select_penalty.null_space_penalty` computes
`S_null` from a term's own already-independently-verified penalty block(s)
via NumPy's own eigendecomposition and `matrix_rank` tolerance; `mgcv`
computes it via `gam(formula, family, data, knots, select=TRUE,
fit=FALSE)$smooth[[i]]$S` (the last entry); compared on `S_null`, one case
per target-formula term archetype.

**Stage B claim sentence:** `gam_model.assemble_model_design(ModelSpec(...,
select=True))` assembles the three-term design (the already-INDEPENDENT
`cr`/`by`/`ti` producers, ADR-194/200/205) plus each term's own null-space
penalty from Stage A, fit with `gam_fit.penalized_irls_general` at a fixed,
externally-supplied `sp`; `mgcv` computes the identical model natively via
`gam(..., select=TRUE, sp=sp_fixed)`; compared on `eta`.

**Mechanical test applied to both producers' signatures:**
`null_space_penalty(s_blocks)` takes only Python-computed penalty blocks —
structurally cannot see an R payload. `fit_select_multiterm_case(r_case)`
is typed to `RSelectMultiTermRecipe`, which excludes `eta`/`coef` the same
way `RMultiTermRecipe`/`RSzMultiTermRecipe` already do
(`test_fit_select_multiterm_case_signature_takes_no_r_fit_output` checks
this at the type).

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `S_null` | `gam_select_penalty.null_space_penalty` | `mgcv gam(..., select=TRUE, fit=FALSE)$smooth[[i]]$S`, last entry | INDEPENDENT |
| `eta` (Stage B) | `gam_fit.penalized_irls_general` over `assemble_model_design(ModelSpec(..., select=True))` | `mgcv::predict(m, type='link')` on a native `select=TRUE` fit at the same fixed `sp` | INDEPENDENT |

Coefficients travel in the R payload for diagnostic reading only and are
never compared (Anchor 2).

## Oracle version

Tier 1: R 4.3.3 (2024-02-29) / mgcv 1.9-1 (local apt). **Tier 3: not
dispatched this session** — no digest or CI run to record yet.

## Quality gate

- `uv run ruff format src/ tests/` — reformatted 4 files on the first pass
  (new files, line-length wraps), 0 on the second (clean).
- `uv run ruff check src/ tests/ --fix` — 3 issues on the first pass (two
  `E501` line-too-long in docstrings, one `RUF043` unescaped regex
  metacharacter in a test's `pytest.raises(match=...)`), all fixed; clean
  on re-run.
- `uv run mypy` on the four touched/new modules
  (`gam_select_penalty.py`, `gam_select_multiterm_conformance.py`,
  `gam_model.py`, `gam_term_spec.py`) — one real error caught (a
  `dict[str, object]` parameter type that could not be iterated; fixed
  with a proper `RSelectPenaltyCase` TypedDict rather than a `# type:
  ignore`) — clean after the fix. Full-repo mypy is CI's own job per the
  routine; not chased beyond the touched files.
- `OPENBLAS_NUM_THREADS=1 uv run pytest tests/test_analytics/test_gam_select_penalty.py
  tests/test_analytics/test_gam_select_multiterm_conformance.py
  tests/test_analytics/test_gam_model.py tests/test_analytics/test_gam_model_conformance.py
  tests/test_analytics/test_gam_multiterm_conformance.py
  tests/test_analytics/test_gam_multiterm_sz_conformance.py
  tests/test_analytics/test_gam_term_spec.py` — 74 passed, including every
  R-gated end-to-end parity test touched or added this session.
- `uv run pytest tests/qa/ -q` — 85 passed, 9 skipped (the same
  mortality-table-dependent goldens the baseline already skipped) — no
  regression; this session's changes are new epic-only surface
  (`gam_model.py`/`gam_term_spec.py`/two new modules), not called from
  `experience_gam_penalized` or the CLI.
- Required conformance levels re-run at tier 1 (`scripts/mgcv_conformance.R`
  + `compare_mgcv_conformance.py`): **levels 1/2/3/5 AGREE, level 4
  DISAGREES** — the same standing, permanent state
  `ROUTINE_MGCV_PARITY.md` documents (ADR-190's separate `dw/drho` gap).
  No regression from this session's changes.
- Full suite, `OPENBLAS_NUM_THREADS=1 uv run pytest tests/ -m "not slow"`
  (R installed): **3533 passed, 5 failed (the same pre-existing
  mortality-table environment gap named in the baseline above, unrelated to
  this epic), 22 skipped, 126 deselected.** No new failure beyond the 5
  pre-existing ones — every new/changed test in the targeted 74-test
  re-run above passed as part of this same run.

## Definition of done (PLAN slice 7's own acceptance, per ADR-209 decision 3)

The PLAN's slice 7 entry (before this session) named no acceptance
criteria beyond the double-penalty description itself and the at-bound
collision — this session's own Status update states what was actually
delivered, tagged here:

- `[machine]` **The at-bound-guard collision is fixed, per the reviewer's
  own suggested shape.** →
  `test_fit_polaris_gam_reports_rather_than_raises_at_the_upper_bound`,
  `test_fit_polaris_gam_strict_raises_at_the_upper_bound_too`
  (`tests/test_analytics/test_gam_model.py`), both PASSED.
- `[machine]` **`select=TRUE`'s null-space penalty is INDEPENDENT Stage-A
  parity evidence, one rule, all four term archetypes.** →
  `test_the_r_probe_runs_end_to_end_and_agrees`
  (`tests/test_analytics/test_gam_select_penalty.py`), tier 1 PASSED, six
  cases, `SELECT_PENALTY_CLAIM` gated by `require_parity_evidence`
  (`test_select_penalty_claim_is_independent`). **NOT MET at tier 3** —
  not yet dispatched this session.
- `[machine]` **A `select=TRUE` multi-term fit is INDEPENDENT Stage-B
  parity evidence on `eta`, at a fixed `sp`.** →
  `test_the_r_probe_runs_end_to_end_and_agrees`
  (`tests/test_analytics/test_gam_select_multiterm_conformance.py`), tier
  1 PASSED, `max_abs_eta_diff=6.164e-11`, `SELECT_MULTITERM_CLAIM` gated
  (`test_select_multiterm_claim_is_independent_on_every_declared_quantity`).
  **NOT MET at tier 3** — not yet dispatched this session.
- `[machine]` **The null-space rule is verified as combining blocks BEFORE
  taking the null space, not per-block** — the actual mechanism, not a
  coincidence. →
  `test_null_space_penalty_combines_several_blocks_before_the_null_space`
  (R-free, synthetic, known answer), PASSED.
- `[machine]` **Nothing is re-pointed; every earlier slice's behaviour is
  unchanged when `select=False` (the default).** →
  `test_assemble_model_design_ignores_select_by_default`, plus every
  pre-existing test in `test_gam_model.py`/`test_gam_multiterm_conformance.py`/
  `test_gam_multiterm_sz_conformance.py`/`test_gam_model_conformance.py`
  passing unchanged (74/74 across the touched-module re-run above).
  `tests/qa/` byte-identical.
- `[judgement]` **Free-`sp` selection under `select=True` is out of this
  session's scope, and is named rather than silently skipped.** → this
  log's "What remains" section, `gam_select_penalty.py`'s and
  `gam_select_multiterm_conformance.py`'s own module docstrings, PLAN
  slice 7's updated entry.

## Follow-ups filed

- **This session's own open item, not a future session's**: dispatch
  `mgcv-conformance.yml` on this PR (or via `workflow_dispatch`) before
  merge, and confirm both Stage-A and Stage-B tier-1 figures at tier 3 —
  per `ROUTINE_MGCV_PARITY.md`'s "run it if it is under an hour" (a CI
  round trip on the pinned digest costs about a minute).
- **Named, not yet a registered slice** (below the ADR-209 decision-1 bar
  for a session-blocking gap, per this session's own judgement — a future
  session should register as slice 7b if it becomes the epic's next
  unchecked work): extending `select_lambdas_continuous` to a
  `select=True`-shaped block structure, and a full eight-term
  `select=True` model including more than one `sz` term.

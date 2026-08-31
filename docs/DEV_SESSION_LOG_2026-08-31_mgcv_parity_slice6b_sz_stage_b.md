# Session log — 2026-08-31 — Slice 6b: `sz` Stage B, the first sz-carrying multi-term fit

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 6b — `docs/PLAN_mgcv_parity_engine.md`. READY since ADR-215 (slice 6's
Stage A closed the same day); the routine's "next unchecked slice, no fallback
picks" rule selected it.
**PR:** `claude/intelligent-hamilton-srcegv` (branch, this session continues the
epic's shared working branch).
**ADR:** ADR-216.

## Setup

- `uv sync --all-extras` — clean (4 new packages: `statsmodels`, `patsy`,
  `openpyxl`, `et-xmlfile`).
- Installed the local scratch oracle (tier 1): `apt-get update` then
  `apt-get install -y -qq r-base-core r-cran-mgcv r-cran-jsonlite` — the
  first attempt failed on stale package-index 404s (the same recurring
  transient prior sessions record), `apt-get update` fixed it. Versions
  recorded: **R 4.3.3 (2024-02-29) / mgcv 1.9-1** — matches the routine's
  expected apt versions, no drift to flag.
- Read `docs/PLAN_mgcv_parity_engine.md` (slice 6/6b, Anchors 1, 2, 3, 8),
  the CONTINUATION status block through ADR-215, `docs/CONFORMANCE_LEDGER.md`,
  CLAUDE.md, and `docs/DEV_SESSION_LOG_2026-08-31_mgcv_parity_slice6_sz_basis.md`
  (the immediately-prior session, which registered this slice).

## `make test` baseline

`OPENBLAS_NUM_THREADS=1 uv run pytest tests/ -q -m "not slow"` after
generating the mortality tables (`scripts/convert_soa_tables.py`, a one-time
per-environment step, CLAUDE.md §11): **3529 passed, 3 skipped** — clean,
nothing pre-existing to account for. (Without `OPENBLAS_NUM_THREADS=1`,
`test_gam_model_conformance.py::test_the_r_probe_runs_end_to_end` fails
non-deterministically — the documented ADR-211/213 BLAS-thread sensitivity
of `select_lambdas_continuous`'s single-start default, not a regression;
confirmed by re-running that one test with the pin set, which passes.)
Match — proceed, per the routine's own baseline rule.

## Gap Before

**No Python producer for an `sz`-carrying multi-term model existed.**
`gam_model.assemble_model_design` raised on `basis="sz"` (`"'sz' is slice 6
... "` — the ADR-208-era message). PLAN's own gap-audit table (in
`CONTINUATION_mgcv_parity_engine.md`) read `bs = "sz"`: **Stage A DONE
(ADR-215) — Stage B (slice 6b) — a multi-term fit including an sz term —
remains.** The claim sentence could not be filled in for a two-term
`cr`+`sz` model at all — there was no left-hand producer to name.

**Tier and digest:** N/A — no prior measurement exists to state a "before"
number for.

## What was built

The same pattern ADR-206 used for `ti`/numeric-`by` (slice 5's remaining
scope), applied to `sz`:

- `src/polaris_re/analytics/gam_term_spec.py`: `TermSpec.n_levels` (new,
  optional field) — the factor-level count for a `basis="sz"` term, an
  *input* (Anchor 4), never derived from a sample's own observed group
  codes. Validated: must be `>= 2` when set on an `sz` term, and must be
  `None` on any other basis. Deliberately optional even for `sz`:
  `build_python_sz_term`'s own narrower Stage-A harness (ADR-215) takes
  `n_levels` as its own explicit function argument and does not read the
  spec — only the `ModelSpec`-driven multi-term path
  (`gam_model.assemble_model_design`) requires it set, and raises loudly if
  it is not.
- `src/polaris_re/analytics/gam_model.py`: `_build_term_extract` now
  dispatches `basis="sz"` to `build_python_sz_term` (reading the factor's
  0-indexed level codes from `data[term.variables[0]]` and the smoothed
  margin from `data[term.variables[1]]`, `TermSpec`'s own documented
  variable order) — the third and (for this epic's target formula) final
  basis `assemble_model_design` needed to wire, alongside `cr` and `ti`.
- `src/polaris_re/analytics/gam_multiterm_sz_conformance.py` (new): the
  Stage-B comparison itself, `MULTITERM_CLAIM`-shaped. Model:
  `y ~ s(AttdAge,k=13,bs="cr") + s(FaceSize,AttdAge,k=13,bs="sz",
  xt=list(bs="cr"))`, binomial/cloglog, `ExposCnt` weights (Anchor 5,
  absolute idiom) — the target formula's own first `sz` term verbatim
  (PLAN Section 1), at its own `AttdAge` k=13 knot vector (the same knots
  ADR-215's "sz-target-attdage-k13" Stage-A case already used). Fit at a
  FIXED, externally-supplied `sp` (1 reference block + 2 sz-factor-level
  blocks = 3), never selecting its own lambda (out of this slice's scope —
  see "What remains" below).
- `scripts/gam_multiterm_sz_probe.R` (new): builds the shared recipe
  (`AttdAge`, `FaceSize`'s 0-indexed level code, `ExposCnt`, `y`, the
  reference term's knot vector, `sp`) deterministically (`set.seed`,
  ADR-074) and fits the identical formula natively via `mgcv::gam(...,
  sp=sp_fixed)`.
- `.github/workflows/mgcv-conformance.yml`: a job-1 fit step (`continue-on-error`,
  diagnostic) and a job-2 compare step (same contract as the slice 5/5b
  Stage-B sections — printed to stdout from the start, ADR-194's
  methodology fix, never gated into `REQUIRED_LEVELS`), plus path filters
  and artifact-list entries for the new files.
- Tests: `tests/test_analytics/test_gam_term_spec.py` (`n_levels`
  validation), `tests/test_analytics/test_gam_model.py` (`sz` dispatch:
  block widths/spans, the "one penalty block per factor level, same shared
  span" shape, the `n_levels=None` guard, and the now-actually-unbuilt-basis
  case moved to `basis="raw"` since `sz` is no longer unbuilt),
  `tests/test_analytics/test_gam_multiterm_sz_conformance.py` (R-free
  structural tests plus the R-gated end-to-end parity test, same shape as
  `test_gam_multiterm_conformance.py`).

## Measurement

Tier 1 (local apt R 4.3.3 / mgcv 1.9.1), first measurement:

| n | p | max abs eta diff | agrees |
|---:|---:|---:|---|
| 700 | 26 | 3.921e-12 | True |

Same order of magnitude as ADR-206's own first multi-term measurement
(1.242e-10) and tighter — no iteration needed, the same shape ADR-206 and
ADR-215 both had.

**Tier 3: CONFIRMED, same session.** Dispatched `mgcv-conformance.yml` on
this branch (CI run
[33393744694](https://github.com/jonathancrawford05/polaris-re/actions/runs/33393744694),
oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
— build 8, the same digest this epic has used throughout — R 4.6.1 / mgcv
1.9.4):

| tier | n | p | max abs eta diff | agrees |
|---|---:|---:|---:|---|
| 1 | 700 | 26 | 3.921e-12 | True |
| 3 | 700 | 26 | 3.912e-12 | True |

Both tiers agree to the same order of magnitude. Both jobs (`mgcv reference
(R)`, `Compare against the Python reference`) completed successfully;
required conformance levels 1-3 show no regression (the gate step fails the
job outright on a levels-1-3 regression, so the green job is itself the
evidence).

## Gap After

**Stage B closed for the scope this slice named**: an `sz`-carrying
multi-term model can be assembled and fit by `gam_model.assemble_model_design`
+ `gam_fit.penalized_irls_general`, and its `eta` agrees with `mgcv`'s own
native fit of the identical formula to float round-trip precision (tier 1;
tier 3 pending). `SZ_MULTITERM_CLAIM` declares `eta` `INDEPENDENT`.

**What remains, named but not attempted (PLAN slice 6b's own scope line):**
extending `select_lambdas_continuous` to an `sz`-shaped block structure (one
smoothing parameter per factor level) — this slice fits at a fixed,
externally-supplied `sp` only. Also unexercised: a model with more than one
`sz` term, or an `sz` term sharing covariates with a `ti`/`by` term the way
the target formula's own four `sz` terms plus the MI/`ti` terms do together
— this slice's model is deliberately the minimal `cr`+`sz` pair, the same
"prove the smallest new shape first" discipline ADR-206 used for `ti`/`by`.

## Provenance (ADR-193)

**Claim sentence:** `gam_multiterm_sz_conformance.fit_sz_multiterm_case`
computes `eta` by assembling a two-term design (`s(AttdAge,k=13,bs="cr")` +
`s(FaceSize,AttdAge,k=13,bs="sz",xt=list(bs="cr"))`) from
`gam_model.assemble_model_design` (via `gam_basis_cr.cr_basis` and
`gam_basis_cr.sz_basis`, ADR-194/ADR-215) and fitting with
`gam_fit.penalized_irls_general` at a FIXED, externally-supplied `sp` per
block; `mgcv` computes the identical two-term model natively via
`gam(y ~ s(AttdAge,k=13,bs="cr") + s(FaceSize,AttdAge,k=13,bs="sz",
xt=list(bs="cr")), family=binomial(link="cloglog"), weights=ExposCnt,
sp=sp_fixed)`; compared on `eta` at the training design.

**Mechanical test applied to `fit_sz_multiterm_case`'s signature**: it takes
only `r_case: RSzMultiTermRecipe`, which structurally excludes `eta`/`coef`
(`RSzMultiTermPayload` is the wider type that adds them, read only by
`compare_sz_multiterm_case`). Passes —
`test_fit_sz_multiterm_case_signature_takes_no_r_fit_output` checks this at
the type, not merely by convention.

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `eta` | `gam_fit.penalized_irls_general` over a design from `gam_model.assemble_model_design`'s independently-verified `cr`/`sz` producers | `mgcv::predict(m, type='link')` on a native `gam()` fit of the identical formula at the same fixed `sp` | INDEPENDENT |

Coefficients are read from the R payload for diagnostic purposes only and
are never compared (Anchor 2) — `SZ_MULTITERM_CLAIM` does not name `coef`.

**This is real parity evidence**, the same class of result ADR-206
established for `ti`/`by`: two distinct implementations from the same
recipe, agreeing at float round-trip precision on the first measurement. A
disagreement would have been an equally legitimate, reportable result (the
routine's own "an INDEPENDENT comparison that disagrees is a success").

## Oracle version

Tier 1: R 4.3.3 (2024-02-29) / mgcv 1.9-1 (local apt).
Tier 3: R 4.6.1 (2026-06-24) / mgcv 1.9.4, oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
(build 8), CI run
[33393744694](https://github.com/jonathancrawford05/polaris-re/actions/runs/33393744694).

## Quality gate

- `uv run ruff format src/ tests/` — 329 files unchanged (no reformatting
  needed).
- `uv run ruff check src/ tests/ --fix` — all checks passed.
- `OPENBLAS_NUM_THREADS=1 uv run pytest tests/ -q -m "not slow"`: 3538
  passed (+9 over baseline, exactly the new tests added), 3 skipped — no
  regression.
- `uv run pytest tests/qa/ -q`: 94 passed — golden outputs byte-identical
  (no production path touched; `assemble_model_design`/`TermSpec` are new
  epic-only surface, not called from `experience_gam_penalized` or the CLI).
- Conformance run again (targeted): `tests/test_analytics/test_gam_term_spec.py
  tests/test_analytics/test_gam_model.py
  tests/test_analytics/test_gam_multiterm_sz_conformance.py
  tests/test_analytics/test_gam_multiterm_conformance.py
  tests/test_analytics/test_gam_model_conformance.py` — 55 passed, including
  the R-gated end-to-end parity tests for both this slice and slice 5.
- `uv run python scripts/perf_history.py`: run once on this PR's initial
  open (ADR-177). No structural creep (`has_structural_creep: false`, peak
  MiB 33 → 33). Wall-time ratio advisory only, never gates.

## Definition of done (PLAN slice 6b's own acceptance, reproduced per ADR-209 decision 3)

- `[machine]` **An INDEPENDENT `eta` comparison (ADR-206's own pattern) on a
  multi-term model containing at least one `sz` term, agreeing to a
  derived — not tuned — tolerance.** →
  `test_the_r_probe_runs_end_to_end_and_agrees`
  (`tests/test_analytics/test_gam_multiterm_sz_conformance.py`), tier 1
  PASSED (`max_abs_eta_diff=3.921e-12` against `_AGREEMENT_TOLERANCE=1e-9`,
  the same order ADR-206's `MULTITERM_CLAIM` used, derived from the
  existing verified fixed-sp regime, not chosen to make this check green).
  Tier 3: CONFIRMED, CI run 33393744694, `max_abs_eta_diff=3.912e-12`.
- `[machine]` **Every claimed quantity declared `INDEPENDENT` in the type,
  gated by `require_parity_evidence`.** → `SZ_MULTITERM_CLAIM`,
  `test_sz_multiterm_claim_is_independent_on_every_declared_quantity`.
- `[machine]` **Not blocking slice 7** (PLAN slice 6b's own acceptance
  line). → no change to slice 7's own PLAN entry or its own known
  at-bound-guard collision (unrelated to this slice's scope).
- `[judgement]` **Extending `select_lambdas_continuous` to an `sz`-shaped
  block structure is out of this slice's scope, and is named rather than
  silently skipped.** → module docstring's "Not in scope here" paragraph,
  this log's "What remains" section.

## Follow-ups filed

- **Named, not yet a registered slice**: extending
  `select_lambdas_continuous` (free-`sp` selection) to an `sz`-shaped
  block structure (one smoothing parameter per factor level) — carried
  over from slice 6's own session log, still open after 6b. Left for a
  future session to register as a slice if it becomes the epic's next
  unchecked work, per ADR-209 decision 1's "closed or registered" rule.
- **Named, not yet a registered slice**: a multi-term model combining an
  `sz` term with a `ti`/numeric-`by` term (the target formula's own actual
  shape — all eight terms together), and models with more than one `sz`
  term (the target has four). This slice deliberately proved the minimal
  new pairing first.

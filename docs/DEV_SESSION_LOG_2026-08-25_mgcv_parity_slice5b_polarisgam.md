# Session log — 2026-08-25 — Slice 5b: `PolarisGAM` from a `ModelSpec`

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 5b — `docs/WORK_ORDER_multi_term_assembly.md`, registered as PLAN slice
5b by the immediately-prior session (`ff1cf58`, merged as PR #211). The routine's
"next unchecked slice" rule selected it.
**PR:** (this branch, `claude/intelligent-hamilton-u7hpca`), draft.
**ADR:** ADR-208.

## Setup

- `uv sync --all-extras` — clean (4 packages resolved for `--all-extras`,
  `statsmodels` re-downloaded).
- Installed the local scratch oracle: `r-base-core r-cran-mgcv r-cran-jsonlite`.
  `apt-get install` failed on stale package-index 404s first, exactly the same
  transient the 2026-08-24 session's log recorded; `apt-get update -qq` fixed it
  (two PPA `InRelease` fetches still failed — `deadsnakes`/`ondrej-php`, both
  irrelevant to R — with index files falling back to cached copies, no effect on
  the R install). Versions recorded: **R 4.3.3 / mgcv 1.9.1** — matches the
  routine's expected apt versions exactly, no drift to flag.
- `OPENBLAS_NUM_THREADS=1` exported for every R invocation.
- `uv run pytest tests/ -m "not slow"` baseline (before any code change): **3434
  passed, 22 skipped, 126 deselected, 5 failed** — the 5 failures were
  `FileNotFoundError` on `data/mortality_tables/*.csv`, the same recurring
  environment-setup gap prior sessions' logs have already named (generated
  files, not committed). Regenerated via
  `uv run python scripts/convert_soa_tables.py --source pymort --output-dir
  data/mortality_tables` (cheap, unrelated to this epic, removes noise from the
  baseline) — re-run clean: **3472 passed, 3 skipped, 126 deselected, 0
  failed**, after this session's code landed (see Quality Gate below for the
  identical re-run confirming no regression).
- The main branch had just received PR #211 (registering slice 5b in the PLAN)
  moments before this session started — `git fetch` showed this session's
  designated branch already equal to `origin/main` at `7f2195e`, so no rebase
  or branch-reset was needed.

## Gap Before

`PolarisGAM` did not exist: `test -f src/polaris_re/analytics/gam_model.py`
failed. Per the work order §1: "This is not a criticism of ADR-206... the work
here is to re-drive verified code from a different input, not to write new
numerics" — the gap was exactly what the work order named, no more and no less.

Ran the ten-cell conformance suite at tier 1 before changing anything:

```
level 1: AGREES     level 2: AGREES     level 3: AGREES
level 4: DISAGREES  level 5: AGREES
```

Matches `docs/CONFORMANCE_LEDGER.md`'s last-recorded state (no drift): `l2-free-sp`
`max_abs_log10_sp_diff` 6.4525e-02, `rel_unconditional_inflation_diff` -3.2209e-01
(FAIL, the known ADR-190 blocker, out of this session's scope). `l5-gamma` both
metrics PASS.

## Provenance gate (ADR-193), applied before writing code

**Claim sentence:** `PolarisGAM` (`gam_model.fit_polaris_gam`) assembles the
three-term design from the shared recipe via the already-independently-verified
`cr`/`by`/`ti` basis producers, then selects its own `log10(lambda)` per block by
minimizing `gam_reml.reml_score_general` via `select_lambdas_continuous`, and
fits with `penalized_irls_general` — never reading `mgcv`'s own `eta`, `coef`,
`sp` or `edf`; `mgcv` computes the identical three-term formula via
`gam(..., method="REML")` with free `sp`, selecting its own smoothing parameters
independently; compared on `eta`, `log10(sp)` per block, `edf_total` and
per-term `edf`.

**The mechanical test, applied to the signature:** `fit_free_sp_case`'s only
parameter is `RFreeSpRecipe`, a `TypedDict` with no `eta`/`coef`/`sp`/
`edf_total`/`term_edf` key — asserted by
`test_fit_free_sp_case_signature_takes_no_r_fit_output`.

**The asymmetry (work order §3), stated in the type:** ADR-206's
`RMultiTermRecipe` carries `sp` as a shared input (both sides fit at the same
externally-supplied value). `RFreeSpRecipe` has no `sp` key at all — there is
nothing to share; `mgcv`'s own `sp` is read only by `compare_free_sp_case`
(via the wider `RFreeSpPayload`), never by the producer.

**Classification:** every one of the four declared quantities (`eta`,
`log10(sp)` per block, `edf_total`, per-term `edf`) is **INDEPENDENT** —
`FREE_SP_MODEL_CLAIM`, gated by `require_parity_evidence`
(`test_free_sp_model_claim_is_independent_on_every_declared_quantity`).

## What was built

1. **Extracted the shared assembly** (work order step 1):
   `gam_model.assemble_model_design(model: ModelSpec, data)` generalises
   `gam_multiterm_conformance.assemble_multiterm_design`'s column/penalty-padding
   arithmetic from exactly three hardcoded terms to any `ModelSpec` built from
   `"cr"` (with or without numeric `by`) and `"ti"` terms — raises on any other
   basis rather than silently skipping it. `assemble_multiterm_design` is now a
   thin `RMultiTermRecipe`-shaped adapter onto this function.
   **Check that the extraction was behaviour-preserving:**
   `tests/test_analytics/test_gam_multiterm_conformance.py` — ADR-206's own
   tests, unmodified — pass unchanged against the refactor (5/5, R-free
   subset; the R-gated 6th also ran and agreed since R is present this
   session).
2. **`PolarisGAM` from `ModelSpec`** (work order step 2):
   `gam_model.fit_polaris_gam(model, data, y)` — composes
   `select_lambdas_continuous` (λ), `penalized_irls_general` (the fit, called
   internally by the search) and a new `_per_term_edf` helper (the same
   hat-matrix-diagonal identity `experience_gam_penalized`'s own
   `edf_tensor`/`edf_factors` split already uses, generalised to any number of
   named terms). R-free tests (`tests/test_analytics/test_gam_model.py`, 8
   tests): block widths sum to `p` (86, ADR-206's own arithmetic), penalty
   blocks land only in their own term's span, a `by` term is unconstrained
   where a plain `cr` term is constrained (ADR-200), `ti`'s two penalty blocks
   share one span (ADR-205 decision 2), an unbuilt basis (`"sz"`) is rejected
   rather than silently skipped, and a full small fit converges and returns a
   `PolarisGAMFit` with the expected per-term keys.
3. **Free-`sp` conformance** (work order step 3): `gam_model_conformance.py`
   (`FREE_SP_MODEL_CLAIM`, `fit_free_sp_case`, `compare_free_sp_case`) and
   `scripts/gam_multiterm_free_sp_probe.R` (the identical three-term formula,
   `method="REML"`, no `sp=` supplied, seed `20260825` — distinct from
   `gam_multiterm_probe.R`'s `20260824`, a genuinely new draw). Wired into
   `.github/workflows/mgcv-conformance.yml`: a new R fit step (job 1) and a
   new comparison step (job 2), same `continue-on-error: true` /
   print-to-stdout contract every probe since ADR-194 has used.

## Tier-1 measurement (R 4.3.3 / mgcv 1.9.1, local apt)

```
max_abs_eta_diff        3.677e-02
max_abs_log10_sp_diff   0.7766   (block 2, the by-term)
edf_total_diff          +0.7263  (Python 17.16 vs mgcv 16.44)
max_abs_term_edf_diff   0.7054
converged (both sides)  True / True
at_bound                False
```

Python `log10(sp) = [6.753, 9.096, 3.099, 3.054]`;
mgcv `log10(sp) = [6.696, 9.872, 3.292, 3.029]`.

## The registered prediction (work order §4) — REFUTED

> "the prediction is that N=4 lands in the same range \[as ADR-199's 2-block
> 6.9e-04-to-9.8e-04]."

It does not. `max_abs_log10_sp_diff=0.7766` is three orders of magnitude
larger, concentrated in one block. Per the work order's own alternative:
*"the 2-block result was narrower than it appeared — the search may scale
differently with block count — and that is the finding."*

## Hypotheses tried

1. **Hypothesis:** the disagreement is a criterion gap re-opening (a formula
   difference at N=4 that ADR-196/197's N=2/fixed-sp verification did not
   catch).
   **The one change:** none — a diagnostic-only evaluation of the already
   tier-3-verified `reml_score_general` at both sides' own selected
   `log10(sp)`, on the identical shared design (not part of the committed
   comparator; this reads `mgcv`'s own `sp`, which would violate the
   mechanical test if it were).
   **Result:** Python's own (mgcv-independent) optimum scores **611.892**;
   `mgcv`'s own exact selection scores **612.618** under the SAME criterion —
   worse. If the criterion itself disagreed with `mgcv`'s, `mgcv`'s own
   selection would be expected to score at least as well under its own
   criterion; it does not, under ours.
   **Verdict:** REFUTED — not a criterion gap.

2. **Hypothesis:** the search converges to a genuinely different local optimum
   depending on starting point (a flat or multi-modal REML surface), rather
   than there being one basin `mgcv`'s optimizer path happens to reach and
   ours does not.
   **The one change:** re-ran `select_lambdas_continuous` with `x0` set to
   `mgcv`'s own selected `log10(sp)` (diagnostic-only, same reason as above —
   not how the committed `fit_free_sp_case` is called, since seeding from
   `mgcv`'s output would make the Python side read the R side's, breaking
   independence).
   **Result:** converges to `[6.683, 9.820, 2.860, 3.059]`, score **612.155**
   — closer to `mgcv`'s point on the by-term block (log10 diff 0.052, not
   0.777) but a DIFFERENT point from both the neutral-start optimum and
   `mgcv`'s own exact selection, and still scoring lower than `mgcv`'s exact
   point under the shared criterion.
   **Verdict:** CONFIRMED — the REML surface is flat enough along this
   direction that different starting points land on different, all
   comparably-scoring points. This is PLAN §5 risk 3 ("the 21-dimensional
   optimiser may be badly conditioned where the 2-D grid was merely shallow"),
   measured at N=4 rather than merely anticipated.

Two passes were enough to localize the finding to convergence behaviour on a
flat criterion surface rather than a formula defect — the routine's "three
passes without movement" ceiling was not reached because the second pass
already isolated the mechanism.

## PLAN §6's separate registered prediction — CONFIRMED again

*"The optimiser does not land on `mgcv`'s `sp`, but `edf` agrees far better
than `sp` does."* `edf_total_diff` (0.726 out of ~16-17, ≈4%) is far tighter
than `max_abs_log10_sp_diff` (0.777, nearly a full decade) — the same pattern
ADR-199 already found at N=2, now confirmed at N=4.

## Why the search bounds were widened (not Anchor-8 tuning)

`mgcv`'s own selection reaches `log10(sp) ≈ 9.87` on the by-term, outside
`gam_reml_optimize.DEFAULT_LOG10_BOUNDS`'s `(-2, 8)`. Measured before the
comparator's bounds were set, not guessed.
`gam_model_conformance._SEARCH_BOUNDS = (-2, 11)` widens the SEARCH DOMAIN so
the optimiser can reach the region `mgcv` itself selects in — no comparison
threshold moved, and `at_bound` (still reported) reads `False`, so the widened
bound was not itself binding on this measurement.

## Provenance

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `eta` | `gam_model.fit_polaris_gam` at its own selected `log_lambda` | `mgcv gam(method='REML')` free-sp fit, `predict(type='link')` | INDEPENDENT |
| `log10(sp)` per block | `select_lambdas_continuous`'s own `log_lambda` | `mgcv`'s own `log10(m$sp)` at its free-sp REML selection | INDEPENDENT |
| `edf_total` | `PolarisGAMFit.edf_total` | `mgcv`'s own `sum(m$edf)` | INDEPENDENT |
| per-term `edf` | `PolarisGAMFit.edf_per_term` (hat-diagonal per span) | `mgcv`'s own `summary(m)$s.table[, 'edf']`, read positionally | INDEPENDENT |

No ECHO or TRANSPORT quantity in this comparison — `RFreeSpRecipe` carries no
`mgcv`-computed value of any kind (unlike `RMultiTermRecipe`'s `sp`), so there
was nothing for either side to merely echo or transport this time.

## Oracle version

Tier 1: R 4.3.3 / mgcv 1.9.1 (local apt). Tier 3: R 4.6.1 / mgcv 1.9.4, oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
(build 8), CI `workflow_dispatch` on `c7c5ac6`, run
[32855338611](https://github.com/jonathancrawford05/polaris-re/actions/runs/32855338611)
— R job ~43s, compare job ~40s.

## Tier-3 confirmation

Read directly from job-log stdout via `get_job_logs` (both steps print their
report from the start, no masked step-conclusion reads):

| quantity | tier 1 | tier 3 |
|---|---:|---:|
| `max_abs_eta_diff` | 3.677e-02 | 3.775e-02 |
| `max_abs_log10_sp_diff` | 0.7766 | 0.6398 |
| `edf_total_diff` | +0.7263 | +1.1482 |
| `max_abs_term_edf_diff` | 0.7054 | 0.8776 |
| `at_bound` | False | False |
| `agrees` | False | False |

**Identical in verdict, same order of magnitude on every metric** — the
tier-to-tier differences are consistent with the different `mgcv` release
(1.9.1 vs 1.9.4) / BLAS the routine's own tier discipline predicts, not a
new finding. Required levels 1-3 of the ten-cell suite also agreed on this
run (`level 1: AGREES`, `level 2: AGREES`, `level 3: AGREES` — no
regression); level 4 still `DISAGREES` (ADR-190's separate, unaffected
`dw/drho` gap) and level 5 still `AGREES`. The work order's §4 registered
prediction is REFUTED at both tiers, not a tier-1 artefact.

## Quality Gate

- `uv run ruff format src/ tests/` — 3 files reformatted (line wrapping only,
  no semantic change; confirmed via the harness's own diff-on-disk notices).
- `uv run ruff check src/ tests/ --fix` — 4 findings (two `E501` long
  docstring lines, two `RUF043` ambiguous regex `match=` patterns in new
  tests), all fixed; re-run clean.
- `uv run pytest tests/ -m "not slow"` — **3472 passed, 3 skipped, 126
  deselected, 0 failed** (up from the 3434-passed-plus-5-mortality-failures
  baseline: +38 from this session's new tests plus the mortality-table
  regeneration, 0 regressions).
- `uv run pytest tests/qa/` — **94 passed**, 0 failed. `tests/qa/golden_outputs/`
  untouched by this session's diff (confirmed via `git status` — no file under
  that path appears).
- Ten-cell conformance suite, re-run after the code landed:
  ```
  level 1: AGREES     level 2: AGREES     level 3: AGREES
  level 4: DISAGREES  level 5: AGREES
  ```
  Identical to Gap Before — no regression from this session's workflow or
  module edits. `l2-free-sp` `rel_unconditional_inflation_diff` FAIL is the
  known, unaffected ADR-190 blocker (out of scope, Anchor 7).

## Follow-ups filed

- Whether a more robust search strategy (multi-start from several
  mgcv-independent points, informed initialisation) would narrow the free-sp
  N=4 disagreement is open. `select_lambdas_continuous` was reused unchanged
  per the work order's own scope ("if this work starts producing new
  numerics, stop") — evaluating a different search strategy is new numerics
  and is 2nd-order follow-on work, not required by this slice's definition of
  done.
- Anchor 2's primary MI-contrast-on-a-grid metric remains unmeasured (named by
  ADR-206, unaffected by this slice).
- `bs = "sz"` (slice 6) and `select = TRUE` (slice 7) remain unbuilt.

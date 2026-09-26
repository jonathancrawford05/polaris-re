# Dev session log — 2026-09-21 — mgcv capability ladder slice 2 (`bs="re"`)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Epic:** `docs/PLAN_mgcv_capability_ladder.md` / `docs/CONTINUATION_mgcv_capability_ladder.md` (ACTIVE)
**Slice:** 2 — L2 `bs="re"`
**ADR:** ADR-230
**PR:** (draft, this branch — `claude/intelligent-hamilton-7yeu7m`)

---

## Setup

`uv sync --all-extras` — clean. Installed the tier-1 scratch oracle via apt
(idempotent check first; none was present in this environment):

```
R version 4.3.3 (2024-02-29)
mgcv 1.9.1
```

Matches `ROUTINE_MGCV_PARITY.md`'s expectation exactly (R 4.3.3 / mgcv 1.9.1
from apt).

Baseline `make test`-equivalent (`uv run pytest tests/ -q -m "not slow"`):
`3672 passed, 5 failed, 22 skipped` before any change. The 5 failures are
pre-existing and environmental — `test_loaded_ilec_feeds_tensor_mi_surface`
(missing `data/mortality_tables/*.csv`, generated, not committed — CLAUDE.md
§11) and four `TestCalibratedPremiums` failures in `test_synthetic_block.py`
unrelated to this session's scope. Confirmed unrelated: none of the four
touch `analytics/gam_*`, `TermSpec`, or `assemble_model_design`. Mortality
tables were then generated
(`uv run python scripts/convert_soa_tables.py --source pymort --output-dir
data/mortality_tables`) as ordinary environment setup; the four
`TestCalibratedPremiums` failures are untouched by this session and out of
its scope (not `gam`/GAM-adjacent).

With R installed, `test_the_r_script_runs_end_to_end_and_agrees` (and its
siblings across `test_gam_*_conformance.py`) flip from SKIPPED to PASSED, per
the routine's own documented delta.

---

## Gap Before

`docs/MGCV_FEATURE_COVERAGE.md` §2.1: `bs="re"` — **NO**. Not expressible,
no Stage A, no Stage B. Named explicitly in the maintainer's own objective
statement (§1: *"including `ti`, `s(..., bs='re')`, etc."*) and identified by
the ladder plan as the highest value-to-effort rung on the board — the
cheapest basis in `mgcv` (level indicators + identity penalty, exactly one
smoothing parameter regardless of level count) and the mechanism by which
Bühlmann-Straub credibility falls out of the GAM machinery rather than
needing a hand-set Z.

`docs/CONTINUATION_mgcv_capability_ladder.md`: "Slice 1 complete; slice 2
(`bs="re"`) not started."

## Gap After

- `SUPPORTED_BASES` now `("cr", "ti", "sz", "re", "raw")`.
- `TermSpec` accepts `basis="re"` (one factor variable, no `k`, `n_levels`
  required).
- `gam_model.assemble_model_design` dispatches `"re"` alongside `cr`/`ti`/`sz`.
- Stage A: `build_python_re_term` vs `smoothCon(s(fac, bs="re"))` — **exact**
  agreement, tier 3, at both 4 and 7 factor levels.
- Stage B, fixed `sp` (`gaussian(identity)`, matching ladder slice 1's own
  regime): `max_abs_eta_diff = 2.176e-14`, `edf_total_diff = 1.066e-14`, tier
  3.
- Stage B, free `sp` (`poisson(log)`, chosen so this half does not wait on
  rung L5): `max_abs_eta_diff = 3.226e-05`, `max_abs_log10_sp_diff = 0.0010`,
  `edf_total_diff = -0.0010`, single-start, tier 3.
- `MGCV_FEATURE_COVERAGE.md` §2.1's `re` row moves from **NO** to **yes**,
  Stage A ✅ tier 3 (exact), Stage B ✅ tier 3 **fixed AND free `sp`** — both
  regimes landed in this one slice (unlike `sz`, which shipped Stage A, then
  fixed-`sp` Stage B, then never reached free `sp` across three separate
  slices).

**Nothing was deferred.** The slice's full Definition of Done (Stage A,
Stage B fixed `sp`, Stage B free `sp`, all under ADR-221's imported gate, all
tier 3) was measurable within this session, because `poisson(log)`'s free-`sp`
search was already independently verified elsewhere in this epic and does not
share Gaussian's free-scale blocker.

---

## Hypotheses Tried

1. **"`mgcv` absorbs the same sum-to-zero constraint on `bs="re"` that it does
   on `cr`/`ti`/`sz`, so `build_python_re_term` needs a null-space step too."**
   Tested by direct R probe BEFORE writing any Python:
   ```r
   sm_true  <- smoothCon(s(fac, bs="re"), data=df, absorb.cons=TRUE)[[1]]
   sm_false <- smoothCon(s(fac, bs="re"), data=df, absorb.cons=FALSE)[[1]]
   identical(sm_true$X, sm_false$X)  # TRUE
   nrow(sm_true$C)                    # 0
   ```
   **REFUTED.** `absorb.cons` changes nothing for `"re"`, and no constraint is
   ever absorbed — documented `mgcv` behaviour (a random-effect smooth must
   stay free to shrink toward the overall mean at large `sp`, which a
   sum-to-zero constraint would prevent), not an artifact of this probe. This
   is what makes `re_basis` the two-line construction it is, and it is also
   why the Stage-A claim names one `mgcv` producer rather than two — there was
   a real risk of over-scoping the claim (declaring a comparison across
   `absorb.cons` settings that would in fact be comparing the same `mgcv`
   output against itself).
2. **"Stage B free `sp` needs `multistart=True`, matching the epic's 7-block
   `select=TRUE` fixtures."** Tested by running `fit_re_free_sp_case` with its
   default `multistart=False` first, both at tier 1 and tier 3. **REFUTED as a
   necessity** — single-start already reached `agrees=True` at
   `max_abs_eta_diff = 3.226e-05` (620x inside ADR-221's `2e-2` bound) on this
   2-block structure. `multistart` was never invoked; the module supports it
   (`fit_re_free_sp_case(..., multistart=True)`) for a future harder fixture,
   but this slice's own recipe did not need it — a genuine finding, not an
   oversight (the epic's own multistart need scales with block count and
   identifiability, not with `"re"` specifically).
3. No third hypothesis was needed — the first two passes closed the slice.

## Oracle Version

- **Tier 1** (local apt, structure only): R 4.3.3 / mgcv 1.9.1.
- **Tier 3** (authoritative): R 4.6.1 / mgcv 1.9.4, oracle image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8, the first host-independent build — `OPENBLAS_NUM_THREADS=1`
  pinned). CI run
  [35553707543](https://github.com/jonathancrawford05/polaris-re/actions/runs/35553707543),
  dispatched via `workflow_dispatch` on `claude/intelligent-hamilton-7yeu7m`,
  completed successfully (levels 1-3 AGREE, the CI gate that blocks a merge).

## Provenance

Per-comparison, per-column classification (ADR-193):

| Comparison | Column(s) | Classification | Why |
|---|---|---|---|
| Stage A (`re-4level`, `re-7level`) | `design_X`, `penalty_S`, `rank` | **INDEPENDENT** | `build_python_re_term(group, n_levels, term)` never reads the R payload's `X`/`S`/`rank` — only the shared `group`/`n_levels` recipe, matching `sz`'s own shared-recipe discipline |
| Stage B, fixed `sp` | `eta`, `edf_total` | **INDEPENDENT** | `fit_re_fixed_sp_case` takes `RReFixedSpRecipe`, structurally excluding every `mgcv`-produced key (`eta`, `edf_total`, `term_edf`, `offset_gap`, `coef`, `converged`) |
| Stage B, free `sp` | `eta`, `log10(sp)` per block, `edf_total`, per-term `edf` | **INDEPENDENT** | `fit_re_free_sp_case` takes `RReFreeSpRecipe`, structurally excluding `sp` itself in addition to every fixed-`sp` key — `sp` is the compared quantity, not a shared input |

No `REFERENCE_INTERNAL` or `MEASUREMENT (own criterion)` quantity appears
anywhere in this slice — every comparison has Polaris as one of its two
producers, and both `require_parity_evidence` calls (one per claim, exercised
in `test_gam_re_conformance.py`) pass on the full quantity set.

**Suspicion, not just a check**, applied per the continuation's own
instruction: the near-machine-precision fixed-`sp` reading and the exact
Stage-A zero were each interrogated the same two ways ADR-229 used for ladder
slice 1's own near-exact `edf_total`:

1. Every `mgcv`-produced key stripped from the payload leaves the Polaris fit
   bit-identical (`test_fixed_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped`,
   `test_free_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped`).
2. `edf_total` is not vacuously insensitive to the `"re"` block's own penalty:
   raising the fixed-`sp` recipe's `re` block from `1.2` to `50.0` strictly
   reduces `edf_total`
   (`test_fixed_sp_edf_total_moves_with_the_re_blocks_own_penalty`).

---

## Quality gate

- `uv run ruff format src/ tests/` — 5 files reformatted, applied.
- `uv run ruff check src/ tests/ --fix` — clean (one en-dash and one
  over-length line fixed by hand; one unused-unpacked-variable auto-fixed).
- `uv run pytest tests/ -v --tb=short -m "not slow"` — `3700 passed, 5
  failed (pre-existing, unrelated), 22 skipped`. Net +28 tests, 0 new
  failures.
- `uv run pytest tests/qa/ -v --tb=short` — `85 passed, 9 skipped`. Goldens
  byte-identical (no product/reinsurance/CLI path touched, confirmed by
  `git status --short` scope before committing).
- `uv run mypy` on the five changed/created `analytics/` modules — clean.
  Full-package mypy carries 54 pre-existing errors in unrelated files
  (`experience_gam.py`, `capital_base.py`, `solvency2.py`,
  `experience_loaders.py`, `experience_gam_penalized.py`,
  `experience_diligence.py`, `scenario.py`) — CI's own baseline, not this
  session's.
- `perf/history.jsonl` — one row appended (ADR-177), `has_structural_creep:
  False`.

---

## What was and was not accomplished

**Accomplished, fully, both `sp` regimes, tier 3:** the `bs="re"` basis is
built, wired into the `ModelSpec`/`assemble_model_design` path, and measured
against `mgcv` at Stage A (exact) and Stage B (fixed and free `sp`, both
`agrees=True` under ADR-221's imported gate). Nothing in this slice's own
Definition of Done was deferred or cut.

**Not attempted, correctly out of scope:** `multistart=True` was never
exercised for this basis (single-start already agreed); factor-`by` (ladder
L3) and `bs="fs"` (ladder L6) are different constructions and untouched;
`gaussian(identity)`'s own free-`sp` blocker (rung L5) is unaffected by this
slice and remains slice 3's scope.

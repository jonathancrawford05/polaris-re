# Dev session log — 2026-09-26 — mgcv capability ladder slice 4 (L3, factor-`by`)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Epic:** `docs/PLAN_mgcv_capability_ladder.md` / `docs/CONTINUATION_mgcv_capability_ladder.md` (ACTIVE)
**Slice:** 4 — L3 factor-`by`
**ADR:** ADR-232
**PR:** (draft, this branch — `claude/intelligent-hamilton-7m6dzu`)

---

## Setup

`uv sync --all-extras` — installed `patsy`/`statsmodels`/`openpyxl`/
`et-xmlfile` (not previously synced in this environment). Installed the
tier-1 scratch oracle via apt (idempotent check first; none was present):

```
R version 4.3.3 (2024-02-29)
mgcv 1.9.1
```

Matches `ROUTINE_MGCV_PARITY.md`'s expectation exactly (R 4.3.3 / mgcv 1.9.1
from apt). `OPENBLAS_NUM_THREADS=1` exported for tier-1 R invocations.

Also ran the one-time mortality-table conversion
(`scripts/convert_soa_tables.py --source pymort`), since `uv run pytest -m
"not slow" tests/` on a fresh checkout showed 5 failures traced to missing
`data/mortality_tables/*.csv` (generated, not committed — CLAUDE.md §11).
After conversion: **3768 passed, 3 skipped, 133 deselected** — the clean
baseline this session's own changes are measured against. (3 skips remain,
unrelated to R availability — not investigated further, out of this slice's
scope.) `tests/qa/` — **94 passed** — goldens byte-identical.

---

## Gap Before

`assemble_model_design` could express a numeric `by` (`TermSpec.by`,
ADR-200) but had **no route at all** for a **factor** `by` (`s(x, by =
fac)`). `TermSpec.by` is documented as numeric and `TermSpec.factor` marks
the unrelated `sz`/`fs` construction. `docs/MGCV_NOTATION_PRIMER.md` §4:
a factor `by` is a term **multiplier** — an `n`-level factor produces `n`
*separate* smooths, each with its own smoothing parameter — not a
continuous-scaling term the way numeric `by` is.

`docs/CONTINUATION_mgcv_capability_ladder.md`: "Slices 1, 2 and 3 complete;
slice 4 (L3, factor-`by`) next."

## Gap After

- `TermSpec` gains `by_factor: str | None` / `by_level: int | None`
  (orthogonal fields, not a widened `by`) and `gam_term_spec.factor_by_terms`
  — the one place a factor-`by` term expands into its `n_levels` separate
  `TermSpec`s.
- `gam_basis_cr.by_factor_mask_design` + `gam_stage_a.build_python_cr_by_factor_term`
  (+ `CR_BY_FACTOR_BASIS_CLAIM`) — the independent Python producer, built
  from a construction DERIVED from measurement, not guessed: the shared
  no-`by` `cr` smooth on the WHOLE covariate column, masked to one level
  AFTER the constraint is absorbed.
- `gam_term_extract.R` gains `extract_smooth_by_factor` (2 cases, 5 levels).
- `gam_by_factor_conformance.py` — Stage B, both `sp` regimes, ONE family
  (`gaussian(identity)`) throughout since ladder L5 (ADR-231) already closed
  the free-scale blocker before this slice was written.
- Two new R probes, workflow wiring (path filters + 2 R-job steps + 3
  compare-job steps), and unit/closed-form tests.
- `MGCV_FEATURE_COVERAGE.md` §2.1/§4 updated; ladder slice 4 marked DONE.

**Nothing in this slice's own Definition of Done was deferred.** Only
`basis="cr"` is wired for `by_factor`/`by_level` — no other basis names a
factor-`by` term in the target formula, so nothing else was owed.

---

## Hypotheses Tried

1. **"Each level of a factor-`by` term is a standalone `cr` smooth built
   from just that level's own `x` subset, sharing the full-data knots."**
   Tested tier 1 against `smoothCon(s(x, by=fac, bs="cr", k),
   absorb.cons=TRUE)` on a synthetic 3-level case. The UNCONSTRAINED design
   matched exactly (`0.0`), confirming the raw per-row basis values do not
   depend on level bookkeeping — but the CONSTRAINED design and the
   (already-scaled) penalty did NOT (`diffX` up to `0.26`, `diffS` up to
   `0.21`). **REFUTED.**
2. **"The `scale.penalty` normalising constant is computed from the
   COMBINED multi-level design (every level's own block stacked side by
   side), not from any one level's own design."** Isolated by comparing the
   UNCONSTRAINED, un-rescaled penalty first (matched exactly once masking
   was set aside): the actual scale factor is `norm_one(S_raw) /
   norm_inf(X_combined)²`, and since every row of the combined design has
   nonzero entries in only one level's own column block, `norm_inf` of the
   combined design equals the MAX over levels of each level's own
   `norm_inf`. **CONFIRMED**, exact (`0.0`) prediction before writing any
   basis code.
3. **"The identifiability constraint is `mgcv`'s ORDINARY no-`by` `colMeans`
   constraint, computed on the WHOLE covariate column and IDENTICAL across
   every level — not a per-level-subset constraint (hypothesis 1's
   assumption)."** Tested directly: `mgcv`'s own `$C` for a factor-`by`
   term's unconstrained smooth is bit-identical across all three levels and
   equals `colMeans()` of a bare (non-split) `s(x)` smooth fit on the SAME
   full dataset. **CONFIRMED** — building the shared no-`by` `cr` smooth
   once (unchanged from `build_python_cr_term`'s own no-`by` path), then
   masking to one level AFTER the constraint is absorbed, reproduced
   `smoothCon(...)` bit-exactly (`0.0`, not merely float round-trip) on
   every level, before `by_factor_mask_design` was written into the module
   proper.
4. No further hypothesis was needed for Stage B: the fixed- and free-`sp`
   fits agreed to float round-trip precision / well inside ADR-221's gate
   on the FIRST measurement, the same "no iteration needed" pattern every
   prior capability-ladder slice in this epic has shown once its own Stage A
   was independently correct.

## Oracle Version

- **Tier 1** (local apt, structure and formula derivation checks): R 4.3.3 /
  mgcv 1.9.1.
- **Tier 3** (authoritative): R 4.6.1 / mgcv 1.9.4, oracle image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8). CI run
  [36262093452](https://github.com/jonathancrawford05/polaris-re/actions/runs/36262093452),
  dispatched via `workflow_dispatch` on `claude/intelligent-hamilton-7m6dzu`,
  completed successfully. Required conformance levels 1-3 AGREE (no
  regression from this slice's own edits); level 4 unchanged (DISAGREES,
  ADR-190, permanently expected — not this slice's concern per the routine's
  own standing facts); level 5 AGREES.

All three of this slice's own new comparisons ran and confirmed the tier-1
reading, same order of magnitude, same verdict, tier 3 tighter on every
Stage-B quantity (a pattern, not a surprise — same as every prior ladder
slice's own tier-1/tier-3 comparison).

## Provenance

Per-comparison, per-column classification (ADR-193):

| Comparison | Column(s) | Classification | Why |
|---|---|---|---|
| Stage A, factor-`by` basis | `design_X`, `penalty_S`, `rank` | **INDEPENDENT** | `build_python_cr_by_factor_term(x, group, term)` takes only the shared covariate/group recipe and the term spec — never an R payload; `gam_term_extract.R`'s `extract_smooth_by_factor` reads `smoothCon()`'s own per-level list, an entirely separate implementation |
| Stage B, fixed `sp` | `eta`, `edf_total` | **INDEPENDENT** | `RByFactorFixedSpRecipe` structurally excludes `eta`/`edf_total` — `fit_by_factor_fixed_sp_case`'s signature cannot see `mgcv`'s fit even if handed the wider payload type |
| Stage B, free `sp` | `eta`, `log10(sp)` per block, `edf_total`, per-term `edf` | **INDEPENDENT** | `RByFactorFreeSpRecipe` structurally excludes every `mgcv`-produced key, including `sp` itself — free `sp` is the compared quantity, not a shared input |

No `ECHO`, `TRANSPORT`, `REFERENCE_INTERNAL` or `MEASUREMENT (own
criterion)` quantity appears anywhere in this slice's own new comparisons —
every one has Polaris as one of its two producers, and every one is a
genuine parity comparison, not a harness check.

**Suspicion, not just a check.** Both R probes give the by-term's levels
genuinely different slopes so `edf_total` has real signal to move against
(`test_fixed_sp_edf_total_moves_with_the_by_term_penalty`), and every
`mgcv`-produced key is structurally excluded from the recipe type AND
stripped-and-refit at runtime
(`test_fixed_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped`,
`test_free_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped`) — the same
pair every prior capability-ladder Stage-B module in this epic carries.

---

## Quality gate

- `uv run ruff format src/ tests/` — 3 files reformatted (new test files).
- `uv run ruff check src/ tests/ --fix` — one over-length line fixed by
  hand (a `ComparedQuantity.quantity` string), otherwise clean.
- `uv run pytest tests/ -q -m "not slow"` — `3768 passed, 3 skipped, 133
  deselected`, 0 failures. Net +69 passed relative to the pre-slice baseline
  (new unit tests in `test_gam_term_spec.py`, `test_gam_basis_cr.py`,
  `test_gam_stage_a.py`, and the new `test_gam_by_factor_conformance.py`).
- `uv run pytest tests/qa/ -q` — `94 passed`. Goldens byte-identical (no
  product/reinsurance/CLI path touched).
- `uv run mypy` on the five changed/created `analytics/` modules
  (`gam_by_factor_conformance.py`, `gam_term_spec.py`, `gam_basis_cr.py`,
  `gam_stage_a.py`, `gam_model.py`) — clean, no new errors.
- `perf/history.jsonl` — one row appended (ADR-177), on the initial PR open,
  since this PR touches `src/polaris_re/`.

---

## What was and was not accomplished

**Accomplished, fully, tier 3 (confirmed — see ADR-232):** the `by` axis
(numeric and factor) is now complete. The factor-`by` construction was
derived from direct measurement against `mgcv` (three hypotheses, two
refuted) before any Python was written, and reproduces `smoothCon(s(x,
by=fac, bs="cr", k), absorb.cons=TRUE)` bit-exactly per level. Stage B
agrees at both fixed and free `sp`, ONE family throughout, first
measurement, no iteration needed at either stage.

**Not attempted, correctly out of scope:** any basis other than `cr` for
`by_factor`/`by_level`; extending `select=TRUE`'s null-space penalty to a
factor-`by` block shape (the free-`sp` measurement uses ordinary,
non-`select` penalty blocks — the target formula's own `select=TRUE` usage
was verified against other block shapes in the predecessor epic, and
combining it with factor-`by` is not named by this slice's own acceptance
criterion).

**Noted, not fixed (pre-existing, not a regression):** `gam_term_extract.R`'s
Stage-A "sz" report step lists the new `by-factor-*` cases as `UNKNOWN CASE`
— the same cosmetic label it already gave `re-4level`/`re-7level` before
this slice, in a `continue-on-error: true` diagnostic that does not gate
anything. Not registered as a gap.

**Next:** `docs/PLAN_mgcv_capability_ladder.md` slice 5 — L4, the
unpenalized parametric block. This is the last rung this epic's own plan
names; climbing it closes `PLAN_mgcv_capability_ladder.md` itself.

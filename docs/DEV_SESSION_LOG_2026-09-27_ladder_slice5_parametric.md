# Dev session log — 2026-09-27 — mgcv capability ladder slice 5 (L4, unpenalized parametric block)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Epic:** `docs/PLAN_mgcv_capability_ladder.md` / `docs/CONTINUATION_mgcv_capability_ladder.md` — **now COMPLETE**
**Slice:** 5 — L4 unpenalized parametric block (the LAST rung this plan names)
**ADR:** ADR-233
**PR:** (draft, this branch — `claude/intelligent-hamilton-kjxt1s`)

---

## Setup

`uv sync --all-extras` — clean. Installed the tier-1 scratch oracle via apt
(idempotent check first; none was present):

```
R version 4.3.3 (2024-02-29)
mgcv 1.9.1
```

Matches `ROUTINE_MGCV_PARITY.md`'s expectation exactly (R 4.3.3 / mgcv 1.9.1
from apt; first `apt-get install` attempt failed on stale package-index
404s, `apt-get update` then a retry succeeded — noted, not a code finding).
`OPENBLAS_NUM_THREADS=1` exported for tier-1 R invocations.

`uv run pytest tests/ -q -m "not slow"` on the untouched checkout: **3744
passed, 22 skipped, 133 deselected, 5 failed** — all 5 failures traced to
missing `data/mortality_tables/*.csv` (generated, not committed —
CLAUDE.md §11; this environment had no prior mortality-table conversion
run and none was performed this session, since the parametric-block work
does not touch the mortality/product path at all). `tests/qa/` — **85
passed, 9 skipped** — goldens intact. This is this session's baseline;
PROCEED per the routine's own instruction (known-standing, environment-only
failures, not a new or changed failure set).

---

## Gap Before

`assemble_model_design` built an intercept and then penalized terms only —
`"cr"`, `"ti"`, `"sz"` and `"re"`. There was no route for unpenalized
parametric *columns* at all. `docs/MGCV_FEATURE_COVERAGE.md` §1's target
formula opens with `FaceSize + Smoke + FaceSize:Smoke` — three parametric
terms — so it was inexpressible for this reason quite independently of any
basis question. `docs/CONTINUATION_mgcv_capability_ladder.md`: "Slices 1-4
complete; slice 5 (L4, unpenalized parametric block) next."

## Gap After

- `TermSpec` gains `basis="parametric"` and a new `levels: tuple[int, ...]
  | None` field (one factor-level count per named variable — a main effect
  names one, an interaction names two or more), deliberately separate from
  the existing `n_levels` (a single count, used by `"sz"`/`"re"`/
  factor-`by`, each of which names exactly one factor).
- `gam_basis_parametric.parametric_design` — `mgcv`'s own `contr.treatment`
  dummy coding: one indicator column per non-reference level for a main
  effect, or the outer product of each named variable's own dummy columns
  (first-named variable fastest) for an interaction. No knots, no
  rescaling, no constraint, and **zero penalty** — the first basis in this
  epic with no penalty block at all.
- `gam_stage_a.build_python_parametric_term` + `PARAMETRIC_BASIS_CLAIM` —
  the Stage-A independent producer.
- `gam_model._build_term_extract`'s dispatch extended for `"parametric"`.
- A real edge case found and fixed in MEASURE FIRST:
  `null_space_penalty` raises on an empty penalty-block tuple rather than
  returning `None`; `assemble_model_design`'s `select=True` branch called
  it unconditionally, which crashes on a term with zero existing blocks —
  guarded with `if model.select and extract.s:`.
- `gam_parametric_conformance.py` — Stage B, both `sp` regimes, ONE family
  (`gaussian(identity)`) throughout, matching ladder rungs L3/L5 since L5
  (ADR-231) already closed the free-scale blocker.
- A new, self-contained R Stage-A probe
  (`scripts/gam_parametric_stage_a_probe.R`) that needs **no fit at all** —
  the parametric block does not depend on `sp`/`y`/the smooth — reusing the
  SHARED `compare_term_extract` machinery unchanged, since the R export
  already matches `RTermPayload`'s existing shape.
- Two new Stage-B R probes, workflow wiring (path filters + 3 R-job steps +
  3 compare-job steps + artifact-list entries), and unit/closed-form tests
  (`test_gam_basis_parametric.py`, `test_gam_parametric_conformance.py`,
  plus additions to `test_gam_term_spec.py` and `test_gam_model.py`).
- `MGCV_FEATURE_COVERAGE.md` (§2.1 new row, §2.3 row moved NO → tier 3,
  §2.4 scorecard, §4 ladder row and status banner) and
  `PLAN_mgcv_capability_ladder.md` (slice 5 marked DONE, status banner)
  updated. **This closes the capability ladder epic — L1 through L5 are
  all climbed.**

**Nothing in this slice's own Definition of Done was deferred.** Only a
main effect and a two-way interaction are exercised (the target formula
names no three-way parametric interaction), and `select=TRUE`'s null-space
penalty was exercised only insofar as this slice found and fixed the
zero-block edge case — neither is part of this slice's own acceptance
criterion.

---

## Hypotheses Tried

1. **"`mgcv`'s parametric block for `A + B + A:B` is R's ordinary
   `model.matrix(~A + B + A:B)` under `contr.treatment`, with the
   interaction's columns ordered first-named-variable-fastest."** Tested
   tier 1 directly on a synthetic 3-level/2-level factor pair BEFORE any
   Python was written:
   ```r
   > colnames(model.matrix(~A + B + A:B, data.frame(A=A,B=B)))
   [1] "(Intercept)" "Aa1" "Aa2" "Bb1" "Aa1:Bb1" "Aa2:Bb1"
   ```
   **CONFIRMED** — a main effect drops the reference level and keeps one
   column per remaining level in level order; the interaction is the outer
   product of the two main-effect blocks, first-named variable fastest.
   `gam_basis_parametric.parametric_design`'s fold
   (`np.einsum("ni,nj->nji", design, dummy).reshape(...)`) reproduces this
   exactly, verified bit-for-bit against the R reading before being written
   into the module, and against a synthetic 3-variable case (no R
   counterpart) confirming the fold generalises correctly.
2. **"Column order does not need to match `mgcv`'s for Stage B, only for
   Stage A."** Not tested by measurement (it is a consequence of Anchor 2 —
   `eta` is basis-invariant, a linear model's fitted values do not depend
   on which order its unpenalized columns are in) — stated as the reason
   Stage A's exact column-order match is a Stage-A finding, not a Stage-B
   dependency, and recorded as such in the module docstring rather than
   left implicit.
3. **A genuine defect, found by inspection during MEASURE FIRST, not by a
   failing test:** `null_space_penalty`'s own docstring requires "at least
   one penalty block" and raises otherwise.
   `assemble_model_design`'s `select=True` branch calls it unconditionally
   on every term's own blocks. Read `gam_select_penalty.py` before writing
   any parametric code (since a zero-penalty term was about to exist for
   the first time in this engine) and confirmed the call would raise on
   `extract.s == ()`. **Fixed before it could be discovered as a runtime
   crash**, with a guard and a dedicated regression test
   (`test_parametric_terms_have_nothing_for_select_to_double`).
4. No further hypothesis was needed for Stage B: the fixed- and free-`sp`
   fits agreed to `1e-14`/`1e-7` respectively on the FIRST measurement —
   the tightest free-`sp` reading this epic has produced, tighter than
   every other rung's own first Stage-B measurement — the same "no
   iteration needed" pattern every prior capability-ladder slice has shown
   once its own Stage A was independently correct.

## Oracle Version

- **Tier 1** (local apt, structure and formula-derivation checks): R 4.3.3
  / mgcv 1.9.1.
- **Tier 3** (authoritative): R 4.6.1 / mgcv 1.9.4, oracle image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8). CI run
  [36289418480](https://github.com/jonathancrawford05/polaris-re/actions/runs/36289418480),
  dispatched via `workflow_dispatch` on `claude/intelligent-hamilton-kjxt1s`.
  Completed successfully (both jobs green) at 2026-09-27T02:52:48Z. Required
  levels 1-3 of the existing ten-cell suite AGREE (no regression), level 4
  unchanged (DISAGREES, ADR-190, permanently expected), level 5 AGREES.

## Provenance

Per-comparison, per-column classification (ADR-193):

| Comparison | Column(s) | Classification | Why |
|---|---|---|---|
| Stage A, parametric block | `design_X` | **INDEPENDENT** | `build_python_parametric_term(groups, term)` takes only the shared 0-indexed level-code recipe and the term spec — never an R payload; the R side is a bare `model.matrix()` call, an entirely separate implementation. No `penalty_S`/`rank` column: the block carries no penalty at all |
| Stage B, fixed `sp` | `eta`, `edf_total` | **INDEPENDENT** | `RParametricFixedSpRecipe` structurally excludes `eta`/`edf_total` — `fit_parametric_fixed_sp_case`'s signature cannot see `mgcv`'s fit even if handed the wider payload type |
| Stage B, free `sp` | `eta`, `log10(sp)`, `edf_total`, the smooth's own per-term `edf` | **INDEPENDENT** | `RParametricFreeSpRecipe` structurally excludes every `mgcv`-produced key, including `sp` itself |

No `ECHO`, `TRANSPORT`, `REFERENCE_INTERNAL` or `MEASUREMENT (own
criterion)` quantity appears anywhere in this slice's own new comparisons.

**Suspicion, not just a check.** Both R probes give `FaceSize`, `Smoke` and
their interaction genuinely different effects on the mean, and every
`mgcv`-produced key is structurally excluded from the recipe type AND
stripped-and-refit at runtime
(`test_fixed_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped`,
`test_free_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped`) — the same
pair every prior capability-ladder Stage-B module in this epic carries.
Additionally, this slice's own closed-form test suite proves (not merely
observes) that a parametric block's per-term `edf` is exactly its own
column count regardless of correlation with any other term, derived from
`hat = I - (X'WX+S)^{-1}S` and the fact that every column of `S` at a
parametric index is identically zero.

---

## Quality gate

- `uv run ruff format src/ tests/` — 5 files reformatted.
- `uv run ruff check src/ tests/ --fix` — clean, no findings.
- `uv run mypy` on the five changed/created `analytics/` modules
  (`gam_basis_parametric.py`, `gam_stage_a.py`, `gam_term_spec.py`,
  `gam_model.py`, `gam_parametric_conformance.py`) — clean, no new errors.
- `uv run pytest tests/ -q -m "not slow"` — **3773 passed, 22 skipped, 136
  deselected, 5 failed** — the SAME 5 pre-existing, environment-only
  failures as the session baseline (missing mortality tables), net +29
  passed (new unit/conformance tests) and +3 deselected (new `@slow`
  R-gated round-trip tests). No regression.
- `uv run pytest tests/qa/ -q` — **85 passed, 9 skipped**. Goldens
  byte-identical (no product/reinsurance/CLI path touched).
- `perf/history.jsonl` — one row appended (ADR-177), on this PR's initial
  open, since it touches `src/polaris_re/`. `has_structural_creep: False`
  (peak_mib flat at 33), `has_wall_time_creep: False`.

---

## What was and was not accomplished

**Accomplished, fully, tier 1 AND tier 3 both confirmed:** an
unpenalized parametric block (main effect and interaction) is now
expressible and reproduces `mgcv` exactly at Stage A (`0.000e+00`, both
tiers) and well inside ADR-221's committed gate at Stage B, both fixed
(`max_abs_eta_diff=1.066e-14`, tier 3) and free `sp`
(`max_abs_eta_diff=3.261e-07`, tier 3), first measurement, no iteration
needed at either stage, no regression on either tier's ten-cell suite. **This
closes `docs/PLAN_mgcv_capability_ladder.md` — L1 through L5 are now all
climbed at both tiers**, the capability ladder epic's own stated completion
condition. See ADR-233 and `docs/CONFORMANCE_LEDGER.md` for the full tier-3
figures.

**Not attempted, correctly out of scope:** a three-way (or higher)
parametric interaction; `select=TRUE`'s null-space penalty against a model
mixing a parametric term with a `select=TRUE` smooth (only the zero-block
edge case itself was exercised, at assembly time — the free-`sp` Stage B
measurement uses ordinary, non-`select` penalty blocks, matching every
prior ladder rung's own Stage B scope).

**Registered, not attempted (pre-existing, unrelated to this slice):**
slice 3b (quasi-Poisson's own fit-level free-`sp` re-run) remains open and
unsized in `PLAN_mgcv_capability_ladder.md` §3 — not this slice's own
scope, and the plan's own text says it does not block slice 5.

**Next:** the successor epic for ladder rungs L6-L8 (`bs="fs"`, `bs="tp"`,
`te`/`t2`) is the expected next ACTIVE EPIC, named in
`MGCV_FEATURE_COVERAGE.md` §4/§5 and `PLAN_mgcv_capability_ladder.md` §5
but **deliberately unregistered until it is sized** — the session that
sizes it creates its own PLAN and CONTINUATION file, per the
one-active-epic rule this epic's own start followed.

**PRODUCT_DIRECTION harvest:** considered, nothing new to add. This slice's
only two follow-ups (slice 3b, and the L6-L8 successor epic) are already
registered/named in `PLAN_mgcv_capability_ladder.md` §3/§5, which is the
correct container for them (ADR-209 decision 1) — no new gap was opened by
this slice that isn't already tracked there.

# Session log — 2026-08-31 — Slice 6: the single-factor `sz` basis (Stage A)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 6 — `docs/PLAN_mgcv_parity_engine.md`. READY since ADR-212/ADR-214;
the routine's "next unchecked slice, no fallback picks" rule selected it —
slice 5f (the last item ahead of it) closed the same day.
**PR:** this branch, draft.
**ADR:** ADR-215.

## Setup

- `uv sync --all-extras` — clean (4 new packages: `statsmodels`, `patsy`,
  `openpyxl`, `et-xmlfile`).
- Installed the local scratch oracle (tier 1): `apt-get install -y -qq
  r-base-core r-cran-mgcv r-cran-jsonlite` failed on stale package-index
  404s first (the same recurring transient prior sessions record); `apt-get
  update` fixed it. Versions recorded: **R 4.3.3 (2024-02-29) / mgcv 1.9-1**
  — matches the routine's expected apt versions, no drift to flag.
- Read `docs/PLAN_mgcv_parity_engine.md` (Anchors 1, 2, 3, 8), the
  CONTINUATION status block through ADR-214, `docs/VERIFICATION_STANDARD.md`,
  `docs/CONFORMANCE_LEDGER.md`'s tail, and CLAUDE.md.

## `make test` baseline

`uv run pytest tests/ -q -m "not slow"`: **3504 passed, 6 failed, 22 skipped**
(519s). All 6 failures reproduce identically on the pre-session `HEAD`
(`git stash` + re-run, confirmed before writing any code): 5 are missing
`data/mortality_tables/*.csv` (generated, not committed — CLAUDE.md §11, this
environment never ran `convert_soa_tables.py`), 1 is
`test_gam_model_conformance.py::test_the_r_probe_runs_end_to_end`'s own
documented, thread-dependent free-`sp` reading
(`max_abs_log10_sp_diff=0.2606` — the exact ADR-212 tier-3 figure quoted in
CONTINUATION's own "Not closed: the coordinate" note). **Match — proceed**,
per the routine's own baseline rule.

## Gap Before

**No Python `sz` producer existed.** PLAN's own gap-audit table read `bs =
"sz"`: **Not started, expected hardest basis (PLAN §6 registered
prediction)**. `scripts/gam_term_extract.R` had no `extract_smooth_sz`
branch; `gam_stage_a.py` had no `build_python_sz_term`; `gam_basis_cr.py` had
no `sz_basis`. The claim sentence could not be filled in at all — there was
no left-hand producer to name.

**Tier and digest:** N/A — no prior measurement exists to state a "before"
number for.

## What `mgcv` actually does (measured, not read off documentation)

`?smooth.terms`'s prose ("the sum over all factor levels of equivalent spline
coefficients are all zero") does not specify a construction precise enough to
implement. Read `mgcv:::smooth.construct.sz.smooth.spec` (`deparse`) and
`mgcv:::smoothCon` (`deparse`) to find the actual mechanism (Anchor 8:
understanding source code to find out what it computes is not the licensing
violation transcribing it into this MIT repo would be):

1. The constructor calls the **bare** `smooth.construct` generic on the base
   class (`cr` here), never `smoothCon()` — so no `scale.penalty` has run on
   the per-level block yet. Confirmed by instrumenting the constructor
   (`assign("SZ_DUMP", result, envir=.GlobalEnv)` inside a wrapped copy) and
   comparing the dumped `object$base$S`/`object$Xb` bit-for-bit (`max abs
   diff 0`) against a direct call to
   `mgcv:::smooth.construct.cr.smooth.spec`.
2. It tensors that raw block against a one-hot factor-level indicator,
   factor **slower** / base **faster** in column order (confirmed by the
   per-level block-diagonal placement of the pre-constraint `S` list — each
   `S[[i]]` nonzero only in its own diagonal block).
3. It sets `object$C <- c(0, nf)` — a plain numeric vector, not a matrix.
   `smoothCon`'s own `absorb.cons` step branches on `length(sm$C) > 1`
   (found by reading `smoothCon`'s source directly, not by trial and error)
   into `mgcv:::XZKr`, a recursive column-major reshape-and-difference
   loop — the branch every OTHER basis in this repo skips.

**`scale.penalty` fires once**, on the assembled (pre-constraint) design and
each pre-constraint penalty block independently — confirmed by dumping
`norm(SZ_DUMP$S[[i]])` and `norm(SZ_DUMP$X, "I")^2` and predicting the final
(post-`XZKr`) blocks from them directly (a probe script, not committed):
matched `smoothCon()`'s actual output to `max abs diff 0` on a toy 2-level
case before any Python was written.

## The independent re-derivation (not a transcription of `XZKr`)

`XZKr`'s loop has no closed-form statement anywhere `mgcv` documents, and
Anchor 8's licensing companion rule (`mgcv` is GPL (>= 2), this project is
MIT) forbids porting it. Derived instead: for a single factor with
`n_levels` levels and a `p0`-column raw base block, the transform mgcv
applies is right-multiplication (design) or conjugation (penalty) by
`M = D ⊗ I_{p0}`, where `D` is `(n_levels, n_levels - 1)` with `D[l,l] = 1`
for `l < n_levels - 1` and `D[n_levels - 1, l] = -1` for every `l` — each of
the first `n_levels - 1` levels compared against the last one.

**Verified in two independent steps before it was written into the shipped
module:**
1. A from-scratch Python transliteration of `mgcv:::XZKr`'s own reshape loop
   (using `numpy`'s `order="F"` to match R's column-major semantics),
   checked against `mgcv:::XZKr`'s own output on 4 synthetic matrices —
   confirmed the reshape loop's *effect*, not committed as code (transcribed
   structure, kept only as a scratch verification aid, never shipped).
2. The closed-form `M = D ⊗ I_{p0}` derivation, checked directly against
   `smoothCon(bs="sz", absorb.cons=TRUE)`'s actual `X`/`S`/`rank` on 3
   synthetic cases (`nf=2, k=5`; `nf=3, k=4`; `nf=2, k=8`) — this is the
   form that shipped, and step 1 served only to build confidence in step 2's
   result before spending the effort to write it into `gam_basis_cr.py`.

## What was built

- `src/polaris_re/analytics/gam_basis_cr.py`:
  - `_cr_basis_raw` — `cr_basis` split into its pre-`scale.penalty` half
    (needed because `sz`'s per-level block skips that step) and the public
    `cr_basis`, now a thin wrapper re-adding the scale. No behaviour change
    to `cr_basis`'s own contract.
  - `sz_basis(x, group, n_levels, knots)` — the construction above, single
    factor only (scope matches every one of the target's four `sz` terms).
- `src/polaris_re/analytics/gam_stage_a.py`: `build_python_sz_term` (same
  mechanical-test shape as `build_python_cr_term`/`build_python_ti_term` —
  takes only the shared `x`/`group`/`n_levels` recipe and the `TermSpec`,
  never an R payload) and `SZ_BASIS_CLAIM` (`design_X`/`penalty_S`/`rank`,
  all `INDEPENDENT`). `RTermPayload` gained `group`/`n_levels` fields.
- `scripts/gam_term_extract.R`: `extract_smooth_sz`, mirroring
  `extract_smooth_ti`'s own internal guard (`smoothCon()` vs
  `predict(type="lpmatrix")`/`m$smooth[[1]]`, `stop()`-gated) and exporting
  the shared recipe (`x`, `group`, `n_levels`) rather than any mgcv-computed
  quantity. Three cases added to `smooth_cases`: a synthetic 3-level factor
  (Anchor 1 — the target's own terms are all 2-level, so this is the only
  case exercising `n_levels > 2`), and the target formula's own `AttdAge`
  (k=13) / `PolYear` (k=6) knots at 2 levels.
- `.github/workflows/mgcv-conformance.yml`: a "Slice 6" section in the
  diagnostic per-term report step, mirroring the `ti` section. **Caught and
  fixed a filter bug while building it**: the existing `single_var_smooth_terms`
  predicate (`r_term.get("knots") is not None`) also matched the new `sz`
  cases (which carry a non-`None` `knots` — the smoothed margin's own
  recipe), causing them to appear as spurious "UNKNOWN CASE" rows under the
  **slice 2 (`cr`)** table and falsely flip `any_cr_disagree`. Fixed by
  adding `and r_term.get("group") is None` to the filter — found by actually
  running the extracted diagnostic script locally against a real
  `gam_term_extract.json`, not just reading the diff.
- Tests: `tests/test_analytics/test_gam_basis_cr.py` (7 closed-form
  invariants, no R needed — shape, symmetry, PSD-ness, the rank-preservation
  identity, and 3 refusal paths); `tests/test_analytics/test_gam_stage_a.py`
  (`build_python_sz_term` unit tests plus the R-gated
  `test_the_python_sz_basis_agrees_with_smoothcon_on_every_sz_design`).

**One test written wrong, caught by running it, not by review.** The first
version of `test_sz_basis_every_level_shares_the_same_scale_penalty_factor`
asserted every level's FINAL (post-constraint) penalty block has the same
one-norm — conflating "the pre-constraint `scale.penalty` factor is shared"
(true) with "the final conjugated norm is shared" (false: the last level's
block conjugates through the whole `(n_levels-1)²` contrast grid and is
exactly `(n_levels-1)` times larger — confirmed on the 3-level case,
`5.185.../2.593... = 2.0` exactly). Fixed the test to state the correct
invariant rather than loosen a tolerance (Anchor 8 applies to test
assertions too).

## Measurement

Tier 1, all three `extract_smooth_sz` cases, first attempt:

| case | max abs X diff | max abs S diff (per level) | rank diff |
|---|---:|---:|---|
| `sz-default-knots-k6-3level` (n_levels=3) | 2.854e-14 | 5.107e-15, 5.107e-15, 5.107e-15 | (0, 0, 0) |
| `sz-target-attdage-k13` (n_levels=2) | 1.443e-14 | 4.441e-15, 4.441e-15 | (0, 0) |
| `sz-target-polyear-k6` (n_levels=2) | 1.699e-14 | 5.773e-15, 5.773e-15 | (0, 0) |

Same order of magnitude as slice 2's `cr` cases (~1e-14) and slice 5's `ti`
cases (~1e-14/1e-15) — float round-trip precision, no iteration needed.

## Gap After

**Stage A closed for the scope the target formula needs**: a Python
producer exists (`gam_basis_cr.sz_basis`), agrees with `mgcv` bit-for-bit on
`design_X`/`penalty_S`/`rank` at both `n_levels=2` (matching every target
`sz` term) and `n_levels=3` (exercising the general case), and every
compared quantity is `INDEPENDENT` (`SZ_BASIS_CLAIM`). **PLAN §6's own
"hardest basis" prediction did not bite Stage A** — the cost was entirely in
*understanding* `mgcv`'s constraint machinery (no closed-form documentation
anywhere), not in getting the numbers to agree once that understanding
existed.

**What remains, registered as PLAN slice 6b** (ADR-209 decision 1: a gap
this session opens is closed or registered, not merely filed): Stage B — a
multi-term fit including an `sz` term, compared on `eta` against `mgcv`'s
own native fit, ADR-206's own pattern. Also open, named but not attempted:
extending slice 4 part B's `select_lambdas_continuous` to an `sz`-shaped
penalty-block structure (one smoothing parameter per factor level).

## Provenance (ADR-193)

**Claim sentence:** `polaris_re`'s new single-factor `sz` basis computes
`design_X` and every `penalty_S` block from the covariate locations, the
0-indexed factor-level code per row and a knot vector (`gam_basis_cr.sz_basis`,
called through `build_python_sz_term`); `mgcv` computes them via
`smoothCon(s(fac, x, bs="sz", k, xt=list(bs="cr")), absorb.cons=TRUE)`
(`scripts/gam_term_extract.R`'s `extract_smooth_sz`); compared on `design_X`,
every `penalty_S` block and `rank`.

**Mechanical test applied to `build_python_sz_term`'s signature**: it takes
`x`, `group`, `n_levels` (the shared recipe) and `term` (the shared spec) —
never an R payload. Passes.

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `design_X` | `gam_basis_cr.sz_basis` (per-row factor selection of the raw `cr` block, then the contrast-vs-last-level constraint) | `mgcv smoothCon(s(fac, x, bs="sz", ...), absorb.cons=TRUE)$X` | INDEPENDENT |
| `penalty_S` (every level) | `gam_basis_cr.sz_basis` (one raw-block-derived penalty per level, rescaled once, then constraint-conjugated) | `mgcv smoothCon(...)$S` | INDEPENDENT |
| `rank` (every level) | `numpy.linalg.matrix_rank` on each Python `sz` penalty block | `mgcv smoothCon(...)$rank` (mgcv's own rank determination) | INDEPENDENT |
| `knots` | `build_python_sz_term` (supplied recipe, or `cr_default_knots`) | `mgcv smoothCon(...)$xp` | ECHO in the 2 supplied-knot cases; would be INDEPENDENT only in a default-knot case (none among the 3 shipped) — excluded from `SZ_BASIS_CLAIM`, same reasoning as `CR_BASIS_CLAIM` |

**This is real parity evidence**, the same class of result ADR-194 (`cr`)
and ADR-205 (`ti`) established: two distinct implementations from the same
recipe, agreeing at float round-trip precision. Per ADR-193's own framing, an
agreement here is one of the two defined successful outcomes (the other
being a disagreement with a named mechanism) — not a foregone conclusion,
since a wrong sign or a wrong axis in the closed-form contrast derivation
would have produced a real, measurable disagreement.

## Oracle version

Tier 1: R 4.3.3 (2024-02-29) / mgcv 1.9-1 (local apt). Tier 3: dispatched
this session against the pinned oracle digest — see
`docs/CONFORMANCE_LEDGER.md` for the run and reading.

## Quality gate

- `uv run ruff format src/ tests/` — 1 file reformatted (`gam_stage_a.py`,
  whitespace only).
- `uv run ruff check src/ tests/ --fix` — caught 15 `RUF002` (ambiguous
  Unicode `ℓ` in the new docstring); fixed by using ASCII `l` throughout.
  All checks passed after.
- `uv run mypy src/polaris_re/analytics/gam_basis_cr.py
  src/polaris_re/analytics/gam_stage_a.py` — no issues.
- `uv run pytest tests/test_analytics/test_gam_stage_a.py
  tests/test_analytics/test_gam_basis_cr.py -q` — 95 passed (includes the
  R-gated `sz` parity test, since R is installed this session).
- `uv run pytest tests/qa/ -q` — 85 passed, 9 skipped (mortality-table-gated),
  golden outputs byte-identical (`git diff` on `tests/qa/golden_outputs/`
  empty) — no production path touched.
- Full suite (`uv run pytest tests/ -q -m "not slow"`): 3504 passed, 6 failed
  (all pre-existing, confirmed via `git stash` against the same baseline),
  22 skipped — matches the session's own recorded baseline exactly.

## Definition of done (PLAN slice 6's own acceptance, reproduced per ADR-209 decision 3)

Slice 6's PLAN entry names no separate formal acceptance list beyond "Stage
A is where a mistake here is cheap" (PLAN §6). Reproducing what this session
actually closes, in the shape other slices' DoD sections use:

- `[machine]` **Python `sz` basis agrees with `smoothCon(bs="sz",
  absorb.cons=TRUE)` on `design_X`, every `penalty_S` block and `rank`, at
  `n_levels` 2 and 3, including the target formula's own `AttdAge`/`PolYear`
  knots.** → `test_the_python_sz_basis_agrees_with_smoothcon_on_every_sz_design`
  (R-gated, PASSED this session at tier 1); tier-3 CI dispatch, this session.
- `[machine]` **Every claimed quantity declared `INDEPENDENT` in the type,
  gated by `require_parity_evidence`.** → `SZ_BASIS_CLAIM`,
  `test_the_python_sz_basis_declares_every_quantity_independent`.
- `[machine]` **The construction is derived, not transcribed, from `mgcv`'s
  source** (Anchor 8's licensing companion rule). → module docstring's
  numbered derivation plus this log's "independent re-derivation" section;
  no code in `sz_basis` resembles `mgcv:::XZKr`'s own reshape loop.
- `[machine]` **`cr_basis`'s existing behaviour is unchanged by the
  `_cr_basis_raw` refactor.** → the full pre-existing `cr`/`ti` test suite
  passes unchanged (37/37 in `test_gam_basis_cr.py`, including every
  pre-existing case).
- `[machine]` **Nothing in `products/`, `reinsurance/` or the CLI moves;
  `tests/qa/` untouched.** → `tests/qa/` byte-identical, confirmed above.
- `[judgement]` **Scope stated explicitly: single factor, no `id`.** →
  module docstring, `SZ_BASIS_CLAIM`'s own docstring, PLAN slice 6's status
  note, this log's "Gap After" section. Confirmed by the PR reviewer against
  the target formula's own four `sz` terms (PLAN §1) — all four are
  single-factor, none sets `id`.
- `[judgement]` **The remaining gap (Stage B) is registered, not left
  implicit.** → PLAN slice 6b, ADR-215's own "Consequences" section.

## Follow-ups filed

- **PLAN slice 6b** (this session): `sz` Stage B — a multi-term fit
  including an `sz` term, compared on `eta` against `mgcv`'s own native fit.
  Not blocking slice 7.
- **Named, not filed as a slice**: extending slice 4 part B's
  `select_lambdas_continuous` to an `sz`-shaped penalty-block structure (one
  smoothing parameter per factor level). Left for whoever takes slice 6b, or
  a later slice if 6b's own measurement does not reach it cleanly.

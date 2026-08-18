# Dev Session Log — 2026-08-18 (production REML-score check, work order)

## Item Selected

- **Source:** `docs/ROUTINE_MGCV_PARITY.md` — scheduled firing of the parity routine.
- **Priority:** ACTIVE EPIC, `docs/CONTINUATION_mgcv_parity_engine.md`.
- **Work order:** `docs/WORK_ORDER_reml_penalized_deviance_production_check.md` — named
  explicitly, in `docs/PLAN_mgcv_parity_engine.md`'s Slice 4 section and PR #203's own
  description, as the next `ROUTINE_MGCV_PARITY.md` firing, gating slice 4 part B (the
  N-dimensional outer search). Supersedes generic slice-picking for this session per the
  work order's own framing.
- **Scope:** three measurements (§3.1, §3.2, §3.3) and a recommendation — explicitly NOT a
  license to patch `experience_gam_penalized.py` (PLAN Anchor 7) or re-baseline
  `data/mgcv_exchange/synthetic/python_reference.json` without separate maintainer
  sign-off.
- **Branch:** `claude/zealous-mendel-j0huik`.

## Setup

- `uv sync --all-extras`.
- Installed the tier-1 scratch oracle: `apt-get update` (stale index, needed first —
  unrelated PPA 403s on `deadsnakes`/`ondrej/php`, main Ubuntu repos fine), then
  `r-base-core r-cran-mgcv r-cran-jsonlite`. **R 4.3.3 / mgcv 1.9.1** — matches the
  routine's documented apt expectation exactly, no version drift. `export
  OPENBLAS_NUM_THREADS=1` per SETUP step 2.
- Read, in full: `docs/ROUTINE_MGCV_PARITY.md`,
  `docs/WORK_ORDER_reml_penalized_deviance_production_check.md`,
  `docs/VERIFICATION_STANDARD.md`, `docs/PLAN_mgcv_parity_engine.md` (Anchors 1, 2, 8, the
  Slice 4 section), `docs/CONTINUATION_mgcv_parity_engine.md`,
  `docs/CONFORMANCE_LEDGER.md`, CLAUDE.md, `docs/DECISIONS.md` (ADR-189 + amendments 1 and
  2, ADR-190 through ADR-196), `docs/RUNBOOK_mgcv_conformance.md`.
- Read the source: `gam_reml.py`, `gam_reml_conformance.py`, `experience_gam_penalized.py`
  (`reml_score`, `_penalized_irls`, `select_lambdas_reml`, `smoothing_uncertainty`,
  `_fit_and_score`), `experience_mgcv_conformance.py` (`DesignExport`, `read_exchange`,
  `PythonCellResult`), `gam_family.py`, `core/verification.py`.

## Baseline and end state

| | |
|---|---|
| Baseline (`pytest -m "not slow"`, before touching code, R present) | **3298 passed, 5 failed, 22 skipped, 126 deselected** |
| The 5 failures | Pre-existing `data/mortality_tables/*.csv`-absent root cause — the CSVs are not part of this checkout, generating them is a separate unrelated setup step. Unrelated to this epic and to R/mgcv. Not a regression (matches the prior parity session's baseline note exactly, and the delta from that session's 3285/3295 is explained by intervening merges into `main` before this branch started). |
| `tests/qa/` (94 tests) | 85 passed, 9 skipped — unmodified goldens, byte-identical, both before and after. |
| End state (`pytest -m "not slow"`, after) | **3308 passed, 5 failed (same), 22 skipped (same), 126 deselected** — the 10-pass increase is exactly this session's new tests (`test_gam_reml_production_check.py`). |
| `ruff format` / `ruff check` on `src/`, `tests/` | Clean. |
| Perf row | one row appended (`perf/history.jsonl`, commit `170bd76`) — `gam_reml_production_check.py` is a new module under `src/polaris_re/analytics/`, so ADR-177 amendment 1's docs/scripts/tests-only exemption does not apply (same reasoning the prior parity session applied to `gam_reml.py`). **Creep verdict:** no structural creep — `peak_mib` 33 → 33 (Δ0); wall-time ratio 1.343x is advisory only and does not gate. |

## Gap Before

ADR-196 fixed `gam_reml.reml_score_general`'s missing `β̂ᵀSβ̂` penalized-deviance term and
found, by inspection, that `experience_gam_penalized.reml_score` — the already-shipped
production tensor-MI 2-D grid selector's own score — has the identical formula shape and
the identical omission. Whether that mattered — the actuarial impact, not the code-level
fact — was explicitly unmeasured, and PLAN Anchor 7 protects that module from being
touched without separate maintainer sign-off. `docs/CONTINUATION_mgcv_parity_engine.md`
named this work order as the gate ahead of slice 4 part B (the N-dimensional outer
search) — the epic's largest remaining piece of work could not proceed meaningfully
while the production selector's own status was a hypothesis, not a measurement.

## Gap After

**Measured, characterized, and a recommendation is on record — not fixed.** §3.1: the
raw/offset-adjusted score gap at each free-sp cell's own mismatched point does NOT
collapse (it roughly doubles) — a named limitation, not a refutation. §3.2, the decisive
measurement: re-scoring `select_lambdas_reml`'s own grid search with the corrected
criterion selects a point measurably CLOSER to `mgcv`'s own free-sp selection on **all
three** free-sp cells tested, and independently reproduces the exact grid-step move a
maintainer-run local patch already found. §3.3: the correction shifts
`smoothing_uncertainty`'s finite-difference Hessian materially (~25-40% on eigenvalues)
but does not materially close ADR-190's already-characterized 3.2-4.1x Kass-Steffey
under-inflation gap. ADR-197 records the full result and a recommendation (fix it; the
re-baseline is maintainer-gated). Slice 4 part B is now unblocked to proceed regardless
of that decision, since its own criterion (`gam_reml.reml_score_general`) needed no fix.

## Hypotheses Tried

1. **§3.1 hypothesis:** "the offset-adjusted residual against mgcv's own score should
   collapse toward zero under the corrected criterion, the way ADR-196's fixed-`sp`
   pairwise-difference measurement did." **REFUTED as literally stated** — the residual
   roughly doubles (current: -1.84/-2.50/-1.66; corrected: -3.74/-4.65/-3.79 across the
   three free-sp cells). Not treated as a dead end or a failure: the work order itself
   anticipated this class of outcome ("§3.2 is the harder question"), and the reason is
   structural — a free-sp cell has each side selecting a DIFFERENT `lambda`, so the raw
   score gap mixes the formula error with the point mismatch. Recorded honestly as a
   real, negative result for §3.1's own framing, not spun as a partial success.
2. **§3.2 hypothesis (registered before running, per the work order's own Anchor-9-style
   discipline):** "if the missing term is a real bug, the corrected grid search should
   select measurably closer to mgcv's own free-sp selection." **CONFIRMED on all 3
   cells** — log10 distance to mgcv's selection: 0.3149→0.0663 (`l2-free-sp`),
   0.1870→0.1097 (`-factors`), 0.4559→0.1248 (`-kb`). The `l2-free-sp` move
   (3162.28→5623.41) is a second, independent confirmation of the exact number a
   maintainer-run local patch-and-refit experiment already found (ADR-196's resolution
   section) — reached via a structurally different route (a from-scratch parallel grid
   search, never touching the production function).
3. **§3.3 hypothesis:** "this bug is a material contributor to the standing level-4
   Kass-Steffey BLOCKER (ADR-190)." **REFUTED** — the Hessian/eigenvalues shift
   materially (~25-40%) but the resulting inflation-ratio move is a few percentage
   points, nowhere near ADR-190's separately-characterized 3.2-4.1x gap. A useful
   negative result: it rules this bug in or out as an explanation for a DIFFERENT,
   already-open finding, cheaply, rather than leaving the two conflated.

No hypothesis required more than one pass — each was measured once, tier 1, then
confirmed identical at tier 3, per the routine's own discipline (iterate on tier 1,
verify on tier 3).

## Oracle Version

- **Tier 1:** R 4.3.3 / mgcv 1.9.1, local apt install, this session.
- **Tier 3:** R 4.6.1 / mgcv 1.9.4, jsonlite 2.0.0, oracle image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8), CI run
  [32181109927](https://github.com/jonathancrawford05/polaris-re/actions/runs/32181109927),
  commit `170bd76`. Both jobs completed in ~67s total (`mgcv reference (R)`: 33s;
  `Compare against the Python reference`: 29s, including the new diagnostic step's ~3s).
  Exchange hash `78dc8914de78…` confirmed identical between `python_reference.json` and
  the freshly-generated `mgcv_reference.json` on both tiers — no stale-reference risk.
  Every number in §3.1/§3.2/§3.3 is identical between tier 1 and tier 3 at every printed
  digit. Required levels 1-3 of the existing ten-cell suite also still agree on the tier-3
  run — no regression from the workflow edit.

## Provenance

Every comparison this session reports, per ADR-193's per-column discipline:

| Comparison | Left producer | Right producer | Provenance |
|---|---|---|---|
| §3.1 `reml_score` (current, production formula) vs mgcv | `experience_gam_penalized.reml_score`, evaluated at the `(design, coef, penalty)` `select_lambdas_reml` already produced — never reads mgcv's fit/score | `mgcv m$gcv.ubre` at its own independently-selected free-sp REML fit | **INDEPENDENT** |
| §3.1 `reml_score` (corrected, Dp-based) vs mgcv | `gam_reml.reml_score_general(family=poisson_log())` (ADR-196, already independently verified), evaluated at the SAME already-fitted `(design, coef, penalty)` | same mgcv fit as the row above | **INDEPENDENT** |
| §3.2 selected `(λ_age, λ_year)`, current vs corrected vs mgcv | `select_lambdas_reml`'s own already-committed selection (current) and `select_lambdas_corrected`'s diagnostic replica (corrected) — a from-scratch parallel grid search, never calling or importing the production selector's scorer | mgcv's own free-sp `sp` from its own REML fit | **INDEPENDENT** (both Python producers; neither reads mgcv's `sp` or coefficients) |
| §3.3 Hessian/eigenvalues/inflation, current vs corrected | `score_shape_diagnostic`'s diagnostic replica of `smoothing_uncertainty`'s own central-difference construction, scored two ways from one shared fit per grid point | N/A — this is an internal Python-vs-Python comparison (current formula vs corrected formula), not a comparison against mgcv | **INDEPENDENT** producers of the two Python quantities; not a claim about mgcv at all |
| §3.3 `mgcv inflation (reported)` | `experience_gam_penalized.smoothing_uncertainty`'s already-published number (ADR-189 amendment 1) | `mgcv vcov(unconditional=TRUE)` at its own free-sp fit | Restated for scale only, not recomputed this session — same provenance as ADR-189 amendment 1 |

`PRODUCTION_REML_CHECK_CLAIM` (`gam_reml_production_check.py`) declares the §3.1
quantities formally and is gated by `require_parity_evidence` in
`tests/test_analytics/test_gam_reml_production_check.py::TestProvenanceClaim`. §3.2 and
§3.3 are reported without a separate `VerificationClaim` object (they compare Python
selections/diagnostics against each other and against mgcv's already-independent `sp`,
not a fresh producer pair needing its own declaration) — provenance is stated in prose
above and in the probe script's own report text, per the same discipline.

## What was NOT done, deliberately

- **`experience_gam_penalized.reml_score` was not edited.** PLAN Anchor 7.
- **`data/mgcv_exchange/synthetic/python_reference.json` was not re-baselined.** Confirmed
  unmoved: `git diff` against it is empty. The recommendation (ADR-197 decision 2) names
  this as the maintainer's decision, not this session's.
- **`tests/qa/golden_outputs/` was not touched.** Confirmed unmoved.
- **Slice 4 part B (the N-dimensional outer search) was not started.** Out of scope for
  this session; now unblocked per ADR-197 decision 3.
- **No tolerance was widened, no constant tuned.** The `_AGREEMENT_TOLERANCE` in
  `gam_reml_conformance.py` (unrelated to this session's new module) is untouched.

## Deliverables

- `src/polaris_re/analytics/gam_reml_production_check.py` — the diagnostic module
  (`corrected_reml_score`, `measure_production_score_gap`, `select_lambdas_corrected`,
  `score_shape_diagnostic`, `PRODUCTION_REML_CHECK_CLAIM`).
- `scripts/reml_production_check_probe.py` — the report generator, runnable locally
  (tier 1) or read from CI (tier 3).
- `tests/test_analytics/test_gam_reml_production_check.py` — 10 new tests.
- `.github/workflows/mgcv-conformance.yml` — one new diagnostic (`continue-on-error`)
  step in the existing `compare` job, plus path-filter entries.
- `docs/DECISIONS.md` — ADR-197.
- `docs/CONFORMANCE_LEDGER.md` — 6 new rows (§3.1/§3.2/§3.3, tier 1 and tier 3 each).
- `docs/CONTINUATION_mgcv_parity_engine.md` — updated status line, slice 4 detail, gap
  audit table, backlog.
- `docs/PRODUCT_DIRECTION_2026-07-24.md` — harvest entry, 1st-order.
- `perf/history.jsonl` — one row, commit `170bd76`.

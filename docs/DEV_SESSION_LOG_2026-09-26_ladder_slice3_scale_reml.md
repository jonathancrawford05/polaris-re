# Dev session log — 2026-09-26 — mgcv capability ladder slice 3 (L5, scale-estimated REML)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Epic:** `docs/PLAN_mgcv_capability_ladder.md` / `docs/CONTINUATION_mgcv_capability_ladder.md` (ACTIVE)
**Slice:** 3 — L5 scale-estimated REML
**ADR:** ADR-231
**PR:** (draft, this branch — `claude/intelligent-hamilton-otwvq6`)

---

## Setup

`uv sync --all-extras` — clean. Installed the tier-1 scratch oracle via apt
(idempotent check first; none was present in this environment):

```
R version 4.3.3 (2024-02-29)
mgcv 1.9.1
```

Matches `ROUTINE_MGCV_PARITY.md`'s expectation exactly (R 4.3.3 / mgcv 1.9.1
from apt). `OPENBLAS_NUM_THREADS=1` exported for the tier-1 R invocations
(harmless — local apt R links reference `libblas`, not OpenBLAS).

Baseline `make test`-equivalent (`uv run pytest tests/ -q -m "not slow"`),
run BEFORE any code change other than the two edits MEASURE FIRST itself
produced (see below): `3699 passed, 6 failed, 22 skipped, 130 deselected`.
Five of the six failures are pre-existing and environmental —
`test_loaded_ilec_feeds_tensor_mi_surface` and four
`TestCalibratedPremiums` cases in `test_synthetic_block.py`, all traced to
`data/mortality_tables/*.csv` not existing in this container (generated, not
committed — CLAUDE.md §11; this session did not generate them, since doing
so needs a working pymort download this environment's egress policy may not
allow, and none of these five tests touch `gam_*`/`TermSpec`/
`assemble_model_design`, so they are out of this slice's scope). The sixth,
`test_utils/test_measurement_provenance.py::test_check_passes_on_the_current_repository`,
**was caused by this session's own edits** (`gam_family.py`'s deviance fix
changed that file's content-hash, which moved
`docs/MEASUREMENT_unconditional_coverage.md`'s dependency-closure hash even
though the study's own measured path — `experience_gam_penalized` /
`gam_uncertainty_mi`, whose only `gam_family` dependency is `poisson_log()`
— is untouched in substance). Resolved with
`scripts/measurement_stamp.py stamp ... --assert --note "..."`, recording
why the change does not touch the measured path (ADR-204's own prescribed
remedy). Final baseline after that fix: **`3699 passed, 5 failed`** — the
five pre-existing environmental ones only.

With R installed, the R-gated tests in `test_gam_*_conformance.py` flip from
SKIPPED to PASSED.

---

## Gap Before

`gam_reml.reml_score_general` (`gam_reml.py:263`) raised UNCONDITIONALLY
whenever `family.dispersion_fixed` was `False`. Two registered families
carry that flag: `gaussian`/`identity` (ladder L1, ADR-229 — shipped "fixed
`sp` only" for exactly this reason) and `quasipoisson`/`log` (marked
expressible in the coverage table, raising at free `sp` — the standing ⚠️).
Neither could select its own smoothing parameters:
`select_lambdas_continuous` had no criterion to search.

`docs/CONTINUATION_mgcv_capability_ladder.md`: "Slice 1 and 2 complete;
slice 3 (L5, scale-estimated REML) not started."

## Gap After

- `gam_reml.reml_score_general` has a free-scale branch, derived from Wood
  (2011) §2 eq. (4) profiled over the unknown scale
  (`φ̂ = Dp/(n-Mp)`, `Mp` = the paper's own null-space dimension of `S`).
- A real, pre-existing factor-of-2 defect in
  `gam_family._gaussian_deviance_terms` (shipped at ladder L1, harmless
  there) is fixed — `mgcv`'s own `gaussian()$deviance` is the plain RSS,
  measured directly, not `2*RSS`.
- `gam_free_scale_reml_conformance.py` — score-level Stage-C comparison,
  BOTH free-scale families, against `mgcv`'s own `m$gcv.ubre`: Gaussian on
  the ABSOLUTE score (exact, first measurement), quasi-Poisson on PAIRWISE
  DIFFERENCES (same convention ADR-196 established for the known-scale
  Poisson criterion).
- `gam_gaussian_conformance.py` gains `GAUSSIAN_FREE_SP_CLAIM` — the
  fit-level free-sp re-run of ladder L1's own three-term recipe, `agrees=True`
  on the first measurement.
- `MGCV_FEATURE_COVERAGE.md` §2.2/§2.3 updated; the L5 ladder row marked
  climbed; **ladder slice 1's own "fixed `sp` only" qualifier removed in
  this PR** — the plan's own acceptance criterion for this slice.

**Nothing in this slice's own Definition of Done was deferred.** Quasi-
Poisson's own FIT-level free-sp re-run (a `PolarisGAM` measurement analogous
to Gaussian's) was correctly NOT attempted — the plan names only the score
measurement (both families) and the Gaussian fit re-run as this slice's
acceptance.

---

## Hypotheses Tried

1. **"The free-scale REML criterion can be derived from Wood (2011) eq. (4)
   by profiling over the unknown scale, the same way the known-scale branch
   already implements the fixed-scale half of the same equation."** This was
   the primary hypothesis and it HELD, but not on the first attempt at a
   *source*: every web host tried (journal publishers behind paywalls,
   ResearchGate, Semantic Scholar, arXiv, a university course-notes PDF) was
   blocked by this session's egress policy (`EGRESS_BLOCKED` from the
   `WebFetch` tool on every domain tried). The coordinating agent then
   supplied the paper directly as a local PDF
   (`/root/.claude/uploads/771c7e8b-f189-5f07-b686-6a0a679ac8ef/c9aa1c86-Wood_JRSSB_2011_73_1_3.pdf`),
   which this session read with `pdftotext` (installing `poppler-utils` —
   also initially blocked by a stale apt mirror, resolved with
   `apt-get update` first). Reading §2 p.4 in full CONFIRMED the derivation
   this session had already worked out independently from first-principles
   REML theory (Patterson & Thompson 1971 / Harville 1974) before the PDF
   arrived — the paper states `Mp` (used in `n - Mp`) is literally "the
   dimension of the null space of `S`," matching what the independent
   derivation had already required, and names the exact two routes to `φ̂`
   this session's route (i) implements.
2. **"`mgcv`'s reported `m$scale` under `method="REML"` IS the criterion's
   own internally-profiled `φ̂`."** Tested directly, tier 1, on an
   UNPENALIZED case first (`r=0`, `Mp=p`): `φ̂` (mine) matched `m$scale`
   bit-identically (`0.2391795807` both). **REFUTED as a general claim** by
   the PENALIZED case (`r=6`, `Mp=2`): `φ̂` (mine, `0.0816`–`0.1239` across
   4 `sp` values) did NOT match `m$scale` (`0.0841`–`0.0987`) at all, while
   the ABSOLUTE SCORE still matched `mgcv`'s `gcv.ubre` exactly at every
   point. Correct interpretation, confirmed by re-reading the paper's own
   text: `m$scale` is a SEPARATE, Pearson/`edf`-based dispersion estimate
   (the paper's own route (ii)), not this criterion's internal `φ̂` (route
   (i)) — recorded in ADR-231 explicitly so a later session does not read a
   `phi_hat`-vs-`m$scale` mismatch as a defect.
3. **"Quasi-Poisson's absolute REML score also reproduces `mgcv`'s
   `gcv.ubre` exactly, the same way Gaussian's does."** Tested tier 1 on a
   shared two-block design at 3 fixed `(sp1,sp2)` points. **REFUTED** — a
   small, nearly-`sp`-independent additive residual (~275.68, stable to
   ~1 part in 4e5 across a 2000x `sp` spread) survives. Diagnosed rather than
   chased further: quasi-likelihood has no proper saturated log-likelihood
   (its own `a(y,φ)` normalizing term is not uniquely defined by the
   quasi-score equations), so `ls(φ)` in the paper's own decomposition is not
   the same well-defined quantity it is for a genuine exponential family —
   the SAME shape of finding ADR-196 already accepted for the known-scale
   Poisson criterion's own convention offset. Resolution: compare
   quasi-Poisson on PAIRWISE DIFFERENCES only (agrees to `~1e-14`), never
   claim its absolute score — declared as such in the claim sentence, not
   left to a caption.
4. No fourth hypothesis was needed for the core formula — 1-3 closed it. A
   fifth, smaller one surfaced only in MEASURE FIRST (see "Gap Before"):
   **"the Gaussian deviance factor-of-2 in `gam_family.py` is inert, per its
   own docstring."** Tested by a standalone R check BEFORE writing any new
   Python (`m$deviance` vs `RSS` vs `2*RSS`, unpenalized). **REFUTED** — it
   was a real, pre-existing defect (see "Gap After"), caught precisely
   because this slice's own formula was the first consumer that needed
   `D(β̂)` directly rather than only as an IRLS convergence signal.

## Oracle Version

- **Tier 1** (local apt, structure and formula derivation checks): R 4.3.3 /
  mgcv 1.9.1.
- **Tier 3** (authoritative): R 4.6.1 / mgcv 1.9.4, oracle image
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`
  (build 8). CI run
  [36242943352](https://github.com/jonathancrawford05/polaris-re/actions/runs/36242943352),
  dispatched via `workflow_dispatch` on `claude/intelligent-hamilton-otwvq6`,
  completed successfully (levels 1-3 AGREE, the CI gate that blocks a merge;
  both new comparison steps ran and `agrees=True` on every gated quantity —
  score: Gaussian absolute diffs `0.000e+00`/`4.263e-14`/`-7.105e-14`,
  quasi-Poisson pairwise residuals `4.263e-14`/`2.842e-14`/`-1.421e-14`; fit:
  `max_abs_eta_diff=2.933e-04`, `edf_total_diff=-0.0206` on `n=900`, `p=86`).
  Tier 1 agreed first on the identical recipes (same verdict, same order of
  magnitude — full figures in ADR-231).

## Provenance

Per-comparison, per-column classification (ADR-193):

| Comparison | Column(s) | Classification | Why |
|---|---|---|---|
| Score, Gaussian | `gaussian_reml_score` | **INDEPENDENT** | `score_free_scale_point` takes plain arrays, the family object and the `sp` setting itself — never any R-payload-shaped argument |
| Score, quasi-Poisson | `quasipoisson_reml_score_pairwise_diff` | **INDEPENDENT** | same signature, same guarantee |
| Fit, Gaussian free `sp` | `eta`, `log10(sp)` per block, `edf_total`, per-term `edf` | **INDEPENDENT** | `fit_gaussian_free_sp_case` takes `RGaussianFreeSpRecipe`, structurally excluding every `mgcv`-produced key including `sp` itself (free `sp` is the compared quantity, not a shared input) |
| Deviance-convention finding (pre-work) | `mgcv`'s own `gaussian()$deviance` | **MEASUREMENT (own criterion)** — no second producer; `mgcv`'s value is the referent a bug in OUR code is measured against, per `VERIFICATION_STANDARD.md` §2.1 | not a comparison — removing the reference leaves no number (there is nothing to compare our OLD, wrong deviance against without it) |

No `REFERENCE_INTERNAL` quantity appears anywhere in this slice — every
comparison has Polaris as one of its two producers.

**Suspicion, not just a check**, applied per the continuation's own
instruction — but this slice's own strongest result went further than the
usual strip/perturb pair: the Gaussian score's EXACT match against `mgcv`'s
`gcv.ubre` (absolute value, not shape) was arrived at by DERIVING the
formula from the paper FIRST, then measuring — the derivation predicted the
exact value before any R payload was read, which is the strongest form this
epic's "suspicion before result" discipline can take. The strip/perturb pair
was still run on the fit-level free-sp claim
(inherited unchanged from `fit_polaris_gam`'s own already-verified
machinery — no new independence test needed there, since nothing about the
free-scale branch changes what `RGaussianFreeSpRecipe` excludes).

---

## Quality gate

- `uv run ruff format src/ tests/` — applied; several files reformatted
  during iteration.
- `uv run ruff check src/ tests/ --fix` — clean (two over-length lines fixed
  by hand).
- `uv run pytest tests/ -v --tb=short -m "not slow"` — `3710 passed, 5
  failed (pre-existing, unrelated, environmental), 22 skipped, 131
  deselected`. Net +11 passed, +1 deselected (the new `@pytest.mark.slow`
  free-sp round-trip test), 0 new failures.
- `uv run pytest tests/qa/ -v --tb=short` — `85 passed, 9 skipped`. Goldens
  byte-identical (no product/reinsurance/CLI path touched).
- `uv run mypy` on the four changed/created `analytics/` modules —
  `gam_reml.py`, `gam_free_scale_reml_conformance.py`,
  `gam_gaussian_conformance.py` clean; `gam_family.py` carries the SAME 7
  pre-existing `no-any-return` errors present before this session's edit
  (confirmed by diffing `mypy` output against `git show HEAD:...` — CI's own
  baseline, not this session's).
- `perf/history.jsonl` — one row appended (ADR-177), `has_structural_creep:
  False`.

---

## What was and was not accomplished

**Accomplished, fully, tier 3 (confirmed — see ADR-231):** the free-scale REML criterion is derived from Wood (2011)
eq. (4), implemented, and measured against `mgcv`'s own `gcv.ubre` for both
registered free-scale families — Gaussian exact (absolute score), quasi-
Poisson exact in shape (pairwise). Ladder slice 1's own "fixed `sp` only"
qualifier is removed via a free-sp re-run of its identical recipe,
`agrees=True` on the first measurement. A real, pre-existing defect
(Gaussian's deviance factor-of-2) was found and fixed in MEASURE FIRST,
before any new formula was written.

**Not attempted, correctly out of scope:** quasi-Poisson's own FIT-level
free-sp re-run; registering `Gamma`/Tweedie in `_FAMILY_LINKS` (unblocked in
principle by this slice, but neither is a registered family and registering
one is separate work); extending `gamma` to the free-scale branch (no
derivation exists for what it should do to an estimated `φ` — raises rather
than guesses, a marked scope boundary per CLAUDE.md).

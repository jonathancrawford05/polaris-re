# Session log — 2026-10-16 — real-data readiness Slice R3, Stage A (`bam` discretisation)

**Branch:** `claude/dreamy-galileo-ckoo7w` (the environment-designated branch). **PR class:** `feat(mgcv-parity)` for Stage A only — it lands an INDEPENDENT comparison — but **R3 is NOT done**: Stage B (the `bgam.fitd` port) is not started and no fitter is user-callable yet. PR is a draft.

**Box vs repo.** The box names no epic; the repo's pointer names `PLAN_gam_real_data_readiness.md`, R3 next. Consistent. One staleness note for the maintainer: ADR-260's "Open" item (the binning rule) is closed by this session, but the box/ADR framing "Polaris must reproduce `bam`'s discretisation" understated the real work — see Finding 2.

## Oracle Version
Tier 1 (scratch only): local apt R 4.3.3 / mgcv 1.9.1 (after `apt-get update`), `OPENBLAS_NUM_THREADS=1`. Tier 2 unavailable (`docker info`: no daemon). Tier 3 (every committed number): CI run `38840851229`, digest `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, mgcv 1.9.4 / R 4.6.1 (2026-06-24) as printed by the run. The tier-3 algorithm-section numbers equal the tier-1 ones to the printed digits.

## Baseline (full suite, `pytest tests/ -m "not slow"`, no `-x`)
**5 failed, 4112 passed, 22 skipped, 145 deselected** (799 s), taken while the new test file was being added. The 5 failures are environmental and not from this change: 4 in `tests/test_synthetic_block.py::TestCalibratedPremiums` and `test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface` raise `FileNotFoundError: data/mortality_tables/soa_vbt_2015_male_smoker.csv` (the mortality tables are not converted in this sandbox). `tests/qa/`: 85 passed, 9 skipped (goldens untouched; nothing under `src/` re-pointed). The new file alone: 23 passed (R-gated test included).

## Gap Before
No Polaris `bam` capability existed; ADR-260 PROPOSED with the binning rule marked open. Provenance: no comparison existed. The measured `gam`-vs-`bam` gap (ADR-260 table) was unexplained.

## Hypotheses Tried
1. **R3A-H1 (tier 1): `bam(discrete=TRUE)`'s gap from `gam` on the trial covariates is binning.** Read the source; ran gam / `bam(discrete=FALSE)` / `bam(discrete=TRUE)` on a no-binning integer cell. **Refuted**: with <=1000 unique values `discrete.mf` bins nothing; `bam` still differs from `gam`, and discrete vs non-discrete `bam` differ only by ~1e-6. The gap is `bgam.fitd`'s performance iteration. Re-read at tier 3 in the run above.
2. **R3A-H2: the port reproduces `discrete.mf`.** First tier-1 reading 18/19, one DIFFERENT (`exactly_1001_unique_binned`). Localised in two measurements to a **transport artefact**: jsonlite `digits = NA` writes 15 significant digits, so Polaris saw data one ulp from `mgcv`'s and an engineered exact rounding tie (`q = 499.49999999999994` vs `499.5`) flipped. Fixed with `digits = I(17)`; then 19/19. Not widened, not explained away: the cell is kept because it is the sharpest test of the rounding rule.
Chain cap: first slice of this mechanism class (criterion/algorithm, not outer search); no solver work done.

## Gap After
Stage A: binning port INDEPENDENT-agrees on every variable (19 of 19 variable comparisons, tier 3). **The gap to `bam` itself is unchanged and still unmeasured for Polaris**, because no Polaris fit of `bam`'s algorithm exists. The ADR now says what Stage B must be.

## Provenance
- `nr`, discretised value per row, row partition: **INDEPENDENT.** Left: `discretise_frame(formula, data)` (signature: a formula string and a DataFrame, no `mgcv` payload). Right: `mgcv:::discrete.mf` / `compress.df` on the same formula and data. Cell labels deliberately NOT compared (mgcv shuffles them with a seeded `sample`).
- gam vs bam(discrete=FALSE) vs bam(discrete=TRUE) eta / edf: **REFERENCE_INTERNAL** (mgcv against mgcv, Polaris absent). Real evidence about the reference, none about Polaris; the gate `require_parity_evidence` refuses it (tested).
- Declared in `BINNING_CLAIM` / `ALGORITHM_CLAIM`; the report headlines come from `evidence_markdown`.

## Definition of done (CONTINUATION "R3 pick-up")
- Stage A claim written before code, exact equality of binning/discretised design on synthetic cells in CI: **MET for binning** (`tests/test_gam/test_bam_binning_conformance.py`; tier 3 run `38840851229`). **NOT MET for "the discretised design"**: no discretised `X'WX`/`X'Wz` accumulation exists yet (Stage B).
- Stage B Polaris `bam` fit vs `bam(discrete=TRUE)` at the unchanged gates: **NOT MET, because** the `bgam.fitd` port is not built; this session's finding is that it is the work.
- Maintainer's real-data `bam` run at `full` within 10 minutes: **NOT MET, because** nothing to run yet.
- `fit_polaris` accepts `discrete=TRUE, method="fREML"`, refusing the rest by name: **NOT MET, because** Stage B.

## Follow-ups
Registered, not merely filed: Stage B is R3's remaining scope (CONTINUATION "R3 Stage A status"). Loose ends 3-5 and 7 from the R2 list are untouched this session (harness failure reasons, S1 data-rule counts, `slogdet` warnings, `full`-ratio evidence): they are the next session's first items before the Stage-B ADR text is finalised. Maintainer questions re-put: ADR-260 decision 5 and `discrete=TRUE` in the reference.

## Perf
No `perf/history.jsonl` row: the only `src/polaris_re/` file touched is `gam/bam_binning_conformance.py`, a `*_conformance.py` module outside the perf probe's import closure (ADR-177 amendment 2).

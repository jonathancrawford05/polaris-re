# Dev session log — 2026-09-30 — ladder slice 3b: quasipoisson(log) at free `sp`

**Branch:** `claude/intelligent-hamilton-twezu8` (PR #245, draft)
**Slice:** `PLAN_mgcv_capability_ladder.md` slice 3b (next unchecked; slice 6 was the last landed).
**PR title class:** `feat(mgcv-parity)` — lands an INDEPENDENT comparison.

## Claim sentence (written before the code)
`polaris_re`'s `fit_polaris_gam` assembles the three-term cr/cr-by/ti design from a shared
recipe and selects its own four `log10(lambda)` under `quasipoisson(log)` via the free-scale
REML branch; `mgcv` computes it via `gam(family=quasipoisson(link="log"), method="REML")`
with its own sp and dispersion; compared on `eta`, `edf_total`, per-term `edf` (gated,
ADR-221 imported) and `log10(sp)` (reported).

## Oracle Version
- Tier 1: R 4.3.3 / mgcv 1.9.1 (apt; matches the expected versions, nothing moved).
- Tier 3: R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, run 36704353339 (branch head `8b6a998`).
- Tier 2 (docker daemon): not checked; not needed.

## Baseline
`make test` on the untouched checkout (R installed): **5 failed, 3788 passed, 22 skipped**.
All 5 are environmental — `data/mortality_tables/*.csv` absent (see earlier session logs):
`test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface` and four
`test_synthetic_block.py::TestCalibratedPremiums` cases. (An earlier draft of this log named only
the first; five is the complete set.)

## Gap Before
The `quasipoisson(log)` fit-level free-`sp` comparison did not exist (slice 3 measured the
score only). Nothing existing to measure; first reading is the slice's own.

## Hypotheses Tried
1. *Ladder L1's design under `quasipoisson(log)` with an overdispersed count response
   reproduces mgcv's free-sp fit with no new production code.* HELD at tier 1 and tier 3
   on the first measurement. No iteration.
- Probe draft 1 (linear age signal) drove two blocks to mgcv's `sp -> inf` corner
  (sp ~ 1e10, 1e11) — it would have measured the search bound, not the criterion. Replaced
  by a genuinely non-linear signal BEFORE any number was recorded (mgcv sp 2.5e4 / 1.0e6 / 839 / 182,
  none at a bound on the Polaris side).

## Gap After (tier 3, oracle above)
`max_abs_eta_diff` 4.236e-06; `log10(sp)` diff 0.0000 (4dp); `edf_total` diff -0.0000 (4dp);
per-term edf diff 0.0001; mgcv scale 2.009; `converged` both, `at_bound=False`, offset
tripwire 1.332e-15; `agrees=True`. Tier 1: 4.267e-06 / 2.1e-05 / -2.85e-05 / 5.2e-05.

## Provenance
| quantity | Polaris side | mgcv side | class |
|---|---|---|---|
| `eta` | `fit_polaris_gam` at its own selected log_lambda | `m$linear.predictors` of a free-sp REML fit | INDEPENDENT |
| `log10(sp)` (reported) | `select_lambdas_continuous` | `log10(m$sp)` | INDEPENDENT |
| `edf_total` | `PolarisGAMFit.edf_total` | `sum(m$edf)` | INDEPENDENT |
| per-term `edf` | hat-matrix diagonal per term span | `summary(m)$s.table[,"edf"]` | INDEPENDENT |

Mechanical test: `fit_quasipoisson_free_sp_case(r_case: RQuasiPoissonFreeSpRecipe)` — the
recipe type carries no `eta`/`sp`/`edf_total`/`term_edf`/`coef`/`scale`; a test plants hostile
values under each and the fit is bit-identical. mgcv is handed neither sp nor scale. Headline
in the CI report is `evidence_markdown(QUASIPOISSON_FREE_SP_CLAIM)`, not hand-written.

Power check: same design under `poisson` (scale fixed at 1) lands `eta` 0.17 / `edf_total` +7.3 away,
so the comparison would have failed had the criterion ignored dispersion.

## Quality gate
`ruff format`/`check` clean. `tests/test_analytics/test_gam_quasipoisson_conformance.py`
7 passed (incl. the slow R round trip). Full `make test` / `tests/qa` results: see PR body.
No golden touched (no production code changed). `tests/qa`: 85 passed, 9 skipped.
Perf creep verdict: `peak_mib` creep false (33 -> 33); wall-time ratio 1.267x over the 1.25 band,
advisory only — probe ran on a loaded machine and no engine code changed.

## Registered follow-up (2026-09-30, maintainer request on PR #245)
- **Ladder slice 3c** — expose and verify the estimated dispersion, and the two-stage
  Poisson -> fixed-scale quasi-Poisson workflow. Registered in `PLAN_mgcv_capability_ladder.md`
  with a release condition (supersedes the earlier "parked, 3rd-order" note on the accessor).
  Sequenced after slice 7. No severity threshold is imposed: the estimate is reported and the two-stage route is an optional, non-standard user choice.

## Parked Polish (order-classified; none promoted)
- Slice 7 (fixed `scale`) is next; its MEASURE-FIRST hypothesis (`poisson` + `gamma=phi`) is
  untouched here. The scale-fixed-at-1 contrast above is a free by-product data point for it.
- The fit does not expose its own dispersion estimate, so the scale is reported from mgcv
  only, not compared. Registering that as a compared quantity would need a Polaris-side
  Pearson-scale accessor — now registered as slice 3c (see above).

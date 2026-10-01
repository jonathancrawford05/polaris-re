# Dev session log — 2026-10-01 — ladder slice 7: quasipoisson(log) at a supplied fixed `scale`

**Branch:** `claude/intelligent-hamilton-h7d631` (draft PR). **PR title class:** `feat(mgcv-parity)` — lands an INDEPENDENT comparison (which, at the far phi, DISAGREES).

## Claim sentence (written before the code)
Polaris's `fit_polaris_gam` (`poisson(log)`, `gamma=phi`) assembles the three-term design and selects its own four `log10(lambda)` under the known-scale criterion with `gamma` as the fixed `phi`; `mgcv` computes it via `gam(quasipoisson(log), method="REML", scale=phi)`; compared at phi in {2, 6} on `eta`, `edf_total` (ADR-221 gate, imported), `log10(sp)` and per-term edf (reported).

## Oracle Version
- Tier 1: R 4.3.3 / mgcv 1.9.1 (apt; as expected, nothing moved; needed `apt-get update` first).
- Tier 3: R 4.6.1 / mgcv 1.9.4, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, run 36806900876 (head `eff34e9`).
- Tier 2: `docker` binary present; daemon not used.

## Baseline
`make test`: **1 failed, 3799 passed, 22 skipped** — the failure is `test_experience_loaders.py::test_loaded_ilec_feeds_tensor_mi_surface`, environmental (`data/mortality_tables/soa_vbt_2015_male_smoker.csv` absent; the converter's pymort source did not supply it here). The previous log's four `TestCalibratedPremiums` failures did not recur because the converter wrote the tables they need. Final run after this session's changes is the same set.

## Gap Before
No fixed-scale comparison existed.

## Hypotheses Tried
1. *`poisson(scale=phi)` and `quasipoisson(scale=phi)` are the same call in mgcv.* REFUTED (tier 1, re-measured tier 3): `poisson` ignores `scale`, reports 1.
2. *Polaris `poisson`+`gamma=phi` reproduces `quasipoisson(scale=phi)` with no new production code.* HELD at phi=2, REFUTED at phi=6 (tiers agree in verdict).
3. *The phi=6 gap is a criterion difference.* Not supported: gradient ~0 at both points, mgcv's point scores lower under Polaris's criterion, warm start at mgcv's sp stays (tier 1). It is a second stationary point.
4. `multistart=True`, `analytic_gradient`, `step_halving` (tier 1): by-block reaches 6.44 (mgcv 6.45) under multistart but the `ti` blocks land at a different point (score 204.552); the others stay at 205.076. Not closed — registered as slice 7b.
- Probe draft with phi=12 put mgcv's `sp` at ~3e11 (a null-space corner); replaced by phi=6 before any number was recorded, to avoid measuring the bound.

## Gap After (tier 3)
phi=2: `eta` 2.296e-06, `edf_total` +0.0001, `log10(sp)` 0.0000 — agrees. phi=6: `eta` 0.2841, `edf_total` -2.1797, `log10(sp)` 4.2093 — DISAGREES (gate 2e-2 / 1.0). Scores @ Polaris/mgcv sp at phi=6: 205.0760 / 204.2549.

## Provenance
| column | left producer | right producer | class |
|---|---|---|---|
| `eta` | `fit_polaris_gam` at its own selected lambda | `m$linear.predictors` of `quasipoisson(scale=phi)` | INDEPENDENT |
| `log10(sp)` | `select_lambdas_continuous` | `log10(m$sp)` | INDEPENDENT |
| `edf_total` / per-term edf | `PolarisGAMFit` | `sum(m$edf)` / `s.table` | INDEPENDENT |
| `phi` | supplied to both | supplied to both | input, not compared |
| score/gradient table | Polaris's criterion at both sp | (mgcv's sp is a scorer input) | DIAGNOSTIC, not parity |
The fit function's signature takes the recipe type (no `mgcv`-produced key); a test plants hostile values under every such key.

## Quality gate
`ruff format`/`check` clean; new tests 8 passed (incl. slow R round trip at tier 1: near-phi asserted, far-phi recorded not asserted); golden gate and `tests/qa/` run before commit (see PR). No `perf/history.jsonl` row. A first draft claimed the amendment-1 exemption while this PR added a module under `src/polaris_re/analytics/` (review P1-1: not exempt as worded); a row was appended, then — after the maintainer authorized widening the rule — withdrawn in the same unmerged PR under **ADR-177 amendment 2** (conformance-only modules outside the probe's import closure are exempt). Mechanical check run: the changed `src/` file is `gam_quasipoisson_fixed_scale_conformance.py`, referenced only by tests and CI.

## Follow-ups
Slice 7b registered (PLAN). Slice 3c unaffected except that the fixed mode is verified only near the free estimate.

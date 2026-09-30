# Dev session log — 2026-09-28 — ladder slice 6: `cr` + `re` + `ti` joint composition

Branch: `claude/intelligent-hamilton-x89mos`. Routine: `docs/ROUTINE_MGCV_PARITY.md`. Work selection: PLAN_mgcv_capability_ladder.md
Slice 6 (the CONTINUATION's stated next slice). Title class: **feat** (INDEPENDENT).

## Baseline
`make test`: 5 failed / 3756 passed / 39 skipped (R was still installing, hence the extra
skips). The 5 failures are the standing missing-mortality-table failures, identical to the
previous parity session's stated baseline (`data/mortality_tables` absent). PROCEED.
`tests/qa/`: 85 passed, 9 skipped, goldens intact.

## Oracle Version
- Tier 1: R 4.3.3 / mgcv 1.9.1 (apt; first install needed `apt-get update`), `OPENBLAS_NUM_THREADS=1`.
- Tier 2: unavailable (`docker` binary, no daemon).
- Tier 3: R 4.6.1 / mgcv 1.9.4, oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`, run 36476048762 (workflow_dispatch on the branch, head fc72fd1).
- Note: ROUTINE_MGCV_PARITY.md and the registered prompt agree on facts; no staleness found.

## Gap Before
Unmeasured: no committed measurement of the three bases fit together. Nothing to
quantify numerically; the composition itself was the open question.

## Hypotheses Tried
1. *The three verified producers compose without any new production code.* One change: a new
   conformance module + probe (no `src/` production change). HELD on first measurement at
   tier 1 and tier 3. No iteration.
2. (Design tweak, not a hypothesis) first draft response surfaces had near-linear age terms so
   `cr` smoothing parameters hit 1e4-1e9; the probe's data was made genuinely nonlinear
   before any Polaris comparison so the blocks are identified.

## Gap After
Tier 3: fixed-sp `eta` diff 2.515e-14, `edf_total` diff -1.421e-13. Free sp: gaussian
`eta` 6.119e-07, poisson `eta` 2.960e-05, `log10(sp)` ≤ 1e-4, per-term edf ≤ 1e-4. All agree. Tier 1 identical in verdict.

## Provenance
| comparison | left | right | column | class |
|---|---|---|---|---|
| fixed sp | `penalized_irls_general` on `assemble_model_design` (cr+re+ti producers) at supplied sp | `mgcv::gam(sp=)` `linear.predictors` | eta | INDEPENDENT |
| fixed sp | Polaris hat-matrix trace | `sum(m$edf)` | edf_total | INDEPENDENT |
| free sp | `fit_polaris_gam` own REML selection | `gam(method="REML")` | eta, log10(sp) per block, edf_total, per-term edf | INDEPENDENT |
The fit functions take recipe types with no mgcv-output keys (tested structurally and by stripping). `sp_fixed` is an input to both sides. The s.table row-order check is an alignment guard, not a compared quantity. Coefficients never compared.

## Quality gate
ruff format/check clean (unrelated script reformatting reverted); mypy clean on the new module; 16 new tests pass; `tests/qa/` byte-identical goldens. `perf/history.jsonl` row appended (PR touches `src/`). Creep verdict (PR #244 review re-run): no structural creep, `peak_mib` creep false, wall-time ratio 1.141 against band 1.25.

## Follow-ups
- Slice 6b registered in the PLAN (`select=TRUE` on the composition; needs maintainer confirmation).
- Next PLAN slices: 3b then 7 (quasi-Poisson dispersion).
- Limits: one dataset/seed; poisson(log) stands in for quasi-Poisson.

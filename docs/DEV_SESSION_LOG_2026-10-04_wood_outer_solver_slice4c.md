# Dev session log — 2026-10-04 — outer-solver slice 4c, part 1 (gate exit-path test, case 5 thread axis)

**Branch:** `claude/intelligent-hamilton-nptc63`. **PR title class:** `harness(mgcv-parity)` — nothing INDEPENDENT landed. **Perf:** no row (ADR-177 amendment 2: the only `src/` file touched is `gam_newton_gauntlet_conformance.py`, a `*_conformance.py` module outside the probe closure; ADR-246's `sys.modules` check on it returned `[]`; not re-run this session).
**Registered-prompt vs ROUTINE file:** the box says the epic is at ADR-207 and to take the parity PLAN's next slice; the ROUTINE file's ACTIVE EPIC POINTER (ADR-241) names `PLAN_wood_outer_solver.md`, now at ADR-246. ROUTINE file wins; the box is stale (maintainer edit).

## Baseline
`uv run pytest tests/ -m "not slow"` (R installed): the run was stopped at the first failure (`-x`): `test_loaded_ilec_feeds_tensor_mi_surface`, FileNotFoundError for `data/mortality_tables/soa_vbt_2015_male_smoker.csv` — the standing generated-table failure class (pymort source unavailable). 590 passed before it. After the change: `tests/test_analytics/test_gam_newton_gauntlet_conformance.py` 25 passed (+5 new); `tests/qa/` 85 passed, 9 skipped, goldens untouched.

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1 (apt after `apt-get update`), `OPENBLAS_NUM_THREADS=1`. Tier 2 unavailable (docker binary, no daemon check beyond `docker info` header). Tier 3: run 37232079212 on `7258f0f`, R 4.6.1 / mgcv 1.9.4, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`. The job succeeded; step output was read from the job log (the run-level log endpoint is blocked by the proxy).

## Gap Before
Gate exit path untested (PR #255 review). Case 5 (reproducibility) measured on `select=TRUE` only (ADR-244); the other eight Newton cases had no thread-axis reading.

## Hypotheses Tried
1. The Newton search is thread-reproducible on every gauntlet case, not only `select=TRUE`. **HELD**: tier 1 then tier 3, worst d eta 3.6e-08. No failures to record; no tolerance touched; no start strategy added.

## Gap After
Case 5 thread axis: measured on all nine cases (ADR-247). Seed axis: no operand. Not closed: `epsilon_rel` question, INDEPENDENT `log10(sp)` reading on `select=TRUE`, default flip, `evidence_markdown` DoD table.

## Provenance
- **Thread axis, `eta` / `log10(sp)` / `edf_total`: Polaris vs Polaris, same producer at different BLAS thread counts.** Not INDEPENDENT, not ECHO, not TRANSPORT — there is no `mgcv` side and no `VerificationClaim`; reported as a MEASUREMENT (own criterion). Mechanical test: the producing function's signature takes the recipe payload only; the comparison is between two of its own outputs.
- The gate exit-path tests compare no numbers against `mgcv`; they test control flow with monkeypatched readings.

## DoD (PLAN Slice 4, verbatim, with evidence)
- [x] case 1, six free-scale cells, one start — ADR-245; unchanged by this slice.
- [x] case 2, fixed scale=6, blocking CI step — ADR-246; exit path now unit-tested (`test_gate_flag_*`); never seen failing in CI.
- [x] case 3, `select=TRUE` N=7 — ADR-245.
- [x] case 4, 4-term HGAM — ADR-246.
- [~] case 5, both reproducibility axes — thread axis MET on nine cases, tier 3 (ADR-247, own criterion); seed axis NOT MET because Newton has no seed operand.
- [ ] `epsilon_rel` / curvature-to-noise put to the maintainer — NOT MET, not run this session.
- [ ] default flip; `[machine]` gauntlet table via `evidence_markdown()` — NOT MET (no flip).
- [x] goldens byte-identical — `pytest tests/qa/`: 85 passed, 9 skipped; no change under `tests/qa/golden_outputs/`.
- [x] `[judgement]` reliability claim names axes, cases, tolerance — ADR-247 "Not claimed"; no unqualified "reliable".

## Open / follow-ups
Slice 4c continues: the INDEPENDENT `log10(sp)` comparison on `select=TRUE` (the thread axis shows it is the least stable column, 7.3e-04), `epsilon_rel` to the maintainer, then the default flip. Mechanism class (iii) is already owned by this epic; no new slice registered.

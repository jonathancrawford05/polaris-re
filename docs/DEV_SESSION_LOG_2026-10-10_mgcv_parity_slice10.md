# Dev session log — 2026-10-10 — mgcv parity: Slice 10 (reproduce `mgcv`'s pivot) — BLOCKED AT STEP 1

**Branch:** `claude/dreamy-galileo-2j6swv` (environment-designated; draft PR). **PR title class:** `harness(mgcv-parity)` — no comparison against `mgcv` was landed; docs only. **Box vs repo:** the box names no epic; the repo's pointer (PLAN Slice 10, "next session after PR #263 merges"; #263 is merged at `2ec15aa`) was followed. No conflict on fact.
**Perf:** no row (nothing under `src/polaris_re/` changed; ADR-177 amendment 1).

## Baseline
Code unchanged since the Slice 9 close: full-suite baseline stands at the last log (5 failed environmental, 4069 passed, 22 skipped, 145 deselected). Not re-run: this session changed only `docs/`.

## Oracle Version
Tier 1 only: R 4.3.3 / mgcv 1.9.1 (apt), as expected. No tier-3 dispatch (nothing committed as a number).

## Gap Before / Gap After
Unchanged: `Vc` refused for pivoted fits; per-term edf of `gaussian_factor_by_with_bare_smooth` off by 1.002 (tier 3, run 37977750939, `sha256:0d54c192…`). No number moved.

## Hypotheses Tried (all tier 1, ledger 2026-10-10)
1. `gam.side()`/`fixDependence()` drops the column: REFUTED by reading its R code and `del.index` (no-op: by-level names are distinct).
2. The pivoting is in R code: REFUTED, it is in compiled `C_pls_fit1`/`C_gdi1`; source unavailable (CRAN fetch refused). Step 1 cannot be met; stopped rather than infer a rule from outputs.
3. Smallest unpenalised-column norm picks the dropped level: REFUTED (1 of 9 cells).
4. Dropped level stable under factor-level reorder: INCONCLUSIVE (edf-0 is a weak observable).
No tolerance, constant or test touched.

## Provenance
No comparison reported. The tier-1 sweeps are MEASUREMENTS of `mgcv` against itself (reordered / redrawn data), not parity; no Polaris producer was involved.

## Definition of done (PLAN Slice 10)
All four steps and the acceptance: **NOT MET, because** step 1 (mechanism with function and lines) needs `mgcv`'s C source, which this environment cannot obtain; steps 2-4 depend on it.

## Follow-ups
Q12 in the CONTINUATION (recommended: allow a read-only fetch of the mgcv source). Nothing else opened.

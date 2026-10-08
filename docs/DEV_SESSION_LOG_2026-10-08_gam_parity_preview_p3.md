# Dev session log — 2026-10-08 — GAM parity preview: Slice P3 (formula front end, refusal list)

**Branch:** `claude/dreamy-galileo-lzuua1` (the environment-designated branch). **PR title class:** `feat(mgcv-parity)` — every compared column is INDEPENDENT.
**Box vs repo:** the registered box names no epic; the repo's active-epic pointer named `PLAN_gam_parity_preview.md`, next slice P3. Repo followed; no conflict on fact.
**Perf:** one row appended (ADR-177): the PR adds `src/polaris_re/gam/{api,formula}.py`, neither a `*_conformance.py` module.

## Baseline
No mortality tables here, so five environmental failures stand (`test_loaded_ilec_feeds_tensor_mi_surface`, four `TestCalibratedPremiums`). **Before** (previous parity log): 3952 passed, 5 failed, 22 skipped, 145 deselected. **This session's start (R installed, new package present but untested):** 3953 passed, 5 failed, 22 skipped, 145 deselected (`-m "not slow"`, whole `tests/`, incl. `tests/qa/` — goldens untouched; +1 pass = the R-gated end-to-end test flipping from skipped, per the routine). **After:** **4025 passed, 5 failed, 22 skipped, 145 deselected** (same five failures; +72 = the new `tests/test_gam/` tests; goldens untouched)..

## Oracle Version
Tier 1: R 4.3.3 / mgcv 1.9.1, `LC_COLLATE=C` (after `apt-get update`). Tier 3 (every committed number): CI run 37770947784 (commit `45971de`) and re-run 37772378216 (commit `d736e9d`), mgcv 1.9.4 / R 4.6.1, `LC_COLLATE=en_US.UTF-8`, `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`.

## Gap Before
`fit_polaris_gam` callable only with a hand-built `ModelSpec`; no formula parser, no factor coding from a DataFrame, no refusal list. Starting gap for the new columns: none existed.

## Hypotheses Tried
1. `gam(<formula string>)` reproduces `mgcv::gam(<same string>)` on eta/edf (ADR-221) and exactly on structure and level order. Tier 1: held on 10 cells. Tier 3 run 1: held on 9 of 10 fitted cells; **level order DISAGREED** on the mixed-case/numeric-string cell.
2. R's collation on the oracle is `C`. **Refuted at tier 3**: the image runs `en_US.UTF-8`; R sorts `[b,B,a,A,10,9,_z,Z]` as `[_z,10,9,a,A,b,B,Z]` (tier 1 gave the `C` order, which is why tier 1 could not settle it).
3. `en_US` order is `_` < digits < letters, letters case-insensitive, lowercase first on a tie. HELD at tier 3, run 37772378216 (`d736e9d`): `gaussian_level_order` level order True, eta 5.558e-08.
4. `s(x) + s(x, by=f)` is refused by the structural test (null space of `sum S_j` unseen by `X`) and `f + s(x, by=f)` is fitted. Held (1 direction; identified spelling eta 7.5e-08).
No tolerance was touched.

## Gap After
All 10 fitted cells agree with `mgcv::gam(<same string>)` on eta (<= 6.2e-04), `edf_total` (<= 9.5e-03), exact term structure and exact level order; the rank-deficient cell is refused as expected. Open: the `en_US` rule is verified on one 8-string sample; `select=TRUE` with `re`/parametric terms is refused (question 4); `log10(sp)` up to 0.89 on plateau rows (reported only).

## Provenance
All columns INDEPENDENT (`FORMULA_CLAIM`; headline from `evidence_markdown`). Left producer: `polaris_re.gam.gam` via `fit_formula_case(recipe: FormulaRecipe)` — formula string, family, data columns (factors as strings); no mgcv output is a key (pinned by test). Right producer: `mgcv::gam(as.formula(<same string>), method="REML")` with R's own `factor()`. Per column: eta, `edf_total` (INDEPENDENT, gated ADR-221); smooth labels / `bs.dim` / coefficients per smooth / `nsdf` (INDEPENDENT, exact; Polaris reads its parser and design blocks, R reads `m$smooth`); factor level order (INDEPENDENT, exact); per-smooth edf and `log10(sp)` (INDEPENDENT, reported). Neither side is handed anything the other produced. The `gaussian_factor_by_with_bare_smooth` row is an expected refusal: "agrees" means Polaris refused on the structural condition; mgcv's fit is carried, not compared. `tests/test_gam/` is MEASUREMENT (own criterion), not parity.

## Definition of done (PLAN P3)
- Parses the verified subset (`s(bs="cr")`, `by` numeric/factor, `ti`, `re`, `a + b + a:b`, `offset`): **MET** — `tests/test_gam/test_formula.py::test_parses_the_verified_subset`, run 37770947784.
- Bare `s(x)` refused, explicit equivalent accepted: **MET** — `test_a_bare_smooth_is_refused_and_its_explicit_equivalent_is_accepted`.
- Factor coding reproduces R's; mixed-case and numeric-string ordering pinned against an R probe: **MET after one correction** — `gaussian_level_order`, run 37772378216 (ADR-251 decision 5).
- INDEPENDENT `[machine]` same-formula-string comparison on eta/`edf_total` for every gauntlet formula, plus structure column: **MET on the 10 fitted cells** (the six free-scale cells and the HGAM are among them). **Not the Wood gauntlet's ten rows verbatim**: the formulas are the P1/P2 probe cells re-expressed as strings, plus a weights cell, a `select=TRUE` cell, a factor-`by` cell and a level-order cell.
- Refusal list `[machine]`, one test per construct: **MET** — `test_every_refused_construct_is_refused_by_name` (31 parametrised constructs) and the `test_api.py` refusals.
- `polaris_re.gam` depends on `analytics`, never the reverse: **MET** — `test_analytics_never_imports_the_gam_facade`.

## Maintainer questions
4 (new): `select=TRUE` with `re`/parametric/factor-`by` terms is refused, yet P4's target fit needs it. Recommended answer in the CONTINUATION. Work that does not depend on it continues (P4).

## Follow-up (same session): `select=TRUE` scope, ADR-252
On the maintainer's question the refusal was re-examined: it is a verification gap, not `bam`. Lifted for `re` and parametric terms; two new INDEPENDENT cells, tier 3 run 37779421820 (`cfab000`), both agree (eta 5.4e-07, 3.7e-04). Factor-`by` stays refused. `tests/test_gam/` 72 passed locally; the full-suite count above predates this change (test count unchanged, 72 -> 72: one test replaced by two, one removed).

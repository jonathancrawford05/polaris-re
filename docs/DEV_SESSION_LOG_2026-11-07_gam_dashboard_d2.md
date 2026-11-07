# Dev session log — 2026-11-07 — GAM dashboard slice D2 (`harness`-class: no mgcv comparison)

**Routine:** `docs/ROUTINE_MGCV_PARITY.md` (active epic pointer: `docs/PLAN_gam_dashboard.md`).
**Branch:** `claude/dreamy-galileo-6yhuo3` (environment-designated). **Slice:** D2, one slice, six checkpoints, ADR-263.
**PR title class:** this slice lands NO `mgcv` comparison. Its one comparison is HGAM vs a CLOSED FORM (INDEPENDENT producers, truth recovery, not parity), so the PR is titled `harness(...)`-style by the routine's rule, not `feat(mgcv-parity)`.

**Box vs repo.** The box names no epic; the repo pointer names `PLAN_gam_dashboard.md`, D1 merged, D2 planned with the maintainer's go recorded in the PLAN ("given in conversation 2026-11-07, to be confirmed on the D2 PR"). Taken as the release condition being met. Nothing disagreed.

## Oracle Version
Local scratch oracle (tier 1): R 4.3.3 / mgcv 1.9.1 (apt, as expected). **Not used for any number**: this slice compares against a closed form, no `mgcv` call was made, no tier-3 CI dispatch was needed. No digest applies.

## Gap Before / Gap After
Not a parity epic and no `mgcv` gap exists for this scope. Before: the page's views were the older model's; no HGAM partial effects or improvement surface existed. After: both exist, with a truth-recovery check. Nothing here moved a parity number.

## Provenance
| quantity | left producer | right producer | classification |
|---|---|---|---|
| `mi_age_year` | test generator closed form `1 - exp(-(b0 + b1 (age-40)))` | `improvement_surface` on `gam()` / `bam` fit | INDEPENDENT (closed-form truth, not mgcv) |
| `band_coverage` | the same closed form (inside/outside) | `improvement_surface` delta-method band `D Vp D^T` | INDEPENDENT (same) |
| test (a) `MI = 0.015` on the built-in sample | the sample's generating law | `improvement_surface` on `gam()` fit | INDEPENDENT (same) |
| `partial_effects` closed-form checks (sine, factor shifts) | generating function in the test | `partial_effects` on `gam()` fit | INDEPENDENT (closed form) |
| surface vs public `predict` contrast | `fit.predict` at two frames | `improvement_surface` | NOT independent: both read the same fit. Internal-consistency check (MEASUREMENT), not evidence of correctness |
| `d_se` / `partial_effects.se` | no second producer | `Vp` of the same fit | MEASUREMENT (own criterion) |

The auto-generated headline below says "Parity comparison" because that is `evidence_markdown`'s wording for two independent producers; the claim sentence under it limits the claim to closed-form recovery.

**Parity comparison** — independently produced on both sides: `mi_age_year`, `band_coverage`.

*Claim:* The data generator computes MI_x(y) from its closed-form improvement law; improvement_surface computes MI_x(y) from the HGAM fitted to a draw of that data; compared on MI at each (age, year) cell and on band coverage. Closed-form truth recovery, not mgcv parity.

| quantity | left producer | right producer | provenance | parity evidence |
|---|---|---|---|---|
| `mi_age_year` | test generator closed form 1 - exp(-(b0 + b1 (age - 40))) | polaris_re.gam.effects.improvement_surface on gam()/bam fit | INDEPENDENT | yes |
| `band_coverage` | test generator closed form (truth inside or outside) | improvement_surface delta-method band D Vp D^T | INDEPENDENT | yes |

| engine | seed | max abs z (<=4.5) | coverage (>=0.75) | max abs MI error | edf |
|---|---|---|---|---|---|
| gam | 20260101 | 2.76 | 0.852 | 0.0062 | 6.0 |
| gam | 20260102 | 1.80 | 1.000 | 0.0041 | 5.6 |
| gam | 20260103 | 1.89 | 1.000 | 0.0016 | 4.8 |
| gam | 20260104 | 0.64 | 1.000 | 0.0005 | 4.4 |
| gam | 20260105 | 1.75 | 1.000 | 0.0028 | 4.5 |
| gam | 20260106 | 0.86 | 1.000 | 0.0005 | 4.0 |
| gam | 20260107 | 0.83 | 1.000 | 0.0017 | 4.9 |
| gam | 20260108 | 2.76 | 0.791 | 0.0056 | 5.2 |
| gam | 20260109 | 2.09 | 0.968 | 0.0038 | 5.3 |
| gam | 20260110 | 0.81 | 1.000 | 0.0007 | 4.2 |
| bam | 20260101 | 2.76 | 0.852 | 0.0062 | 6.0 |
| bam | 20260102 | 1.80 | 1.000 | 0.0041 | 5.6 |
| bam | 20260103 | 1.89 | 1.000 | 0.0016 | 4.7 |

mean coverage gam 0.961 (>=0.90); bam 0.951

## Hypotheses Tried
No convergence loop (no gap to close). One pre-registered test family, run once, nothing tuned between runs; all bounds met (ADR-263 amendment 1 holds the derivations and the results). Honest reading: the band over-covers (7/10 `gam` seeds at 1.000, mean 0.961) and the generator is smooth and bilinear, so this does not show recovery of a sharply varying surface. Not examined: the `slogdet` warnings on the `gam` path (open from D1).

## What shipped
`polaris_re/gam/effects.py` (`partial_effects`, `improvement_surface`, `truth_recovery_claim`); page: HGAM section leads, partial effects replace link profiles, MI surface + band-width map + CSV download, `q_base` offset (`log_expected`), old views inside an expander labelled "Legacy model ... (not the HGAM above)". Old model code untouched; goldens not re-pointed (no pricing path calls any of this).

## Baseline
Full run, `pytest tests/ -m "not slow"` (no `-x`), with R installed, after the D2 changes: **5 failed, 4236 passed, 22 skipped, 147 deselected** (556.75 s). The 5 failures (`test_experience_loaders::test_loaded_ilec_feeds_tensor_mi_surface`, 4 x `test_synthetic_block::TestCalibratedPremiums`) fail identically on the pre-change base `05333c1` (re-run in a clean worktree): `FileNotFoundError: data/mortality_tables/soa_vbt_2015_male_smoker.csv` -- the mortality-table CSVs are not converted in this environment. Standing environment failures, not caused by D2. The 4 new slow truth tests pass when run with `-m "slow or not slow"` (also run via `scripts/gam_d2_truth_report.py`). The `tests/qa` goldens ran inside this suite and passed (byte-identical, nothing re-pointed).

## Quality gate
`ruff format`, `ruff check`: clean. mypy on the new module: clean (`scipy.stats` avoided; `statistics.NormalDist` used).

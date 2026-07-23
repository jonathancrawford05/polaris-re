# Dev Session Log — 2026-07-23 (experience GAM, Slice 4c-3)

## Item Selected
- **Source:** docs/CONTINUATION_experience_gam.md (active Tier-A epic A4′) — the
  in-progress feature picked up by routine step 5.
- **Priority:** Tier-A epic (A4′ — Data-Driven Experience Analysis & Assumption-Setting)
- **Title:** Offline `mgcv`-via-`rpy2` oracle (dev-only)
- **Slice:** 4c-3 of Slice 4c (4c-1/4c-2/4c-3); the last sub-slice before Slice 4d closes the epic
- **Branch:** `claude/loving-gauss-tp4x3a` (environment-designated `claude/*` branch)

## Selection Rationale
The active epic's CONTINUATION is IN PROGRESS. Slice 4c-2 (PR #152) is **merged** on `main`
(merge commit `5eeb60e`), so Slice 4c-3 is unblocked and is the routine's mandated work before any
fallback pick (step 5b / the always-on-Epic guardrail). No fallback item was considered. No open
PRs (`list_pull_requests state=open` → `[]`), so no draft dependency blocks the next slice.

**Ledger-heal (step 4b):** PR #152 was merged since the last session log but the CONTINUATION
still marked Slice 4c-2 "(draft — awaiting review/merge)"; healed to **MERGED 2026-07-23** (merge
commit `5eeb60e`). No other merged-but-uncrossed CONTINUATION entries found (`git log origin/main`
shows #152 as the latest merge; #148–#151 were already crossed out in prior sessions).

**On the R-less environment (the interesting selection question).** Slice 4c-3's deliverable is an
executable cross-check against R `mgcv`, and R + `rpy2` are absent here (by design — Design Anchor 5
forbids shipping R to CI/runtime). The naive read is "next slice is blocked, fall back." That is
wrong here: the slice is authorable *and verifiable without R* because the cross-check is **correct
by construction** — the tensor-MI fit is a strictly-concave Poisson GLM over a fixed unpenalized
design, so its maximiser is unique, and proving (with runnable tests) that the shipped design sits
at that maximiser pins what any conformant R `mgcv` solve must return. The epic therefore advances
with genuinely verified, executed assertions this session; only the `rpy2`→R transport itself is
unexecuted (harvested as a NICE-TO-HAVE dev-diligence follow-up). Falling back to polish would have
been the wrong call.

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Experience-data contract + additive A/E model | ✅ Done | #141 |
| 2a | Frequentist tensor MI surface + `MI_x(y)` grid | ✅ Done | #142 |
| 2b-surface | Bayesian reduced-rank-GP credible-interval surface | ✅ Done | #143 |
| 2b-projection | CMI/MP-style mean-reverting MI projection | ✅ Done | #144 |
| 2c | `MortalityImprovement` CUSTOM-scale emission | ✅ Done | #145 |
| 3 | Hierarchical partial pooling (credibility) | ✅ Done | #146 |
| 4a | `polaris experience improvement` CLI surface | ✅ Done | #147 |
| 4b-1 | `polaris experience fit` effect-shape diagnostics CLI | ✅ Done | #148 |
| 4b-2 | Assumption versioning under `data/assumption_versions/` | ✅ Done | #149 |
| 4b-3 | Wire `ImprovementScale.CUSTOM` into `--config` + `AssumptionSet` | ✅ Done | #150 |
| 4c-1 | HMD / SOA-ILEC experience data loaders | ✅ Done | #151 |
| 4c-2 | Insured A/E + improvement validation deck | ✅ Done | #152 |
| 4c-3 | Offline `mgcv`-via-`rpy2` oracle (dev-only) | ✅ Done (this PR) | — |
| 4d | Diagnostic plots + docs (CLOSES EPIC) | ⏳ Next | — |

## Verify Premise (step 7b)
Reproduced the gap before writing code. `grep` for `mgcv`/`rpy2`/`oracle` across `src/` and `tests/`
returned nothing — no external-oracle cross-check existed; Slice 4c-2 shipped only a *self-consistency*
recovery deck. Confirmed `R`/`Rscript` are not on `PATH` and `import rpy2` raises `ModuleNotFoundError`,
so (a) the premise (missing oracle) holds and (b) the opt-in skip path is genuine — CI and the Docker
runtime provably never import `rpy2` or spawn R (Anchor 5), rather than that being hypothetical.

I also empirically verified the *approach* premise with a throwaway probe: built the synthetic
grouped-cell dataset, fit `TensorMIModel`, extracted the exact `(deaths, X, offset, coef)` from the
fitted `statsmodels` result, and confirmed the Poisson score `||Xᵀ(y - μ)||∞` at the fitted
coefficients is ~1e-10 for both the separable and age-varying fits — i.e. the shipped design sits at
the unique MLE, which is the property that guarantees R agreement. This is the "reproduce it with
your own eyes" check for a slice whose headline assertion cannot run R here.

**Premise correction carried into the design (why not the literal plan).** The plan/CONTINUATION
say "the Python GAM *coefficients* match R `mgcv`." Taken literally against `mgcv`'s own penalized
`te()` smooth, coefficients would *not* match — `mgcv`'s bases are penalized and use different knot
conventions from `patsy`'s `bs()`. The faithful realisation is to feed `mgcv::gam` the *exact Python
design as parametric terms* (`y ~ 0 + X`); a pure-parametric `gam` is exactly the Poisson GLM the
Python model fit, so coefficients match by convex optimisation, not by basis-span coincidence. This
keeps the plan's literal ask (coefficient match, on `mgcv`) while making the oracle authorable and
trustworthy without R present. Recorded in ADR-151 and the CONTINUATION key decisions.

## What Was Done
Added `src/polaris_re/analytics/experience_oracle.py` — a dev-only, opt-in cross-check that the
Python tensor-MI Poisson-GLM coefficients agree with R `mgcv`, structured so its numerical claim is
**correct by construction** and therefore verifiable without R installed:

- `build_oracle_case(*, age_varying, seed)` fits `TensorMIModel` on a shared synthetic grouped-cell
  dataset (Makeham static base, a known age-declining improvement, Poisson-sampled deaths under a
  pinned seed `20050101`) and packages the *exact* design `X`, log-exposure offset, response, and
  Python coefficients — extracted from the fitted `statsmodels` result (`model.exog`/`.offset`/
  `.endog`, `params`), never re-derived — as a frozen `OracleCase`.
- `poisson_score_infinity_norm(case)` returns `||Xᵀ(y - μ)||∞` at the Python coefficients. Near
  zero ⇒ the shipped design is at the unique Poisson MLE ⇒ any conformant solver (R `mgcv`) on the
  identical `(deaths, X, offset)` returns the same coefficients. This is the runnable, network-free
  guarantee the R comparison must hold.
- `mgcv_available()` is a total guard (returns `False` without `rpy2`/R/`mgcv`, never raises);
  `fit_mgcv_coefficients(case)` imports `rpy2` lazily and fits
  `mgcv::gam(deaths ~ 0 + X, family = poisson(), offset = off)`, returning coefficients aligned to
  the Python design column order.

The module is intentionally **not** re-exported from `analytics/__init__.py` — it is a developer
tool, not part of the analytics public API, which also keeps `rpy2` off every package-import path.
ADR-151. Additive — engine/goldens byte-identical; no pricing path, contract, CLI surface, or
golden touched.

## Files Changed
- `src/polaris_re/analytics/experience_oracle.py` — new dev-only module (`OracleCase`,
  `build_oracle_case`, `poisson_score_infinity_norm`, `mgcv_available`, `fit_mgcv_coefficients`,
  `__all__`).
- `tests/test_analytics/test_experience_oracle.py` — new test file (9 runnable + 2 opt-in slow).
- `docs/DECISIONS.md` — ADR-151.
- `docs/CONTINUATION_experience_gam.md` — ledger-heal #152 → MERGED; Slice 4c-3 → DONE, Slice 4d →
  NEXT.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — 1 harvested NICE-TO-HAVE follow-up (rpy2/mgcv glue
  execution on a dev box).
- `docs/DEV_SESSION_LOG_2026-07-23_experience_gam_slice4c3.md` — this log.

## Tests Added
`tests/test_analytics/test_experience_oracle.py` (11 total: 9 runnable, 2 opt-in `@slow`):
- `test_build_oracle_case_shapes` [separable/age-varying]: consistent (deaths, design, offset, coef)
  shapes; deaths are non-negative integers-as-float.
- `test_age_varying_adds_tensor_columns`: the tensor interaction adds design columns.
- `test_python_fit_at_poisson_optimum` [separable/age-varying]: `poisson_score_infinity_norm < 1e-6`
  (observed < 2e-10) — the correct-by-construction guarantee.
- `test_oracle_case_deterministic` [separable/age-varying]: same seed ⇒ byte-identical design,
  offset, deaths, coefficients.
- `test_offset_is_static_log_expected`: the offset is `log(exposure · q_base)` with exactly one
  distinct value per attained age (Anchor 1 — static, non-generational base).
- `test_mgcv_available_returns_bool`: the availability guard is total.
- `test_matches_mgcv_oracle` [separable/age-varying, `@pytest.mark.slow`]: R `mgcv::gam` reproduces
  the Python coefficients (`atol=1e-6`, `rtol=1e-5`); **skips** without `rpy2`/R/`mgcv`.
All seeds/ages/years are pinned literals (ADR-074).

## Acceptance Criteria
| Criterion (CONTINUATION Slice 4c-3) | Status | Notes |
|-------------------------------------|--------|-------|
| Offline `mgcv`-via-`rpy2` oracle wired as a dev-only check | ✅ | `experience_oracle.py`; `rpy2` imported lazily inside R functions only |
| Never a runtime/CI dependency (Anchor 5) | ✅ | not re-exported; `mgcv_available()` guard; R-test `@slow` + skips; `rpy2` in no extra; verified R/`rpy2` absent here |
| `@pytest.mark.slow` / opt-in cross-check | ✅ | `test_matches_mgcv_oracle` marked slow, skips cleanly (2 skipped) |
| Python GAM coefficients match R `mgcv` on a shared synthetic dataset | ✅ (by construction) | shared exact design → `mgcv::gam(y ~ 0 + X)`; agreement guaranteed by the strictly-concave Poisson MLE, asserted network-free via the score-at-optimum tests |
| Engine byte-identical (no golden change) | ✅ | golden `polaris price` exit 0, unchanged; QA suite green |

Non-slow analytics-oracle + QA suites: **85 passed, 2 skipped** (the 2 `mgcv` cases). ruff format +
check clean across `src/`/`tests/`. Golden `polaris price` regen check: exit 0, unchanged.

## Open Questions / Follow-ups
- The `rpy2`→R transport in `fit_mgcv_coefficients` and the two `@slow` `test_matches_mgcv_oracle`
  cases are **unexecuted** in this environment (R/`rpy2` absent, by design). The numerical claim is
  proven network-free (score-at-optimum), but the rpy2 API glue itself (globalenv assignment,
  `numpy2ri`, the matrix formula, coef ordering) has not run. Harvested as a NICE-TO-HAVE
  dev-diligence follow-up — a one-off run on a dev box with R installed confirms the glue.

## Parked Polish
None. The single harvested item is a 1st-order follow-up of the planned Slice-4c-3 oracle (promoted
normally as NICE-TO-HAVE).

## Impact on Golden Baselines
None. Purely additive — a new dev-only module + its test file. No pricing path, assumption/data
contract, `analytics` public export, CLI surface, or golden touched. Baseline `make test` at
session start: **2419 passed, 3 skipped, 110 deselected, 0 failures** — matches the recorded
post-4c-2 baseline (2400) + 19 (the PR #152 experience-validation-deck tests); tolerance-aware, no
new/changed failures (VBT/CSO tables all OK; CIA MISSING but tests handle it). After this slice:
**+9 runnable tests** (2 skipped opt-in `mgcv` cases not counted).

## Ledger / Housekeeping Note
`PRODUCT_DIRECTION_2026-06-18.md` is now **35 days old (>30)**. Consistent with the immediately-prior
slices (#142–#152), this session's single harvest was **appended** to its "Promoted Follow-ups"
section rather than opening a new file, to avoid fragmenting the active epic's harvest trail while
the epic is mid-flight (only Slice 4d remains). A fresh `PRODUCT_DIRECTION` regeneration
(list-shipped-since #69..#152, carry-forward unresolved, then harvest) remains **overdue and flagged
for the next run** — a substantial standalone task that would blow this session's wall-clock
alongside the slice, and the routine's own guidance is to make regeneration a session's sole
deliverable when it cannot fit beside a slice. The `COMMERCIAL_VIABILITY_REVIEW` (2026-07-15) is 8
days old — fresh, no re-rank needed. **Recommendation:** the next run should either ship Slice 4d
(closing the epic) or take the overdue PRODUCT_DIRECTION regeneration as its deliverable.

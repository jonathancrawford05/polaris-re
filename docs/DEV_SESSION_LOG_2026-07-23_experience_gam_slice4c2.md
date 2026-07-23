# Dev Session Log — 2026-07-23 (experience GAM, Slice 4c-2)

## Item Selected
- **Source:** docs/CONTINUATION_experience_gam.md (active Tier-A epic A4′) — the
  in-progress feature picked up by routine step 5.
- **Priority:** Tier-A epic (A4′ — Data-Driven Experience Analysis & Assumption-Setting)
- **Title:** Insured A/E + improvement validation deck
- **Slice:** 4c-2 of Slice 4c (4c-1/4c-2/4c-3); Slice 4 of the 4-slice epic
- **Branch:** `claude/loving-gauss-6gxn54` (environment-designated `claude/*` branch)

## Selection Rationale
The active epic's CONTINUATION is IN PROGRESS. Slice 4c-1 (PR #151) is **merged** on `main`
(merge commit `dd6e725`), so Slice 4c-2 is unblocked and is the routine's mandated work before
any fallback pick (step 5b / the always-on-Epic guardrail). No fallback item was considered. No
open PRs (`list_pull_requests state=open` → `[]`), so no draft dependency blocks the next slice.

**Ledger-heal (step 4b):** PR #151 was merged since the last session log but the CONTINUATION
still marked Slice 4c-1 "(draft — awaiting review/merge)"; healed to **MERGED 2026-07-23** (merge
commit `dd6e725`). No other merged-but-uncrossed CONTINUATION entries found (`git log origin/main`
shows #151 as the latest merge; #148/#149/#150 were already crossed out in the 4c-1 session).

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
| 4c-2 | Insured A/E + improvement validation deck | ✅ Done (this PR) | — |
| 4c-3 | Offline `mgcv`-via-`rpy2` oracle (dev-only) | ⏳ Next | — |
| 4d | Diagnostic plots + docs (CLOSES EPIC) | 🔲 Planned | — |

## Verify Premise (step 7b)
Reproduced the gap before writing code. `analytics/validation.py` carried only three categories
(`CLOSED_FORM`, `TEXTBOOK`, `STATUTORY_DECK`) — no experience-analysis deck, and `polaris
benchmark` exposed only `full`/`closed-form`/`deck`. The A4′ capability (the whole tensor-MI
stack) had **no** validation surface, exactly as the CONTINUATION states.

I also empirically verified the *approach* premise: a throwaway probe injected a known improvement
into an ILEC-shaped extract, ran it through `load_ilec` → `attach static base` → `TensorMIModel`,
and confirmed the recovered `MI_x(y)` matches the injection to numerical precision (flat: max|err|
1.25e-16; age-varying MIM-shaped: 2.41e-12 across the full grid). This confirmed the deck is a
genuine closed-form-grade *recovery identity* — the log-linear-in-year improvement is spanned
exactly by the tensor B-spline basis — before any module code was written.

## What Was Done
Added `src/polaris_re/analytics/experience_validation.py` — the experience-analysis analogue of
the pricing engine's validation pack. The obvious framing ("reproduce SOA MIM-2021 / CIA published
improvement numbers") is unavailable network-free (those tables are licensed/large; the #61/#66
trap and Design Anchor 6). So the deck is a **recovery identity**, mirroring the whole-life deck's
parametric Makeham reference (which reproduces the SOA Illustrative Life Table from its *published
law*, not a copied column):

1. A known annual improvement surface `MI(x)` is injected into a synthetic, ILEC-*source*-schema
   extract whose `Death Count` is the *expected* deaths under it,
   `d(x,y) = E·q0(x)·(1-MI(x))^(y-base_year)`, with `q0(x)` the cited Makeham base.
2. The extract is written to a `tempfile.TemporaryDirectory()` and fed through the **real**
   `load_ilec` loader (loaders-not-data — nothing is vendored).
3. The tensor MI GAM is refit and the recovered `MI_x(y)` is checked against the injected target.

Because `MI(x)` is constant across calendar years, `log d(x,y)` is linear in `y` with an
age-varying slope — a function the tensor-product B-spline basis spans *exactly* — so recovery is
numerical (observed residual < 3e-12; `atol=1e-6` guards platform BLAS variation). Two sub-decks:
a **flat** improvement recovered by a separable age+calendar fit, and an **age-declining**
improvement (2.0%/yr at age 40 tapering to 0.5% at 85 — the general shape of the SOA MIM-2021 / CIA
aggregate scales) recovered by the age-varying tensor fit. Five sampled cases join the harness via
a new `ValidationCategory.EXPERIENCE_IMPROVEMENT` and a `run_experience_improvement_benchmarks()`
builder.

Wired into the harness (the scope's explicit requirement): `run_full_validation_pack()` now
appends the experience results (lazy import — avoids the `validation ↔ experience_validation`
import cycle and keeps `validation` importable without `[ml]`); the `polaris benchmark` CLI gains a
selectable `--pack experience`; and the self-verifying validation notebook
(`05_validation_report.ipynb`) is updated to run and assert the fourth category. Noiseless
expected-death data fits the Poisson mean exactly, which statsmodels flags as perfect
separation / no residual to converge on — both benign for a recovery identity, so only those two
warnings are filtered around the fit. ADR-150. Additive — engine/goldens byte-identical; the full
pack grows 13 → 18 cases.

## Files Changed
- `src/polaris_re/analytics/experience_validation.py` — new module
  (`run_experience_improvement_benchmarks`, private injection/recovery helpers, `__all__`).
- `src/polaris_re/analytics/validation.py` — new `ValidationCategory.EXPERIENCE_IMPROVEMENT`;
  `run_full_validation_pack()` appends the experience deck (lazy import).
- `src/polaris_re/analytics/__init__.py` — export `run_experience_improvement_benchmarks`.
- `src/polaris_re/cli.py` — `benchmark --pack experience` (builder + `_BENCHMARK_PACKS` + help).
- `notebooks/05_validation_report.ipynb` — fourth category in intro, imports, and diligence asserts.
- `docs/DECISIONS.md` — ADR-150.
- `docs/CONTINUATION_experience_gam.md` (ledger-heal #151 → MERGED; Slice 4c-2 → DONE,
  Slice 4c-3 → NEXT), `docs/PRODUCT_DIRECTION_2026-06-18.md` (1 harvested NICE-TO-HAVE follow-up),
  this session log.

## Tests Added
- `tests/validation/test_experience_improvement_pack.py` (18): all 5 cases pass; exactly 5 cases;
  every case is `EXPERIENCE_IMPROVEMENT`; recovery high-precision (max abs_error < 1e-9); stable
  unique case ids; every case carries an atol rationale; injected-target shape (flat constant,
  age-declining endpoints + interior, monotone-declining); full-surface flat recovery; full-surface
  age-varying gradient recovery; determinism (two runs → byte-identical surfaces); full pack
  contains the 5 experience cases. All calendar years pinned literals (ADR-074).
- `tests/validation/test_cli_benchmark.py` (+1): `benchmark --pack experience` exits 0, `5/5`.
- `tests/validation/test_statutory_deck_pack.py` (2 updated): full-pack category set + union now
  include the experience deck (intended composition change per ADR-150).

## Acceptance Criteria
| Criterion (CONTINUATION Slice 4c-2) | Status | Notes |
|-------------------------------------|--------|-------|
| Fit the tensor MI surface on an ILEC extract via `load_ilec` | ✅ | synthetic ILEC-source-schema extract → `tempfile` → real `load_ilec` |
| Check emitted `MI_x(y)` against MIM-2021 / CIA-style improvement targets within tolerance | ✅ | recovery identity vs injected MIM-2021/CIA-shaped target; residual < 3e-12, atol 1e-6 (real-data-vs-published-numbers harvested as NICE-TO-HAVE) |
| Wire into the `analytics/validation.py` benchmark harness | ✅ | new category + builder in full pack + `benchmark --pack experience` + notebook |
| In-repo tests use a synthetic fixture only (loaders-not-data) | ✅ | synthetic extract in `tmp`; parametric reference; no vendored ILEC/MIM data |
| Dockerfile COPY + `.dockerignore` allowlist updated if files land under `data/` | ✅ (N/A) | No files land under `data/`; allowlist untouched |
| Engine byte-identical (no golden change) | ✅ | golden `polaris price` + QA suite unchanged |

Non-slow validation + analytics + QA + notebook suites: all green (+19 tests over baseline). ruff
format + check clean. Golden `polaris price` regen check: exit 0, unchanged.

## Open Questions / Follow-ups
- The deck proves *recovery of a known surface*, not reproduction of *published* MIM-2021/CIA
  numbers (which are licensed/large and out of CI scope). A caller-side diligence run fitting a
  real cached ILEC extract (or freely-available HMD population data) against actual published
  targets would strengthen the credibility claim — harvested as NICE-TO-HAVE.

## Parked Polish
None. The single harvested item is a 1st-order follow-up of the planned Slice-4c-2 validation deck
(promoted normally as NICE-TO-HAVE).

## Impact on Golden Baselines
None. Purely additive — a new validation module + one `ValidationCategory` member + one CLI pack
key. No pricing path, assumption contract, or golden touched. Baseline `make test` at session
start: **2400 passed, 3 skipped, 110 deselected, 0 failures** — matches the recorded post-4c-1
baseline (2398) +2 (the PR #151 review-fix tests from merge `dd6e725`, commit `1d75865`);
tolerance-aware, no new/changed failures (VBT/CSO tables all OK; CIA MISSING but tests handle it).
After this slice: **+19 tests** (5-case deck + 18 pack tests + 1 CLI test, less the pre-existing
recount).

## Ledger / Housekeeping Note
`PRODUCT_DIRECTION_2026-06-18.md` is now **35 days old (>30)**. Consistent with the
immediately-prior slices (#142–#151), this session's harvest was **appended** to its "Promoted
Follow-ups" section rather than opening a new file, to avoid fragmenting the active epic's harvest
trail while the epic is mid-flight (Slice 4c-3/4d remain). A fresh `PRODUCT_DIRECTION` regeneration
(list-shipped-since #69..#151, carry-forward unresolved, then harvest) remains **overdue and
flagged for the next run** — a substantial standalone task that would blow this session's
wall-clock alongside the slice. The `COMMERCIAL_VIABILITY_REVIEW` (2026-07-15) is 8 days old —
fresh, no re-rank needed.

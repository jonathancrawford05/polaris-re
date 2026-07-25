# Dev Session Log — 2026-07-25 (B1: LICAT capital surface → `for_product_interim`)

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-07-24.md` — Re-ranked Catalogue Tier-B / "Recommended
  Next Sprint" **S3**, item **B1** ("Switch capital surfaces to `for_product_interim` —
  expose the built C-1/C-3 factors everywhere").
- **Priority:** Tier-B (Sprint-0 quick win) — gated fallback, maintenance mode.
- **Title:** Resolve the LICAT capital surface to `LICATCapital.for_product_interim`.
- **Slice:** complete (SMALL — single PR; not multi-session).
- **Branch:** `claude/loving-gauss-38wiey` (environment-designated; `feat/auto-*` default overridden).
- **PR:** #162 (draft) — https://github.com/jonathancrawford05/polaris-re/pull/162

## Selection Rationale
**Step 5 (continuation check):** the only IN PROGRESS CONTINUATION is `reserve_basis_correctness`,
explicitly **DEPRIORITISED / parked** (not the active epic) — step 5 picks up nothing. Every other
CONTINUATION is COMPLETE, including `pipeline_relocation` (S1, PR #158) and `mi_dashboard` (S2,
PRs #159–161), which merged since the last session log (2026-07-24).

**Step 5b (active epic):** **no** epic is active — the entire written roadmap is shipped and the
fresh `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` confirms **no unstarted Tier-A item** (the only
Tier-A-scale candidates are the reference-blocked AXIS/Prophet Slice 4 and an unchosen Phase-7
frontier, still AWAITING MAINTAINER). Per the ACTIVE-EPIC guardrail, with no startable epic the
session falls to **gated Sprint-0 fallback** and flags maintenance mode.

**Step 6 (fallback gate):** the maintainer-directed S1/S2 both merged, so the documented S3 sequence
(value-per-day order **B1 → B2 → B4**, all explicitly in the review's Sprint-0 / between-epics set)
governs. **B1** is next. It is self-contained (one registry chokepoint), clearly scoped (behaviour
change → ADR, and — as reproduced below — **no** golden rebaseline), and testable by pytest. No
other fallback item was taken.

## Verify Premise (step 7b)
Reproduced with a live interpreter before writing code:
- `capital_model_for("licat", pt)` returned **c1=0.0, c3=0.0** for every product — the single-deal
  priced path (CLI/API/dashboard) does **not** surface the built asset/interest factors.
- `LICATCapital.for_product_interim(pt)` returned the non-zero interim factors (c1=0.005 uniformly;
  c3 duration-scaled: TERM 0.005, WL 0.010, UL 0.015, ANNUITY 0.020).
- `dashboard/views/portfolio.py` **already** constructs `for_product_interim` — so the single-deal
  and portfolio LICAT bases disagreed. Premise holds; the fix also removes that inconsistency.

Premise **correction / refinement (carried into the ADR):** the headline "expose the built C-1/C-3
factors" understates the change. `for_product_interim` is built on `for_product_extended`, so
switching the resolver also upgrades C-2 from **mortality-only** to the full ADR-065 **extended C-2
(lapse + morbidity)** schedule. The ADR documents the exact per-product delta (C-2 lapse 0 →
default, C-2 morbidity 0 → default for DI/CI, C-1 0 → 0.005, C-3 0 → duration-scaled). This is
consistent with the portfolio path and is the coherent reading of "use `for_product_interim`".

## What Was Done
Changed the `licat` branch of the single capital registry `capital_model_for` (ADR-101) from
`LICATCapital.for_product` to `LICATCapital.for_product_interim`, so the CLI `--capital licat`, the
REST `capital_model="licat"` field, and the dashboard Deal-Pricing capital toggle all move together
to the interim committee-stage screening basis — the same basis the portfolio roll-up already used,
and consistent with US RBC / EU Solvency II already loading asset/interest components. Updated the
resolver docstring and corrected a now-stale "resolves to `for_product`, byte-identical" comment in
`pricing.py`. Added **ADR-160** documenting the behaviour change, the exact per-product factor
delta, why no golden regeneration is required, and the alternatives (add-C-1/C-3-only; configurable
selector; wait-for-ALM-calibration) with rejection rationale.

**No golden regeneration.** None of the four QA golden configs (`yrt`, `coins`, `policy_cession`,
`flat`) enable a capital model, so `polaris price` output on the committed configs is unchanged.
The QA golden guards (`test_cli_golden.py` 12/12, `test_pipeline_golden.py` 11/11) pass. The
existing API capital tests assert `peak_capital>0` / `pv_capital>0` (already true via C-2) and a
scale-invariant capital-ratio relationship — all preserved.

## Files Changed
- `src/polaris_re/analytics/capital_base.py` (resolver `licat` branch → `for_product_interim`; docstring)
- `src/polaris_re/dashboard/views/pricing.py` (corrected stale byte-identical comment)
- `docs/DECISIONS.md` (**ADR-160**)
- `tests/test_analytics/test_capital_base.py` (new `TestLicatResolverUsesInterimFactors`, 18 cases)
- `docs/DEV_SESSION_LOG_2026-07-25_b1_licat_interim.md` (this file)
- `docs/PRODUCT_DIRECTION_2026-07-24.md` (B1 annotated done-this-session / PR #162; harvest)

## Tests Added
`tests/test_analytics/test_capital_base.py::TestLicatResolverUsesInterimFactors` (18 cases):
resolver LICAT factors `==` `for_product_interim` per product; non-zero C-1 per product;
C-3 duration ladder (TERM 0.005 / WL 0.010 / UL 0.015 / ANNUITY 0.020); resolver `==` portfolio
path basis; and a closed-form check that peak required capital is strictly larger than the old
mortality-only `for_product` basis on an identical reserve/NAR stream. Verified red→green
(18 failing before the resolver change, all passing after).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| Priced LICAT path surfaces built C-1/C-3 (B1) | ✅ | Resolver → `for_product_interim` |
| Single-deal LICAT == portfolio roll-up basis | ✅ | `test_licat_resolver_consistent_with_portfolio_path` |
| C-3 scales with reserve duration | ✅ | Parametrised TERM→ANNUITY |
| No QA golden regeneration | ✅ | No golden config enables capital; guards 23/23; `polaris price` unchanged |
| Existing API capital tests preserved | ✅ | `peak_capital>0` / ratio scale-invariance still hold |
| ruff format + check clean | ✅ | 240 files unchanged; all checks passed |
| ADR added | ✅ | ADR-160 |
| Capital-relevant suites green | ✅ | analytics/api/cli_config/dashboard/qa/integration: 1187 passed, 0 failures |

## Open Questions / Follow-ups
- **Confirm the default flip (maintainer).** Making the interim ADR-072 placeholders the default
  LICAT priced basis is an actuarial-policy call, not just plumbing. The factors are conservative
  committee-stage placeholders; the "proper" successor is an ALM-derived shock-based calibration.
  The PR is draft and flags this for review before merge.
- **ALM-derived shock-based C-1/C-3 calibration** to supersede the interim placeholders now that
  they are the default (harvested below — IMPORTANT).
- **Configurable capital-basis selector** (interim vs mortality-only) on the CLI/API, if a user
  wants the pre-B1 basis explicitly (harvested below — NICE-TO-HAVE).

## Parked Polish
None. ADR-160's out-of-scope items are 1st-order follow-ups of a catalogue (planned) item and are
promoted normally below; no 3rd-order-or-deeper follow-up surfaced.

## Impact on Golden Baselines
None. No QA golden config enables a capital model, so `polaris price` on all four committed configs
is byte-identical and no golden was regenerated. (The raw `tests/qa/golden_outputs/*.json` snapshots
already diverge in byte-format from the CLI `-o` schema — a pre-existing tracked NICE-TO-HAVE,
unrelated to this change; the authoritative parsed guards pass 23/23.)

## Baseline
`make test`-equivalent (`pytest -m "not slow"`) at session start (branch reset to `main` @ #161,
`e002d34`): **2477 passed, 3 skipped, 112 deselected**, 0 failures — matches the recorded standing
baseline (VBT/CSO tables OK; CIA 2014 MISSING but handled — the 3 skips). No new/changed failures →
proceeded. After this session: capital-relevant suites **1187 passed** + `test_capital_base` **38
passed**, 0 failures; ruff clean; QA golden guards 23/23; `polaris price` golden `flat` run
byte-identical.

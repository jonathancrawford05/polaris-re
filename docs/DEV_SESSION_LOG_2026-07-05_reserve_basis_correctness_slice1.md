# Dev Session Log — 2026-07-05 (Reserve-Basis Correctness, Slice 1)

## Item Selected
- **Source:** `CONTINUATION_reserve_basis_correctness.md` (IN PROGRESS) — the
  active Epic, Slice 1. Backing item: PRODUCT_DIRECTION_2026-06-18 Promoted
  Follow-ups — IMPORTANT "WholeLife does not model mortality improvement on any
  basis" (silent correctness bug, ADR-128 Out of scope, 1st-order).
- **Priority:** IMPORTANT (correctness bug — reprioritised to the front of the
  epic ahead of the interest-exactness slices).
- **Title:** WholeLife honours the `AssumptionSet.improvement` scale on its
  best-estimate bases.
- **Slice:** 1 of 3 (+ a viability-review checkpoint after Slice 1).
- **Branch:** claude/loving-gauss-8brpd5

## Baseline
`make test` at session start: **1990 passed, 2 skipped, 110 deselected**, 0
failures (clean green). `convert_soa_tables.py` produced the VBT/CSO tables;
the four CIA tables report MISSING from pymort (known-standing, no test depends
on them). No new or changed failures vs the prior recorded baseline (1925/1940,
grown by intervening merged PRs) → PROCEED.

## Ledger Healing (step 4b)
No PRs merged since the prior session log (2026-07-03): `git log main` shows the
2026-07-03 exactness Slice-1 work (PR #124) and the subsequent Slices 2–4
(#125/#126/#127) already merged and struck; commit 57f7425 constituted this
epic. Nothing to strike this morning.

## Selection Rationale
Step 5 found `CONTINUATION_reserve_basis_correctness.md` IN PROGRESS with Slice 1
= NEXT, so the CONTINUATION IS the work selection (skip steps 5b/6). Slice 1 is
independent — it depends only on PR #127 (WL GAAP), already merged to main. No
fallback pick considered (the epic's next slice was advanceable).

## Verify Premise (step 7b)
Reproduced the bug before writing code: priced a WL block (age-40 whole-life
pay, GAAP basis) with and without `MortalityImprovement.scale_aa(base_year=2015)`
configured. Result: **byte-identical** claims ($259,665.74) and GAAP@month-60
($96,697.41) — WholeLife silently ignored the improvement scale. Premise holds.
Post-fix the same repro diverges (claims $259,665.74 → $257,750.51; GAAP
$96,697.41 → $95,857.79). Byte-identity checkpoint: grep over `data/` found NO
golden / QA / sample config sets a WL improvement scale → the fix is
byte-identical on every golden (confirmed by the golden `flat` check below).

## Decomposition Plan
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | WholeLife improvement on best-estimate bases (projection, NET_PREMIUM, GAAP, VM-20 DR); statutory (CRVM/NPR) stay static | ✅ Done | (this PR) |
| — | CHECKPOINT: regenerate COMMERCIAL_VIABILITY_REVIEW | ⏳ Next | — |
| 2 | Prescribed statutory valuation-interest helper — engine (provisional) | 🔲 Planned | — |
| 3 | Surface valuation-interest on the deal path + docs (provisional) | 🔲 Planned | — |

## What Was Done
`WholeLife._build_rate_arrays` now applies a configured
`AssumptionSet.improvement` scale exactly as `TermLife._build_rate_arrays` does —
monthly q → annual (`1-(1-q)**12`) → `apply_improvement(q, ages, cal_year)` at
the projection calendar year → back to monthly via
`constant_force_interpolate_rates`, **before** the per-policy substandard rating
(ADR-042) and the max-age certain-death forcing. This drives the projection cash
flows and the NET_PREMIUM reserve.

`_build_valuation_mortality` gained an explicit `apply_improvement: bool = False`
parameter. The best-estimate valuation callers pass `True` — GAAP
(`_compute_reserves_gaap`) and the VM-20 **deterministic** reserve
(`_compute_reserves_vm20`); the prescribed statutory callers keep the default
`False` — CRVM (`_compute_reserves_crvm`) and, through it, the VM-20 NPR floor.
The seam is deliberately the **caller**, not `table is None`: CRVM without a
prescribed slot passes `table=None` yet must stay static, while the VM-20 DR
also passes `table=None` and must be improved — an explicit flag is the only
correct boundary. With no improvement configured the flag is a no-op, so all
existing behaviour is byte-identical.

Recorded in ADR-129; ARCHITECTURE.md reserve-basis section updated; the stale
"WL does not model improvement on any basis" notes in the WholeLife GAAP
docstring and the `test_wl_gaap_reserve.py` module docstring were corrected.

## Files Changed
- `src/polaris_re/products/whole_life.py` — improvement in `_build_rate_arrays`;
  `apply_improvement` seam on `_build_valuation_mortality`; GAAP + VM-20-DR
  callers pass `True`; `constant_force_interpolate_rates` import; docstrings.
- `ARCHITECTURE.md` — Reserve Basis Selection section (improvement-per-basis note).
- `docs/DECISIONS.md` — ADR-129.
- `tests/test_products/test_wl_improvement.py` — NEW (11 tests).
- `tests/test_products/test_wl_gaap_reserve.py` — guardrail docstring corrected.
- `docs/PLAN_reserve_basis_correctness.md` / `CONTINUATION_reserve_basis_correctness.md`
  — Slice 1 → DONE.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — WL-improvement item struck (SHIPPED).
- `docs/DEV_SESSION_LOG_2026-07-05_reserve_basis_correctness_slice1.md` — this log.

## Tests Added
- `tests/test_products/test_wl_improvement.py` (11 tests): projected claims,
  NET_PREMIUM, GAAP, and the VM-20-DR best-estimate q all move DOWN under a Scale
  AA scale; CRVM (with and without a prescribed table) and the VM-20 NPR floor
  byte-identical under improvement (statutory static rule); best-estimate
  valuation q (`apply_improvement=True`) equals the projection q over the horizon
  (the VM-20 DR invariant); independent hand-built numpy Scale AA recomputation
  reproduces the engine's improved monthly q to 1e-15; no-improvement → flag is a
  no-op on every path (byte-identity).

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| WholeLife applies `improvement` on best-estimate bases (GAAP/VM-20 DR/projected claims move) | ✅ | isolation + guardrail tests |
| CRVM and VM-20 NPR on a prescribed table unchanged by improvement | ✅ | static-basis tests (with/without prescribed table) |
| Byte-identical goldens/QA when no WL config sets improvement | ✅ | 2001 fast + 76 QA green; golden `flat` $45,386 / $3,513,563 exact |
| Independent recomputation matches | ✅ | 1e-15 vs hand-built numpy |

## Open Questions / Follow-ups
- **CHECKPOINT before Slice 2 (process step).** Per PLAN/CONTINUATION, regenerate
  `docs/COMMERCIAL_VIABILITY_REVIEW_<date>.md` (re-review last ~10 PRs + docs,
  re-rank the catalogue) before committing the epic to the interest-exactness
  slices — the Tier-A ladder is exhausted and the 2026-06-18 review turns 30 days
  old ~2026-07-18. Confirm Slices 2–3 (valuation-interest exactness) still
  out-rank a productization epic (data-ingestion robustness, AXIS/Prophet
  benchmark validation, packaging, docs); redirect the epic if not. This is the
  next session's likely deliverable.
- Human question (carried in the CONTINUATION): should the regenerated review be
  allowed to redirect the epic to a productization theme if it ranks higher?

## Parked Polish
None. The one harvested item (see below) is a 1st-order residual of an
originally-planned feature and is promoted normally.

## Impact on Golden Baselines
None. WholeLife improvement is off on every golden/QA/sample config (verified by
grep over `data/`), so all priced numbers are byte-identical. Golden `flat`
reproduces Total PV Profits Reinsurer $45,386 / Cedant $3,513,563 exactly. No
baseline regeneration.

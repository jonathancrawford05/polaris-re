# Dev Session Log — 2026-04-25

## Item Selected

- **Source:** PRODUCT_DIRECTION_2026-04-19.md (Recommended Next Sprint
  item #5 — "LICAT regulatory capital (Milestone 5.1 kick-off)")
- **Priority:** BLOCKER (last remaining BLOCKER from the 2026-04-19
  product direction; the prior four — WL expense fix, profit guardrails,
  per-policy substandard rating, deal-pricing Excel export — have all
  been merged.)
- **Title:** Standalone `LICATCapital` calculator (factor-based)
- **Slice:** 1 of 3
- **CONTINUATION:** `docs/CONTINUATION_licat_capital.md`

## Selection Rationale

PRODUCT_DIRECTION_2026-04-19 listed five items in the "Recommended Next
Sprint". A scan of the merge history (`git log --oneline -20`) and the
two existing CONTINUATION files showed that items 1-4 are all DONE:

| # | Item | Evidence |
|---|---|---|
| 1 | WL expense fix | `46a7806 fix: linting`, `7d62730 fix: gate acquisition cost on new business`, `6fd7f7c fix(products): apply expense loading in WholeLife projection` (PR #26 merged) |
| 2 | ProfitTester guardrails | `31f6ca8 feat(analytics): reporting guardrails on ProfitTester (ADR-041)` (PR #27 merged) |
| 3 | Per-policy substandard rating | PRs #28, #29, #30; CONTINUATION_substandard_rating.md status COMPLETE |
| 4 | Deal-pricing Excel export | PRs #31, #32; CONTINUATION_deal_pricing_excel.md status COMPLETE |
| 5 | LICAT regulatory capital | NOT STARTED — selected for this session |

No CONTINUATION file in IN PROGRESS state and no open PRs (`gh pr
list --state open` returns empty). Item 5 is the obvious next BLOCKER:
- Self-contained and testable.
- 4 dev-day estimate → MEDIUM per the routine's classification.
- Needs decomposition into slices, each independently mergeable.
- The "new module, then integration" pattern (B) fits exactly: Slice 1
  is the pure calculator; Slice 2 wires it through ProfitTester; Slice 3
  surfaces RoC via CLI / API / Excel.

## Decomposition Plan

| Slice | Scope | Status | PR |
|---|---|---|---|
| 1 | `LICATCapital` calculator + factor model + ADR-047 | ✅ Done | (this draft) |
| 2 | `ProfitTester.run_with_capital` + RoC metric + ADR-048 | ⏳ Next | — |
| 3 | CLI `--capital licat`, API `capital_model`, Excel Summary rows | 🔲 Planned | — |

Each slice leaves the codebase in a fully passing state. Slice 1 is
purely additive — no existing pricing path consumes the new module —
so golden baselines are unchanged.

## What Was Done

Added `src/polaris_re/analytics/capital.py` implementing the LICAT
factor-based capital model. Three public symbols:

1. **`LICATFactors`** (Pydantic frozen model) carries the three risk
   factors (`c2_mortality_factor`, `c1_asset_default`,
   `c3_interest_rate`), each validated `[0, 1]`. Defaults: 0.10 / 0.0 /
   0.0 — C-1 and C-3 are zero stubs to be populated by Phase 5.4 once
   the asset / ALM model is in.

2. **`CapitalResult`** (dataclass) carries the per-period component and
   aggregate capital arrays plus the `initial_capital` and
   `peak_capital` scalars. Adds a `pv_capital(rate)` method that
   discounts the capital stock at a flat annual rate.

3. **`LICATCapital`** (Pydantic frozen model) is the calculator. The
   `for_product(ProductType)` factory returns an instance pre-populated
   with the product-type-specific C-2 factor (TERM 0.15, WL 0.10, UL
   0.08, DI 0.05, CI 0.05, ANN 0.03 — calibrated to the OSFI 2024 LICAT
   mortality shock proxy). The `required_capital(cashflows, nar=None)`
   method resolves NAR from the explicit override (precedence) or
   `cashflows.nar` (fallback, which YRT treaty populates), rejects
   CEDED basis, and returns the `CapitalResult`.

The module is intentionally standalone — it imports from `core/` only,
not from `analytics/profit_test`. This keeps the integration surface
narrow so Slice 2 (ProfitTester) and a possible future shock-based v2
can replace the factor formula without rewriting downstream code.

`analytics/__init__.py` re-exports the three new symbols and keeps
`__all__` alphabetical. `docs/DECISIONS.md` gains ADR-047 documenting
the OSFI factor calibration, the explicit non-shock-based scope of
Slice 1, and the open questions handed to Slice 2 (RoC stock vs strain;
whether CashFlowResult needs `face_in_force`).

## Files Changed

- `src/polaris_re/analytics/capital.py` — NEW (216 lines)
- `src/polaris_re/analytics/__init__.py` — modified (3 exports added,
  `__all__` re-sorted)
- `tests/test_analytics/test_capital.py` — NEW (305 lines, 31 tests)
- `docs/DECISIONS.md` — appended ADR-047 (~85 lines)
- `docs/CONTINUATION_licat_capital.md` — NEW
- `docs/DEV_SESSION_LOG_2026-04-25_licat_capital_slice_1.md` — NEW
  (this file)

## Tests Added

`tests/test_analytics/test_capital.py` — 31 tests across 6 classes:

| Class | Count | Coverage |
|---|---|---|
| `TestLICATFactors` | 4 | Defaults, non-negativity, ≤1 cap, frozen |
| `TestLICATCapitalForProduct` | 7 (parametrised) + 1 | Factor per product type; zero C-1/C-3 stubs |
| `TestLICATCapitalRequiredCapital` | 6 | C-2 = factor × NAR closed-form, total = sum, initial / peak, sensitivity, zero factor |
| `TestLICATCapitalNarResolution` | 4 | cashflow.nar source, override precedence, missing-NAR raise, length-mismatch raise |
| `TestLICATCapitalBasis` | 3 | GROSS / NET accepted, CEDED rejected |
| `TestCapitalResult` | 4 | Shape, dtype, pv monotone in rate, pv at rate=0 |
| `TestC2ClosedFormOSFI` | 2 | TERM 1M @ 0.15 = 150K; WL 2M @ 0.10 = 200K |
| (module level) | 1 | Public symbols importable from `polaris_re.analytics` |

## Acceptance Criteria

| Criterion | Status | Notes |
|---|---|---|
| C-2 closed-form (factor × NAR) | ✅ | Test `test_c2_equals_factor_times_nar` and OSFI hand-calc tests |
| Per-product defaults via `for_product` | ✅ | `TestLICATCapitalForProduct` parametrised across all six `ProductType` values |
| C-1 and C-3 zero stubs | ✅ | `test_c1_c3_stubs_zero_by_default` |
| NAR resolution via cashflows or override | ✅ | `TestLICATCapitalNarResolution` covers all four paths |
| CEDED basis rejected | ✅ | `test_ceded_basis_rejected` |
| Existing 726 non-slow tests still pass | ✅ | Suite is now 757 (= 726 + 31 new) |
| QA suite 33/33 | ✅ | All golden regressions and dashboard flows |
| Golden baselines unchanged | ✅ | New module not yet wired into any pricing path |
| ADR-047 written | ✅ | `docs/DECISIONS.md` |
| Module exports surfaced | ✅ | `from polaris_re.analytics import LICATCapital` works |
| Ruff format / check clean | ✅ | All three modified files |

## Open Questions / Follow-ups

Captured in `docs/CONTINUATION_licat_capital.md` "Open Questions
(for human)". Highlights:

1. **RoC denominator — stock vs strain.** Slice 2 will default to
   stock (`pv_capital`) but flag for review.
2. **`face_amount_in_force` on `CashFlowResult`.** Slice 2 will
   default to NOT introducing this contract change; instead, the
   `run_with_capital` call site computes NAR from the InforceBlock.
3. **C-1 and C-3 stubs at zero.** Whether to populate an interim C-3
   factor before Phase 5.4 lands. Default: stay at zero with a clear
   "not modelled" note.
4. **Lapse / morbidity risk components.** Out of scope until after
   Slice 3 ships.

## Impact on Golden Baselines

**None.** Slice 1 is purely additive — `LICATCapital` is a new module
with no callers in `cli.py`, `pipeline.py`, `profit_test.py`, or any
treaty / product engine. The pricing path is byte-identical to before.
Verified by:

- 33/33 QA tests pass (including `TestGoldenYRT.test_yrt_golden_regression`
  and `TestGoldenFlat.test_flat_golden_regression`).
- 726 → 757 tests pass with only new tests added; no existing test
  broken.
- `polaris price --inforce data/qa/golden_inforce.csv --config
  data/qa/golden_config_flat.json` runs successfully and emits the same
  Rich table summary as before (Cohorts 2, Total PV Profits Cedant
  $3,513,563, Reinsurer $45,386).

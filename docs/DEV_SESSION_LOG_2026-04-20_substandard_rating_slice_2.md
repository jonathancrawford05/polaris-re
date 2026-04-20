# Dev Session Log — 2026-04-20 (Slice 2)

## Item Selected
- **Source:** `docs/CONTINUATION_substandard_rating.md` (feature source
  PRODUCT_DIRECTION_2026-04-19.md — BLOCKER)
- **Priority:** BLOCKER
- **Title:** Per-policy substandard rating — wire into product engines
- **Slice:** 2 of 3 (wire into product engines)

## Selection Rationale

The CONTINUATION file for the substandard-rating feature is IN PROGRESS.
Slice 1 landed in PR #28 (now merged to main) and added the data-model
fields on `Policy` plus the vectorized `InforceBlock` accessors. The
next scheduled slice per the CONTINUATION plan is Slice 2: wire into
`TermLife`, `WholeLife`, and `UniversalLife` engines so that
`q_eff = q_base * multiplier + flat_extra / 1000 / 12` flows into
projected claims, `lx`, and reserves.

No other BLOCKER items were selected because the CONTINUATION plan
explicitly dictates sequential execution, and starting a new multi-
session feature while one is IN PROGRESS would leave two in flight.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Policy fields + InforceBlock vecs + CSV round-trip + ADR-042 | Done | #28 |
| 2 | Wire TermLife / WholeLife / UniversalLife + closed-form tests | Done (this session) | (draft) |
| 3 | Ingestion rating-code registry + CLI/dashboard surface | Next | — |

See `docs/CONTINUATION_substandard_rating.md` for the full plan.

## What Was Done

Applied the ADR-042 effective-mortality formula inside the three life
product engines. Each engine now computes, per month, per policy,

    q_eff = min(q_base * mortality_multiplier + flat_extra / 12000, 1.0)

and the result is consumed by every downstream calculation — claim
projection, in-force factor `lx`, net premium reserves, and (for UL)
COI charges. The cap at `1.0` preserves the actuarial invariant that
mortality rates are probabilities. In `TermLife` the substandard
adjustment sits after mortality-improvement so the multiplier scales
the calendar-year-adjusted rate; in `WholeLife` and `UniversalLife`
it sits just before the max-age override so certain-death at `omega`
is still forced to 1.0. The change is vectorized — the two per-policy
vectors (`multiplier_vec`, `flat_extra_monthly_vec`) are lifted out of
the month loop and broadcast in the existing (N, T) construction.

Documented the implementation and its actuarial consequences in
ADR-043, including three deliberate choices that affect downstream
slices:

- YRT ceded premium is NOT scaled by the mortality multiplier.
  Substandard risk still flows to the reinsurer through ceded claims
  because `CashFlowResult.death_claims` reflects `q_eff`. The cedant
  bears any incremental rated-premium delta unless a future treaty
  field overrides this default.
- `DisabilityProduct` is left untouched — CI/DI substandard is a
  morbidity concept and lives behind a separate registry decision
  that Slice 3 (ingestion) will inform.
- The flat-extra component is folded into aggregate `death_claims`
  rather than reported as a new cash-flow line, preserving the
  `CashFlowResult` contract.

Added 15 closed-form tests (5 per product): `test_default_is_identity`
(explicit defaults reproduce baseline exactly), `test_multiplier_
scales_first_month_claim` (multiplier=2.0 ⇒ exactly 2× first-month
claim because `lx[0] = 1`), `test_flat_extra_adds_expected_monthly_
increment` (`$5/1000` on the engine's test face produces the expected
`face * 5 / 12000` additive increment), `test_zero_multiplier_and_
zero_flat_extra_produces_zero_claims` (`q_eff = 0` produces zero
projected claims), and `test_q_eff_capped_at_one_for_extreme_
multiplier` (multiplier=20.0 with flat_extra=100 cannot exceed face).

The 669 pre-existing unit tests continue to pass (now 684 total with
the 15 new tests). The 27 QA tests — including the two golden-
regression tests (`test_yrt_golden_regression`, `test_flat_golden_
regression`) — pass without any baseline regeneration because every
existing fixture has default `mortality_multiplier = 1.0` and
`flat_extra_per_1000 = 0.0`, which are identity elements under the
formula.

## Files Changed

- `src/polaris_re/products/term_life.py` — substandard applied after
  improvement, before `active` mask.
- `src/polaris_re/products/whole_life.py` — substandard applied before
  the `at_max_age` override.
- `src/polaris_re/products/universal_life.py` — substandard applied in
  `_build_mortality_arrays` before the max-age override.
- `tests/test_products/test_term_life.py` — `TestTermLifeSubstandardRating`
  class (5 tests).
- `tests/test_products/test_whole_life.py` — `TestWholeLifeSubstandardRating`
  class (5 tests).
- `tests/test_products/test_universal_life.py` —
  `TestUniversalLifeSubstandardRating` class (5 tests).
- `docs/DECISIONS.md` — ADR-043 added.
- `docs/CONTINUATION_substandard_rating.md` — Slice 1 marked DONE,
  Slice 2 marked DONE with decisions, Slice 3 set to NEXT. Open
  questions updated.
- `docs/DEV_SESSION_LOG_2026-04-20_substandard_rating_slice_2.md` —
  this file.

## Tests Added

- `tests/test_products/test_term_life.py::TestTermLifeSubstandardRating::test_default_is_identity`
- `tests/test_products/test_term_life.py::TestTermLifeSubstandardRating::test_multiplier_scales_first_month_claim`
- `tests/test_products/test_term_life.py::TestTermLifeSubstandardRating::test_flat_extra_adds_expected_monthly_increment`
- `tests/test_products/test_term_life.py::TestTermLifeSubstandardRating::test_zero_multiplier_and_zero_flat_extra_produces_zero_claims`
- `tests/test_products/test_term_life.py::TestTermLifeSubstandardRating::test_q_eff_capped_at_one_for_extreme_multiplier`
- `tests/test_products/test_whole_life.py::TestWholeLifeSubstandardRating::test_default_is_identity`
- `tests/test_products/test_whole_life.py::TestWholeLifeSubstandardRating::test_multiplier_scales_first_month_claim`
- `tests/test_products/test_whole_life.py::TestWholeLifeSubstandardRating::test_flat_extra_adds_expected_monthly_increment`
- `tests/test_products/test_whole_life.py::TestWholeLifeSubstandardRating::test_zero_multiplier_and_zero_flat_extra_produces_zero_claims`
- `tests/test_products/test_whole_life.py::TestWholeLifeSubstandardRating::test_q_eff_capped_at_one_for_extreme_multiplier`
- `tests/test_products/test_universal_life.py::TestUniversalLifeSubstandardRating::test_default_is_identity`
- `tests/test_products/test_universal_life.py::TestUniversalLifeSubstandardRating::test_multiplier_scales_first_month_claim`
- `tests/test_products/test_universal_life.py::TestUniversalLifeSubstandardRating::test_flat_extra_adds_expected_monthly_increment`
- `tests/test_products/test_universal_life.py::TestUniversalLifeSubstandardRating::test_zero_multiplier_and_zero_flat_extra_produces_zero_claims`
- `tests/test_products/test_universal_life.py::TestUniversalLifeSubstandardRating::test_q_eff_capped_at_one_for_extreme_multiplier`

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| TERM consumes `mortality_multiplier` and `flat_extra_per_1000` | Done | `_build_rate_arrays` post-improvement |
| WL consumes both fields | Done | Before `at_max_age` override |
| UL consumes both fields | Done | Before `at_max_age` in `_build_mortality_arrays` |
| Closed-form test: multiplier=2.0 ⇒ 2× first-month claim | Done | Per product |
| Closed-form test: $5/1000 flat extra ⇒ `face * 5/12000` month-0 increment | Done | Per product |
| Edge test: multiplier=0 with flat_extra=0 ⇒ zero claims | Done | Per product |
| Edge test: extreme multiplier capped at 1.0 | Done | Per product |
| Existing unit + QA + golden tests unchanged | Done | 669 → 684 (only additions); 27/27 QA pass |
| ADR written | Done | ADR-043 |
| CONTINUATION updated; Slice 3 marked NEXT | Done | |

## Open Questions / Follow-ups

1. Should a treaty-level flag be added in Slice 3 to enable
   `yrt_rate × mortality_multiplier` billing for cedants whose treaties
   specify rated-premium cession? The Slice 2 default is unmultiplied
   YRT premium.
2. Should CI/DI active-life mortality decrement be scaled by
   `mortality_multiplier`? Deferred until Slice 3 confirms whether
   cedant rating codes in the ingestion registry apply to morbidity
   products.
3. Should `flat_extra_per_1000` eventually become its own reported
   cash-flow line? The current default folds it into `death_claims`.
   A future ADR would split the output contract if the reinsurance
   committee requires line-item reporting.

## Impact on Golden Baselines

None. All existing policy fixtures carry default
`mortality_multiplier = 1.0` and `flat_extra_per_1000 = 0.0`, which
are identity elements under the ADR-042 formula
(`q_base * 1.0 + 0.0 = q_base`, always below the cap of 1.0 for
realistic ages). The golden regression CLI check
(`uv run polaris price --inforce data/qa/golden_inforce.csv --config
data/qa/golden_config_flat.json`) produces byte-identical outputs vs.
the baseline bundled in `tests/qa/test_pipeline_golden.py`, which
still passes without modification.

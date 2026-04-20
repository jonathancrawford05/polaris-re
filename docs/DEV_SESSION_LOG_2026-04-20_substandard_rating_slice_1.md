# Dev Session Log — 2026-04-20

## Item Selected
- **Source:** PRODUCT_DIRECTION_2026-04-19.md
- **Priority:** BLOCKER
- **Title:** Per-policy substandard rating and flat extras
- **Slice:** 1 of 3 (data model first)

## Selection Rationale

All BLOCKERs from PRODUCT_DIRECTION_2026-04-19 that were small-scoped
(WL expense fix — #1, reporting guardrails — #2) have already merged
via PRs #26 and #27. The three remaining BLOCKERs are:

1. Per-policy substandard rating (3 days, MEDIUM, 3 slices)
2. LICAT regulatory capital (8+ days, LARGE, 4 slices)
3. Deal-pricing Excel export (2 days, SMALL/MEDIUM)

The substandard-rating feature was chosen over Excel export and LICAT
because it is the most actuarially central of the three (without it the
engine cannot quote ANY substandard deal), it is independently useful
at each slice boundary, and the routine's own example prompt cites it
as the canonical multi-session decomposition. The "data model first"
pattern used in Slice 1 is pure additive structure with default values
that preserve every existing test and golden baseline — zero behavioural
risk.

## Decomposition Plan

| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 1 | Policy fields + InforceBlock vecs + CSV round-trip + ADR | Done (this session) | (draft) |
| 2 | Wire into TermLife / WholeLife / UniversalLife _build_rate_arrays with closed-form tests | Next | — |
| 3 | Ingestion rating-code registry + CLI/dashboard surface | Planned | — |

See `docs/CONTINUATION_substandard_rating.md` for full details.

## What Was Done

Added two new fields to `Policy` — `mortality_multiplier` (default 1.0,
bounded 0.0–20.0) and `flat_extra_per_1000` (default 0.0, bounded
0.0–100.0). Exposed both as vectorized `np.ndarray` properties on
`InforceBlock` (`mortality_multiplier_vec`, `flat_extra_vec`), matching
the existing vectorization contract. Extended `InforceBlock.from_csv()`
to read the two optional columns and fall back to defaults when the
columns are absent so all pre-existing CSV fixtures continue to load
unchanged.

Documented the design decision as ADR-042 including the effective-
mortality formula `q_eff = q_base * multiplier + flat_extra / 1000 / 12`
that Slices 2/3 will use, the bounds rationale, and the backward-
compatibility guarantee.

Added 12 new tests covering field defaults, bound validation on both
fields (low and high), explicit-value round-trip, InforceBlock vec
shape/dtype/neutral-defaults, and CSV round-trip with and without the
new columns. All 669 unit tests plus 27 QA tests pass (up from 657 unit
tests). Golden regression pipeline tests pass without modification —
Slice 1 is behaviour-neutral by construction.

## Files Changed

- `src/polaris_re/core/policy.py` — add two `Field`-validated attributes.
- `src/polaris_re/core/inforce.py` — add two `@property` vecs and plumb
  through `from_csv()`.
- `tests/test_core/test_models.py` — `TestPolicySubstandardRating` and
  `TestInforceBlockSubstandardVecs` classes.
- `tests/test_core/test_inforce_csv.py` — two new tests for optional
  column behaviour.
- `docs/DECISIONS.md` — ADR-042.
- `docs/CONTINUATION_substandard_rating.md` — created.
- `docs/DEV_SESSION_LOG_2026-04-20_substandard_rating_slice_1.md` —
  this file.

## Tests Added

- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_default_multiplier_is_one`
- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_default_flat_extra_is_zero`
- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_explicit_table_2`
- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_explicit_flat_extra`
- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_negative_multiplier_rejected`
- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_multiplier_above_bound_rejected`
- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_negative_flat_extra_rejected`
- `tests/test_core/test_models.py::TestPolicySubstandardRating::test_flat_extra_above_bound_rejected`
- `tests/test_core/test_models.py::TestInforceBlockSubstandardVecs::test_defaults_are_neutral`
- `tests/test_core/test_models.py::TestInforceBlockSubstandardVecs::test_explicit_ratings_flow_through`
- `tests/test_core/test_inforce_csv.py::TestInforceBlockFromCSV::test_substandard_rating_defaults_when_columns_missing`
- `tests/test_core/test_inforce_csv.py::TestInforceBlockFromCSV::test_substandard_rating_read_from_csv`

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `Policy.mortality_multiplier` field exists with default 1.0 | Done | ge=0.0, le=20.0 |
| `Policy.flat_extra_per_1000` field exists with default 0.0 | Done | ge=0.0, le=100.0 |
| `InforceBlock.mortality_multiplier_vec` returns `(N,)` float64 | Done | |
| `InforceBlock.flat_extra_vec` returns `(N,)` float64 | Done | |
| Existing test suite unaffected | Done | 657 → 669 passing (12 new) |
| Golden baselines unchanged | Done | Field defaults are identity elements |
| CSV round-trip handles old + new CSV schemas | Done | |
| ADR written | Done | ADR-042 |
| CONTINUATION file tracks Slices 2/3 | Done | |

## Open Questions / Follow-ups

1. Slice 2: should the YRT treaty bill ceded premium at
   `yrt_rate × mortality_multiplier` or at flat `yrt_rate`? Default in
   Slice 2 will be **unmultiplied** (cedant absorbs the extra risk
   unless the treaty is explicitly configured otherwise). Needs human
   confirmation before Slice 2 proceeds.
2. Should `flat_extra_per_1000` produce a separate reported cash flow
   line on `CashFlowResult` or fold into `death_claims`? Default in
   Slice 2 will be **folded**. Flagging for review.

## Impact on Golden Baselines

None. Slice 1 adds data-model fields only; no product engine consumes
them yet. Default values (1.0, 0.0) are identity elements under the
planned effective-mortality formula. Existing golden tests rerun with
byte-identical results.

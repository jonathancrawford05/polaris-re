# Dev Session Log — 2026-06-02

## Item Selected

- **Source:** PRODUCT_DIRECTION_2026-05-23.md
- **Priority:** IMPORTANT
- **Title:** LICAT lapse-risk and morbidity-risk capital components
- **Slice:** complete (SMALL item — single session)
- **Provenance:** CONTINUATION_licat_capital — Open Question #4
  (deferred to a Phase 5.1.b ADR)

## Selection Rationale

PRODUCT_DIRECTION_2026-05-23 recommends LICAT lapse / morbidity factors
as the one IMPORTANT item that fits a single session (~3 dev-days
estimated). All four BLOCKERs from 2026-04-19 are shipped; the two
other IMPORTANT items (Reserve-basis matching, IFRS 17 movement table)
are 10+ dev-days each and explicitly flagged for dedicated roadmap
entries, not mid-sprint picks.

The item was originally Open Question #4 on the closed
CONTINUATION_licat_capital — Slice 1 documented it as a "straight
extension of the factor model that doesn't change the ProfitTester
integration surface", which is exactly the size profile sought for a
single-session pick. No conflicting open PRs (verified via
`mcp__github__list_pull_requests` — empty list).

The implementation footprint is 1 source file + 1 test file + 1 ADR
section, no contract changes on `CashFlowResult`, `Policy`, or
`InforceBlock`, no behaviour change to existing
`LICATCapital.for_product(...)` calls — clean SMALL classification.

## What Was Done

Extended `LICATFactors` and `CapitalResult` with two new C-2 insurance-
risk sub-components: lapse risk (applied to `reserve_balance`) and
morbidity risk (applied to NAR, non-zero only for DI / CI). Both factors
default to zero so a bare `LICATFactors()` and the existing
`LICATCapital.for_product(...)` factory produce the same capital number
as before — preserving backward compatibility for the ADR-049 CLI / API /
Excel surfacing.

A new `LICATCapital.for_product_extended(product_type)` factory
populates all three C-2 sub-factors per product (mortality + lapse +
morbidity). This is the opt-in path for callers that want the full LICAT
2024 C-2 number. `CapitalResult` gains
`c2_lapse_component` / `c2_morbidity_component` array fields and a
`c2_insurance_risk` property that returns the aggregate of mortality +
lapse + morbidity. `capital_by_period` now sums all five components
(C-1 + mortality + lapse + morbidity + C-3) but its time-zero value is
unchanged when only the mortality factor is set, so existing golden
baselines and tests are unaffected.

ADR-065 documents the default factor schedule, the lapse-on-reserve and
morbidity-on-NAR exposure-base choices, and explicitly leaves CLI / API
surfacing to a follow-up promoted in the next PRODUCT_DIRECTION.

## Files Changed

- `src/polaris_re/analytics/capital.py` — added `c2_lapse_factor` and
  `c2_morbidity_factor` on `LICATFactors`, added `c2_lapse_component`
  and `c2_morbidity_component` arrays + `c2_insurance_risk` property on
  `CapitalResult`, added `_C2_LAPSE_DEFAULT_BY_PRODUCT` and
  `_C2_MORBIDITY_DEFAULT_BY_PRODUCT` constants, added
  `for_product_extended` classmethod, updated `required_capital` to
  compute the five components, refreshed module docstring (+135 lines).
- `tests/test_analytics/test_capital.py` — added 32 new tests across 6
  test classes covering factor validation, closed-form lapse component,
  closed-form morbidity component, aggregate sums, backward-compat of
  `for_product`, and the new `for_product_extended` factory (+278
  lines).
- `docs/DECISIONS.md` — added ADR-065 with the default factor schedule,
  exposure-base rationale, and out-of-scope follow-ups (+127 lines).

## Tests Added

- `TestLICATFactorsExtendedC2` (6 tests) — defaults, non-negative
  validation, cap-at-one validation for both new factors.
- `TestLapseRiskComponent` (4 tests) — closed-form `c2_lapse =
  factor * reserve`, zero-factor zero-component, doubling-factor
  sensitivity, reserve-shape tracking.
- `TestMorbidityRiskComponent` (4 tests) — closed-form `c2_morbidity =
  factor * NAR`, zero-factor zero-component, doubling-factor
  sensitivity, explicit-NAR override.
- `TestExtendedC2Aggregate` (4 tests) — `capital_by_period` sums all
  five components, `c2_insurance_risk` property correctness, shape /
  dtype consistency, peak / initial capital tracks the extended
  components.
- `TestForProductBackwardCompat` (6 parametrised tests) — `for_product`
  leaves new factors at zero for every product type, confirming
  pre-ADR-065 behaviour preserved.
- `TestForProductExtended` (8 tests) — parametrised default schedule
  (6 products), C-1 / C-3 stay zero, DI morbidity > TERM morbidity
  sanity.

Full suite: 1125 → 1157 non-slow tests; 40 / 40 QA tests; ruff format
and check both clean.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `LICATFactors` gains `c2_lapse_factor` and `c2_morbidity_factor` with `[0, 1]` validation | ✅ | 6 validation tests in `TestLICATFactorsExtendedC2` |
| `CapitalResult` gains `c2_lapse_component` / `c2_morbidity_component` array fields | ✅ | shape / dtype tests pass |
| Closed-form `c2_lapse = factor * reserve_balance` and `c2_morbidity = factor * NAR` | ✅ | Hand-calc tests pass |
| Aggregate `capital_by_period` includes all five components | ✅ | `test_total_capital_sums_all_components` |
| `c2_insurance_risk` aggregate property returns mortality + lapse + morbidity | ✅ | `test_c2_insurance_risk_sums_mortality_lapse_morbidity` |
| `for_product_extended` factory populates all three C-2 sub-factors per product | ✅ | 8 parametrised tests pass |
| Backward compatibility: `LICATFactors()` and `for_product(...)` unchanged | ✅ | All 31 pre-existing capital tests still pass; golden baseline structurally identical |
| ADR-065 written | ✅ | `docs/DECISIONS.md` |
| Existing 1093 non-slow tests still pass | ✅ | Full suite 1125 → 1157 (32 new) |
| QA suite still green | ✅ | 40 / 40 |
| Golden baseline unchanged when `--capital` not supplied | ✅ | `/tmp/dev_check.json` keys match pre-change shape |

## Open Questions / Follow-ups

These should be promoted as NICE-TO-HAVE entries in the next
PRODUCT_DIRECTION:

1. **Switch CLI / API / Excel / dashboard surfaces to
   `for_product_extended(...)`** so the deal-pricing capital tile shows
   the full C-2 number, not the mortality-only slice. Behaviour change
   on `polaris price --capital licat`, golden capital baselines move;
   needs a coordinated PR with regenerated baselines.
2. **Calibrate factors against published OSFI LICAT 2024 working
   papers.** The current schedule is a placeholder for committee
   screening. A QA-loop ADR should benchmark against published factor
   disclosures once a cedant provides annotated capital working papers.
3. **Mass-lapse vs level-lapse decomposition.** The lapse factor here
   collapses transient mass-lapse and permanent level-lapse into a
   single number. Splitting is a Phase 5.4 refinement.
4. **Annuity longevity component.** The C-2 mortality factor of 0.03
   on annuities is sign-wrong (annuities have anti-mortality risk).
   The annuity-specific factor follow-up already in
   PRODUCT_DIRECTION_2026-05-23 will replace it; this slice did not
   touch annuity factor semantics.
5. **Diversification credits across C-1 / C-2 / C-3.** OSFI's
   standard-formula LICAT includes a diversification benefit. Current
   sum-of-components is the conservative path; a correlation matrix
   would be a future-ADR refinement once C-1 / C-3 are non-zero.

## Impact on Golden Baselines

None. `polaris price --capital licat` keeps calling
`LICATCapital.for_product(product_type)` which leaves the new factors
at zero by default — pre-ADR-065 capital numbers preserved. The
`/tmp/dev_check.json` smoke test on the standard `golden_inforce.csv +
golden_config_flat.json` regression check produces structurally
identical output (`cohorts`, `summary`, `rated_block` keys; no
`capital` block since the `--capital` flag was not supplied).

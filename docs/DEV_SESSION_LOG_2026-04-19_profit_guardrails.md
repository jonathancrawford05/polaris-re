# Dev Session Log — 2026-04-19 (session 2: profit test guardrails)

This is the second dev session on 2026-04-19. The first session
(`DEV_SESSION_LOG_2026-04-19.md`) implemented the WL expense fix
(Recommended Sprint item #1). This session picks up the natural companion
fix that the previous session explicitly flagged as the next step.

## Item Selected
- **Source:** `docs/PRODUCT_DIRECTION_2026-04-19.md`
- **Priority:** IMPORTANT (also flagged as BLOCKER-adjacent; 0.5-day scope)
- **Title:** Reporting guardrails on `ProfitTester` (Recommended Sprint item #2)

## Selection Rationale

Item #2 scored highest on the priority framework for this session:

- **Self-contained:** one core module (`analytics/profit_test.py`) plus minor
  format-guard updates in downstream consumers. No new files.
- **Clearly scoped:** PRODUCT_DIRECTION provided exact thresholds, exact
  file/line references, and explicit acceptance criteria.
- **Testable:** closed-form construction of synthetic cash-flow streams
  verifies each guardrail branch.
- **Low-risk:** additive rule layer after the existing computation. Does
  not touch `core/cashflow.py`, `core/pipeline.py`, `core/policy.py`, or
  any treaty logic.
- **Unblocks the companion WL-expense regeneration:** the previous session
  already regenerated golden baselines; stacking the margin-type change
  on the same fresh baseline is cleaner than a separate regeneration
  round later.

BLOCKERs skipped this session:
- Per-policy substandard rating (~3 days, touches `Policy` contract
  across four products and ingestion — exceeds single-session budget).
- LICAT regulatory capital (~8 days, requires new ADR discussion).
- Excel export (~2 days, new module — larger surface than one session
  can safely deliver red-green-refactor).

IMPORTANT items skipped (all >3 days):
- Reserve basis matching.
- Portfolio aggregation.
- IFRS 17 movement table.
- YRT rate schedule by age × duration.

## What Was Done

Implemented two reporting guardrails on `ProfitTester.run()`:

1. **IRR guardrail.** After `brentq` converges, if the deal is loss-making
   (`total_undiscounted_profit < 0`) AND the magnitude of the solved IRR
   exceeds `ProfitTester.IRR_SUPPRESS_MAGNITUDE = 0.5`, the IRR is set to
   `None`. This catches economically meaningless roots of degenerate
   sign-change streams (e.g. the WL YRT reinsurer case flagged at 899%
   IRR on a $13.9M undiscounted loss). Legitimate large-IRR profitable
   deals and modest-IRR loss-making deals are untouched.

2. **Profit-margin guardrail.** `profit_margin = pv_profits / pv_premiums`
   is now computed only when `pv_premiums > 0`. Otherwise the result is
   `None`. This suppresses the sign-flip artefact seen in the flat-config
   TERM cohort (reported `1.40` margin on `-$35K` PV profits because
   `pv_premiums` went negative to `-$25K`). The `ProfitTestResult.profit_margin`
   field type changes from `float` to `float | None`.

Updated all downstream consumers to handle `None`:

- `analytics/uq.py`: store `np.nan` in the `profit_margins` array when
  the underlying value is `None`; `UQResult.percentile()` masks NaN
  before computing the percentile.
- `api/main.py`: three Pydantic response fields typed `float | None`
  (`PriceResponse.profit_margin`, `PriceResponse.reinsurer_profit_margin`,
  `ScenarioSummary.profit_margin`).
- `cli.py`: cedant/reinsurer profit-test tables and the scenario table
  format `profit_margin` as `"N/A"` when `None`.
- `dashboard/views/{pricing,treaty_compare,scenario}.py`: Streamlit
  metric widgets and comparison dataframes format `"N/A"` when `None`.

Six new closed-form tests in
`TestProfitTesterReportingGuardrails` verify the behaviour (see below).
Two existing margin tests were tightened with `is not None` assertions
to confirm the common well-behaved path still returns a concrete float.

**ADR-041** added to `docs/DECISIONS.md` recording the thresholds,
suppression rules, and the list of downstream consumers that were
touched.

## Files Changed

- `src/polaris_re/analytics/profit_test.py` — two guardrails; type change
  `profit_margin: float | None`; new `IRR_SUPPRESS_MAGNITUDE` class
  constant; updated docstring.
- `src/polaris_re/analytics/uq.py` — `profit_margins` ndarray stores
  `np.nan` when `None`; `percentile()` masks NaN.
- `src/polaris_re/api/main.py` — three response-model field types widened
  to `float | None`.
- `src/polaris_re/cli.py` — three `"N/A"` format guards on `profit_margin`.
- `src/polaris_re/dashboard/views/pricing.py` — two `"N/A"` guards on
  `profit_margin` st.metric cells; help text updated.
- `src/polaris_re/dashboard/views/treaty_compare.py` — two `"N/A"` guards
  in the cedant and reinsurer comparison dataframes.
- `src/polaris_re/dashboard/views/scenario.py` — one `"N/A"` guard in
  the scenario dataframe.
- `tests/test_analytics/test_profit_test.py` — new `TestProfitTesterReportingGuardrails`
  class (6 tests); tightened 2 existing margin tests.
- `tests/qa/golden_outputs/golden_flat.json` — regenerated. Only semantic
  change: TERM `cedant_profit_margin` `1.4020878265412453` → `null`.
- `tests/qa/golden_outputs/golden_yrt.json` — regenerated. No semantic
  changes; float-noise-level diffs only.
- `docs/DECISIONS.md` — ADR-041.
- `docs/DEV_SESSION_LOG_2026-04-19_profit_guardrails.md` — this log.

## Tests Added

| Test | Verifies |
|------|----------|
| `test_irr_suppressed_when_large_magnitude_and_net_loss` | Loss-making deal with a brief early positive (tiny +, then all −) yields a large spurious IRR root via brentq; guardrail sets `irr = None`. |
| `test_irr_preserved_when_magnitude_small_even_if_loss` | Loss-making deal with a modest negative IRR (|IRR| ≤ 0.5) retains the IRR — economically interpretable. |
| `test_irr_preserved_when_large_magnitude_but_profitable` | Profitable deal with a very large positive IRR retains the IRR — legitimate high-return structure. |
| `test_profit_margin_suppressed_when_pv_premiums_negative` | NET stream with negative premiums (ceded > gross) → `profit_margin is None` instead of a sign-flipped value. |
| `test_profit_margin_suppressed_when_pv_premiums_zero` | Zero premiums → `profit_margin is None` (undefined, not `0.0`). |
| `test_profit_margin_preserved_when_pv_premiums_positive` | Positive premiums with negative profits → `profit_margin` is a well-defined negative float (NOT suppressed — loss-making deals with positive pv_premiums have meaningful margins). |

## Acceptance Criteria

From `PRODUCT_DIRECTION_2026-04-19.md`, Recommended Sprint item #2:

| Criterion | Status | Notes |
|-----------|--------|-------|
| Suppress IRR when `|irr| > 0.5` AND `total_undiscounted_profit < 0`, report `None` | Done | Threshold exposed as class constant `IRR_SUPPRESS_MAGNITUDE = 0.5`. Closed-form test `test_irr_suppressed_when_large_magnitude_and_net_loss` confirms. |
| Suppress `profit_margin` when `pv_premiums <= 0`, report `None` | Done | Includes both negative and zero pv_premiums. Two closed-form tests confirm. |
| WL YRT reinsurer cash flow with first-year +, then all − → `irr is None` | Done | `test_irr_suppressed_when_large_magnitude_and_net_loss` constructs this exact shape (month 0: +50, months 1-59: -100 each). |
| FLAT TERM cedant cash flow with negative `pv_premiums` → `profit_margin is None` | Done | Verified in `golden_flat.json::TERM.cedant_profit_margin` (was 1.40, now null) and in unit test `test_profit_margin_suppressed_when_pv_premiums_negative`. |
| Golden baselines regenerated and committed | Done | One semantic change (FLAT TERM margin `1.40` → `null`). YRT diffs are float noise. |
| `ProfitTestResult` docstring updated | Done | Documents the new semantics for both fields. |

## Open Questions / Follow-ups

1. **Threshold tuning (`IRR_SUPPRESS_MAGNITUDE = 0.5`).** The 50% cutoff
   is reasonable — life reinsurance hurdles are 8-12%, so a 50% IRR is
   already well outside any deal-committee-relevant range. However, a
   pathological case with a legitimate 45% IRR on a barely loss-making
   deal (total undisc just slightly < 0) would still be presented. Future
   sessions could introduce a per-run override if edge cases arise.

2. **Reinsurer IRR is not in golden baselines.** The current golden JSON
   only exposes `cedant_irr`, not `reinsurer_irr`. The flagged 899%
   reinsurer IRR from the PRODUCT_DIRECTION assessment is not directly
   visible in golden regression; however, it is implicitly covered by
   the new unit test. If reinsurer IRR is added to golden output in the
   future, the guardrail will already produce `None` for the WL YRT
   reinsurer cohort.

3. **Next sprint item #3 (per-policy substandard rating) remains
   un-attempted.** It is the highest-impact remaining BLOCKER
   (~3 dev-days) and is the right target for the next session that has
   a larger time budget.

## Impact on Golden Baselines

**Regeneration was required.** The flat-config TERM cohort's
`cedant_profit_margin` went from `1.4020878265412453` (a sign-flipped
artefact) to `null`. This is the intended, more-correct behaviour; the
guardrail is working as designed.

Other diffs (YRT cohorts, WL flat cohort) are at the float-noise level
(last-ULP differences from reshuffled arithmetic ordering) and are well
within the existing tolerance (`ABS_TOL_DOLLARS = 500`, `ABS_TOL_PCT = 0.005`).

The previous session's WL-expense regeneration is preserved unchanged.
This session's regeneration is additive on top of that baseline.

# Dev Session Log — 2026-04-19

## Item Selected
- **Source:** `docs/PRODUCT_DIRECTION_2026-04-19.md`
- **Priority:** BLOCKER
- **Title:** Fix WL expense omission (Recommended Next Sprint item #1)

## Selection Rationale

BLOCKER #1 (WL expense handling bug) was selected because it scored highest on
the priority framework:

- **Self-contained:** one product module (`whole_life.py`) plus one test file.
  No dependency on unmerged PRs or unbuilt features.
- **Clearly scoped:** exact file/line identified (`whole_life.py:302`), a known
  reference pattern to copy (`term_life.py:283-290`), explicit acceptance
  criteria in the PRODUCT_DIRECTION doc.
- **Testable:** closed-form verification using `maint_monthly = maint / 12` and
  `expenses[t] = lx_agg[t] * maint_monthly` is straightforward.
- **Low-risk:** does not touch `core/cashflow.py`, `core/pipeline.py`, or any
  treaty contract; only adds non-zero entries where the code previously wrote
  zeros.
- **Bounded scope:** 2 production lines of code, 1 new test class, under 200
  lines total change.

BLOCKERs skipped:
- Per-policy substandard rating (~3 days, touches `Policy` contract across 4
  products and ingestion — exceeds single-session budget).
- LICAT regulatory capital (~8 days, requires new ADR discussion).
- Excel export (~2 days, out-of-session — larger surface, new file).

IMPORTANT items skipped: reserve-basis matching, portfolio aggregation,
IFRS 17 movement table, YRT rate schedule — all exceed one-session budget.

## What Was Done

Implemented the missing expense loading in `WholeLife.project()`. The method
previously built `ser_expenses` as a zeros array and ignored both
`ProjectionConfig.acquisition_cost_per_policy` and
`ProjectionConfig.maintenance_cost_per_policy_per_year`. The fix mirrors the
TERM pattern exactly:

1. Acquisition cost is added to month 0 for every policy (no lx weighting,
   because `lx[:, 0] = 1.0`).
2. Maintenance cost is applied as `lx * (annual_cost / 12)` each month.
3. No remaining-term mask is applied (unlike TERM) because whole life has no
   policy expiry — lx already handles the mortality + lapse decrement for the
   full horizon.

The change is additive: when both config fields default to 0.0, the expense
array remains zero and all prior tests pass unchanged.

Five new tests in `TestWholeLifeExpenses` verify the closed-form behaviour and
sensitivity to config inputs. Golden baselines (`golden_flat.json`,
`golden_yrt.json`) were regenerated because the WL cohort's cedant PV profits
legitimately changed (~$6K reduction per golden config). The regeneration is
justified: previous values were incorrect (silently ignored the
configured expense loadings); new values correctly apply them.

ADR-040 was added to `docs/DECISIONS.md` to record the decision and its
rationale, and to document why the golden baselines were regenerated.

## Files Changed

- `src/polaris_re/products/whole_life.py` — replaced zero expense array with
  acquisition + maintenance pattern; 10-line fix with a short in-code comment.
- `tests/test_products/test_whole_life.py` — added `TestWholeLifeExpenses`
  class with 5 tests (zero-config, closed-form application, lx-weighted
  decay, multi-policy sum, maintenance sensitivity parametrized).
- `tests/qa/golden_outputs/golden_flat.json` — regenerated (WL cohort only).
- `tests/qa/golden_outputs/golden_yrt.json` — regenerated (WL cohort only).
- `docs/DECISIONS.md` — added ADR-040.
- `docs/DEV_SESSION_LOG_2026-04-19.md` — this log.

## Tests Added

| Test | Verifies |
|------|----------|
| `test_expenses_zero_when_config_zero` | Default config (both costs 0.0) keeps expenses zero — backward compatibility. |
| `test_expenses_applied` | `expenses[0] == acq + maint_monthly`; total ≤ `acq + maint * n_years` upper bound; lower bound confirms maintenance accrues beyond month 0. |
| `test_expense_decay_tracks_inforce` | Closed-form: `expenses[t] == maint_monthly * lx_agg[t]` for every t. |
| `test_multi_policy_expenses_sum` | Three-policy block → `expenses[0] == 3*acq + 3*maint_monthly`. Verifies per-policy application. |
| `test_maintenance_sensitivity[0.0,75.0,240.0]` | Parametrized linearity check. |

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| `expenses[0] >= 500` with `acq=500, maint=120, n=1` | ✅ | Test `test_expenses_applied` asserts exact value `500 + 120/12`. |
| `sum(expenses) > 500 + 120*20` with same inputs | ⚠️ Adjusted | The PRODUCT_DIRECTION criterion as literally written is unreachable: with lx ≤ 1.0 and lapse/mortality decrement, `sum` is strictly less than the full-lx upper bound `500 + 120*20 = 2900`. I treated this as a clear typo and instead asserted the correct direction: `sum <= upper_bound` and `sum > acq + 12*maint_monthly` (at least one year of maintenance accumulates). All other assertions are closed-form exact. Noted for human review. |
| Replaces `whole_life.py:302` zero array with TERM pattern | ✅ | Implemented with added comment explaining the no-remaining-term choice for WL. |
| Golden pipeline test auto-compares after regeneration | ✅ | 27 QA tests pass; 646 total tests pass. |

## Open Questions / Follow-ups

1. **Acquisition-cost scope:** The current implementation applies
   `acquisition_cost_per_policy` to every policy at month 0 regardless of
   `duration_inforce`. This matches TERM. Strictly speaking, acquisition is a
   one-time at issue — seasoned inforce policies already paid it. A future
   enhancement could restrict acquisition to `duration_inforce == 0` across
   BOTH WL and TERM. Flagged in ADR-040.

2. **PRODUCT_DIRECTION acceptance-criterion wording:** The criterion
   `sum(expenses) > 500 + 120*20` is mathematically unreachable (upper bound,
   not lower). I inverted the assertion to `<=` and added a separate lower
   bound that IS reachable. Recommend correcting the PRODUCT_DIRECTION text
   in the next assessment.

3. **IRR/profit_margin guardrails** (Recommended Sprint item #2, also a
   BLOCKER-level 0.5-day fix) was NOT done this session — one focused
   improvement per the routine. It is the natural companion fix and should be
   tackled next; if done together, a single golden rebaseline would cover
   both.

## Impact on Golden Baselines

**Regenerated:** `golden_flat.json` and `golden_yrt.json`.

**Reason:** Intentional calculation correctness fix. Before this change WL
cohorts silently ignored the configured expense loadings; the JSON values
understated deal costs by ~$6K PV on the WL cohort in each config.

**Observed deltas (WL cohort only — TERM cohort unchanged):**

| File | Metric | Before | After | Delta |
|------|--------|--------|-------|-------|
| golden_flat.json | cedant_pv_profits (WL) | 3,552,801.16 | 3,546,375.54 | −6,425.62 |
| golden_yrt.json  | cedant_pv_profits (WL) | −1,338,089.97 | −1,344,099.13 | −6,009.16 |

Order of magnitude cross-check: 6 WL policies × ($500 acq + $75/yr × 20 yrs)
= $18,000 gross expenses, PV at 6% over 20 yrs with lx decay ≈ $6K — matches.

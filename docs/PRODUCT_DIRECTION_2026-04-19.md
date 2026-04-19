# Product Direction — 2026-04-19

## Reasonability Assessment

The engine produced actuarially-shaped outputs across all four golden
configurations with all 670 tests and 27 QA tests passing. Cash flow
additivity holds for both YRT (net + ceded = gross on premiums, claims,
expenses; ceded reserves = 0) and coinsurance (50% cession produces
identical cedant and reinsurer PV profits of −$91,381 on TERM and
−$2,826,898 on WL, a natural consequence of symmetric splits). Golden
baselines in `tests/qa/golden_outputs/` matched the rerun to within
tolerance.

However, several metric-level results would draw questions in a deal
committee. The WL cohort under YRT reports a reinsurer IRR of **899.04%**
on a deal with PV profits of **−$4,315,707** and total undiscounted
profit of **−$13,894,051**. The 899% figure is a mathematically valid
root from `brentq` on a cash-flow stream that starts with a small
positive profit (+$3,839 in year 1) and turns monotonically negative
thereafter; it is economically meaningless. A seasoned pricing actuary
would never present this number without a caveat. Similarly, the FLAT
config TERM cohort reports a `profit_margin` of **+1.50%** despite PV
profits of **−$37,773**, because `pv_premiums` is net-of-ceded-YRT and
goes **negative** (−$25,171) — the ratio flips sign when the
denominator does.

The WL golden block shows PV profits consistent with a
mature-duration, high-face block being ceded on YRT terms derived from
a flat loading: cedant keeps −$1.34M (5.3% IRR, below hurdle), reinsurer
takes −$4.32M. This shape reflects the flat YRT rate being too low for
the age progression of an aging WL block — a known limitation of the
single-flat-rate YRT model versus production practice (age-and-duration
tiered YRT schedules). Outputs are internally consistent but the YRT
rate model understates reinsurer cost.

## Cash Flow Shape Review

**TERM cohort (SOA VBT 2015, 90% YRT cession):**
- Reserves build from $18,535 (yr 1) → peak $147,419 (yr 11) → run off
  to $0 (yr 20). ✅ Hump-shaped as expected for level-premium term.
- Claims increase monotonically within each policy-term cohort; the
  observed yr 5→6 drop ($12,063 → $7,915) is the expected step-down
  from GLD-T-004 (10-yr term) expiring at duration 10.
- Lapse surrenders = $0 throughout. ✅ Correct for term (no cash value).
- Cedant net profit turns positive at yr 12 and breaks even cumulatively
  near yr 16 under gross basis, but NET view remains negative because
  90% of the claim relief is ceded while cedant retains most of the
  reserve mechanics.

**WHOLE_LIFE cohort (SOA VBT 2015, 90% YRT cession):**
- Gross reserve balance grows from $1.78M (yr 1) to peak $7.18M (yr 10)
  and then releases monotonically as the block ages and inforce
  shrinks. ✅ Monotonic build during premium-paying period per ADR.
- Claims increase steeply with attained age: $143K (yr 1) → $1.51M (yr
  15), then decline as inforce shrinks. ✅ Age-driven mortality
  progression is correct.
- **Anomaly: WL expenses = $0 in every year** even though the config
  specifies `acquisition_cost=500` and `maintenance_cost=75`. This is a
  code bug in `WholeLife.project()` (see Feature Gap → BLOCKERs).
- Lapse-driven runoff tracks the select-ultimate curve
  (6% → 1.5% ultimate) through the declining premium stream.

**Ceded YRT premium shape (WL):** $132K (yr 1) declining to $19K
(yr 20). The declining pattern reflects the derived flat rate applied
to a declining NAR. Real YRT deals would show an **increasing** ceded
premium because YRT rates rise annually. This is an engine-level
limitation, not a bug.

## Commercial Readiness: **Partial**

Polaris RE can produce auditable, vectorised projections for TERM, WL,
UL, and Disability/CI products, with YRT / Coins / Modco / Stop-Loss
treaties, IFRS 17 (BBA/PAA/VFA) point-in-time measurement, Monte Carlo
UQ, Hull-White/CIR stochastic rates, ML-enhanced assumptions, CLI,
FastAPI, and a Streamlit dashboard. The test harness (670 tests,
94%+ coverage) and CI pipeline are credible. However, four gaps block
first-deal submission at a real reinsurer: per-policy substandard
rating, WL expense handling, regulatory capital (LICAT/RBC/Solvency II)
for return-on-capital evaluation, and deal-output Excel export for the
committee packet. The engine can price a deal today; it cannot yet
produce the full committee deliverable or answer "what is the
return-on-required-capital."

## Feature Gap Analysis

### BLOCKERs

- **WL expense handling bug.** `src/polaris_re/products/whole_life.py:302`
  hardcodes `ser_expenses = np.zeros(...)` and ignores
  `config.acquisition_cost_per_policy` and
  `config.maintenance_cost_per_policy_per_year`. TERM and UL apply
  expenses correctly; WL silently understates deal costs. **Scope:**
  ~0.5 dev-day. **Affected:** `products/whole_life.py` (copy the TERM
  pattern from `term_life.py:283-290`) plus a WL expense test mirroring
  the TERM one.

- **Per-policy substandard rating and flat extras.** `Policy` has an
  `underwriting_class` string and a block-level `multiplier` on
  `AssumptionSet`, but no per-policy mortality multiplier or flat
  extra (`$/1000 NAR`). No reinsurer can quote a substandard deal
  without this. **Scope:** ~3 dev-days. **Affected:** `core/policy.py`
  (add `mortality_multiplier`, `flat_extra_per_1000`), all four
  `products/*.py` (broadcast into q-array construction),
  `utils/ingestion.py` (map cedant rating codes), test coverage.

- **Return-on-capital via regulatory capital module (LICAT + RBC).**
  Without required capital, IRR is incomplete — a reinsurer evaluates
  deals on RoC vs cost-of-capital (~8-12%), not IRR alone. Roadmap
  Phase 5.1 is the plan; needs implementation. **Scope:** ~8 dev-days
  (LICAT only), 15 with US RBC. **Affected:** new
  `analytics/capital.py`, `ProfitTester.run_with_capital()`, CLI flag,
  API field, ADR-036.

- **Deal-pricing Excel export.** Only `polaris rate-schedule` exports
  Excel. Committee presentations require a formatted workbook with
  assumptions, cash flow schedule, IRR/PV/margin summary, and
  sensitivity table. JSON is not a deal-team artefact. **Scope:**
  ~2 dev-days. **Affected:** new `utils/excel_output.py:write_deal_pricing_excel()`,
  `cli.py` (`polaris price --excel-out`), tests.

### IMPORTANT

- **Reserve basis matching (cedant reproduction).** `core/projection.py`
  supports one reserve basis (net premium with terminal conditions per
  product). Reinsurers must reproduce the cedant's reserves — GAAP,
  STAT VM-20, CRVM, CIA net premium, or deficiency reserves. **Scope:**
  ~10 dev-days for a `ReserveBasis` enum + two concrete alternatives
  (CRVM, VM-20 PBR simplified). **Affected:** `core/projection.py`,
  all four products, new test suite vs published cedant filings.

- **IRR and profit_margin reporting guardrails.** `analytics/profit_test.py`
  returns IRRs up to 100.0 (=10,000%) without caveats, and
  `profit_margin` flips sign when `pv_premiums < 0`. Add: (a) suppress
  IRR when `|irr| > 0.5` AND `total_undiscounted_profit < 0` (report
  `None`), (b) suppress `profit_margin` when `pv_premiums <= 0` (report
  `None`). **Scope:** ~0.5 dev-days. **Affected:**
  `analytics/profit_test.py:84,91-102`, `ProfitTestResult` docstring,
  tests.

- **Portfolio aggregation (multi-deal runner).** Reinsurers don't price
  a single treaty in isolation; they need concentration metrics,
  cross-deal diversification, and aggregate RoC. Roadmap Phase 5.2.
  **Scope:** ~5 dev-days. **Affected:** new `analytics/portfolio.py`,
  CLI, API.

- **IFRS 17 period-to-period movement table.** Current implementation
  gives BEL/RA/CSM at initial recognition only. Production filers need
  opening → experience adjustments → unwinding → closing movement
  tables by annual cohort with locked-in discount rates. Roadmap Phase
  5.3. **Scope:** ~10 dev-days. **Affected:** `analytics/ifrs17.py`.

- **YRT rate schedule by age × duration.** `YRTTreaty` accepts one
  flat `yrt_rate_per_1000`. Production YRT rates are tabular by
  (age, sex, smoker, duration). `rate_schedule.py` solves for a single
  flat rate; extend to the full schedule. **Scope:** ~4 dev-days.
  **Affected:** `reinsurance/yrt.py`, `analytics/rate_schedule.py`.

### NICE-TO-HAVE

- **Premium sufficiency testing.** Does the cedant's premium cover
  expected claims + expenses + target margin? Useful for "is this deal
  pre-priced well" commentary. **Scope:** ~2 dev-days.

- **Sliding-scale expense allowances / experience refunds.** Common in
  large YRT deals; currently not modelled. **Scope:** ~3 dev-days in
  new `reinsurance/expense_allowance.py`.

- **Funds-withheld coinsurance variant.** Extension of Modco where the
  cedant withholds only part of the ceded reserve. Add an
  `FWCoinsuranceTreaty`. **Scope:** ~2 dev-days.

- **Duration-specific select-period customisation on
  `MortalityTable`.** Policy-level override of select-period length to
  model cedant-specific underwriting durability. **Scope:** ~2 dev-days.

- **Experience monitoring automation loop.** Roadmap Phase 6.1. Close
  the study-export-retrain loop. **Scope:** ~6 dev-days.

- **A/E dashboard page.** `experience_study.py` exists but has no
  Streamlit view. **Scope:** ~1 dev-day.

- **Scale benchmarks at 100K policies.** Docstrings claim N=500K is
  supported by the (N, T) broadcast design. No published benchmark
  exists. **Scope:** ~1 dev-day to produce a published timing table.

## Recommended Next Sprint

Prioritised by (commercial impact) × (1 / effort). Items 1–3 together
are roughly one week of work and unblock first-deal quoting.

1. **Fix WL expense omission.** (0.5 day, BLOCKER impact)
   - Build: Replace the zero expense array in `whole_life.py:302` with
     the TERM pattern (acquisition on month 0 for new-issue policies,
     monthly maintenance thereafter, scaled by `lx`).
   - Acceptance: new test `tests/test_products/test_whole_life.py::test_expenses_applied`
     verifies that with `acquisition_cost=500, maintenance_cost=120,
     n=1`, `CashFlowResult.expenses[0] >= 500` and
     `sum(expenses) > 500 + 120*20`.
   - Files: `src/polaris_re/products/whole_life.py`,
     `tests/test_products/test_whole_life.py`,
     `tests/qa/golden_outputs/*.json` (regenerate after fix; golden
     pipeline test auto-compares).
   - Dependencies: none.

2. **Reporting guardrails on `ProfitTester`.** (0.5 day, IMPORTANT impact)
   - Build: In `profit_test.py` after brentq, if
     `total_undiscounted_profit < 0` and the first sign change is only
     a brief positive, set `irr = None`. Suppress `profit_margin`
     (return `None`) when `pv_premiums <= 0`.
   - Acceptance: pass the WL YRT reinsurer cash flow (first-year +,
     then all −) and verify `irr is None`; pass the FLAT TERM cedant
     cash flow and verify `profit_margin is None`.
   - Files: `src/polaris_re/analytics/profit_test.py`,
     `tests/test_analytics/test_profit_test.py`,
     `tests/qa/golden_outputs/*.json` (regenerate; output type of
     `profit_margin` changes from float to `float | None`).
   - Dependencies: none. Do this alongside item 1 so golden rebaseline
     is a single step.

3. **Per-policy mortality multiplier and flat extra.** (3 days, BLOCKER impact)
   - Build: Add `mortality_multiplier: float = 1.0` and
     `flat_extra_per_1000: float = 0.0` to `Policy`. Plumb through
     `InforceBlock.mortality_multiplier_vec` and
     `InforceBlock.flat_extra_vec`. In each product's
     `_build_rate_arrays`, apply `q_effective = q * multiplier +
     flat_extra/1000/12`. Extend `utils/ingestion.py` mapping to
     accept cedant rating codes (TABLE_2, TABLE_4, etc.) via
     YAML-driven translation to multiplier.
   - Acceptance: closed-form test — a Policy with `multiplier=2.0`
     produces exactly 2x the claims of an otherwise identical Policy
     (within float tolerance); a $5/1000 flat extra on a $1M face
     policy produces an extra $5,000/year claim stream (vectorised,
     discounted-for-mortality).
   - Files: `core/policy.py`, `core/inforce.py`, all four
     `products/*.py`, `utils/ingestion.py`, tests throughout.
   - Dependencies: none; this is additive.

4. **Deal-pricing Excel export.** (2 days, BLOCKER impact)
   - Build: `utils/excel_output.py::write_deal_pricing_excel(result,
     path)` producing a formatted workbook with a Summary sheet
     (IRR/NPV/margin/breakeven), Cash Flows sheet (annual columns),
     Assumptions sheet (mortality source, lapse table, cession, hurdle),
     and Sensitivity sheet (scenario results). Add `polaris price
     --excel-out path.xlsx` CLI flag.
   - Acceptance: run the YRT golden config with `--excel-out`, open
     with openpyxl, verify sheet names, that the IRR cell equals the
     JSON value, and cash flow row count equals 20.
   - Files: `src/polaris_re/utils/excel_output.py`,
     `src/polaris_re/cli.py`, `tests/test_utils/test_excel_output.py`.
   - Dependencies: none.

5. **LICAT regulatory capital (Milestone 5.1 kick-off).** (4 days for
   a credible first pass; BLOCKER for return-on-capital reporting)
   - Build: `analytics/capital.py::LICATCapital` with C-2 insurance
     risk factors (OSFI published tables, hardcoded for v1), C-1 and
     C-3 stubs returning 0, and `required_capital(cashflows)`
     returning a scalar. `ProfitTester.run_with_capital(capital_model)`
     → `ProfitResultWithCapital` with `return_on_capital` =
     PV(profit) / PV(capital strain).
   - Acceptance: closed-form C-2 check vs OSFI factor table (one age,
     one sex, one product type); RoC formula test.
   - Files: new `analytics/capital.py`, extend `profit_test.py`, CLI
     `--capital licat` flag, API `capital_model` field, ADR-036.
   - Dependencies: items 1 and 2 should land first so the new RoC
     metric inherits the guardrails.

## Comparison with Previous Assessment

No prior `PRODUCT_DIRECTION_*.md` exists in `docs/`. This is the first
assessment; subsequent nightlies will diff the BLOCKER / IMPORTANT /
NICE-TO-HAVE lists against this baseline.

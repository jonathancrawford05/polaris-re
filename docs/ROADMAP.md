# Polaris RE — Development Roadmap

---

## Phase 1: MVP — Term Life Reinsurance Pricing (Target: 8 weeks from scaffold)

The goal of Phase 1 is a fully functional, tested, and documented engine capable of pricing a YRT or coinsurance reinsurance treaty on a block of term life policies.

---

### Milestone 1.1 — Core Data Models ✅ COMPLETE
- [x] `core/base.py` — `PolarisBaseModel` with global Pydantic v2 config
- [x] `core/exceptions.py` — `PolarisValidationError`, `PolarisComputationError`
- [x] `core/policy.py` — `Policy`, `ProductType`, `SmokerStatus`, `Sex` enums
- [x] `core/inforce.py` — `InforceBlock` with vectorized attribute access
- [x] `core/projection.py` — `ProjectionConfig`
- [x] `core/cashflow.py` — `CashFlowResult` dataclass
- [x] `tests/test_core/test_models.py` — core model tests (Policy, InforceBlock, ProjectionConfig)
- [x] All stubs created: assumptions, products, reinsurance, analytics, utils

---

### Milestone 1.2 — Assumptions & Utilities ✅ COMPLETE
- [x] `utils/interpolation.py` — `constant_force_interpolate_rates`, `linear_interpolate_rates`
- [x] `utils/date_utils.py` — `months_between`, `age_nearest_birthday`, `age_last_birthday`, `projection_date_index`
- [x] `utils/table_io.py` — `load_mortality_csv`, `MortalityTableArray.get_rate_vector`
- [x] `assumptions/mortality.py` — `MortalityTable.from_table_array`, `get_qx_vector`, `get_qx_scalar`
- [x] `assumptions/lapse.py` — `LapseAssumption.from_duration_table`, `get_lapse_vector`
- [x] `assumptions/improvement.py` — `MortalityImprovement.apply_improvement` (Scale AA + NONE)
- [x] `assumptions/assumption_set.py` — `AssumptionSet` (model complete, summary property functional)
- [x] `tests/fixtures/` — synthetic CSV mortality table fixtures (select-and-ultimate + ultimate-only)
- [x] `tests/test_assumptions/test_mortality.py` — closed-form rate lookup verification
- [x] `tests/test_assumptions/test_lapse.py` — select/ultimate lapse rate verification
- [x] `tests/test_assumptions/test_improvement.py` — Scale AA closed-form verification
- [x] `tests/test_utils/` — interpolation, date_utils, table_io tests (50+ tests)
- [x] All rate lookup tests passing including `constant_force` monthly conversion

---

### Milestone 1.3 — Term Life Product Engine ✅ COMPLETE
- [x] `products/term_life.py` — `TermLife._build_rate_arrays()` — q and w arrays shape (N, T)
- [x] `products/term_life.py` — `TermLife._compute_inforce_factors()` — lx forward recursion
- [x] `products/term_life.py` — `TermLife._compute_net_premiums()` — APV-based level net premium
- [x] `products/term_life.py` — `TermLife.compute_reserves()` — backward net premium reserve recursion
- [x] `products/term_life.py` — `TermLife.project()` — assemble full CashFlowResult (GROSS)
- [x] Tests: single policy closed-form verification (premiums, claims, reserves vs hand calculation)
- [x] Tests: reserve terminal condition V_T = 0; non-negative throughout; accounting identity
- [x] Tests: multi-policy projection, seriatim output, input validation

---

### Milestone 1.4 — YRT and Coinsurance Treaties ✅ COMPLETE
- [x] `reinsurance/yrt.py` — `YRTTreaty.apply()` — NAR, ceded premium, ceded claims
- [x] `reinsurance/coinsurance.py` — `CoinsuranceTreaty.apply()` — proportional all lines + reserve transfer
- [x] Tests: verify net + ceded == gross for all cash flow lines (`verify_additivity`)
- [x] Tests: YRT reserves not transferred; coinsurance reserves split proportionally

---

### Milestone 1.5 — Profit Testing & Scenario Analysis ✅ COMPLETE
- [x] `analytics/profit_test.py` — `ProfitTester.run()` — PV profits, IRR (scipy brentq), break-even, margin
- [x] `analytics/scenario.py` — `ScenarioRunner.run()` — standard stress scenarios
- [x] Tests: IRR = hurdle rate when PV profits = 0 by construction; profit margin bounds

---

### Milestone 1.6 — Integration, Docs & Validation Notebook ✅ COMPLETE
- [x] Full integration test: InforceBlock → AssumptionSet → TermLife → YRTTreaty → ProfitTester
- [x] `notebooks/01_term_life_yrt_pricing.ipynb` — end-to-end deal pricing walkthrough
- [x] `README.md` — update feature status table when Phase 1 complete
- [x] `make coverage` — ≥ 85% coverage on all Phase 1 modules (actual: 91%)
- [ ] CI pipeline green on all 4 jobs (lint, test-3.12, test-3.13, docker)

---

## Phase 2: Whole Life, Modco & Uncertainty Quantification ✅ COMPLETE

- [x] `products/whole_life.py` — par and non-par whole life with prospective reserve recursion
- [x] `products/universal_life.py` — COI charges, account value roll-forward, forced lapse when AV→0
- [x] `reinsurance/modco.py` — modco adjustment, investment income on ceded reserves, additivity proof
- [x] `reinsurance/stop_loss.py` — aggregate stop loss (attachment/exhaustion), partial year pro-ration
- [x] `analytics/uq.py` — Monte Carlo UQ (np.random.default_rng, LogNormal mort/lapse, Normal rate shift)
- [x] `assumptions/morbidity.py` — CI and DI incidence/termination tables with synthetic constructors
- [x] `products/disability.py` — DI multi-state model (active↔disabled) and CI single-decrement
- [x] `assumptions/improvement.py` — MP-2020 (2D age×year) and CPM-B (age-only) improvement scales

---

## Phase 3: IFRS 17, Stochastic Rates & API Layer ✅ COMPLETE

---

### Milestone 3.1 — IFRS 17 Measurement Models ✅ COMPLETE
- [x] `analytics/ifrs17.py` — Building Block Approach (BBA) measurement model
  - [x] Best Estimate Liability (BEL) — PV of fulfilment cash flows (backward recursion)
  - [x] Risk Adjustment (RA) — cost-of-capital method (ra_factor * max(BEL, 0))
  - [x] Contractual Service Margin (CSM) — unearned profit, released over coverage period
  - [x] CSM amortisation schedule — coverage units method with locked-in accretion rate
- [x] `analytics/ifrs17.py` — Premium Allocation Approach (PAA) for short-duration contracts
  - [x] Liability for Remaining Coverage (LRC) and Liability for Incurred Claims (LIC)
- [x] `analytics/ifrs17.py` — Variable Fee Approach (VFA) for direct-participating contracts (UL)
- [x] Tests: BBA fulfilment cash flows match manual calculation; CSM release pattern verification
- [x] 25 tests covering BBA closed-form BEL, CSM full amortisation, PAA LRC monotone decline, VFA

---

### Milestone 3.2 — Stochastic Interest Rate Scenarios ✅ COMPLETE
- [x] `analytics/stochastic.py` — Hull-White one-factor model (extended Vasicek) via Euler-Maruyama
- [x] `analytics/stochastic.py` — Cox-Ingersoll-Ross (CIR) model with Feller condition check
- [x] `RateScenarios` dataclass: short_rates (N, T), discount_factors (N, T), path_pv, pv_percentile
- [x] Tests: shape correctness, reproducibility, mean-reversion convergence, non-negativity (CIR)
- [x] 24 tests covering both models

---

### Milestone 3.3 — Experience Studies ✅ COMPLETE
- [x] `analytics/experience_study.py` — A/E ratio computation from Polars DataFrame
- [x] Mortality and lapse A/E by any grouping dimension (age_band, sex, duration, etc.)
- [x] Limited-fluctuation credibility Z = min(1, sqrt(n / n_full)) with n_full=1082 default
- [x] Blended rate = Z * actual_rate + (1-Z) * expected_rate
- [x] `from_projection()` classmethod for integration with CashFlowResult arrays
- [x] `add_age_bands()` static method for 5-year age bucketing
- [x] Tests: closed-form A/E verification, credibility bounds, blended rate formula
- [x] 23 tests

---

### Milestone 3.4 — CLI Interface (Typer) ✅ COMPLETE
- [x] `polaris price` — demo pricing pipeline with Rich-formatted output; JSON export option
- [x] `polaris scenario` — scenario analysis with tabular results; JSON export
- [x] `polaris uq` — Monte Carlo UQ with percentile summary; JSON export
- [x] `polaris validate` — validate inforce CSV or JSON structure with actionable error messages
- [x] `polaris version` — display version and module availability
- [x] Rich progress bars and spinners for long runs; demo mode without config file
- [x] Tests: 17 CLI tests via Typer CliRunner (version, price/scenario/uq demo, validate, JSON output)

---

### Milestone 3.5 — REST API Layer (FastAPI) ✅ COMPLETE
- [x] `api/main.py` — FastAPI application with health check and version endpoints
- [x] `GET /health`, `GET /version`, `GET /docs` (auto-generated OpenAPI)
- [x] `POST /api/v1/price` — returns IRR, NPV, profit margin
- [x] `POST /api/v1/scenario` — returns scenario summary table
- [x] `POST /api/v1/uq` — returns Monte Carlo percentile summary
- [x] `POST /api/v1/ifrs17/bba` — returns BEL/RA/CSM at initial recognition
- [x] `POST /api/v1/ifrs17/paa` — returns LRC/LIC at initial recognition
- [x] Pydantic request/response models with full input validation
- [x] Tests: 27 integration tests via FastAPI TestClient (httpx)

---

### Milestone 3.6 — Dashboard & Visualization ✅ COMPLETE
- [x] `dashboard/app.py` — Streamlit dashboard (optional dep; excluded from coverage)
- [x] Deal Pricing page: interactive slider inputs, IRR/NPV display, cash flow chart
- [x] Scenario Analysis page: bar chart of NPV under each stress scenario
- [x] Monte Carlo UQ page: histogram of PV profits with VaR/CVaR markers

---

### Milestone 3.7 — Quality & Coverage Enforcement ✅ COMPLETE
- [x] Coverage enforcement ≥ 90% (achieved: 94.14%); dashboard/app.py excluded
- [x] Ruff lint: zero violations across all Phase 3 source files
- [x] All 439 tests pass (116 new Phase 3 tests)
- [x] FastAPI + httpx added as optional `[api]` dependency group in pyproject.toml
- [x] Streamlit added as optional `[dashboard]` dependency

---

## Phase 4: Production Data Infrastructure & ML Assumptions ✅ COMPLETE

Phase 4 closes the gap between the working engine and a tool that can be used
on real deals. The three themes are: (1) data loading parity between mortality
and lapse, (2) cedant inforce data ingestion, and (3) ML-enhanced assumptions.
ML is elevated above its original priority ranking because it represents the
primary long-term differentiation of Polaris RE over AXIS/Prophet.

---

### Milestone 4.1 — Lapse Table ETL & File-Based Loading ✅ COMPLETE

- [x] Lapse CSV schema: 1D `policy_year,rate` format (ADR-033)
- [x] `utils/table_io.py` — `load_lapse_csv()`, `LapseTableArray` class
- [x] `assumptions/lapse.py` — `LapseAssumption.load(path)` factory classmethod
- [x] `scripts/convert_lapse_tables.py` — `--source llat` and `--source excel` modes
- [x] `scripts/validate_tables.py` — extended with lapse CSV validation
- [x] `docs/DECISIONS.md` — ADR-033: lapse CSV schema design
- [x] Tests: 24 new tests (round-trip, validation, lookup verification)

---

### Milestone 4.2 — Cedant Inforce Data Ingestion Pipeline ✅ COMPLETE

- [x] `utils/ingestion.py` — YAML-driven mapping engine with `IngestConfig`,
      `ingest_cedant_data()`, `validate_inforce_df()`, `DataQualityReport`
- [x] `scripts/ingest_inforce.py` — CLI tool for cedant data normalisation
- [x] `polaris ingest` — Typer CLI command with `--config`, `--output`, `--validate-only`
- [x] `api/main.py` — `POST /api/v1/ingest` endpoint
- [x] `InforceBlock.from_csv(path)` classmethod for normalised Polaris RE CSV
- [x] Data quality report with summary statistics and validation errors
- [x] Tests: 26 new tests (CSV round-trip, ingestion, validation)

---

### Milestone 4.3 — ML-Enhanced Mortality & Lapse Assumptions ✅ COMPLETE

- [x] `assumptions/ml_mortality.py` — `MLMortalityAssumption` with `get_qx_vector()`,
      `fit()`, `save()`/`load()` via joblib; same protocol as `MortalityTable`
- [x] `assumptions/ml_lapse.py` — `MLLapseAssumption` matching pattern
- [x] `utils/features.py` — `add_age_bands()`, `add_duration_bands()`,
      `log_face_amount()`, `build_feature_matrix()`
- [x] `scripts/train_ml_assumptions.py` — end-to-end training with synthetic data
- [x] `docs/DECISIONS.md` — ADR-034: ML assumption protocol; ADR-035: feature engineering
- [x] Tests: 36 new tests (prediction shape/dtype, persistence, feature engineering)

---

### Milestone 4.4 — YRT Rate Schedule Generator ✅ COMPLETE

- [x] `analytics/rate_schedule.py` — `YRTRateSchedule` class with `generate()`;
      solves for flat YRT rate per $1000 via `scipy.optimize.brentq` from
      the reinsurer's perspective (CEDED cash flows relabelled as GROSS)
- [x] `utils/excel_output.py` — formatted Excel workbook with openpyxl
- [x] `polaris rate-schedule` — Typer CLI command with `--target-irr`, `--ages` flags
- [x] `api/main.py` — `POST /api/v1/rate-schedule` endpoint
- [x] Tests: 8 tests (monotonicity, IRR target recovery, Excel output)

---

### Milestone 4.5 — Phase 4 Quality Gate ✅ COMPLETE

- [x] Coverage ≥ 90% maintained (90.62% with 533 tests)
- [x] Ruff: zero violations across all source and test files
- [x] `docs/QUICKSTART.md` updated with ML training and lapse table workflows
- [x] All new ADRs documented in `docs/DECISIONS.md` (ADR-033 through ADR-035)

---

## Phase 5: Capital, Portfolio & IFRS 17 Production

Phase 5 elevates the engine from single-deal pricing to portfolio-level risk
and capital management, and extends IFRS 17 from point-in-time measurement
to full period-to-period reporting. The primary new user persona is the CRO
and CFO, not just the pricing actuary.

---

### Milestone 5.1 — Regulatory Capital Module (LICAT) ✅ COMPLETE

Reinsurer deal evaluation is fundamentally return-on-capital (RoC), not just
IRR vs hurdle rate. Without a capital model, the profit tester gives an
incomplete picture. LICAT is the Canadian standard; the equivalent RBC (US)
and Solvency II (EU) modules are tracked under Milestone 5.7.

- [x] `analytics/capital.py` — `LICATCapital` class:
      - C-1 (asset default risk), C-2 (insurance risk), C-3 (interest rate
        risk) component calculations on `CashFlowResult`
      - `required_capital(cashflows, treaty)` → scalar capital amount
      - `return_on_capital(profit_result, capital)` → RoC metric
- [x] `ProfitTester` extended: `run_with_capital(capital_model)` returns
      `ProfitResultWithCapital` including RoC and capital-adjusted IRR
- [x] `polaris price --capital licat` — CLI flag to include capital metrics
- [x] `api/main.py` — `capital_model` optional field in `PriceRequest`;
      `return_on_capital` in `PriceResponse`
- [x] Tests: C-2 insurance risk factor verification vs OSFI published factors;
      RoC formula closed-form check; 20+ tests
- [x] `docs/DECISIONS.md` — ADR-047/048/049 (LICAT core, RoC, surfacing);
      ADR-065 (lapse + morbidity risk components); ADR-072 (C-1 / C-3 interim
      factors). (Supersedes the original ADR-036 placeholder.)

---

### Milestone 5.2 — Portfolio Aggregation ✅ COMPLETE

A reinsurer never prices a single treaty. Portfolio-level risk metrics require
aggregation across multiple independent projection runs.

- [x] `analytics/portfolio.py` — `Portfolio` class:
      - Holds a list of `(InforceBlock, AssumptionSet, BaseTreaty)` tuples
      - `run()` → `PortfolioResult` aggregating `CashFlowResult` across all
        deals into aggregate NCF, total ceded NAR, total ceded face
      - `add_deal(inforce, assumptions, treaty, deal_id)` builder pattern
- [x] `PortfolioResult`: total IRR, total PV profits, deal-level breakdown
      table, concentration by cedant / product type / treaty type
- [x] `polaris portfolio run --config deals.yaml` — YAML-driven multi-deal
      runner; `polaris portfolio report` — Rich summary table
- [x] `api/main.py` — `POST /api/v1/portfolio` endpoint accepting a list
      of deal configs
- [x] Tests: two-deal additivity (aggregate NCF = sum of individual NCFs);
      concentration metrics; 15+ tests
- [x] Extensions shipped beyond the original scope: aggregate `CashFlowResult`
      and RoC (ADR-059/060); calendar-aligned aggregation (ADR-061/062);
      portfolio scenarios (ADR-064) + CLI/API (ADR-066); weighted concentration
      bases + dimension-outer views (ADR-069/070/073); Streamlit portfolio page.
      *Core: ADR-057/058.*

---

### Milestone 5.3 — IFRS 17 Multi-Cohort & Period Reconciliation ✅ COMPLETE

IFRS 17 filers need period-to-period movement tables, not just point-in-time
BEL/CSM. The current model is one-shot; production requires annual cohort
tracking and opening/closing reconciliation. *Delivered as Epic 2 (PRs
#87–#91) under the epic-driven routine.*

- [x] `analytics/ifrs17.py` — `IFRS17CohortManager`:
      - Groups contracts into annual issue-year cohorts
      - Tracks locked-in discount rate per cohort for CSM accretion
      - Produces period-to-period movement table:
        Opening BEL → experience adjustments → unwinding → closing BEL
        Opening CSM → accretion → release → closing CSM
        Opening RA → release → closing RA
- [x] `IFRS17MovementTable` dataclass: structured output matching IASB
      presentation requirements
- [x] `api/main.py` — `POST /api/v1/ifrs17/movement` endpoint
- [x] Tests: opening + movements = closing for all components; CSM exhaustion
      at contract expiry; locked-in rate preserved across periods; 25+ tests
- [x] Surfaced on the REST API, deal-pricing Excel workbook, and `polaris price`
      CLI (ADR-095/096/097)
- [x] `docs/DECISIONS.md` — ADR-093 (cohorts + locked-in rate), ADR-094
      (analysis-of-change movement table). (Supersedes the ADR-037 placeholder.)
      Residual refinements (PAA/VFA cohorts, onerous sub-grouping, heterogeneous-
      term calendar alignment, dashboard view) harvested to
      `PRODUCT_DIRECTION_2026-06-18`.

---

### Milestone 5.4 — Asset / ALM Model 🔄 IN PROGRESS (Epic 4)

Modco profitability depends on investment returns on ceded reserves. Without
an asset model, Modco pricing is incomplete. Also required for any meaningful
duration-matching or embedded value calculation.

> **Started as the fourth epic, after the three Tier-A epics (5.7
> cross-jurisdiction capital shipped 2026-06-26).** Modco prices on a fixed
> credited rate today, so the engine is usable without this; it is a high-value
> but lower-priority big rock per
> `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` (Tier C / C0). Decomposed
> into 4 slices in `docs/PLAN_asset_alm.md`; running log in
> `docs/CONTINUATION_asset_alm.md`.

- [~] `core/asset.py` — `Bond` + `AssetPortfolio` classes:
      - [x] Slice 1 — bond cash flow model (coupon + principal vector) +
            pricing on the engine's effective-annual discounting; `AssetPortfolio`
            aggregation (ADR-108). Additive, goldens byte-identical.
      - [x] Slice 2 — `investment_income(reserve_vector, ...)` → monthly income;
            `book_yield()` (gross IRR), Macaulay/modified duration and convexity
            (ADR-109). Additive, goldens byte-identical.
      - [ ] Follow-up (post-epic) — integration with `stochastic.py` scenarios
            (Hull-White/CIR rates drive reinvestment yields) — harvested as a
            NICE-TO-HAVE; flat/book yield is what the core epic ships
- [x] `reinsurance/modco.py` — Slice 3 — `ModcoTreaty.apply()` accepts an
      optional `AssetPortfolio`; modco interest is driven by the asset book
      yield (Option A precedence) on the notional ceded reserve, with the flat
      `modco_interest_rate` as the fallback; no-portfolio path byte-identical
      (ADR-110). Stochastic credited rates remain a harvested follow-up.
- [~] `analytics/alm.py` — Slice 4 (re-decomposed into 4a core + 4b surfacing):
      - [x] Slice 4a — `analytics/alm.py` duration-gap core: `duration_measures`,
            `liability_cash_flows`, `duration_gap` → `DurationGapResult` (asset vs
            liability Macaulay/modified duration, duration gap, dollar-duration
            gap; both sides at one common flat valuation yield). 21 closed-form
            tests, ADR-111. Additive, goldens byte-identical.
      - [~] Slice 4b — CLI/API/dashboard/Excel surfacing + validation notebook
            (the only slice that may move goldens, and only when an asset
            portfolio is supplied). Re-decomposed into surface-sized sub-slices:
            - [x] Slice 4b-1 — CLI `deal.asset_portfolio` input + per-cohort
                  `alm_duration_gap` JSON output + Rich table. 12 tests, ADR-112.
                  Purely additive (default None → goldens byte-identical); a
                  cohort with non-positive liability PV is skipped, not fatal.
            - [x] Slice 4b-2a — reserve-backed Option-B liability stream
                  (`reserve_liability_cash_flows`, PV ties to the held reserve,
                  basis-agnostic) + CLI rewire. ADR-113; both golden cohorts now
                  carry a block (the 4b-1 WHOLE_LIFE skip resolved).
            - [x] Slice 4b-2b — reinsurer/cedant dual gap (`DualDurationGap`,
                  reinsurer-view ceded reserve as headline, cedant-view retained
                  reserve) + REST `/api/v1/price` surface. ADR-114, PR #113.
            - [~] Slice 4b-3 — dashboard + Excel presentation surfaces. Two
                  surfaces; split surface-sized:
                  - [x] Slice 4b-3a — "ALM Duration Gap" sheet on the deal-pricing
                        Excel workbook (`DealPricingExport.alm_duration_gap`;
                        reinsurer-view headline then cedant-view, mirroring the CLI
                        Rich block). ADR-115; additive, goldens byte-identical.
                  - [ ] Slice 4b-3b — dashboard asset-portfolio input +
                        duration-gap display (carries the PR-#111
                        `DealConfig.to_dict()` carry-forward).
            - [ ] Slice 4b-4 — ALM validation notebook
- [ ] Tests: bond cash flow closed-form; duration formula verification;
      integration with stochastic rate scenarios; 20+ tests

---

### Milestone 5.5 — Phase 5 Quality Gate

- [x] Coverage ≥ 90% maintained
- [x] All modules pass Ruff + mypy strict
- [ ] `docs/QUICKSTART.md` updated with portfolio runner and capital examples
- [x] All new ADRs documented (through ADR-098)

---

### Milestone 5.6 — Reserve-Basis Matching ✅ COMPLETE

Reinsurers must reproduce the cedant's stated reserves, not just a single
net-premium basis, for a consistent profit-test. *Delivered as Epic 1 (PRs
#81–#86) under the epic-driven routine; promoted from the IMPORTANT queue in
`PRODUCT_DIRECTION_2026-06-18`.*

- [x] `core/reserve_basis.py` — `ReserveBasis` enum (NET_PREMIUM / CRVM / VM20)
      + per-product dispatch guard (raises rather than returning a wrong reserve)
- [x] CRVM via Full Preliminary Term for `TermLife` and `WholeLife`
      (prospective-to-omega for WL) — closes the WL terminal-reserve artefact
      under CRVM/VM-20
- [x] VM-20 simplified (deterministic reserve) for `TermLife` and `WholeLife`
- [x] Basis selector surfaced on CLI / API / Excel / validation notebook
- [x] Tests: closed-form CRVM/VM-20 verification; dispatch-guard coverage
- [x] `docs/DECISIONS.md` — ADR-087 through ADR-092
- [ ] **Open (harvested to `PRODUCT_DIRECTION_2026-06-18`, IMPORTANT):** value
      CRVM on the distinct statutory table (2001 CSO) for *exact* cedant
      reproduction; close the artefact on the default NET_PREMIUM basis; extend
      bases to UL and DI (currently Term + WL only).

---

### Milestone 5.7 — Cross-Jurisdiction Capital (US RBC + Solvency II) ✅ COMPLETE

LICAT (5.1) is the Canadian standard only. A reinsurer cannot evaluate a US or
EU deal on a return-on-capital basis without the equivalent RBC (US) and
Solvency II SCR (EU) modules — a market-access gate. *Epic 3 under the
epic-driven routine; plan in `docs/PLAN_cross_jurisdiction_capital.md`.*

- [x] Slice 1 — US NAIC Life RBC core module + shared `CapitalModel` protocol
      (PR #92, ADR-098)
- [x] Slice 2 — RBC ↔ `ProfitTester` integration (PR #98, ADR-099). Both
      return-on-capital entry points — `ProfitTester.run_with_capital` and
      `Portfolio.run_with_capital` — widened from the concrete `LICATCapital` to
      the `CapitalModel` protocol (type-only; LICAT path byte-identical), so US
      `RBCCapital` now drives RoC for deals and books. The RBC ratio is reachable
      on `RBCResult`; a result-level ratio surface was deferred to Slice 4 (shipped
      in 4c-1, ADR-103).
- [x] Slice 3 — EU Solvency II SCR module (PR #99, ADR-100). `analytics/solvency2.py`
      (`SolvencyIICapital` → `SolvencyIIResult`) builds the standard-formula SCR
      through two correlation-matrix aggregations (`sqrt(rᵀ·Corr·r)` via einsum) —
      life sub-modules (mortality / lapse / catastrophe) → life SCR → BSCR with
      market + counterparty, plus a linear operational add-on — with a
      cost-of-capital risk margin. Matrices are Delegated Regulation (EU) 2015/35
      Annex IV constants. Satisfies `CapitalModel` / `CapitalSchedule`; additive
      (nothing wired into pricing), goldens byte-identical.
- [x] Slice 4a — surface the jurisdiction selector on the CLI + REST API
      (ADR-101). One shared `capital_model_for` registry (`SUPPORTED_CAPITAL_MODELS`,
      `CapitalModelId`) maps `licat` / `rbc` / `solvency2` to the calculator; the
      CLI `--capital {licat,rbc,solvency2}` flag and the API `capital_model` field
      both route through it. Default / `licat` paths byte-identical; only an
      explicit non-LICAT selection moves the numbers. (Slice 4 was re-decomposed
      into 4a machine surfaces + 4b presentation surfaces + 4c ratio/notebook.)
- [x] Slice 4b — surface the selector on the Streamlit dashboard ("Regulatory
      capital basis (RoC)" selectbox routed through `capital_model_for`) and the
      deal-pricing Excel workbook (jurisdiction-labelled capital-block header via a
      new `DealPricingExport.capital_model_id`); shared `CAPITAL_MODEL_LABELS` /
      `capital_model_label()` is the single labelling site so dashboard and Excel
      cannot drift (PR #101, ADR-102). Default / `licat` paths byte-identical.
- [x] Slice 4c-1 — the `ProfitResultWithCapital`-level RBC/solvency-ratio surface
      core (PR #102, ADR-103). A `CapitalSchedule.capital_ratio(available_capital)`
      protocol method (LICAT total ratio / RBC ratio / EU solvency ratio, with the
      denominator encapsulated per jurisdiction) surfaced on `ProfitResultWithCapital`
      via an optional `run_with_capital(..., available_capital=...)` keyword; both
      new fields default `None`, so goldens stay byte-identical. `rbc_ratio` retained
      as a thin alias of `capital_ratio`.
- [x] Slice 4c-2 — surface the ratio: thread the TAC / own-funds / target-multiple
      `available_capital` input through the CLI / API / dashboard and render
      `capital_ratio` on the Excel capital block and dashboard tiles, plus a
      three-standard validation notebook comparing LICAT / RBC / Solvency II on the
      golden block. Re-decomposed into 4c-2a (CLI + API numerator, PR #103,
      ADR-104), 4c-2b (Excel ratio row + dashboard input/tile, PR #105, ADR-106),
      and 4c-2c (`notebooks/03_capital_standards_comparison.ipynb`, PR #106,
      ADR-107) — the final slice, which closes the epic.
- [x] Tests: RBC factor verification vs NAIC tables; SCR correlation aggregation;
      RoC parity across jurisdictions (`test_rbc.py`, `test_solvency2.py`,
      `test_pricing_capital_jurisdiction.py`, `test_cli_streamlit_parity.py`)

---

## Phase 6: Operationalisation & Ecosystem

Phase 6 is about making Polaris RE usable by teams, not just individual
actuaries. Themes: deployment hardening, observability, and the ML feedback
loop that makes the system self-improving with experience data.

---

### Milestone 6.1 — Experience Monitoring Automation

Close the loop between the experience study module (Phase 3) and the assumption
pipeline (Phase 4). Study results should feed back into ML model retraining and
blended table updates without manual intervention.

- [ ] `analytics/experience_study.py` — `ExperienceStudy.export_to_lapse_csv()`
      and `export_to_mortality_csv()`: write credibility-blended rates in the
      Polaris RE CSV schema so they can be loaded via `LapseAssumption.load()`
      and `MortalityTable.load()`
- [ ] `scripts/update_assumptions.py` — automates the full loop:
      load claims data → run experience study → export blended CSVs →
      retrain ML models → log changes to `docs/DECISIONS.md`
- [ ] `polaris experience run` — CLI command with `--data`, `--output-dir`,
      `--retrain-ml` flags
- [ ] Assumption versioning: each exported CSV is tagged with study date and
      credibility weight; version history tracked in `data/assumption_versions/`
- [ ] Tests: round-trip study → export → load → projection; version tag
      preservation; 20+ tests

---

### Milestone 6.2 — Production Hardening & Observability

- [ ] `api/main.py` — structured JSON request/response logging with
      correlation IDs; request duration metrics
- [ ] OpenTelemetry integration (optional dep): trace spans for projection,
      treaty application, and profit test steps
- [ ] `api/auth.py` — optional API key authentication middleware
- [ ] Rate limiting via `slowapi` (optional dep)
- [ ] Kubernetes deployment manifests: `deploy/k8s/deployment.yaml`,
      `deploy/k8s/service.yaml`, `deploy/k8s/configmap.yaml`
- [ ] Helm chart: `deploy/helm/polaris-re/` for parameterised K8s deployment
- [ ] `docker-compose.yml` — add `prometheus` and `grafana` services for
      local metrics dashboard
- [ ] `docs/DECISIONS.md` — ADR-038: observability approach

---

### Milestone 6.3 — Phase 6 Quality Gate

- [ ] All CI jobs green
- [ ] Load test: 100 concurrent `/api/v1/price` requests complete in < 2s
      (pytest-benchmark or locust)
- [ ] `docs/QUICKSTART.md` updated with K8s deployment and observability guide
- [ ] All ADRs current

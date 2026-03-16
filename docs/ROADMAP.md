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

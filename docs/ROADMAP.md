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

## Phase 3: IFRS 17, Stochastic Rates & API Layer

---

### Milestone 3.1 — IFRS 17 Measurement Models
- [ ] `analytics/ifrs17.py` — Building Block Approach (BBA) measurement model
  - [ ] Best Estimate Liability (BEL) — PV of fulfilment cash flows
  - [ ] Risk Adjustment (RA) — quantile-based or cost-of-capital method
  - [ ] Contractual Service Margin (CSM) — unearned profit, released over coverage period
  - [ ] CSM amortisation schedule — coverage units based on expected claims
- [ ] `analytics/ifrs17.py` — Premium Allocation Approach (PAA) for short-duration contracts
  - [ ] Liability for Remaining Coverage (LRC) and Liability for Incurred Claims (LIC)
- [ ] `analytics/ifrs17.py` — Variable Fee Approach (VFA) for direct-participating contracts (UL)
- [ ] Tests: BBA fulfilment cash flows match manual calculation; CSM release pattern verification

---

### Milestone 3.2 — Stochastic Interest Rate Scenarios
- [ ] `analytics/stochastic.py` — Hull-White one-factor model for short-rate simulation
- [ ] `analytics/stochastic.py` — Cox-Ingersoll-Ross (CIR) model as alternative
- [ ] Interest rate scenario generator: N paths of monthly discount curves from t=0 to T
- [ ] Integration with `ProjectionConfig` — replace flat `discount_rate` with a yield curve array
- [ ] Integration with UL `credited_rate` — stochastic credited rates linked to scenario paths
- [ ] Tests: mean-reversion properties, no-arbitrage verification, scenario shape correctness

---

### Milestone 3.3 — Experience Studies
- [ ] `analytics/experience_study.py` — A/E ratio computation from historical data
- [ ] Mortality A/E by age band, duration, sex, smoker status
- [ ] Lapse A/E by duration
- [ ] Credibility weighting (limited fluctuation or Buhlmann)
- [ ] Output: calibrated assumption adjustments for use in `AssumptionSet`
- [ ] Tests: known dataset produces expected A/E ratios

---

### Milestone 3.4 — CLI Interface (Typer)
- [ ] `polaris price` — run a deal pricing pipeline from YAML/JSON config
- [ ] `polaris scenario` — run scenario analysis with tabular output
- [ ] `polaris uq` — run Monte Carlo UQ with summary statistics
- [ ] `polaris validate` — validate inforce CSV, mortality tables, assumption sets
- [ ] Rich-formatted terminal output with progress bars for long runs
- [ ] Tests: CLI invocation via `subprocess` or Typer's `CliRunner`

---

### Milestone 3.5 — REST API Layer (FastAPI)
- [ ] `api/main.py` — FastAPI application with health check
- [ ] `POST /api/v1/price` — submit inforce + assumptions + treaty → returns ProfitTestResult
- [ ] `POST /api/v1/scenario` — run scenario analysis → returns ScenarioResult
- [ ] `POST /api/v1/uq` — run Monte Carlo UQ → returns UQResult summary
- [ ] JSON serialization of all Pydantic models (CashFlowResult, ProfitTestResult, UQResult)
- [ ] Input validation via Pydantic request models
- [ ] Tests: FastAPI TestClient integration tests

---

### Milestone 3.6 — Dashboard & Visualization
- [ ] Streamlit or Panel dashboard for interactive deal comparison
- [ ] Side-by-side treaty comparison (YRT vs coinsurance vs modco)
- [ ] Interactive scenario sensitivity charts
- [ ] UQ distribution plots (histogram of PV profits, VaR/CVaR markers)
- [ ] Cash flow waterfall charts by year

---

### Milestone 3.7 — Quality & Coverage Enforcement
- [ ] Codecov integration with badge in README
- [ ] Coverage enforcement ≥ 90% (up from 85%)
- [ ] Full mypy strict compliance (resolve remaining pre-existing type ignores)
- [ ] CI pipeline green on all jobs (lint, format, test-3.12, test-3.13, docker)
- [ ] Documentation site generation (mkdocs or sphinx)

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

### Milestone 1.2 — Assumptions & Utilities 🔄 IN PROGRESS
- [ ] `utils/date_utils.py` — `months_between`, `age_nearest_birthday`, `age_last_birthday`, `projection_date_index`
- [ ] `utils/interpolation.py` — `constant_force_interpolate_rates`, `linear_interpolate_rates`
- [ ] `utils/table_io.py` — `load_mortality_csv`, `MortalityTableArray.get_rate_vector`
- [ ] `assumptions/mortality.py` — `MortalityTable.load`, `get_qx_vector`
- [ ] `assumptions/lapse.py` — `LapseAssumption.from_duration_table`, `get_lapse_vector`
- [ ] `assumptions/improvement.py` — `MortalityImprovement.apply_improvement` (Scale AA + NONE)
- [ ] `assumptions/assumption_set.py` — `AssumptionSet` (depends on above; model is complete, summary property needs lapse loaded)
- [ ] `tests/fixtures/` — synthetic CSV mortality table fixtures for testing (no licensing required)
- [ ] `tests/test_assumptions/test_mortality.py` — closed-form rate lookup verification
- [ ] All rate lookup tests passing including `constant_force` monthly conversion

---

### Milestone 1.3 — Term Life Product Engine
- [ ] `products/term_life.py` — `TermLife._build_rate_arrays()` — q and w arrays shape (N, T)
- [ ] `products/term_life.py` — `TermLife._compute_inforce_factors()` — lx forward recursion
- [ ] `products/term_life.py` — `TermLife.compute_reserves()` — backward net premium reserve recursion
- [ ] `products/term_life.py` — `TermLife.project()` — assemble full CashFlowResult (GROSS)
- [ ] Tests: single policy closed-form verification (premiums, claims, reserves vs hand calculation)
- [ ] Tests: reserve terminal condition V_T = 0; non-negative throughout; accounting identity

---

### Milestone 1.4 — YRT and Coinsurance Treaties
- [ ] `reinsurance/yrt.py` — `YRTTreaty.apply()` — NAR, ceded premium, ceded claims
- [ ] `reinsurance/coinsurance.py` — `CoinsuranceTreaty.apply()` — proportional all lines + reserve transfer
- [ ] Tests: verify net + ceded == gross for all cash flow lines (`verify_additivity`)
- [ ] Tests: YRT reserves not transferred; coinsurance reserves split proportionally

---

### Milestone 1.5 — Profit Testing & Scenario Analysis
- [ ] `analytics/profit_test.py` — `ProfitTester.run()` — PV profits, IRR (scipy brentq), break-even, margin
- [ ] `analytics/scenario.py` — `ScenarioRunner.run()` — standard stress scenarios
- [ ] Tests: IRR = hurdle rate when PV profits = 0 by construction; profit margin bounds

---

### Milestone 1.6 — Integration, Docs & Validation Notebook
- [ ] Full integration test: InforceBlock → AssumptionSet → TermLife → YRTTreaty → ProfitTester
- [ ] `notebooks/01_term_life_yrt_pricing.ipynb` — end-to-end deal pricing walkthrough
- [ ] `README.md` — update feature status table when Phase 1 complete
- [ ] `make coverage` — ≥ 85% coverage on all Phase 1 modules (threshold set in pyproject.toml)
- [ ] CI pipeline green on all 4 jobs (lint, test-3.12, test-3.13, docker)

---

## Phase 2: Whole Life, Modco & Uncertainty Quantification (Target: +8 weeks)

- [ ] `products/whole_life.py` — par and non-par whole life with reserve recursion
- [ ] `products/universal_life.py` — COI charges, account value roll-forward
- [ ] `reinsurance/modco.py` — modco adjustment, investment income on ceded reserves
- [ ] `reinsurance/stop_loss.py` — aggregate stop loss (attachment/exhaustion points)
- [ ] `analytics/uq.py` — Monte Carlo UQ (np.random.default_rng, N scenarios)
- [ ] `assumptions/morbidity.py` — CI and disability incidence/termination tables
- [ ] `products/disability.py` — DI / CI product cash flows
- [ ] `assumptions/improvement.py` — MP-2020 and CPM-B improvement scales

---

## Phase 3: IFRS 17, Stochastic Rates & API Layer (Target: +12 weeks)

- [ ] IFRS 17 measurement models (BBA, PAA, VFA)
- [ ] Contractual Service Margin (CSM) amortisation
- [ ] Stochastic interest rate scenarios (Hull-White, CIR)
- [ ] FastAPI REST layer for programmatic pricing
- [ ] Streamlit or Panel dashboard for deal comparison
- [ ] CLI interface via Typer (`polaris price`, `polaris scenario`)
- [ ] Codecov badge and full coverage enforcement (≥ 90%)

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

## Phase 4: Production Data Infrastructure & ML Assumptions

Phase 4 closes the gap between the working engine and a tool that can be used
on real deals. The three themes are: (1) data loading parity between mortality
and lapse, (2) cedant inforce data ingestion, and (3) ML-enhanced assumptions.
ML is elevated above its original priority ranking because it represents the
primary long-term differentiation of Polaris RE over AXIS/Prophet.

---

### Milestone 4.1 — Lapse Table ETL & File-Based Loading

Parity with the mortality table infrastructure. Every real deal has cedant-
provided lapse experience that currently must be hardcoded. This milestone
lets lapse assumptions be loaded from CSV files the same way mortality tables
are, including a validated CSV schema and a conversion script for the public
SOA Term Lapse and Termination Study (LLAT 2014).

- [ ] Define lapse CSV schema: `policy_year, sex, smoker_status, lapse_rate`
      (ultimate-only) or `policy_year, sex, smoker_status, select_rate_1 ...
      select_rate_N, ultimate_rate` (select-and-ultimate)
- [ ] `utils/table_io.py` — `load_lapse_csv(path, select_period)` function
      mirroring `load_mortality_csv`; validate rates in [0, 1], contiguous years
- [ ] `assumptions/lapse.py` — `LapseAssumption.load(path)` factory classmethod
- [ ] `scripts/convert_lapse_tables.py` — convert SOA LLAT 2014 Excel workbook
      to Polaris RE schema; `--source llat` and `--source excel` modes matching
      the mortality converter pattern
- [ ] `scripts/validate_tables.py` — extend to cover lapse CSV files
- [ ] `data/lapse_tables/` — sample benchmark lapse tables (SOA LLAT 2014 NS/S)
- [ ] `docs/DECISIONS.md` — ADR-033: lapse CSV schema design choices
- [ ] Tests: closed-form round-trip load/lookup verification; validation error
      cases; 15+ tests in `tests/test_assumptions/test_lapse.py`

---

### Milestone 4.2 — Cedant Inforce Data Ingestion Pipeline

Reinsurers receive inforce data in inconsistent layouts: different column names,
date formats, code mappings, and missing fields. Without a normalisation layer
every deal requires manual CSV transformation. This milestone delivers a
configurable mapping pipeline so any cedant layout can be ingested without code
changes.

- [ ] `scripts/ingest_inforce.py` — CLI tool: reads raw cedant CSV/Excel,
      applies a YAML mapping config, validates and writes a normalised Polaris
      RE inforce CSV (matching `generate_synthetic_block.py` output schema)
- [ ] YAML mapping schema: maps arbitrary source column names to Polaris RE
      field names; defines code translations (e.g. `M → MALE`), date formats,
      and default values for missing optional fields
- [ ] `polaris ingest` — new Typer CLI command wrapping `ingest_inforce.py`
- [ ] `api/main.py` — `POST /api/v1/ingest` endpoint: accepts raw JSON
      inforce block + column mapping, returns validated Polaris RE inforce
- [ ] `InforceBlock.from_csv(path)` classmethod that reads the normalised schema
- [ ] Data quality report: missing rates, out-of-range ages, duplicate IDs,
      summary statistics (total face, mean age, sex/smoker split)
- [ ] Tests: round-trip ingestion of synthetic block with column renaming;
      validation error cases; 20+ tests

---

### Milestone 4.3 — ML-Enhanced Mortality & Lapse Assumptions

The ML dependencies (scikit-learn, XGBoost) are already declared but unused.
This milestone implements trained model wrappers that plug directly into the
existing `AssumptionSet` contract, making ML predictions a first-class assumption
source alongside table-based lookups. This is the primary long-term
differentiation of Polaris RE over AXIS/Prophet.

- [ ] `assumptions/ml_mortality.py` — `MLMortalityAssumption` class:
      - Wraps a fitted scikit-learn or XGBoost pipeline
      - `get_qx_vector(ages, sex, smoker, durations, features)` → shape (N,)
      - `from_trained_model(model, feature_names)` factory
      - `fit(X, y)` convenience method for training from a Polars DataFrame
      - `save(path)` / `load(path)` via joblib for model persistence
      - Satisfies the same protocol as `MortalityTable` so `AssumptionSet`
        requires no changes
- [ ] `assumptions/ml_lapse.py` — `MLLapseAssumption` matching the above
      pattern for lapse rate prediction from policy features
- [ ] `scripts/train_ml_assumptions.py` — end-to-end training script:
      loads normalised inforce CSV + actual claims data, engineers features
      (age^2, log_face, duration bands, interaction terms), trains
      XGBoost model with cross-validation, reports feature importance and
      A/E vs table-based assumptions
- [ ] Feature engineering: `utils/features.py` — standard transformations
      (age bands, duration bands, face amount log-transform, BMI if available)
- [ ] `notebooks/02_ml_mortality_assumptions.ipynb` — walkthrough: load
      synthetic data, train model, compare ML q_x vs VBT 2015, run pricing
      with ML assumptions vs table assumptions, visualise IRR impact
- [ ] `api/main.py` — `POST /api/v1/train` endpoint: accepts labelled
      inforce + claims data, returns model artefact reference
- [ ] Tests: prediction shape/dtype contract; A/E metric within expected bounds
      on synthetic data; model persistence round-trip; 25+ tests
- [ ] `docs/DECISIONS.md` — ADR-034: ML assumption protocol design; ADR-035:
      feature engineering conventions

---

### Milestone 4.4 — YRT Rate Schedule Generator

New business pricing output is a rate schedule table (per-$1000 YRT rates by
age/sex/smoker/duration), not just an IRR number. This is the actual deliverable
reinsurers send cedants. Without it, users still complete final output in Excel.

- [ ] `analytics/rate_schedule.py` — `YRTRateSchedule` class:
      - Iterates over a grid of (issue_age × sex × smoker × duration) combinations
      - Calls the projection engine for each combination
      - Solves for the flat YRT rate per $1000 that achieves a target IRR
        (binary search via `scipy.optimize.brentq`)
      - Returns a Polars DataFrame and exports to CSV or Excel
- [ ] `polaris rate-schedule` — CLI command with `--target-irr`, `--ages`,
      `--sex`, `--smoker` flags; Rich progress bar across the grid
- [ ] `api/main.py` — `POST /api/v1/rate-schedule` endpoint
- [ ] Excel output formatter: `utils/excel_output.py` producing a formatted
      workbook matching the layout reinsurers use in practice
- [ ] Tests: monotonicity of rates with age; IRR target recovery within
      tolerance; 15+ tests

---

### Milestone 4.5 — Phase 4 Quality Gate

- [ ] Coverage ≥ 90% maintained across all Phase 4 modules
- [ ] All new modules pass Ruff + mypy strict
- [ ] `uv.lock` updated and CI green on Python 3.12 and 3.13
- [ ] `docs/QUICKSTART.md` updated with ML assumption training workflow
- [ ] All new ADRs documented in `docs/DECISIONS.md`

---

## Phase 5: Capital, Portfolio & IFRS 17 Production

Phase 5 elevates the engine from single-deal pricing to portfolio-level risk
and capital management, and extends IFRS 17 from point-in-time measurement
to full period-to-period reporting. The primary new user persona is the CRO
and CFO, not just the pricing actuary.

---

### Milestone 5.1 — Regulatory Capital Module (LICAT)

Reinsurer deal evaluation is fundamentally return-on-capital (RoC), not just
IRR vs hurdle rate. Without a capital model, the profit tester gives an
incomplete picture. LICAT is the Canadian standard; equivalent modules for
RBC (US) and Solvency II (EU) follow the same pattern.

- [ ] `analytics/capital.py` — `LICATCapital` class:
      - C-1 (asset default risk), C-2 (insurance risk), C-3 (interest rate
        risk) component calculations on `CashFlowResult`
      - `required_capital(cashflows, treaty)` → scalar capital amount
      - `return_on_capital(profit_result, capital)` → RoC metric
- [ ] `ProfitTester` extended: `run_with_capital(capital_model)` returns
      `ProfitResultWithCapital` including RoC and capital-adjusted IRR
- [ ] `polaris price --capital licat` — CLI flag to include capital metrics
- [ ] `api/main.py` — `capital_model` optional field in `PriceRequest`;
      `return_on_capital` in `PriceResponse`
- [ ] Tests: C-2 insurance risk factor verification vs OSFI published factors;
      RoC formula closed-form check; 20+ tests
- [ ] `docs/DECISIONS.md` — ADR-036: LICAT scope and simplifying assumptions

---

### Milestone 5.2 — Portfolio Aggregation

A reinsurer never prices a single treaty. Portfolio-level risk metrics require
aggregation across multiple independent projection runs.

- [ ] `analytics/portfolio.py` — `Portfolio` class:
      - Holds a list of `(InforceBlock, AssumptionSet, BaseTreaty)` tuples
      - `run()` → `PortfolioResult` aggregating `CashFlowResult` across all
        deals into aggregate NCF, total ceded NAR, total ceded face
      - `add_deal(inforce, assumptions, treaty, deal_id)` builder pattern
- [ ] `PortfolioResult`: total IRR, total PV profits, deal-level breakdown
      table, concentration by cedant / product type / treaty type
- [ ] `polaris portfolio run --config deals.yaml` — YAML-driven multi-deal
      runner; `polaris portfolio report` — Rich summary table
- [ ] `api/main.py` — `POST /api/v1/portfolio` endpoint accepting a list
      of deal configs
- [ ] Tests: two-deal additivity (aggregate NCF = sum of individual NCFs);
      concentration metrics; 15+ tests

---

### Milestone 5.3 — IFRS 17 Multi-Cohort & Period Reconciliation

IFRS 17 filers need period-to-period movement tables, not just point-in-time
BEL/CSM. The current model is one-shot; production requires annual cohort
tracking and opening/closing reconciliation.

- [ ] `analytics/ifrs17.py` — `IFRS17CohortManager`:
      - Groups contracts into annual issue-year cohorts
      - Tracks locked-in discount rate per cohort for CSM accretion
      - Produces period-to-period movement table:
        Opening BEL → experience adjustments → unwinding → closing BEL
        Opening CSM → accretion → release → closing CSM
        Opening RA → release → closing RA
- [ ] `IFRS17MovementTable` dataclass: structured output matching IASB
      presentation requirements
- [ ] `api/main.py` — `POST /api/v1/ifrs17/movement` endpoint
- [ ] Tests: opening + movements = closing for all components; CSM exhaustion
      at contract expiry; locked-in rate preserved across periods; 25+ tests
- [ ] `docs/DECISIONS.md` — ADR-037: cohort grouping criteria

---

### Milestone 5.4 — Asset / ALM Model

Modco profitability depends on investment returns on ceded reserves. Without
an asset model, Modco pricing is incomplete. Also required for any meaningful
duration-matching or embedded value calculation.

- [ ] `core/asset.py` — `AssetPortfolio` class:
      - Bond cash flow model: coupon + principal on a vector of fixed-income
        instruments
      - `investment_income(reserve_vector, credited_rate)` → monthly income
      - Duration and convexity calculation
      - Integration with `stochastic.py` scenarios (Hull-White/CIR rates drive
        reinvestment yields)
- [ ] `reinsurance/modco.py` — updated `ModcoTreaty.apply()` to accept an
      optional `AssetPortfolio`; use stochastic credited rates when provided
- [ ] `analytics/alm.py` — duration gap analysis on net reinsurer position
- [ ] Tests: bond cash flow closed-form; duration formula verification;
      integration with stochastic rate scenarios; 20+ tests

---

### Milestone 5.5 — Phase 5 Quality Gate

- [ ] Coverage ≥ 90% maintained
- [ ] All modules pass Ruff + mypy strict
- [ ] `docs/QUICKSTART.md` updated with portfolio runner and capital examples
- [ ] All new ADRs documented

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

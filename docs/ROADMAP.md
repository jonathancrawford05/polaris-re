# Polaris RE — Development Roadmap

---

## Phase 1: MVP — Term Life Reinsurance Pricing (Target: 8 weeks)

The goal of Phase 1 is a fully functional, tested, and documented engine capable of pricing a YRT or coinsurance reinsurance treaty on a block of term life policies. This is the most common deal type at a life reinsurer and provides the foundation for all subsequent phases.

### Milestone 1.1 — Core Data Models (Week 1)
- [ ] `core/base.py` — `PolarisBaseModel` with global Pydantic v2 config
- [ ] `core/exceptions.py` — `PolarisValidationError`, `PolarisComputationError`
- [ ] `core/policy.py` — `Policy`, `ProductType` enum, `SmokerStatus` enum, `Sex` enum
- [ ] `core/inforce.py` — `InforceBlock` with vectorized attribute access (`.attained_age_vec`, `.face_amount_vec`, etc.)
- [ ] `core/projection.py` — `ProjectionConfig` (horizon, time step, discount rate, valuation date)
- [ ] `core/cashflow.py` — `CashFlowResult` dataclass with all required fields
- [ ] Tests: `tests/test_core/` — full coverage on all core models

### Milestone 1.2 — Mortality Assumptions (Week 2)
- [ ] `assumptions/mortality.py` — `MortalityTable` class
  - Load CIA 2014 from CSV
  - Load SOA VBT 2015 (select and ultimate) from CSV
  - `get_qx_vector(ages, sex, smoker, durations)` — returns `np.ndarray[float64]` shape `(N,)`
  - Sex-distinct rates, smoker/non-smoker distinct rates
  - Age interpolation (nearest birthday and last birthday)
- [ ] `assumptions/improvement.py` — `MortalityImprovement`
  - Scale AA factors
  - MP-2020 projection scale
  - `apply_improvement(qx_base, calendar_year, projection_years)` method
- [ ] `assumptions/lapse.py` — `LapseAssumption`
  - Duration-based select and ultimate structure
  - `get_lapse_vector(durations)` — returns `np.ndarray[float64]` shape `(N,)`
- [ ] `assumptions/assumption_set.py` — `AssumptionSet` (bundles all above with version metadata)
- [ ] Tests: closed-form verification — single policy, known q_x, verify rates match table values exactly

### Milestone 1.3 — Term Life Product Engine (Weeks 3–4)
- [ ] `products/base_product.py` — `BaseProduct` abstract class
- [ ] `products/term_life.py` — `TermLife`
  - Monthly projection loop (vectorized over policies)
  - `lx` in-force factor array `(N, T)` with mortality and lapse decrements
  - Gross premium calculation
  - Net premium reserve recursion
  - `CashFlowResult` output on gross basis
- [ ] Tests:
  - Single policy, 10-year term — verify premiums, claims, reserves match hand calculation
  - Verify `sum(lx * q) == total deaths` is internally consistent
  - Verify reserves are non-negative and reach 0 at policy expiry

### Milestone 1.4 — YRT and Coinsurance Treaties (Week 5)
- [ ] `reinsurance/base_treaty.py` — `BaseTreaty` abstract class
- [ ] `reinsurance/yrt.py` — `YRTTreaty`
  - NAR calculation from gross reserve
  - Ceded premium = NAR × YRT rate / 1000
  - Ceded claims = gross claims × cession %
  - Returns `CashFlowResult` on ceded and net bases
- [ ] `reinsurance/coinsurance.py` — `CoinsuranceTreaty`
  - Proportional share of all cash flow lines
  - Ceded reserve transfer
  - Returns net `CashFlowResult`
- [ ] Tests: verify YRT net + ceded = gross for all cash flow lines

### Milestone 1.5 — Profit Testing & Analytics (Week 6)
- [ ] `analytics/profit_test.py` — `ProfitTester`
  - PV of profits at hurdle rate
  - IRR computation (`numpy_financial.irr`)
  - Break-even duration
  - Profit margin
- [ ] `analytics/scenario.py` — `ScenarioRunner`
  - Runs projection under N assumption scenarios
  - Returns `ScenarioResult` with profit metric distribution
- [ ] Tests: verify IRR = hurdle rate when PV profits = 0 by construction

### Milestone 1.6 — Integration, Docs & Validation Notebook (Weeks 7–8)
- [ ] Full integration test: load inforce block → apply assumptions → project term life → apply YRT treaty → profit test
- [ ] `notebooks/01_term_life_yrt_pricing.ipynb` — end-to-end deal pricing walkthrough
- [ ] `README.md` complete with quickstart
- [ ] `ARCHITECTURE.md` complete
- [ ] `docs/ACTUARIAL_GLOSSARY.md` complete
- [ ] `make coverage` shows ≥ 90% coverage on all Phase 1 modules

---

## Phase 2: Whole Life, Modco & Uncertainty Quantification (Target: +8 weeks)

- [ ] `products/whole_life.py` — par and non-par whole life with dividend projections
- [ ] `products/universal_life.py` — COI charges, account value roll-forward, no-lapse guarantee
- [ ] `reinsurance/modco.py` — modco adjustment, investment income on ceded reserves
- [ ] `reinsurance/stop_loss.py` — aggregate stop loss with attachment/exhaustion points
- [ ] `analytics/uq.py` — Monte Carlo uncertainty quantification
- [ ] `assumptions/morbidity.py` — CI and disability incidence tables
- [ ] `products/disability.py` — DI / CI product cash flows

---

## Phase 3: IFRS 17, Stochastic Rates & API Layer (Target: +12 weeks)

- [ ] IFRS 17 measurement models (BBA, PAA, VFA)
- [ ] Contractual Service Margin (CSM) amortization
- [ ] Stochastic interest rate scenarios (Hull-White, CIR)
- [ ] FastAPI REST layer for programmatic pricing
- [ ] Streamlit or Panel dashboard for deal comparison
- [ ] CLI interface via Typer (`polaris price`, `polaris scenario`)

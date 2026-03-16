# Architecture — Polaris RE

> Read this document before working on any core module. It contains the full system design rationale.

---

## 1. Design Philosophy

Polaris RE is designed around three constraints common in actuarial work:

1. **Auditability** — every output number must be traceable back to an input assumption and a formula. No black boxes.
2. **Performance** — inforce blocks in production can contain 100k–500k policies. Looping over policies in Python is not acceptable. All projections must be vectorized.
3. **Composability** — a reinsurer needs to price the same inforce block under 5 treaty structures and 20 assumption scenarios in a single run. Components must be independently swappable without touching projection logic.

---

## 2. Core Data Model

### Policy
The atomic unit. Represents a single insured life under a single coverage.

```python
class Policy(PolarisBaseModel):
    policy_id: str
    issue_age: int                    # age at issue (age nearest birthday)
    attained_age: int                 # current age (drives mortality table lookup)
    sex: Literal["M", "F"]
    smoker_status: Literal["S", "NS", "U"]   # U = unknown/aggregate
    underwriting_class: str           # e.g. "PREF_PLUS", "PREF", "STANDARD"
    face_amount: float                # in dollars
    annual_premium: float             # gross premium
    product_type: ProductType         # enum: TERM, WHOLE_LIFE, UL, DISABILITY, ANNUITY
    policy_term: int | None           # in years; None for permanent products
    duration_inforce: int             # months in force at projection start
    reinsurance_cession_pct: float    # fraction ceded (0.0 to 1.0)
    issue_date: date
    valuation_date: date
```

### InforceBlock
A validated collection of policies with vectorized attribute extraction. This is what gets passed to the projection engine.

The vectorization pattern:
```python
block = InforceBlock(policies=policy_list)
ages = block.attained_age_vec   # np.ndarray[int32], shape (N,)
face = block.face_amount_vec    # np.ndarray[float64], shape (N,)
```

This design avoids iterating over the policy list in the projection engine itself.

---

## 3. Assumption Architecture

Assumptions are fully decoupled from product logic. The `AssumptionSet` is the single object passed to projections — it carries all assumption tables and is immutable once constructed.

```
AssumptionSet
├── MortalityTable         (base q_x rates by age, sex, smoker, duration)
│   └── MortalityImprovement  (Scale AA, MP-2020, CPM-B)
├── LapseAssumption        (duration-based select and ultimate lapse rates)
├── MorbidityTable         (CI incidence, DI incidence + termination)
├── ExpenseAssumption      (per-policy and % of premium expense basis)
└── metadata: dict         (version, source, effective date — for audit trail)
```

**Critically:** `MortalityTable.get_qx_vector(ages, sex, durations)` returns a numpy array of shape `(N,)` — it operates on vectors of ages, not scalars. This is the performance contract.

### Supported Tables

**Mortality:**
- CIA 2014 Individual Life (Canadian industry standard)
- SOA VBT 2015 (US individual life, select and ultimate)
- 2001 CSO (US regulatory minimum — used for CRVM/CARVM reserves)

**Improvement Scales:**
- Scale AA (SOA, age-only — embedded constant array)
- MP-2020 (SOA, 2D age×calendar year 2015-2031 — embedded 121×17 array)
- CPM-B (CIA, age-only Canadian scale — embedded constant array)

**Morbidity:**
- CI incidence tables (by age, sex) — synthetic constructors for testing
- DI incidence + termination tables (by age, sex) — synthetic constructors for testing

Mortality tables are loaded from CSV files in `$POLARIS_DATA_DIR/mortality_tables/`. File format is standardized: columns = `[age, sex, smoker, select_year_1, ..., select_year_N, ultimate]`.

---

## 4. Projection Engine

The projection engine operates on an `InforceBlock` for a single product type. It produces monthly time-step cash flows over the projection horizon.

### Vectorization Strategy

For a block of N policies projected over T months:
- All intermediate arrays have shape `(N, T)`
- Assumptions are broadcast across the time dimension
- Policy decrements (deaths, lapses) are applied cumulatively to an "in-force factor" array `lx` of shape `(N, T)`

```
lx[:, 0] = 1.0                              # all policies active at t=0
lx[:, t] = lx[:, t-1] * (1 - q[:, t-1]) * (1 - w[:, t-1])
           # q = mortality rate, w = lapse rate (both shape N×T)

claims[:, t]   = lx[:, t-1] * q[:, t-1] * face_vec   # death claims
premiums[:, t] = lx[:, t] * premium_vec               # premiums in force
```

This approach scales to 500k policies with no changes — numpy broadcasts across N trivially.

### Reserve Calculation

Reserves are required for coinsurance, modco, and profit testing. The reserve method depends on product type:

**Term Life:** Net premium reserves with terminal condition V_T = 0 at policy expiry.

**Whole Life:** Net premium reserves with prospective terminal estimate V_T = face * q_T * v. Backward recursion proceeds from this approximation. (Phase 3 will extend to true prospective reserves.)

**Universal Life:** Reserve = account value (simplified). The AV roll-forward itself is the reserve.

**Disability / CI:** Reserves set to zero (simplified for Phase 2; DI GAAP reserves are complex).

All products use the standard reserve recursion:
```
(V_t + P_t) * (1 + i)^(1/12) = q_t * b_t + (1 - q_t) * V_{t+1}
```

Where `i` is the valuation interest rate and `b_t` is the benefit paid at death.

### Product-Specific Projection Details

**Whole Life (`WholeLife`):**
- Supports `NON_PAR` and `PAR` variants (dividends not yet modelled)
- Optional limited-pay: `premium_payment_years` restricts premium collection period
- `_compute_annual_net_premiums()` returns annual premium; divided by 12 for monthly use
- Rate arrays have no remaining-term mask (active until max age 120 or death/lapse)
- Terminal reserve at projection end: one-period prospective estimate V_T = face * q_T * v

**Universal Life (`UniversalLife`):**
- Account value roll-forward loop: `AV_{t+1} = (AV_t + prem - expense) * (1 + i/12) - COI`
- COI = NAR * q / (1 + i/12) where NAR = max(face - AV, 0)
- Forced lapse when AV reaches zero: `w_total = min(w_voluntary + forced_lapse, 1.0)`
- Surrender value = max(AV - surrender_charge, 0)
- Requires `account_value` and `credited_rate` fields on Policy

**Disability / Critical Illness (`DisabilityProduct`):**
- CI: single-decrement model — lx decremented by mortality + lapse + incidence; claims = lx * incidence * face
- DI: multi-state model with `lx_active` and `lx_disabled` arrays:
  - `new_disabled = lx_active * incidence_rate`
  - `lx_disabled_{t+1} = lx_disabled_t * (1 - termination_rate) + new_disabled`
  - DI benefits = lx_disabled * monthly_benefit
- Requires a `MorbidityTable` with incidence (and termination for DI) rates

---

## 5. Reinsurance Treaty Layer

Treaties are applied as **transformations on `CashFlowResult`**. They do not re-run the projection — they modify the gross cash flow arrays.

### YRT Treaty

The most common North American individual life reinsurance structure.

```
NAR_t         = face_amount - reserve_t           # Net Amount at Risk
ceded_prem_t  = NAR_t * yrt_rate_t / 1000        # YRT rate per $1000 NAR
ceded_claim_t = claim_t * cession_pct             # Death claims: proportional
net_claim_t   = claim_t * (1 - cession_pct)
```

YRT rates are typically provided as a rate table by age, sex, smoker, and reinsurance duration. The `YRTTreaty` model stores these as a `MortalityTable`-like structure.

### Coinsurance Treaty

```
ceded_prem_t     = gross_prem_t * cession_pct
ceded_claim_t    = gross_claim_t * cession_pct
ceded_expense_t  = gross_expense_t * cession_pct
ceded_reserve_t  = gross_reserve_t * cession_pct
net_cashflow_t   = gross_cashflow_t * (1 - cession_pct)
```

### Modco Treaty

In modco, the cedant retains the assets backing ceded reserves. The reinsurer receives modco interest as compensation:
```
ceded_premiums  = gross_premiums * cession_pct
ceded_claims    = gross_claims * cession_pct
modco_interest  = ceded_reserve_balance * modco_interest_rate / 12
ceded_ncf       = ceded_premiums - ceded_claims + modco_interest
```
Reserves are NOT transferred — the cedant retains 100%. The `CashFlowResult.modco_interest` field carries this component. NCF additivity (net + ceded = gross) holds because modco_interest cancels between sides.

### Stop Loss Treaty

Aggregate stop loss covers annual claims above an attachment point up to an exhaustion point:
```
reinsurer_payment_y = min(max(annual_claims_y - attachment, 0), exhaustion - attachment)
```
Monthly back-allocation is pro-rata by monthly claims. Partial final years use pro-rated attachment/exhaustion (`year_fraction = n_months / 12`).

---

## 6. Output Structure

`CashFlowResult` is the canonical output of any projection or treaty application.

```python
class CashFlowResult(PolarisBaseModel):
    # Metadata
    run_id: str
    valuation_date: date
    basis: Literal["GROSS", "CEDED", "NET"]
    assumption_set_version: str

    # Time dimension
    projection_months: int
    time_index: np.ndarray   # shape (T,), dtype datetime64[M]

    # Aggregated cash flows (all shape (T,), summed across policies)
    gross_premiums: np.ndarray
    death_claims: np.ndarray
    lapse_surrenders: np.ndarray
    expenses: np.ndarray
    reserve_balance: np.ndarray
    reserve_increase: np.ndarray
    net_cash_flow: np.ndarray    # = premiums - claims - expenses - ΔReserve

    # Reinsurance-specific (populated by treaty.apply())
    modco_interest: np.ndarray | None = None   # Modco treaty only

    # Optional seriatim (shape (N, T)) — populated only when requested
    seriatim_premiums: np.ndarray | None = None
    seriatim_claims: np.ndarray | None = None
```

---

## 7. Analytics Layer Architecture

### Profit Tester
Accepts NET or GROSS basis `CashFlowResult` (rejects CEDED). Computes:
- Present value of profits at hurdle rate
- IRR (via `scipy.optimize.brentq` root-finding; returns None when NCF has no sign change)
- Break-even duration (first month where cumulative PV profit > 0)
- Profit margin (PV profits / PV premiums)

### Scenario Runner
Takes a base `AssumptionSet` and a list of `ScenarioAdjustment` objects (e.g., "multiply mortality by 110%"). Runs the projection once per scenario and returns a `ScenarioResult` with per-scenario profit metrics. Creates deep copies of scaled assumptions to respect immutability.

### Monte Carlo UQ
Samples N scenarios from parametric distributions over key assumptions:
- Mortality multiplier ~ LogNormal(mu=0, sigma) — always positive, mean ≈ 1
- Lapse multiplier ~ LogNormal(mu=0, sigma) — always positive, mean ≈ 1
- Interest rate shift ~ Normal(0, sigma) — additive shift to discount rate (floored at 0%)

All sampling uses `np.random.default_rng(seed)` for reproducibility.

Returns `UQResult` with:
- Full distributions of PV profits, IRRs, and profit margins (shape `(n_scenarios,)`)
- `percentile(pct)` — dict with pv_profit, irr, profit_margin at any percentile
- `var(confidence)` — Value at Risk (e.g., 5th percentile of PV profits at 95% confidence)
- `cvar(confidence)` — Conditional VaR (expected shortfall in the tail)
- Base (unperturbed) scenario results for comparison

---

## 8. Key Design Decisions

See `docs/DECISIONS.md` for full ADRs. Summary:

| Decision | Choice | Rationale |
|---|---|---|
| ORM for policy data | Polars DataFrame + Pydantic | Performance over convenience |
| Projection time step | Monthly | Industry standard for life insurance |
| Reserve basis | Net premium (Term/WL), AV (UL), zero (DI/CI) | Simplest auditable basis per product; IFRS 17 in Phase 3 |
| Mortality table format | CSV with standard column schema | No binary dependencies; auditability |
| Improvement scales | Embedded NumPy constants | Small data (< 15KB); no file I/O dependency |
| UL forced lapse | Indicator combined with voluntary lapse | Handles AV→0 gracefully in vectorized framework |
| Modco NCF additivity | Algebraic proof: modco_interest cancels | Ensures net + ceded = gross by construction |
| Stop loss partial year | Pro-rated attachment/exhaustion | Industry-standard for mid-year inception/expiry |
| UQ distributions | LogNormal (mort/lapse), Normal (rates) | Positive multipliers, reproducible via default_rng |
| Random number generation | `np.random.default_rng(seed)` | Reproducibility without global state |
| IRR solver | `scipy.optimize.brentq` | Guaranteed convergence; returns None when no sign change |
| Discount rate basis | Flat rate (per `ProjectionConfig`) | Stochastic rates in Phase 3 |

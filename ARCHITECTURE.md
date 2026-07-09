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

**Whole Life:** On the default `NET_PREMIUM` basis, net premium reserves with a prospective terminal estimate V_T = face * q_T * v; backward recursion proceeds from this approximation, which produces a horizon-edge decline (the $7.18M→$56k golden-WL artefact). The `CRVM` and `VM20` bases value the reserve to omega and close that artefact — see **Reserve Basis Selection** below.

**Universal Life:** Reserve = account value (simplified). The AV roll-forward itself is the reserve.

**Disability / CI:** Reserves set to zero (simplified for Phase 2; DI GAAP reserves are complex).

All products use the standard reserve recursion:
```
(V_t + P_t) * (1 + i)^(1/12) = q_t * b_t + (1 - q_t) * V_{t+1}
```

Where `i` is the valuation interest rate and `b_t` is the benefit paid at death.

### Reserve Basis Selection (`ReserveBasis`)

A reinsurer pricing an inforce block must reproduce the **cedant's** reserve, not
just a single net-premium reserve, because the reserve drives the YRT Net Amount
at Risk, the coinsurance reserve transfer, and the profit signature. The basis is
a projection-wide selector — `core/reserve_basis.py::ReserveBasis` (a `StrEnum`:
`NET_PREMIUM`, `CRVM`, `VM20`, `GAAP`) — set on `ProjectionConfig` (or via the
`--reserve-basis` CLI flag / API field) and dispatched inside each product's
`compute_reserves()`:

- **`NET_PREMIUM`** (default) — the classic net level premium reserve; the
  engine's historical behaviour, byte-identical to prior runs.
- **`CRVM`** — Commissioners Reserve Valuation Method (US statutory), implemented
  as **Full Preliminary Term**: a modified valuation that expenses the entire
  first-year net premium, lowering the first-year reserve. For Whole Life the
  CRVM reserve is valued **prospectively to omega** (max age), independent of the
  projection horizon — so it grades monotonically toward the face amount and does
  **not** show the horizon-edge collapse of the net-premium terminal estimate
  (the $7.18M→$56k golden-WL artefact, ADR-089).
- **`VM20`** — VM-20 simplified principle-based reserve (the deterministic-reserve
  / net-premium-reserve floor of US PBR), for Term and Whole Life (ADR-090/091).
- **`GAAP`** — US GAAP (FAS 60) net-premium benefit reserve on locked-in
  **best-estimate** assumptions plus explicit provisions for adverse deviation
  (PADs): the net premium reserve valued on a margined basis — the projection
  best-estimate `q` scaled by `ProjectionConfig.gaap_mortality_pad` and discounted
  at `gaap_valuation_rate` (the valuation rate less `gaap_interest_margin`).
  Neutral PADs (the defaults) collapse it onto the locked-in best-estimate net
  premium reserve. Unlike the statutory bases it does **not** read
  `valuation_mortality` and does **not** suppress mortality improvement — FAS 60 is
  a best-estimate-plus-PAD basis, not a prescribed static one. Implemented for
  `TermLife` (ADR-127, Slice 3) and `WholeLife` (ADR-128, Slice 4). For `TermLife`
  it is a finite-horizon net-premium recursion (terminal `V_T = 0`); for
  `WholeLife` it is a net **level** premium reserve valued **prospectively to
  omega** (like CRVM/VM-20, so it does not collapse at the horizon edge), using a
  single level valuation premium rather than CRVM's Full-Preliminary-Term split.

CRVM, VM-20, and GAAP (FAS 60) are all implemented for `TermLife` and `WholeLife`
(ADR-087–092, ADR-127, ADR-128) — the Reserve-Basis Exactness epic is complete.
Each product declares the bases it supports; selecting an **unsupported** basis
raises `PolarisComputationError` rather than silently falling back, so a run can
never report a reserve on a basis the engine did not actually compute. For *exact*
cedant CRVM reproduction, `AssumptionSet.valuation_mortality` supplies a distinct
**prescribed statutory valuation table** (e.g. 2001 CSO) that CRVM and the VM-20
NPR floor value on — static (no improvement scale), substandard rating applied,
valued to the valuation table's own omega for WL (ADR-125). Default `None` keeps
statutory bases on the projection mortality table; `NET_PREMIUM`, `GAAP`, and the
VM-20 deterministic reserve (anticipated experience by definition) always use the
projection assumptions. A configured `AssumptionSet.improvement` scale is a
best-estimate property: both `TermLife` and `WholeLife` apply it to the projection
cash flows and every best-estimate reserve (`NET_PREMIUM`, `GAAP`, VM-20 DR), and
never to the prescribed statutory bases (CRVM / VM-20 NPR), which stay static
(WholeLife: ADR-129). `valuation_mortality` is surfaced on the config / CLI
(`--valuation-mortality`) / API deal path (ADR-126, Slice 2). The GAAP PADs
(`gaap_mortality_pad` / `gaap_interest_margin`) currently live on
`ProjectionConfig`; surfacing them on the `DealConfig` / CLI / API deal path is a
tracked follow-up.

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
Reserves are NOT transferred — the cedant retains 100%. The `CashFlowResult.modco_interest` field carries this component. NCF additivity (net + ceded = gross) holds because modco_interest cancels between sides. `ModcoTreaty.apply()` optionally accepts an `AssetPortfolio`: when supplied, `modco_interest_rate` is replaced by the portfolio's `book_yield()` (Option A precedence — the flat rate is the fallback when the book yield is unrecoverable), so the modco interest reflects what the backing assets actually earn (ADR-110, Asset/ALM Slice 3). The no-portfolio path is byte-identical to the flat-rate formula above; see "Asset / ALM Model" below.

### Stop Loss Treaty

Aggregate stop loss covers annual claims above an attachment point up to an exhaustion point:
```
reinsurer_payment_y = min(max(annual_claims_y - attachment, 0), exhaustion - attachment)
```
Monthly back-allocation is pro-rata by monthly claims. Partial final years use pro-rated attachment/exhaustion (`year_fraction = n_months / 12`).

### Expense Allowance & Experience Refund

Proportional treaties (`CoinsuranceTreaty`, `YRTTreaty`) carry two optional reinsurer→cedant transfers that price the deal's economics without changing the gross block — both preserve `net + ceded = gross` by netting to zero across the (net, ceded) pair, so neither adds a `CashFlowResult` field (Expense-allowance epic, Tier-B B3).

**Expense allowance** (`reinsurance/expense_allowance.py`, ADR-118/119, wired in Slice 2). `ExpenseAllowance` quotes an allowance as a % of **ceded premium** — a high first-year rate (reimbursing acquisition cost) and a lower renewal rate, optionally on a **sliding scale** keyed to the realized ceded loss ratio (validated monotone non-increasing: better experience pays at least as much). When set on a treaty, the per-period allowance is folded into the expense line (`+A` ceded, `−A` net) via `BaseTreaty._expense_allowance_transfer()`. The first-year rate maps **projection month → policy duration** on an inforce block (`first_year_fraction_for_block`, face-weighted) so mid-duration renewal business is charged the renewal rate, not the first-year rate. Default `None` → byte-identical.

**Experience refund** (`reinsurance/experience_refund.py`, ADR-120 model + primitive, ADR-121 treaty wiring in Slice 3b-1). `ExperienceRefund` refunds the cedant a share of accumulated favourable experience: an experience account accumulates `premium − claims − allowance − reinsurer_margin_pct·premium` per period (optionally at interest), and `compute_refund() = refund_pct · max(0, balance − retention)` (non-negative — an unfavourable balance refunds nothing). When set on a treaty (`experience_refund` field), the scalar refund is a **single terminal** reinsurer→cedant transfer placed at the final projection period via `BaseTreaty._experience_refund_transfer()` and folded into the expense line (`+R` ceded, `−R` net), computed **net of** any expense allowance already paid (no double-count). Default `None` → byte-identical.

**Deal-path surfacing** (Slice 3b-2, split into 3b-2a CLI/config + 3b-2b API/Excel). Slice 3b-2a (ADR-122) surfaced both terms on the **CLI config path**: `DealConfig` carries optional `expense_allowance` / `experience_refund` fields, `_parse_config_to_pipeline_inputs` parses the `deal.expense_allowance` / `deal.experience_refund` JSON blocks (validated by the models — a malformed scale raises at parse time), and `build_treaty` / `_build_treaty_for_pipeline` thread them onto the YRT / Coinsurance treaty. So `polaris price --config` honours both terms end-to-end; default `None` → goldens byte-identical. Slice 3b-2b (API + Excel) was split surface-by-surface: Slice 3b-2b-1 (ADR-123) surfaced both terms on the **REST API** request models (`PriceRequest`, `ScenarioRequest`, `UQRequest`, `PortfolioDealRequest`), threaded through `_build_treaty` onto the YRT (flat + tabular) / Coinsurance treaty at all four call sites, with an app-level `PolarisValidationError` → HTTP 422 handler so a malformed nested term fails cleanly during request-body parsing; default `None` → responses byte-identical. Slice 3b-2b-2 (ADR-124) surfaced them on the **deal-pricing Excel export**: `DealPricingExport` carries optional `expense_allowance` / `experience_refund` fields and the writer appends a **"Treaty Terms" panel** to the Assumptions sheet (the rated-block-panel precedent) rendering the allowance (first-year/renewal %, sliding-scale bands) and refund (refund %, retention, margin, interest) terms, threaded from `_cohort_to_deal_pricing_export` via `inputs.deal.*`; default `None` for both → workbook byte-identical. **With this slice the B3 epic is COMPLETE** — the allowance/refund terms are consistent across all four deal-pricing consumers (config, CLI, API, Excel). Per-period/annual refund settlement timing, deficit carryforward, and a dashboard input surface remain future refinements (harvested to PRODUCT_DIRECTION_2026-06-18 Promoted Follow-ups).

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

### Premium Sufficiency
`PremiumSufficiencyTester` (`analytics/premium_sufficiency.py`) answers "is the premium adequate?" independent of the reserve. It compares PV(premiums) against PV(benefits = claims + surrenders) + PV(expenses), **excluding the reserve movement** (a balance-sheet timing item, not an economic cost — this is what distinguishes it from the Profit Tester). Returns PV loss / expense / combined ratios, a `sufficiency_margin = 1 − combined_ratio`, and an `is_sufficient` verdict against a target margin. Basis-agnostic: GROSS = cedant premium adequacy, reinsurer-view NET = reinsurance premium adequacy.

### IFRS 17 — Measurement and Movement
`analytics/ifrs17.py` provides point-in-time measurement (BBA → BEL/RA/CSM; PAA → LRC/LIC; VFA) **and** the period-to-period analysis of change. `IFRS17CohortManager` groups contracts into annual issue-year cohorts, each measured BBA at its **own locked-in discount rate**, and rolls each forward `opening → new business → interest accretion → release → closing` for BEL, RA, and CSM. Each `IFRS17ComponentMovement` foots by construction (`opening + Σ movements − closing ≈ 0`); `cohort_movement_tables()` returns the per-cohort `IFRS17MovementTable`s (ordered by issue year) and `aggregate_movement_table()` their per-period sum.

### Regulatory Capital and Return on Capital
Capital models share a structural contract in `analytics/capital_base.py`: the `CapitalModel` protocol — `required_capital(cashflows, nar=None) -> CapitalSchedule` — and the `CapitalSchedule` protocol (`capital_by_period (T,)`, `initial_capital`, `peak_capital`, `pv_capital(rate)`, `capital_strain()`, `pv_capital_strain(rate)`, `capital_ratio(available_capital)`). The last is the jurisdiction's regulatory solvency ratio at issue — `available_capital / denominator₀` — with the denominator encapsulated per implementation (ADR-103). Three implementations satisfy the contract structurally (all `@runtime_checkable`):
- **LICAT** (`capital.py`): `LICATCapital` → `CapitalResult`, with C-1 (asset default), C-2 (insurance = mortality + lapse + morbidity), and C-3 (interest) components on the `CashFlowResult`; `capital_ratio` is the LICAT total ratio (available capital ÷ required capital₀).
- **US RBC** (`rbc.py`): `RBCCapital` → `RBCResult`, aggregating the NAIC C-0…C-4 components by the covariance square root; `capital_ratio` is the RBC ratio (TAC ÷ ACL₀, where ACL = ½ the Company Action Level it holds), with `rbc_ratio(total_adjusted_capital)` retained as a thin RBC-named alias (ADR-098 / ADR-103).
- **EU Solvency II** (`solvency2.py`): `SolvencyIICapital` → `SolvencyIIResult`, building the standard-formula SCR through two correlation-matrix aggregations (`sqrt(rᵀ·Corr·r)` via einsum) — life sub-modules (mortality / lapse / catastrophe) → life SCR → BSCR with market + counterparty, plus a linear operational add-on — and exposing a cost-of-capital `risk_margin(rate)` (ADR-100); `capital_ratio` is the EU solvency ratio (own funds ÷ SCR₀). Matrices are Delegated Regulation (EU) 2015/35 Annex IV constants.

Both return-on-capital entry points consume any `CapitalModel` through this seam (ADR-099): `ProfitTester.run_with_capital(capital_model, *, nar=None, available_capital=None)` for a single deal and `Portfolio.run_with_capital(hurdle_rate, capital_model)` for an aggregate book, each returning return-on-capital, peak capital, PV capital (stock), and PV capital strain. Both depend only on the `CapitalSchedule` surface, so widening them from the concrete `LICATCapital` to the protocol was type-only and left the LICAT path byte-identical. The protocol seam is what lets the same RoC machinery serve every jurisdiction. The regulatory solvency ratio is surfaced jurisdiction-agnostically: when `run_with_capital` is given an optional `available_capital` numerator (available capital / TAC / own funds), it computes `capital.capital_ratio(available_capital)` and populates `ProfitResultWithCapital.available_capital` / `.capital_ratio` (both default `None`, so omitting the input leaves the result byte-identical) — the per-jurisdiction denominator stays encapsulated on the concrete `CapitalSchedule` (ADR-103). Other jurisdiction-specific extras (e.g. RBC's `authorized_control_level`) remain on the concrete schedule rather than the jurisdiction-agnostic result.

The jurisdiction is selectable end-to-end: a single registry `capital_model_for(model_id, product_type)` in `capital_base.py` (with `SUPPORTED_CAPITAL_MODELS` and the `CapitalModelId` literal) maps `licat` / `rbc` / `solvency2` to the matching calculator, and every surface routes through it — the CLI `polaris price --capital {licat,rbc,solvency2}` flag and the REST API `capital_model` field (ADR-101), and the Streamlit dashboard's "Regulatory capital basis (RoC)" selector and the deal-pricing Excel workbook's jurisdiction-labelled capital block (ADR-102). A shared `CAPITAL_MODEL_LABELS` / `capital_model_label()` in the same module is the single labelling site, so the dashboard tiles and the Excel header always name the standard the calculator actually ran. The default (and `licat`) path stays byte-identical; only an explicit non-LICAT selection moves the priced numbers. Calculator imports inside the registry are deferred to call time because the calculators import `capital_base` for shared helpers — a module-level import would be circular. The result-level solvency/RBC-ratio field is shipped (Slice 4c-1, ADR-103) as the `capital_ratio` surface described above; the remaining Slice 4c-2 work is *surfacing* it — threading the `available_capital` numerator in from the CLI / API / dashboard and rendering the ratio on the Excel capital block and dashboard tiles — plus a three-standard validation notebook.

### Portfolio Aggregation
`analytics/portfolio.py::Portfolio` holds many `(InforceBlock, AssumptionSet, BaseTreaty)` deals and aggregates their `CashFlowResult`s into a `PortfolioResult` — aggregate NCF/IRR/PV, a per-deal breakdown, and concentration / HHI by cedant, product, and treaty type across three weight bases (ceded face, peak ceded NAR, PV premium). Calendar alignment places mixed-inception books on a common monthly grid; `run_scenarios()` applies the standard stress set across the whole portfolio. Each deal is projected on the reinsurer view by default.

### Asset / ALM Model
The asset side (Epic 4, Tier-C C0, ROADMAP 5.4) gives the engine fixed-income assets to set against the liability. `core/asset.py` defines `Bond` (a single instrument valued on the monthly grid — `cash_flow_vector(months)` for coupon + principal, `price(annual_yield)`) and `AssetPortfolio` (a non-empty list of bonds aggregating cash flow, market/book value, and face). All asset pricing and risk measures use the **same** discounting as `CashFlowResult.pv_*` — `v = (1 + y) ** (-1/12)`, cash flow at month `t` discounted by `v ** t` — so a bond PV and a projection PV are directly comparable (ADR-108). `AssetPortfolio` also exposes `book_yield()` (gross effective-annual IRR of carrying value vs cash flows via `brentq`, `None` on no sign change — a scalar held flat), `investment_income(reserve_vector, annual_yield=None)` (`= reserve · y / 12`), and `macaulay_duration` / `modified_duration` / `convexity` (time in years, textbook closed forms under the effective-annual yield) (ADR-109). The Modco integration (ADR-110) drives modco interest from `book_yield()` — see the Modco Treaty section above.

`analytics/alm.py` closes the loop with asset-liability **duration-gap** analysis (ADR-111). `duration_measures(cash_flows, annual_yield) -> DurationMeasures` is the reusable core: PV plus Macaulay / modified duration of any stream on the engine convention — the same closed form as the `AssetPortfolio` duration methods, generalised (a consistency test locks the two together). `liability_cash_flows(result)` extracts the net benefit-outgo stream `death_claims + lapse_surrenders + expenses - gross_premiums` — the obligation the assets fund. `duration_gap(portfolio, liability_cash_flow_vector, valuation_yield) -> DurationGapResult` measures both sides at one common flat valuation yield (isolating the timing mismatch from any yield difference) and reports each side's value and Macaulay / modified duration, the duration gap (asset minus liability modified duration, years), and the dollar-duration gap (`modified · value` differenced — the surplus change per unit yield). Malformed input raises `PolarisValidationError`; a non-positive present/market value raises `PolarisComputationError`. For the user-facing surfaces the duration-gap liability is the reserve-backed run-off stream `reserve_liability_cash_flows(result, reserve_valuation_rate)`, whose PV telescopes to the held reserve (ADR-113), and the gap is reported as a dual `DualDurationGap` — the reinsurer-view (ceded reserve, headline) and cedant-view (retained reserve), each `None` when its reserve is non-positive at the yield (ADR-114). The duration gap is surfaced on `polaris price` (per-cohort `alm_duration_gap` JSON + Rich table, ADR-112), the REST `/api/v1/price` response (ADR-114), the deal-pricing Excel workbook's "ALM Duration Gap" sheet (ADR-115), and the Streamlit dashboard's Deal Pricing page (an optional asset-portfolio JSON input + duration-gap display reusing the same `dual_duration_gap` compute path, ADR-116) — each emitted only when an `AssetPortfolio` is supplied, so any run without one leaves goldens byte-identical. An end-to-end validation notebook (4b-4) is the one remaining sub-slice.

`analytics/validation.py` is the **validation & benchmark pack** — the executable evidence behind the "credible open-source alternative to AXIS / Prophet" thesis (ADR-130 / ADR-131 / ADR-132). It holds engine-agnostic reference cases (`ValidationCase` = authoritative expected value + citation + documented tolerance; `ValidationReport` scores them and renders a diligence-grade Markdown pass/fail table). References are **identities or cited constants, never recalled numbers**: constant-force term/annuity APVs vs their exact discrete closed forms and the continuous-force textbook identity (`run_closed_form_benchmarks()`), and the SOA Illustrative Life Table whole-life `A_x` / `ä_x` / `P_x` at `i=6%` reproduced by the live WholeLife engine to machine precision (`run_statutory_deck_benchmarks()`; the vendored `l_x` is regenerated from the table's published Makeham law and self-checked). `run_full_validation_pack()` is the single entry point spanning all three categories. It is surfaced headless by `polaris benchmark` (`--pack {full,closed-form,deck}`, `-o` Markdown / `--json` export, **non-zero exit on any FAIL** so it can gate CI — ADR-132; distinct from `polaris validate`, which checks *input-file* schemas) and by `notebooks/05_validation_report.ipynb`, whose embedded `assert`s make executing it the verification. The pack never touches the pricing path, so every surface is pricing-neutral and leaves goldens byte-identical.

### API Observability
`api/observability.py` is the production-hardening layer for the REST service (A2′, ROADMAP 6.2, Slice 1 — ADR-133). `RequestContextMiddleware` (a Starlette `BaseHTTPMiddleware` wired in at app construction) assigns every request a **correlation id** — echoing an inbound `X-Request-ID` / `X-Correlation-ID` header for trace propagation, otherwise a generated uuid4 — times it on `time.perf_counter` (monotonic), emits a structured access-log record, and returns the correlation id and duration as the `X-Correlation-ID` / `X-Response-Time-Ms` response headers. `JsonLogFormatter` renders each record as single-line JSON (timestamp, level, logger, message, correlation id, structured `extra`s) for a log aggregator; `configure_api_logging` idempotently attaches it to a dedicated, non-propagating `polaris_re.api.access` logger; and `correlation_id_var` (a `ContextVar`) publishes the id so any engine log during the request can be stamped with it. Standard-library only (no new runtime dependency), fully additive — the pricing path is untouched and goldens stay byte-identical. Optional API-key auth + rate limiting (Slice 2) and Kubernetes/Helm manifests + a Prometheus `/metrics` endpoint (Slice 3) follow.

---

## 8. Key Design Decisions

See `docs/DECISIONS.md` for full ADRs. Summary:

| Decision | Choice | Rationale |
|---|---|---|
| ORM for policy data | Polars DataFrame + Pydantic | Performance over convenience |
| Projection time step | Monthly | Industry standard for life insurance |
| Reserve basis | Selectable `ReserveBasis` — NET_PREMIUM (default), CRVM, VM20, GAAP (FAS 60) for Term/WL; AV (UL); zero (DI/CI) | Reproduce the cedant's statutory reserve; unsupported basis raises, never silently falls back |
| Regulatory capital | `CapitalModel` / `CapitalSchedule` protocols; LICAT + US RBC + EU Solvency II implementations | One RoC machinery across jurisdictions; structural (runtime-checkable) seam, no inheritance |
| IFRS 17 movement | Annual issue-year cohorts, locked-in rate per cohort, footing movement tables | Matches IASB analysis-of-change presentation; cohorts sum to the aggregate by construction |
| Mortality table format | CSV with standard column schema | No binary dependencies; auditability |
| Improvement scales | Embedded NumPy constants | Small data (< 15KB); no file I/O dependency |
| UL forced lapse | Indicator combined with voluntary lapse | Handles AV→0 gracefully in vectorized framework |
| Modco NCF additivity | Algebraic proof: modco_interest cancels | Ensures net + ceded = gross by construction |
| Asset / ALM model | `Bond` / `AssetPortfolio` on the engine discounting convention; modco interest from `book_yield()`; `analytics/alm.py` duration gap at one common flat yield | Bond and projection PVs reconcile; one closed form for asset + liability duration; flat-yield scope isolates the timing mismatch |
| API observability | `RequestContextMiddleware` + `JsonLogFormatter` on a non-propagating access logger; correlation id via `X-Request-ID` header or uuid4; monotonic-clock duration | Structured, correlated, duration-instrumented logs with no new runtime dependency; additive so goldens stay byte-identical |
| Stop loss partial year | Pro-rated attachment/exhaustion | Industry-standard for mid-year inception/expiry |
| UQ distributions | LogNormal (mort/lapse), Normal (rates) | Positive multipliers, reproducible via default_rng |
| Random number generation | `np.random.default_rng(seed)` | Reproducibility without global state |
| IRR solver | `scipy.optimize.brentq` | Guaranteed convergence; returns None when no sign change |
| Discount rate basis | Flat rate (per `ProjectionConfig`) | Stochastic rates in Phase 3 |

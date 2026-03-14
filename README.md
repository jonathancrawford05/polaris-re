# Polaris RE

**A Python-native life reinsurance cash flow projection and deal pricing engine.**

Polaris RE is an open-source actuarial modeling library targeting the individual life reinsurance pricing workflow. It is designed as a modern, vectorized, Python-first alternative to proprietary actuarial modeling systems (AXIS, Prophet) for the specific use case of reinsurance deal evaluation.

---

## Why Polaris RE?

Reinsurance deal pricing today is predominantly done in:
- **AXIS / Prophet** — powerful but proprietary, expensive, Windows-only, disconnected from the Python/ML ecosystem
- **Excel** — fragile, not version-controlled, not reproducible

Polaris RE provides:
- ✅ Full Python — `pip install`, Git-native, CI/CD compatible
- ✅ Vectorized projections — designed for 100k+ policy inforce blocks
- ✅ Actuarially correct — closed-form verified, auditable
- ✅ Composable — swap assumptions, products, and treaty structures independently
- ✅ ML-ready — assumptions can be driven by XGBoost or scikit-learn models
- ✅ Modern — Pydantic v2, Polars, NumPy, typed throughout

---

## Supported Features (Phase 1)

| Feature | Status |
|---|---|
| Term Life cash flow projection (monthly) | 🔄 In progress |
| CIA 2014 and SOA VBT 2015 mortality tables | 🔄 In progress |
| Mortality improvement (Scale AA, MP-2020) | 🔄 In progress |
| Duration-based lapse assumptions | 🔄 In progress |
| YRT reinsurance treaty | 🔄 In progress |
| Coinsurance treaty | 🔄 In progress |
| Net premium reserve calculation | 🔄 In progress |
| Profit testing (IRR, PV profits, break-even) | 🔄 In progress |
| Scenario analysis | 🔄 In progress |

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full phased build plan.

---

## Quick Start

```bash
# Install
git clone https://github.com/your-org/polaris-re.git
cd polaris-re
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
make test

# Launch validation notebook
make notebook
```

### Example: Price a YRT Treaty on a Term Life Block

```python
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.analytics.profit_test import ProfitTester
from datetime import date

# 1. Define an inforce block
policies = [
    Policy(
        policy_id="P001",
        issue_age=40,
        attained_age=45,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="PREFERRED",
        face_amount=500_000.0,
        annual_premium=1_200.0,
        product_type=ProductType.TERM,
        policy_term=20,
        duration_inforce=60,  # 5 years in force
        reinsurance_cession_pct=0.50,
        issue_date=date(2020, 1, 1),
        valuation_date=date(2025, 1, 1),
    )
]
block = InforceBlock(policies=policies)

# 2. Build assumption set
mortality = MortalityTable.load(source=MortalityTableSource.SOA_VBT_2015)
lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.05, "ultimate": 0.03})
assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="v1.0")

# 3. Configure projection
config = ProjectionConfig(
    valuation_date=date(2025, 1, 1),
    projection_horizon_years=20,
    discount_rate=0.05,
)

# 4. Project gross cash flows
product = TermLife(inforce=block, assumptions=assumptions, config=config)
gross_cashflows = product.project()

# 5. Apply YRT treaty
treaty = YRTTreaty(cession_pct=0.50, yrt_rate_table=mortality)
net_cashflows = treaty.apply(gross_cashflows)

# 6. Profit test
profit_tester = ProfitTester(cashflows=net_cashflows, hurdle_rate=0.10)
result = profit_tester.run()

print(f"IRR:            {result.irr:.2%}")
print(f"PV Profits:     ${result.pv_profits:,.0f}")
print(f"Profit Margin:  {result.profit_margin:.2%}")
print(f"Break-even:     Year {result.breakeven_year}")
```

---

## Project Structure

```
polaris-re/
├── CLAUDE.md              ← Build instructions for Claude Code
├── ARCHITECTURE.md        ← System design documentation
├── docs/
│   ├── ROADMAP.md         ← Phased feature plan
│   ├── DECISIONS.md       ← Architecture decision records
│   └── ACTUARIAL_GLOSSARY.md
├── src/polaris_re/
│   ├── core/              ← Policy, InforceBlock, ProjectionConfig, CashFlowResult
│   ├── assumptions/       ← Mortality tables, improvement scales, lapse
│   ├── products/          ← Term life, whole life, UL (Phase 2)
│   ├── reinsurance/       ← YRT, coinsurance, modco (Phase 2)
│   ├── analytics/         ← Profit testing, scenarios, UQ
│   └── utils/             ← Table loaders, interpolation, date utilities
├── tests/
├── notebooks/
└── pyproject.toml
```

---

## Domain Background

Polaris RE targets the **individual life reinsurance** market. The primary users are:

- **Reinsurance actuaries** pricing YRT and coinsurance treaties on inforce blocks
- **Valuation actuaries** running IFRS 17 projections (Phase 3)
- **Data scientists** integrating ML-based mortality assumptions into actuarial projections

The core methodology follows industry-standard North American actuarial practice. All cash flow calculations are fully transparent and auditable.

---

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for the complete build specification. This project is designed to be built iteratively with Claude Code.

## License

MIT

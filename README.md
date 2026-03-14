# Polaris RE

**A Python-native life reinsurance cash flow projection and deal pricing engine.**

Polaris RE is an open-source actuarial modeling library targeting the individual life reinsurance pricing workflow. It is designed as a modern, vectorized, Python-first alternative to proprietary actuarial modeling systems (AXIS, Prophet) for the specific use case of reinsurance deal evaluation.

---

## Why Polaris RE?

Reinsurance deal pricing today is predominantly done in:
- **AXIS / Prophet** — powerful but proprietary, expensive, Windows-only, disconnected from the Python/ML ecosystem
- **Excel** — fragile, not version-controlled, not reproducible

Polaris RE provides:
- ✅ **Full Python** — managed with `uv`, Git-native, CI/CD on GitHub Actions
- ✅ **Vectorized** — designed for 100k+ policy inforce blocks; NumPy (N×T) arrays throughout
- ✅ **Actuarially correct** — closed-form verified, auditable cash flows
- ✅ **Composable** — swap assumptions, products, and treaty structures independently
- ✅ **ML-ready** — assumptions can be driven by XGBoost or scikit-learn models
- ✅ **Modern stack** — Python 3.12+, Pydantic v2, Polars 1.0+, NumPy 2.0+, fully typed

---

## Status

| Feature | Status |
|---|---|
| Core data models (`Policy`, `InforceBlock`, `ProjectionConfig`, `CashFlowResult`) | ✅ Complete |
| Term Life cash flow projection (monthly, vectorized) | 🔄 In progress (Phase 1) |
| CIA 2014 and SOA VBT 2015 mortality tables | 🔄 In progress (Phase 1) |
| Duration-based lapse assumptions | 🔄 In progress (Phase 1) |
| YRT reinsurance treaty | 🔄 In progress (Phase 1) |
| Coinsurance treaty | 🔄 In progress (Phase 1) |
| Net premium reserve recursion | 🔄 In progress (Phase 1) |
| Profit testing (IRR, PV profits, break-even) | 🔄 In progress (Phase 1) |
| Scenario analysis (stress testing) | 🔄 In progress (Phase 1) |
| Whole Life, UL, Modco, Monte Carlo UQ | 📅 Phase 2 |
| IFRS 17, stochastic rates, REST API | 📅 Phase 3 |

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full phased build plan.

---

## Quick Start

**Requires:** Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and set up
git clone https://github.com/jonathancrawford05/polaris-re.git
cd polaris-re
uv sync                    # creates .venv and installs all dependencies

# Verify
uv run python -c "import polaris_re; print(polaris_re.__version__)"

# Run tests
make test

# Launch validation notebook
make notebook
```

### Common commands

```bash
make test           # fast tests (excludes @slow)
make test-all       # all tests
make lint           # ruff + mypy
make format         # auto-fix formatting
make coverage       # test with HTML coverage report
make docker-build   # build Docker image
make docker-test    # run tests inside Docker
make validate-tables  # check mortality table CSV files are present
make synthetic-block  # generate synthetic inforce block for testing
```

---

## Example: Price a YRT Treaty on a Term Life Block

> **Note:** The projection engine is currently in Phase 1 development. The example below shows the intended API once complete.

```python
from datetime import date
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.analytics.profit_test import ProfitTester

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
        duration_inforce=60,   # 5 years in force
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
gross = product.project()

# 5. Apply YRT treaty
treaty = YRTTreaty(cession_pct=0.50, flat_yrt_rate_per_1000=1.20)
net, ceded = treaty.apply(gross)

# 6. Profit test
result = ProfitTester(cashflows=net, hurdle_rate=0.10).run()

print(f"IRR:           {result.irr:.2%}")
print(f"PV Profits:    ${result.pv_profits:,.0f}")
print(f"Profit Margin: {result.profit_margin:.2%}")
print(f"Break-even:    Year {result.breakeven_year}")
```

---

## Project Structure

```
polaris-re/
├── CLAUDE.md              ← Claude Code build instructions (read before every session)
├── ARCHITECTURE.md        ← System design, data flow, formulas
├── Dockerfile             ← Multi-stage build (builder / runtime / dev)
├── docker-compose.yml     ← Local dev and JupyterLab service
├── .github/
│   └── workflows/ci.yml   ← GitHub Actions: lint → test (3.12/3.13) → docker → coverage
├── docs/
│   ├── ROADMAP.md         ← Phased feature plan with milestone checklists
│   ├── DECISIONS.md       ← Architecture decision records (ADRs)
│   └── ACTUARIAL_GLOSSARY.md  ← Domain terminology reference
├── src/polaris_re/
│   ├── core/              ← Policy, InforceBlock, ProjectionConfig, CashFlowResult ✅
│   ├── assumptions/       ← Mortality tables, improvement scales, lapse 🔄
│   ├── products/          ← Term life, whole life, UL 🔄
│   ├── reinsurance/       ← YRT, coinsurance, modco 🔄
│   ├── analytics/         ← Profit testing, scenarios, UQ 🔄
│   └── utils/             ← Table loaders, interpolation, date utilities 🔄
├── tests/
├── notebooks/
├── scripts/
│   ├── validate_tables.py        ← Check mortality CSV files are present
│   └── generate_synthetic_block.py  ← Generate test inforce data
└── pyproject.toml
```

---

## Development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — fast Python package manager
- Docker (optional, for containerized test runs)

### Setup

```bash
uv sync           # install all dependencies including dev extras
make lint         # ruff check + mypy
make test         # run fast tests
make coverage     # run tests with coverage report
```

### Mortality Table Data

Real CIA 2014 and SOA VBT 2015 tables require licensing from the respective actuarial bodies. For development and testing, use synthetic fixture tables:

```bash
make synthetic-block   # generates data/synthetic_block.csv for testing
```

Place licensed table CSVs in `$POLARIS_DATA_DIR/mortality_tables/` and run `make validate-tables` to confirm they are correctly formatted.

---

## Domain Background

Polaris RE targets the **individual life reinsurance** market. Primary users:

- **Reinsurance actuaries** pricing YRT and coinsurance treaties on inforce blocks
- **Valuation actuaries** running IFRS 17 projections (Phase 3)
- **Data scientists** integrating ML-based mortality assumptions into actuarial projections

The methodology follows industry-standard North American actuarial practice (CIA, SOA). All cash flow calculations are transparent and auditable.

---

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for the complete build specification and session workflow. This project is designed to be built iteratively with Claude Code.

## License

MIT

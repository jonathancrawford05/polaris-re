# Polaris RE

**A Python-native life reinsurance cash flow projection and deal pricing engine.**

Polaris RE is an open-source actuarial modeling library for the individual life reinsurance pricing workflow. It is designed as a modern, vectorized, Python-first alternative to proprietary actuarial modeling systems (AXIS, Prophet) for the specific use case of reinsurance deal evaluation.

---

## Why Polaris RE?

Reinsurance deal pricing today is predominantly done in:
- **AXIS / Prophet** — powerful but proprietary, expensive, Windows-only, disconnected from the Python/ML ecosystem
- **Excel** — fragile, not version-controlled, not reproducible

Polaris RE provides:
- ✅ **Full Python** — managed with `uv`, Git-native, CI/CD on GitHub Actions
- ✅ **Vectorized** — NumPy `(N × T)` arrays throughout; no loops over policies
- ✅ **Actuarially correct** — closed-form verified, auditable cash flows
- ✅ **Composable** — swap assumptions, products, and treaty structures independently
- ✅ **ML-ready** — assumptions can be driven by XGBoost or scikit-learn models
- ✅ **Modern stack** — Python 3.12+, Pydantic v2, Polars 1.0+, NumPy 2.0+, fully typed
- ✅ **API-first** — full REST API (FastAPI), CLI (Typer), and Streamlit dashboard
- ✅ **IFRS 17** — BBA, PAA, and VFA measurement models

---

## Status

All three phases are complete. 439 tests, 94% coverage.

| Module | Feature | Status |
|---|---|---|
| `core/` | Policy, InforceBlock, ProjectionConfig, CashFlowResult | ✅ |
| `assumptions/` | Mortality tables (SOA VBT 2015, CIA 2014, 2001 CSO) | ✅ |
| `assumptions/` | Mortality improvement — Scale AA, MP-2020, CPM-B | ✅ |
| `assumptions/` | Lapse — duration-based select/ultimate | ✅ |
| `assumptions/` | Morbidity — CI incidence, DI incidence + termination | ✅ |
| `products/` | Term Life — monthly vectorized projection, net premium reserves | ✅ |
| `products/` | Whole Life — par/non-par, limited pay, prospective reserves | ✅ |
| `products/` | Universal Life — COI charges, account value roll-forward, forced lapse | ✅ |
| `products/` | Disability / Critical Illness — DI multi-state, CI single-decrement | ✅ |
| `reinsurance/` | YRT — NAR-based premiums, ceded claims | ✅ |
| `reinsurance/` | Coinsurance — proportional split, reserve transfer | ✅ |
| `reinsurance/` | Modco — cedant retains assets, modco interest | ✅ |
| `reinsurance/` | Stop Loss — aggregate cover, attachment/exhaustion, pro-ration | ✅ |
| `analytics/` | Profit Testing — IRR, PV profits, break-even, margin | ✅ |
| `analytics/` | Scenario Analysis — 6 standard stress scenarios | ✅ |
| `analytics/` | Monte Carlo UQ — LogNormal/Normal sampling, VaR, CVaR | ✅ |
| `analytics/` | IFRS 17 — BBA (BEL/RA/CSM), PAA (LRC/LIC), VFA | ✅ |
| `analytics/` | Stochastic Rates — Hull-White one-factor, CIR | ✅ |
| `analytics/` | Experience Studies — A/E, limited-fluctuation credibility, blended rates | ✅ |
| `api/` | REST API — FastAPI with full OpenAPI docs | ✅ |
| `cli.py` | CLI — `polaris price / scenario / uq / validate / version` | ✅ |
| `dashboard/` | Streamlit dashboard — pricing, scenarios, Monte Carlo | ✅ |

---

## Quick Start

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for the full setup guide including Docker, Codespaces, mortality table loading, and API testing.

**Requires:** Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone https://github.com/jonathancrawford05/polaris-re.git
cd polaris-re
uv sync --all-extras
make test
```

### Common commands

```bash
make test             # fast tests (excludes @slow)
make test-all         # all tests including slow
make lint             # ruff check + mypy
make format           # auto-fix formatting
make coverage         # test with HTML coverage report (target ≥ 90%)
make docker-build     # build Docker image
make docker-test      # run tests inside Docker (mirrors CI job 3)
make validate-tables  # validate mortality CSV files in $POLARIS_DATA_DIR
make synthetic-block  # generate 1000-policy synthetic inforce block
make notebook         # launch JupyterLab
```

### CLI demo mode

`polaris price` (and `scenario`, `uq`) runs in **demo mode** when no `--config`
is supplied, using the shipped fixtures at `data/configs/demo.json` and
`data/inputs/demo.csv`:

```bash
uv run polaris price                      # price the demo block end-to-end
uv run polaris price -i my_block.csv      # demo config, custom inforce CSV
uv run polaris price -c my_deal.json      # custom config, embedded policies
```

Set `POLARIS_PARITY_DEBUG=1` to dump year-by-year cash flow CSVs (gross / net /
ceded) to `data/outputs/parity/`. Override the location with
`POLARIS_PARITY_OUTPUT=<path>`.

---

## Example: Price a YRT Deal on a Term Life Block

```python
from datetime import date
from pathlib import Path

from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.analytics.profit_test import ProfitTester

# 1. Inforce block
policy = Policy(
    policy_id="P001", issue_age=40, attained_age=40,
    sex=Sex.MALE, smoker_status=SmokerStatus.NON_SMOKER,
    underwriting_class="STANDARD", face_amount=1_000_000.0,
    annual_premium=12_000.0, product_type=ProductType.TERM,
    policy_term=20, duration_inforce=0, reinsurance_cession_pct=0.50,
    issue_date=date(2025, 1, 1), valuation_date=date(2025, 1, 1),
)
block = InforceBlock(policies=[policy])

# 2. Load real mortality table (SOA VBT 2015)
mortality = MortalityTable.load(
    source=MortalityTableSource.SOA_VBT_2015,
    data_dir=Path("data"),
)
lapse = LapseAssumption.from_duration_table(
    {1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03}
)
assumptions = AssumptionSet(
    mortality=mortality, lapse=lapse,
    version="v1.0", effective_date=date(2025, 1, 1),
)

# 3. Project gross cash flows
config = ProjectionConfig(
    valuation_date=date(2025, 1, 1),
    projection_horizon_years=20,
    discount_rate=0.06,
)
gross = TermLife(block, assumptions, config).project()

# 4. Apply YRT treaty
treaty = YRTTreaty(cession_pct=0.90, total_face_amount=1_000_000.0)
net, ceded = treaty.apply(gross)

# 5. Profit test
result = ProfitTester(cashflows=net, hurdle_rate=0.10).run()
print(f"IRR:           {result.irr:.2%}")
print(f"PV Profits:    ${result.pv_profits:,.0f}")
print(f"Profit Margin: {result.profit_margin:.2%}")
print(f"Break-even:    Year {result.breakeven_year}")
```

---

## Example: REST API

Once the API container is running (see [QUICKSTART.md](docs/QUICKSTART.md)):

```bash
# Price a deal
curl -s -X POST http://localhost:8000/api/v1/price \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool

# IFRS 17 BBA measurement
curl -s -X POST http://localhost:8000/api/v1/ifrs17/bba \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool

# Interactive OpenAPI docs
open http://localhost:8000/docs
```

---

## Example: Monte Carlo UQ on a Reinsurance Deal

```python
from polaris_re.analytics.uq import MonteCarloUQ, UQParameters

# Run 1000 scenarios with perturbed mortality, lapse, and discount rates
uq = MonteCarloUQ(
    inforce=block,
    base_assumptions=assumptions,
    base_config=config,
    treaty=treaty,            # YRT, coinsurance, modco, or None for standalone
    hurdle_rate=0.10,
    n_scenarios=1000,
    seed=42,
    params=UQParameters(mortality_log_sigma=0.10, lapse_log_sigma=0.15),
)
result = uq.run()

print(f"Base PV Profit:  ${result.base_pv_profit:,.0f}")
print(f"95% VaR:         ${result.var(0.95):,.0f}")
print(f"95% CVaR:        ${result.cvar(0.95):,.0f}")
print(f"P10/P50/P90 PV:  {result.percentile(10)['pv_profit']:,.0f} / "
      f"{result.percentile(50)['pv_profit']:,.0f} / "
      f"{result.percentile(90)['pv_profit']:,.0f}")
```

---

## Project Structure

```
polaris-re/
├── CLAUDE.md              ← Claude Code build instructions (read before every session)
├── ARCHITECTURE.md        ← System design, data flow, actuarial formulas
├── Dockerfile             ← Multi-stage build: builder → runtime → dev
├── docker-compose.yml     ← Services: dev shell, api pod, JupyterLab
├── .devcontainer/
│   └── devcontainer.json  ← GitHub Codespaces configuration
├── .github/
│   └── workflows/ci.yml   ← GitHub Actions: lint → test (3.12/3.13) → docker → coverage
├── docs/
│   ├── QUICKSTART.md      ← Setup guide: local, Docker, Codespaces, API, tables
│   ├── ROADMAP.md         ← Phased feature plan with milestone checklists
│   ├── DECISIONS.md       ← Architecture decision records (ADRs 001–032)
│   └── ACTUARIAL_GLOSSARY.md  ← Domain terminology reference
├── src/polaris_re/
│   ├── core/              ← Policy, InforceBlock, ProjectionConfig, CashFlowResult
│   ├── assumptions/       ← Mortality, improvement, lapse, morbidity
│   ├── products/          ← Term, Whole Life, UL, Disability/CI
│   ├── reinsurance/       ← YRT, Coinsurance, Modco, Stop Loss
│   ├── analytics/         ← Profit testing, scenarios, UQ, IFRS 17, stochastic rates,
│   │                         experience studies
│   ├── api/               ← FastAPI application
│   ├── dashboard/         ← Streamlit dashboard
│   ├── utils/             ← Table loaders, interpolation, date utilities
│   └── cli.py             ← Typer CLI entry point
├── tests/                 ← 439 tests, 94% coverage
├── notebooks/
│   └── 01_term_life_yrt_pricing.ipynb  ← End-to-end validation notebook
├── scripts/
│   ├── convert_soa_tables.py     ← Download/convert SOA VBT 2015, CSO 2001, CIA 2014
│   ├── validate_tables.py        ← Validate mortality CSV files
│   └── generate_synthetic_block.py  ← Generate test inforce data
└── pyproject.toml
```

---

## Architecture Overview

```
InforceBlock (N policies)
    │
    ├── AssumptionSet ─── MortalityTable (VBT 2015 / CIA 2014 / CSO 2001)
    │                ├─── MortalityImprovement (Scale AA / MP-2020 / CPM-B)
    │                └─── LapseAssumption (select + ultimate)
    ├── ProjectionConfig (horizon, discount rate, time step)
    │
    └──► BaseProduct.project()
              └──► CashFlowResult [GROSS]  (N×T arrays: premiums, claims, reserves)
                        │
                        └──► BaseTreaty.apply()
                                  ├──► CashFlowResult [NET]
                                  └──► CashFlowResult [CEDED]
                                            │
                                            ├──► ProfitTester   → IRR, PV profits, margin
                                            ├──► ScenarioRunner → stress scenario table
                                            ├──► MonteCarloUQ   → VaR, CVaR, percentiles
                                            └──► IFRS17         → BEL, RA, CSM schedule
```

---

## Mortality Table Data

Polaris RE supports three standard North American mortality tables.
The conversion script handles downloading and formatting automatically.

```bash
# Install conversion dependencies
uv sync --extra tables

# Download SOA VBT 2015 and 2001 CSO directly from mort.soa.org
uv run python scripts/convert_soa_tables.py \
  --source pymort --output-dir data/mortality_tables

# Convert CIA 2014 from downloaded Excel workbook (222040T1e.xlsx from cia-ica.ca)
uv run python scripts/convert_soa_tables.py \
  --source excel \
  --excel-file ~/Downloads/222040T1e.xlsx \
  --output-dir data/mortality_tables

# Validate all 10 required CSVs
uv run python scripts/convert_soa_tables.py \
  --validate-only --output-dir data/mortality_tables
```

| Table | Source | Script path |
|---|---|---|
| SOA VBT 2015 (M/F × NS/S) | mort.soa.org IDs 3265–3268 | `--source pymort` |
| 2001 CSO (M/F composite) | mort.soa.org IDs 1136, 1139 | `--source pymort` |
| CIA 2014 (M/F × NS/S) | cia-ica.ca → `222040T1e.xlsx` | `--source excel` |

---

## Development

### Prerequisites

- Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker (for `make docker-build` / `make docker-test`)

### Environment

```bash
uv sync --all-extras     # installs dev + api + ml + tables extras
cp .env.example .env     # set POLARIS_DATA_DIR to your table directory
make lint                # ruff + mypy
make test                # fast test suite
make coverage            # full suite with HTML report → htmlcov/index.html
```

### CI Pipeline

GitHub Actions runs on every push and PR:
1. **lint** — Ruff (style + formatting) + mypy (strict)
2. **test** — pytest matrix: Python 3.12 and 3.13
3. **docker** — multi-stage image build + test run inside container
4. **coverage** — upload to Codecov (main branch only)

---

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for the complete build specification and session workflow.
See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for local and Codespace setup.

## License

MIT

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
- ✅ **IFRS 17** — BBA, PAA, and VFA measurement plus the period-to-period movement table
- ✅ **Return-on-capital** — LICAT (Canada), US RBC, and EU Solvency II SCR are all selectable for return-on-capital on the CLI (`--capital`), REST API (`capital_model`), Streamlit dashboard (capital-basis selector), and the deal-pricing Excel workbook (jurisdiction-labelled capital block)
- ✅ **Statutory reserves** — reproduce the cedant's basis (CRVM, VM-20) alongside net-premium
- ✅ **Validated** — an executable **validation & benchmark pack** reproduces authoritative actuarial references (SOA Illustrative Life Table APVs / premiums, constant-force closed forms, a continuous-force textbook identity) to machine precision; run it headless with `polaris benchmark` (non-zero exit on any FAIL, so it can gate CI). This is the executable evidence behind the "credible alternative to AXIS / Prophet" claim.

---

## Status

Phases 1–5 (capital, portfolio & IFRS 17 production) are substantially complete,
Phase 6 (operationalisation & ecosystem) is largely done, and Phase 7 (agent
access — an in-process MCP server) is complete. 2,730+ tests, coverage ≥ 90%
enforced in CI, ADRs through ADR-174. See [`docs/ROADMAP.md`](docs/ROADMAP.md)
for the milestone-level breakdown.

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
| `products/` | Per-policy substandard rating — mortality multiplier + flat extra | ✅ |
| `core/` | Reserve-basis matching — NET_PREMIUM, CRVM (Full Preliminary Term), VM-20 simplified for Term + Whole Life; GAAP (FAS 60) for Term | ✅ |
| `reinsurance/` | YRT — NAR-based premiums, ceded claims | ✅ |
| `reinsurance/` | Coinsurance — proportional split, reserve transfer | ✅ |
| `reinsurance/` | Modco — cedant retains assets, modco interest | ✅ |
| `reinsurance/` | Stop Loss — aggregate cover, attachment/exhaustion, pro-ration | ✅ |
| `analytics/` | Profit Testing — IRR, PV profits, break-even, margin | ✅ |
| `analytics/` | Premium Sufficiency — PV loss/expense/combined ratios, sufficiency verdict | ✅ |
| `analytics/` | Scenario Analysis — 6 standard stress scenarios; reinsurer/cedant perspective | ✅ |
| `analytics/` | Monte Carlo UQ — LogNormal/Normal sampling, VaR, CVaR | ✅ |
| `analytics/` | IFRS 17 — BBA (BEL/RA/CSM), PAA (LRC/LIC), VFA; period-to-period **movement table** by annual cohort | ✅ |
| `analytics/` | Stochastic Rates — Hull-White one-factor, CIR | ✅ |
| `analytics/` | Experience Studies — A/E, limited-fluctuation credibility, blended rates | ✅ |
| `analytics/` | Portfolio aggregation — multi-deal runner, concentration/HHI, calendar alignment, portfolio scenarios | ✅ |
| `analytics/` | Regulatory capital — LICAT (C-1/C-2/C-3 + lapse/morbidity) → return-on-capital | ✅ |
| `analytics/` | Regulatory capital — US NAIC Life RBC + shared `CapitalModel` protocol; drives return-on-capital | ✅ module + RoC + CLI/API/dashboard/Excel selector + RBC ratio (`capital_ratio`) surfaced on CLI/API/Excel/dashboard |
| `analytics/` | Regulatory capital — EU Solvency II SCR (standard-formula correlation-matrix BSCR + risk margin) | ✅ module + CLI/API/dashboard/Excel selector + solvency ratio (`capital_ratio`) surfaced on CLI/API/Excel/dashboard |
| `analytics/` | YRT rate schedule generator — flat + per-duration solve to a target IRR | ✅ |
| `analytics/` | Validation & benchmark pack — reproduce published/closed-form actuarial references (SOA Illustrative Life Table, constant-force identities); scored pass/fail report via `polaris benchmark` + `05_validation_report.ipynb` | ✅ |
| `assumptions/` | ML-enhanced mortality & lapse (scikit-learn / XGBoost), same protocol as table-based | ✅ |
| `utils/` | Cedant inforce data ingestion — YAML-driven mapping, data-quality report | ✅ |
| `api/` | REST API — FastAPI with full OpenAPI docs (price, scenario, uq, ifrs17 bba/paa/movement, portfolio, ingest, rate-schedule) | ✅ |
| `cli.py` | CLI — `price / scenario / uq / portfolio / rate-schedule / ingest / validate / benchmark / version`; `price --excel-out` (committee workbook), `--reserve-basis {NET_PREMIUM,CRVM,VM20,GAAP}` (GAAP: Term), `--capital {licat,rbc,solvency2}` (RoC); `benchmark` runs the actuarial validation pack (exit ≠ 0 on any FAIL) | ✅ |
| `dashboard/` | Streamlit dashboard — pricing, scenarios, Monte Carlo, portfolio | ✅ |
| `mcp/` | MCP server — in-process, read-only pricing tools (`polaris_price_block` / `polaris_price` / `polaris_run_scenario` / `polaris_run_uq`) + `polaris://capabilities` for Claude Code / Claude Desktop; stdio default, optional streamable-HTTP; committed 10-question eval set | ✅ |

---

## Quick Start

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for the full setup guide including Docker, Codespaces, mortality table loading, API testing, `--excel-out` usage, and `--capital {licat,rbc,solvency2}` for return-on-capital under the Canadian, US, or EU standard ([§10](docs/QUICKSTART.md#10-regulatory-capital--return-on-capital)).

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

# Write a committee-grade Excel workbook alongside the JSON result
uv run polaris price \
  -c my_deal.json \
  -i my_block.csv \
  -o result.json \
  --excel-out deal.xlsx

# Add regulatory capital + return-on-capital metrics (ADR-049/101). Choose
# the jurisdiction: licat (Canada), rbc (US NAIC), or solvency2 (EU SCR).
# The flag is opt-in; when absent (or with --capital licat) the JSON /
# console / Excel output is byte-identical to a vanilla run.
uv run polaris price \
  -c my_deal.json \
  -i my_block.csv \
  -o result.json \
  --excel-out deal.xlsx \
  --capital solvency2
```

Set `POLARIS_PARITY_DEBUG=1` to dump year-by-year cash flow CSVs (gross / net /
ceded) to `data/outputs/parity/`. Override the location with
`POLARIS_PARITY_OUTPUT=<path>`.

### Validation & benchmark pack

`polaris benchmark` reproduces authoritative actuarial reference values (the SOA
Illustrative Life Table whole-life APVs / premiums, constant-force closed forms,
and a continuous-force textbook identity) and renders a diligence-grade pass/fail
table. It needs no config or data — the references are cited constants and
identities. It **exits non-zero on any FAIL**, so it can gate a CI job.

```bash
uv run polaris benchmark                     # full pack (all categories), pretty table
uv run polaris benchmark --pack deck         # just the SOA Illustrative Life Table cases
uv run polaris benchmark -o report.md        # export the Markdown report
uv run polaris benchmark --json report.json  # export the structured results
```

`notebooks/05_validation_report.ipynb` renders the same report with its diligence
checks embedded as executable assertions.

See [`docs/QUICKSTART.md §9`](docs/QUICKSTART.md#9-deal-pricing--excel-export) for the full
`polaris price` command reference, workbook contents, and mixed-cohort filename behaviour.

### Performance & scale

The engine vectorizes over policies — a block projects as `(N × T)` NumPy arrays
with no Python loop over policies — so projection time grows **linearly** with the
block size. Measured on one core, projecting a synthetic TERM block over a 20-year
monthly horizon:

| Policies | Projection time | Policies / sec |
|---------:|----------------:|---------------:|
| 1,000    | 0.06 s          | ~17,000        |
| 10,000   | 0.63 s          | ~16,000        |
| 100,000  | 11.4 s          | ~8,800         |
| 500,000  | 66.2 s          | ~7,500         |

Half a million policies price in about a minute on a single core (peak ~10 GB RAM).
Regenerate the table on your own hardware — see [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md):

```bash
uv run python scripts/scale_benchmark.py --sizes 1000 10000 100000 500000
```

**Regression guard.** A CI `perf` job runs `scripts/perfbench.py` on every pull
request: it probes the engine's hot path on the PR head **and** on an
`origin/main` git-worktree checkout in the same job, so machine noise cancels in
the head/main ratio. It **gates the merge only on a structural regression**
(mismatched policy/month counts or a changed output fingerprint — a *hard
delta*); the wall-time ratio and peak-memory delta are advisory alerts printed to
the log, never a build failure (deterministic metrics gate, raw wall-time only
informs). The machine-readable `perf.json` — verdict first, then both per-branch
reports — is uploaded as a build artifact. Run it locally with:

```bash
uv run python scripts/perfbench.py --ref origin/main -o perf.json   # exits non-zero on a hard delta
```

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

## Example: Connect an AI agent (MCP)

Polaris RE ships an **in-process [MCP](https://modelcontextprotocol.io) server** so
an actuary can drive the engine conversationally from Claude Code / Claude Desktop —
"price the `golden` block YRT 90% at 6% discount, valuation 2025-01-01, then stress
mortality +10% and show me the reinsurer IRR delta". The tools are **read-only** and
call the same in-process engine path as the CLI and REST API (no HTTP proxy, works
offline). A committed `.mcp.json` at the repo root registers it for a cloned checkout
with no manual `claude mcp add`:

```bash
uv sync --extra mcp                       # pre-warm the venv
uv run polaris-mcp                        # run the stdio server directly (Ctrl-C to stop)

# Smoke-test every tool in a browser UI, no Claude needed:
npx @modelcontextprotocol/inspector -- uv run polaris-mcp
```

Tools: `polaris_price_block` (price a named sample block or an inforce CSV),
`polaris_price` (inline policies), `polaris_run_scenario` (standard stress set),
`polaris_run_uq` (Monte-Carlo profit bands) — plus a `polaris://capabilities` resource
listing the valid product/treaty/capital/reserve enums. Every tool requires an explicit
`valuation_date` so quotes are reproducible, and output is compact by default
(`detail=true` for the full per-year arrays). An optional streamable-HTTP transport
(`--transport http`) reuses the REST API's `POLARIS_API_KEYS` auth for shared
deployments. See [QUICKSTART §10](docs/QUICKSTART.md) for the full connect-and-verify
walkthrough. A committed 10-question eval set (`polaris_re.mcp.evals`) is a green golden
regression on the tool surface.

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
│   ├── QUICKSTART.md      ← Setup guide: local, Docker, Codespaces, API, tables, Excel export
│   ├── ROADMAP.md         ← Phased feature plan with milestone checklists
│   ├── DECISIONS.md       ← Architecture decision records (ADRs 001–174)
│   └── ACTUARIAL_GLOSSARY.md  ← Domain terminology reference
├── src/polaris_re/
│   ├── core/              ← Policy, InforceBlock, ProjectionConfig, CashFlowResult, ReserveBasis
│   ├── assumptions/       ← Mortality, improvement, lapse, morbidity, ML mortality/lapse
│   ├── products/          ← Term, Whole Life, UL, Disability/CI
│   ├── reinsurance/       ← YRT, Coinsurance, Modco, Stop Loss
│   ├── analytics/         ← Profit testing, premium sufficiency, scenarios, UQ, IFRS 17
│   │                         (incl. movement table), stochastic rates, experience studies,
│   │                         portfolio aggregation, regulatory capital (LICAT, RBC, Solvency II),
│   │                         YRT rate schedule
│   ├── services/          ← Engine-invocation composition root (run_price) shared by every host
│   ├── api/               ← FastAPI application
│   ├── mcp/               ← In-process MCP server (agent access) + committed eval set
│   ├── dashboard/         ← Streamlit dashboard
│   ├── utils/             ← Table loaders, interpolation, date utilities, Excel writer, ingestion
│   └── cli.py             ← Typer CLI entry point
├── tests/                 ← 2,730+ tests, coverage ≥ 90% (CI-enforced)
├── notebooks/
│   ├── 01_term_life_yrt_pricing.ipynb        ← End-to-end YRT deal-pricing walkthrough
│   ├── 02_reserve_basis_comparison.ipynb     ← CRVM / VM-20 / GAAP reserve-basis comparison
│   ├── 03_capital_standards_comparison.ipynb ← LICAT / RBC / Solvency II capital comparison
│   ├── 04_alm_duration_gap.ipynb             ← Asset-liability duration gap + closed-form validation
│   └── 05_validation_report.ipynb            ← Validation & benchmark pack — pass/fail report vs published references
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
                                            ├──► IFRS17         → BEL, RA, CSM schedule
                                            └──► ExcelWriter    → committee deal workbook
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

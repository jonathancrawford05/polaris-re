# Polaris RE — Quick Start Guide

This guide covers four paths to get Polaris RE running and tested:

1. [Local Setup](#1-local-setup) — native Python on your machine
2. [GitHub Codespaces](#2-github-codespaces) — zero-install cloud environment
3. [Docker API Server](#3-docker-api-server) — simulate a deployed reinsurance pricing pod
4. [Mortality Tables](#4-mortality-tables) — loading real actuarial data
5. [Lapse Tables](#5-lapse-tables) — loading lapse assumption CSVs
6. [Cedant Inforce Ingestion](#6-cedant-inforce-data-ingestion) — normalising raw cedant data
7. [ML-Enhanced Assumptions](#7-ml-enhanced-assumptions) — training ML mortality/lapse models
8. [YRT Rate Schedule](#8-yrt-rate-schedule-generation) — generating reinsurer rate tables

---

## 1. Local Setup

### Prerequisites

- Python 3.12+ (check: `python3 --version`)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # or restart shell
```

### Install and verify

```bash
git clone https://github.com/jonathancrawford05/polaris-re.git
cd polaris-re

# Install all dependencies (dev + api + ml + tables extras)
uv sync --all-extras

# Verify the install
uv run python -c "import polaris_re; print(polaris_re.__version__)"
```

### Environment variables

```bash
cp .env.example .env
```

Edit `.env` and set `POLARIS_DATA_DIR` to the directory where you will store
mortality table CSVs (e.g. `POLARIS_DATA_DIR=/path/to/polaris-re/data`).

### Run the test suite

```bash
make test          # fast suite — excludes @slow marks (~30 seconds)
make test-all      # full suite including slow tests
make coverage      # full suite + HTML report → htmlcov/index.html
make lint          # ruff check + mypy strict
```

Expected outcome: **533 tests pass, 90%+ coverage**.

### CLI quick smoke test

```bash
uv run polaris version
uv run polaris price       # demo pricing run with Rich output
uv run polaris scenario    # scenario analysis
uv run polaris uq          # Monte Carlo UQ (200 scenarios by default)
uv run polaris rate-schedule  # YRT rate schedule generation
```

### Validation notebook

```bash
make notebook
# Opens JupyterLab at http://localhost:8888
# Open notebooks/01_term_life_yrt_pricing.ipynb
```

---

## 2. GitHub Codespaces

The repo includes a `.devcontainer/devcontainer.json` that configures Codespaces
automatically. No local software installation is required.

### Starting a Codespace

1. Go to [github.com/jonathancrawford05/polaris-re](https://github.com/jonathancrawford05/polaris-re)
2. Click **Code → Codespaces → New codespace**
3. Wait for the container to build (first time ~3–4 minutes)

The `postCreateCommand` runs `uv sync --frozen --all-extras` automatically,
so all dependencies are installed when the terminal opens.

### What's pre-configured

| Feature | Detail |
|---|---|
| Python interpreter | `/workspaces/polaris-re/.venv/bin/python` (auto-selected) |
| VS Code extensions | Ruff, Pylance, pytest explorer, coverage-gutters, Jupyter, Docker |
| Ports forwarded | 8000 (FastAPI), 8501 (Streamlit), 8888 (JupyterLab) |
| Docker-in-Docker | Enabled — `make docker-build` and `make docker-test` work |
| `.venv` activation | Added to `.bashrc` — `python` and `pytest` work without `uv run` |

### First commands in the Codespace terminal

```bash
# Confirm environment
python -c "import polaris_re; print(polaris_re.__version__)"

# Run fast tests (native, no Docker)
make test

# Run full test suite + coverage
make coverage

# Lint
make lint

# Full Docker CI mirror (builds image and runs all tests inside it)
make docker-build
make docker-test
```

### Subsequent Codespace sessions

Codespaces persist your environment between sessions. On resume, the
`postStartCommand` re-activates the `.venv` in `.bashrc`. Simply open the
terminal and run commands as above.

---

## 3. Docker API Server

This simulates Polaris RE deployed as a pricing pod — exactly how an actuarial
team would call the engine from downstream systems, reports, or notebooks.

### Prerequisites

- Docker installed and running
- The Docker image built (`make docker-build`)

### Build the image (first time, or after code changes)

```bash
make docker-build
# Expected: Successfully tagged polaris-re:dev
# Runtime smoke tests print: polaris_re 0.1.0 OK
```

### Start the API server (persistent, port-bound container)

```bash
docker compose up api
```

You will see:
```
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
api-1  | INFO:     Application startup complete.
```

The container stays running until you stop it. Port 8000 is forwarded to your
host (or automatically forwarded in Codespaces).

### Call the API

In a second terminal (or from your Mac if running in Codespaces with port forwarding):

```bash
# Health check
curl http://localhost:8000/health

# OpenAPI Swagger UI (browser)
open http://localhost:8000/docs   # macOS
# or visit http://localhost:8000/docs in your browser

# Price a deal using the sample fixture (3-policy mixed block)
curl -s -X POST http://localhost:8000/api/v1/price \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool

# Scenario analysis
curl -s -X POST http://localhost:8000/api/v1/scenario \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool

# Monte Carlo UQ
curl -s -X POST http://localhost:8000/api/v1/uq \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool

# IFRS 17 BBA measurement
curl -s -X POST http://localhost:8000/api/v1/ifrs17/bba \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool

# IFRS 17 PAA measurement
curl -s -X POST http://localhost:8000/api/v1/ifrs17/paa \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool
```

### Call the API from Python

```python
import httpx, json

BASE = "http://localhost:8000"

with open("tests/fixtures/sample_price_request.json") as f:
    payload = json.load(f)

# Pricing
r = httpx.post(f"{BASE}/api/v1/price", json=payload)
result = r.json()
print(f"IRR:           {result['irr']:.2%}")
print(f"PV Profits:    ${result['pv_profits']:,.0f}")
print(f"Profit Margin: {result['profit_margin']:.2%}")

# Scenario analysis
r = httpx.post(f"{BASE}/api/v1/scenario", json=payload)
for s in r.json()["scenarios"]:
    print(f"{s['scenario_name']:25s}  IRR={s['irr'] or 0:.2%}  Margin={s['profit_margin']:.2%}")
```

### Available API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/version` | Package version info |
| `GET` | `/docs` | Interactive Swagger UI |
| `GET` | `/redoc` | ReDoc API reference |
| `POST` | `/api/v1/price` | Full pricing pipeline — IRR, NPV, margin |
| `POST` | `/api/v1/scenario` | 6 standard stress scenarios |
| `POST` | `/api/v1/uq` | Monte Carlo UQ — VaR, CVaR, percentiles |
| `POST` | `/api/v1/ifrs17/bba` | IFRS 17 Building Block Approach |
| `POST` | `/api/v1/ifrs17/paa` | IFRS 17 Premium Allocation Approach |
| `POST` | `/api/v1/ingest` | Ingest raw cedant inforce data |
| `POST` | `/api/v1/rate-schedule` | Generate YRT rate schedule |

### Container management

```bash
docker compose up api           # start in foreground (Ctrl+C to stop)
docker compose up -d api        # start in background
docker compose logs api         # view logs when running in background
docker compose restart api      # restart after code changes
docker compose ps               # check container status and health
docker compose down             # stop and remove container
```

### Run all tests inside Docker (CI mirror)

```bash
make docker-test
# Equivalent to CI job 3: builds image, runs 439 tests, tears down
```

### Start the Streamlit dashboard

```bash
docker compose run --rm dev \
  uv run streamlit run src/polaris_re/dashboard/app.py \
  --server.address 0.0.0.0 --server.port 8501
# Then open http://localhost:8501
```

---

## 4. Mortality Tables

The API demo endpoints use a synthetic flat mortality rate and will work without
real tables. To use `MortalityTable.load()` with production-grade assumptions,
you need 10 CSV files in `$POLARIS_DATA_DIR/mortality_tables/`.

### Install conversion dependencies

```bash
uv sync --extra tables   # adds pymort, openpyxl, pandas
```

### Step 1 — SOA VBT 2015 and 2001 CSO (automated)

Downloads directly from [mort.soa.org](https://mort.soa.org) via the pymort library.
No manual download required.

```bash
uv run python scripts/convert_soa_tables.py \
  --source pymort \
  --output-dir data/mortality_tables
```

This writes 6 files:

| File | Table | Source ID |
|---|---|---|
| `soa_vbt_2015_male_ns.csv` | SOA VBT 2015 Male Non-Smoker ANB | 3265 |
| `soa_vbt_2015_male_smoker.csv` | SOA VBT 2015 Male Smoker ANB | 3266 |
| `soa_vbt_2015_female_ns.csv` | SOA VBT 2015 Female Non-Smoker ANB | 3267 |
| `soa_vbt_2015_female_smoker.csv` | SOA VBT 2015 Female Smoker ANB | 3268 |
| `cso_2001_male.csv` | 2001 CSO Male Composite Ultimate ANB | 1136 |
| `cso_2001_female.csv` | 2001 CSO Female Composite Ultimate ANB | 1139 |

### Step 2 — CIA 2014 (manual Excel download required)

The CIA 2014 tables are not on mort.soa.org. Download the tables workbook from
the Canadian Institute of Actuaries:

**URL:** `https://www.cia-ica.ca/publications/rp222040t1e/`

Download the Excel workbook (`222040T1e.xlsx`), then convert it:

```bash
uv run python scripts/convert_soa_tables.py \
  --source excel \
  --excel-file ~/Downloads/222040T1e.xlsx \
  --output-dir data/mortality_tables
```

This writes 4 files using sheets `MnsN`, `MsmN`, `FnsN`, `FsmN`
(N suffix = Age Nearest Birthday, select period = 20 years):

| File | Sheet | Description |
|---|---|---|
| `cia_2014_male_ns.csv` | `MnsN` | CIA 2014 Male Non-Smoker ANB |
| `cia_2014_male_smoker.csv` | `MsmN` | CIA 2014 Male Smoker ANB |
| `cia_2014_female_ns.csv` | `FnsN` | CIA 2014 Female Non-Smoker ANB |
| `cia_2014_female_smoker.csv` | `FsmN` | CIA 2014 Female Smoker ANB |

### Step 3 — Validate all 10 files

```bash
uv run python scripts/convert_soa_tables.py \
  --validate-only \
  --output-dir data/mortality_tables
```

Expected output — all 10 rows showing `OK`, with:
- VBT 2015: 78 ages, 26 rate columns, max q_x ≈ 0.5
- CSO 2001: 121 ages, 1 rate column, max q_x ≈ 1.0 at age 120
- CIA 2014: 73 ages, 21 rate columns, max q_x in typical mortality range

### CSV schema reference

**Select-and-ultimate tables** (VBT 2015, CIA 2014):
```
age, dur_1, dur_2, ..., dur_N, ultimate
18, 0.000130, 0.000148, ..., 0.000195, 0.000210
...
```
- `age` = issue age (ANB), integers from 18 upward
- `dur_1..dur_N` = annual q_x rates during select period, as decimals
- `ultimate` = annual q_x rate after select period elapses

**Ultimate-only tables** (2001 CSO):
```
age, rate
0, 0.00352
1, 0.00089
...
120, 1.0
```

### Debugging a CIA Excel file

If you have a different CIA workbook and the converter fails, use the inspect
flag to see the actual sheet names and column layout:

```bash
uv run python scripts/convert_soa_tables.py --inspect ~/Downloads/myfile.xlsx
```

---

## 5. Lapse Tables

Lapse assumptions can be loaded from CSV files, mirroring the mortality table
workflow.

### Lapse CSV schema

```
policy_year,rate
1,0.12
2,0.10
3,0.08
...
```

Each row is one policy year with the annual lapse rate as a decimal.

### Convert SOA LLAT 2014 tables

```bash
uv run python scripts/convert_lapse_tables.py \
  --source llat \
  --input-file ~/Downloads/llat_2014.xlsx \
  --output-dir data/lapse_tables
```

### Load lapse assumptions in code

```python
from polaris_re.assumptions.lapse import LapseAssumption

lapse = LapseAssumption.load("my_lapse_table.csv", data_dir=Path("data"))
```

---

## 6. Cedant Inforce Data Ingestion

Normalise raw cedant CSV files into the Polaris RE schema using a YAML mapping
config.

### Create a YAML mapping file

```yaml
source_format:
  delimiter: ","
  date_format: "%Y-%m-%d"
column_mapping:
  policy_id: "POLNUM"
  issue_age: "AGE_AT_ISSUE"
  sex: "GENDER"
  face_amount: "SUM_ASSURED"
  annual_premium: "ANNUAL_PREM"
code_translations:
  sex:
    M: "M"
    MALE: "M"
    F: "F"
defaults:
  underwriting_class: "STANDARD"
```

### Run ingestion

```bash
# CLI
uv run polaris ingest --config mapping.yaml --output normalised.csv raw_cedant.csv

# Python
from polaris_re.core.inforce import InforceBlock
block = InforceBlock.from_csv("normalised.csv")
```

---

## 7. ML-Enhanced Assumptions

Train ML models (scikit-learn / XGBoost) that serve as drop-in replacements
for table-based mortality and lapse assumptions.

### Train a mortality model

```bash
uv run python scripts/train_ml_assumptions.py \
  --data inforce_with_claims.csv \
  --output-dir models/ \
  --model-type gradient_boosting
```

### Use ML assumptions in code

```python
from polaris_re.assumptions.ml_mortality import MLMortalityAssumption
from polaris_re.assumptions.assumption_set import AssumptionSet

ml_mort = MLMortalityAssumption.load("models/mortality_model.joblib")
assumptions = AssumptionSet(mortality=ml_mort, lapse=lapse, version="ml-v1")
# Use exactly like table-based assumptions in any projection
```

### Feature engineering

```python
from polaris_re.utils.features import build_feature_matrix

features = build_feature_matrix(
    ages=ages, sexes=sexes, smoker_statuses=smokers,
    durations_months=durations, face_amounts=faces,
)
```

---

## 8. YRT Rate Schedule Generation

Generate the actual deliverable reinsurers send cedants: a table of YRT rates
per $1,000 NAR by age, sex, and smoker status.

### CLI

```bash
uv run polaris rate-schedule --target-irr 0.10 --ages 25-65
```

### Python

```python
from polaris_re.analytics.rate_schedule import YRTRateSchedule

scheduler = YRTRateSchedule(assumptions=assumptions, config=config, target_irr=0.10)
df = scheduler.generate(ages=[30, 40, 50], sexes=[Sex.MALE], smoker_statuses=[SmokerStatus.UNKNOWN])
print(df)
```

### Excel export

```python
from polaris_re.utils.excel_output import write_rate_schedule_excel
write_rate_schedule_excel(df, "rates.xlsx")
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `uv: command not found` | uv not on PATH | `source $HOME/.local/bin/env` or restart shell |
| `Import "polaris_re" could not be resolved` | Venv not activated | `source .venv/bin/activate` or use `uv run` |
| `POLARIS_DATA_DIR not set` | Missing env var | Copy `.env.example` to `.env` and set the path |
| `No table loaded for sex=F, smoker=NS` | Real tables not loaded | API demo uses flat synthetic rates — this is expected without real tables |
| `docker: executable not found` | Docker not installed/running | Start Docker Desktop |
| `uv run` fails in Docker | uv not in runtime image | Use `python -m pytest` directly (as per Makefile) |
| `curl: (7) Failed to connect` | API container not running | Run `docker compose up api` first |
| `GET / → 404` in browser | No root route defined | Navigate to `/docs` for the Swagger UI |

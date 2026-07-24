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
9. [Deal Pricing & Excel Export](#9-deal-pricing--excel-export) — `polaris price` with `--excel-out`

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
uv run polaris benchmark   # actuarial validation pack (reference reproduction, exit ≠ 0 on FAIL)
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

# IFRS 17 analysis-of-change (movement) table — annual issue-year cohorts
curl -s -X POST http://localhost:8000/api/v1/ifrs17/movement \
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
| `POST` | `/api/v1/ifrs17/movement` | IFRS 17 analysis-of-change (movement) table by annual cohort |
| `POST` | `/api/v1/portfolio` | Multi-deal portfolio run — aggregate IRR/PV, concentration |
| `POST` | `/api/v1/portfolio/scenarios` | Portfolio run under the standard stress scenarios |
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
# Equivalent to CI job 3: builds image, runs the full test suite (1,500+), tears down
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
# Optional value coercion (all default to a no-op if omitted):
unit_scale:
  face_amount: 1000.0        # face reported in thousands → dollars
premium_mode: "annual"       # or monthly / quarterly / semiannual (annualised)
currency:
  code: "CAD"                # static FX: reporting = source × rate
  rate: 0.75
date_columns:                # coerce mixed date formats to canonical ISO
  - issue_date
  - valuation_date
date_formats:                # optional explicit format per column
  issue_date: "%d/%m/%Y"     # forces EU order + suppresses the ambiguity warning
```

### Run ingestion

```bash
# CLI
uv run polaris ingest --config mapping.yaml --output normalised.csv raw_cedant.csv

# Python
from polaris_re.core.inforce import InforceBlock
block = InforceBlock.from_csv("normalised.csv")
```

### Messy files — quarantine instead of abort

Real cedant extracts have bad rows (missing cells, non-positive face/premium,
unparseable dates) mixed in with usable ones. Ingestion is **best-effort**: it
coerces messy *values*, prices the usable rows, and quarantines the rest instead
of failing the whole block.

```bash
uv run polaris ingest \
  --config mapping.yaml \
  --output clean.csv \
  --rejects clean.rejects.csv \      # default: <output>.rejects.csv; only written if rows are rejected
  --max-reject-pct 5 \               # optional: hard-fail (exit 1) if > 5% of rows are rejected
  raw_cedant.csv
```

The summary reports rows examined / clean / rejected with a per-reason
breakdown; `clean.csv` holds the priceable block (values coerced) and
`clean.rejects.csv` holds each dropped row with a `_reject_reason` column
listing every rule it failed. Without `--max-reject-pct`, the command ingests
whatever is usable and exits 0. When `--max-reject-pct` is breached the command
exits 1 and **still writes the rejects file** (so you can see which rows failed)
but **withholds the clean output** — a breach means the mapping is probably wrong,
so no clean block is emitted for a downstream step to consume. `--validate-only`
reports without writing either file.

The same behaviour is available on the API: `POST /api/v1/ingest` accepts the
coercion fields in its `mapping` object and returns `n_input` / `n_rejected` /
`reject_reasons` and a `rejects` list alongside the clean `policies`.

### Reject-reason catalogue

Each rejected row's `_reject_reason` is a `"; "`-joined list of every rule it
failed; the report's `reject_reasons` counts each rule independently (so the
counts can sum to more than the rejected-row total when a row fails several
rules). The rules are the closed set below — the reason strings are the
authoritative names emitted by `_row_rules()` / `_date_reject_rules()` in
`utils/ingestion.py` (single source of truth; this table mirrors them).

| `_reject_reason` | Triggers when | Typical cause → fix |
|------------------|---------------|---------------------|
| `missing_<field>` | a required cell is null/empty (one reason per field, e.g. `missing_issue_age`, `missing_face_amount`) | source column unmapped or misnamed → check `column_mapping` covers that field; or the cell is genuinely blank in the extract |
| `non_positive_face_amount` | `face_amount` ≤ 0 | sentinel value (0, −1, −999), face mapped to the wrong column, or a unit left unapplied → verify `column_mapping` + `unit_scale` |
| `non_positive_premium` | `annual_premium` ≤ 0 | sentinel, wrong column, or a genuinely paid-up policy (0 premium) → verify mapping; paid-up blocks need separate handling |
| `negative_issue_age` / `negative_attained_age` | the age is < 0 | sentinel or parse error in the age column → check the source values |
| `attained_before_issue` | `attained_age` < `issue_age` | transposed age columns in the mapping, or a data error → fix the mapping / correct the record |
| `unparseable_<col>` | a non-empty `issue_date` / `valuation_date` string matches no known format (ISO, US `MM/DD/YYYY`, EU `DD/MM/YYYY`, `YYYY/MM/DD`, or Excel serial) | an exotic date format or free-text ("N/A", "unknown") → set `date_formats['<col>']` to the explicit format; if it is free text, the row is genuinely bad |

Required fields (any of which can raise `missing_<field>`): `policy_id`,
`issue_age`, `attained_age`, `sex`, `smoker_status`, `face_amount`,
`annual_premium`, `product_type`, `duration_inforce`, `issue_date`,
`valuation_date`.

Because `missing_<field>` names the offending column, a high count against a
single field (e.g. `missing_face_amount: 9,812`) usually points at one wrong
`column_mapping` line rather than dirty data — the fastest signal that a mapping,
not the extract, needs fixing.

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

## 9. Deal Pricing & Excel Export

`polaris price` runs the full deal pricing pipeline — InforceBlock → AssumptionSet →
Product → Treaty → ProfitTester — and outputs Rich terminal tables plus a JSON
result file. The `--excel-out` flag (added in ADR-046, Slice 2) additionally writes
a formatted committee-grade Excel workbook for each priced cohort.

### Command reference

```
polaris price [OPTIONS]

Options:
  -c, --config PATH        Pricing config JSON file (mortality/lapse/deal blocks).
  -i, --inforce PATH       Inforce CSV file. Overrides any 'policies' embedded in config.
  -o, --output PATH        Write JSON results to PATH (default: stdout).
  -r, --hurdle-rate FLOAT  Annual hurdle rate for profit test (default: 0.10).
      --excel-out PATH     Write a formatted deal-pricing Excel workbook to PATH.
                           Mixed-cohort blocks write one file per cohort with the
                           cohort id appended to the stem (e.g. deal-TERM.xlsx).
      --capital MODEL      Regulatory capital model: "licat" (Canada OSFI),
                           "rbc" (US NAIC), or "solvency2" (EU SCR)
                           (ADR-049/101). When set, JSON output and the workbook
                           Summary sheet gain RoC, peak capital, and PV capital
                           rows. See §10 for usage.
      --yrt-rate-table DIR Bill YRT premiums from a tabular (age × duration) rate
                           table directory instead of the flat / mortality-derived
                           rate (ADR-052). See "Tabular YRT rate table" below; the
                           config-file equivalent is deal.yrt_rate_table_path
                           (ADR-075).
      --reserve-basis BASIS  Reserve valuation basis: NET_PREMIUM (default), CRVM,
                           or VM20 (reserve-basis epic, ADR-087..092). Lets a
                           reinsurer reproduce the cedant's reserve method, which
                           drives the YRT NAR, the coinsurance reserve transfer,
                           and the profit signature. NET_PREMIUM is byte-identical
                           to prior runs; an unsupported basis for the product
                           raises an error. See "Reserve basis" below.
      --sufficiency-target-margin FLOAT
                           Premium-sufficiency target margin in [0, 1) (ADR-083).
                           The premium is reported "sufficient" when its post-cost
                           margin ratio meets this target (default 0.0 = bare cost
                           coverage). Surfaced on the Rich table, JSON, and the
                           Excel Summary sheet. See "Premium sufficiency" below.
      --ifrs17-movement    Emit the IFRS 17 analysis-of-change (movement) table
                           per product cohort (ADR-093..096). Off by default. See
                           §11. Tune with --ifrs17-ra-factor (default 0.05) and
                           --ifrs17-months-per-period (default 12).
      --help               Show this message and exit.
```

### Reserve basis

By default reserves use the net-premium basis. A reinsurer pricing an inforce
block usually needs to reproduce the **cedant's** statutory reserve, because the
reserve drives the YRT net-amount-at-risk, the coinsurance reserve transfer, and
the profit signature. Select an alternative basis with `--reserve-basis`:

```bash
# Price the demo block reproducing a US CRVM (Full Preliminary Term) reserve
uv run polaris price --reserve-basis CRVM -o result_crvm.json

# VM-20 simplified (deterministic reserve)
uv run polaris price --reserve-basis VM20 -o result_vm20.json
```

`NET_PREMIUM` (default) is byte-identical to prior runs; `CRVM` and `VM20` are
implemented for `TermLife` and `WholeLife`. Selecting a basis a product does not
support raises a `PolarisComputationError` rather than silently returning the
wrong reserve. The basis can also be set in the config `deal` block
(`"reserve_basis": "CRVM"`); the `--reserve-basis` flag overrides it.

### Premium sufficiency

Every `polaris price` run reports a **premium-sufficiency** panel — does the
premium cover expected claims + expenses (+ a target margin)? The PV loss,
expense, and combined ratios and an `is_sufficient` verdict appear on the Rich
table, in the JSON (`premium_sufficiency` / `reinsurer_premium_sufficiency`
blocks, with a per-line-item PV breakdown), and on the Excel Summary sheet.
Tighten the bar with a target margin:

```bash
# Require a 5% post-cost margin for the premium to read "sufficient"
uv run polaris price --sufficiency-target-margin 0.05
```

### Tabular YRT rate table

By default YRT premiums use a flat / mortality-derived rate. To bill premiums
from an `(age × duration)` rate table instead (ADR-052), point `polaris price`
at a directory holding one CSV per `(sex, smoker)` cohort, named
`{label}_{sex}_{smoker}.csv` (e.g. `yrt_male_ns.csv`):

```bash
polaris price --config deal.json --inforce block.csv \
  --yrt-rate-table data/rate_tables/deal2026 \
  --yrt-rate-table-label deal2026
```

Equivalently, reference the same directory from the config's `deal` block
(ADR-075) so a saved config fully captures the tabular basis — no flag needed:

```json
{
  "deal": {
    "treaty_type": "YRT",
    "yrt_rate_table_path": "data/rate_tables/deal2026",
    "yrt_rate_table_select_period": 3,
    "yrt_rate_table_label": "deal2026",
    "yrt_rate_table_smoker_distinct": true
  }
}
```

The `--yrt-rate-table` flag takes precedence when both are supplied (a one-line
notice is printed). Paths are used as-is — resolved relative to the current
working directory, matching the `mortality.data_dir` convention.

### Workbook contents

Each Excel workbook produced by `--excel-out` always contains these core sheets:

| Sheet | Contents |
|---|---|
| **Summary** | Key pricing metrics: IRR, PV profits, profit margin, break-even year (cedant and reinsurer views), plus the premium-sufficiency panel (ADR-083/084). Under `--capital {licat,rbc,solvency2}` (ADR-049/101) the sheet gains a `Regulatory Capital — {jurisdiction}` header row (ADR-102 — e.g. "Regulatory Capital — US RBC") above **five additional rows** — `Return on Capital`, `Peak Capital`, `PV Capital (stock)`, `PV Capital Strain`, and `Capital-Adjusted IRR` — for both the Cedant and Reinsurer columns. |
| **Cash Flows** | Annual net cash-flow rollup for `projection_years` rows |
| **Assumptions** | Treaty type, cession %, hurdle rate, discount rate, projection years, mortality source, lapse description |

Additional sheets are written **conditionally**: `Gross Cash Flows` /
`Ceded Cash Flows` and the `Cash Flow Comparison` / `Line Item Comparison`
sheets whenever the gross and ceded bases are populated (ADR-080/081/086 — the
CLI populates them on every run), and an `IFRS 17 Movement` sheet when
`--ifrs17-movement` is supplied (ADR-096). A net-only export stays
byte-identical to the core three.

The Sensitivity sheet is intentionally absent — `polaris scenario` remains the
authoritative sensitivity entry point (see ADR-046).

### Smoke test with the shipped fixtures

These commands use `data/inputs/test_inforce.json` (SOA VBT 2015, YRT, WHOLE_LIFE
deal config) and `data/inputs/test_inforce.csv` (2 WHOLE_LIFE policies). The block
is homogeneous so a single workbook is written at the exact path supplied.

```bash
# 1. Validate the inforce CSV first
uv run polaris validate data/inputs/test_inforce.csv

# 2. Pricing only — JSON to stdout
uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv

# 3. Pricing with JSON output saved to disk
uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv \
  --output data/outputs/test_price_result.json

# 4. Pricing with Excel workbook output (the main PR-32 feature)
uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv \
  --output data/outputs/test_price_result.json \
  --excel-out data/outputs/test_deal.xlsx

# 5. Override the hurdle rate
uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv \
  --output data/outputs/test_price_result.json \
  --excel-out data/outputs/test_deal.xlsx \
  --hurdle-rate 0.12
```

Expected terminal output for command 4:
```
╭─────────────────────────────────────────────────────╮
│ Polaris RE  v<version>                              │
│ Life Reinsurance Cash Flow Projection & Pricing ... │
╰─────────────────────────────────────────────────────╯
Results written to: data/outputs/test_price_result.json
Excel workbook written to: data/outputs/test_deal.xlsx
```

Open `data/outputs/test_deal.xlsx` in Excel or Numbers to verify the three
sheets are present and the Summary IRR matches the JSON `cohorts[0].cedant.irr`.

### Mixed-cohort blocks (TERM + WHOLE_LIFE)

When the inforce CSV contains multiple `product_type` values, `polaris price`
prices each cohort independently and writes one workbook per cohort, appending
the cohort id to the stem:

```bash
uv run polaris price \
  --config data/configs/demo.json \
  --inforce data/inputs/demo.csv \
  --output data/outputs/mixed_result.json \
  --excel-out data/outputs/mixed_deal.xlsx
# Writes: mixed_deal-TERM.xlsx and mixed_deal-WHOLE_LIFE.xlsx
```

Note: `polaris scenario` and `polaris uq` do not support mixed-cohort blocks —
they will exit with an error and instruct you to filter to a single product type
first or use `polaris price` instead.

### Config file schema (nested format)

```json
{
  "mortality": {
    "source": "SOA_VBT_2015",
    "multiplier": 1.0
  },
  "lapse": {
    "duration_table": {
      "1": 0.06, "2": 0.05, "3": 0.04,
      "ultimate": 0.015
    }
  },
  "deal": {
    "product_type": "WHOLE_LIFE",
    "treaty_type": "YRT",
    "cession_pct": 0.20,
    "yrt_loading": 0.10,
    "discount_rate": 0.06,
    "hurdle_rate": 0.10,
    "projection_years": 30,
    "acquisition_cost": 500.0,
    "maintenance_cost": 75.0,
    "valuation_date": "2026-04-06"
  }
}
```

A complete worked example is at `data/inputs/test_inforce.json`. Legacy flat
configs (`flat_qx` / `flat_lapse` top-level keys) still work but emit a
deprecation warning; migrate to the nested format.

### Debugging cash flows

Set `POLARIS_PARITY_DEBUG=1` before any `polaris price` run to dump year-by-year
gross / net / ceded cash flow CSVs alongside the workbook:

```bash
POLARIS_PARITY_DEBUG=1 uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv \
  --excel-out data/outputs/test_deal.xlsx
# Parity CSVs written to data/outputs/parity/
```

---

## 10. Regulatory Capital & Return on Capital

`polaris price --capital {licat,rbc,solvency2}` (ADR-049/101) runs a
factor-based required-capital calculator alongside the profit test
(ADR-048) and surfaces return-on-capital (RoC) on every cohort. Pick the
jurisdiction the cedant files under:

| Id | Standard | Module |
|---|---|---|
| `licat` | Canada — OSFI LICAT (C-1/C-2/C-3 + lapse/morbidity) | ADR-047/065/072 |
| `rbc` | US — NAIC Life RBC (C-0…C-4 covariance square root) | ADR-098 |
| `solvency2` | EU — Solvency II standard-formula SCR (correlation-matrix BSCR + risk margin) | ADR-100 |

All three plug into one shared `CapitalModel` protocol via the
`capital_model_for` registry (ADR-101). The same jurisdiction choice is exposed
on every surface (ADR-102): the REST API `capital_model` field, the Streamlit
dashboard's "Regulatory capital basis (RoC)" selector on the Deal Pricing page,
and the deal-pricing Excel workbook's jurisdiction-labelled capital block. A
shared `CAPITAL_MODEL_LABELS` / `capital_model_label()` in `capital_base.py` is
the single labelling site, so the dashboard tiles and the Excel header always
name the standard the calculator actually ran. The flag is opt-in everywhere —
the default (no `--capital`) JSON, console, dashboard, and Excel outputs are
byte-identical to a vanilla `polaris price` run, and the `licat` priced numbers
are unchanged; only an explicit `rbc` / `solvency2` selection moves the numbers.

The metric set populated under `--capital` (identical across jurisdictions —
the schedule that drives it differs):

| Field | Meaning |
|---|---|
| `peak_capital` | Maximum required capital across the projection (point-in-time, the intuitive comparator). |
| `pv_capital` | PV of the capital STOCK at the hurdle rate — sum of each monthly capital balance discounted to t=0. The default RoC denominator (ADR-048). For a 30-year cohort 360 monthly balances are discounted, so this is **substantially larger** than `peak_capital`. |
| `pv_capital_strain` | PV of the capital STRAIN (period-over-period injections) at the hurdle rate. Advisory metric — the alternative RoC denominator. |
| `return_on_capital` | `pv_profits / pv_capital`. Compare to your 8–12% cost-of-capital hurdle to gate treaty acceptance. |
| `capital_adjusted_irr` | IRR of distributable cash flow `net_cash_flow_t − strain_t`, with the residual capital balance released at month T-1. |

### CLI smoke test

These commands use the shipped fixtures
(`data/inputs/test_inforce.json` + `data/inputs/test_inforce.csv` —
SOA VBT 2015, YRT, WHOLE_LIFE) and write the capital block into the
JSON output and the Excel workbook Summary sheet.

```bash
# Pricing with LICAT (Canada) capital — JSON only
uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv \
  --capital licat \
  --output data/outputs/test_capital_result.json

# Same block under the US NAIC RBC standard — swap the jurisdiction id
uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv \
  --capital rbc \
  --output data/outputs/test_capital_rbc_result.json

# Pricing with EU Solvency II capital + Excel workbook
uv run polaris price \
  --config data/inputs/test_inforce.json \
  --inforce data/inputs/test_inforce.csv \
  --capital solvency2 \
  --output data/outputs/test_capital_result.json \
  --excel-out data/outputs/test_capital_deal.xlsx
```

Expected JSON shape (top-level fields populated only on single-cohort
runs; the per-cohort `cohorts[].cedant` / `cohorts[].reinsurer`
entries always carry the same fields):

```json
{
  "cohorts": [
    {
      "product_type": "WHOLE_LIFE",
      "cedant": {
        "pv_profits": ...,
        "irr": ...,
        "return_on_capital": 0.0234,
        "peak_capital": 2295000.0,
        "pv_capital": 211751790.0,
        "pv_capital_strain": 1903344.0,
        "capital_adjusted_irr": 0.0025
      },
      "reinsurer": { ... }
    }
  ]
}
```

The Rich console table also gains `Peak Capital`, `PV Capital
(stock)`, `PV Capital Strain`, `Return on Capital`, and
`Capital-Adjusted IRR` rows for both the Cedant and Reinsurer views.

### Dashboard & Excel (ADR-102)

The same jurisdiction choice is available interactively. On the Streamlit
dashboard's **Deal Pricing** page, the "Regulatory capital basis (RoC)" selector
(None / LICAT (Canada) / US RBC / EU Solvency II) runs the chosen calculator and
adds the RoC / Peak Capital / PV Capital Strain tiles — captioned with the live
jurisdiction — to the cedant and reinsurer views. The `--excel-out` workbook's
Summary sheet labels the capital block with a `Regulatory Capital — {jurisdiction}`
header so a committee reader sees which standard the numbers were computed under.
The result-level RBC / solvency ratio (own funds-or-TAC ÷ SCR-or-ACL) is
computable today via `ProfitTester.run_with_capital(..., available_capital=...)`,
which populates `ProfitResultWithCapital.capital_ratio` (Slice 4c-1, ADR-103 — see
the Python example below). The remaining Slice 4c-2 work is *surfacing* it:
threading the `available_capital` numerator in from the CLI / API / dashboard and
rendering the ratio on the Excel capital block and dashboard tiles, plus a
three-standard validation notebook.

### Python usage

The `LICATCapital` calculator is standalone and can be used outside
the CLI / API. The `for_product(...)` factory pre-populates the
OSFI-aligned C-2 mortality factor (TERM 0.15, WHOLE_LIFE 0.10, UL
0.08, DI 0.05, CI 0.05, ANNUITY 0.03; see ADR-047):

```python
from polaris_re.analytics.capital import LICATCapital
from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.core.policy import ProductType

capital_model = LICATCapital.for_product(ProductType.TERM)

# Option A: ProfitTester integration (recommended) — joins profits
# and capital in one call, returns ProfitResultWithCapital.
tester = ProfitTester(cashflows=net, hurdle_rate=0.10)
result = tester.run_with_capital(capital_model, nar=cedant_nar)
print(result.return_on_capital, result.peak_capital, result.pv_capital)

# Optional: pass the company's available capital / TAC / own funds to also
# get the regulatory solvency ratio at issue (ADR-103). The ratio's
# denominator is jurisdiction-specific (LICAT required capital / RBC ACL /
# EU SCR) but the surface is uniform: result.capital_ratio (a multiple,
# 1.5 = 150%). Omit available_capital and capital_ratio stays None.
result = tester.run_with_capital(
    capital_model, nar=cedant_nar, available_capital=12_000_000.0
)
print(result.capital_ratio)  # e.g. 1.5 — available capital / required₀

# Option B: standalone capital schedule (advanced).
capital = capital_model.required_capital(net, nar=cedant_nar)
print(capital.capital_by_period.shape, capital.peak_capital)
print(capital.capital_ratio(12_000_000.0))  # ratio straight off the schedule
```

Both `ProfitTester.run_with_capital` and `Portfolio.run_with_capital` accept
**any** `CapitalModel` (ADR-099), not just `LICATCapital`. Swapping in the US
NAIC standard is a one-line change — `RBCCapital.for_product(ProductType.TERM)`
in place of `LICATCapital.for_product(...)` — and returns the same
return-on-capital / peak-capital / capital-strain metrics, plus the uniform
`capital_ratio` surface (the RBC ratio for `RBCCapital`, the EU solvency ratio
for `SolvencyIICapital`, the LICAT total ratio for `LICATCapital`); `RBCResult`
additionally exposes `authorized_control_level` and `rbc_ratio(tac)` (a thin
RBC-named alias of `capital_ratio`). The CLI
`--capital {licat,rbc,solvency2}` flag and the API `capital_model` field select
the jurisdiction directly (ADR-101) via the `capital_model_for` registry, so the
swap shown here is also reachable from the command line and HTTP API — no Python
needed.

NAR derivation at the call site uses
`polaris_re.core.pipeline.derive_capital_nar`:

```python
from polaris_re.core.pipeline import derive_capital_nar

# Cedant view (face_share = 1 - cession_pct)
cedant_nar = derive_capital_nar(
    gross=gross_cashflows,
    reserve_balance=net.reserve_balance,
    face_amount_total=block.total_face_amount(),
    cession_pct=0.90,
    is_reinsurer=False,
)
```

### REST API

```bash
curl -X POST http://localhost:8000/api/v1/price \
  -H "Content-Type: application/json" \
  -d '{
    "policies": [...],
    "treaty_type": "YRT",
    "cession_pct": 0.90,
    "capital_model": "licat"
  }'
```

The response gains the optional capital fields on both the cedant
and reinsurer views:

```json
{
  "irr": 0.118,
  "pv_profits": 1234567.0,
  "return_on_capital": 0.094,
  "peak_capital": 2_500_000.0,
  "pv_capital": 218_000_000.0,
  "pv_capital_strain": 2_100_000.0,
  "capital_adjusted_irr": 0.073,
  "reinsurer_return_on_capital": 0.087,
  "reinsurer_peak_capital": 1_800_000.0,
  ...
}
```

Unknown `capital_model` values are rejected at the Pydantic layer
with a 422; only `"licat"` and `null` are accepted today.

### Stock vs strain (ADR-048)

The default RoC denominator is **PV of capital STOCK** —
`pv_profits / pv_capital`, where `pv_capital` discounts each monthly
capital balance to t=0 and sums. Because the capital is held over
the full projection, the stock measure compounds month-over-month
and ends up much larger than `peak_capital`. As a rough anchor: for
a 30-year cohort with roughly flat capital `K`, `pv_capital ≈ K × 12 × ä_n|`
where `ä_n|` is the annuity factor at the hurdle rate over the
horizon (~9.4 at 10% over 30 years, so ~110 × K). Compare
`peak_capital` for the point-in-time view.

`pv_capital_strain` (PV of period-over-period injections) is
exposed for callers that prefer the incremental view; it does not
change the default RoC formula. See ADR-048 for the rationale.

### Streamlit dashboard

The Pricing page exposes a **"Compute LICAT capital + RoC"**
checkbox alongside the existing run controls. When checked, the
Cedant and Reinsurer view sections each gain a row of three tiles:
`Return on Capital`, `Peak Capital`, and `PV Capital Strain`. The
RoC tile tooltip explains the stock-vs-strain distinction and the
monthly-accumulation effect that makes `pv_capital ≫ peak_capital`.

---

## 11. IFRS 17 Movement Table

IFRS 17 filers need a period-to-period **analysis of change** (movement table),
not just point-in-time recognition. Polaris RE groups policies into annual
issue-year cohorts, measures each BBA at its own locked-in discount rate, and
rolls each forward `opening → new business → interest accretion → release →
closing` for BEL, RA, and CSM (each foots by construction).

### CLI

```bash
# Emit the movement table on the demo block (added to the JSON output)
uv run polaris price --ifrs17-movement -o result.json

# With an Excel workbook, this also writes an "IFRS 17 Movement" sheet
uv run polaris price --ifrs17-movement --excel-out deal.xlsx \
  --ifrs17-ra-factor 0.05 \
  --ifrs17-months-per-period 12
```

The console prints a one-line summary (cohort count, reporting period, max
footing error); the per-cohort and aggregate tables land in the
`ifrs17_movement` block of the JSON and, with `--excel-out`, on the
`IFRS 17 Movement` sheet. It is **off by default** — runs without
`--ifrs17-movement` are byte-identical to prior output. Tune the Risk
Adjustment with `--ifrs17-ra-factor` (fraction of |BEL|, default 0.05) and the
reporting-period length with `--ifrs17-months-per-period` (12 = annual).

### REST API

```bash
curl -s -X POST http://localhost:8000/api/v1/ifrs17/movement \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_price_request.json | python -m json.tool
```

Returns the per-cohort tables (ordered by issue year) and the aggregate.

---

## 12. Portfolio Runs

A reinsurer never prices a single treaty in isolation. The `polaris portfolio`
sub-app aggregates many deals into portfolio-level metrics — aggregate IRR / PV
profits, per-deal breakdown, and concentration / HHI by cedant, product, and
treaty type — with optional calendar alignment for mixed-inception books.

### Run a portfolio

```bash
# Run the shipped demo portfolio config (writes aggregate + per-deal JSON)
uv run polaris portfolio run --config data/configs/portfolio_demo.yaml -o portfolio.json

# A larger sample with per-deal inforce CSVs:
uv run polaris portfolio run --config data/inputs/portfolio_sample/portfolio.yaml
```

### Stress the whole portfolio

```bash
# Run the standard six stress scenarios across the portfolio
uv run polaris portfolio scenarios --config data/configs/portfolio_demo.yaml

# Filter to a subset (standard scenario ids)
uv run polaris portfolio scenarios --config data/configs/portfolio_demo.yaml \
  --scenarios "BASE,MORT_110,LAPSE_120"
```

The standard set is `BASE`, `MORT_110` / `MORT_90` (±10% mortality),
`LAPSE_80` / `LAPSE_120` (∓20% lapses), and `MORT_110_LAPSE_80` (combined
adverse).

### Re-render a saved result

```bash
# Pretty-print a previously written result, choosing the concentration weight basis
uv run polaris portfolio report --result portfolio.json \
  --concentration-basis ceded_face
```

`--concentration-basis` accepts `ceded_face`, `ceded_nar_peak`, `pv_premium`,
or `all`. The same workflows are available over the REST API at
`POST /api/v1/portfolio` and `POST /api/v1/portfolio/scenarios`, and as a
**Portfolio** page in the Streamlit dashboard (file upload + per-deal table +
concentration charts).

---

## 13. Production Deployment (ROADMAP 6.2 — A2′)

The REST API ships with the observability, security, and metrics surfaces an ops
team expects (ADR-133 / ADR-134 / ADR-135). Everything is **default-off**: an
un-configured deployment behaves exactly like the plain API.

### Observability, security & metrics envs

| Env var | Effect | Default |
|---|---|---|
| `POLARIS_API_KEYS` | Comma-separated API keys. When set, protected endpoints require `X-API-Key` (or `Authorization: Bearer`); else `401`. | unset → auth disabled |
| `POLARIS_API_RATE_LIMIT` | e.g. `600/minute` (or a bare count = per-minute). Past the threshold → `429` + `Retry-After`. | unset → no limit |
| `POLARIS_TRUSTED_PROXIES` | Comma-separated IPs/CIDRs of trusted proxies. Only then is `X-Forwarded-For` used for rate-limit keying (anti-spoof). | unset → key on peer IP |
| `POLARIS_LOG_LEVEL` | Access-log level for the JSON access logger. | `INFO` |

Every request emits a single-line JSON access log with a correlation id
(`X-Correlation-ID`, echoed from an inbound `X-Request-ID`/`X-Correlation-ID` or
generated) and a duration. `/health`, `/version`, `/metrics`, and the docs are
always reachable (exempt from auth + rate limiting).

### Metrics

`GET /metrics` exposes Prometheus text exposition (v0.0.4) — no extra dependency:

```bash
docker compose up -d api
curl http://localhost:8000/metrics
# polaris_http_requests_total{method="GET",path="/health",status="200"} 3
# polaris_http_request_duration_seconds_bucket{method="POST",path="/api/v1/price",le="0.5"} 5
```

The `path` label is the matched route template (e.g. `/api/v1/price`); requests
that never route (404, or a pre-routing 401/429) collapse to `__unmatched__`, so
label cardinality stays bounded.

### Local metrics stack (Prometheus + Grafana)

```bash
docker compose up -d api prometheus grafana
# Prometheus  → http://localhost:9090   (scrapes api:8000/metrics every 15s)
# Grafana     → http://localhost:3000   (anonymous admin; "Polaris RE API" dashboard
#                                          auto-provisioned: req rate, 5xx rate, p95 latency)
```

### Kubernetes / Helm

Apply the raw manifests:

```bash
kubectl apply -f deploy/k8s/          # deployment, service, configmap, ingress
# API keys go in a Secret named polaris-re-secrets, key "api-keys" (optional):
kubectl create secret generic polaris-re-secrets --from-literal=api-keys='key1,key2'
```

Or install the chart:

```bash
helm install polaris-re deploy/helm/polaris-re \
  --set image.tag=runtime \
  --set config.POLARIS_API_RATE_LIMIT=600/minute \
  --set-string apiKeys='key1,key2' \
  --set ingress.enabled=true
```

The pods/service carry `prometheus.io/scrape` annotations for annotation-based
Prometheus discovery. Behind the ingress, set `config.POLARIS_TRUSTED_PROXIES` to
the ingress/pod CIDR so the rate limiter keys on the real client (ADR-135).

> **Single-replica note.** The rate limiter and metrics registry are in-process.
> Behind N replicas the effective rate limit is ~N× and Prometheus aggregates
> per-pod series. A shared (Redis) rate-limit backend is a tracked follow-up.

---

## 14. Experience Analysis & Assumption-Setting (GAM)

The `polaris experience` command group (A4′ epic; ADR-139…153) fits a **data-driven,
interpretable** mortality basis from your own experience and emits a
`MortalityImprovement` scale the pricing engine consumes directly. It is the auditable
middle layer between the grouped credibility in `experience_study.py` and the black-box
XGBoost in `ml_mortality.py`. All commands need the `[ml]` extra (`uv sync --all-extras`
installs it); the static diagnostic plots also need `[viz]`.

### Input — the canonical grouped-cell CSV

The fit input is **grouped Lexis cells** — one row per covariate combination, not seriatim
(grouping is statistically sufficient for the Poisson/log-exposure GAM). Minimum columns for a
mortality-improvement surface:

```
attained_age,calendar_year,central_exposure,death_count
55,2015,120000.0,180.0
55,2016,124000.0,176.0
56,2015,118000.0,205.0
...
```

- **`q_base` is optional.** If present it is used as-is as the static select-and-ultimate
  offset. Otherwise pass `--table` (e.g. `soa_vbt_2015`) and Polaris attaches the annual base
  from that standard table (Anchor 1 — a single-reference-year *static* table; a generational
  base is rejected). Additional optional keys — `duration_months`, `sex`, `smoker`, `band`,
  `product`, `uw_class`, `channel`, `underwriting_era`, `segment`, and the by-amount pair
  `amount_exposed` / `death_amount` — activate the corresponding effects when present.

A seriatim extract folds into this contract via `analytics.aggregate_seriatim`, and real public
data loads via `analytics.load_hmd` / `analytics.load_ilec` (loaders, not data — see the Python
API below).

### Fit an improvement surface and emit a CUSTOM scale

```bash
# Frequentist tensor MI surface (delta-method band) → emit an ImprovementScale.CUSTOM scale
uv run polaris experience improvement \
  --experience experience_cells.csv \
  --table soa_vbt_2015 \
  --output custom_improvement.json \
  --grid-out mi_grid.csv

# Bayesian reduced-rank-GP surface (honest posterior CREDIBLE band), forward-projected
# 40 years mean-reverting to a 1% long-term rate (CMI/MP-style)
uv run polaris experience improvement \
  --experience experience_cells.csv \
  --table soa_vbt_2015 \
  --bayesian \
  --project-horizon 40 --long-term-rate 0.01 \
  --output custom_improvement_projected.json
```

`--output` writes the `MortalityImprovement` (`ImprovementScale.CUSTOM`) JSON — the artifact the
versioned store and the pricing config consume. `--grid-out` writes the raw `MI_x(y)` grid
(long-format, with band). `--project-horizon` requires `--bayesian` (the projection anchors on the
posterior). Tuning knobs: `--age-df` / `--year-df` (spline flexibility), `--basis {count,amount}`,
`--confidence-level`, `--age-varying/--no-age-varying`, `--convergence-period`.

### Inspect per-feature effect shapes (diagnostics)

```bash
uv run polaris experience fit \
  --experience experience_cells.csv \
  --table soa_vbt_2015 \
  --effects-out effects.csv
```

Reports overall A/E, quasi-Poisson dispersion φ, and each standard feature's smooth/categorical
effect on the A/E multiplier with a confidence band. `--effects-out` writes the plot-ready
long-format CSV (`feature, term_type, x, x_value, multiplier, lower, upper`).

### Freeze and version a basis

The store is **append-only** — re-saving a study date never overwrites, so the full history of
frozen bases is preserved. Version ids are `{study_date}-{seq:03d}` (keyed on the pinned study
date, never the wall clock).

```bash
# Persist the emitted CUSTOM scale as a versioned basis
uv run polaris experience save \
  --improvement custom_improvement.json \
  --study-date 2024-12-31 \
  --credibility 0.8 \
  --label "US term, 2019 study" \
  --store-dir data/assumption_versions

# List the stored history (newest study last)
uv run polaris experience list --store-dir data/assumption_versions
```

### Drive a priced run from a versioned basis

A frozen basis flows into `polaris price` through the `mortality` config block or a CLI flag; it is
threaded onto `AssumptionSet.improvement`, which the product engines already consume — no engine
change. Omitting the selector leaves pricing byte-identical.

```jsonc
// in your --config JSON, under "mortality":
"mortality": {
  "table": "soa_vbt_2015",
  "improvement_version_id": "2024-12-31-001",
  "improvement_store_dir": "data/assumption_versions"
}
```

```bash
# Or override the config's version id from the command line (flag beats config):
uv run polaris price \
  --inforce data/qa/golden_inforce.csv \
  --config my_config.json \
  --improvement-version 2024-12-31-001 \
  -o priced.json
# The selected id is echoed in the JSON summary as "mortality_improvement_version".
```

> Dashboard and REST-API surfacing of the improvement selector is a tracked follow-up (the
> config/CLI path is wired today).

### Python API

```python
import polars as pl
# Import polaris_re.analytics before assumptions.mortality — analytics primes the
# core/pipeline import chain in the right order (a known package import-order quirk).
from polaris_re.analytics import (
    TensorMIModel,             # frequentist surface (delta-method band)
    BayesianTensorMIModel,     # reduced-rank GP (credible band) + projection
    HierarchicalMIModel,       # segment partial pooling (credibility)
    ExperienceGAM,             # interpretable additive A/E GAM
    attach_base_rate,          # attach the static q_base offset (Anchor 1)
    load_hmd, load_ilec,       # loaders, not data
)
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource

# Cells must carry a static `q_base` offset. If the CSV lacks it, attach it from a
# standard table (the fit rejects a generational/projected base — Anchor 1).
cells = pl.read_csv("experience_cells.csv")
if "q_base" not in cells.columns:
    table = MortalityTable.load(MortalityTableSource.SOA_VBT_2015)
    cells = attach_base_rate(cells, table)

# Frequentist tensor MI surface → emit a MortalityImprovement the engine consumes
result = TensorMIModel(cells, age_df=6, year_df=4).fit()   # cells to the constructor, fit() takes none
surface = result.improvement_surface()                     # MI_x(y) grid + delta-method band
improvement = surface.to_mortality_improvement()           # ImprovementScale.CUSTOM

# Bayesian credible band + CMI/MP-style forward projection (40y → 1% long-term rate)
bres = BayesianTensorMIModel(cells).fit()
projection = bres.project_improvement(horizon_years=40, long_term_rate=0.01)
projected_scale = projection.to_mortality_improvement()    # band narrows to the long-term rate

# The emitted scale plugs into any AssumptionSet / projection exactly like a built-in scale.
```

Population data loads via `load_hmd(deaths_path, exposures_path)` (HMD 1x1 Deaths/Exposures →
by-count cells; `fetch_hmd` is a fetch-and-cache helper) and insured grouped files via
`load_ilec(path, basis="both")`. Neither ships data — you supply the cached/licensed file. The
recovery-identity validation deck runs headless via `polaris benchmark --pack experience`.

### Static diagnostic plots (`[viz]` extra)

```python
from polaris_re.viz import plot_effects, plot_mi_surface, plot_mi_projection
# Every band is captioned with its kind — confidence (frequentist) / credible (Bayesian) /
# posterior-predictive (projection) — so the three are never conflated.
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
| `--excel-out` produces no file | Output directory doesn't exist | The CLI creates parent directories automatically; check for a config or inforce error above the Excel line in stderr |
| Mixed-cohort: only one `.xlsx` written | Single cohort in CSV | Cohort suffix is only appended when >1 product type is present — check `product_type` column values |
| `return_on_capital` is `null` under `--capital licat` | Capital factor is zero (e.g. wrong product type or zero `c2_mortality_factor`) | Confirm `LICATCapital.for_product(...)` matches the cohort's `product_type`; ANNUITY defaults to 0.03 and TERM to 0.15 (ADR-047). For custom factors, instantiate `LICATCapital(factors=LICATFactors(...))` directly. |
| `pv_capital` looks huge (e.g. 100× `peak_capital`) | Stock measure compounds monthly across the full projection (ADR-048) | Expected — compare to `peak_capital` for the point-in-time view. `pv_capital_strain` shows the incremental measure. See §10 for the order-of-magnitude rule of thumb. |

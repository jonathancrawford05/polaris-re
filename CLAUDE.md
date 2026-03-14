# CLAUDE.md — Polaris RE Project Instructions

> This file is the **primary instruction set** for Claude Code. Read it fully at the start of every session before writing any code.

---

## 1. Project Vision

**Polaris RE** is a Python-native life reinsurance cash flow projection and deal pricing engine.

The primary target use case is **inforce block evaluation at a reinsurer** — specifically pricing and risk analysis of reinsurance treaty structures (YRT, coinsurance, modified coinsurance) applied to blocks of individual life insurance policies.

The long-term vision is a credible open-source Python alternative to proprietary actuarial modeling systems (AXIS, Prophet) for the reinsurance pricing and risk analytics workflow. The immediate goal is a production-quality MVP that solves a real problem reinsurers face today: disconnected, Excel-driven deal pricing with no native ML integration, no Git-based version control, and no modern uncertainty quantification.

**Key design principles:**
- Actuarially correct above all else — results must be auditable and match expected values
- Vectorized by default — all projections use NumPy arrays, not Python loops over policies
- Pydantic-first — all data contracts are Pydantic v2 models, never raw dicts
- Composable — each component (assumptions, products, treaties) is independently testable
- Transparent — every cash flow output carries full metadata about what assumptions drove it

---

## 2. Repository Layout

```
polaris-re/
├── CLAUDE.md                    ← YOU ARE HERE — read before every session
├── ARCHITECTURE.md              ← Deep system design; read before any core module work
├── README.md                    ← Public-facing project description
├── Dockerfile                   ← Production/CI container build
├── .dockerignore
├── .github/
│   └── workflows/
│       └── ci.yml               ← GitHub Actions CI/CD pipeline
├── docs/
│   ├── ROADMAP.md               ← Phased build plan; consult before starting new features
│   ├── DECISIONS.md             ← Architecture decision records (ADRs)
│   └── ACTUARIAL_GLOSSARY.md    ← Domain terms; consult if uncertain about business logic
├── src/
│   └── polaris_re/
│       ├── __init__.py
│       ├── core/
│       ├── assumptions/
│       ├── products/
│       ├── reinsurance/
│       ├── analytics/
│       └── utils/
├── tests/
├── notebooks/
├── scripts/
├── pyproject.toml               ← Project metadata, deps, tool config
└── Makefile                     ← Common dev commands
```

---

## 3. Technology Stack

| Layer              | Library / Tool         | Notes                                                                 |
|--------------------|------------------------|-----------------------------------------------------------------------|
| Python version     | **3.12+**              | Use native `X \| Y` unions, `type` aliases, improved generics. Never use `from __future__ import annotations` — it is redundant on 3.12. |
| Package manager    | **uv**                 | `uv sync` to install, `uv run <cmd>` to execute. No pip/venv directly. |
| Data validation    | **Pydantic v2**        | All data models — policy, treaty, assumptions                         |
| Vectorized compute | **NumPy 2.0+**         | Core projection arrays — all with explicit dtype                      |
| Data manipulation  | **Polars 1.0+**        | Preferred over pandas; use pandas only for interop                    |
| Numerical          | **SciPy**              | IRR root-finding, statistical utilities                               |
| ML assumptions     | **scikit-learn / XGBoost** | ML-enhanced mortality and lapse modelling                         |
| Testing            | **pytest** + pytest-cov | Strict coverage requirements                                         |
| Linting            | **Ruff**               | Single tool replacing flake8 / isort / pyupgrade                     |
| Type checking      | **mypy** (strict)      | All public APIs must be typed                                         |
| Build backend      | **hatchling**          | Via pyproject.toml — no setup.py                                      |
| CLI                | **Typer**              | Command-line interface (Phase 3)                                      |
| Display / logging  | **Rich**               | CLI output and notebook-friendly printing                             |
| Container          | **Docker**             | Multi-stage build; `make docker-build` and `make docker-test`         |
| CI/CD              | **GitHub Actions**     | `.github/workflows/ci.yml` — lint, test, coverage on every PR        |

---

## 4. Python 3.12 Typing Guidelines

Python 3.12 eliminates the need for several legacy typing patterns. **Always use the modern style.**

| ❌ Old (pre-3.12)                          | ✅ New (3.12+)                              |
|-------------------------------------------|---------------------------------------------|
| `from __future__ import annotations`      | Not needed — remove it                      |
| `Optional[X]`                             | `X \| None`                                 |
| `Union[X, Y]`                             | `X \| Y`                                    |
| `List[X]`, `Dict[K, V]`, `Tuple[X, Y]`   | `list[X]`, `dict[K, V]`, `tuple[X, Y]`     |
| `TypeAlias` from `typing`                 | `type MyAlias = ...` statement              |
| `TypeVar("T")`                            | `type T = TypeVar("T")` or generic syntax   |
| `from typing import TYPE_CHECKING` guards | Usually unnecessary with 3.12 annotations  |

The Ruff `UP` ruleset enforces these automatically — run `make format` to auto-fix.

---

## 5. Coding Conventions

### General
- All files must have a module-level docstring explaining purpose.
- Use `__all__` in every `__init__.py` to explicitly declare public API.
- Never use `Any` from typing — define proper types or use `TypeVar`.
- All numeric arrays are `np.ndarray` with explicit `dtype` — never leave dtype implicit.
- Monetary/actuarial values use `float64`. Ages/counts use `int32`.

### Naming
- Actuarial variables follow standard notation: `q_x` for mortality rate, `v` for discount factor, `A_x` for APV, `a_x` for annuity value.
- Policy-level arrays are named with suffix `_vec` (e.g. `face_amount_vec`).
- Scenario arrays carry a leading `s_` prefix (e.g. `s_mortality_rates`).

### Pydantic Models
- All models inherit from `polaris_re.core.base.PolarisBaseModel`.
- Use `Field(description=...)` on every field.
- Validators use `@model_validator` or `@field_validator` — never override `__init__`.

### Testing
- Every actuarial calculation must have at least one **closed-form verification test**.
- Tests mirror the `src/` structure.
- Use `pytest.mark.parametrize` for sensitivity tests.
- Mark slow tests with `@pytest.mark.slow` — excluded from default `make test`.

### Error Handling
- Raise `PolarisValidationError` for business logic failures.
- Raise `PolarisComputationError` for numerical failures.
- Never suppress exceptions silently.

---

## 6. Module Responsibilities

### `core/`
Foundational layer. Nothing in `core/` may import from `products/`, `reinsurance/`, `assumptions/`, or `analytics/`.

- `base.py` — `PolarisBaseModel`
- `policy.py` — `Policy`, enums
- `inforce.py` — `InforceBlock` with vectorized attribute access
- `projection.py` — `ProjectionConfig`
- `cashflow.py` — `CashFlowResult`
- `exceptions.py` — `PolarisValidationError`, `PolarisComputationError`

### `assumptions/`
- `mortality.py` — `MortalityTable` (CIA 2014, SOA VBT 2015, 2001 CSO)
- `improvement.py` — `MortalityImprovement` (Scale AA, MP-2020, CPM-B)
- `lapse.py` — `LapseAssumption`
- `assumption_set.py` — `AssumptionSet`

### `products/`
- `base_product.py` — `BaseProduct` abstract class
- `term_life.py` — **Phase 1 priority**
- `whole_life.py`, `universal_life.py`, `annuity.py` — Phase 2+

### `reinsurance/`
- `base_treaty.py` — `BaseTreaty`
- `yrt.py`, `coinsurance.py` — **Phase 1 priority**
- `modco.py`, `stop_loss.py` — Phase 2+

### `analytics/`
- `profit_test.py`, `scenario.py` — **Phase 1 priority**
- `uq.py`, `experience_study.py` — Phase 2+

---

## 7. Data Flow

```
InforceBlock (policies)
    │
    ├── AssumptionSet (mortality + improvement + lapse)
    ├── ProjectionConfig (horizon, discount rate, time step)
    │
    └──► BaseProduct.project()
              └──► CashFlowResult [GROSS]
                        └──► BaseTreaty.apply()
                                  └──► (CashFlowResult [NET], CashFlowResult [CEDED])
                                            └──► ProfitTester / ScenarioRunner / UQ
```

---

## 8. Phase 1 MVP Scope

**In scope:**
- [ ] `InforceBlock` and `Policy` with vectorized attribute access
- [ ] `MortalityTable` loading CIA 2014 and SOA VBT 2015
- [ ] `MortalityImprovement` with Scale AA
- [ ] `LapseAssumption` with duration-based select structure
- [ ] `TermLife` monthly projection (net and gross premium basis)
- [ ] `YRTTreaty` — NAR, ceded premium, ceded claims
- [ ] `CoinsuranceTreaty` — proportional cash flows including reserves
- [ ] `ProfitTester` — PV profits, IRR, break-even
- [ ] `ScenarioRunner` — standard stress scenarios
- [ ] Full test suite with closed-form verification
- [ ] Validation notebook end-to-end

**Out of scope for Phase 1:**
UL account value, Modco, Monte Carlo UQ, experience studies, CLI.

---

## 9. Key Actuarial Concepts

**Net Amount at Risk (NAR):** `Face Amount - Reserve`. YRT premiums are based on NAR, not face amount.

**Coinsurance:** Reinsurer takes a proportional share of ALL cash flows including reserves.

**Modified Coinsurance (Modco):** Like coinsurance but cedant retains assets. Reinsurer receives modco adjustment = investment income on ceded reserves.

**Select and Ultimate Mortality:** Select-period rates apply for 15–25 years post-underwriting. After select period, ultimate rates apply.

**Profit Testing:** IRR is the discount rate at which PV of profits = 0. Deal attractive if IRR > cost of capital (8–12% for life reinsurance).

---

## 10. Session Workflow for Claude Code

At the start of each session:
1. Read `CLAUDE.md` (this file) in full.
2. Read `ARCHITECTURE.md` for the module you are working on.
3. Read `docs/ROADMAP.md` to confirm phase scope.
4. Check `docs/DECISIONS.md` for relevant architecture decisions.
5. Run `make test` to confirm baseline test state.
6. Complete one module fully (passing tests) before starting the next.
7. After a module is complete, update `docs/DECISIONS.md` with choices made.

**Never:**
- Use `from __future__ import annotations` (Python 3.12 — not needed)
- Use `Optional[X]` — use `X | None`
- Use `List[X]` / `Dict[K, V]` — use `list[X]` / `dict[K, V]`
- Loop over policies in projection code — vectorize with NumPy
- Hardcode assumption values in product or treaty code
- Use `==` for float comparisons — always use `np.testing.assert_allclose`
- Run `pip` directly — use `uv run` or `uv sync`

---

## 11. Environment Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and set up
git clone https://github.com/jonathancrawford05/polaris-re.git
cd polaris-re
uv sync                    # creates .venv and installs all deps

# Verify
uv run python -c "import polaris_re; print(polaris_re.__version__)"

# Common commands
make test                  # fast tests (excludes @slow)
make test-all              # all tests
make lint                  # ruff + mypy
make format                # auto-fix formatting
make coverage              # test with coverage report
make docker-build          # build Docker image
make docker-test           # run tests inside Docker
```

Environment variables go in `.env` (copy from `.env.example`).
Key variable: `POLARIS_DATA_DIR` — path to actuarial table CSV files.

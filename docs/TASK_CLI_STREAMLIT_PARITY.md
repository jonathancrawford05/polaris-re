# Task: CLI ↔ Streamlit Parity (Phase: CLI Alignment)

## Summary

Bring the `polaris` CLI (`src/polaris_re/cli.py`) into functional and numerical
parity with the Streamlit dashboard. The dashboard is the reference
implementation — the CLI currently takes a materially different (and cruder)
path through the pricing pipeline, producing results that diverge by an order
of magnitude on the same underlying policies.

**Ground truth for this task:** the Streamlit dashboard. Where the CLI and
dashboard disagree, the dashboard is correct and the CLI must be changed to
match.

---

## Evidence of the discrepancy

Test file: `data/inputs/test_inforce.csv` (2 whole-life policies, 20% cession).

| Metric                     | Streamlit (reference)     | CLI (current)             |
|----------------------------|---------------------------|---------------------------|
| PV Profits (Cedant NET)    | **−$8,513,595**           | **+$9,092,542**           |
| Cedant Profit Margin       | −88.58%                   | +87.35%                   |
| Cedant IRR                 | −17.24%                   | N/A (never positive)      |
| Break-even Year (Cedant)   | Never                     | Year 1 (spurious)         |
| PV Profits (Reinsurer)     | **−$2,103,043**           | **+$25,312**              |
| Reinsurer Margin           | −570.87%                  | +7.16%                    |
| Reinsurer IRR              | 420.96% (degenerate)      | N/A                       |

The sign flip on cedant PV profits and the magnitude gap on reinsurer PV
profits both trace back to the CLI's crude assumption set, not to the
projection engine or treaty code. The projection/profit-test stack is shared
between CLI and dashboard and is not at fault here.

---

## Root cause inventory

These are the specific divergences between `cli.py::_build_pipeline_from_config`
and the dashboard's `views/assumptions.py` + `components/projection.py` stack.

### 1. Mortality basis (dominant driver)

**Dashboard:** loads a real select-ultimate mortality table via
`MortalityTable.load(source=SOA_VBT_2015 | CIA_2014 | CSO_2001,
data_dir=data/mortality_tables)`, with sex/smoker-distinct rates and an
optional multiplier (default 1.0).

**CLI:** hard-coded flat `q_x` applied uniformly to every sex/smoker bucket:

```python
flat_qx = float(raw.get("flat_qx", 0.001))
n_ages = 121 - 18
qx = np.full(n_ages, flat_qx, dtype=np.float64)
# ...same 2-D array cloned into all 6 sex × smoker keys...
```

For a 49-year-old non-smoker female and a 62-year-old non-smoker male on
whole-life contracts over a 30-year horizon, a flat 0.005 q_x materially
understates claims — especially the 62-year-old male, whose VBT 2015 q_x
climbs through the 0.01–0.10+ range over the projection window. The CLI sees
almost no claims, so its "profit" is nearly all premium.

### 2. Lapse curve

**Dashboard default** (from `_DEFAULT_LAPSE_RATES` in `views/assumptions.py`):
an 11-point duration-based select curve running 6% → 1.5% ultimate.

**CLI:** a single flat rate applied to all durations:
```python
flat_lapse = float(raw.get("flat_lapse", 0.05))
lapse = LapseAssumption.from_duration_table(
    {1: flat_lapse, 2: flat_lapse, 3: flat_lapse, "ultimate": flat_lapse}
)
```

### 3. Missing assumption-set features

The dashboard exposes — and uses — these, and the CLI silently ignores them:

- **Mortality multiplier** (session key `mortality_multiplier`)
- **Mortality improvement** (if configured on the assumptions page)
- **Expense loading beyond per-policy acquisition/maintenance**
- **ML mortality / ML lapse model overlays** (`ml_mortality_model`,
  `ml_lapse_model`)

Most of these are optional in the dashboard and default to off, so they are
second-order relative to items 1 and 2 — but they need first-class config
surface area in the CLI so the two paths can be driven from the same inputs.

### 4. Treaty configuration coverage

**Dashboard `run_treaty_projection`** supports:
- `yrt_rate_basis ∈ {"Mortality-based", "Manual Rate"}`
- Policy-level cession overrides (`use_policy_cession=True` flag passed to
  `treaty.apply`)
- Explicit `treaty_name` per treaty type

**CLI `_build_treaty_from_config`** supports a subset: derives YRT rate OR
takes a manual `yrt_rate_per_1000`, but has no policy-level cession override
switch and uses hard-coded treaty names (`YRT-CLI`, `COINS-CLI`, `MODCO-CLI`).

### 5. Inforce input format asymmetry (biggest ergonomic gap)

**Dashboard:** `InforceBlock.from_csv(path)` — the user uploads a CSV and the
rest of the pipeline runs. This is the workflow Jonathan just validated end
to end on `test_inforce.csv`.

**CLI:** `_build_pipeline_from_config` expects a JSON config with an embedded
`policies: [...]` list. There is no CSV input path anywhere in the CLI. This
is why we had to hand-roll `data/inputs/test_inforce.json` just to test the
same two policies through the CLI.

### 6. `_build_demo_pipeline` is a parallel assumption set

`_build_demo_pipeline` (used when no `--config` is supplied) builds yet
another variant — synthetic flat q_x, different lapse dict, hard-coded term
policy — which drifts from both the dashboard and the JSON-config path. It
should either be deleted or re-implemented on top of the shared builder.

---

## Target architecture

**Single source of truth for pipeline construction.** The fundamental fix is
to stop having two code paths that build `(InforceBlock, AssumptionSet,
ProjectionConfig, Treaty)` from scratch. Extract one builder that both the
CLI and the dashboard call, then delete the duplicated logic.

Proposed new module: `src/polaris_re/core/pipeline.py`

```python
"""Shared pipeline builder — single source of truth for CLI and dashboard."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig


@dataclass
class MortalityConfig:
    source: str = "SOA_VBT_2015"  # or "CIA_2014" | "CSO_2001" | "flat"
    multiplier: float = 1.0
    flat_qx: float | None = None  # only used if source == "flat"
    data_dir: Path = Path("data/mortality_tables")


@dataclass
class LapseConfig:
    # Dashboard default curve — keep in sync with _DEFAULT_LAPSE_RATES
    duration_table: dict[int | str, float] = field(default_factory=lambda: {
        1: 0.06, 2: 0.05, 3: 0.04, 4: 0.035, 5: 0.03,
        6: 0.025, 7: 0.02, 8: 0.02, 9: 0.02, 10: 0.02,
        "ultimate": 0.015,
    })


@dataclass
class DealConfig:
    """Mirror of dashboard state.DEFAULTS — keep these two in lockstep."""
    product_type: str = "TERM"
    treaty_type: str = "YRT"
    cession_pct: float = 0.90
    yrt_loading: float = 0.10
    yrt_rate_per_1000: float | None = None
    yrt_rate_basis: str = "Mortality-based"  # or "Manual Rate"
    modco_rate: float = 0.045
    discount_rate: float = 0.06
    hurdle_rate: float = 0.10
    projection_years: int = 20
    acquisition_cost: float = 500.0
    maintenance_cost: float = 75.0
    use_policy_cession: bool = False


@dataclass
class PipelineInputs:
    mortality: MortalityConfig = field(default_factory=MortalityConfig)
    lapse: LapseConfig = field(default_factory=LapseConfig)
    deal: DealConfig = field(default_factory=DealConfig)


def load_inforce(
    csv_path: Path | None = None,
    policies_dict: list[dict] | None = None,
) -> InforceBlock:
    """Load an inforce block from either a CSV file or a list-of-dicts.

    Exactly one of csv_path / policies_dict must be provided.
    """
    ...


def build_assumption_set(inputs: PipelineInputs) -> AssumptionSet:
    """Build an AssumptionSet matching how the dashboard would build it."""
    ...


def build_projection_config(inputs: PipelineInputs, valuation_date: date) -> ProjectionConfig:
    """Build a ProjectionConfig matching dashboard.components.projection."""
    ...


def build_pipeline(
    inforce: InforceBlock,
    inputs: PipelineInputs,
) -> tuple[InforceBlock, AssumptionSet, ProjectionConfig]:
    """One-shot builder that produces the full pipeline tuple."""
    ...
```

Once this module exists, `dashboard/components/projection.py::build_projection_config`
and `cli.py::_build_pipeline_from_config` / `_build_demo_pipeline` collapse
into thin adapters that fill `PipelineInputs` from their respective sources
(Streamlit session state vs. JSON/YAML config) and delegate to
`core.pipeline.build_pipeline`.

---

## File Changes

### 1. New: `src/polaris_re/core/pipeline.py`

Implement the module above. Key requirements:

- `MortalityConfig.source == "flat"` branch must build the same 6-bucket
  flat-rate table the CLI currently constructs (preserve backward-compat for
  the JSON config path).
- Non-flat sources call `MortalityTable.load(source=..., data_dir=...)` — the
  same call the dashboard makes.
- Apply `MortalityConfig.multiplier` if ≠ 1.0. Look at how the dashboard
  actually applies the multiplier (likely on `qx` after load) and mirror it.
- `LapseConfig` default matches `views/assumptions.py::_DEFAULT_LAPSE_RATES`
  exactly. Add a module-level constant in `core/pipeline.py` and import it in
  the dashboard to eliminate the duplicate.

### 2. Refactor: `src/polaris_re/dashboard/components/projection.py`

- Import `DealConfig` and `build_projection_config` from `core.pipeline`.
- Delete the local `build_projection_config` (keep the name as a re-export
  for backward compatibility with existing imports).
- `run_treaty_projection` stays here (it's dashboard-UI glue), but the inner
  construction calls should go through `core.pipeline` helpers so the CLI can
  reuse them.

### 3. Refactor: `src/polaris_re/dashboard/components/state.py`

- Replace the `DEFAULTS` dict literal with a dict projection of
  `DealConfig()` so the two can never drift.

### 4. Refactor: `src/polaris_re/cli.py`

This is the bulk of the work.

**4a. New `--inforce` flag on `price`, `scenario`, `uq`:**

```python
inforce_path: Annotated[
    Path | None,
    typer.Option("--inforce", "-i", help="Path to inforce CSV file."),
] = None,
```

When `--inforce` is supplied, load the block via
`InforceBlock.from_csv(inforce_path)` and build assumptions from `--config`
(which now describes *assumptions and deal config only*, no policies). When
both `--inforce` and `policies` in `--config` are present, error out with a
clear message.

**4b. Expand the JSON config schema:**

Replace the current flat `flat_qx` / `flat_lapse` keys with nested blocks
that map 1:1 onto `PipelineInputs`:

```json
{
  "mortality": {
    "source": "SOA_VBT_2015",
    "multiplier": 1.0
  },
  "lapse": {
    "duration_table": {
      "1": 0.06, "2": 0.05, "3": 0.04, "4": 0.035, "5": 0.03,
      "6": 0.025, "7": 0.02, "8": 0.02, "9": 0.02, "10": 0.02,
      "ultimate": 0.015
    }
  },
  "deal": {
    "product_type": "WHOLE_LIFE",
    "treaty_type": "YRT",
    "cession_pct": 0.20,
    "yrt_loading": 0.10,
    "yrt_rate_basis": "Mortality-based",
    "discount_rate": 0.06,
    "hurdle_rate": 0.10,
    "projection_years": 30,
    "acquisition_cost": 500.0,
    "maintenance_cost": 75.0,
    "use_policy_cession": false
  },
  "policies": [ /* optional if --inforce is used */ ]
}
```

**4c. Backward-compat shim:** if the loader sees top-level `flat_qx` /
`flat_lapse` / `product_type` (old schema), emit a deprecation warning via
`console.print("[yellow]⚠ ...[/yellow]")` and translate to the new schema
in-memory. Delete the shim after one release.

**4d. Delete `_build_demo_pipeline`.** Replace with a fixture-driven demo
path that uses a shipped `data/inputs/demo.csv` + `data/configs/demo.json`,
so "demo mode" goes through the same code path as real runs.

**4e. `_build_treaty_from_config` gains `use_policy_cession`** wiring, reads
`deal.use_policy_cession`, and passes it through to `treaty.apply(gross,
inforce=inforce if use_policy_cession else None)` — mirroring
`run_treaty_projection` in the dashboard.

### 5. New: `tests/test_cli_streamlit_parity.py`

This is the acceptance gate for the task. Without it, future drift will
silently reintroduce the bug.

```python
"""CLI ↔ dashboard parity — every metric must agree to within tolerance."""

from pathlib import Path

import pytest

from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import (
    DealConfig, LapseConfig, MortalityConfig, PipelineInputs,
    build_pipeline,
)
from polaris_re.products.dispatch import get_product_engine
from polaris_re.analytics.profit_test import ProfitTester
# ...and whatever the dashboard's projection helpers resolve to after refactor.

FIXTURE_CSV = Path("data/inputs/test_inforce.csv")


@pytest.fixture
def whole_life_inputs() -> PipelineInputs:
    return PipelineInputs(
        mortality=MortalityConfig(source="SOA_VBT_2015", multiplier=1.0),
        lapse=LapseConfig(),  # default curve
        deal=DealConfig(
            product_type="WHOLE_LIFE",
            treaty_type="YRT",
            cession_pct=0.20,
            yrt_loading=0.10,
            discount_rate=0.06,
            hurdle_rate=0.10,
            projection_years=30,
        ),
    )


def test_cli_matches_dashboard_on_test_inforce(whole_life_inputs):
    """Given the same inputs, CLI path and dashboard path must agree."""
    inforce = InforceBlock.from_csv(FIXTURE_CSV)
    inf, assumps, cfg = build_pipeline(inforce, whole_life_inputs)

    gross = get_product_engine(inforce=inf, assumptions=assumps, config=cfg).project()
    # Apply treaty via the same shared helper the dashboard uses.
    # Profit-test both cedant NET and reinsurer view.

    # Sanity checks grounded in the 2-policy test case:
    assert cedant.pv_profits < 0, "2 large WL policies at SOA VBT 2015 should be loss-making"
    assert -10_000_000 < cedant.pv_profits < -7_000_000
    assert reinsurer.pv_profits < 0
    assert -3_000_000 < reinsurer.pv_profits < -1_500_000


def test_cli_command_smoke(tmp_path):
    """Invoke `polaris price --inforce ... --config ...` via typer.CliRunner
    and assert it exits 0 and produces JSON matching the builder path above."""
    ...
```

Tolerance bands are chosen to bracket Jonathan's observed Streamlit run
(cedant PV −$8.5M, reinsurer PV −$2.1M) with ±$1.5M headroom for
non-determinism in YRT rate derivation across minor refactors. Tighten once
the refactor is stable.

### 6. New: `data/inputs/test_inforce.json` (rewrite)

Update the hand-rolled JSON to use the new schema. Delete the `flat_qx` /
`flat_lapse` keys. After refactor, this file should be runnable as:

```bash
uv run polaris price \
  --inforce data/inputs/test_inforce.csv \
  --config data/inputs/test_inforce.json \
  -o data/outputs/test_price.json
```

---

## Acceptance criteria

The task is complete when all of the following are true:

1. **`core/pipeline.py` is the only place** where `MortalityTable`,
   `LapseAssumption`, `AssumptionSet`, and `ProjectionConfig` are constructed
   for a deal. `cli.py` and `dashboard/components/projection.py` are pure
   adapters.
2. Running `polaris price --inforce data/inputs/test_inforce.csv --config
   data/inputs/test_inforce.json` produces cedant PV profits within ±$250k
   of what the dashboard produces for the same CSV with SOA VBT 2015 and the
   default lapse curve. (Tighter tolerance than the parity test; that's
   intentional — the acceptance gate is stricter than the regression guard.)
3. The same tolerance holds for reinsurer PV profits and for scenario and
   UQ commands.
4. `tests/test_cli_streamlit_parity.py` passes on CI.
5. Old CLI JSON configs with `flat_qx` / `flat_lapse` still run, emit a
   deprecation warning, and produce numerically identical results to the
   pre-refactor CLI (verified by a second "legacy schema" parity test).
6. `DEFAULTS` in `dashboard/components/state.py` is a dict view of
   `DealConfig()` — grep for the two occurrences should find only one
   literal.
7. `_build_demo_pipeline` is deleted and replaced by the fixture-driven demo.
8. `uv run ruff check src tests` and `uv run mypy src` are clean.

---

## Out of scope

- ML mortality / ML lapse model loading in the CLI. Add a `# TODO:
  ml_mortality_path` field in `MortalityConfig` but don't implement it in
  this task — the dashboard path is still maturing and the joblib-over-CLI
  UX needs its own ADR.
- YAML config support (we're JSON-only for now; note it as a follow-up).
- IFRS 17 BBA measurement from the CLI. The dashboard's IFRS 17 page should
  be exposed as `polaris ifrs17` in a separate task once parity is proven.

---

## Notes for the implementer

- The dashboard's `projection.py::derive_yrt_rate` and the CLI's
  `_derive_yrt_rate` are already identical character-for-character. Move to
  `core/pipeline.py` (or a new `core/yrt.py`), have both callers import from
  there, and delete the duplicate. ADR-038 should be updated to reference
  the new canonical location.
- Same goes for `ceded_to_reinsurer_view` — it's duplicated verbatim in
  `cli.py` and `dashboard/components/projection.py`. Consolidate per ADR-039.
- Before touching the CLI, write the parity test and make sure it fails
  against `main`. Red-green-refactor. The sign flip on cedant PV profits is
  the specific regression the test should catch.
- When loading mortality tables from the CLI, respect the
  `POLARIS_DATA_DIR` environment variable the dashboard uses
  (`Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"`).
  Jonathan's local tables live under that path.
- Whole-life policies in the test CSV have `policy_term` empty and
  `duration_inforce=120` (months). This was the Streamlit fix Jonathan
  shipped in the previous session. Confirm the CLI path round-trips that
  same CSV through `InforceBlock.from_csv()` without coercion differences.

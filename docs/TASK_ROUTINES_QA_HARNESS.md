# Task: Automated QA Harness & Claude Code Routines

## Summary

Build a headless QA harness that replaces the manual "launch Streamlit →
Claude-in-Chrome inspects UI → write task doc" workflow with automated
`AppTest` scenarios and CLI assertions. Wire the harness into Claude Code
routines so every PR and nightly build produces structured QA findings in
the `TASK_*.md` format — closing the development feedback loop without
human intervention.

**Ground truth for this task:** the existing parity tests in
`tests/test_cli_streamlit_parity.py` prove that CLI and dashboard share the
same numerical code paths via `core/pipeline.py`. The QA harness extends
this proof to cover *UI state flow* (widget values propagating through
session state) and *golden output regression* (numerical drift detection
across releases).

---

## Motivation

### What the current workflow looks like

1. Claude Code implements a feature on a branch
2. Jonathan runs `streamlit run src/polaris_re/dashboard/app.py` locally
3. Claude-in-Chrome navigates the live UI — uploads CSV, adjusts sliders,
   reads profit test tables, spots bugs
4. Findings are distilled into a structured task doc (e.g.
   `TASK_POST_PARITY_REFINEMENTS.md`)
5. Next Claude Code session picks up the task doc and implements fixes

Steps 2–4 take 15–30 minutes per iteration and require Jonathan's manual
involvement.

### What this task enables

- **PR trigger:** Every PR gets automated functional QA through the same
  pipeline code paths the dashboard uses. Claude Code routine posts a
  structured pass/fail comment on the PR.
- **Nightly sweep:** Broader regression across all product types and treaty
  configurations. Produces a `QA_FINDINGS_YYYY-MM-DD.md` in `TASK_*` format
  that the next Claude Code session can consume directly.
- **On-demand:** POST a prompt to a routine endpoint for ad-hoc exploration.

### Why this works without a browser

Every major bug in polaris-re history was detectable without visual rendering:

| Bug | Detection method |
|-----|-----------------|
| Sign-flip (flat mortality vs VBT 2015) | Numerical assertion: `cedant.pv_profits < 0` |
| Cession slider floor (<50%) | AppTest: read `st.slider` min_value |
| Valuation date not propagating | AppTest: assert `deal_config["valuation_date"]` after upload |
| Reserve projection flat-rate fallback | Golden output diff on reserve columns |
| IFRS 17 onerous contract (underpriced premiums) | Assert `csm < 0` matches expectation |

The genuine UX review ("is this layout confusing?") is a product design
activity done occasionally by a human, not a per-PR gate.

---

## Golden Input Sample Design

### File: `data/qa/golden_inforce.csv`

12 policies chosen to cover the full combinatorial space:

| Policy ID | Product | Age | Sex | Smoker | Face | Duration | Cession Override | Purpose |
|-----------|---------|-----|-----|--------|------|----------|-----------------|---------|
| GLD-T-001 | TERM | 30→35 | M | NS | $500K | 60m | — | Young male NS, preferred UW, mid-term |
| GLD-T-002 | TERM | 45→50 | F | NS | $1M | 60m | — | Middle-aged female NS, standard UW |
| GLD-T-003 | TERM | 35→40 | M | S | $750K | 60m | — | Smoker male, 30-year term |
| GLD-T-004 | TERM | 55→60 | F | S | $250K | 60m | — | Older smoker female, short 10yr term |
| GLD-WL-001 | WL | 40→50 | M | NS | $2M | 120m | — | Seasoned WL male, preferred |
| GLD-WL-002 | WL | 50→60 | F | NS | $5M | 120m | — | Large seasoned WL female |
| GLD-WL-003 | WL | 35→40 | M | S | $1.5M | 60m | — | Younger WL smoker |
| GLD-WL-004 | WL | 60→65 | F | S | $3M | 60m | — | Older WL smoker female, substandard |
| GLD-T-005 | TERM | 28→33 | F | NS | $300K | 60m | **0.50** | Policy-level cession override (ADR-036) |
| GLD-WL-005 | WL | 45→55 | M | NS | $10M | 120m | **0.35** | Large WL with policy-level override |
| GLD-T-006 | TERM | 40 | M | NS | $500K | 0m | — | New issue (duration=0) |
| GLD-WL-006 | WL | 55 | F | NS | $4M | 0m | — | New issue WL |

**Coverage guarantees:**
- Both sexes (6M, 6F)
- Both smoker statuses (4 S, 8 NS)
- Both product types (6 TERM, 6 WL) → tests `iter_cohorts` partitioning
- Seasoned (120m), mid-duration (60m), and new-issue (0m) policies
- 2 policies with `reinsurance_cession_pct` overrides → tests ADR-036
- Face amounts from $250K to $10M → tests aggregation and scale
- Ages spanning 28–65 → tests mortality table edge coverage
- All valuation dates fixed to `2026-04-01` for reproducibility

### Config files: `data/qa/golden_config_*.json`

Four configs test distinct treaty/assumption combinations:

| Config file | Treaty | Mortality | Cession | Policy cession | Purpose |
|-------------|--------|-----------|---------|----------------|---------|
| `golden_config_yrt.json` | YRT | SOA VBT 2015 | 90% | off | Primary baseline |
| `golden_config_coins.json` | COINS | SOA VBT 2015 | 50% | off | Additivity proof |
| `golden_config_policy_cession.json` | YRT | SOA VBT 2015 | 90% | **on** | ADR-036 |
| `golden_config_flat.json` | YRT | flat 0.3% | 90% | off | CI fallback (no tables) |

---

## File Changes

### 1. New: `data/qa/golden_inforce.csv`

The CSV described above. Committed as a fixture. Must not be modified
without re-generating golden baselines.

### 2. New: `data/qa/golden_config_*.json`

The four JSON configs described above.

### 3. New: `tests/qa/__init__.py`

Empty init file for the QA test package.

### 4. New: `tests/qa/conftest.py`

Shared fixtures for the QA test suite.

```python
"""QA test fixtures — golden inputs and pipeline builders."""

import os
from datetime import date
from pathlib import Path

import pytest

from polaris_re.core.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    load_inforce,
)

GOLDEN_CSV = Path("data/qa/golden_inforce.csv")
GOLDEN_CONFIGS_DIR = Path("data/qa")
GOLDEN_OUTPUTS_DIR = Path("tests/qa/golden_outputs")

# Mortality tables required for SOA VBT 2015 configs
_MORTALITY_DIR = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
_HAS_SOA_TABLES = (_MORTALITY_DIR / "soa_vbt_2015_male_nonsmoker.csv").exists()


def requires_soa_tables(fn):
    """Skip decorator for tests that need real mortality tables."""
    return pytest.mark.skipif(
        not _HAS_SOA_TABLES,
        reason=f"SOA VBT 2015 tables not found at {_MORTALITY_DIR}",
    )(fn)


@pytest.fixture()
def golden_inforce():
    """Load the golden inforce block."""
    if not GOLDEN_CSV.exists():
        pytest.skip(f"Golden CSV not found: {GOLDEN_CSV}")
    return load_inforce(csv_path=GOLDEN_CSV)


@pytest.fixture()
def golden_yrt_inputs() -> PipelineInputs:
    """PipelineInputs matching golden_config_yrt.json."""
    return PipelineInputs(
        mortality=MortalityConfig(source="SOA_VBT_2015", multiplier=1.0),
        lapse=LapseConfig(),
        deal=DealConfig(
            product_type="TERM",
            treaty_type="YRT",
            cession_pct=0.90,
            yrt_loading=0.10,
            discount_rate=0.06,
            hurdle_rate=0.10,
            projection_years=20,
            valuation_date=date(2026, 4, 1),
        ),
    )


@pytest.fixture()
def golden_flat_inputs() -> PipelineInputs:
    """PipelineInputs matching golden_config_flat.json (no SOA tables)."""
    return PipelineInputs(
        mortality=MortalityConfig(source="flat", flat_qx=0.003),
        lapse=LapseConfig(),
        deal=DealConfig(
            product_type="TERM",
            treaty_type="YRT",
            cession_pct=0.90,
            yrt_loading=0.10,
            discount_rate=0.06,
            hurdle_rate=0.10,
            projection_years=20,
            valuation_date=date(2026, 4, 1),
        ),
    )
```

### 5. New: `tests/qa/test_pipeline_golden.py`

Golden output regression tests via the CLI pipeline path. These run
the pricing engine on the golden inputs and compare against committed
baseline JSON files.

```python
"""Golden output regression tests — CLI pipeline path.

Run the pricing engine on the golden inputs and compare against
committed baselines. When a baseline doesn't exist yet, generate it.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.core.pipeline import (
    build_pipeline,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    iter_cohorts,
    load_inforce,
)
from polaris_re.products.dispatch import get_product_engine

from .conftest import GOLDEN_CSV, GOLDEN_OUTPUTS_DIR, requires_soa_tables

# Tolerance for golden output comparison ($ amount)
ABS_TOL_DOLLARS = 500.0
# Tolerance for percentage metrics
ABS_TOL_PCT = 0.005


def _run_pricing(inforce, inputs):
    """Run full pricing pipeline, return per-cohort results dict."""
    inf, assumptions, config = build_pipeline(inforce, inputs)
    cohorts = iter_cohorts(inf)
    results = {}

    for product_type, cohort_inforce in cohorts:
        gross = get_product_engine(
            inforce=cohort_inforce,
            assumptions=assumptions,
            config=config,
        ).project()

        face_amount = cohort_inforce.total_face_amount()
        yrt_rate = derive_yrt_rate(
            gross, face_amount, inputs.deal.yrt_loading
        )

        treaty = build_treaty(
            treaty_type=inputs.deal.treaty_type,
            cession_pct=inputs.deal.cession_pct,
            face_amount=face_amount,
            yrt_rate_per_1000=yrt_rate,
        )

        if treaty is not None:
            use_policy = inputs.deal.use_policy_cession
            inforce_arg = cohort_inforce if use_policy else None
            net, ceded = treaty.apply(gross, inforce=inforce_arg)
        else:
            net, ceded = gross, None

        cedant = ProfitTester(
            cashflows=net, hurdle_rate=inputs.deal.hurdle_rate
        ).run()

        reinsurer = None
        if ceded is not None:
            reinsurer = ProfitTester(
                cashflows=ceded_to_reinsurer_view(ceded),
                hurdle_rate=inputs.deal.hurdle_rate,
            ).run()

        results[product_type.value] = {
            "n_policies": cohort_inforce.n_policies,
            "face_amount": face_amount,
            "cedant_pv_profits": cedant.pv_profits,
            "cedant_profit_margin": cedant.profit_margin,
            "cedant_irr": cedant.irr,
            "cedant_breakeven": cedant.breakeven_year,
            "reinsurer_pv_profits": (
                reinsurer.pv_profits if reinsurer else None
            ),
            "reinsurer_profit_margin": (
                reinsurer.profit_margin if reinsurer else None
            ),
            "gross_total_premiums": float(gross.gross_premiums.sum()),
            "gross_total_claims": float(gross.death_claims.sum()),
            "projection_months": gross.projection_months,
        }

    return results


def _save_golden(results: dict, name: str) -> Path:
    """Save golden output as JSON baseline."""
    GOLDEN_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_OUTPUTS_DIR / f"{name}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    return path


def _load_golden(name: str) -> dict | None:
    """Load golden output baseline, or None if not yet generated."""
    path = GOLDEN_OUTPUTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _compare_golden(actual: dict, expected: dict, label: str) -> list[str]:
    """Compare actual vs expected results, return list of discrepancies."""
    failures = []

    for cohort_key in expected:
        if cohort_key not in actual:
            failures.append(f"{label}/{cohort_key}: missing from actual")
            continue

        exp = expected[cohort_key]
        act = actual[cohort_key]

        for metric in [
            "cedant_pv_profits", "reinsurer_pv_profits",
            "gross_total_premiums", "gross_total_claims",
        ]:
            e_val = exp.get(metric)
            a_val = act.get(metric)
            if e_val is None and a_val is None:
                continue
            if e_val is None or a_val is None:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={e_val}, actual={a_val}"
                )
                continue
            if abs(float(a_val) - float(e_val)) > ABS_TOL_DOLLARS:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={float(e_val):,.2f}, "
                    f"actual={float(a_val):,.2f}, "
                    f"delta={float(a_val) - float(e_val):+,.2f}"
                )

        for metric in ["cedant_profit_margin", "reinsurer_profit_margin"]:
            e_val = exp.get(metric)
            a_val = act.get(metric)
            if e_val is None and a_val is None:
                continue
            if e_val is None or a_val is None:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={e_val}, actual={a_val}"
                )
                continue
            if abs(float(a_val) - float(e_val)) > ABS_TOL_PCT:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={float(e_val):.4%}, "
                    f"actual={float(a_val):.4%}"
                )

    return failures


class TestGoldenYRT:
    """Golden output tests for YRT treaty config."""

    GOLDEN_NAME = "golden_yrt"

    @requires_soa_tables
    def test_yrt_golden_regression(
        self, golden_inforce, golden_yrt_inputs
    ):
        """YRT pricing must match golden baseline."""
        actual = _run_pricing(golden_inforce, golden_yrt_inputs)
        expected = _load_golden(self.GOLDEN_NAME)

        if expected is None:
            _save_golden(actual, self.GOLDEN_NAME)
            pytest.skip(
                f"Golden baseline not found — generated at "
                f"{GOLDEN_OUTPUTS_DIR / self.GOLDEN_NAME}.json. "
                f"Commit this file and re-run."
            )

        failures = _compare_golden(actual, expected, self.GOLDEN_NAME)
        if failures:
            # Overwrite with actual so the diff is visible in git
            _save_golden(actual, f"{self.GOLDEN_NAME}_actual")
            pytest.fail(
                f"Golden output regression ({len(failures)} failures):\n"
                + "\n".join(f"  • {f}" for f in failures)
            )


class TestGoldenFlat:
    """Golden output tests for flat mortality (CI-safe, no SOA tables)."""

    GOLDEN_NAME = "golden_flat"

    def test_flat_golden_regression(
        self, golden_inforce, golden_flat_inputs
    ):
        """Flat-mortality pricing must match golden baseline."""
        actual = _run_pricing(golden_inforce, golden_flat_inputs)
        expected = _load_golden(self.GOLDEN_NAME)

        if expected is None:
            _save_golden(actual, self.GOLDEN_NAME)
            pytest.skip(
                f"Golden baseline not found — generated at "
                f"{GOLDEN_OUTPUTS_DIR / self.GOLDEN_NAME}.json. "
                f"Commit this file and re-run."
            )

        failures = _compare_golden(actual, expected, self.GOLDEN_NAME)
        if failures:
            _save_golden(actual, f"{self.GOLDEN_NAME}_actual")
            pytest.fail(
                f"Golden output regression ({len(failures)} failures):\n"
                + "\n".join(f"  • {f}" for f in failures)
            )


class TestGoldenSanity:
    """Sanity checks that don't depend on committed baselines."""

    def test_golden_csv_loads(self, golden_inforce):
        """Golden CSV loads without error and has expected policy count."""
        assert golden_inforce.n_policies == 12

    def test_golden_csv_has_both_product_types(self, golden_inforce):
        """Golden CSV contains both TERM and WHOLE_LIFE policies."""
        from polaris_re.core.policy import ProductType
        pts = golden_inforce.product_types
        assert ProductType.TERM in pts
        assert ProductType.WHOLE_LIFE in pts

    def test_golden_csv_has_policy_cession_overrides(self, golden_inforce):
        """At least 2 policies have reinsurance_cession_pct set."""
        overrides = [
            p for p in golden_inforce.policies
            if p.reinsurance_cession_pct is not None
        ]
        assert len(overrides) >= 2

    def test_golden_csv_has_new_issue_policies(self, golden_inforce):
        """At least 1 policy with duration_inforce == 0."""
        new_issues = [
            p for p in golden_inforce.policies
            if p.duration_inforce == 0
        ]
        assert len(new_issues) >= 1

    def test_cohort_partitioning(self, golden_inforce):
        """iter_cohorts splits golden block into exactly 2 cohorts."""
        from polaris_re.core.pipeline import iter_cohorts
        cohorts = iter_cohorts(golden_inforce)
        assert len(cohorts) == 2
        total = sum(sub.n_policies for _, sub in cohorts)
        assert total == 12
```

### 6. New: `tests/qa/test_dashboard_flows.py`

AppTest-based scenarios that drive the Streamlit dashboard headlessly.
These test the *UI state flow* — widgets propagating values through
`session_state` and downstream pages consuming them correctly.

```python
"""Dashboard flow tests using Streamlit AppTest.

These tests drive the Streamlit app headlessly, verifying that:
- Widget values propagate through session_state correctly
- Page navigation renders without error
- Deal config changes on Assumptions page reach Deal Pricing
- Inforce upload populates the expected session state keys

AppTest limitations:
- Cannot test matplotlib chart rendering (use golden output tests)
- Cannot test file_uploader directly (use session state injection)
- Cannot test real SOA table loading (mock or use flat mortality)
"""

import streamlit as st
import pytest

# NOTE: AppTest is available from streamlit >= 1.28
# Import will fail on older versions — skip gracefully.
try:
    from streamlit.testing.v1 import AppTest
    _HAS_APPTEST = True
except ImportError:
    _HAS_APPTEST = False

pytestmark = pytest.mark.skipif(
    not _HAS_APPTEST,
    reason="streamlit.testing.v1 not available",
)

APP_PATH = "src/polaris_re/dashboard/app.py"


class TestAppBootstrap:
    """Verify the app starts and renders the default page."""

    def test_app_starts_without_error(self):
        """App should start and render the Inforce Block page."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert not at.exception, f"App raised: {at.exception}"

    def test_sidebar_navigation_exists(self):
        """Sidebar should have a radio widget with all 7 pages."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        # Radio widget for navigation
        assert len(at.sidebar.radio) >= 1
        nav = at.sidebar.radio[0]
        assert "Inforce Block" in nav.options
        assert "Deal Pricing" in nav.options
        assert "IFRS 17" in nav.options


class TestPageNavigation:
    """Verify each page renders without error when navigated to."""

    @pytest.mark.parametrize("page_name", [
        "Inforce Block",
        "Assumptions",
        "Deal Pricing",
        "Treaty Comparison",
        "Scenario Analysis",
        "Monte Carlo UQ",
        "IFRS 17",
    ])
    def test_page_renders(self, page_name):
        """Each page should render without raising exceptions."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value(page_name)
        at.run()
        assert not at.exception, (
            f"Page '{page_name}' raised: {at.exception}"
        )


class TestSessionStateDefaults:
    """Verify session state initialisation from DealConfig."""

    def test_deal_config_initialised(self):
        """deal_config should be initialised with DealConfig defaults."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()

        # Session state should have deal_config
        assert "deal_config" in at.session_state
        cfg = at.session_state["deal_config"]
        assert cfg is not None
        assert cfg["product_type"] == "TERM"
        assert cfg["treaty_type"] == "YRT"
        assert cfg["cession_pct"] == 0.90
        assert cfg["discount_rate"] == 0.06

    def test_inforce_block_initially_none(self):
        """inforce_block should be None before any CSV is uploaded."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert at.session_state.get("inforce_block") is None


class TestAssumptionsPageWidgets:
    """Verify widget rendering and state updates on Page 2."""

    def test_mortality_selectbox_renders(self):
        """Mortality table selectbox should render on Assumptions page."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Assumptions")
        at.run()
        assert not at.exception

    def test_cession_slider_bounds(self):
        """Cession slider must allow values from 0% to 100%.

        This is the regression test for the <50% slider floor bug.
        """
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Assumptions")
        at.run()
        # Find the cession slider — look for sliders on the page
        # The exact slider index depends on rendering order;
        # search by examining slider labels or values.
        sliders = at.slider
        cession_sliders = [
            s for s in sliders
            if hasattr(s, 'label') and 'cession' in str(s.label).lower()
        ]
        if cession_sliders:
            cs = cession_sliders[0]
            # Verify the slider allows sub-50% values
            cs.set_value(0.10)
            at.run()
            assert not at.exception, "Cession slider rejected 10%"
            # Verify it reaches the full range
            cs.set_value(1.0)
            at.run()
            assert not at.exception, "Cession slider rejected 100%"


class TestDealPricingWithInjectedState:
    """Test Deal Pricing page with pre-injected session state.

    Since AppTest cannot drive file_uploader, we inject a pre-built
    InforceBlock and AssumptionSet into session state before navigating
    to the Deal Pricing page. This mirrors what Pages 1 and 2 would do.
    """

    @pytest.fixture()
    def app_with_inforce(self):
        """App with a synthetic inforce block injected into state."""
        from datetime import date
        from polaris_re.core.pipeline import (
            MortalityConfig,
            LapseConfig,
            DealConfig,
            PipelineInputs,
            build_pipeline,
            load_inforce,
        )

        # Build a minimal single-policy block with flat mortality
        policies = [{
            "policy_id": "TEST-001",
            "issue_age": 40,
            "attained_age": 40,
            "sex": "M",
            "smoker": False,
            "face_amount": 500000.0,
            "annual_premium": 1200.0,
            "policy_term": 20,
            "duration_inforce": 0,
            "issue_date": "2026-04-01",
            "valuation_date": "2026-04-01",
            "product_type": "TERM",
        }]
        inforce = load_inforce(policies_dict=policies)
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.003),
            lapse=LapseConfig(),
            deal=DealConfig(product_type="TERM", projection_years=10),
        )
        inf, assumptions, config = build_pipeline(inforce, inputs)

        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()

        # Inject state
        at.session_state["inforce_block"] = inf
        at.session_state["assumption_set"] = assumptions

        return at

    def test_pricing_page_renders_with_state(self, app_with_inforce):
        """Deal Pricing page should render when state is populated."""
        at = app_with_inforce
        at.sidebar.radio[0].set_value("Deal Pricing")
        at.run()
        assert not at.exception, (
            f"Deal Pricing raised with injected state: {at.exception}"
        )
```

### 7. New: `tests/qa/test_cli_golden.py`

End-to-end CLI command tests against golden inputs. Uses `typer.CliRunner`
to invoke `polaris price` with the golden CSV and configs.

```python
"""CLI end-to-end tests against golden inputs.

Uses typer.CliRunner to invoke polaris price/scenario/uq commands
with the golden inforce CSV and config files, asserting on exit code
and output structure.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from polaris_re.cli import app
from .conftest import GOLDEN_CSV, GOLDEN_CONFIGS_DIR, requires_soa_tables

runner = CliRunner()


class TestCLIGoldenSmoke:
    """Smoke tests: CLI commands run to completion on golden inputs."""

    def test_price_flat_mortality(self, tmp_path):
        """polaris price runs on golden CSV with flat mortality."""
        output = tmp_path / "result.json"
        result = runner.invoke(app, [
            "price",
            "--config", str(GOLDEN_CONFIGS_DIR / "golden_config_flat.json"),
            "--inforce", str(GOLDEN_CSV),
            "--output", str(output),
        ])
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
        payload = json.loads(output.read_text())
        assert "cohorts" in payload
        assert payload["summary"]["n_cohorts"] == 2

    @requires_soa_tables
    def test_price_yrt_soa(self, tmp_path):
        """polaris price runs with SOA VBT 2015 tables."""
        output = tmp_path / "result.json"
        result = runner.invoke(app, [
            "price",
            "--config", str(GOLDEN_CONFIGS_DIR / "golden_config_yrt.json"),
            "--inforce", str(GOLDEN_CSV),
            "--output", str(output),
        ])
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
        payload = json.loads(output.read_text())
        assert payload["summary"]["n_cohorts"] == 2
        # Both cohorts should have cedant profit test results
        for cohort in payload["cohorts"]:
            assert "pv_profits" in cohort["cedant"]

    @requires_soa_tables
    def test_price_coinsurance(self, tmp_path):
        """polaris price runs with coinsurance treaty."""
        output = tmp_path / "result.json"
        result = runner.invoke(app, [
            "price",
            "--config", str(GOLDEN_CONFIGS_DIR / "golden_config_coins.json"),
            "--inforce", str(GOLDEN_CSV),
            "--output", str(output),
        ])
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"

    @requires_soa_tables
    def test_price_policy_cession(self, tmp_path):
        """polaris price runs with policy-level cession overrides."""
        output = tmp_path / "result.json"
        result = runner.invoke(app, [
            "price",
            "--config", str(
                GOLDEN_CONFIGS_DIR / "golden_config_policy_cession.json"
            ),
            "--inforce", str(GOLDEN_CSV),
            "--output", str(output),
        ])
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"

    def test_scenario_rejects_mixed_block(self, tmp_path):
        """polaris scenario exits non-zero on mixed product block."""
        result = runner.invoke(app, [
            "scenario",
            "--config", str(GOLDEN_CONFIGS_DIR / "golden_config_flat.json"),
            "--inforce", str(GOLDEN_CSV),
        ])
        assert result.exit_code != 0

    def test_validate_golden_csv(self):
        """polaris validate accepts the golden CSV."""
        result = runner.invoke(app, [
            "validate", str(GOLDEN_CSV),
        ])
        assert result.exit_code == 0
```

### 8. New: `tests/qa/golden_outputs/.gitkeep`

Empty directory. Baselines are generated on first test run and
committed. The `.gitignore` should NOT exclude this directory.

### 9. Update: `pyproject.toml`

Add `streamlit[testing]` to the dev dependency group:

```toml
# In [dependency-groups] dev section, add:
"streamlit>=1.35",    # already present
```

**Note:** `streamlit.testing.v1` is available from streamlit >= 1.28. No
additional dependency is needed beyond the existing `streamlit>=1.35`
requirement. Verify with:

```bash
uv run python -c "from streamlit.testing.v1 import AppTest; print('OK')"
```

### 10. New: `tests/qa/generate_golden.py`

Script to regenerate golden baselines on demand:

```python
"""Generate golden output baselines.

Run this script when the golden inputs or the projection engine change.
Outputs are written to tests/qa/golden_outputs/ and should be committed.

Usage:
    uv run python tests/qa/generate_golden.py
    uv run python tests/qa/generate_golden.py --flat-only  # CI mode
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from polaris_re.core.pipeline import (
    DealConfig, LapseConfig, MortalityConfig, PipelineInputs,
    build_pipeline, build_treaty, ceded_to_reinsurer_view,
    derive_yrt_rate, iter_cohorts, load_inforce,
)
from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.products.dispatch import get_product_engine

GOLDEN_CSV = Path("data/qa/golden_inforce.csv")
OUTPUT_DIR = Path("tests/qa/golden_outputs")


def run_and_save(inputs: PipelineInputs, name: str) -> None:
    """Run pricing pipeline and save golden output."""
    inforce = load_inforce(csv_path=GOLDEN_CSV)
    inf, assumptions, config = build_pipeline(inforce, inputs)
    cohorts = iter_cohorts(inf)
    results = {}

    for product_type, cohort_inforce in cohorts:
        gross = get_product_engine(
            inforce=cohort_inforce, assumptions=assumptions, config=config
        ).project()
        face_amount = cohort_inforce.total_face_amount()
        yrt_rate = derive_yrt_rate(gross, face_amount, inputs.deal.yrt_loading)
        treaty = build_treaty(
            treaty_type=inputs.deal.treaty_type,
            cession_pct=inputs.deal.cession_pct,
            face_amount=face_amount,
            yrt_rate_per_1000=yrt_rate,
        )
        if treaty is not None:
            use_pc = inputs.deal.use_policy_cession
            inf_arg = cohort_inforce if use_pc else None
            net, ceded = treaty.apply(gross, inforce=inf_arg)
        else:
            net, ceded = gross, None

        cedant = ProfitTester(
            cashflows=net, hurdle_rate=inputs.deal.hurdle_rate
        ).run()
        reinsurer = None
        if ceded is not None:
            reinsurer = ProfitTester(
                cashflows=ceded_to_reinsurer_view(ceded),
                hurdle_rate=inputs.deal.hurdle_rate,
            ).run()

        results[product_type.value] = {
            "n_policies": cohort_inforce.n_policies,
            "face_amount": face_amount,
            "cedant_pv_profits": cedant.pv_profits,
            "cedant_profit_margin": cedant.profit_margin,
            "cedant_irr": cedant.irr,
            "cedant_breakeven": cedant.breakeven_year,
            "reinsurer_pv_profits": reinsurer.pv_profits if reinsurer else None,
            "reinsurer_profit_margin": reinsurer.profit_margin if reinsurer else None,
            "gross_total_premiums": float(gross.gross_premiums.sum()),
            "gross_total_claims": float(gross.death_claims.sum()),
            "projection_months": gross.projection_months,
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"✓ {name}: {len(results)} cohorts → {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flat-only", action="store_true",
                        help="Only generate flat-mortality baseline (no SOA tables)")
    args = parser.parse_args()

    val_date = date(2026, 4, 1)

    # Always generate the flat baseline
    flat_inputs = PipelineInputs(
        mortality=MortalityConfig(source="flat", flat_qx=0.003),
        lapse=LapseConfig(),
        deal=DealConfig(
            treaty_type="YRT", cession_pct=0.90, yrt_loading=0.10,
            discount_rate=0.06, hurdle_rate=0.10, projection_years=20,
            valuation_date=val_date,
        ),
    )
    run_and_save(flat_inputs, "golden_flat")

    if not args.flat_only:
        yrt_inputs = PipelineInputs(
            mortality=MortalityConfig(source="SOA_VBT_2015"),
            lapse=LapseConfig(),
            deal=DealConfig(
                treaty_type="YRT", cession_pct=0.90, yrt_loading=0.10,
                discount_rate=0.06, hurdle_rate=0.10, projection_years=20,
                valuation_date=val_date,
            ),
        )
        run_and_save(yrt_inputs, "golden_yrt")

    print("\nDone. Commit the files in tests/qa/golden_outputs/.")


if __name__ == "__main__":
    main()
```

---

## Claude Code Routine Definitions

### Routine 1: `qa-on-pr` — GitHub trigger

**Trigger:** `pull_request.opened` against `main`

**Repos:** `jonathancrawford05/polaris-re`

**Connectors:** GitHub (for PR comments)

**Prompt:**

```
You are a QA actuary reviewing a polaris-re pull request.

1. Run `uv sync --all-extras` to install all dependencies.
2. Run `uv run pytest tests/qa/ -v --tb=long -x` to execute the QA test suite.
3. Run `uv run polaris price --inforce data/qa/golden_inforce.csv --config data/qa/golden_config_flat.json -o /tmp/pr_flat.json` for the flat-mortality smoke test.
4. If SOA VBT 2015 tables exist in data/mortality_tables/, also run:
   `uv run polaris price --inforce data/qa/golden_inforce.csv --config data/qa/golden_config_yrt.json -o /tmp/pr_yrt.json`
5. Compare output JSON files against tests/qa/golden_outputs/ baselines.

Report format — post as a PR comment:

## QA Report

### Test Suite
- ✅/❌ tests/qa/test_pipeline_golden.py
- ✅/❌ tests/qa/test_dashboard_flows.py
- ✅/❌ tests/qa/test_cli_golden.py

### Golden Output Comparison
For each cohort (TERM, WHOLE_LIFE), report:
| Metric | Baseline | This PR | Delta |
|--------|----------|---------|-------|
| Cedant PV Profits | ... | ... | ... |
| Cedant Profit Margin | ... | ... | ... |
| Reinsurer PV Profits | ... | ... | ... |

### Findings
If any test failed or golden output drifted beyond tolerance ($500):
- Describe the failure
- Identify the likely root cause by examining the PR diff
- Classify severity: BLOCKER / WARNING / INFO

If all pass: "✅ All QA checks passed. No regressions detected."
```

### Routine 2: `qa-nightly` — Scheduled trigger

**Trigger:** Nightly at 02:00 ET

**Repos:** `jonathancrawford05/polaris-re`

**Connectors:** GitHub

**Prompt:**

```
You are performing a nightly QA sweep of polaris-re on the main branch.

1. Run `uv sync --all-extras`
2. Run the full test suite: `uv run pytest tests/ -v --tb=long`
3. Run the QA suite: `uv run pytest tests/qa/ -v --tb=long`
4. Run pricing across ALL golden configs:
   - data/qa/golden_config_yrt.json
   - data/qa/golden_config_coins.json
   - data/qa/golden_config_policy_cession.json
   - data/qa/golden_config_flat.json
   Each with --inforce data/qa/golden_inforce.csv
5. Run scenario analysis on a single-product subset:
   Filter golden_inforce.csv to TERM-only policies, run polaris scenario
6. Compare all outputs against golden baselines

If any failures or drift are detected, produce a findings document:

Create docs/QA_FINDINGS_{YYYY-MM-DD}.md using this template:

# QA Findings — {date}

## Summary
{one paragraph: what was tested, what failed}

## Issues

### Issue 1: {short title}
- **Severity:** BLOCKER / WARNING / INFO
- **Symptom:** {what the test reported}
- **Root cause hypothesis:** {your analysis of the code}
- **Suggested fix:** {concrete code change}
- **Acceptance criteria:** {how to verify the fix}

## Regression Status
{table of all golden output metrics vs baseline}

Open a draft PR on branch `qa/nightly-{date}` with the findings doc.
If all checks pass, do not open a PR — just log the result.
```

### Routine 3: `qa-on-demand` — API trigger

**Trigger:** API endpoint (POST with bearer token)

**Repos:** `jonathancrawford05/polaris-re`

**Prompt:**

```
You are a QA actuary for polaris-re. The user has sent a specific
investigation request in the trigger payload text.

1. Run `uv sync --all-extras`
2. Read the request carefully
3. Execute the investigation using the CLI, pytest, or direct Python
4. Report findings structured as:
   - What was tested
   - What was found
   - Recommended action (if any)

Default to running against data/qa/golden_inforce.csv unless the
request specifies different inputs.
```

---

## Setup Instructions

### Creating the routines

1. Navigate to `claude.ai/code/routines` (or type `/schedule` in Claude Code CLI)
2. Create each routine with the prompt, repo, and trigger type above
3. For `qa-on-pr`: set GitHub trigger to `pull_request.opened` on `main`
4. For `qa-nightly`: set schedule to nightly
5. For `qa-on-demand`: note the endpoint URL and bearer token

### Generating initial golden baselines

Before the routines can detect regressions, baselines must exist:

```bash
cd /path/to/polaris-re
uv sync --all-extras

# Generate flat baseline (always works)
uv run python tests/qa/generate_golden.py --flat-only

# Generate SOA baseline (requires mortality tables)
uv run python tests/qa/generate_golden.py

# Verify
uv run pytest tests/qa/ -v

# Commit the baselines
git add data/qa/ tests/qa/
git commit -m "feat: add golden QA inputs and baselines"
```

### Daily routine budget (Max plan: 15/day)

| Routine | Trigger rate | Runs/day |
|---------|-------------|----------|
| qa-on-pr | ~2-3 PRs/day | 2-3 |
| qa-nightly | 1/night | 1 |
| qa-on-demand | ad hoc | 1-2 |
| **Total** | | **4-6** |

Well within the 15-run Max plan cap. Leaves headroom for other routines.

---

## Acceptance Criteria

1. `data/qa/golden_inforce.csv` loads via `InforceBlock.from_csv()` without
   error and produces 2 cohorts (TERM, WL) via `iter_cohorts()`.
2. `tests/qa/test_pipeline_golden.py` passes — golden baselines generated
   and committed.
3. `tests/qa/test_dashboard_flows.py` passes — all 7 pages render via
   AppTest, session state defaults match `DealConfig`.
4. `tests/qa/test_cli_golden.py` passes — CLI commands complete on golden
   inputs.
5. `uv run pytest tests/qa/ -v` passes with zero failures (SOA-dependent
   tests skip gracefully when tables are absent).
6. Golden baseline files committed in `tests/qa/golden_outputs/`.
7. Routine prompts are ready to paste into `claude.ai/code/routines`.

## Out of Scope

- Playwright/browser-based visual regression testing. The AppTest approach
  covers functional and state-flow testing. Visual testing can be added
  later if needed.
- Automatic routine creation via API. Routines are created manually in the
  UI for now.
- ML model overlay testing (mortality/lapse). Not yet stable enough for
  golden baselines.
- IFRS 17 BBA golden outputs. The IFRS 17 page should be exercised via
  AppTest (renders without error) but numerical baselines are deferred
  until the measurement logic stabilises.

## Notes for the Implementer

- `AppTest.from_file()` resolves paths relative to the working directory.
  Run tests from the repo root (`uv run pytest tests/qa/`).
- `AppTest` cannot simulate `st.file_uploader` directly. Use session state
  injection (see `TestDealPricingWithInjectedState`) for any test that
  needs an inforce block.
- The golden baseline generation script (`generate_golden.py`) must be run
  from the repo root so `data/qa/golden_inforce.csv` resolves correctly.
- `AppTest` creates a real Streamlit runtime. Tests may be slow (~2-5s each).
  Mark the entire `tests/qa/` directory with `@pytest.mark.slow` if needed,
  but keep them in the default `make test` run initially to catch regressions.
- The `cession_slider_bounds` test in `test_dashboard_flows.py` depends on
  the Assumptions page rendering sliders in a discoverable order. If the
  Assumptions page layout changes, this test may need adjustment — search
  for sliders by label text rather than index.

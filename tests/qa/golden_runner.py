"""Shared, config-driven golden-regression machinery.

The committed ``data/qa/golden_config_*.json`` files are the **single source of
truth** for both the baseline generator (``generate_golden.py``) and the
pipeline regression test (``test_pipeline_golden.py``). Each config is loaded
through the *same* parser the CLI uses (``_parse_config_to_pipeline_inputs``),
priced on the shared golden inforce block, and compared against / written to a
committed baseline in ``golden_outputs/``.

Previously the generator and the test each hand-built ``PipelineInputs`` in
Python for only ``flat`` and ``yrt``, so the ``coins`` and ``policy_cession``
configs shipped without byte-level baselines (covered by CLI smoke tests only)
and the two in-code input sets could silently drift from the committed JSON
configs the CLI actually consumes. Enumerating the JSON configs here closes both
gaps (PR #103 review P2; PRODUCT_DIRECTION_2026-06-18 Promoted Follow-up).

This module imports **no pytest**, so the generator script can import it
directly (``import golden_runner`` when run as ``python tests/qa/generate_golden.py``,
``from .golden_runner import …`` under pytest).
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

# The config → PipelineInputs translation lives in the CLI and is the exact path
# `polaris price --config …` takes; reuse it so the goldens bind to what the CLI
# actually produces rather than a parallel hand-built copy (the drift this PR
# fixes). These are private helpers, but they are the single source of truth for
# config parsing — if they change, the goldens should reflect that.
from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.cli import _load_json_config, _parse_config_to_pipeline_inputs
from polaris_re.pipeline import (
    PipelineInputs,
    build_pipeline,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    iter_cohorts,
    load_inforce,
)
from polaris_re.products.dispatch import get_product_engine

QA_DATA_DIR = Path("data/qa")
GOLDEN_CSV = QA_DATA_DIR / "golden_inforce.csv"
GOLDEN_CONFIG_GLOB = "golden_config_*.json"
GOLDEN_OUTPUTS_DIR = Path(__file__).parent / "golden_outputs"

# Comparison tolerances (mirror the prior test_pipeline_golden thresholds).
ABS_TOL_DOLLARS = 500.0
ABS_TOL_PCT = 0.005

# A per-cohort golden metric value: dollar/ratio floats, integer counts, or None
# (IRR / breakeven when the cash flows have no sign change). Narrowing from a bare
# ``object`` lets the numeric comparison call ``float(...)`` without a cast.
type MetricValue = float | int | None
type GoldenResult = dict[str, dict[str, MetricValue]]

# Metrics compared against the baseline, split by tolerance class.
_DOLLAR_METRICS = (
    "cedant_pv_profits",
    "reinsurer_pv_profits",
    "gross_total_premiums",
    "gross_total_claims",
)
_PCT_METRICS = ("cedant_profit_margin", "reinsurer_profit_margin")

_MORTALITY_DIR = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"


def has_soa_tables() -> bool:
    """True when the SOA VBT 2015 tables required by non-flat configs are present."""
    return (_MORTALITY_DIR / "soa_vbt_2015_male_ns.csv").exists()


@dataclass(frozen=True)
class GoldenCase:
    """One golden config: its baseline name, source JSON, and SOA-table need."""

    name: str  # baseline name, e.g. "golden_coins"
    config_path: Path  # e.g. data/qa/golden_config_coins.json
    needs_soa: bool  # True when mortality.source != "flat"

    @property
    def baseline_path(self) -> Path:
        return GOLDEN_OUTPUTS_DIR / f"{self.name}.json"


def _baseline_name(config_path: Path) -> str:
    """``golden_config_coins.json`` → ``golden_coins`` (the baseline file stem)."""
    return config_path.stem.replace("golden_config_", "golden_")


def discover_golden_cases() -> list[GoldenCase]:
    """Enumerate every ``data/qa/golden_config_*.json`` as a GoldenCase.

    Sorted by name for deterministic test/parametrize ordering. A config whose
    mortality source is not ``flat`` needs the SOA tables (``needs_soa``).
    """
    cases: list[GoldenCase] = []
    for config_path in sorted(QA_DATA_DIR.glob(GOLDEN_CONFIG_GLOB)):
        raw = json.loads(config_path.read_text())
        source = raw.get("mortality", {}).get("source", "SOA_VBT_2015")
        cases.append(
            GoldenCase(
                name=_baseline_name(config_path),
                config_path=config_path,
                needs_soa=(source != "flat"),
            )
        )
    return cases


def load_inputs(case: GoldenCase) -> PipelineInputs:
    """Parse a case's config JSON into PipelineInputs via the CLI's own parser."""
    raw = _load_json_config(case.config_path)
    inputs, _policies = _parse_config_to_pipeline_inputs(raw)
    return inputs


def run_pricing(inputs: PipelineInputs) -> GoldenResult:
    """Price the golden inforce block under ``inputs``; return per-cohort metrics.

    This is the single result-extraction path shared by the generator and the
    regression test, so a baseline can never disagree with what the test
    recomputes for the same config. Mirrors the CLI pricing pipeline (gross
    projection → treaty → cedant/reinsurer profit test) for each product cohort.
    """
    inforce = load_inforce(csv_path=GOLDEN_CSV)
    inf, assumptions, config = build_pipeline(inforce, inputs)
    results: GoldenResult = {}

    for product_type, cohort_inforce in iter_cohorts(inf):
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
            inforce_arg = cohort_inforce if inputs.deal.use_policy_cession else None
            # build_treaty is annotated `object | None`; mirror the CLI's ignore.
            net, ceded = treaty.apply(gross, inforce=inforce_arg)  # type: ignore[attr-defined]
        else:
            net, ceded = gross, None

        cedant = ProfitTester(cashflows=net, hurdle_rate=inputs.deal.hurdle_rate).run()
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
            "reinsurer_pv_profits": (reinsurer.pv_profits if reinsurer else None),
            "reinsurer_profit_margin": (reinsurer.profit_margin if reinsurer else None),
            "gross_total_premiums": float(gross.gross_premiums.sum()),
            "gross_total_claims": float(gross.death_claims.sum()),
            "projection_months": gross.projection_months,
        }

    return results


def save_golden(results: GoldenResult, name: str) -> Path:
    """Write a golden baseline as indented JSON; return its path."""
    GOLDEN_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_OUTPUTS_DIR / f"{name}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    return path


def load_golden(name: str) -> GoldenResult | None:
    """Load a committed baseline, or None if it has not been generated yet."""
    path = GOLDEN_OUTPUTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    loaded: GoldenResult = json.loads(path.read_text())
    return loaded


def compare_golden(
    actual: GoldenResult,
    expected: GoldenResult,
    label: str,
) -> list[str]:
    """Compare actual vs expected per-cohort metrics; return discrepancy strings."""
    failures: list[str] = []

    for cohort_key in expected:
        if cohort_key not in actual:
            failures.append(f"{label}/{cohort_key}: missing from actual")
            continue

        exp = expected[cohort_key]
        act = actual[cohort_key]

        for metric in _DOLLAR_METRICS:
            e_val = exp.get(metric)
            a_val = act.get(metric)
            if e_val is None and a_val is None:
                continue
            if e_val is None or a_val is None:
                failures.append(f"{label}/{cohort_key}/{metric}: expected={e_val}, actual={a_val}")
                continue
            if abs(float(a_val) - float(e_val)) > ABS_TOL_DOLLARS:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={float(e_val):,.2f}, "
                    f"actual={float(a_val):,.2f}, "
                    f"delta={float(a_val) - float(e_val):+,.2f}"
                )

        for metric in _PCT_METRICS:
            e_val = exp.get(metric)
            a_val = act.get(metric)
            if e_val is None and a_val is None:
                continue
            if e_val is None or a_val is None:
                failures.append(f"{label}/{cohort_key}/{metric}: expected={e_val}, actual={a_val}")
                continue
            if abs(float(a_val) - float(e_val)) > ABS_TOL_PCT:
                failures.append(
                    f"{label}/{cohort_key}/{metric}: "
                    f"expected={float(e_val):.4%}, "
                    f"actual={float(a_val):.4%}"
                )

    return failures

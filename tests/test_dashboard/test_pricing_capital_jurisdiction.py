"""Dashboard Deal-Pricing jurisdiction-selector tests (Epic 3, Slice 4b).

Slice 4a routed the CLI ``--capital`` flag and the API ``capital_model`` field
through the shared ``capital_model_for`` registry, but the Streamlit Deal Pricing
page still hard-coded LICAT: ``_run_pricing_for_cohort`` ran capital ONLY when
``capital_model_id == "licat"`` and silently dropped any other id into the
no-capital branch, so US RBC / EU Solvency II were unreachable from the
dashboard. Slice 4b routes the dashboard through the same registry.

These tests drive ``_run_pricing_for_cohort`` directly (it does not touch session
state and, for ``treaty_type="None (Gross)"`` with ``show_yrt_info=False``, emits
no Streamlit UI), asserting that each registry jurisdiction now produces a
``ProfitResultWithCapital`` and that the three standards yield genuinely distinct
required capital on the same block — the dashboard analogue of Slice 4a's
three-way CLI/API peak-capital test.
"""

import numpy as np
import pytest

from polaris_re.analytics.profit_test import ProfitResultWithCapital, ProfitTestResult
from polaris_re.dashboard.views.pricing import (
    _CAPITAL_MODEL_CHOICES,
    _run_pricing_for_cohort,
)
from polaris_re.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
    load_inforce,
)


def _term_pipeline():
    """A minimal single-cohort TERM pipeline (no wall-clock dependence)."""
    policies = [
        {
            "policy_id": "P1",
            "issue_age": 45,
            "attained_age": 45,
            "sex": "M",
            "smoker": False,
            "face_amount": 1_000_000.0,
            "annual_premium": 3_000.0,
            "policy_term": 20,
            "duration_inforce": 0,
            "issue_date": "2026-04-01",
            "valuation_date": "2026-04-01",
            "product_type": "TERM",
        }
    ]
    inforce = load_inforce(policies_dict=policies)
    inputs = PipelineInputs(
        mortality=MortalityConfig(source="flat", flat_qx=0.003),
        lapse=LapseConfig(),
        deal=DealConfig(product_type="TERM", projection_years=10),
    )
    inf, assumptions, config = build_pipeline(inforce, inputs)
    return inf, assumptions, config


def _price(capital_model_id: str | None) -> ProfitTestResult:
    inf, assumptions, config = _term_pipeline()
    cohort = _run_pricing_for_cohort(
        cohort_id="TERM",
        cohort_inforce=inf,
        assumption_set=assumptions,
        config=config,
        treaty_type="None (Gross)",
        use_policy_cession=False,
        hurdle_rate=0.10,
        parity_label="test_capital_jurisdiction",
        show_yrt_info=False,
        capital_model_id=capital_model_id,
    )
    return cohort.result


def test_choices_map_to_registry_ids() -> None:
    """The selector exposes None plus the three registry jurisdictions."""
    assert set(_CAPITAL_MODEL_CHOICES.values()) == {None, "licat", "rbc", "solvency2"}


def test_no_capital_selection_runs_plain_profit_test() -> None:
    result = _price(None)
    assert not isinstance(result, ProfitResultWithCapital)


@pytest.mark.parametrize("model_id", ["licat", "rbc", "solvency2"])
def test_each_jurisdiction_produces_capital(model_id: str) -> None:
    """RBC / Solvency II were unreachable pre-Slice-4b; now each yields capital."""
    result = _price(model_id)
    assert isinstance(result, ProfitResultWithCapital)
    assert result.peak_capital > 0.0


def test_three_standards_give_distinct_capital() -> None:
    """The registry actually swaps the model: peaks differ across standards."""
    peaks = {m: _price(m).peak_capital for m in ("licat", "rbc", "solvency2")}
    values = list(peaks.values())
    # All three are distinct (pairwise) — a regression guard that the selector
    # is not silently collapsing to a single calculator.
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            assert not np.isclose(values[i], values[j]), f"capital collapsed: {peaks}"

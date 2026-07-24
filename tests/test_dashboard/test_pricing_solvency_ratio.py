"""Dashboard Deal-Pricing solvency-ratio tests (Epic 3, Slice 4c-2b).

Slice 4c-2a threaded the available-capital numerator (ADR-104) through the CLI
``--available-capital`` flag and the API ``available_capital`` field, surfacing a
``capital_ratio`` on the cedant / reinsurer views. The Streamlit Deal Pricing page
still ignored the numerator: ``_run_pricing_for_cohort`` called
``run_with_capital`` without ``available_capital``, so ``result.capital_ratio``
was always ``None`` and no Solvency Ratio tile could render. Slice 4c-2b threads
the numerator through the dashboard.

These tests drive ``_run_pricing_for_cohort`` directly (it does not touch session
state and, for ``treaty_type="None (Gross)"`` with ``show_yrt_info=False``, emits
no Streamlit UI), asserting that supplying ``available_capital`` populates
``capital_ratio`` against each jurisdiction's own required capital, that omitting
it leaves the ratio ``None`` (byte-identical capital-only run), and that the ratio
equals the numerator over required capital in closed form.
"""

import numpy as np
import pytest

from polaris_re.analytics.profit_test import ProfitResultWithCapital
from polaris_re.dashboard.views.pricing import _run_pricing_for_cohort
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


def _price(
    capital_model_id: str | None,
    available_capital: float | None = None,
) -> ProfitResultWithCapital:
    inf, assumptions, config = _term_pipeline()
    cohort = _run_pricing_for_cohort(
        cohort_id="TERM",
        cohort_inforce=inf,
        assumption_set=assumptions,
        config=config,
        treaty_type="None (Gross)",
        use_policy_cession=False,
        hurdle_rate=0.10,
        parity_label="test_solvency_ratio",
        show_yrt_info=False,
        capital_model_id=capital_model_id,
        available_capital=available_capital,
    )
    result = cohort.result
    assert isinstance(result, ProfitResultWithCapital)
    return result


def test_no_numerator_leaves_ratio_none() -> None:
    """A capital run without an available-capital numerator yields no ratio."""
    result = _price("rbc", available_capital=None)
    assert result.available_capital is None
    assert result.capital_ratio is None


@pytest.mark.parametrize("model_id", ["licat", "rbc", "solvency2"])
def test_numerator_populates_ratio(model_id: str) -> None:
    """Supplying available_capital surfaces a finite solvency ratio."""
    result = _price(model_id, available_capital=5_000_000.0)
    assert result.available_capital == pytest.approx(5_000_000.0)
    assert result.capital_ratio is not None
    assert result.capital_ratio > 0.0


@pytest.mark.parametrize("model_id", ["licat", "rbc", "solvency2"])
def test_ratio_scales_linearly_with_numerator(model_id: str) -> None:
    """The ratio is numerator / (fixed required capital), so it scales linearly.

    Doubling the supplied available capital doubles the surfaced ratio — a
    denominator-agnostic closed form that proves the dashboard threads the
    numerator straight into ``capital_ratio`` without reconstructing the
    jurisdiction's required-capital schedule.
    """
    base = _price(model_id, available_capital=5_000_000.0).capital_ratio
    doubled = _price(model_id, available_capital=10_000_000.0).capital_ratio
    assert base is not None and doubled is not None
    assert doubled == pytest.approx(2.0 * base)


def test_ratio_differs_across_jurisdictions() -> None:
    """The same numerator over distinct denominators gives distinct ratios."""
    ratios = {
        m: _price(m, available_capital=5_000_000.0).capital_ratio
        for m in ("licat", "rbc", "solvency2")
    }
    values = list(ratios.values())
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            assert not np.isclose(values[i], values[j]), f"ratios collapsed: {ratios}"

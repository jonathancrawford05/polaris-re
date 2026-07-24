"""Dashboard Deal-Pricing versioned-improvement selector tests (mi-dashboard Slice 2).

The A4' epic (ADR-139..154) built an experience-derived mortality-improvement
capability whose frozen, audited ``ImprovementScale.CUSTOM`` bases are persisted
in the append-only :class:`AssumptionVersionStore` (``polaris experience save``)
and can drive a priced run via the CLI ``--improvement-version`` flag /
``mortality.improvement_version_id`` config key (ADR-148). Slice 2 surfaces the
*dashboard* half of that IMPORTANT #12 item: the Deal Pricing page now lets an
actuary pick a stored version, which overrides the Assumptions-page improvement
for that run.

These tests drive the mechanism directly (no Streamlit context needed):

* ``DealConfig.to_dict()`` round-trips the new ``improvement_version_id`` field
  (the dashboard parity surface must carry it);
* a dashboard-selected version — applied as
  ``AssumptionSet.model_copy(update={"improvement": load_improvement_version(id)})``
  — prices **byte-identically** to the CLI ``--improvement-version`` path built by
  ``build_assumption_set``, and materially differs from the improvement-free run
  (so the override actually bites).

The AppTest end-to-end flow (widget → echoed session config) lives in
``tests/qa/test_dashboard_flows.py``.

All ages / years / dates are pinned literals (ADR-074 — never the wall clock).
"""

from datetime import date

import numpy as np

from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement
from polaris_re.assumptions.version_store import AssumptionVersionStore
from polaris_re.dashboard.components.state import get_deal_config
from polaris_re.dashboard.views.pricing import _run_pricing_for_cohort
from polaris_re.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
    load_improvement_version,
    load_inforce,
)

# A synthetic experience-derived CUSTOM improvement: a flat 2%/yr annual
# improvement over ages 40-70 and calendar years 2026-2045 (base year 2025).
# Constant across the grid so the recovered mortality is easy to reason about
# and the projection unambiguously improves the flat base rate.
_STUDY_DATE = date(2025, 12, 31)


def _make_custom_improvement() -> MortalityImprovement:
    ages = np.arange(40, 71, dtype=np.int64)
    years = np.arange(2026, 2046, dtype=np.int64)
    mi_grid = np.full((ages.size, years.size), 0.02, dtype=np.float64)
    mi = MortalityImprovement.from_grid(ages, years, mi_grid, ultimate_rate=0.02)
    assert mi.scale is ImprovementScale.CUSTOM
    return mi


def _seed_store(root) -> str:
    """Persist one CUSTOM improvement version under ``root`` and return its id."""
    store = AssumptionVersionStore(root)
    version = store.save(
        _make_custom_improvement(),
        study_date=_STUDY_DATE,
        credibility=0.8,
        label="unit-test-basis",
    )
    return version.version_id


def _term_inputs(improvement_version_id: str | None, store_dir) -> PipelineInputs:
    return PipelineInputs(
        mortality=MortalityConfig(
            source="flat",
            flat_qx=0.01,
            improvement_version_id=improvement_version_id,
            improvement_store_dir=store_dir,
        ),
        lapse=LapseConfig(),
        deal=DealConfig(product_type="TERM", treaty_type="YRT", projection_years=15),
    )


def _term_inforce():
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
            "issue_date": "2026-01-01",
            "valuation_date": "2026-01-01",
            "product_type": "TERM",
        }
    ]
    return load_inforce(policies_dict=policies)


def _price(assumption_set, config, inforce):
    cfg = get_deal_config()
    cfg["treaty_type"] = "YRT"
    cfg["cession_pct"] = 0.90
    return _run_pricing_for_cohort(
        cohort_id="TERM",
        cohort_inforce=inforce,
        assumption_set=assumption_set,
        config=config,
        treaty_type="YRT",
        use_policy_cession=False,
        hurdle_rate=0.10,
        parity_label="test_improvement_version",
        show_yrt_info=False,
    )


def test_deal_config_to_dict_includes_improvement_version_id() -> None:
    """to_dict() round-trips the new improvement_version_id (default None + set)."""
    d = DealConfig().to_dict()
    assert "improvement_version_id" in d
    assert d["improvement_version_id"] is None

    d_set = DealConfig(improvement_version_id="2025-12-31-001").to_dict()
    assert d_set["improvement_version_id"] == "2025-12-31-001"


def test_selected_version_prices_identically_to_cli(tmp_path) -> None:
    """A dashboard-applied versioned basis prices byte-identically to the CLI path.

    The dashboard override —
    ``assumptions.model_copy(update={"improvement": load_improvement_version(id)})``
    — must reproduce, cash flow for cash flow, the ``build_assumption_set`` run
    the CLI ``--improvement-version`` flag produces (both load the same frozen
    scale from the same store), and must differ from the improvement-free run.
    """
    root = tmp_path / "assumption_versions"
    version_id = _seed_store(root)
    inforce = _term_inforce()

    # CLI path: improvement_version_id threaded onto MortalityConfig, loaded by
    # build_assumption_set into AssumptionSet.improvement.
    _, cli_assumptions, config = build_pipeline(inforce, _term_inputs(version_id, root))
    cli_cohort = _price(cli_assumptions, config, inforce)

    # Dashboard path: base assumptions carry NO improvement; the selector applies
    # the loaded version via model_copy — exactly what page_pricing does.
    _, base_assumptions, base_config = build_pipeline(inforce, _term_inputs(None, root))
    assert base_assumptions.improvement is None
    loaded = load_improvement_version(version_id, store_dir=root)
    effective = base_assumptions.model_copy(update={"improvement": loaded})
    dash_cohort = _price(effective, base_config, inforce)

    # The frozen scale the dashboard applies is the same one the CLI loaded.
    assert cli_assumptions.improvement == loaded

    # Byte-identical gross death claims: the dashboard override drives the run
    # exactly as the CLI flag does.
    np.testing.assert_array_equal(dash_cohort.gross.death_claims, cli_cohort.gross.death_claims)
    np.testing.assert_allclose(
        dash_cohort.result.pv_profits, cli_cohort.result.pv_profits, rtol=0, atol=0
    )

    # And it materially bites: an improvement-free run has strictly higher
    # cumulative death claims than the improved run (mortality is scaled down).
    no_improvement_cohort = _price(base_assumptions, base_config, inforce)
    assert dash_cohort.gross.death_claims.sum() < no_improvement_cohort.gross.death_claims.sum()

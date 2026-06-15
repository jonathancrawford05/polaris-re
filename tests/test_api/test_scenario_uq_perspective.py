"""Tests for reinsurer-vs-cedant profit-test perspective on the REST scenario /
uq endpoints (ADR-078).

ADR-077 added the additive ``perspective`` parameter to ``ScenarioRunner`` /
``MonteCarloUQ`` and defaulted the *CLI* ``scenario`` / ``uq`` commands to the
reinsurer view, but the FastAPI ``POST /api/v1/scenario`` and ``/api/v1/uq``
endpoints still reported the cedant ``net`` view — the same primary-use-case
correctness gap on another product surface. ADR-078 closes it: both endpoints
accept ``perspective`` (default ``"reinsurer"``), pass it through to the runner,
downgrade to ``cedant`` when no treaty is configured, and surface the effective
perspective in the response.

A 50% cession is degenerate (net == ceded), so the differential tests use an
80% coinsurance deal where the two views are materially different — the same
blind spot ADR-077 documented.
"""

import numpy as np
from fastapi.testclient import TestClient

from polaris_re.analytics.scenario import ScenarioRunner
from polaris_re.analytics.uq import MonteCarloUQ, UQParameters
from polaris_re.api import main as api_main
from polaris_re.api.main import (
    ScenarioRequest,
    UQRequest,
    app,
)

client = TestClient(app)

# An 80% coinsurance deal — non-degenerate so reinsurer != cedant.
_POLICY = {
    "policy_id": "PERSP001",
    "issue_age": 40,
    "attained_age": 40,
    "sex": "M",
    "smoker": False,
    "underwriting_class": "PREFERRED",
    "face_amount": 500_000.0,
    "annual_premium": 1_200.0,
    "policy_term": 20,
    "duration_inforce": 0,
    "issue_date": "2025-01-01",
    "valuation_date": "2025-01-01",
}


def _coins_payload(**overrides: object) -> dict:
    payload: dict = {
        "policies": [_POLICY],
        "treaty_type": "Coinsurance",
        "cession_pct": 0.80,
        "projection_horizon_years": 20,
    }
    payload.update(overrides)
    return payload


def _direct_scenario_base_pv(perspective: str) -> float:
    """Build the same components the endpoint builds and run a direct
    ``ScenarioRunner`` for the requested perspective — the closed-form anchor.
    """
    req = ScenarioRequest(**_coins_payload())
    inforce, assumptions, config = api_main._build_components(
        policies_in=req.policies,
        projection_horizon_years=req.projection_horizon_years,
        discount_rate=req.discount_rate,
        flat_qx=req.flat_qx,
        flat_lapse=req.flat_lapse,
        product_type_str=req.product_type,
        acquisition_cost_per_policy=req.acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=req.maintenance_cost_per_policy_per_year,
    )
    gross = api_main._run_gross_projection(inforce, assumptions, config)
    total_face = sum(p.face_amount for p in req.policies)
    treaty = api_main._build_treaty(
        treaty_type=req.treaty_type,
        gross=gross,
        face_amount=total_face,
        cession_pct=req.cession_pct,
        yrt_loading=req.yrt_loading,
        modco_interest_rate=req.modco_interest_rate,
    )
    runner = ScenarioRunner(
        inforce=inforce,
        base_assumptions=assumptions,
        config=config,
        treaty=treaty,
        hurdle_rate=req.hurdle_rate,
        perspective=perspective,  # type: ignore[arg-type]
    )
    results = runner.run()
    base = results.base_case()
    assert base is not None
    return base.pv_profits


def _scenario_base_pv(data: dict) -> float:
    base = next(s for s in data["scenarios"] if s["scenario_name"] == "BASE")
    return base["pv_profits"]


# ---------------------------------------------------------------------------
# Scenario endpoint
# ---------------------------------------------------------------------------


class TestScenarioPerspective:
    def test_default_is_reinsurer(self):
        data = client.post("/api/v1/scenario", json=_coins_payload()).json()
        assert data["perspective"] == "reinsurer"

    def test_explicit_cedant_reported(self):
        data = client.post("/api/v1/scenario", json=_coins_payload(perspective="cedant")).json()
        assert data["perspective"] == "cedant"

    def test_reinsurer_differs_from_cedant(self):
        """Guards the degenerate-50%-cession blind spot: at 80% cession the two
        perspectives must give materially different BASE PV profits."""
        reins = _scenario_base_pv(
            client.post("/api/v1/scenario", json=_coins_payload(perspective="reinsurer")).json()
        )
        cedant = _scenario_base_pv(
            client.post("/api/v1/scenario", json=_coins_payload(perspective="cedant")).json()
        )
        assert not np.isclose(reins, cedant)
        # Reinsurer holds 80% of the ceded economics; cedant retains 20%.
        assert abs(reins) > abs(cedant)

    def test_reinsurer_matches_direct_runner(self):
        data = client.post("/api/v1/scenario", json=_coins_payload(perspective="reinsurer")).json()
        np.testing.assert_allclose(
            _scenario_base_pv(data), _direct_scenario_base_pv("reinsurer"), rtol=1e-12
        )

    def test_cedant_matches_direct_runner(self):
        data = client.post("/api/v1/scenario", json=_coins_payload(perspective="cedant")).json()
        np.testing.assert_allclose(
            _scenario_base_pv(data), _direct_scenario_base_pv("cedant"), rtol=1e-12
        )

    def test_invalid_perspective_rejected(self):
        resp = client.post("/api/v1/scenario", json=_coins_payload(perspective="cedent"))
        assert resp.status_code == 422

    def test_no_treaty_downgrades_to_cedant(self):
        """With no treaty the reinsurer view is undefined and is downgraded."""
        data = client.post(
            "/api/v1/scenario",
            json=_coins_payload(treaty_type=None, perspective="reinsurer"),
        ).json()
        assert data["perspective"] == "cedant"


# ---------------------------------------------------------------------------
# UQ endpoint
# ---------------------------------------------------------------------------


def _uq_payload(**overrides: object) -> dict:
    payload: dict = {
        "policies": [_POLICY],
        "treaty_type": "Coinsurance",
        "cession_pct": 0.80,
        "projection_horizon_years": 20,
        "n_scenarios": 50,
        "seed": 7,
    }
    payload.update(overrides)
    return payload


def _direct_uq_base_pv(perspective: str) -> float:
    req = UQRequest(**_uq_payload())
    inforce, assumptions, config = api_main._build_components(
        policies_in=req.policies,
        projection_horizon_years=req.projection_horizon_years,
        discount_rate=req.discount_rate,
        flat_qx=req.flat_qx,
        flat_lapse=req.flat_lapse,
        product_type_str=req.product_type,
        acquisition_cost_per_policy=req.acquisition_cost_per_policy,
        maintenance_cost_per_policy_per_year=req.maintenance_cost_per_policy_per_year,
    )
    gross = api_main._run_gross_projection(inforce, assumptions, config)
    total_face = sum(p.face_amount for p in req.policies)
    treaty = api_main._build_treaty(
        treaty_type=req.treaty_type,
        gross=gross,
        face_amount=total_face,
        cession_pct=req.cession_pct,
        yrt_loading=req.yrt_loading,
        modco_interest_rate=req.modco_interest_rate,
    )
    runner = MonteCarloUQ(
        inforce=inforce,
        base_assumptions=assumptions,
        base_config=config,
        treaty=treaty,
        hurdle_rate=req.hurdle_rate,
        n_scenarios=req.n_scenarios,
        seed=req.seed,
        params=UQParameters(
            mortality_log_sigma=req.mortality_log_sigma,
            lapse_log_sigma=req.lapse_log_sigma,
            interest_rate_sigma=req.interest_rate_sigma,
        ),
        perspective=perspective,  # type: ignore[arg-type]
    )
    return runner.run().base_pv_profit


class TestUQPerspective:
    def test_default_is_reinsurer(self):
        data = client.post("/api/v1/uq", json=_uq_payload()).json()
        assert data["perspective"] == "reinsurer"

    def test_explicit_cedant_reported(self):
        data = client.post("/api/v1/uq", json=_uq_payload(perspective="cedant")).json()
        assert data["perspective"] == "cedant"

    def test_reinsurer_differs_from_cedant(self):
        reins = client.post("/api/v1/uq", json=_uq_payload(perspective="reinsurer")).json()
        cedant = client.post("/api/v1/uq", json=_uq_payload(perspective="cedant")).json()
        assert not np.isclose(reins["base_pv_profit"], cedant["base_pv_profit"])
        assert abs(reins["base_pv_profit"]) > abs(cedant["base_pv_profit"])

    def test_reinsurer_matches_direct_runner(self):
        data = client.post("/api/v1/uq", json=_uq_payload(perspective="reinsurer")).json()
        np.testing.assert_allclose(
            data["base_pv_profit"], _direct_uq_base_pv("reinsurer"), rtol=1e-12
        )

    def test_cedant_matches_direct_runner(self):
        data = client.post("/api/v1/uq", json=_uq_payload(perspective="cedant")).json()
        np.testing.assert_allclose(data["base_pv_profit"], _direct_uq_base_pv("cedant"), rtol=1e-12)

    def test_invalid_perspective_rejected(self):
        resp = client.post("/api/v1/uq", json=_uq_payload(perspective="bogus"))
        assert resp.status_code == 422

    def test_no_treaty_downgrades_to_cedant(self):
        data = client.post(
            "/api/v1/uq",
            json=_uq_payload(treaty_type=None, perspective="reinsurer"),
        ).json()
        assert data["perspective"] == "cedant"

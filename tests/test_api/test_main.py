"""
Tests for the Polaris RE REST API (polaris_re/api/main.py).

Uses FastAPI's TestClient (built on httpx) to test all endpoints
without running a live server.
"""

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared test policy payload
# ---------------------------------------------------------------------------

DEMO_POLICY = {
    "policy_id": "TEST001",
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


# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------


class TestSystemEndpoints:
    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_schema(self):
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_version_returns_200(self):
        response = client.get("/version")
        assert response.status_code == 200

    def test_version_response_schema(self):
        data = client.get("/version").json()
        assert "polaris_re" in data
        assert "python" in data

    def test_docs_available(self):
        """FastAPI should serve OpenAPI docs at /docs."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema_available(self):
        """OpenAPI JSON schema should be accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data


# ---------------------------------------------------------------------------
# /api/v1/price
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestPriceEndpoint:
    def test_price_returns_200(self):
        payload = {
            "policies": [DEMO_POLICY],
            "projection_horizon_years": 20,
            "discount_rate": 0.06,
            "hurdle_rate": 0.10,
            "cession_pct": 0.90,
        }
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 200, response.text

    def test_price_response_schema(self):
        payload = {"policies": [DEMO_POLICY]}
        data = client.post("/api/v1/price", json=payload).json()
        required_keys = {
            # Cedant (NET) view
            "hurdle_rate",
            "pv_profits",
            "pv_premiums",
            "profit_margin",
            "irr",
            "breakeven_year",
            "total_undiscounted_profit",
            "profit_by_year",
            # Reinsurer view (ADR-039)
            "reinsurer_pv_profits",
            "reinsurer_profit_margin",
            "reinsurer_irr",
            "reinsurer_breakeven_year",
            "reinsurer_total_undiscounted_profit",
            "reinsurer_profit_by_year",
            # Metadata
            "n_policies",
            "projection_months",
        }
        assert required_keys.issubset(data.keys())

    def test_price_n_policies_matches_request(self):
        """n_policies in response equals number of policies in request."""
        policies = [dict(DEMO_POLICY, policy_id=f"P{i}") for i in range(3)]
        data = client.post("/api/v1/price", json={"policies": policies}).json()
        assert data["n_policies"] == 3

    def test_price_profit_by_year_length(self):
        """profit_by_year should have length = projection_horizon_years."""
        payload = {"policies": [DEMO_POLICY], "projection_horizon_years": 10}
        data = client.post("/api/v1/price", json=payload).json()
        assert len(data["profit_by_year"]) == 10

    def test_price_hurdle_rate_reflected(self):
        """hurdle_rate in response should match request."""
        payload = {"policies": [DEMO_POLICY], "hurdle_rate": 0.12}
        data = client.post("/api/v1/price", json=payload).json()
        assert abs(data["hurdle_rate"] - 0.12) < 1e-9

    def test_price_capital_model_omitted_returns_null_capital_fields(self):
        """ADR-049: when capital_model is omitted, capital fields are null."""
        payload = {"policies": [DEMO_POLICY]}
        data = client.post("/api/v1/price", json=payload).json()
        assert data["return_on_capital"] is None
        assert data["peak_capital"] is None
        assert data["pv_capital"] is None
        assert data["pv_capital_strain"] is None
        assert data["capital_adjusted_irr"] is None
        assert data["reinsurer_return_on_capital"] is None

    def test_price_capital_model_licat_populates_capital_block(self):
        """capital_model='licat' returns numeric peak_capital and pv_capital."""
        payload = {"policies": [DEMO_POLICY], "capital_model": "licat"}
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data["peak_capital"], (int, float))
        assert data["peak_capital"] > 0.0
        assert isinstance(data["pv_capital"], (int, float))
        assert data["pv_capital"] > 0.0
        assert isinstance(data["pv_capital_strain"], (int, float))
        # Reinsurer side too (default treaty is YRT with 90% cession)
        assert isinstance(data["reinsurer_peak_capital"], (int, float))
        assert data["reinsurer_peak_capital"] > 0.0

    def test_price_capital_model_invalid_value_returns_422(self):
        """Unknown capital_model values are rejected by Pydantic.

        ``solvency2`` is now a *valid* jurisdiction (ADR-101 Slice 4a), so the
        rejection probe uses a still-unrecognised id.
        """
        payload = {"policies": [DEMO_POLICY], "capital_model": "bogus"}
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 422, response.text

    @pytest.mark.parametrize("jurisdiction", ["rbc", "solvency2"])
    def test_price_capital_model_jurisdiction_populates_capital_block(self, jurisdiction: str):
        """capital_model='rbc'/'solvency2' returns numeric capital fields (ADR-101)."""
        payload = {"policies": [DEMO_POLICY], "capital_model": jurisdiction}
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data["peak_capital"], (int, float))
        assert data["peak_capital"] > 0.0
        assert isinstance(data["pv_capital"], (int, float))
        assert data["pv_capital"] > 0.0
        assert isinstance(data["pv_capital_strain"], (int, float))
        assert isinstance(data["reinsurer_peak_capital"], (int, float))
        assert data["reinsurer_peak_capital"] > 0.0

    def test_price_capital_licat_doubling_cession_shifts_reinsurer_capital_up(self):
        """Higher cession → larger reinsurer capital share (face_share scaling)."""
        low_payload = {
            "policies": [DEMO_POLICY],
            "capital_model": "licat",
            "cession_pct": 0.20,
        }
        high_payload = {
            "policies": [DEMO_POLICY],
            "capital_model": "licat",
            "cession_pct": 0.80,
        }
        low = client.post("/api/v1/price", json=low_payload).json()
        high = client.post("/api/v1/price", json=high_payload).json()
        assert high["reinsurer_peak_capital"] > low["reinsurer_peak_capital"]
        assert low["peak_capital"] > high["peak_capital"]

    def test_price_invalid_request_returns_422(self):
        """Missing required fields should return 422 Unprocessable Entity."""
        response = client.post("/api/v1/price", json={"policies": []})
        assert response.status_code == 422


@pytest.mark.slow
class TestPriceDateConsistencyGuard:
    """ADR-074 ingestion guard on the API path — inconsistent stored
    age/duration scalars are rejected with HTTP 422 (the same status the
    endpoints use for every semantic validation failure), never silently
    ignored."""

    def test_inconsistent_duration_returns_422(self):
        """Stored duration_inforce contradicting the dates is a 422."""
        bad = dict(
            DEMO_POLICY,
            issue_date="2020-01-01",
            valuation_date="2025-01-01",
            duration_inforce=0,  # dates imply 60 months
        )
        response = client.post("/api/v1/price", json={"policies": [bad]})
        assert response.status_code == 422, response.text
        assert "internally inconsistent" in response.json()["detail"]
        assert "duration_inforce=0" in response.json()["detail"]

    def test_inconsistent_attained_age_returns_422(self):
        """Stored attained_age contradicting issue_age + elapsed is a 422."""
        bad = dict(
            DEMO_POLICY,
            issue_date="2020-01-01",
            valuation_date="2025-01-01",
            duration_inforce=60,
            attained_age=40,  # issue_age 40 + 5 years implies 45
        )
        response = client.post("/api/v1/price", json={"policies": [bad]})
        assert response.status_code == 422, response.text
        assert "attained_age=40" in response.json()["detail"]

    def test_consistent_seasoned_policy_returns_200(self):
        """A seasoned policy whose scalars match the dates prices fine."""
        seasoned = dict(
            DEMO_POLICY,
            issue_date="2020-01-01",
            valuation_date="2025-01-01",
            duration_inforce=60,
            attained_age=45,
        )
        response = client.post("/api/v1/price", json={"policies": [seasoned]})
        assert response.status_code == 200, response.text


class TestScenarioEndpoint:
    def test_scenario_returns_200(self):
        payload = {"policies": [DEMO_POLICY]}
        response = client.post("/api/v1/scenario", json=payload)
        assert response.status_code == 200, response.text

    def test_scenario_response_schema(self):
        payload = {"policies": [DEMO_POLICY]}
        data = client.post("/api/v1/scenario", json=payload).json()
        assert "scenarios" in data
        assert "n_scenarios" in data
        assert isinstance(data["scenarios"], list)
        assert data["n_scenarios"] > 0

    def test_scenario_each_result_has_required_fields(self):
        payload = {"policies": [DEMO_POLICY]}
        data = client.post("/api/v1/scenario", json=payload).json()
        for s in data["scenarios"]:
            assert "scenario_name" in s
            assert "pv_profits" in s
            assert "profit_margin" in s


@pytest.mark.slow
class TestUQEndpoint:
    def test_uq_returns_200(self):
        payload = {"policies": [DEMO_POLICY], "n_scenarios": 20}
        response = client.post("/api/v1/uq", json=payload)
        assert response.status_code == 200, response.text

    def test_uq_response_schema(self):
        payload = {"policies": [DEMO_POLICY], "n_scenarios": 20}
        data = client.post("/api/v1/uq", json=payload).json()
        required_keys = {
            "n_scenarios",
            "seed",
            "base_pv_profit",
            "base_irr",
            "p5_pv_profit",
            "p50_pv_profit",
            "p95_pv_profit",
            "var_95",
            "cvar_95",
        }
        assert required_keys.issubset(data.keys())

    def test_uq_n_scenarios_reflected(self):
        """n_scenarios in response should match request."""
        payload = {"policies": [DEMO_POLICY], "n_scenarios": 30}
        data = client.post("/api/v1/uq", json=payload).json()
        assert data["n_scenarios"] == 30

    def test_uq_var_le_median(self):
        """VaR (5th percentile) should be ≤ median PV profit."""
        payload = {"policies": [DEMO_POLICY], "n_scenarios": 50, "seed": 42}
        data = client.post("/api/v1/uq", json=payload).json()
        assert data["var_95"] <= data["p50_pv_profit"]

    def test_uq_cvar_le_var(self):
        """CVaR (expected shortfall) should be ≤ VaR."""
        payload = {"policies": [DEMO_POLICY], "n_scenarios": 50, "seed": 42}
        data = client.post("/api/v1/uq", json=payload).json()
        assert data["cvar_95"] <= data["var_95"] + 1e-6  # CVaR ≤ VaR

    def test_uq_percentile_ordering(self):
        """p5 ≤ p50 ≤ p95 for PV profits."""
        payload = {"policies": [DEMO_POLICY], "n_scenarios": 50}
        data = client.post("/api/v1/uq", json=payload).json()
        assert data["p5_pv_profit"] <= data["p50_pv_profit"] <= data["p95_pv_profit"]


@pytest.mark.slow
class TestIFRS17Endpoints:
    def test_bba_returns_200(self):
        payload = {
            "policies": [DEMO_POLICY],
            "discount_rate": 0.04,
            "ra_factor": 0.05,
        }
        response = client.post("/api/v1/ifrs17/bba", json=payload)
        assert response.status_code == 200, response.text

    def test_bba_response_schema(self):
        payload = {"policies": [DEMO_POLICY]}
        data = client.post("/api/v1/ifrs17/bba", json=payload).json()
        required_keys = {
            "approach",
            "initial_bel",
            "initial_ra",
            "initial_csm",
            "loss_component",
            "total_initial_liability",
            "insurance_liability",
            "bel",
            "risk_adjustment",
            "csm",
        }
        assert required_keys.issubset(data.keys())

    def test_bba_approach_label(self):
        payload = {"policies": [DEMO_POLICY]}
        data = client.post("/api/v1/ifrs17/bba", json=payload).json()
        assert data["approach"] == "BBA"

    def test_bba_insurance_liability_length(self):
        """insurance_liability list should have length = projection_months."""
        payload = {
            "policies": [DEMO_POLICY],
            "projection_horizon_years": 10,
        }
        data = client.post("/api/v1/ifrs17/bba", json=payload).json()
        assert len(data["insurance_liability"]) == 10 * 12

    def test_paa_returns_200(self):
        payload = {"policies": [DEMO_POLICY]}
        response = client.post("/api/v1/ifrs17/paa", json=payload)
        assert response.status_code == 200, response.text

    def test_paa_approach_label(self):
        payload = {"policies": [DEMO_POLICY]}
        data = client.post("/api/v1/ifrs17/paa", json=payload).json()
        assert data["approach"] == "PAA"


# A valuation date shared by every movement-table cohort policy below.
_MOVEMENT_VALUATION_DATE = "2025-01-01"

# Two issue-year cohorts valued at a common date (2025-01-01):
#   - 2025 cohort: issued at valuation, duration 0, attained == issue age.
#   - 2023 cohort: issued two years earlier, duration 24m, attained age + 2.
MOVEMENT_POLICY_2025 = {
    "policy_id": "MOV2025",
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
    "valuation_date": _MOVEMENT_VALUATION_DATE,
}
MOVEMENT_POLICY_2023 = {
    "policy_id": "MOV2023",
    "issue_age": 45,
    "attained_age": 47,
    "sex": "F",
    "smoker": False,
    "underwriting_class": "STANDARD",
    "face_amount": 250_000.0,
    "annual_premium": 900.0,
    "policy_term": 20,
    "duration_inforce": 24,
    "issue_date": "2023-01-01",
    "valuation_date": _MOVEMENT_VALUATION_DATE,
}


@pytest.mark.slow
class TestIFRS17MovementEndpoint:
    """POST /api/v1/ifrs17/movement — analysis-of-change (movement) table."""

    def _payload(self, **overrides):
        payload = {
            "policies": [MOVEMENT_POLICY_2025, MOVEMENT_POLICY_2023],
            "projection_horizon_years": 10,
            "discount_rate": 0.04,
            "ra_factor": 0.05,
        }
        payload.update(overrides)
        return payload

    def test_returns_200(self):
        response = client.post("/api/v1/ifrs17/movement", json=self._payload())
        assert response.status_code == 200, response.text

    def test_response_schema(self):
        data = client.post("/api/v1/ifrs17/movement", json=self._payload()).json()
        assert set(data) == {
            "months_per_period",
            "n_cohorts",
            "max_footing_error",
            "aggregate",
            "cohorts",
        }

    def test_two_issue_years_form_two_cohorts(self):
        data = client.post("/api/v1/ifrs17/movement", json=self._payload()).json()
        assert data["n_cohorts"] == 2
        assert len(data["cohorts"]) == 2

    def test_cohorts_ordered_by_issue_year(self):
        data = client.post("/api/v1/ifrs17/movement", json=self._payload()).json()
        years = [c["issue_year"] for c in data["cohorts"]]
        assert years == [2023, 2025]

    def test_table_foots(self):
        """The headline disclosure property: opening + Σ movements == closing."""
        data = client.post("/api/v1/ifrs17/movement", json=self._payload()).json()
        assert data["max_footing_error"] < 1e-6

    def test_aggregate_has_null_cohort_metadata(self):
        data = client.post("/api/v1/ifrs17/movement", json=self._payload()).json()
        assert data["aggregate"]["issue_year"] is None
        assert data["aggregate"]["locked_in_rate"] is None

    def test_annual_reporting_periods_default(self):
        data = client.post("/api/v1/ifrs17/movement", json=self._payload()).json()
        assert data["months_per_period"] == 12
        # 10-year horizon → 10 annual reporting periods.
        assert data["aggregate"]["n_periods"] == 10

    def test_months_per_period_override(self):
        data = client.post(
            "/api/v1/ifrs17/movement", json=self._payload(months_per_period=6)
        ).json()
        assert data["months_per_period"] == 6
        assert data["aggregate"]["n_periods"] == 20

    def test_per_cohort_locked_in_rate_override(self):
        """`locked_in_rates` sets each cohort's rate; it is echoed on the table."""
        data = client.post(
            "/api/v1/ifrs17/movement",
            json=self._payload(locked_in_rates={2023: 0.02, 2025: 0.06}),
        ).json()
        by_year = {c["issue_year"]: c["locked_in_rate"] for c in data["cohorts"]}
        assert by_year[2023] == pytest.approx(0.02)
        assert by_year[2025] == pytest.approx(0.06)

    def test_row_has_all_components(self):
        data = client.post("/api/v1/ifrs17/movement", json=self._payload()).json()
        row = data["aggregate"]["rows"][0]
        assert {"bel", "ra", "csm", "total"}.issubset(row)
        assert {"opening", "new_business", "interest_accretion", "release", "closing"}.issubset(
            row["bel"]
        )

    def test_mixed_valuation_dates_rejected(self):
        """Cohorts must share one valuation date — the manager raises → HTTP 422."""
        bad = dict(MOVEMENT_POLICY_2023)
        bad["valuation_date"] = "2024-06-01"
        bad["duration_inforce"] = 17
        bad["attained_age"] = 46
        response = client.post(
            "/api/v1/ifrs17/movement",
            json=self._payload(policies=[MOVEMENT_POLICY_2025, bad]),
        )
        assert response.status_code == 422

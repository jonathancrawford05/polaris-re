"""
Tests for the ``POST /api/v1/portfolio`` endpoint (Milestone 5.2 Slice 2).

Uses FastAPI's ``TestClient`` to exercise the endpoint end-to-end without a
live server. Each test posts a multi-deal request, validates the response
shape, and cross-checks aggregate totals against the per-deal sum.
"""

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
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


def _deal_request(
    deal_id: str,
    cedant: str,
    valuation_date: str = "2025-01-01",
    **overrides,
) -> dict:
    """Build one deal entry for the /api/v1/portfolio request body.

    ``valuation_date`` is stamped on every policy (the API resolves the
    deal's projection date from the first policy when no explicit date is
    supplied at the deal level) so calendar-alignment tests can build
    mixed-date payloads.
    """
    policies = [
        dict(DEMO_POLICY, policy_id=f"{deal_id}_001", valuation_date=valuation_date),
        dict(DEMO_POLICY, policy_id=f"{deal_id}_002", valuation_date=valuation_date),
    ]
    base = {
        "deal_id": deal_id,
        "cedant": cedant,
        "product_type": "TERM",
        "treaty_type": "Coinsurance",
        "cession_pct": 0.5,
        "policies": policies,
        "projection_horizon_years": 10,
        "discount_rate": 0.06,
        "flat_qx": 0.002,
        "flat_lapse": 0.05,
        "yrt_loading": 0.10,
        "modco_interest_rate": 0.045,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Endpoint behaviour
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestPortfolioEndpoint:
    def test_post_returns_200(self):
        payload = {
            "hurdle_rate": 0.10,
            "deals": [
                _deal_request("D1", "CedantA"),
                _deal_request("D2", "CedantB"),
            ],
        }
        response = client.post("/api/v1/portfolio", json=payload)
        assert response.status_code == 200, response.text

    def test_response_top_level_schema(self):
        payload = {
            "hurdle_rate": 0.10,
            "deals": [_deal_request("D1", "CedantA"), _deal_request("D2", "CedantB")],
        }
        data = client.post("/api/v1/portfolio", json=payload).json()
        expected_keys = {
            "n_deals",
            "hurdle_rate",
            "projection_months",
            "total_pv_profits",
            "total_irr",
            "total_face_amount",
            "total_ceded_face",
            "peak_ceded_nar",
            "deals",
            "concentration",
            "hhi",
        }
        assert expected_keys.issubset(data.keys())
        assert data["n_deals"] == 2

    def test_total_pv_equals_sum_of_per_deal_pv(self):
        """PV is linear: portfolio total == sum of per-deal PV profits."""
        payload = {
            "hurdle_rate": 0.10,
            "deals": [
                _deal_request("D1", "CedantA"),
                _deal_request("D2", "CedantB"),
            ],
        }
        data = client.post("/api/v1/portfolio", json=payload).json()
        per_deal_sum = sum(deal["profit_test"]["pv_profits"] for deal in data["deals"])
        assert data["total_pv_profits"] == pytest.approx(per_deal_sum, rel=1e-9, abs=1e-3)

    def test_concentration_and_hhi_per_dimension(self):
        payload = {
            "hurdle_rate": 0.10,
            "deals": [_deal_request("D1", "CedantA"), _deal_request("D2", "CedantB")],
        }
        data = client.post("/api/v1/portfolio", json=payload).json()
        assert set(data["concentration"].keys()) == {"cedant", "product", "treaty"}
        assert set(data["hhi"].keys()) == {"cedant", "product", "treaty"}
        assert data["concentration"]["cedant"]["CedantA"] == pytest.approx(0.5)
        assert data["concentration"]["cedant"]["CedantB"] == pytest.approx(0.5)

    def test_yrt_deal_populates_ceded_nar(self):
        payload = {
            "hurdle_rate": 0.10,
            "deals": [_deal_request("D1", "CedantA", treaty_type="YRT", cession_pct=0.8)],
        }
        data = client.post("/api/v1/portfolio", json=payload).json()
        assert data["peak_ceded_nar"] > 0.0

    def test_empty_deals_list_rejected(self):
        payload = {"hurdle_rate": 0.10, "deals": []}
        response = client.post("/api/v1/portfolio", json=payload)
        assert response.status_code in (400, 422)

    def test_non_proportional_treaty_rejected(self):
        payload = {
            "hurdle_rate": 0.10,
            "deals": [_deal_request("D1", "CedantA", treaty_type=None)],
        }
        response = client.post("/api/v1/portfolio", json=payload)
        assert response.status_code in (400, 422)

    def test_duplicate_deal_id_rejected(self):
        payload = {
            "hurdle_rate": 0.10,
            "deals": [
                _deal_request("D1", "CedantA"),
                _deal_request("D1", "CedantB"),
            ],
        }
        response = client.post("/api/v1/portfolio", json=payload)
        assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# POST /api/v1/portfolio align field (ADR-061 Slice 2)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestPortfolioEndpointAlignField:
    """``align`` field on ``POST /api/v1/portfolio`` (ADR-061 Slice 2)."""

    def test_default_strict_rejects_mixed_valuation_dates(self):
        """Omitting ``align`` preserves the strict default — mixed dates 422."""
        payload = {
            "hurdle_rate": 0.10,
            "deals": [
                _deal_request("D1", "CedantA", valuation_date="2025-01-01"),
                _deal_request("D2", "CedantB", valuation_date="2025-07-01"),
            ],
        }
        response = client.post("/api/v1/portfolio", json=payload)
        assert response.status_code == 422
        assert "same valuation date" in response.text

    def test_calendar_mode_accepts_mixed_valuation_dates(self):
        """``align="calendar"`` round-trips a mixed-date 2-deal request."""
        payload = {
            "hurdle_rate": 0.10,
            "align": "calendar",
            "deals": [
                _deal_request("D1", "CedantA", valuation_date="2025-01-01"),
                _deal_request("D2", "CedantB", valuation_date="2025-07-01"),
            ],
        }
        response = client.post("/api/v1/portfolio", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["n_deals"] == 2
        assert data["grid_origin"] == "2025-01-01"
        # Earliest deal at offset 0, later deal at 6 months
        assert data["projection_months"] == 126

    def test_calendar_mode_exposes_per_deal_offsets(self):
        """Each deal carries its own ``valuation_date`` and ``grid_offset``."""
        payload = {
            "hurdle_rate": 0.10,
            "align": "calendar",
            "deals": [
                _deal_request("D1", "CedantA", valuation_date="2025-01-01"),
                _deal_request("D2", "CedantB", valuation_date="2025-07-01"),
            ],
        }
        data = client.post("/api/v1/portfolio", json=payload).json()
        deals_by_id = {d["deal_id"]: d for d in data["deals"]}
        assert deals_by_id["D1"]["valuation_date"] == "2025-01-01"
        assert deals_by_id["D1"]["grid_offset"] == 0
        assert deals_by_id["D2"]["valuation_date"] == "2025-07-01"
        assert deals_by_id["D2"]["grid_offset"] == 6

    def test_strict_explicit_matches_default(self):
        """Explicit ``align="strict"`` is identical to the default."""
        payload = {
            "hurdle_rate": 0.10,
            "align": "strict",
            "deals": [
                _deal_request("D1", "CedantA"),
                _deal_request("D2", "CedantB"),
            ],
        }
        data = client.post("/api/v1/portfolio", json=payload).json()
        assert data["n_deals"] == 2
        # All on shared 2025-01-01 — strict and calendar agree.
        assert data["grid_origin"] == "2025-01-01"
        for deal in data["deals"]:
            assert deal["grid_offset"] == 0

    def test_invalid_align_value_rejected_by_pydantic(self):
        """Pydantic's ``Literal`` rejects unrecognised align modes with 422."""
        payload = {
            "hurdle_rate": 0.10,
            "align": "bogus",
            "deals": [_deal_request("D1", "CedantA")],
        }
        response = client.post("/api/v1/portfolio", json=payload)
        assert response.status_code == 422

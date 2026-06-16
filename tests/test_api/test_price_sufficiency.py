"""
Tests for the premium-sufficiency block on POST /api/v1/price (ADR-083).

The price endpoint always returns a `premium_sufficiency` (cedant) and
`reinsurer_premium_sufficiency` block computed at the valuation discount
rate. An optional `sufficiency_target_margin` request field drives the
`is_sufficient` verdict.
"""

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app

client = TestClient(app)

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

_SUFFICIENCY_KEYS = {
    "discount_rate",
    "target_margin",
    "pv_premiums",
    "pv_claims",
    "pv_surrenders",
    "pv_benefits",
    "pv_expenses",
    "sufficiency_margin",
    "sufficiency_ratio",
    "loss_ratio",
    "expense_ratio",
    "combined_ratio",
    "is_sufficient",
}


class TestPriceSufficiencyBlock:
    def test_block_present_with_all_keys(self) -> None:
        data = client.post("/api/v1/price", json={"policies": [DEMO_POLICY]}).json()
        assert data["premium_sufficiency"] is not None
        assert data["reinsurer_premium_sufficiency"] is not None
        assert _SUFFICIENCY_KEYS.issubset(data["premium_sufficiency"].keys())
        assert _SUFFICIENCY_KEYS.issubset(data["reinsurer_premium_sufficiency"].keys())

    def test_default_target_margin_is_zero(self) -> None:
        data = client.post("/api/v1/price", json={"policies": [DEMO_POLICY]}).json()
        assert data["premium_sufficiency"]["target_margin"] == 0.0

    def test_target_margin_echoed(self) -> None:
        payload = {"policies": [DEMO_POLICY], "sufficiency_target_margin": 0.07}
        data = client.post("/api/v1/price", json=payload).json()
        assert data["premium_sufficiency"]["target_margin"] == pytest.approx(0.07)
        assert data["reinsurer_premium_sufficiency"]["target_margin"] == pytest.approx(0.07)

    def test_sufficiency_uses_discount_rate_not_hurdle(self) -> None:
        """The block's discount_rate is the request discount rate, not hurdle."""
        payload = {"policies": [DEMO_POLICY], "discount_rate": 0.05, "hurdle_rate": 0.12}
        data = client.post("/api/v1/price", json=payload).json()
        assert data["premium_sufficiency"]["discount_rate"] == pytest.approx(0.05)

    def test_ratio_identities_hold(self) -> None:
        data = client.post("/api/v1/price", json={"policies": [DEMO_POLICY]}).json()
        for block in (data["premium_sufficiency"], data["reinsurer_premium_sufficiency"]):
            cr = block["combined_ratio"]
            if cr is None:
                continue
            assert block["loss_ratio"] + block["expense_ratio"] == pytest.approx(cr)
            assert block["sufficiency_ratio"] == pytest.approx(1.0 - cr)

    def test_verdict_consistent_with_ratio(self) -> None:
        payload = {"policies": [DEMO_POLICY], "sufficiency_target_margin": 0.10}
        block = client.post("/api/v1/price", json=payload).json()["premium_sufficiency"]
        if block["sufficiency_ratio"] is not None:
            assert block["is_sufficient"] == (block["sufficiency_ratio"] >= 0.10)

    def test_no_treaty_reinsurer_mirrors_cedant(self) -> None:
        """With no treaty the reinsurer view mirrors the cedant view."""
        payload = {"policies": [DEMO_POLICY], "treaty_type": None}
        data = client.post("/api/v1/price", json=payload).json()
        assert data["premium_sufficiency"] == data["reinsurer_premium_sufficiency"]

    @pytest.mark.parametrize("bad", [-0.01, 1.0, 1.5])
    def test_invalid_target_margin_rejected(self, bad: float) -> None:
        payload = {"policies": [DEMO_POLICY], "sufficiency_target_margin": bad}
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 422, response.text

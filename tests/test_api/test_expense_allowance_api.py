"""Tests for expense-allowance / experience-refund surfacing on the REST API.

Expense-allowance epic (Tier-B B3), Slice 3b-2b-1 — surface the
``expense_allowance`` / ``experience_refund`` treaty terms on the four
deal-pricing API request models (``PriceRequest``, ``ScenarioRequest``,
``UQRequest``, ``PortfolioDealRequest``) and thread them through
``_build_treaty`` onto the YRT / Coinsurance engines (ADR-123). Slice 3b-2a
(PR #121) wired the same terms onto the CLI config path; this slice does the
API surface.

The treaty-level mechanics (the allowance/refund transfer, ``net + ceded ==
gross``) are verified by the reinsurance test suites; here we assert only the
*surfacing*: that a request-supplied term reaches the treaty (the value moves),
that an absent term is byte-identical, that the transfer offsets between the
cedant and reinsurer views, that Modco ignores the terms, and that a malformed
term is rejected at request validation.
"""

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app

client = TestClient(app)

# A single large policy so the allowance/refund move the priced numbers
# materially. Short horizon keeps the endpoint calls fast.
_POLICY = {
    "policy_id": "ALLOW001",
    "issue_age": 45,
    "attained_age": 45,
    "sex": "M",
    "smoker": False,
    "underwriting_class": "STANDARD",
    "face_amount": 1_000_000.0,
    "annual_premium": 20_000.0,
    "policy_term": 20,
    "duration_inforce": 0,
    "issue_date": "2026-01-01",
    "valuation_date": "2026-01-01",
}


def _base(treaty_type: str = "Coinsurance", **overrides) -> dict:
    payload = {
        "policies": [dict(_POLICY)],
        "treaty_type": treaty_type,
        "cession_pct": 0.90,
        "projection_horizon_years": 10,
        "discount_rate": 0.06,
        "hurdle_rate": 0.10,
    }
    payload.update(overrides)
    return payload


# A high first-year / low renewal allowance — a large reinsurer→cedant transfer.
_ALLOWANCE = {"first_year_pct": 1.0, "renewal_pct": 0.10}
_REFUND = {"refund_pct": 0.50, "retention": 0.0}


# ---------------------------------------------------------------------------
# /api/v1/price
# ---------------------------------------------------------------------------


class TestPriceAllowanceRefund:
    def test_absent_terms_are_byte_identical(self):
        """No allowance/refund key → identical response to omitting the fields."""
        baseline = client.post("/api/v1/price", json=_base()).json()
        explicit_none = client.post(
            "/api/v1/price",
            json=_base(expense_allowance=None, experience_refund=None),
        ).json()
        assert explicit_none == baseline

    def test_allowance_moves_reinsurer_profit(self):
        """A config allowance reaches the Coinsurance treaty and changes pricing."""
        baseline = client.post("/api/v1/price", json=_base()).json()
        withal = client.post("/api/v1/price", json=_base(expense_allowance=_ALLOWANCE)).json()
        # The reinsurer pays the allowance to the cedant → its profit falls.
        assert withal["reinsurer_pv_profits"] < baseline["reinsurer_pv_profits"]

    def test_allowance_is_a_zero_sum_transfer(self):
        """The allowance is a reinsurer→cedant transfer: undiscounted deltas offset.

        Folding the allowance into the expense line (+A ceded, -A net) means the
        cedant's undiscounted profit rises by exactly the amount the reinsurer's
        falls — a closed-form additivity check at the API surface.
        """
        baseline = client.post("/api/v1/price", json=_base()).json()
        withal = client.post("/api/v1/price", json=_base(expense_allowance=_ALLOWANCE)).json()
        d_reinsurer = (
            withal["reinsurer_total_undiscounted_profit"]
            - baseline["reinsurer_total_undiscounted_profit"]
        )
        d_cedant = withal["total_undiscounted_profit"] - baseline["total_undiscounted_profit"]
        assert d_reinsurer < 0.0  # reinsurer pays out
        assert d_cedant == pytest.approx(-d_reinsurer, rel=1e-9, abs=1e-6)

    def test_allowance_applies_to_yrt(self):
        """The allowance threads onto the YRT treaty too (not just Coinsurance)."""
        baseline = client.post("/api/v1/price", json=_base(treaty_type="YRT")).json()
        withal = client.post(
            "/api/v1/price", json=_base(treaty_type="YRT", expense_allowance=_ALLOWANCE)
        ).json()
        assert withal["reinsurer_pv_profits"] < baseline["reinsurer_pv_profits"]

    def test_refund_moves_reinsurer_profit(self):
        """A config experience refund reaches the treaty and reduces reinsurer profit."""
        baseline = client.post("/api/v1/price", json=_base()).json()
        withref = client.post("/api/v1/price", json=_base(experience_refund=_REFUND)).json()
        assert withref["reinsurer_pv_profits"] < baseline["reinsurer_pv_profits"]

    def test_sliding_scale_parses_and_applies(self):
        """A loss-ratio sliding scale is accepted and changes the priced numbers."""
        scale = {
            "first_year_pct": 1.0,
            "renewal_pct": 0.20,
            "sliding_scale": [
                {"max_loss_ratio": 0.50, "allowance_pct": 0.20},
                {"max_loss_ratio": 0.80, "allowance_pct": 0.10},
            ],
        }
        resp = client.post("/api/v1/price", json=_base(expense_allowance=scale))
        assert resp.status_code == 200, resp.text
        baseline = client.post("/api/v1/price", json=_base()).json()
        assert resp.json()["reinsurer_pv_profits"] != baseline["reinsurer_pv_profits"]

    def test_modco_ignores_allowance(self):
        """Modco has no allowance field → supplying one is byte-identical."""
        baseline = client.post("/api/v1/price", json=_base(treaty_type="Modco")).json()
        withal = client.post(
            "/api/v1/price",
            json=_base(
                treaty_type="Modco",
                expense_allowance=_ALLOWANCE,
                experience_refund=_REFUND,
            ),
        ).json()
        assert withal == baseline

    def test_malformed_sliding_scale_rejected(self):
        """A non-monotone scale (allowance rising with loss ratio) → 422."""
        bad = {
            "first_year_pct": 1.0,
            "renewal_pct": 0.10,
            "sliding_scale": [
                {"max_loss_ratio": 0.50, "allowance_pct": 0.10},
                {"max_loss_ratio": 0.80, "allowance_pct": 0.20},
            ],
        }
        resp = client.post("/api/v1/price", json=_base(expense_allowance=bad))
        assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# /api/v1/scenario  and  /api/v1/uq
# ---------------------------------------------------------------------------


class TestScenarioUQAllowance:
    def test_scenario_absent_is_byte_identical(self):
        baseline = client.post("/api/v1/scenario", json=_base()).json()
        explicit_none = client.post("/api/v1/scenario", json=_base(expense_allowance=None)).json()
        assert explicit_none == baseline

    def test_scenario_allowance_changes_results(self):
        baseline = client.post("/api/v1/scenario", json=_base()).json()
        withal = client.post("/api/v1/scenario", json=_base(expense_allowance=_ALLOWANCE)).json()
        base_pv = [s["pv_profits"] for s in baseline["scenarios"]]
        al_pv = [s["pv_profits"] for s in withal["scenarios"]]
        assert al_pv != base_pv

    def test_uq_absent_is_byte_identical(self):
        baseline = client.post("/api/v1/uq", json=_base(n_scenarios=20, seed=7)).json()
        explicit_none = client.post(
            "/api/v1/uq", json=_base(n_scenarios=20, seed=7, expense_allowance=None)
        ).json()
        assert explicit_none == baseline

    def test_uq_allowance_changes_results(self):
        baseline = client.post("/api/v1/uq", json=_base(n_scenarios=20, seed=7)).json()
        withal = client.post(
            "/api/v1/uq",
            json=_base(n_scenarios=20, seed=7, expense_allowance=_ALLOWANCE),
        ).json()
        assert withal["base_pv_profit"] != baseline["base_pv_profit"]


# ---------------------------------------------------------------------------
# /api/v1/portfolio
# ---------------------------------------------------------------------------


class TestPortfolioAllowance:
    def _deal(self, **overrides) -> dict:
        deal = {
            "deal_id": "D1",
            "cedant": "ACME Life",
            "policies": [dict(_POLICY)],
            "treaty_type": "Coinsurance",
            "cession_pct": 0.90,
            "projection_horizon_years": 10,
            "discount_rate": 0.06,
        }
        deal.update(overrides)
        return deal

    def test_portfolio_absent_is_byte_identical(self):
        baseline = client.post("/api/v1/portfolio", json={"deals": [self._deal()]}).json()
        explicit_none = client.post(
            "/api/v1/portfolio",
            json={"deals": [self._deal(expense_allowance=None)]},
        ).json()
        assert explicit_none == baseline

    def test_portfolio_allowance_changes_results(self):
        baseline = client.post("/api/v1/portfolio", json={"deals": [self._deal()]}).json()
        withal = client.post(
            "/api/v1/portfolio",
            json={"deals": [self._deal(expense_allowance=_ALLOWANCE)]},
        ).json()
        assert withal["total_pv_profits"] != baseline["total_pv_profits"]

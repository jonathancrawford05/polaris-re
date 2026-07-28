"""Unit tests for the pricing service layer (``polaris_re.services.pricing``).

Slice 1 of the MCP-server epic extracted the deal-pricing engine invocation out
of the FastAPI ``POST /api/v1/price`` route into
:func:`polaris_re.services.pricing.run_price`. These tests lock in the two
guarantees that make the extraction useful:

1. **Route/service parity** — the HTTP endpoint and a direct ``run_price`` call
   produce the identical response for the same inputs (the route is now a thin
   422-mapping adapter). This is what lets a second host (an MCP server) reuse
   the engine path without drift.
2. **Web-framework-free contract** — ``run_price`` performs no HTTP concerns:
   validation failures propagate as the domain
   :class:`~polaris_re.core.exceptions.PolarisValidationError`, not a FastAPI
   ``HTTPException``, so a non-HTTP host can map errors to its own surface.

All dates are pinned (ADR-074 guard — no wall-clock dependence).
"""

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.services.pricing import (
    PolicyInput,
    PriceRequest,
    PriceResponse,
    run_price,
)

client = TestClient(app)

# A seasoned single-policy block with self-consistent dates (issue == valuation,
# duration_inforce 0), so the ADR-074 ingestion guard passes.
_POLICY_KW = {
    "policy_id": "SVC001",
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


def _request(**overrides: object) -> PriceRequest:
    """Build a valid single-policy ``PriceRequest`` with optional overrides."""
    return PriceRequest(policies=[PolicyInput(**_POLICY_KW)], **overrides)


class TestRunPriceContract:
    def test_returns_price_response(self) -> None:
        """``run_price`` returns a typed ``PriceResponse`` for a valid request."""
        result = run_price(_request())
        assert isinstance(result, PriceResponse)
        assert result.n_policies == 1
        assert result.projection_months == 20 * 12
        # A YRT deal has a real ceded position, so the reinsurer view is
        # distinct from the cedant view (not the gross-only passthrough).
        assert result.reinsurer_pv_profits != result.pv_profits

    def test_gross_only_mirrors_cedant_on_reinsurer_view(self) -> None:
        """With no treaty the reinsurer view mirrors the cedant view (ADR-039)."""
        result = run_price(_request(treaty_type=None))
        assert result.reinsurer_pv_profits == result.pv_profits
        assert result.reinsurer_irr == result.irr

    def test_neutral_gaap_pads_echoed(self) -> None:
        """The default (neutral) GAAP PADs are echoed unchanged (1.0 / 0.0)."""
        result = run_price(_request())
        assert result.gaap_mortality_pad == 1.0
        assert result.gaap_interest_margin == 0.0


class TestRunPriceIsWebFrameworkFree:
    def test_unknown_treaty_raises_domain_error_not_http(self) -> None:
        """An unknown treaty raises the domain ``PolarisValidationError`` — NOT a
        FastAPI ``HTTPException`` — so a non-HTTP host can handle it. The message
        still enumerates the valid treaty types (incl. FWCoinsurance)."""
        with pytest.raises(PolarisValidationError) as excinfo:
            run_price(_request(treaty_type="NopeCoinsurance"))
        assert "FWCoinsurance" in str(excinfo.value)

    def test_services_module_imports_no_fastapi(self) -> None:
        """The service layer must not import the web framework (design anchor:
        the engine path works offline, with no ``fastapi`` / ``uvicorn`` dep)."""
        import polaris_re.services.pricing as pricing_mod

        for name, value in vars(pricing_mod).items():
            module = getattr(value, "__module__", "") or ""
            assert not module.startswith("fastapi"), (
                f"services.pricing.{name} leaks a fastapi symbol ({module})"
            )


class TestRouteServiceParity:
    """The HTTP route is a thin adapter — it must return exactly what a direct
    ``run_price`` call returns for the same inputs."""

    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            {"treaty_type": "Coinsurance"},
            {"treaty_type": None},
            {"cession_pct": 0.5, "discount_rate": 0.05, "hurdle_rate": 0.12},
            {"capital_model": "licat"},
        ],
    )
    def test_route_equals_service(self, overrides: dict[str, object]) -> None:
        request = _request(**overrides)
        service_json = run_price(request).model_dump()

        payload = {"policies": [_POLICY_KW], **overrides}
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 200, response.text
        # The route serialises the same PriceResponse; compare the response
        # model round-trip so numeric types line up.
        route_json = PriceResponse(**response.json()).model_dump()

        assert route_json == service_json

    def test_route_maps_domain_error_to_422(self) -> None:
        """The thin route maps ``run_price``'s domain error to HTTP 422 with the
        original message (pre-existing behaviour, now via the service)."""
        response = client.post(
            "/api/v1/price",
            json={"policies": [_POLICY_KW], "treaty_type": "NopeCoinsurance"},
        )
        assert response.status_code == 422
        assert "FWCoinsurance" in response.json()["detail"]

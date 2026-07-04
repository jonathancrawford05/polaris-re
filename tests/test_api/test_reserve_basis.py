"""Tests for the ``reserve_basis`` field on POST /api/v1/price (slice 4).

The price endpoint accepts an optional ``reserve_basis`` (NET_PREMIUM default)
and echoes the basis the run was priced on in the response. A non-default basis
changes the reserve and therefore the priced numbers; an unsupported basis for
the product yields HTTP 422.
"""

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


def _request(**overrides: object) -> dict:  # type: ignore[type-arg]
    body: dict = {  # type: ignore[type-arg]
        "policies": [DEMO_POLICY],
        "product_type": "TERM",
        "treaty_type": "YRT",
        "flat_qx": 0.01,
        "flat_lapse": 0.05,
    }
    body.update(overrides)
    return body


def test_default_response_reports_net_premium() -> None:
    resp = client.post("/api/v1/price", json=_request())
    assert resp.status_code == 200, resp.text
    assert resp.json()["reserve_basis"] == "NET_PREMIUM"


def test_explicit_net_premium_byte_identical_to_default() -> None:
    default = client.post("/api/v1/price", json=_request()).json()
    explicit = client.post("/api/v1/price", json=_request(reserve_basis="NET_PREMIUM")).json()
    assert default == explicit


def test_crvm_changes_priced_numbers() -> None:
    # Whole life carries a material reserve, so the CRVM basis (to-omega
    # prospective) moves the priced numbers vs the net-premium reserve. A
    # new-issue level term reserve is ~0 on both bases, which would not exercise
    # the difference.
    wl_policy = {**DEMO_POLICY, "policy_term": None, "annual_premium": 12_000.0}
    wl_request = _request(policies=[wl_policy], product_type="WHOLE_LIFE")
    net = client.post("/api/v1/price", json=wl_request).json()
    crvm_req = {**wl_request, "reserve_basis": "CRVM"}
    crvm = client.post("/api/v1/price", json=crvm_req)
    assert crvm.status_code == 200, crvm.text
    crvm_json = crvm.json()
    assert crvm_json["reserve_basis"] == "CRVM"
    # CRVM moves the WL reserve materially vs the net-premium basis; assert a
    # tolerance-based difference rather than a bare float inequality.
    assert abs(net["pv_profits"] - crvm_json["pv_profits"]) > 1.0


def test_unsupported_basis_for_product_is_422() -> None:
    # GAAP (FAS 60) is implemented for TermLife (ADR-127) but not yet for
    # WholeLife, so selecting it on a WL policy surfaces the
    # PolarisComputationError as HTTP 422.
    wl_policy = {**DEMO_POLICY, "policy_term": None, "annual_premium": 12_000.0}
    resp = client.post(
        "/api/v1/price",
        json=_request(policies=[wl_policy], product_type="WHOLE_LIFE", reserve_basis="GAAP"),
    )
    assert resp.status_code == 422


def test_invalid_basis_string_is_422() -> None:
    resp = client.post("/api/v1/price", json=_request(reserve_basis="BOGUS"))
    # Pydantic enum validation rejects the unknown value before the handler runs.
    assert resp.status_code == 422

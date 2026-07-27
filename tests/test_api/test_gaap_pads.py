"""Tests for the GAAP (FAS 60) PAD fields on POST /api/v1/price.

The two GAAP provisions for adverse deviation are built onto ``ProjectionConfig``
(ADR-127/128); this surfacing work adds them to ``PriceRequest``
(``gaap_mortality_pad`` default 1.0, ``gaap_interest_margin`` default 0.0),
threads them onto the config, and echoes them on ``PriceResponse``. These tests
verify: omitting them is byte-identical to explicit neutral values; a non-neutral
PAD on the GAAP basis moves ``pv_profits`` and is echoed on the response; the PADs
are ignored on a non-GAAP basis; and an out-of-range value yields HTTP 422.

A WHOLE_LIFE policy is used because it carries a material reserve — the PAD effect
is not exercised by a ~0 new-issue term reserve. GAAP values on the projection
best-estimate mortality plus the PADs, so no prescribed table (CSO) is needed.
"""

from fastapi.testclient import TestClient

from polaris_re.api.main import app

client = TestClient(app)

WL_POLICY = {
    "policy_id": "WL001",
    "issue_age": 45,
    "attained_age": 50,
    "sex": "M",
    "smoker": False,
    "underwriting_class": "STANDARD",
    "face_amount": 1_000_000.0,
    "annual_premium": 12_000.0,
    "policy_term": None,
    "duration_inforce": 60,
    "issue_date": "2021-01-01",
    "valuation_date": "2026-01-01",
}


def _request(**overrides: object) -> dict:  # type: ignore[type-arg]
    body: dict = {  # type: ignore[type-arg]
        "policies": [WL_POLICY],
        "product_type": "WHOLE_LIFE",
        "treaty_type": None,
        "reserve_basis": "GAAP",
        "flat_qx": 0.02,
        "flat_lapse": 0.05,
    }
    body.update(overrides)
    return body


def test_default_omitted_is_accepted_and_echoes_neutral() -> None:
    resp = client.post("/api/v1/price", json=_request())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gaap_mortality_pad"] == 1.0
    assert body["gaap_interest_margin"] == 0.0


def test_omitting_is_byte_identical_to_explicit_neutral() -> None:
    omitted = client.post("/api/v1/price", json=_request()).json()
    explicit = client.post(
        "/api/v1/price",
        json=_request(gaap_mortality_pad=1.0, gaap_interest_margin=0.0),
    ).json()
    assert omitted == explicit


def test_mortality_pad_changes_priced_numbers_and_echoes() -> None:
    neutral = client.post("/api/v1/price", json=_request()).json()
    padded_resp = client.post("/api/v1/price", json=_request(gaap_mortality_pad=1.10))
    assert padded_resp.status_code == 200, padded_resp.text
    padded = padded_resp.json()
    assert padded["gaap_mortality_pad"] == 1.10
    assert abs(neutral["pv_profits"] - padded["pv_profits"]) > 1.0


def test_interest_margin_changes_priced_numbers_and_echoes() -> None:
    neutral = client.post("/api/v1/price", json=_request()).json()
    padded_resp = client.post("/api/v1/price", json=_request(gaap_interest_margin=0.01))
    assert padded_resp.status_code == 200, padded_resp.text
    padded = padded_resp.json()
    assert padded["gaap_interest_margin"] == 0.01
    assert abs(neutral["pv_profits"] - padded["pv_profits"]) > 1.0


def test_pads_ignored_on_net_premium_basis() -> None:
    plain = client.post("/api/v1/price", json=_request(reserve_basis="NET_PREMIUM")).json()
    padded = client.post(
        "/api/v1/price",
        json=_request(
            reserve_basis="NET_PREMIUM", gaap_mortality_pad=1.25, gaap_interest_margin=0.02
        ),
    ).json()
    assert plain["pv_profits"] == padded["pv_profits"]


def test_below_one_mortality_pad_is_422() -> None:
    resp = client.post("/api/v1/price", json=_request(gaap_mortality_pad=0.9))
    assert resp.status_code == 422


def test_out_of_range_interest_margin_is_422() -> None:
    resp = client.post("/api/v1/price", json=_request(gaap_interest_margin=1.5))
    assert resp.status_code == 422

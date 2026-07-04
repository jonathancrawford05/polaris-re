"""Tests for the ``valuation_mortality`` field on POST /api/v1/price.

Reserve-Basis Exactness epic, Slice 2 (surfacing). The price endpoint accepts an
optional ``valuation_mortality`` (a named source id, default ``None``) that is
loaded server-side from ``$POLARIS_DATA_DIR/mortality_tables`` and threaded onto
``AssumptionSet.valuation_mortality`` (ADR-125). When set, CRVM values on the
prescribed table; ``NET_PREMIUM`` and omitting the field are byte-identical to
prior responses; an unknown source id yields HTTP 422.

A WHOLE_LIFE policy is used because it carries a material reserve — the
CRVM-on-CSO difference is not exercised by a ~0 new-issue term reserve. The 2001
CSO CSVs are loaded server-side, so these tests are skipped when the converted
files are absent.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app

client = TestClient(app)

_REPO_DATA_DIR = Path(os.environ.get("POLARIS_DATA_DIR", "data")).resolve()
_HAS_CSO = (_REPO_DATA_DIR / "mortality_tables" / "cso_2001_male.csv").exists()
requires_cso = pytest.mark.skipif(
    not _HAS_CSO, reason="2001 CSO tables required (run scripts/convert_soa_tables.py)"
)

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


@pytest.fixture(autouse=True)
def _point_data_dir_at_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the server resolves valuation tables from the repo data dir.

    ``valuation_mortality`` is loaded from ``$POLARIS_DATA_DIR/mortality_tables``;
    pin it to the repo's ``data`` dir so a sibling test that repointed the env
    var cannot leak into these runs.
    """
    monkeypatch.setenv("POLARIS_DATA_DIR", str(_REPO_DATA_DIR))


def _request(**overrides: object) -> dict:  # type: ignore[type-arg]
    body: dict = {  # type: ignore[type-arg]
        "policies": [WL_POLICY],
        "product_type": "WHOLE_LIFE",
        "treaty_type": None,
        "reserve_basis": "CRVM",
        "flat_qx": 0.02,
        "flat_lapse": 0.05,
    }
    body.update(overrides)
    return body


def test_default_omitted_is_accepted() -> None:
    resp = client.post("/api/v1/price", json=_request())
    assert resp.status_code == 200, resp.text


def test_omitting_is_byte_identical_to_explicit_null() -> None:
    omitted = client.post("/api/v1/price", json=_request()).json()
    explicit = client.post("/api/v1/price", json=_request(valuation_mortality=None)).json()
    assert omitted == explicit


@requires_cso
def test_crvm_on_cso_changes_priced_numbers() -> None:
    crvm = client.post("/api/v1/price", json=_request()).json()
    crvm_cso = client.post("/api/v1/price", json=_request(valuation_mortality="CSO_2001"))
    assert crvm_cso.status_code == 200, crvm_cso.text
    assert abs(crvm["pv_profits"] - crvm_cso.json()["pv_profits"]) > 1.0


@requires_cso
def test_net_premium_ignores_the_slot() -> None:
    plain = client.post("/api/v1/price", json=_request(reserve_basis="NET_PREMIUM")).json()
    with_slot = client.post(
        "/api/v1/price",
        json=_request(reserve_basis="NET_PREMIUM", valuation_mortality="CSO_2001"),
    ).json()
    assert plain == with_slot


def test_unknown_source_is_422() -> None:
    resp = client.post("/api/v1/price", json=_request(valuation_mortality="BOGUS_TABLE"))
    assert resp.status_code == 422

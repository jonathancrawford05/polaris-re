"""Tests for the ``improvement_version`` field on POST /api/v1/price.

mi-dashboard epic, Slice 3 — the API half of IMPORTANT #12 (ADR-148/ADR-158).
The A4' epic (ADR-139..154) built an experience-derived mortality-improvement
capability whose frozen, audited ``ImprovementScale.CUSTOM`` bases are persisted
in the append-only :class:`AssumptionVersionStore` (``polaris experience save``)
and can already drive a priced run via the CLI ``--improvement-version`` flag /
``mortality.improvement_version_id`` config key (ADR-148) and the dashboard
Deal-Pricing selector (ADR-158). This slice surfaces the *REST-API* half: the
price endpoint accepts an optional ``improvement_version`` (a ``version_id``,
default ``None``) that is loaded server-side from
``$POLARIS_DATA_DIR/assumption_versions`` and threaded onto
``AssumptionSet.improvement``.

Contract:
* omitting the field / passing ``null`` is byte-identical to prior responses;
* a stored version echoes back on the response and **materially** lowers the
  priced mortality (the improvement scale scales q_x down over calendar time),
  identical to the CLI / dashboard path;
* an unknown version id yields HTTP 422.

The store is seeded into a ``tmp_path`` and ``POLARIS_DATA_DIR`` is repointed at
it, so no committed store fixture is needed. The flat-``flat_qx`` synthetic
mortality path needs no mortality-table CSVs, so the redirected data dir can be
empty apart from the seeded store. All ages / years / dates are pinned literals
(ADR-074 — never the wall clock).
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from polaris_re.api.main import app
from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement
from polaris_re.assumptions.version_store import AssumptionVersionStore

client = TestClient(app)

# A synthetic experience-derived CUSTOM improvement: a flat 2%/yr annual
# improvement over ages 40-70 and calendar years 2026-2045 (base year 2025),
# with a 2%/yr ultimate beyond the grid. Constant across the grid so the
# recovered mortality unambiguously improves the flat base rate.
_STUDY_DATE = date(2025, 12, 31)

TERM_POLICY = {
    "policy_id": "T001",
    "issue_age": 45,
    "attained_age": 45,
    "sex": "M",
    "smoker": False,
    "underwriting_class": "STANDARD",
    "face_amount": 1_000_000.0,
    "annual_premium": 3_000.0,
    "policy_term": 20,
    "duration_inforce": 0,
    "issue_date": "2026-01-01",
    "valuation_date": "2026-01-01",
}


def _make_custom_improvement() -> MortalityImprovement:
    ages = np.arange(40, 71, dtype=np.int32)
    years = np.arange(2026, 2046, dtype=np.int32)
    mi_grid = np.full((ages.size, years.size), 0.02, dtype=np.float64)
    mi = MortalityImprovement.from_grid(ages, years, mi_grid, ultimate_rate=0.02)
    assert mi.scale is ImprovementScale.CUSTOM
    return mi


@pytest.fixture
def seeded_version(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Seed one CUSTOM improvement version under a fresh ``POLARIS_DATA_DIR``.

    Returns the allocated ``version_id``. ``load_improvement_version`` resolves
    the store at ``$POLARIS_DATA_DIR/assumption_versions`` (``default_store_root``),
    the same default the CLI / dashboard use, so repointing the env var makes the
    server load the seeded version.
    """
    monkeypatch.setenv("POLARIS_DATA_DIR", str(tmp_path))
    store = AssumptionVersionStore(tmp_path / "assumption_versions")
    version = store.save(
        _make_custom_improvement(),
        study_date=_STUDY_DATE,
        credibility=0.8,
        label="api-test-basis",
    )
    return version.version_id


def _request(**overrides: object) -> dict:  # type: ignore[type-arg]
    body: dict = {  # type: ignore[type-arg]
        "policies": [TERM_POLICY],
        "product_type": "TERM",
        "treaty_type": "YRT",
        "projection_horizon_years": 15,
        "flat_qx": 0.01,
        "flat_lapse": 0.05,
    }
    body.update(overrides)
    return body


def test_default_omitted_is_accepted() -> None:
    resp = client.post("/api/v1/price", json=_request())
    assert resp.status_code == 200, resp.text
    # The echo field is present and null on the default no-improvement run.
    assert resp.json()["improvement_version"] is None


def test_omitting_is_byte_identical_to_explicit_null() -> None:
    omitted = client.post("/api/v1/price", json=_request()).json()
    explicit = client.post("/api/v1/price", json=_request(improvement_version=None)).json()
    assert omitted == explicit


def test_selected_version_echoes_and_bites(seeded_version: str) -> None:
    """A stored version echoes on the response and materially lowers claims.

    The improvement scale scales q_x down over calendar time, so the priced run
    has strictly lower total undiscounted claims (hence a different profit) than
    the improvement-free run — the same effect the CLI ``--improvement-version``
    flag and the dashboard selector produce.
    """
    baseline = client.post("/api/v1/price", json=_request()).json()

    resp = client.post("/api/v1/price", json=_request(improvement_version=seeded_version))
    assert resp.status_code == 200, resp.text
    improved = resp.json()

    # The response confirms which frozen basis drove the run.
    assert improved["improvement_version"] == seeded_version

    # Mortality improvement lowers projected claims → the reinsurer's ceded
    # (mortality-driven) result differs materially from the no-improvement run.
    assert abs(improved["reinsurer_pv_profits"] - baseline["reinsurer_pv_profits"]) > 1.0


def test_unknown_version_is_422(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """An unrecognised version id is a clean 422, not a 500."""
    monkeypatch.setenv("POLARIS_DATA_DIR", str(tmp_path))
    # An empty store: any id is unknown.
    AssumptionVersionStore(tmp_path / "assumption_versions")
    resp = client.post("/api/v1/price", json=_request(improvement_version="2025-12-31-999"))
    assert resp.status_code == 422

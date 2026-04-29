"""API tests for the ``yrt_rate_table_path`` field on ``/api/v1/price`` (ADR-052)."""

from __future__ import annotations

from pathlib import Path

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


def _write_synthetic_yrt_csv(path: Path, base_rate: float, age_slope: float) -> None:
    """Write a synthetic YRT CSV (ages 18-85) used by API tests."""
    lines = ["age,dur_1,dur_2,dur_3,ultimate"]
    for age in range(18, 86):
        d1 = base_rate + age_slope * (age - 18)
        d2 = d1 + 0.02
        d3 = d2 + 0.02
        ult = d3 + 0.50
        lines.append(f"{age},{d1:.4f},{d2:.4f},{d3:.4f},{ult:.4f}")
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def yrt_rate_table_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a fixture directory and point ``POLARIS_DATA_DIR`` at it."""
    monkeypatch.setenv("POLARIS_DATA_DIR", str(tmp_path))
    d = tmp_path / "yrt"
    d.mkdir()
    _write_synthetic_yrt_csv(d / "yrt_male_ns.csv", 0.30, 0.06)
    _write_synthetic_yrt_csv(d / "yrt_male_smoker.csv", 0.55, 0.10)
    _write_synthetic_yrt_csv(d / "yrt_female_ns.csv", 0.25, 0.05)
    _write_synthetic_yrt_csv(d / "yrt_female_smoker.csv", 0.45, 0.08)
    return d


@pytest.mark.slow
class TestPriceEndpointYRTRateTable:
    """Tests for ``POST /api/v1/price`` with ``yrt_rate_table_path``."""

    def test_yrt_rate_table_returns_200(self, yrt_rate_table_dir: Path) -> None:
        """Tabular YRT request returns 200 and a non-zero reinsurer view."""
        payload = {
            "policies": [DEMO_POLICY],
            "yrt_rate_table_path": "yrt",
            "yrt_rate_table_select_period": 3,
        }
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        # Cedant pays YRT premium → reinsurer pv_profits should be > 0.
        assert data["reinsurer_pv_profits"] > 0.0

    def test_yrt_rate_table_field_default_is_none(self) -> None:
        """Without ``yrt_rate_table_path`` the legacy flat path is taken
        (response shape unchanged from prior versions)."""
        payload = {"policies": [DEMO_POLICY]}
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 200
        # Just a smoke test — this is the existing flat-rate path.
        assert "reinsurer_pv_profits" in response.json()

    def test_yrt_rate_table_path_traversal_rejected(self, yrt_rate_table_dir: Path) -> None:
        """A path that escapes ``POLARIS_DATA_DIR`` returns 400."""
        payload = {
            "policies": [DEMO_POLICY],
            "yrt_rate_table_path": "../etc",
        }
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code in (400, 422), response.text
        body = response.json()
        # FastAPI maps HTTPException(400) to {"detail": "..."}; the
        # outer try/except in the price endpoint may also wrap into 422.
        detail = body.get("detail", "")
        assert "POLARIS_DATA_DIR" in str(detail) or "yrt_rate_table_path" in str(detail)

    def test_yrt_rate_table_missing_dir_returns_404_or_422(self, yrt_rate_table_dir: Path) -> None:
        """A non-existent directory under POLARIS_DATA_DIR returns 404 (or 422)."""
        payload = {
            "policies": [DEMO_POLICY],
            "yrt_rate_table_path": "nonexistent",
        }
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code in (404, 422), response.text

    def test_yrt_rate_table_path_without_data_dir_env_returns_500(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without POLARIS_DATA_DIR set, the endpoint returns 500."""
        monkeypatch.delenv("POLARIS_DATA_DIR", raising=False)
        payload = {
            "policies": [DEMO_POLICY],
            "yrt_rate_table_path": "yrt",
        }
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code in (422, 500), response.text

    def test_aggregate_mode_via_api(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`yrt_rate_table_smoker_distinct=False` resolves _unknown files."""
        monkeypatch.setenv("POLARIS_DATA_DIR", str(tmp_path))
        d = tmp_path / "agg"
        d.mkdir()
        for sex_label in ("male", "female"):
            _write_synthetic_yrt_csv(d / f"yrt_{sex_label}_unknown.csv", 0.40, 0.06)
        payload = {
            "policies": [DEMO_POLICY],
            "yrt_rate_table_path": "agg",
            "yrt_rate_table_smoker_distinct": False,
        }
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["reinsurer_pv_profits"] > 0.0

    def test_invalid_select_period_validation(self, yrt_rate_table_dir: Path) -> None:
        """Pydantic enforces ``select_period >= 1``."""
        payload = {
            "policies": [DEMO_POLICY],
            "yrt_rate_table_path": "yrt",
            "yrt_rate_table_select_period": 0,
        }
        response = client.post("/api/v1/price", json=payload)
        assert response.status_code == 422, response.text

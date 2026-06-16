"""
CLI premium-sufficiency surfacing tests (ADR-083).

`polaris price` emits a `premium_sufficiency` block per cohort (and at the
top level for single-cohort runs) and accepts `--sufficiency-target-margin`.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from polaris_re.cli import app

runner = CliRunner()

REPO_ROOT = Path(__file__).parent.parent.parent
GOLDEN_DIR = REPO_ROOT / "data" / "qa"
GOLDEN_CSV = GOLDEN_DIR / "golden_inforce.csv"
GOLDEN_CONFIG = GOLDEN_DIR / "golden_config_flat.json"

_SUFFICIENCY_KEYS = {
    "discount_rate",
    "target_margin",
    "pv_premiums",
    "pv_benefits",
    "pv_expenses",
    "sufficiency_margin",
    "sufficiency_ratio",
    "loss_ratio",
    "expense_ratio",
    "combined_ratio",
    "is_sufficient",
}


def _run(tmp_path: Path, *extra: str) -> dict:
    out = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "price",
            "--config",
            str(GOLDEN_CONFIG),
            "--inforce",
            str(GOLDEN_CSV),
            "--output",
            str(out),
            *extra,
        ],
    )
    assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
    return json.loads(out.read_text())


class TestCLIPremiumSufficiency:
    def test_each_cohort_has_sufficiency_block(self, tmp_path: Path) -> None:
        payload = _run(tmp_path)
        assert payload["cohorts"]
        for cohort in payload["cohorts"]:
            assert "premium_sufficiency" in cohort
            block = cohort["premium_sufficiency"]
            assert _SUFFICIENCY_KEYS.issubset(block["cedant"].keys())
            # reinsurer present (golden_config_flat applies a treaty)
            assert block["reinsurer"] is not None
            assert _SUFFICIENCY_KEYS.issubset(block["reinsurer"].keys())

    def test_target_margin_flows_into_block(self, tmp_path: Path) -> None:
        payload = _run(tmp_path, "--sufficiency-target-margin", "0.08")
        block = payload["cohorts"][0]["premium_sufficiency"]["cedant"]
        assert block["target_margin"] == pytest.approx(0.08)

    def test_discount_rate_is_valuation_rate(self, tmp_path: Path) -> None:
        # golden_config_flat uses discount_rate 0.06; sufficiency uses that,
        # not the profit hurdle.
        payload = _run(tmp_path)
        block = payload["cohorts"][0]["premium_sufficiency"]["cedant"]
        assert block["discount_rate"] == pytest.approx(0.06)

    def test_reinsurer_ratio_identities(self, tmp_path: Path) -> None:
        payload = _run(tmp_path)
        block = payload["cohorts"][0]["premium_sufficiency"]["reinsurer"]
        if block["combined_ratio"] is not None:
            assert block["loss_ratio"] + block["expense_ratio"] == pytest.approx(
                block["combined_ratio"]
            )

    def test_invalid_target_margin_exits_nonzero(self, tmp_path: Path) -> None:
        out = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(GOLDEN_CONFIG),
                "--inforce",
                str(GOLDEN_CSV),
                "--output",
                str(out),
                "--sufficiency-target-margin",
                "1.5",
            ],
        )
        assert result.exit_code != 0

"""CLI end-to-end tests against golden inputs.

Uses typer.CliRunner to invoke polaris price/scenario/uq commands
with the golden inforce CSV and config files, asserting on exit code
and output structure.
"""

import json

from typer.testing import CliRunner

from polaris_re.cli import app

from .conftest import GOLDEN_CONFIGS_DIR, GOLDEN_CSV, requires_soa_tables

runner = CliRunner()


class TestCLIGoldenSmoke:
    """Smoke tests: CLI commands run to completion on golden inputs."""

    def test_price_flat_mortality(self, tmp_path):
        """polaris price runs on golden CSV with flat mortality."""
        output = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(GOLDEN_CONFIGS_DIR / "golden_config_flat.json"),
                "--inforce",
                str(GOLDEN_CSV),
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
        payload = json.loads(output.read_text())
        assert "cohorts" in payload
        assert payload["summary"]["n_cohorts"] == 2

    @requires_soa_tables
    def test_price_yrt_soa(self, tmp_path):
        """polaris price runs with SOA VBT 2015 tables."""
        output = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(GOLDEN_CONFIGS_DIR / "golden_config_yrt.json"),
                "--inforce",
                str(GOLDEN_CSV),
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
        payload = json.loads(output.read_text())
        assert payload["summary"]["n_cohorts"] == 2
        # Both cohorts should have cedant profit test results
        for cohort in payload["cohorts"]:
            assert "pv_profits" in cohort["cedant"]

    @requires_soa_tables
    def test_price_coinsurance(self, tmp_path):
        """polaris price runs with coinsurance treaty."""
        output = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(GOLDEN_CONFIGS_DIR / "golden_config_coins.json"),
                "--inforce",
                str(GOLDEN_CSV),
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"

    @requires_soa_tables
    def test_price_policy_cession(self, tmp_path):
        """polaris price runs with policy-level cession overrides."""
        output = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(GOLDEN_CONFIGS_DIR / "golden_config_policy_cession.json"),
                "--inforce",
                str(GOLDEN_CSV),
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"

    def test_scenario_rejects_mixed_block(self, tmp_path):
        """polaris scenario exits non-zero on mixed product block."""
        result = runner.invoke(
            app,
            [
                "scenario",
                "--config",
                str(GOLDEN_CONFIGS_DIR / "golden_config_flat.json"),
                "--inforce",
                str(GOLDEN_CSV),
            ],
        )
        assert result.exit_code != 0

    def test_validate_golden_csv(self):
        """polaris validate accepts the golden CSV."""
        result = runner.invoke(
            app,
            [
                "validate",
                str(GOLDEN_CSV),
            ],
        )
        assert result.exit_code == 0

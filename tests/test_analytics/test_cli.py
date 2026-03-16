"""
Tests for the Polaris RE CLI (polaris_re/cli.py).

Tests use Typer's CliRunner to invoke commands in-process without subprocess.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from polaris_re.cli import app

runner = CliRunner()


class TestVersionCommand:

    def test_version_exits_zero(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0, result.output

    def test_version_output_contains_version(self):
        import polaris_re
        result = runner.invoke(app, ["version"])
        assert polaris_re.__version__ in result.output

    def test_version_output_contains_python(self):
        result = runner.invoke(app, ["version"])
        assert "Python" in result.output or "python" in result.output.lower()


@pytest.mark.slow
class TestPriceCommand:

    def test_price_demo_mode_exits_zero(self):
        """price without config runs demo mode and exits 0."""
        result = runner.invoke(app, ["price"])
        assert result.exit_code == 0, result.output

    def test_price_outputs_irr(self):
        """price command output should mention key profit metrics."""
        result = runner.invoke(app, ["price"])
        # Should show at least some financial metrics in the table
        output = result.output
        assert any(kw in output for kw in ["IRR", "PV Profit", "Margin", "Hurdle"])

    def test_price_writes_json_output(self, tmp_path: Path):
        """price --output writes valid JSON to file."""
        out_file = tmp_path / "result.json"
        result = runner.invoke(app, ["price", "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "pv_profits" in data
        assert "irr" in data
        assert "profit_by_year" in data

    def test_price_custom_hurdle_rate(self):
        """price with custom hurdle rate should succeed."""
        result = runner.invoke(app, ["price", "--hurdle-rate", "0.12"])
        assert result.exit_code == 0, result.output


@pytest.mark.slow
class TestScenarioCommand:

    def test_scenario_demo_mode_exits_zero(self):
        """scenario without config runs demo mode and exits 0."""
        result = runner.invoke(app, ["scenario"])
        assert result.exit_code == 0, result.output

    def test_scenario_writes_json_output(self, tmp_path: Path):
        """scenario --output writes valid JSON to file."""
        out_file = tmp_path / "scenario_result.json"
        result = runner.invoke(app, ["scenario", "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "scenarios" in data
        assert isinstance(data["scenarios"], list)
        assert len(data["scenarios"]) > 0


@pytest.mark.slow
class TestUQCommand:

    def test_uq_demo_mode_exits_zero(self):
        """uq without config runs demo mode and exits 0."""
        result = runner.invoke(app, ["uq", "--scenarios", "20"])
        assert result.exit_code == 0, result.output

    def test_uq_writes_json_output(self, tmp_path: Path):
        """uq --output writes valid JSON to file."""
        out_file = tmp_path / "uq_result.json"
        result = runner.invoke(app, ["uq", "--scenarios", "20", "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "base_pv_profit" in data
        assert "var_95" in data


class TestValidateCommand:

    def test_validate_missing_file_exits_one(self):
        """validate with non-existent file exits with code 1."""
        result = runner.invoke(app, ["validate", "/nonexistent/path/file.csv"])
        assert result.exit_code == 1

    def test_validate_valid_csv(self, tmp_path: Path):
        """validate accepts a CSV with required columns."""
        csv_file = tmp_path / "inforce.csv"
        csv_file.write_text(
            "policy_id,issue_age,attained_age,sex,face_amount,annual_premium\n"
            "P001,40,40,M,500000,1200\n"
            "P002,35,35,F,250000,800\n"
        )
        result = runner.invoke(app, ["validate", str(csv_file)])
        assert result.exit_code == 0, result.output
        assert "PASSED" in result.output

    def test_validate_invalid_csv_missing_cols(self, tmp_path: Path):
        """validate fails if required columns are missing."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("policy_id,age\nP001,40\n")
        result = runner.invoke(app, ["validate", str(csv_file)])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_validate_valid_json(self, tmp_path: Path):
        """validate accepts JSON with required keys."""
        json_file = tmp_path / "assumptions.json"
        json_file.write_text(
            '{"version": "v1", "mortality": {}, "lapse": {}}'
        )
        result = runner.invoke(app, ["validate", str(json_file)])
        assert result.exit_code == 0, result.output

    def test_validate_invalid_json(self, tmp_path: Path):
        """validate fails for JSON with missing required keys."""
        json_file = tmp_path / "bad.json"
        json_file.write_text('{"version": "v1"}')  # missing mortality and lapse
        result = runner.invoke(app, ["validate", str(json_file)])
        assert result.exit_code == 1

    def test_validate_broken_json(self, tmp_path: Path):
        """validate exits 1 for malformed JSON."""
        bad_file = tmp_path / "broken.json"
        bad_file.write_text("{not valid json}")
        result = runner.invoke(app, ["validate", str(bad_file)])
        assert result.exit_code == 1

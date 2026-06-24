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
        """price --output writes valid JSON with cedant and reinsurer views."""
        out_file = tmp_path / "result.json"
        result = runner.invoke(app, ["price", "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        # Output is now split into cedant and reinsurer views (ADR-038, ADR-039)
        assert "cedant" in data
        assert "reinsurer" in data
        assert "pv_profits" in data["cedant"]
        assert "irr" in data["cedant"]
        assert "profit_by_year" in data["cedant"]
        assert "pv_profits" in data["reinsurer"]

    def test_price_custom_hurdle_rate(self):
        """price with custom hurdle rate should succeed."""
        result = runner.invoke(app, ["price", "--hurdle-rate", "0.12"])
        assert result.exit_code == 0, result.output


@pytest.mark.slow
class TestPriceCommandCapital:
    """Tests for `polaris price --capital licat` (ADR-049, Slice 3)."""

    def test_capital_licat_emits_return_on_capital_in_json(self, tmp_path: Path):
        """JSON output gains return_on_capital and peak_capital under --capital licat."""
        out_file = tmp_path / "result.json"
        result = runner.invoke(app, ["price", "--capital", "licat", "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        data = json.loads(out_file.read_text())
        # Both top-level (single-cohort back-compat) and per-cohort entries
        # carry the capital block.
        assert "return_on_capital" in data["cedant"]
        assert "peak_capital" in data["cedant"]
        assert "pv_capital" in data["cedant"]
        assert "pv_capital_strain" in data["cedant"]
        assert "capital_adjusted_irr" in data["cedant"]
        assert "return_on_capital" in data["reinsurer"]
        # Per-cohort schema mirrors the top-level fields
        assert data["cohorts"][0]["cedant"].get("return_on_capital") is not None or (
            data["cohorts"][0]["cedant"]["pv_capital"] >= 0.0
        )

    def test_capital_off_omits_return_on_capital_field(self, tmp_path: Path):
        """Without --capital, JSON output is byte-equivalent for capital fields."""
        out_file = tmp_path / "result_no_capital.json"
        result = runner.invoke(app, ["price", "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        data = json.loads(out_file.read_text())
        assert "return_on_capital" not in data["cedant"]
        assert "peak_capital" not in data["cedant"]
        assert "return_on_capital" not in data["reinsurer"]

    def test_capital_invalid_value_exits_non_zero(self):
        """--capital with an unknown model id exits 1 with a clear message.

        ``solvency2`` is now a *valid* jurisdiction (ADR-101 Slice 4a), so the
        unknown-value probe uses a still-unrecognised id.
        """
        result = runner.invoke(app, ["price", "--capital", "bogus"])
        assert result.exit_code == 1, result.output
        assert "Unknown --capital value" in result.output

    def test_capital_licat_renders_roc_in_console_table(self):
        """Console output shows the Return on Capital row."""
        result = runner.invoke(app, ["price", "--capital", "licat"])
        assert result.exit_code == 0, result.output
        assert "Return on Capital" in result.output
        assert "Peak Capital" in result.output

    @pytest.mark.parametrize("jurisdiction", ["rbc", "solvency2"])
    def test_capital_jurisdiction_emits_return_on_capital_in_json(
        self, jurisdiction: str, tmp_path: Path
    ):
        """--capital rbc / solvency2 price end-to-end and emit the capital block (ADR-101)."""
        out_file = tmp_path / f"result_{jurisdiction}.json"
        result = runner.invoke(app, ["price", "--capital", jurisdiction, "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        data = json.loads(out_file.read_text())
        assert "return_on_capital" in data["cedant"]
        assert "peak_capital" in data["cedant"]
        assert "pv_capital" in data["cedant"]
        assert "pv_capital_strain" in data["cedant"]
        assert "capital_adjusted_irr" in data["cedant"]
        assert "return_on_capital" in data["reinsurer"]

    def test_capital_rbc_and_solvency2_differ_from_licat(self, tmp_path: Path):
        """The three jurisdictions produce distinct peak capital on the same block.

        Confirms the selector actually routes to a different calculator rather
        than silently falling back to LICAT.
        """
        peaks: dict[str, float] = {}
        for jurisdiction in ("licat", "rbc", "solvency2"):
            out_file = tmp_path / f"peak_{jurisdiction}.json"
            result = runner.invoke(
                app, ["price", "--capital", jurisdiction, "--output", str(out_file)]
            )
            assert result.exit_code == 0, result.output
            peaks[jurisdiction] = json.loads(out_file.read_text())["cedant"]["peak_capital"]
        # Distinct factor models → distinct peak capital across all three.
        assert len({round(p, 2) for p in peaks.values()}) == 3, peaks


@pytest.mark.slow
class TestPriceCommandAvailableCapital:
    """Tests for `polaris price --available-capital` ratio surfacing (ADR-104, Slice 4c-2a).

    The solvency-ratio *computation* is closed-form tested at the analytics
    level (ADR-103, ``TestRunWithCapitalRatio``); these tests verify the CLI
    threads the ``available_capital`` numerator in and emits the resulting
    ``capital_ratio`` on both the cedant and reinsurer JSON blocks.
    """

    def test_available_capital_emits_ratio_in_json(self, tmp_path: Path):
        """--available-capital surfaces capital_ratio + echoes available_capital."""
        out_file = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--capital",
                "licat",
                "--available-capital",
                "5000000",
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_file.read_text())
        assert data["cedant"]["available_capital"] == 5_000_000.0
        assert isinstance(data["cedant"]["capital_ratio"], float)
        assert data["cedant"]["capital_ratio"] > 0.0
        # Reinsurer view also carries the ratio (default treaty cedes a share).
        assert isinstance(data["reinsurer"]["capital_ratio"], float)
        assert data["reinsurer"]["capital_ratio"] > 0.0

    def test_available_capital_ratio_is_linear_in_numerator(self, tmp_path: Path):
        """Doubling available capital doubles the ratio (denominator fixed)."""
        ratios: dict[float, float] = {}
        for avail in (4_000_000.0, 8_000_000.0):
            out_file = tmp_path / f"ratio_{int(avail)}.json"
            result = runner.invoke(
                app,
                [
                    "price",
                    "--capital",
                    "licat",
                    "--available-capital",
                    str(avail),
                    "--output",
                    str(out_file),
                ],
            )
            assert result.exit_code == 0, result.output
            ratios[avail] = json.loads(out_file.read_text())["cedant"]["capital_ratio"]
        assert ratios[8_000_000.0] == pytest.approx(2.0 * ratios[4_000_000.0], rel=1e-9)

    def test_available_capital_renders_solvency_ratio_in_console(self):
        """Console capital table gains a Solvency Ratio row."""
        result = runner.invoke(
            app, ["price", "--capital", "licat", "--available-capital", "5000000"]
        )
        assert result.exit_code == 0, result.output
        assert "Solvency Ratio" in result.output

    def test_available_capital_without_capital_flag_errors(self):
        """--available-capital requires --capital; otherwise exit 1 with a message."""
        result = runner.invoke(app, ["price", "--available-capital", "5000000"])
        assert result.exit_code == 1, result.output
        assert "--available-capital" in result.output
        assert "--capital" in result.output

    def test_available_capital_non_positive_errors(self):
        """A non-positive available-capital numerator is rejected (exit 1)."""
        result = runner.invoke(app, ["price", "--capital", "licat", "--available-capital", "0"])
        assert result.exit_code == 1, result.output
        assert "--available-capital" in result.output

    def test_capital_without_available_leaves_ratio_null(self, tmp_path: Path):
        """--capital without --available-capital → capital_ratio is null (back-compat)."""
        out_file = tmp_path / "no_avail.json"
        result = runner.invoke(app, ["price", "--capital", "licat", "--output", str(out_file)])
        assert result.exit_code == 0, result.output
        data = json.loads(out_file.read_text())
        assert data["cedant"]["capital_ratio"] is None
        assert data["cedant"]["available_capital"] is None


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
        json_file.write_text('{"version": "v1", "mortality": {}, "lapse": {}}')
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

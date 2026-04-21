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


class TestCLIRatedBlockOutput:
    """Slice 3: CLI emits rating composition on `polaris price` JSON output."""

    def test_all_standard_block_reports_zero_rated(self, tmp_path):
        """Golden CSV has no substandard lives → rated_block shows 0 rated."""
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
        assert "rated_block" in payload
        rb = payload["rated_block"]
        assert rb["n_rated"] == 0
        assert rb["pct_rated_by_count"] == 0.0
        assert rb["face_weighted_mean_multiplier"] == 1.0

    def test_rated_csv_surfaces_rating_composition(self, tmp_path):
        """A CSV with substandard lives populates rated_block and renders the table."""
        # Build a rated CSV from the golden block plus two substandard rows.
        import polars as pl

        golden = pl.read_csv(GOLDEN_CSV, try_parse_dates=False)
        # Add the new columns with defaults on existing rows
        golden = golden.with_columns(
            [
                pl.lit(1.0, dtype=pl.Float64).alias("mortality_multiplier"),
                pl.lit(0.0, dtype=pl.Float64).alias("flat_extra_per_1000"),
            ]
        )
        rated_rows = [
            {
                "policy_id": "RATED-TBL2",
                "issue_age": 35,
                "attained_age": 40,
                "sex": "M",
                "smoker_status": "NS",
                "underwriting_class": "SUBSTANDARD",
                "face_amount": 500_000.0,
                "annual_premium": 1200.0,
                "product_type": "TERM",
                "policy_term": 20,
                "duration_inforce": 60,
                "reinsurance_cession_pct": None,
                "mortality_multiplier": 2.0,
                "flat_extra_per_1000": 0.0,
                "issue_date": "2021-04-01",
                "valuation_date": "2026-04-01",
            },
            {
                "policy_id": "RATED-FE5",
                "issue_age": 45,
                "attained_age": 50,
                "sex": "F",
                "smoker_status": "NS",
                "underwriting_class": "SUBSTANDARD",
                "face_amount": 500_000.0,
                "annual_premium": 2000.0,
                "product_type": "TERM",
                "policy_term": 20,
                "duration_inforce": 60,
                "reinsurance_cession_pct": None,
                "mortality_multiplier": 1.0,
                "flat_extra_per_1000": 5.0,
                "issue_date": "2021-04-01",
                "valuation_date": "2026-04-01",
            },
        ]
        rated_df = pl.concat(
            [golden, pl.DataFrame(rated_rows, schema=golden.schema)],
            how="vertical",
        )
        rated_csv = tmp_path / "rated_inforce.csv"
        rated_df.write_csv(rated_csv)

        output = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(GOLDEN_CONFIGS_DIR / "golden_config_flat.json"),
                "--inforce",
                str(rated_csv),
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
        payload = json.loads(output.read_text())
        rb = payload["rated_block"]
        assert rb["n_rated"] == 2
        assert rb["max_multiplier"] == 2.0
        assert rb["max_flat_extra_per_1000"] == 5.0
        # % by count = 2 / (6 + 2 added) — 6 golden + 2 rated = 8 total
        assert rb["pct_rated_by_count"] > 0.0

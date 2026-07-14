"""Tests for the `polaris ingest` CLI surfacing (A3' Slice 3).

Exercises the row-level quarantine + value-coercion pipeline through the CLI:
a messy cedant file ingests to a clean block + a rejects file + a report
enumerating what was dropped and why. Uses Typer's CliRunner in-process.

All fixtures pin explicit dates (ADR-074 guard) — no test reads the wall clock.
"""

import csv
from pathlib import Path

import polars as pl
import yaml
from typer.testing import CliRunner

from polaris_re.cli import app

runner = CliRunner()


def _write_messy_cedant_csv(path: Path) -> None:
    """A 3-row cedant extract: 2 clean rows + 1 bad row (negative face).

    Faces are reported in thousands (needs ``unit_scale``) and dates are US
    ``MM/DD/YYYY`` with a decisive day component (needs ``date_columns``).
    """
    rows = [
        ["POLNUM", "AGE", "CURAGE", "SEX", "SMK", "SUM", "PREM", "PLAN", "MIF", "ISSDT", "VALDT"],
        ["A1", 35, 37, "M", "N", 500, 1200, "TERM", 24, "01/15/2022", "01/15/2024"],
        ["A2", 40, 42, "F", "N", 250, 950, "TERM", 24, "03/10/2022", "03/10/2024"],
        # Bad row: negative face amount → quarantined as non_positive_face_amount.
        ["A3", 45, 47, "M", "Y", -999, 800, "TERM", 24, "06/01/2022", "06/01/2024"],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def _write_clean_cedant_csv(path: Path) -> None:
    """A 2-row all-clean cedant extract (faces in thousands, US dates)."""
    rows = [
        ["POLNUM", "AGE", "CURAGE", "SEX", "SMK", "SUM", "PREM", "PLAN", "MIF", "ISSDT", "VALDT"],
        ["A1", 35, 37, "M", "N", 500, 1200, "TERM", 24, "01/15/2022", "01/15/2024"],
        ["A2", 40, 42, "F", "N", 250, 950, "TERM", 24, "03/10/2022", "03/10/2024"],
    ]
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def _write_mapping(path: Path) -> None:
    """Mapping config that opts into unit scaling + date coercion."""
    config = {
        "column_mapping": {
            "policy_id": "POLNUM",
            "issue_age": "AGE",
            "attained_age": "CURAGE",
            "sex": "SEX",
            "smoker_status": "SMK",
            "face_amount": "SUM",
            "annual_premium": "PREM",
            "product_type": "PLAN",
            "duration_inforce": "MIF",
            "issue_date": "ISSDT",
            "valuation_date": "VALDT",
        },
        "code_translations": {"smoker_status": {"N": "NS", "Y": "S"}},
        "unit_scale": {"face_amount": 1000.0},
        "date_columns": ["issue_date", "valuation_date"],
    }
    with open(path, "w") as f:
        yaml.safe_dump(config, f)


def _setup(tmp_path: Path, messy: bool = True) -> tuple[Path, Path, Path, Path]:
    """Write raw CSV + mapping; return (raw, mapping, output, rejects) paths."""
    raw = tmp_path / "raw.csv"
    mapping = tmp_path / "mapping.yaml"
    output = tmp_path / "clean.csv"
    rejects = tmp_path / "clean.rejects.csv"
    if messy:
        _write_messy_cedant_csv(raw)
    else:
        _write_clean_cedant_csv(raw)
    _write_mapping(mapping)
    return raw, mapping, output, rejects


class TestIngestQuarantine:
    def test_messy_file_exits_zero_best_effort(self, tmp_path):
        """A messy file (1 bad row) ingests best-effort with exit 0, not all-or-nothing."""
        raw, mapping, output, _ = _setup(tmp_path)
        result = runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        assert result.exit_code == 0, result.output

    def test_clean_block_written_with_only_good_rows(self, tmp_path):
        """The clean output holds the 2 good rows; the bad row is not present."""
        raw, mapping, output, _ = _setup(tmp_path)
        runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        clean = pl.read_csv(output)
        assert clean.height == 2
        assert set(clean["policy_id"].to_list()) == {"A1", "A2"}

    def test_unit_scale_applied_to_clean_output(self, tmp_path):
        """Face reported in thousands is scaled to dollars in the clean output."""
        raw, mapping, output, _ = _setup(tmp_path)
        runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        clean = pl.read_csv(output)
        faces = dict(zip(clean["policy_id"].to_list(), clean["face_amount"].to_list(), strict=True))
        assert faces["A1"] == 500_000.0
        assert faces["A2"] == 250_000.0

    def test_dates_coerced_to_iso_in_clean_output(self, tmp_path):
        """US MM/DD/YYYY source dates become canonical ISO in the clean output."""
        raw, mapping, output, _ = _setup(tmp_path)
        runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        clean = pl.read_csv(output)
        issue = dict(zip(clean["policy_id"].to_list(), clean["issue_date"].to_list(), strict=True))
        assert issue["A1"] == "2022-01-15"
        assert issue["A2"] == "2022-03-10"

    def test_rejects_file_written_with_reason(self, tmp_path):
        """The bad row lands in a rejects file with a per-row reason column."""
        raw, mapping, output, rejects = _setup(tmp_path)
        runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        assert rejects.exists(), "rejects file should be written alongside the clean output"
        rej = pl.read_csv(rejects)
        assert rej.height == 1
        assert rej["policy_id"].to_list() == ["A3"]
        assert "_reject_reason" in rej.columns
        assert "non_positive_face_amount" in rej["_reject_reason"][0]

    def test_report_shows_input_and_rejected_counts(self, tmp_path):
        """The printed report enumerates rows examined vs. rejected and the reason."""
        raw, mapping, output, _ = _setup(tmp_path)
        result = runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        assert "3" in result.output  # n_input
        assert "1" in result.output  # n_rejected
        assert "non_positive_face_amount" in result.output

    def test_custom_rejects_path_honoured(self, tmp_path):
        """--rejects overrides the derived rejects path."""
        raw, mapping, output, _ = _setup(tmp_path)
        custom = tmp_path / "dropped.csv"
        runner.invoke(
            app,
            ["ingest", "-c", str(mapping), "-o", str(output), "--rejects", str(custom), str(raw)],
        )
        assert custom.exists()
        assert pl.read_csv(custom)["policy_id"].to_list() == ["A3"]


class TestIngestUnparseableDate:
    def test_unparseable_date_row_quarantined(self, tmp_path):
        """A row whose date parses under no known format is quarantined, not crashed."""
        raw = tmp_path / "raw.csv"
        rows = [
            [
                "POLNUM",
                "AGE",
                "CURAGE",
                "SEX",
                "SMK",
                "SUM",
                "PREM",
                "PLAN",
                "MIF",
                "ISSDT",
                "VALDT",
            ],
            ["A1", 35, 37, "M", "N", 500, 1200, "TERM", 24, "01/15/2022", "01/15/2024"],
            ["A2", 40, 42, "F", "N", 250, 950, "TERM", 24, "notadate", "03/10/2024"],
        ]
        with open(raw, "w", newline="") as f:
            csv.writer(f).writerows(rows)
        mapping = tmp_path / "mapping.yaml"
        _write_mapping(mapping)
        output = tmp_path / "clean.csv"
        result = runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        assert result.exit_code == 0, result.output
        rej = pl.read_csv(tmp_path / "clean.rejects.csv")
        assert rej["policy_id"].to_list() == ["A2"]
        assert "unparseable_issue_date" in rej["_reject_reason"][0]


class TestIngestThreshold:
    def test_max_reject_pct_exceeded_exits_1(self, tmp_path):
        """When rejects exceed --max-reject-pct, the command hard-fails (exit 1)."""
        raw, mapping, output, _ = _setup(tmp_path)  # 1/3 = 33% rejected
        result = runner.invoke(
            app,
            ["ingest", "-c", str(mapping), "-o", str(output), "--max-reject-pct", "10", str(raw)],
        )
        assert result.exit_code == 1, result.output
        assert "reject" in result.output.lower()

    def test_max_reject_pct_within_threshold_exits_0(self, tmp_path):
        """Below the threshold, the command succeeds."""
        raw, mapping, output, _ = _setup(tmp_path)  # 33% rejected
        result = runner.invoke(
            app,
            ["ingest", "-c", str(mapping), "-o", str(output), "--max-reject-pct", "50", str(raw)],
        )
        assert result.exit_code == 0, result.output


class TestIngestCleanFile:
    def test_clean_file_writes_no_rejects_file(self, tmp_path):
        """A fully clean file writes the clean output and no rejects file."""
        raw, mapping, output, rejects = _setup(tmp_path, messy=False)
        result = runner.invoke(app, ["ingest", "-c", str(mapping), "-o", str(output), str(raw)])
        assert result.exit_code == 0, result.output
        assert output.exists()
        assert not rejects.exists()
        assert pl.read_csv(output).height == 2

    def test_validate_only_writes_nothing(self, tmp_path):
        """--validate-only reports but writes neither clean nor rejects files."""
        raw, mapping, output, rejects = _setup(tmp_path)
        result = runner.invoke(
            app, ["ingest", "-c", str(mapping), "-o", str(output), "--validate-only", str(raw)]
        )
        assert result.exit_code == 0, result.output
        assert not output.exists()
        assert not rejects.exists()

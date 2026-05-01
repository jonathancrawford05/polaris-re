"""CLI integration tests for ``polaris rate-schedule --table`` (ADR-053).

The flat-schedule path remains covered by ``test_rate_schedule.py`` and
``polaris rate-schedule`` smoke-tests elsewhere. These tests focus on the
new ``--table`` flag, the standalone ``write_yrt_rate_table_excel``
output, the JSON serialisation helper, and the CSV-rejection guard.

All end-to-end runs solve the actual rate grid via brentq and are
``@pytest.mark.slow``; the JSON helper unit tests are fast.
"""

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook
from typer.testing import CliRunner

from polaris_re.cli import _yrt_rate_table_to_dict, app
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.reinsurance.yrt_rate_table import YRTRateTable, YRTRateTableArray

runner = CliRunner()


# Smallest reasonable axis grid that still exercises the brentq solver
# end-to-end without making the slow tests too slow. Two ages, term 10.
_FAST_AGES = "30,40"
_FAST_TERM = "10"


@pytest.mark.slow
class TestRateScheduleTableCLI:
    """`polaris rate-schedule --table` end-to-end behaviour."""

    def test_no_table_default_runs_unchanged(self, tmp_path: Path) -> None:
        """Without ``--table`` the CSV-output path is preserved (ADR-053 backcompat)."""
        out = tmp_path / "flat.csv"
        result = runner.invoke(
            app,
            [
                "rate-schedule",
                "--ages",
                _FAST_AGES,
                "--term",
                _FAST_TERM,
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        # Flat schedule CSV header carries the per-cohort columns.
        first = out.read_text().splitlines()[0]
        assert "issue_age" in first
        assert "rate_per_1000" in first

    def test_table_emits_xlsx(self, tmp_path: Path) -> None:
        """`--table -o NAME.xlsx` writes a workbook with both sheets."""
        out = tmp_path / "table.xlsx"
        result = runner.invoke(
            app,
            [
                "rate-schedule",
                "--table",
                "--ages",
                _FAST_AGES,
                "--term",
                _FAST_TERM,
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        wb = load_workbook(out)
        assert "Summary" in wb.sheetnames
        assert "YRT Rate Table" in wb.sheetnames

    def test_table_csv_output_rejected(self, tmp_path: Path) -> None:
        """`--table -o NAME.csv` exits 1 with a clear error message."""
        out = tmp_path / "wrong.csv"
        result = runner.invoke(
            app,
            [
                "rate-schedule",
                "--table",
                "--ages",
                _FAST_AGES,
                "--term",
                _FAST_TERM,
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 1
        assert ".xlsx" in result.output
        assert not out.exists()

    def test_table_json_emits_cohort_dict(self, tmp_path: Path) -> None:
        """`--table --json PATH` writes the YRTRateTable dict shape."""
        out = tmp_path / "table.json"
        result = runner.invoke(
            app,
            [
                "rate-schedule",
                "--table",
                "--ages",
                _FAST_AGES,
                "--term",
                _FAST_TERM,
                "--json",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out.read_text())
        # Top-level shape per ADR-053.
        assert set(payload.keys()) >= {
            "table_name",
            "min_age",
            "max_age",
            "select_period_years",
            "cohorts",
        }
        # Single demo cohort: M / U (UNKNOWN smoker, demo aggregate table).
        assert "M_U" in payload["cohorts"]
        cohort = payload["cohorts"]["M_U"]
        assert {"min_age", "max_age", "select_period", "rates"} <= set(cohort.keys())
        # Ages 30..40: n_ages = max(30,40) - min(30,40) + 1 = 11 rows.
        # Only ages 30 and 40 are solved; intermediate rows (31..39)
        # are forward/back-filled by generate_table to satisfy
        # YRTRateTableArray's contiguous-age storage contract
        # (ADR-051 documented behaviour). select_period=0 → 1 column.
        assert len(cohort["rates"]) == 11
        assert all(len(row) == 1 for row in cohort["rates"])

    def test_table_with_select_period(self, tmp_path: Path) -> None:
        """`--select-period N` produces N+1 duration columns per cohort."""
        out = tmp_path / "table.json"
        result = runner.invoke(
            app,
            [
                "rate-schedule",
                "--table",
                "--ages",
                _FAST_AGES,
                "--term",
                _FAST_TERM,
                "--select-period",
                "3",
                "--json",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out.read_text())
        assert payload["select_period_years"] == 3
        cohort = payload["cohorts"]["M_U"]
        assert cohort["select_period"] == 3
        # Each row has select_period + 1 = 4 columns. 11 rows from the
        # contiguous age expansion (ages 30..40); see
        # test_table_json_emits_cohort_dict for the fill-in rationale.
        assert all(len(row) == 4 for row in cohort["rates"])
        # Generated table broadcasts the per-age flat rate across cols
        # (ADR-051 / ADR-053 "Out of scope") — verify the row is constant.
        for row in cohort["rates"]:
            assert max(row) == pytest.approx(min(row))


class TestYrtRateTableJsonHelper:
    """Unit tests for ``_yrt_rate_table_to_dict`` — no CLI invocation."""

    def _make_table(self) -> YRTRateTable:
        import numpy as np

        rates = np.array(
            [
                [0.50, 0.55, 0.60],
                [0.55, 0.60, 0.65],
            ],
            dtype=np.float64,
        )
        arr = YRTRateTableArray(rates=rates, min_age=40, max_age=41, select_period=2)
        return YRTRateTable.from_arrays(
            table_name="unit-test",
            arrays={(Sex.MALE, SmokerStatus.NON_SMOKER): arr},
        )

    def test_top_level_shape(self) -> None:
        """Top-level dict carries table metadata."""
        d = _yrt_rate_table_to_dict(self._make_table())
        assert d["table_name"] == "unit-test"
        assert d["min_age"] == 40
        assert d["max_age"] == 41
        assert d["select_period_years"] == 2

    def test_cohort_dict_round_trip(self) -> None:
        """Cohort entry preserves per-(age, dur) rate values."""
        d = _yrt_rate_table_to_dict(self._make_table())
        cohort = d["cohorts"]["M_NS"]
        assert cohort["min_age"] == 40
        assert cohort["max_age"] == 41
        assert cohort["select_period"] == 2
        # Rate at (age 40, dur_1) == 0.50; (age 41, ultimate) == 0.65.
        assert cohort["rates"][0][0] == pytest.approx(0.50)
        assert cohort["rates"][1][2] == pytest.approx(0.65)

    def test_dict_is_json_serialisable(self) -> None:
        """Output passes through ``json.dumps`` without errors."""
        d = _yrt_rate_table_to_dict(self._make_table())
        # Empty `default` callback so non-serialisable objects raise.
        json.dumps(d)


class TestHelperTypeGuards:
    """`_render_yrt_rate_table` and `_yrt_rate_table_to_dict` use explicit
    `raise PolarisValidationError` (not bare `assert`) so the guard holds
    under `python -O`. PR #39 P1 fix.
    """

    def test_render_rejects_non_table(self) -> None:
        from polaris_re.cli import _render_yrt_rate_table
        from polaris_re.core.exceptions import PolarisValidationError

        with pytest.raises(PolarisValidationError, match="Expected YRTRateTable"):
            _render_yrt_rate_table("not a table", target_irr=0.10)

    def test_to_dict_rejects_non_table(self) -> None:
        from polaris_re.core.exceptions import PolarisValidationError

        with pytest.raises(PolarisValidationError, match="Expected YRTRateTable"):
            _yrt_rate_table_to_dict({"not": "a table"})

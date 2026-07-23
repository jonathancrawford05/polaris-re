"""
Tests for the ``polaris benchmark`` CLI command (validation & benchmark pack).

Slice 3 of the Validation & Benchmark Pack epic surfaces the engine-agnostic
reference pack (``polaris_re.analytics.validation``) on the CLI. These tests use
Typer's :class:`CliRunner` to invoke the command in-process and assert the
diligence contract: the full pack passes and exits 0, each sub-pack is
selectable, a failing case forces a non-zero exit (so CI can gate on it), and
the Markdown / JSON exports are well-formed.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from polaris_re.analytics.validation import (
    ValidationCase,
    ValidationCategory,
    ValidationReport,
    run_full_validation_pack,
)
from polaris_re.cli import app

runner = CliRunner()


class TestBenchmarkCommand:
    def test_full_pack_exits_zero(self) -> None:
        """The full pack reproduces every reference and exits 0."""
        result = runner.invoke(app, ["benchmark"])
        assert result.exit_code == 0, result.output
        assert "cases passed" in result.output

    def test_full_pack_reports_all_cases(self) -> None:
        """Console output announces the full pass count (computed dynamically)."""
        n_cases = run_full_validation_pack().n_cases
        result = runner.invoke(app, ["benchmark"])
        assert result.exit_code == 0, result.output
        assert f"{n_cases}/{n_cases}" in result.output

    def test_closed_form_pack_selectable(self) -> None:
        result = runner.invoke(app, ["benchmark", "--pack", "closed-form"])
        assert result.exit_code == 0, result.output
        assert "cases passed" in result.output

    def test_deck_pack_selectable(self) -> None:
        result = runner.invoke(app, ["benchmark", "--pack", "deck"])
        assert result.exit_code == 0, result.output
        assert "Illustrative Life Table" in result.output

    def test_experience_pack_selectable(self) -> None:
        """The A4' experience improvement-recovery deck is selectable and passes."""
        result = runner.invoke(app, ["benchmark", "--pack", "experience"])
        assert result.exit_code == 0, result.output
        assert "5/5 cases passed" in result.output

    def test_unknown_pack_exits_two(self) -> None:
        """An unrecognised --pack is a usage error (exit 2), not a silent no-op."""
        result = runner.invoke(app, ["benchmark", "--pack", "nonsense"])
        assert result.exit_code == 2, result.output
        assert "Unknown pack" in result.output

    def test_writes_markdown_report(self, tmp_path: Path) -> None:
        out = tmp_path / "report.md"
        result = runner.invoke(app, ["benchmark", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.is_file()
        text = out.read_text(encoding="utf-8")
        assert text == run_full_validation_pack().to_markdown()
        assert "| Case | Category |" in text

    def test_writes_json_report(self, tmp_path: Path) -> None:
        out = tmp_path / "report.json"
        result = runner.invoke(app, ["benchmark", "--json", str(out)])
        assert result.exit_code == 0, result.output
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "results" in data
        assert len(data["results"]) == run_full_validation_pack().n_cases
        assert all(r["status"] == "PASS" for r in data["results"])

    def test_failing_case_forces_nonzero_exit(self, monkeypatch) -> None:
        """A FAIL in the pack must exit non-zero so CI can gate on it.

        Monkeypatch the pack builder to return a report containing one case whose
        computed value is deliberately off its reference; the command must exit 1
        and surface the failure count.
        """
        bad_case = ValidationCase(
            case_id="FORCED-FAIL",
            name="Deliberately failing reference",
            category=ValidationCategory.CLOSED_FORM,
            source="unit test",
            description="Computed intentionally diverges from expected.",
            expected=1.0,
            tolerance_rtol=1e-9,
        )
        forced = ValidationReport(
            title="Forced-fail pack",
            results=(bad_case.evaluate(2.0),),
        )
        monkeypatch.setattr(
            "polaris_re.analytics.validation.run_full_validation_pack",
            lambda: forced,
        )
        result = runner.invoke(app, ["benchmark"])
        assert result.exit_code == 1, result.output
        assert "FAILED" in result.output

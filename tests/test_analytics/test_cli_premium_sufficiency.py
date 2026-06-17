"""
CLI premium-sufficiency surfacing tests (ADR-083).

`polaris price` emits a `premium_sufficiency` block per cohort (and at the
top level for single-cohort runs) and accepts `--sufficiency-target-margin`.
"""

import json
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

import polaris_re.cli as cli_mod
from polaris_re.analytics.premium_sufficiency import PremiumSufficiencyResult
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


def _make_result(**overrides: object) -> PremiumSufficiencyResult:
    """Build a PremiumSufficiencyResult with round, self-consistent values."""
    base: dict[str, object] = {
        "discount_rate": 0.06,
        "target_margin": 0.0,
        "pv_premiums": 100_000.0,
        "pv_claims": 8_000.0,
        "pv_surrenders": 2_000.0,
        "pv_benefits": 10_000.0,  # = pv_claims + pv_surrenders
        "pv_expenses": 4_000.0,
        "sufficiency_margin": 86_000.0,  # = premiums - benefits - expenses
        "sufficiency_ratio": 0.86,
        "loss_ratio": 0.10,
        "expense_ratio": 0.04,
        "combined_ratio": 0.14,
        "is_sufficient": True,
    }
    base.update(overrides)
    return PremiumSufficiencyResult(**base)  # type: ignore[arg-type]


class TestCLISufficiencyTableBreakdown:
    """The Rich `Premium Sufficiency` table splits PV Benefits into its two
    line items (PV Claims / PV Surrenders), matching the Excel Summary panel
    (ADR-084). The JSON block already carried the breakdown since ADR-083."""

    def _render(self, result: PremiumSufficiencyResult, monkeypatch: pytest.MonkeyPatch) -> str:
        recorder = Console(width=200, record=True)
        monkeypatch.setattr(cli_mod, "console", recorder)
        cli_mod._render_sufficiency_table(result, title="T", border_style="cyan")
        return recorder.export_text()

    def test_table_includes_claims_and_surrenders_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        text = self._render(_make_result(), monkeypatch)
        assert "PV Claims" in text
        assert "PV Surrenders" in text

    def test_breakdown_rows_precede_pv_benefits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ADR-084 reading order: the two components sit before their total.
        text = self._render(_make_result(), monkeypatch)
        assert text.index("PV Premiums") < text.index("PV Claims")
        assert text.index("PV Claims") < text.index("PV Surrenders")
        assert text.index("PV Surrenders") < text.index("PV Benefits")

    def test_breakdown_values_sum_to_benefits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Closed-form: rendered PV Claims + PV Surrenders == PV Benefits.
        text = self._render(_make_result(), monkeypatch)
        assert "$8,000" in text  # PV Claims
        assert "$2,000" in text  # PV Surrenders
        assert "$10,000" in text  # PV Benefits = 8,000 + 2,000

    def test_existing_rows_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Additive change: the pre-ADR rows are all still rendered.
        text = self._render(_make_result(), monkeypatch)
        for label in (
            "Discount Rate",
            "Target Margin",
            "PV Premiums",
            "PV Benefits",
            "PV Expenses",
            "Sufficiency Margin",
            "Loss Ratio",
            "Expense Ratio",
            "Combined Ratio",
            "Verdict",
        ):
            assert label in text

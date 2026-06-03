"""
Tests for ``polaris portfolio`` CLI subcommands (Milestone 5.2 Slice 2).

Exercises the real CLI command path via Typer's ``CliRunner``. Each test
builds a minimal YAML / JSON portfolio config (flat mortality so no SOA
tables are required), runs ``polaris portfolio run``, and validates the
JSON output against the in-process ``Portfolio.run().to_dict()`` numbers.
"""

import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from polaris_re.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _policy(policy_id: str, face: float = 500_000.0, product: str = "TERM") -> dict:
    today = date.today().isoformat()
    return {
        "policy_id": policy_id,
        "issue_age": 40,
        "attained_age": 40,
        "sex": "M",
        "smoker": False,
        "underwriting_class": "STANDARD",
        "face_amount": face,
        "annual_premium": face * 0.005,
        "policy_term": 20 if product == "TERM" else None,
        "duration_inforce": 0,
        "issue_date": "2025-01-01",
        "valuation_date": today,
        "product_type": product,
    }


def _deal_block(
    deal_id: str,
    cedant: str,
    *,
    product: str = "TERM",
    treaty_type: str = "Coinsurance",
    cession_pct: float = 0.5,
    n_policies: int = 2,
    face: float = 500_000.0,
    projection_years: int = 10,
    valuation_date: str | None = None,
) -> dict:
    """Return one deal entry for the portfolio YAML config.

    When ``valuation_date`` (ISO string) is supplied, it is stamped on the
    deal config so the runner builds a ``ProjectionConfig`` with that date —
    used by the calendar-alignment tests to build mixed-date portfolios.
    """
    deal: dict = {
        "product_type": product,
        "treaty_type": treaty_type,
        "cession_pct": cession_pct,
        "yrt_loading": 0.10,
        "modco_rate": 0.045,
        "discount_rate": 0.06,
        "hurdle_rate": 0.10,
        "projection_years": projection_years,
    }
    if valuation_date is not None:
        deal["valuation_date"] = valuation_date
    return {
        "deal_id": deal_id,
        "cedant": cedant,
        "mortality": {"source": "flat", "flat_qx": 0.002},
        "lapse": {"duration_table": {"1": 0.05, "2": 0.04, "ultimate": 0.03}},
        "deal": deal,
        "policies": [
            _policy(f"{deal_id}_{i:03d}", face=face, product=product) for i in range(n_policies)
        ],
    }


def _write_yaml(tmp_path: Path, config: dict, name: str = "portfolio.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def _write_json(tmp_path: Path, config: dict, name: str = "portfolio.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(config))
    return path


def _two_deal_config() -> dict:
    return {
        "hurdle_rate": 0.10,
        "deals": [
            _deal_block("D1", "CedantA"),
            _deal_block("D2", "CedantB"),
        ],
    }


# ---------------------------------------------------------------------------
# polaris portfolio run
# ---------------------------------------------------------------------------


class TestPortfolioRunCommand:
    """End-to-end ``polaris portfolio run`` against a YAML config."""

    def test_runs_on_two_deal_yaml(self, tmp_path: Path) -> None:
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "result.json"

        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        assert out_path.exists()

    def test_json_output_total_equals_sum_of_per_deal_pv(self, tmp_path: Path) -> None:
        """``total_pv_profits`` must equal the sum of per-deal PV profits."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "result.json"

        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())

        per_deal_sum = sum(deal["profit_test"]["pv_profits"] for deal in payload["deals"])
        assert payload["total_pv_profits"] == pytest.approx(per_deal_sum, rel=1e-9, abs=1e-3)
        assert payload["n_deals"] == 2

    def test_json_output_includes_concentration_and_hhi(self, tmp_path: Path) -> None:
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "result.json"

        runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(out_path)],
        )
        payload = json.loads(out_path.read_text())
        assert set(payload["concentration"].keys()) == {"cedant", "product", "treaty"}
        assert set(payload["hhi"].keys()) == {"cedant", "product", "treaty"}
        # Two equal-face cedants split 50/50
        assert payload["concentration"]["cedant"]["CedantA"] == pytest.approx(0.5)
        assert payload["concentration"]["cedant"]["CedantB"] == pytest.approx(0.5)

    def test_renders_per_deal_table(self, tmp_path: Path) -> None:
        """The console output should contain a per-deal breakdown header."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result = runner.invoke(app, ["portfolio", "run", "--config", str(config_path)])
        assert result.exit_code == 0, result.output
        # Per-deal table and concentration table titles appear in output
        assert "D1" in result.output
        assert "D2" in result.output
        assert "CedantA" in result.output
        assert "CedantB" in result.output

    def test_accepts_json_config(self, tmp_path: Path) -> None:
        """The CLI must accept a ``.json`` config too — YAML is a superset."""
        config_path = _write_json(tmp_path, _two_deal_config())
        out_path = tmp_path / "result.json"
        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert payload["n_deals"] == 2

    def test_inforce_csv_path_overrides_inline_policies(self, tmp_path: Path) -> None:
        """When a deal specifies ``inforce_csv``, policies come from the CSV."""
        today = date.today().isoformat()
        csv_path = tmp_path / "d1.csv"
        csv_path.write_text(
            "policy_id,issue_age,attained_age,sex,smoker_status,"
            "face_amount,annual_premium,product_type,policy_term,"
            "duration_inforce,issue_date,valuation_date\n"
            f"P1,40,40,M,NS,500000.0,2500.0,TERM,20,0,2020-01-01,{today}\n"
            f"P2,40,40,M,NS,500000.0,2500.0,TERM,20,0,2020-01-01,{today}\n"
        )

        deal = _deal_block("D1", "CedantA")
        deal.pop("policies")
        deal["inforce_csv"] = str(csv_path)
        cfg = {"hurdle_rate": 0.10, "deals": [deal]}

        config_path = _write_yaml(tmp_path, cfg)
        out_path = tmp_path / "result.json"
        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert payload["deals"][0]["n_policies"] == 2

    def test_invalid_treaty_type_rejected(self, tmp_path: Path) -> None:
        """Non-proportional treaties (e.g. StopLoss) are out of scope."""
        # The portfolio runner only accepts YRT / Coinsurance / Modco; "None"
        # treaty must also be rejected because Portfolio.add_deal needs a
        # cession_pct.
        cfg = _two_deal_config()
        cfg["deals"][0]["deal"]["treaty_type"] = "None"
        config_path = _write_yaml(tmp_path, cfg)
        result = runner.invoke(app, ["portfolio", "run", "--config", str(config_path)])
        assert result.exit_code != 0

    def test_missing_config_file_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["portfolio", "run", "--config", str(tmp_path / "nope.yaml")])
        assert result.exit_code != 0

    def test_yrt_rate_derived_when_not_supplied(self, tmp_path: Path) -> None:
        """When treaty_type='YRT' without an explicit rate, derive from gross.

        A claims-only cession (rate=None) would yield ``peak_ceded_nar = 0``;
        a properly derived rate populates the NAR vector and produces
        non-trivial ceded premiums in the per-deal profit test.
        """
        cfg = {
            "hurdle_rate": 0.10,
            "deals": [
                _deal_block("D1", "CedantA", treaty_type="YRT", cession_pct=0.8),
            ],
        }
        config_path = _write_yaml(tmp_path, cfg)
        out_path = tmp_path / "result.json"
        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert payload["peak_ceded_nar"] > 0.0
        # The YRT deal's ceded NAR vector should be non-zero somewhere
        assert max(payload["deals"][0]["ceded_nar"]) > 0.0

    def test_hurdle_rate_flag_overrides_config(self, tmp_path: Path) -> None:
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "portfolio",
                "run",
                "--config",
                str(config_path),
                "--hurdle-rate",
                "0.08",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert payload["hurdle_rate"] == pytest.approx(0.08)
        for deal in payload["deals"]:
            assert deal["profit_test"]["hurdle_rate"] == pytest.approx(0.08)


# ---------------------------------------------------------------------------
# polaris portfolio report
# ---------------------------------------------------------------------------


class TestPortfolioReportCommand:
    """``polaris portfolio report`` re-renders a result JSON without re-running."""

    def test_report_re_renders_from_result_json(self, tmp_path: Path) -> None:
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result_path = tmp_path / "result.json"

        run = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(result_path)],
        )
        assert run.exit_code == 0, run.output

        report = runner.invoke(app, ["portfolio", "report", "--result", str(result_path)])
        assert report.exit_code == 0, report.output
        # Per-deal ids and cedant labels appear in the rendered report
        assert "D1" in report.output
        assert "D2" in report.output
        assert "CedantA" in report.output

    def test_report_missing_file_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["portfolio", "report", "--result", str(tmp_path / "missing.json")]
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# polaris portfolio run --align (ADR-061 Slice 2)
# ---------------------------------------------------------------------------


def _mixed_date_two_deal_config() -> dict:
    """Two deals on different valuation dates — exercises calendar alignment."""
    return {
        "hurdle_rate": 0.10,
        "deals": [
            _deal_block("D1", "CedantA", valuation_date="2025-01-01"),
            _deal_block("D2", "CedantB", valuation_date="2025-07-01"),
        ],
    }


class TestPortfolioRunAlignFlag:
    """``polaris portfolio run --align`` threads the calendar-align mode."""

    def test_strict_default_rejects_mixed_dates(self, tmp_path: Path) -> None:
        """Without ``--align``, mixed inception dates fail with a clean error."""
        config_path = _write_yaml(tmp_path, _mixed_date_two_deal_config())
        result = runner.invoke(app, ["portfolio", "run", "--config", str(config_path)])
        assert result.exit_code != 0
        # The portfolio runner's strict-mode message is surfaced. Rich may
        # line-wrap arbitrarily, so collapse whitespace before searching.
        flat = " ".join(result.output.split())
        assert "same valuation date" in flat

    def test_calendar_mode_accepts_mixed_dates(self, tmp_path: Path) -> None:
        """``--align calendar`` aggregates the mixed-date config."""
        config_path = _write_yaml(tmp_path, _mixed_date_two_deal_config())
        out_path = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "portfolio",
                "run",
                "--config",
                str(config_path),
                "--align",
                "calendar",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        # Grid origin is the earliest valuation date (D1 at 2025-01-01)
        assert payload["grid_origin"] == "2025-01-01"
        # Projection extends to cover the later deal's horizon: 6 months
        # offset + 10 years horizon = 126 months.
        assert payload["projection_months"] == 126

    def test_calendar_mode_exposes_per_deal_offsets_in_json(self, tmp_path: Path) -> None:
        """Each deal block carries its own ``valuation_date`` and ``grid_offset``."""
        config_path = _write_yaml(tmp_path, _mixed_date_two_deal_config())
        out_path = tmp_path / "result.json"
        runner.invoke(
            app,
            [
                "portfolio",
                "run",
                "--config",
                str(config_path),
                "--align",
                "calendar",
                "--output",
                str(out_path),
            ],
        )
        payload = json.loads(out_path.read_text())
        deals_by_id = {d["deal_id"]: d for d in payload["deals"]}
        assert deals_by_id["D1"]["valuation_date"] == "2025-01-01"
        assert deals_by_id["D1"]["grid_offset"] == 0
        assert deals_by_id["D2"]["valuation_date"] == "2025-07-01"
        assert deals_by_id["D2"]["grid_offset"] == 6

    def test_strict_mode_zero_offsets_and_origin_equals_valuation(self, tmp_path: Path) -> None:
        """Default ``strict`` puts every deal at offset 0; origin == shared date."""
        cfg = {
            "hurdle_rate": 0.10,
            "deals": [
                _deal_block("D1", "CedantA", valuation_date="2025-03-01"),
                _deal_block("D2", "CedantB", valuation_date="2025-03-01"),
            ],
        }
        config_path = _write_yaml(tmp_path, cfg)
        out_path = tmp_path / "result.json"
        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert payload["grid_origin"] == "2025-03-01"
        for deal in payload["deals"]:
            assert deal["grid_offset"] == 0
            assert deal["valuation_date"] == "2025-03-01"

    def test_calendar_renders_grid_origin_in_overview(self, tmp_path: Path) -> None:
        """The Rich overview table includes the grid origin row."""
        config_path = _write_yaml(tmp_path, _mixed_date_two_deal_config())
        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--align", "calendar"],
        )
        assert result.exit_code == 0, result.output
        assert "Grid Origin" in result.output
        assert "2025-01-01" in result.output

    def test_invalid_align_value_rejected(self, tmp_path: Path) -> None:
        """An unrecognised ``--align`` value exits cleanly with a helpful error."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--align", "bogus"],
        )
        assert result.exit_code != 0
        flat = " ".join(result.output.split())
        assert "strict" in flat and "calendar" in flat

    def test_calendar_requires_common_day_of_month(self, tmp_path: Path) -> None:
        """Calendar mode rejects valuation dates on different days-of-month."""
        cfg = {
            "hurdle_rate": 0.10,
            "deals": [
                _deal_block("D1", "CedantA", valuation_date="2025-01-01"),
                _deal_block("D2", "CedantB", valuation_date="2025-07-15"),
            ],
        }
        config_path = _write_yaml(tmp_path, cfg)
        result = runner.invoke(
            app,
            ["portfolio", "run", "--config", str(config_path), "--align", "calendar"],
        )
        assert result.exit_code != 0
        flat = " ".join(result.output.split())
        assert "day-of-month" in flat


# ---------------------------------------------------------------------------
# polaris portfolio scenarios (ADR-066)
# ---------------------------------------------------------------------------


class TestPortfolioScenariosCommand:
    """``polaris portfolio scenarios`` surfaces ``Portfolio.run_scenarios``.

    The internal helper landed in ADR-064; this subcommand wires it through
    the CLI so the deal-committee six-scenario stress workflow is reachable
    end-to-end without the Python API.
    """

    def test_runs_standard_scenarios_on_two_deal_yaml(self, tmp_path: Path) -> None:
        """``--scenarios standard`` runs the default six-scenario stress set."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "scenarios.json"

        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "standard",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out_path.exists()
        payload = json.loads(out_path.read_text())
        # PortfolioScenarioResult.to_dict() returns {"scenarios": [...]}
        assert "scenarios" in payload
        names = [entry["name"] for entry in payload["scenarios"]]
        assert names == [
            "BASE",
            "MORT_110",
            "MORT_90",
            "LAPSE_80",
            "LAPSE_120",
            "MORT_110_LAPSE_80",
        ]

    def test_standard_is_default_when_flag_omitted(self, tmp_path: Path) -> None:
        """Omitting ``--scenarios`` runs the standard six-scenario set."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "scenarios.json"
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert len(payload["scenarios"]) == 6

    def test_named_subset_filters_to_requested_scenarios(self, tmp_path: Path) -> None:
        """A comma-separated list filters the standard set in order supplied."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "scenarios.json"
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE,MORT_110",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert [s["name"] for s in payload["scenarios"]] == ["BASE", "MORT_110"]

    def test_each_scenario_entry_carries_full_portfolio_result(self, tmp_path: Path) -> None:
        """Each scenario's nested result mirrors PortfolioResult.to_dict()."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "scenarios.json"
        runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE",
                "--output",
                str(out_path),
            ],
        )
        payload = json.loads(out_path.read_text())
        base = payload["scenarios"][0]["result"]
        # Same keys as PortfolioResult.to_dict()
        for k in (
            "n_deals",
            "hurdle_rate",
            "total_pv_profits",
            "total_irr",
            "total_face_amount",
            "deals",
            "concentration",
            "hhi",
        ):
            assert k in base, f"missing key: {k}"
        assert base["n_deals"] == 2

    def test_mortality_stress_lowers_pv_relative_to_base(self, tmp_path: Path) -> None:
        """+10% mortality stress reduces aggregate PV profits vs. BASE."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "scenarios.json"
        runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE,MORT_110",
                "--output",
                str(out_path),
            ],
        )
        payload = json.loads(out_path.read_text())
        by_name = {s["name"]: s["result"] for s in payload["scenarios"]}
        assert by_name["MORT_110"]["total_pv_profits"] < by_name["BASE"]["total_pv_profits"]

    def test_unknown_scenario_name_rejected(self, tmp_path: Path) -> None:
        """An unknown scenario name exits cleanly with a helpful error."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BOGUS",
            ],
        )
        assert result.exit_code != 0
        flat = " ".join(result.output.split())
        assert "BOGUS" in flat

    def test_renders_per_scenario_table(self, tmp_path: Path) -> None:
        """The console output includes a per-scenario summary table."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE,MORT_110",
            ],
        )
        assert result.exit_code == 0, result.output
        # Scenario names appear in the rendered table
        assert "BASE" in result.output
        assert "MORT_110" in result.output

    def test_hurdle_rate_flag_overrides_config(self, tmp_path: Path) -> None:
        """``--hurdle-rate`` overrides the config value for every scenario."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        out_path = tmp_path / "scenarios.json"
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE",
                "--hurdle-rate",
                "0.08",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        assert payload["scenarios"][0]["result"]["hurdle_rate"] == pytest.approx(0.08)

    def test_calendar_align_threads_through_to_scenarios(self, tmp_path: Path) -> None:
        """``--align calendar`` runs every scenario on the common grid."""
        config_path = _write_yaml(tmp_path, _mixed_date_two_deal_config())
        out_path = tmp_path / "scenarios.json"
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE",
                "--align",
                "calendar",
                "--output",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(out_path.read_text())
        # The BASE scenario carries the calendar-aligned grid metadata
        assert payload["scenarios"][0]["result"]["grid_origin"] == "2025-01-01"

    def test_strict_default_rejects_mixed_dates(self, tmp_path: Path) -> None:
        """Without ``--align calendar``, mixed dates fail with a clean error."""
        config_path = _write_yaml(tmp_path, _mixed_date_two_deal_config())
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE",
            ],
        )
        assert result.exit_code != 0
        flat = " ".join(result.output.split())
        assert "same valuation date" in flat

    def test_missing_config_file_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(tmp_path / "nope.yaml"),
            ],
        )
        assert result.exit_code != 0

    def test_invalid_align_value_rejected(self, tmp_path: Path) -> None:
        """An unrecognised ``--align`` value exits cleanly."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--align",
                "bogus",
            ],
        )
        assert result.exit_code != 0

    def test_empty_scenarios_value_rejected(self, tmp_path: Path) -> None:
        """An empty ``--scenarios`` value exits cleanly with a helpful error."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "",
            ],
        )
        assert result.exit_code != 0

    def test_duplicate_scenario_names_deduplicated(self, tmp_path: Path) -> None:
        """``BASE,BASE`` is rejected — a scenario set should be a unique list."""
        config_path = _write_yaml(tmp_path, _two_deal_config())
        result = runner.invoke(
            app,
            [
                "portfolio",
                "scenarios",
                "--config",
                str(config_path),
                "--scenarios",
                "BASE,BASE",
            ],
        )
        assert result.exit_code != 0
        flat = " ".join(result.output.split())
        assert "duplicate" in flat.lower() or "unique" in flat.lower()

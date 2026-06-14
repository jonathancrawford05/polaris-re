"""Config-driven tabular YRT rate table (``deal.yrt_rate_table_path``) — ADR-075.

Companion to ``test_cli_yrt_rate_table.py`` (which covers the
``--yrt-rate-table`` CLI flag). These tests verify the YAML/JSON config
equivalent: a ``deal.yrt_rate_table_path`` entry must load the same
``YRTRateTable`` and produce byte-identical pricing to the CLI flag, with
the flag taking precedence when both are supplied.

Synthetic CSVs are generated in ``tmp_path`` so we exercise the full
loader without committing fixture tables to the repository.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from polaris_re.cli import _parse_config_to_pipeline_inputs, app

runner = CliRunner()


def _write_synthetic_yrt_csv(path: Path, base_rate: float, age_slope: float) -> None:
    """Write a synthetic age x duration YRT rate CSV (ages 18..85)."""
    lines = ["age,dur_1,dur_2,dur_3,ultimate"]
    for age in range(18, 86):
        d1 = base_rate + age_slope * (age - 18)
        d2 = d1 + 0.02
        d3 = d2 + 0.02
        ult = d3 + 0.50
        lines.append(f"{age},{d1:.4f},{d2:.4f},{d3:.4f},{ult:.4f}")
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def yrt_rate_table_dir(tmp_path: Path) -> Path:
    """Generate four (sex x smoker) synthetic YRT rate CSVs."""
    d = tmp_path / "yrt"
    d.mkdir()
    _write_synthetic_yrt_csv(d / "yrt_male_ns.csv", base_rate=0.30, age_slope=0.06)
    _write_synthetic_yrt_csv(d / "yrt_male_smoker.csv", base_rate=0.55, age_slope=0.10)
    _write_synthetic_yrt_csv(d / "yrt_female_ns.csv", base_rate=0.25, age_slope=0.05)
    _write_synthetic_yrt_csv(d / "yrt_female_smoker.csv", base_rate=0.45, age_slope=0.08)
    return d


def _write_inforce_csv(path: Path) -> None:
    """Two ceded TERM policies so the tabular path emits real ceded premium."""
    path.write_text(
        "policy_id,issue_age,attained_age,sex,smoker_status,"
        "underwriting_class,face_amount,annual_premium,product_type,"
        "policy_term,duration_inforce,reinsurance_cession_pct,"
        "issue_date,valuation_date\n"
        "P001,40,40,M,NS,STANDARD,500000.00,1200.00,TERM,20,0,0.90,"
        "2026-01-01,2026-01-01\n"
        "P002,45,45,F,NS,STANDARD,750000.00,1800.00,TERM,20,0,0.90,"
        "2026-01-01,2026-01-01\n"
    )


def _base_deal() -> dict[str, object]:
    return {
        "product_type": "TERM",
        "treaty_type": "YRT",
        "cession_pct": 0.90,
        "yrt_loading": 0.10,
        "discount_rate": 0.06,
        "hurdle_rate": 0.10,
        "projection_years": 20,
        "acquisition_cost": 500.0,
        "maintenance_cost": 75.0,
    }


def _write_config(path: Path, deal: dict[str, object]) -> None:
    path.write_text(
        json.dumps(
            {
                "mortality": {"source": "flat", "flat_qx": 0.001},
                "lapse": {"duration_table": {"1": 0.05, "2": 0.04, "3": 0.03, "ultimate": 0.02}},
                "deal": deal,
            }
        )
    )


class TestParseConfigYRTRateTablePath:
    """Fast unit tests for ``_parse_config_to_pipeline_inputs`` mapping."""

    def test_path_and_table_params_parsed(self) -> None:
        """The four table fields flow from the deal block onto DealConfig."""
        raw = {
            "mortality": {"source": "flat", "flat_qx": 0.001},
            "deal": {
                "product_type": "TERM",
                "yrt_rate_table_path": "/some/dir",
                "yrt_rate_table_select_period": 5,
                "yrt_rate_table_label": "deal2026",
                "yrt_rate_table_smoker_distinct": False,
            },
        }
        inputs, _ = _parse_config_to_pipeline_inputs(raw)
        assert inputs.deal.yrt_rate_table_path == Path("/some/dir")
        assert inputs.deal.yrt_rate_table_select_period == 5
        assert inputs.deal.yrt_rate_table_label == "deal2026"
        assert inputs.deal.yrt_rate_table_smoker_distinct is False

    def test_defaults_when_absent(self) -> None:
        """Omitting the table keys leaves the path None and defaults intact."""
        raw = {"mortality": {"source": "flat", "flat_qx": 0.001}, "deal": {"product_type": "TERM"}}
        inputs, _ = _parse_config_to_pipeline_inputs(raw)
        assert inputs.deal.yrt_rate_table_path is None
        assert inputs.deal.yrt_rate_table_select_period == 3
        assert inputs.deal.yrt_rate_table_label is None
        assert inputs.deal.yrt_rate_table_smoker_distinct is True


class TestPriceConfigYRTRateTablePath:
    """End-to-end: config-driven table load matches the CLI flag exactly."""

    def test_config_path_loads_table(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """`deal.yrt_rate_table_path` loads the table and bills ceded premium."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)})
        out_file = tmp_path / "out.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(config_path),
                "--inforce",
                str(inforce_csv),
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Loaded tabular YRT rate table" in result.output
        data = json.loads(out_file.read_text())
        assert data["reinsurer"]["pv_premiums"] > 0.0

    def test_config_path_matches_cli_flag(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """Closed-form: config path and --yrt-rate-table give identical pricing."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)

        # (a) table referenced from the config
        cfg_with_path = tmp_path / "with_path.json"
        _write_config(
            cfg_with_path, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)}
        )
        out_cfg = tmp_path / "cfg.json"
        r1 = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(cfg_with_path),
                "--inforce",
                str(inforce_csv),
                "--output",
                str(out_cfg),
            ],
        )
        assert r1.exit_code == 0, r1.output

        # (b) table referenced from the CLI flag, config without the path
        cfg_no_path = tmp_path / "no_path.json"
        _write_config(cfg_no_path, _base_deal())
        out_flag = tmp_path / "flag.json"
        r2 = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(cfg_no_path),
                "--inforce",
                str(inforce_csv),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
                "--output",
                str(out_flag),
            ],
        )
        assert r2.exit_code == 0, r2.output

        d_cfg = json.loads(out_cfg.read_text())
        d_flag = json.loads(out_flag.read_text())
        # Exact equality (not assert_allclose) by construction: both paths feed
        # the same directory through the same _load_yrt_rate_table_from_dir
        # helper into the same projection, so the floats are bit-identical. A
        # tolerance would weaken the "same code path" guarantee being asserted.
        assert d_cfg["reinsurer"]["pv_premiums"] == d_flag["reinsurer"]["pv_premiums"]
        assert d_cfg["reinsurer"]["pv_profits"] == d_flag["reinsurer"]["pv_profits"]
        assert d_cfg["cedant"]["pv_profits"] == d_flag["cedant"]["pv_profits"]

    def test_cli_flag_overrides_config_path(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """When both are given, the flag wins and a notice is printed.

        The config path points at a non-existent directory; if it were
        consulted the run would exit non-zero, so a clean exit proves the
        flag took precedence.
        """
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(
            config_path,
            {**_base_deal(), "yrt_rate_table_path": str(tmp_path / "does_not_exist")},
        )
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(config_path),
                "--inforce",
                str(inforce_csv),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "overrides" in result.output

    def test_config_path_missing_dir_exits_nonzero(self, tmp_path: Path) -> None:
        """A non-existent config-supplied directory fails fast."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, {**_base_deal(), "yrt_rate_table_path": str(tmp_path / "nope")})
        result = runner.invoke(
            app, ["price", "--config", str(config_path), "--inforce", str(inforce_csv)]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

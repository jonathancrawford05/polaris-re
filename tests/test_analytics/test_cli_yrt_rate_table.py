"""CLI integration tests for ``polaris price --yrt-rate-table`` (ADR-052).

The fixtures are generated in ``tmp_path`` so we exercise the full CLI
loader (`YRTRateTable.load` → `load_yrt_rate_csv`) without committing a
60-row CSV times four cohorts to the repository.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from polaris_re.cli import app

runner = CliRunner()


def _write_synthetic_yrt_csv(path: Path, base_rate: float, age_slope: float) -> None:
    """Write a synthetic age x duration YRT rate CSV.

    Rates rise linearly with age and gently with duration so the table
    has a non-degenerate (age, dur) signature. Ultimate rates are set
    above all select-period rates at the same age, reproducing the
    industry pattern. Ages 18..85 ensure the demo (age 40, 20-year
    projection) lands well inside the table.
    """
    lines = ["age,dur_1,dur_2,dur_3,ultimate"]
    for age in range(18, 86):
        d1 = base_rate + age_slope * (age - 18)
        d2 = d1 + 0.02
        d3 = d2 + 0.02
        ult = d3 + 0.50  # ultimate strictly higher than every select cell
        lines.append(f"{age},{d1:.4f},{d2:.4f},{d3:.4f},{ult:.4f}")
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def yrt_rate_table_dir(tmp_path: Path) -> Path:
    """Generate four (sex x smoker) synthetic YRT rate CSVs."""
    d = tmp_path / "yrt"
    d.mkdir()
    # Smokers always cost more than non-smokers; males more than females.
    _write_synthetic_yrt_csv(d / "yrt_male_ns.csv", base_rate=0.30, age_slope=0.06)
    _write_synthetic_yrt_csv(d / "yrt_male_smoker.csv", base_rate=0.55, age_slope=0.10)
    _write_synthetic_yrt_csv(d / "yrt_female_ns.csv", base_rate=0.25, age_slope=0.05)
    _write_synthetic_yrt_csv(d / "yrt_female_smoker.csv", base_rate=0.45, age_slope=0.08)
    return d


@pytest.mark.slow
class TestPriceCommandYRTRateTable:
    """Tests for ``polaris price --yrt-rate-table`` end-to-end behaviour."""

    def test_yrt_rate_table_runs_demo(self, yrt_rate_table_dir: Path) -> None:
        """`polaris price --yrt-rate-table DIR` exits 0 in demo mode."""
        result = runner.invoke(app, ["price", "--yrt-rate-table", str(yrt_rate_table_dir)])
        assert result.exit_code == 0, result.output
        assert "Loaded tabular YRT rate table" in result.output

    def test_yrt_rate_table_emits_nonzero_ceded_premium(
        self, yrt_rate_table_dir: Path, tmp_path: Path
    ) -> None:
        """Tabular YRT path produces a non-zero reinsurer PV premium.

        The shipped demo inforce sets ``reinsurance_cession_pct=0.00`` on
        every policy to exercise the ADR-036 override path. Tabular YRT
        consumption (ADR-051) always honours per-policy cession (the
        seriatim path multiplies by ``effective_cession_vec``), so the
        demo would produce zero ceded premiums. This test therefore
        writes a custom config + inforce pair where each policy carries
        ``reinsurance_cession_pct=0.90`` so the tabular path emits real
        ceded premium.
        """
        inforce_csv = tmp_path / "inforce.csv"
        inforce_csv.write_text(
            "policy_id,issue_age,attained_age,sex,smoker_status,"
            "underwriting_class,face_amount,annual_premium,product_type,"
            "policy_term,duration_inforce,reinsurance_cession_pct,"
            "issue_date,valuation_date\n"
            "P001,40,40,M,NS,STANDARD,500000.00,1200.00,TERM,20,0,0.90,"
            "2026-01-01,2026-01-01\n"
            "P002,45,45,F,NS,STANDARD,750000.00,1800.00,TERM,20,0,0.90,"
            "2026-01-01,2026-01-01\n"
        )
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "mortality": {"source": "flat", "flat_qx": 0.001},
                    "lapse": {
                        "duration_table": {
                            "1": 0.05,
                            "2": 0.04,
                            "3": 0.03,
                            "ultimate": 0.02,
                        }
                    },
                    "deal": {
                        "product_type": "TERM",
                        "treaty_type": "YRT",
                        "cession_pct": 0.90,
                        "yrt_loading": 0.10,
                        "discount_rate": 0.06,
                        "hurdle_rate": 0.10,
                        "projection_years": 20,
                        "acquisition_cost": 500.0,
                        "maintenance_cost": 75.0,
                    },
                }
            )
        )
        out_file = tmp_path / "tabular.json"
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
                "--output",
                str(out_file),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out_file.read_text())
        # Reinsurer PV premiums should be strictly positive — confirms the
        # rate table actually drove ceded premiums.
        assert data["reinsurer"]["pv_premiums"] > 0.0

    def test_yrt_rate_table_missing_dir_exits_nonzero(self, tmp_path: Path) -> None:
        """A non-existent directory fails fast with a clear error."""
        result = runner.invoke(app, ["price", "--yrt-rate-table", str(tmp_path / "does_not_exist")])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_yrt_rate_table_label_override(self, tmp_path: Path) -> None:
        """Custom --yrt-rate-table-label resolves to the named files."""
        d = tmp_path / "custom"
        d.mkdir()
        for sex_label in ("male", "female"):
            for smoker_label in ("ns", "smoker"):
                _write_synthetic_yrt_csv(
                    d / f"deal2026_{sex_label}_{smoker_label}.csv",
                    base_rate=0.30 + (0.10 if smoker_label == "smoker" else 0.0),
                    age_slope=0.06,
                )
        result = runner.invoke(
            app,
            [
                "price",
                "--yrt-rate-table",
                str(d),
                "--yrt-rate-table-label",
                "deal2026",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_yrt_rate_table_aggregate_mode(self, tmp_path: Path) -> None:
        """`--yrt-rate-table-aggregate` expects ``_unknown`` files only."""
        d = tmp_path / "agg"
        d.mkdir()
        for sex_label in ("male", "female"):
            _write_synthetic_yrt_csv(
                d / f"yrt_{sex_label}_unknown.csv",
                base_rate=0.40,
                age_slope=0.06,
            )
        result = runner.invoke(
            app,
            [
                "price",
                "--yrt-rate-table",
                str(d),
                "--yrt-rate-table-aggregate",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_yrt_rate_table_implies_seriatim(self, yrt_rate_table_dir: Path) -> None:
        """When the rate table is set, the projection runs in seriatim mode.

        Verified indirectly by checking that the run completes without
        raising the ``inforce=None`` PolarisComputationError that the
        tabular path would emit if the seriatim arrays were absent and
        the inforce argument was withheld.
        """
        result = runner.invoke(app, ["price", "--yrt-rate-table", str(yrt_rate_table_dir)])
        assert result.exit_code == 0, result.output
        assert "InforceBlock" not in result.output  # error message marker

    def test_no_yrt_rate_table_flag_unchanged_behaviour(self) -> None:
        """Without --yrt-rate-table, the CLI runs the legacy flat-rate path.

        Sanity guard against regressions in the default path: the demo
        mode call must still produce the cedant/reinsurer JSON.
        """
        result = runner.invoke(app, ["price"])
        assert result.exit_code == 0, result.output
        assert "Loaded tabular YRT rate table" not in result.output

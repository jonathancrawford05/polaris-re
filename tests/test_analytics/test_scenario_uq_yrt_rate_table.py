"""Tabular YRT rate table support in ``ScenarioRunner`` and ``MonteCarloUQ``.

Closes ADR-075 Out-of-scope follow-up #1: ``polaris scenario`` and
``polaris uq`` parse the ``deal.yrt_rate_table_path`` config block (PR #67)
but, before this change, silently dropped it — both analytics runners
projected at the aggregate level and applied the treaty without the
``InforceBlock`` the tabular path requires, so a config that referenced a
table priced on the flat derived YRT rate instead.

The closed-form anchor is the BASE / base-case identity: with unit (1.0)
stress multipliers the runner's first scenario must reproduce a direct
seriatim projection + tabular ``YRTTreaty.apply`` + profit test. The CLI
tests mirror the PR #67 ``price`` config tests: synthetic CSVs are written
to ``tmp_path`` so the full loader is exercised without committing fixture
tables.
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.analytics.scenario import ScenarioAdjustment, ScenarioRunner
from polaris_re.analytics.uq import MonteCarloUQ, UQParameters
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.cli import app
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.reinsurance.yrt_rate_table import YRTRateTable
from polaris_re.utils.table_io import load_mortality_csv

runner = CliRunner()
FIXTURES = Path(__file__).parent.parent / "fixtures"


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


@pytest.fixture
def analytics_setup(yrt_rate_table_dir: Path):
    """Block + assumptions + config + tabular YRTTreaty for unit-level tests."""
    policy = Policy(
        policy_id="SCEN_TAB_001",
        issue_age=40,
        attained_age=40,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=1_000_000.0,
        annual_premium=12_000.0,
        product_type=ProductType.TERM,
        policy_term=20,
        duration_inforce=0,
        reinsurance_cession_pct=0.9,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )
    block = InforceBlock(policies=[policy])
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    mortality = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.08, 2: 0.06, 3: 0.04, "ultimate": 0.03})
    assumptions = AssumptionSet(mortality=mortality, lapse=lapse, version="test-v1")
    config = ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=5,
        discount_rate=0.05,
    )
    table = YRTRateTable.load(
        directory=yrt_rate_table_dir,
        select_period=3,
        table_name="yrt",
        smoker_distinct=True,
    )
    treaty = YRTTreaty(
        cession_pct=0.9,
        total_face_amount=block.total_face_amount(),
        yrt_rate_table=table,
    )
    return block, assumptions, config, treaty


def _direct_unstressed_pv_profits(block, assumptions, config, treaty) -> float:
    """PV profits of one unstressed seriatim projection + tabular apply."""
    gross = TermLife(inforce=block, assumptions=assumptions, config=config).project(seriatim=True)
    net, _ceded = treaty.apply(gross, inforce=block)
    return ProfitTester(net, hurdle_rate=0.10).run().pv_profits


class TestScenarioRunnerTabularYRT:
    """ScenarioRunner honours a tabular YRTTreaty (closed-form BASE identity)."""

    def test_base_matches_direct_seriatim_apply(self, analytics_setup) -> None:
        """BASE (unit multipliers) == a direct seriatim projection + apply."""
        block, assumptions, config, treaty = analytics_setup
        expected = _direct_unstressed_pv_profits(block, assumptions, config, treaty)

        runner_obj = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        result = runner_obj.run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])
        _name, base = result.scenarios[0]

        np.testing.assert_allclose(base.pv_profits, expected, rtol=1e-12)

    def test_tabular_differs_from_flat(self, analytics_setup) -> None:
        """The tabular table changes the BASE result vs a flat YRT rate.

        Guards against a silent regression to the pre-fix behaviour where the
        table was dropped and the flat derived rate was used instead.
        """
        block, assumptions, config, treaty = analytics_setup
        flat_treaty = YRTTreaty(
            cession_pct=0.9,
            total_face_amount=block.total_face_amount(),
            flat_yrt_rate_per_1000=2.0,
        )
        tab = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10).run(
            scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)]
        )
        flat = ScenarioRunner(block, assumptions, config, flat_treaty, hurdle_rate=0.10).run(
            scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)]
        )
        assert tab.scenarios[0][1].pv_profits != flat.scenarios[0][1].pv_profits

    def test_stress_scenarios_run(self, analytics_setup) -> None:
        """A full standard-stress run completes with the tabular treaty."""
        block, assumptions, config, treaty = analytics_setup
        result = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10).run()
        assert len(result.scenarios) == 6


class TestMonteCarloUQTabularYRT:
    """MonteCarloUQ honours a tabular YRTTreaty (base-case identity)."""

    def test_base_case_matches_direct_seriatim_apply(self, analytics_setup) -> None:
        """The base case (no perturbation) == a direct seriatim apply."""
        block, assumptions, config, treaty = analytics_setup
        expected = _direct_unstressed_pv_profits(block, assumptions, config, treaty)

        uq = MonteCarloUQ(
            inforce=block,
            base_assumptions=assumptions,
            base_config=config,
            treaty=treaty,
            hurdle_rate=0.10,
            n_scenarios=8,
            seed=7,
        )
        result = uq.run()
        np.testing.assert_allclose(result.base_pv_profit, expected, rtol=1e-12)

    def test_tabular_differs_from_flat(self, analytics_setup) -> None:
        """The tabular table changes the base case vs a flat YRT rate."""
        block, assumptions, config, treaty = analytics_setup
        flat_treaty = YRTTreaty(
            cession_pct=0.9,
            total_face_amount=block.total_face_amount(),
            flat_yrt_rate_per_1000=2.0,
        )
        params = UQParameters()
        tab = MonteCarloUQ(
            inforce=block,
            base_assumptions=assumptions,
            base_config=config,
            treaty=treaty,
            hurdle_rate=0.10,
            n_scenarios=8,
            seed=7,
            params=params,
        ).run()
        flat = MonteCarloUQ(
            inforce=block,
            base_assumptions=assumptions,
            base_config=config,
            treaty=flat_treaty,
            hurdle_rate=0.10,
            n_scenarios=8,
            seed=7,
            params=params,
        ).run()
        assert tab.base_pv_profit != flat.base_pv_profit


# ---------------------------------------------------------------------------
# CLI integration — config-driven ``deal.yrt_rate_table_path``
# ---------------------------------------------------------------------------


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


class TestScenarioCommandTabularYRT:
    """`polaris scenario --config` honours ``deal.yrt_rate_table_path``."""

    def test_config_path_loads_table(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """The table is loaded (console notice) and the run exits 0."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)})
        result = runner.invoke(
            app,
            ["scenario", "--config", str(config_path), "--inforce", str(inforce_csv)],
        )
        assert result.exit_code == 0, result.output
        assert "Loaded tabular YRT rate table" in result.output

    def test_table_changes_base_scenario(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """Closed-form: the tabular config moves the BASE scenario vs flat."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)

        cfg_tab = tmp_path / "tab.json"
        _write_config(cfg_tab, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)})
        out_tab = tmp_path / "tab_out.json"
        r1 = runner.invoke(
            app,
            ["scenario", "-c", str(cfg_tab), "-i", str(inforce_csv), "-o", str(out_tab)],
        )
        assert r1.exit_code == 0, r1.output

        cfg_flat = tmp_path / "flat.json"
        _write_config(cfg_flat, _base_deal())
        out_flat = tmp_path / "flat_out.json"
        r2 = runner.invoke(
            app,
            ["scenario", "-c", str(cfg_flat), "-i", str(inforce_csv), "-o", str(out_flat)],
        )
        assert r2.exit_code == 0, r2.output

        base_tab = next(
            s for s in json.loads(out_tab.read_text())["scenarios"] if s["scenario"] == "BASE"
        )
        base_flat = next(
            s for s in json.loads(out_flat.read_text())["scenarios"] if s["scenario"] == "BASE"
        )
        assert base_tab["pv_profits"] != base_flat["pv_profits"]

    def test_missing_dir_exits_nonzero(self, tmp_path: Path) -> None:
        """A bad ``yrt_rate_table_path`` fails fast rather than silently."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(
            config_path, {**_base_deal(), "yrt_rate_table_path": str(tmp_path / "missing")}
        )
        result = runner.invoke(
            app,
            ["scenario", "--config", str(config_path), "--inforce", str(inforce_csv)],
        )
        assert result.exit_code == 1


class TestUQCommandTabularYRT:
    """`polaris uq --config` honours ``deal.yrt_rate_table_path``."""

    def test_config_path_loads_table(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """The table is loaded (console notice) and the run exits 0."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)})
        result = runner.invoke(
            app,
            [
                "uq",
                "--config",
                str(config_path),
                "--inforce",
                str(inforce_csv),
                "--scenarios",
                "16",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Loaded tabular YRT rate table" in result.output

    def test_table_changes_base_case(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """The tabular config moves the base-case PV profit vs flat."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)

        cfg_tab = tmp_path / "tab.json"
        _write_config(cfg_tab, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)})
        out_tab = tmp_path / "tab_out.json"
        r1 = runner.invoke(
            app,
            ["uq", "-c", str(cfg_tab), "-i", str(inforce_csv), "-n", "16", "-o", str(out_tab)],
        )
        assert r1.exit_code == 0, r1.output

        cfg_flat = tmp_path / "flat.json"
        _write_config(cfg_flat, _base_deal())
        out_flat = tmp_path / "flat_out.json"
        r2 = runner.invoke(
            app,
            ["uq", "-c", str(cfg_flat), "-i", str(inforce_csv), "-n", "16", "-o", str(out_flat)],
        )
        assert r2.exit_code == 0, r2.output

        d_tab = json.loads(out_tab.read_text())
        d_flat = json.loads(out_flat.read_text())
        assert d_tab["base_pv_profit"] != d_flat["base_pv_profit"]


# ---------------------------------------------------------------------------
# CLI integration — ad-hoc ``--yrt-rate-table`` flag (ADR-079)
# ---------------------------------------------------------------------------


@pytest.fixture
def yrt_rate_table_dir_alt(tmp_path: Path) -> Path:
    """A second four-cohort table with distinctly higher rates than the
    primary fixture, so a flag-vs-config precedence test can tell which
    table actually drove the result."""
    d = tmp_path / "yrt_alt"
    d.mkdir()
    _write_synthetic_yrt_csv(d / "yrt_male_ns.csv", base_rate=1.20, age_slope=0.12)
    _write_synthetic_yrt_csv(d / "yrt_male_smoker.csv", base_rate=1.80, age_slope=0.20)
    _write_synthetic_yrt_csv(d / "yrt_female_ns.csv", base_rate=1.10, age_slope=0.10)
    _write_synthetic_yrt_csv(d / "yrt_female_smoker.csv", base_rate=1.60, age_slope=0.16)
    return d


class TestScenarioCommandTabularYRTFlag:
    """`polaris scenario --yrt-rate-table DIR` is the ad-hoc equivalent of the
    config field, with flag-over-config precedence (ADR-079)."""

    def test_flag_loads_table(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """The flag loads the table (console notice) and the run exits 0."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, _base_deal())
        result = runner.invoke(
            app,
            [
                "scenario",
                "-c",
                str(config_path),
                "-i",
                str(inforce_csv),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Loaded tabular YRT rate table" in result.output

    def test_flag_matches_config_field(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """Closed-form: the flag and the config field produce byte-identical
        scenario PV profits for the same table directory."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)

        cfg_flag = tmp_path / "flag.json"
        _write_config(cfg_flag, _base_deal())
        out_flag = tmp_path / "flag_out.json"
        r1 = runner.invoke(
            app,
            [
                "scenario",
                "-c",
                str(cfg_flag),
                "-i",
                str(inforce_csv),
                "-o",
                str(out_flag),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert r1.exit_code == 0, r1.output

        cfg_field = tmp_path / "field.json"
        _write_config(cfg_field, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)})
        out_field = tmp_path / "field_out.json"
        r2 = runner.invoke(
            app,
            ["scenario", "-c", str(cfg_field), "-i", str(inforce_csv), "-o", str(out_field)],
        )
        assert r2.exit_code == 0, r2.output

        flag_rows = {
            s["scenario"]: s["pv_profits"] for s in json.loads(out_flag.read_text())["scenarios"]
        }
        field_rows = {
            s["scenario"]: s["pv_profits"] for s in json.loads(out_field.read_text())["scenarios"]
        }
        assert flag_rows.keys() == field_rows.keys()
        for name, pv in flag_rows.items():
            np.testing.assert_allclose(pv, field_rows[name], rtol=1e-12)

    def test_flag_overrides_config(
        self, yrt_rate_table_dir: Path, yrt_rate_table_dir_alt: Path, tmp_path: Path
    ) -> None:
        """When both the flag and deal.yrt_rate_table_path are present, the flag
        wins (console notice) and the result equals a flag-only run."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)

        # Config points at the alt (high-rate) table; flag points at the primary.
        cfg_both = tmp_path / "both.json"
        _write_config(
            cfg_both, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir_alt)}
        )
        out_both = tmp_path / "both_out.json"
        r1 = runner.invoke(
            app,
            [
                "scenario",
                "-c",
                str(cfg_both),
                "-i",
                str(inforce_csv),
                "-o",
                str(out_both),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert r1.exit_code == 0, r1.output
        assert "overrides deal.yrt_rate_table_path" in r1.output

        # Flag-only baseline (config carries no table path).
        cfg_flag = tmp_path / "flag.json"
        _write_config(cfg_flag, _base_deal())
        out_flag = tmp_path / "flag_out.json"
        r2 = runner.invoke(
            app,
            [
                "scenario",
                "-c",
                str(cfg_flag),
                "-i",
                str(inforce_csv),
                "-o",
                str(out_flag),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert r2.exit_code == 0, r2.output

        both_rows = {
            s["scenario"]: s["pv_profits"] for s in json.loads(out_both.read_text())["scenarios"]
        }
        flag_rows = {
            s["scenario"]: s["pv_profits"] for s in json.loads(out_flag.read_text())["scenarios"]
        }
        for name, pv in both_rows.items():
            np.testing.assert_allclose(pv, flag_rows[name], rtol=1e-12)

    def test_flag_missing_dir_exits_nonzero(self, tmp_path: Path) -> None:
        """A bad --yrt-rate-table path fails fast rather than silently."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, _base_deal())
        result = runner.invoke(
            app,
            [
                "scenario",
                "-c",
                str(config_path),
                "-i",
                str(inforce_csv),
                "--yrt-rate-table",
                str(tmp_path / "missing"),
            ],
        )
        assert result.exit_code == 1


class TestUQCommandTabularYRTFlag:
    """`polaris uq --yrt-rate-table DIR` is the ad-hoc equivalent of the config
    field, with flag-over-config precedence (ADR-079)."""

    def test_flag_loads_table(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """The flag loads the table (console notice) and the run exits 0."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, _base_deal())
        result = runner.invoke(
            app,
            [
                "uq",
                "-c",
                str(config_path),
                "-i",
                str(inforce_csv),
                "-n",
                "16",
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Loaded tabular YRT rate table" in result.output

    def test_flag_matches_config_field(self, yrt_rate_table_dir: Path, tmp_path: Path) -> None:
        """Closed-form: the flag and the config field produce byte-identical
        base-case PV profit for the same table directory and seed."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)

        cfg_flag = tmp_path / "flag.json"
        _write_config(cfg_flag, _base_deal())
        out_flag = tmp_path / "flag_out.json"
        r1 = runner.invoke(
            app,
            [
                "uq",
                "-c",
                str(cfg_flag),
                "-i",
                str(inforce_csv),
                "-n",
                "16",
                "-o",
                str(out_flag),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert r1.exit_code == 0, r1.output

        cfg_field = tmp_path / "field.json"
        _write_config(cfg_field, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir)})
        out_field = tmp_path / "field_out.json"
        r2 = runner.invoke(
            app,
            ["uq", "-c", str(cfg_field), "-i", str(inforce_csv), "-n", "16", "-o", str(out_field)],
        )
        assert r2.exit_code == 0, r2.output

        np.testing.assert_allclose(
            json.loads(out_flag.read_text())["base_pv_profit"],
            json.loads(out_field.read_text())["base_pv_profit"],
            rtol=1e-12,
        )

    def test_flag_overrides_config(
        self, yrt_rate_table_dir: Path, yrt_rate_table_dir_alt: Path, tmp_path: Path
    ) -> None:
        """The flag wins over deal.yrt_rate_table_path (console notice + result
        equals a flag-only run)."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)

        cfg_both = tmp_path / "both.json"
        _write_config(
            cfg_both, {**_base_deal(), "yrt_rate_table_path": str(yrt_rate_table_dir_alt)}
        )
        out_both = tmp_path / "both_out.json"
        r1 = runner.invoke(
            app,
            [
                "uq",
                "-c",
                str(cfg_both),
                "-i",
                str(inforce_csv),
                "-n",
                "16",
                "-o",
                str(out_both),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert r1.exit_code == 0, r1.output
        assert "overrides deal.yrt_rate_table_path" in r1.output

        cfg_flag = tmp_path / "flag.json"
        _write_config(cfg_flag, _base_deal())
        out_flag = tmp_path / "flag_out.json"
        r2 = runner.invoke(
            app,
            [
                "uq",
                "-c",
                str(cfg_flag),
                "-i",
                str(inforce_csv),
                "-n",
                "16",
                "-o",
                str(out_flag),
                "--yrt-rate-table",
                str(yrt_rate_table_dir),
            ],
        )
        assert r2.exit_code == 0, r2.output

        np.testing.assert_allclose(
            json.loads(out_both.read_text())["base_pv_profit"],
            json.loads(out_flag.read_text())["base_pv_profit"],
            rtol=1e-12,
        )

    def test_flag_missing_dir_exits_nonzero(self, tmp_path: Path) -> None:
        """A bad --yrt-rate-table path fails fast rather than silently."""
        inforce_csv = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce_csv)
        config_path = tmp_path / "config.json"
        _write_config(config_path, _base_deal())
        result = runner.invoke(
            app,
            [
                "uq",
                "-c",
                str(config_path),
                "-i",
                str(inforce_csv),
                "-n",
                "16",
                "--yrt-rate-table",
                str(tmp_path / "missing"),
            ],
        )
        assert result.exit_code == 1

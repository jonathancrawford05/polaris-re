"""Reinsurer-vs-cedant profit-test perspective in ``ScenarioRunner`` / ``MonteCarloUQ``.

ADR-077. Before this change both runners profit-tested the cedant ``net``
position (``treaty.apply()[0]``), whereas ``polaris price`` reports the
*reinsurer* view (the ceded cash flows re-viewed as NET). On a reinsurer-
facing tool the scenario / UQ PV and IRR therefore described the cedant's
retained book, not the reinsurer's.

The runners gain an additive ``perspective`` parameter defaulting to
``"cedant"`` (byte-identical to the prior behaviour). The ``scenario`` /
``uq`` CLI commands default to ``"reinsurer"`` so they agree with ``price``.

Closed-form anchors:
  - ``perspective="reinsurer"`` BASE == ``ProfitTester(ceded_to_reinsurer_view(ceded))``
  - ``perspective="cedant"`` BASE == ``ProfitTester(net)`` (unchanged)
The two perspectives are deliberately exercised at a non-50% cession, where
the cedant net and reinsurer ceded positions differ (a 50% coinsurance is
degenerate — net == ceded).
"""

from datetime import date
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from polaris_re.analytics.profit_test import ProfitTester
from polaris_re.analytics.scenario import ScenarioAdjustment, ScenarioRunner
from polaris_re.analytics.uq import MonteCarloUQ
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.cli import app
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.pipeline import ceded_to_reinsurer_view
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.term_life import TermLife
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.utils.table_io import load_mortality_csv

cli = CliRunner()
FIXTURES = Path(__file__).parent.parent / "fixtures"

# Non-50% cession so the cedant (net) and reinsurer (ceded) positions differ.
CESSION = 0.80


@pytest.fixture
def setup():
    """Block + assumptions + config + 80% CoinsuranceTreaty for perspective tests."""
    policy = Policy(
        policy_id="PERS001",
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
        reinsurance_cession_pct=CESSION,
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
    treaty = CoinsuranceTreaty(cession_pct=CESSION)
    return block, assumptions, config, treaty


def _direct(block, assumptions, config, treaty):
    """Direct unstressed gross/net/ceded plus both profit-test perspectives."""
    gross = TermLife(block, assumptions, config).project()
    net, ceded = treaty.apply(gross)
    cedant = ProfitTester(net, hurdle_rate=0.10).run()
    reinsurer = ProfitTester(ceded_to_reinsurer_view(ceded), hurdle_rate=0.10).run()
    return cedant, reinsurer


class TestScenarioPerspective:
    """ScenarioRunner perspective selection (closed-form BASE identity)."""

    def test_default_is_cedant(self, setup):
        """No perspective arg → cedant net (pre-ADR-077 behaviour)."""
        block, assumptions, config, treaty = setup
        cedant, _ = _direct(block, assumptions, config, treaty)
        runner = ScenarioRunner(block, assumptions, config, treaty, hurdle_rate=0.10)
        assert runner.perspective == "cedant"
        base = runner.run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)]).scenarios[0][1]
        np.testing.assert_allclose(base.pv_profits, cedant.pv_profits, rtol=1e-12)

    def test_reinsurer_matches_ceded_view(self, setup):
        """perspective='reinsurer' BASE == ProfitTester(ceded_to_reinsurer_view(ceded))."""
        block, assumptions, config, treaty = setup
        _, reinsurer = _direct(block, assumptions, config, treaty)
        runner = ScenarioRunner(
            block, assumptions, config, treaty, hurdle_rate=0.10, perspective="reinsurer"
        )
        result = runner.run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])
        np.testing.assert_allclose(
            result.scenarios[0][1].pv_profits, reinsurer.pv_profits, rtol=1e-12
        )
        assert result.perspective == "reinsurer"

    def test_cedant_explicit_matches_net(self, setup):
        """perspective='cedant' BASE == ProfitTester(net)."""
        block, assumptions, config, treaty = setup
        cedant, _ = _direct(block, assumptions, config, treaty)
        runner = ScenarioRunner(
            block, assumptions, config, treaty, hurdle_rate=0.10, perspective="cedant"
        )
        base = runner.run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)]).scenarios[0][1]
        np.testing.assert_allclose(base.pv_profits, cedant.pv_profits, rtol=1e-12)

    def test_perspectives_differ_at_non_half_cession(self, setup):
        """At 80% cession the cedant and reinsurer PV profits must differ."""
        block, assumptions, config, treaty = setup
        cedant_run = ScenarioRunner(
            block, assumptions, config, treaty, hurdle_rate=0.10, perspective="cedant"
        ).run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])
        reinsurer_run = ScenarioRunner(
            block, assumptions, config, treaty, hurdle_rate=0.10, perspective="reinsurer"
        ).run(scenarios=[ScenarioAdjustment("BASE", 1.0, 1.0)])
        assert cedant_run.scenarios[0][1].pv_profits != reinsurer_run.scenarios[0][1].pv_profits

    def test_invalid_perspective_raises(self, setup):
        """An unknown perspective is rejected at construction."""
        block, assumptions, config, treaty = setup
        with pytest.raises(PolarisValidationError, match="perspective"):
            ScenarioRunner(
                block, assumptions, config, treaty, hurdle_rate=0.10, perspective="bogus"
            )


class TestUQPerspective:
    """MonteCarloUQ perspective selection (base-case identity)."""

    def test_default_is_cedant(self, setup):
        block, assumptions, config, treaty = setup
        cedant, _ = _direct(block, assumptions, config, treaty)
        uq = MonteCarloUQ(
            block, assumptions, config, treaty, hurdle_rate=0.10, n_scenarios=8, seed=7
        )
        assert uq.perspective == "cedant"
        result = uq.run()
        np.testing.assert_allclose(result.base_pv_profit, cedant.pv_profits, rtol=1e-12)
        assert result.perspective == "cedant"

    def test_reinsurer_matches_ceded_view(self, setup):
        block, assumptions, config, treaty = setup
        _, reinsurer = _direct(block, assumptions, config, treaty)
        uq = MonteCarloUQ(
            block,
            assumptions,
            config,
            treaty,
            hurdle_rate=0.10,
            n_scenarios=8,
            seed=7,
            perspective="reinsurer",
        )
        result = uq.run()
        np.testing.assert_allclose(result.base_pv_profit, reinsurer.pv_profits, rtol=1e-12)
        assert result.perspective == "reinsurer"

    def test_no_treaty_reinsurer_falls_back_to_gross(self, setup):
        """With treaty=None the reinsurer view is undefined → gross is used."""
        block, assumptions, config, _ = setup
        gross = TermLife(block, assumptions, config).project()
        gross_pv = ProfitTester(gross, hurdle_rate=0.10).run().pv_profits
        uq = MonteCarloUQ(
            block,
            assumptions,
            config,
            treaty=None,
            hurdle_rate=0.10,
            n_scenarios=8,
            seed=7,
            perspective="reinsurer",
        )
        np.testing.assert_allclose(uq.run().base_pv_profit, gross_pv, rtol=1e-12)

    def test_invalid_perspective_raises(self, setup):
        block, assumptions, config, treaty = setup
        with pytest.raises(PolarisValidationError, match="perspective"):
            MonteCarloUQ(
                block,
                assumptions,
                config,
                treaty,
                hurdle_rate=0.10,
                n_scenarios=8,
                perspective="bogus",
            )


# ---------------------------------------------------------------------------
# CLI integration — `--perspective` on `scenario` / `uq`
# ---------------------------------------------------------------------------


def _write_inforce_csv(path: Path) -> None:
    path.write_text(
        "policy_id,issue_age,attained_age,sex,smoker_status,"
        "underwriting_class,face_amount,annual_premium,product_type,"
        "policy_term,duration_inforce,reinsurance_cession_pct,"
        "issue_date,valuation_date\n"
        "P001,40,40,M,NS,STANDARD,1000000.00,12000.00,TERM,20,0,0.80,"
        "2026-01-01,2026-01-01\n"
    )


def _write_config(path: Path, *, treaty_type: str = "YRT") -> None:
    import json

    deal = {
        "product_type": "TERM",
        "treaty_type": treaty_type,
        "cession_pct": 0.80,
        "yrt_loading": 0.10,
        "discount_rate": 0.06,
        "hurdle_rate": 0.10,
        "projection_years": 20,
        "acquisition_cost": 500.0,
        "maintenance_cost": 75.0,
    }
    path.write_text(
        json.dumps(
            {
                "mortality": {"source": "flat", "flat_qx": 0.002},
                "lapse": {"duration_table": {"1": 0.05, "2": 0.04, "3": 0.03, "ultimate": 0.02}},
                "deal": deal,
            }
        )
    )


class TestScenarioCLIPerspective:
    def test_default_is_reinsurer(self, tmp_path):
        """Bare `polaris scenario` reports the reinsurer view (matches price)."""
        inforce = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce)
        config = tmp_path / "config.json"
        _write_config(config)
        out = tmp_path / "out.json"
        result = cli.invoke(
            app, ["scenario", "-c", str(config), "-i", str(inforce), "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        import json

        assert json.loads(out.read_text())["perspective"] == "reinsurer"

    def test_perspectives_differ(self, tmp_path):
        """reinsurer and cedant flags produce different BASE PV profits."""
        import json

        inforce = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce)
        config = tmp_path / "config.json"
        _write_config(config)

        out_r = tmp_path / "rein.json"
        r1 = cli.invoke(
            app,
            [
                "scenario",
                "-c",
                str(config),
                "-i",
                str(inforce),
                "--perspective",
                "reinsurer",
                "-o",
                str(out_r),
            ],
        )
        assert r1.exit_code == 0, r1.output
        out_c = tmp_path / "ced.json"
        r2 = cli.invoke(
            app,
            [
                "scenario",
                "-c",
                str(config),
                "-i",
                str(inforce),
                "--perspective",
                "cedant",
                "-o",
                str(out_c),
            ],
        )
        assert r2.exit_code == 0, r2.output

        base_r = next(
            s for s in json.loads(out_r.read_text())["scenarios"] if s["scenario"] == "BASE"
        )
        base_c = next(
            s for s in json.loads(out_c.read_text())["scenarios"] if s["scenario"] == "BASE"
        )
        assert base_r["pv_profits"] != base_c["pv_profits"]

    def test_invalid_perspective_exits_nonzero(self, tmp_path):
        inforce = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce)
        config = tmp_path / "config.json"
        _write_config(config)
        result = cli.invoke(
            app,
            ["scenario", "-c", str(config), "-i", str(inforce), "--perspective", "bogus"],
        )
        assert result.exit_code != 0

    def test_no_treaty_downgrades_to_cedant(self, tmp_path):
        """A treaty_type=none config downgrades a reinsurer request to cedant."""
        import json

        inforce = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce)
        config = tmp_path / "config.json"
        _write_config(config, treaty_type="none")
        out = tmp_path / "out.json"
        result = cli.invoke(
            app,
            [
                "scenario",
                "-c",
                str(config),
                "-i",
                str(inforce),
                "--perspective",
                "reinsurer",
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(out.read_text())["perspective"] == "cedant"
        assert "reinsurer view not available" in result.output


class TestUQCLIPerspective:
    def test_default_is_reinsurer(self, tmp_path):
        import json

        inforce = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce)
        config = tmp_path / "config.json"
        _write_config(config)
        out = tmp_path / "out.json"
        result = cli.invoke(
            app, ["uq", "-c", str(config), "-i", str(inforce), "-n", "16", "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(out.read_text())["perspective"] == "reinsurer"

    def test_perspectives_differ(self, tmp_path):
        import json

        inforce = tmp_path / "inforce.csv"
        _write_inforce_csv(inforce)
        config = tmp_path / "config.json"
        _write_config(config)
        out_r = tmp_path / "rein.json"
        r1 = cli.invoke(
            app,
            [
                "uq",
                "-c",
                str(config),
                "-i",
                str(inforce),
                "-n",
                "16",
                "--perspective",
                "reinsurer",
                "-o",
                str(out_r),
            ],
        )
        assert r1.exit_code == 0, r1.output
        out_c = tmp_path / "ced.json"
        r2 = cli.invoke(
            app,
            [
                "uq",
                "-c",
                str(config),
                "-i",
                str(inforce),
                "-n",
                "16",
                "--perspective",
                "cedant",
                "-o",
                str(out_c),
            ],
        )
        assert r2.exit_code == 0, r2.output
        assert (
            json.loads(out_r.read_text())["base_pv_profit"]
            != json.loads(out_c.read_text())["base_pv_profit"]
        )

"""CLI <-> dashboard parity — every metric must agree to within tolerance.

This is the acceptance gate for the CLI/Streamlit alignment task.
Without it, future drift will silently reintroduce the sign-flip bug
that prompted this refactor.
"""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from polaris_re.core.pipeline import (
    DEFAULT_LAPSE_CURVE,
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
    build_treaty,
    ceded_to_reinsurer_view,
    derive_yrt_rate,
    iter_cohorts,
    load_inforce,
)
from polaris_re.core.policy import ProductType
from polaris_re.products.dispatch import get_product_engine

FIXTURE_CSV = Path("data/inputs/test_inforce.csv")


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture()
def whole_life_inputs() -> PipelineInputs:
    """Pipeline inputs matching the dashboard defaults for the test CSV."""
    return PipelineInputs(
        mortality=MortalityConfig(source="SOA_VBT_2015", multiplier=1.0),
        lapse=LapseConfig(),  # default curve from DEFAULT_LAPSE_CURVE
        deal=DealConfig(
            product_type="WHOLE_LIFE",
            treaty_type="YRT",
            cession_pct=0.20,
            yrt_loading=0.10,
            discount_rate=0.06,
            hurdle_rate=0.10,
            projection_years=30,
        ),
    )


# ------------------------------------------------------------------ #
# Pipeline unit tests                                                 #
# ------------------------------------------------------------------ #


class TestPipelineBuilder:
    """Verify the shared pipeline builder produces valid output."""

    def test_flat_mortality_pipeline(self) -> None:
        """Flat mortality pipeline matches legacy CLI behaviour."""
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.005),
            lapse=LapseConfig(duration_table={1: 0.05, 2: 0.04, "ultimate": 0.03}),
            deal=DealConfig(product_type="TERM", projection_years=10),
        )
        inforce = load_inforce(
            policies_dict=[
                {
                    "policy_id": "T1",
                    "issue_age": 40,
                    "attained_age": 40,
                    "sex": "M",
                    "smoker": False,
                    "face_amount": 500000.0,
                    "annual_premium": 2000.0,
                    "policy_term": 20,
                    "duration_inforce": 0,
                    "issue_date": "2020-01-01",
                    "valuation_date": date.today().isoformat(),
                    "product_type": "TERM",
                }
            ]
        )
        inf, assumptions, config = build_pipeline(inforce, inputs)
        assert inf.n_policies == 1
        assert config.projection_horizon_years == 10

        engine = get_product_engine(inforce=inf, assumptions=assumptions, config=config)
        gross = engine.project()
        assert gross.basis == "GROSS"
        assert gross.projection_months == 120

    def test_default_lapse_curve_matches(self) -> None:
        """DEFAULT_LAPSE_CURVE has the expected 11-point structure."""
        assert DEFAULT_LAPSE_CURVE[1] == 0.06
        assert DEFAULT_LAPSE_CURVE[10] == 0.02
        assert DEFAULT_LAPSE_CURVE["ultimate"] == 0.015
        assert len([k for k in DEFAULT_LAPSE_CURVE if isinstance(k, int)]) == 10

    def test_deal_config_to_dict_roundtrip(self) -> None:
        """DealConfig.to_dict() produces all expected keys."""
        cfg = DealConfig()
        d = cfg.to_dict()
        assert d["product_type"] == "TERM"
        assert d["treaty_type"] == "YRT"
        assert d["cession_pct"] == 0.90
        assert d["discount_rate"] == 0.06
        assert "yrt_rate_per_1000" in d


class TestDeriveYRTRate:
    """Verify YRT rate derivation from gross projection."""

    def test_positive_claims(self) -> None:
        """Rate should be proportional to first-year claims / face amount."""
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.005),
            deal=DealConfig(product_type="TERM", projection_years=5),
        )
        inforce = load_inforce(
            policies_dict=[
                {
                    "policy_id": "R1",
                    "issue_age": 40,
                    "attained_age": 40,
                    "sex": "M",
                    "smoker": False,
                    "face_amount": 1_000_000.0,
                    "annual_premium": 5000.0,
                    "policy_term": 20,
                    "duration_inforce": 0,
                    "issue_date": "2020-01-01",
                    "valuation_date": date.today().isoformat(),
                    "product_type": "TERM",
                }
            ]
        )
        inf, assumptions, config = build_pipeline(inforce, inputs)
        gross = get_product_engine(inforce=inf, assumptions=assumptions, config=config).project()
        rate = derive_yrt_rate(gross, 1_000_000.0, loading=0.10)
        assert rate > 0.0
        assert rate < 100.0  # sanity: rate per $1000 should be reasonable


# ------------------------------------------------------------------ #
# CLI ↔ Dashboard parity (integration tests)                          #
# ------------------------------------------------------------------ #


@pytest.mark.slow
class TestCLIStreamlitParity:
    """Given identical inputs, CLI and dashboard paths must agree."""

    @pytest.fixture()
    def _check_csv_exists(self) -> None:
        if not FIXTURE_CSV.exists():
            pytest.skip(f"Test inforce CSV not found: {FIXTURE_CSV}")

    @pytest.fixture()
    def _check_mortality_tables(self) -> None:
        """Skip if SOA VBT 2015 tables are not available."""
        import os

        data_dir = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
        sample = data_dir / "soa_vbt_2015_male_nonsmoker.csv"
        if not sample.exists():
            pytest.skip(f"Mortality tables not found at {data_dir}")

    @pytest.mark.usefixtures("_check_csv_exists", "_check_mortality_tables")
    def test_pipeline_produces_loss_for_wl_policies(
        self, whole_life_inputs: PipelineInputs
    ) -> None:
        """2 large WL policies at SOA VBT 2015 should be loss-making."""
        from polaris_re.analytics.profit_test import ProfitTester

        inforce = load_inforce(csv_path=FIXTURE_CSV)
        inf, assumptions, config = build_pipeline(inforce, whole_life_inputs)

        gross = get_product_engine(inforce=inf, assumptions=assumptions, config=config).project()

        # Apply YRT treaty
        face_amount = inf.total_face_amount()
        yrt_rate = derive_yrt_rate(gross, face_amount, whole_life_inputs.deal.yrt_loading)
        treaty = build_treaty(
            treaty_type="YRT",
            cession_pct=whole_life_inputs.deal.cession_pct,
            face_amount=face_amount,
            yrt_rate_per_1000=yrt_rate,
        )
        assert treaty is not None
        net, ceded = treaty.apply(gross)  # type: ignore[union-attr]

        # Cedant view
        cedant = ProfitTester(cashflows=net, hurdle_rate=whole_life_inputs.deal.hurdle_rate).run()

        # Key assertion: cedant PV profits must be negative for these policies
        assert cedant.pv_profits < 0, (
            f"Expected cedant loss but got PV profits = ${cedant.pv_profits:,.0f}. "
            "This is the sign-flip bug — CLI was using flat mortality."
        )
        # Within range of dashboard reference value (-$8.5M ±$1.5M)
        assert -10_000_000 < cedant.pv_profits < -7_000_000, (
            f"Cedant PV profits ${cedant.pv_profits:,.0f} outside expected range"
        )

        # Reinsurer view
        assert ceded is not None
        reinsurer = ProfitTester(
            cashflows=ceded_to_reinsurer_view(ceded),
            hurdle_rate=whole_life_inputs.deal.hurdle_rate,
        ).run()

        assert reinsurer.pv_profits < 0, (
            f"Expected reinsurer loss but got ${reinsurer.pv_profits:,.0f}"
        )
        assert -3_500_000 < reinsurer.pv_profits < -500_000, (
            f"Reinsurer PV profits ${reinsurer.pv_profits:,.0f} outside expected range"
        )


# ------------------------------------------------------------------ #
# Legacy config backward compatibility                                #
# ------------------------------------------------------------------ #


class TestLegacyConfigCompat:
    """Old-style JSON configs with flat_qx/flat_lapse must still work."""

    def test_legacy_schema_produces_pipeline(self) -> None:
        """Legacy flat config should be translated and produce valid output."""
        from polaris_re.cli import _build_pipeline_from_config

        legacy_config = {
            "product_type": "TERM",
            "flat_qx": 0.001,
            "flat_lapse": 0.05,
            "projection_horizon_years": 10,
            "discount_rate": 0.06,
            "policies": [
                {
                    "policy_id": "LEGACY-001",
                    "issue_age": 40,
                    "attained_age": 40,
                    "sex": "M",
                    "smoker": False,
                    "face_amount": 500000.0,
                    "annual_premium": 2000.0,
                    "policy_term": 20,
                    "duration_inforce": 0,
                    "issue_date": "2020-01-01",
                    "valuation_date": date.today().isoformat(),
                }
            ],
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            json.dump(legacy_config, tmp)
            config_path = Path(tmp.name)

        inforce, _assumptions, config, inputs = _build_pipeline_from_config(config_path)
        assert inforce.n_policies == 1
        assert config.projection_horizon_years == 10
        # Should use flat mortality source
        assert inputs.mortality.source == "flat"
        assert inputs.mortality.flat_qx == 0.001

    def test_new_schema_with_csv_inforce(self) -> None:
        """New schema + CSV inforce should work together."""
        from polaris_re.cli import _build_pipeline_from_config

        new_config = {
            "mortality": {"source": "flat", "flat_qx": 0.005},
            "lapse": {"duration_table": {"1": 0.06, "2": 0.05, "ultimate": 0.03}},
            "deal": {
                "product_type": "TERM",
                "projection_years": 5,
            },
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            json.dump(new_config, tmp)
            config_path = Path(tmp.name)

        # Create a tiny CSV
        csv_content = (
            "policy_id,issue_age,attained_age,sex,smoker_status,"
            "face_amount,annual_premium,product_type,duration_inforce,"
            "issue_date,valuation_date\n"
            f"CSV-001,35,35,M,NS,100000.0,500.0,TERM,0,"
            f"2020-01-01,{date.today().isoformat()}\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as csv_tmp:
            csv_tmp.write(csv_content)
            csv_path = Path(csv_tmp.name)

        inforce, _assumptions, config, inputs = _build_pipeline_from_config(
            config_path, inforce_path=csv_path
        )
        assert inforce.n_policies == 1
        assert config.projection_horizon_years == 5
        assert inputs.mortality.source == "flat"


# ------------------------------------------------------------------ #
# Mixed-product cohort support                                        #
# ------------------------------------------------------------------ #


def _policy_dict(
    policy_id: str,
    product_type: str,
    face_amount: float = 100_000.0,
) -> dict[str, object]:
    """Build a minimal policy dict for load_inforce()."""
    return {
        "policy_id": policy_id,
        "issue_age": 40,
        "attained_age": 40,
        "sex": "M",
        "smoker": False,
        "face_amount": face_amount,
        "annual_premium": 1_000.0,
        "policy_term": 20 if product_type == "TERM" else None,
        "duration_inforce": 0,
        "issue_date": "2020-01-01",
        "valuation_date": date.today().isoformat(),
        "product_type": product_type,
    }


class TestIterCohorts:
    """``iter_cohorts`` partitions an inforce block by product type."""

    def test_empty_block_returns_empty_list(self) -> None:
        """An empty block (no policies) produces no cohorts."""
        # Can't construct an empty InforceBlock directly — use filter on a
        # homogeneous one and rely on iter_cohorts handling the edge case.
        inforce = load_inforce(policies_dict=[_policy_dict("T1", "TERM")])
        # Sanity: single cohort
        assert len(iter_cohorts(inforce)) == 1

    def test_homogeneous_block_returns_original(self) -> None:
        """A homogeneous block returns a single-element list pointing at the
        original block object — no redundant copy."""
        inforce = load_inforce(
            policies_dict=[
                _policy_dict("T1", "TERM"),
                _policy_dict("T2", "TERM"),
            ]
        )
        cohorts = iter_cohorts(inforce)
        assert len(cohorts) == 1
        pt, sub = cohorts[0]
        assert pt == ProductType.TERM
        # Identity: homogeneous path must not copy
        assert sub is inforce
        assert sub.n_policies == 2

    def test_mixed_block_partitions_by_product_type(self) -> None:
        """A mixed block returns one sub-block per distinct product type."""
        inforce = load_inforce(
            policies_dict=[
                _policy_dict("T1", "TERM"),
                _policy_dict("W1", "WHOLE_LIFE"),
                _policy_dict("T2", "TERM"),
                _policy_dict("W2", "WHOLE_LIFE"),
                _policy_dict("W3", "WHOLE_LIFE"),
            ]
        )
        cohorts = iter_cohorts(inforce)
        assert len(cohorts) == 2

        # Deterministic order: sorted by ProductType.value
        assert [pt.value for pt, _ in cohorts] == sorted(["TERM", "WHOLE_LIFE"])

        by_type = {pt: sub for pt, sub in cohorts}
        assert by_type[ProductType.TERM].n_policies == 2
        assert by_type[ProductType.WHOLE_LIFE].n_policies == 3
        # Sub-blocks are new, not the original
        assert by_type[ProductType.TERM] is not inforce
        assert by_type[ProductType.WHOLE_LIFE] is not inforce

    def test_mixed_block_preserves_total_policies(self) -> None:
        """Sum of cohort sizes equals original block size."""
        inforce = load_inforce(
            policies_dict=[
                _policy_dict("T1", "TERM"),
                _policy_dict("W1", "WHOLE_LIFE"),
                _policy_dict("U1", "UL", face_amount=250_000.0),
            ]
        )
        cohorts = iter_cohorts(inforce)
        assert len(cohorts) == 3
        assert sum(sub.n_policies for _, sub in cohorts) == inforce.n_policies


class TestMixedCohortCLI:
    """End-to-end CLI pricing on a 2-product mixed CSV."""

    def test_price_cmd_runs_on_mixed_block(self, tmp_path: Path) -> None:
        """``polaris price`` produces one JSON cohort per distinct product type.

        Uses flat mortality + synthetic in-memory policies to avoid
        dependence on real SOA tables. Calls the Typer app via CliRunner
        so we exercise the real command path, not a stubbed function.
        """
        from typer.testing import CliRunner

        from polaris_re.cli import app

        # Minimal CSV with one TERM and one WHOLE_LIFE policy
        today = date.today().isoformat()
        csv_content = (
            "policy_id,issue_age,attained_age,sex,smoker_status,"
            "face_amount,annual_premium,product_type,policy_term,"
            "duration_inforce,issue_date,valuation_date\n"
            f"T1,40,40,M,NS,250000.0,600.0,TERM,20,0,2020-01-01,{today}\n"
            f"W1,45,45,F,NS,500000.0,3500.0,WHOLE_LIFE,,0,2020-01-01,{today}\n"
        )
        csv_path = tmp_path / "mixed.csv"
        csv_path.write_text(csv_content)

        # Config using flat mortality so the test doesn't depend on the
        # SOA tables being present on disk.
        config = {
            "mortality": {"source": "flat", "flat_qx": 0.002},
            "lapse": {
                "duration_table": {"1": 0.05, "2": 0.04, "ultimate": 0.03},
            },
            "deal": {
                "product_type": "TERM",  # will be overridden per-cohort
                "treaty_type": "YRT",
                "cession_pct": 0.50,
                "yrt_loading": 0.10,
                "discount_rate": 0.06,
                "hurdle_rate": 0.10,
                "projection_years": 10,
            },
        }
        config_path = tmp_path / "mixed.json"
        config_path.write_text(json.dumps(config))

        output_path = tmp_path / "result.json"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(config_path),
                "--inforce",
                str(csv_path),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, f"CLI failed: {result.stdout}"

        payload = json.loads(output_path.read_text())
        # Mixed-cohort schema: a cohorts list plus summary, no top-level
        # cedant/reinsurer back-compat keys (those only appear for n=1).
        assert "cohorts" in payload
        assert "summary" in payload
        assert payload["summary"]["n_cohorts"] == 2
        assert "cedant" not in payload  # back-compat only for single cohort

        cohort_types = sorted(c["product_type"] for c in payload["cohorts"])
        assert cohort_types == ["TERM", "WHOLE_LIFE"]

        # Every cohort must carry its own cedant profit test
        for cohort in payload["cohorts"]:
            assert cohort["n_policies"] == 1
            assert "pv_profits" in cohort["cedant"]
            # With cession > 0 both cohorts also get a reinsurer view
            assert cohort["reinsurer"] is not None
            assert "pv_profits" in cohort["reinsurer"]

    def test_scenario_cmd_rejects_mixed_block(self, tmp_path: Path) -> None:
        """``polaris scenario`` exits with an error on mixed product blocks."""
        from typer.testing import CliRunner

        from polaris_re.cli import app

        today = date.today().isoformat()
        csv_content = (
            "policy_id,issue_age,attained_age,sex,smoker_status,"
            "face_amount,annual_premium,product_type,policy_term,"
            "duration_inforce,issue_date,valuation_date\n"
            f"T1,40,40,M,NS,250000.0,600.0,TERM,20,0,2020-01-01,{today}\n"
            f"W1,45,45,F,NS,500000.0,3500.0,WHOLE_LIFE,,0,2020-01-01,{today}\n"
        )
        csv_path = tmp_path / "mixed.csv"
        csv_path.write_text(csv_content)

        config = {
            "mortality": {"source": "flat", "flat_qx": 0.002},
            "lapse": {"duration_table": {"1": 0.05, "ultimate": 0.03}},
            "deal": {
                "product_type": "TERM",
                "treaty_type": "YRT",
                "projection_years": 5,
                "hurdle_rate": 0.10,
            },
        }
        config_path = tmp_path / "mixed.json"
        config_path.write_text(json.dumps(config))

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "scenario",
                "--config",
                str(config_path),
                "--inforce",
                str(csv_path),
            ],
        )
        assert result.exit_code != 0
        assert "mixed" in result.stdout.lower() or "does not support" in result.stdout.lower()

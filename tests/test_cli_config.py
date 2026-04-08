"""Tests for CLI --config wiring and product/treaty dispatch."""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from polaris_re.cli import _build_pipeline_from_config, _build_treaty_for_pipeline
from polaris_re.core.policy import ProductType
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.reinsurance.modco import ModcoTreaty
from polaris_re.reinsurance.yrt import YRTTreaty


def _write_config(config: dict) -> Path:  # type: ignore[type-arg]
    """Write a config dict to a temp JSON file and return its path."""
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
        json.dump(config, tmp)
    return Path(tmp.name)


def _base_config(product_type: str = "TERM", **overrides: object) -> dict:  # type: ignore[type-arg]
    """Build a minimal valid config dict using the legacy flat schema."""
    cfg = {
        "product_type": product_type,
        "policies": [
            {
                "policy_id": "TEST-001",
                "issue_age": 40,
                "attained_age": 40,
                "sex": "M",
                "smoker": False,
                "face_amount": 500000.0,
                "annual_premium": 2000.0,
                "policy_term": 20 if product_type == "TERM" else None,
                "duration_inforce": 0,
                "issue_date": "2020-01-01",
                "valuation_date": date.today().isoformat(),
            }
        ],
        "projection_horizon_years": 10,
        "discount_rate": 0.06,
        "flat_qx": 0.001,
        "flat_lapse": 0.05,
    }
    cfg.update(overrides)
    return cfg


class TestBuildPipelineFromConfig:
    """Test _build_pipeline_from_config builds correct inforce/assumptions/config."""

    def test_term_config(self) -> None:
        path = _write_config(_base_config("TERM"))
        inforce, _assumptions, _config, _inputs = _build_pipeline_from_config(path)
        assert inforce.n_policies == 1
        assert inforce.policies[0].product_type == ProductType.TERM

    def test_whole_life_config(self) -> None:
        path = _write_config(_base_config("WHOLE_LIFE"))
        inforce, _assumptions, _config, _inputs = _build_pipeline_from_config(path)
        assert inforce.policies[0].product_type == ProductType.WHOLE_LIFE
        assert inforce.policies[0].policy_term is None

    def test_ul_config(self) -> None:
        cfg = _base_config("UL")
        cfg["policies"][0]["account_value"] = 50000.0  # type: ignore[index]
        cfg["policies"][0]["credited_rate"] = 0.04  # type: ignore[index]
        path = _write_config(cfg)
        inforce, _assumptions, _config, _inputs = _build_pipeline_from_config(path)
        assert inforce.policies[0].product_type == ProductType.UNIVERSAL_LIFE
        assert inforce.policies[0].account_value == 50000.0

    def test_projection_config_values(self) -> None:
        path = _write_config(
            _base_config(
                "TERM",
                projection_horizon_years=15,
                discount_rate=0.08,
                acquisition_cost_per_policy=1000.0,
                maintenance_cost_per_policy_per_year=200.0,
            )
        )
        _inforce, _assumptions, proj_config, _inputs = _build_pipeline_from_config(path)
        assert proj_config.projection_horizon_years == 15
        assert proj_config.discount_rate == 0.08
        assert proj_config.acquisition_cost_per_policy == 1000.0
        assert proj_config.maintenance_cost_per_policy_per_year == 200.0

    def test_config_product_dispatch_and_project(self) -> None:
        """End-to-end: config -> pipeline -> product dispatch -> projection."""
        path = _write_config(_base_config("TERM"))
        inforce, assumptions, config, _inputs = _build_pipeline_from_config(path)
        engine = get_product_engine(inforce, assumptions, config)
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.projection_months == 10 * 12

    def test_whole_life_dispatch_and_project(self) -> None:
        """End-to-end: whole life config -> pipeline -> dispatch -> projection."""
        path = _write_config(_base_config("WHOLE_LIFE"))
        inforce, assumptions, config, _inputs = _build_pipeline_from_config(path)
        engine = get_product_engine(inforce, assumptions, config)
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == ProductType.WHOLE_LIFE


class TestBuildTreatyFromPipeline:
    """Test _build_treaty_for_pipeline builds the correct treaty type."""

    @pytest.fixture()
    def gross_and_inputs(self):
        """Create a minimal gross CashFlowResult + PipelineInputs."""
        path = _write_config(_base_config("TERM"))
        inforce, assumptions, config, inputs = _build_pipeline_from_config(path)
        engine = get_product_engine(inforce, assumptions, config)
        return engine.project(), inputs, inforce

    def test_yrt_treaty(self, gross_and_inputs) -> None:
        gross, inputs, inforce = gross_and_inputs
        inputs.deal.treaty_type = "YRT"
        inputs.deal.cession_pct = 0.85
        treaty, _use_pc = _build_treaty_for_pipeline(inputs, gross, 500_000.0, inforce)
        assert isinstance(treaty, YRTTreaty)

    def test_coinsurance_treaty(self, gross_and_inputs) -> None:
        gross, inputs, inforce = gross_and_inputs
        inputs.deal.treaty_type = "Coinsurance"
        inputs.deal.cession_pct = 0.50
        treaty, _use_pc = _build_treaty_for_pipeline(inputs, gross, 500_000.0, inforce)
        assert isinstance(treaty, CoinsuranceTreaty)

    def test_modco_treaty(self, gross_and_inputs) -> None:
        gross, inputs, inforce = gross_and_inputs
        inputs.deal.treaty_type = "Modco"
        inputs.deal.modco_rate = 0.05
        treaty, _use_pc = _build_treaty_for_pipeline(inputs, gross, 500_000.0, inforce)
        assert isinstance(treaty, ModcoTreaty)

    def test_no_treaty(self, gross_and_inputs) -> None:
        gross, inputs, inforce = gross_and_inputs
        inputs.deal.treaty_type = "None"
        treaty, _use_pc = _build_treaty_for_pipeline(inputs, gross, 500_000.0, inforce)
        assert treaty is None

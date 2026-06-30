"""Tests for surfacing expense-allowance / experience-refund terms on the
deal-pricing config path (expense-allowance epic, Slice 3b-2a).

Covers:
1. Parsing ``deal.expense_allowance`` / ``deal.experience_refund`` blocks of a
   nested-schema config into the corresponding Pydantic models on ``DealConfig``.
2. Absent terms → both fields default ``None`` (byte-identical config).
3. A malformed allowance block raises ``PolarisValidationError`` at parse time.
4. ``build_treaty`` threads both terms onto YRT / Coinsurance treaties and
   ignores them for Modco / gross.
5. ``_build_treaty_for_pipeline`` carries the deal terms onto the built treaty.
6. End-to-end: an allowance supplied via config shifts the net/ceded expense
   line while preserving ``net + ceded == gross``; absent → byte-identical apply.
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from polaris_re.cli import _build_pipeline_from_config, _build_treaty_for_pipeline
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.pipeline import build_treaty
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.coinsurance import CoinsuranceTreaty
from polaris_re.reinsurance.expense_allowance import ExpenseAllowance
from polaris_re.reinsurance.experience_refund import ExperienceRefund
from polaris_re.reinsurance.modco import ModcoTreaty
from polaris_re.reinsurance.yrt import YRTTreaty


def _write_config(config: dict) -> Path:  # type: ignore[type-arg]
    """Write a config dict to a temp JSON file and return its path."""
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
        json.dump(config, tmp)
    return Path(tmp.name)


def _nested_config(**deal_overrides: object) -> dict:  # type: ignore[type-arg]
    """Build a minimal valid nested-schema config with a single TERM policy."""
    deal: dict = {  # type: ignore[type-arg]
        "product_type": "TERM",
        "treaty_type": "Coinsurance",
        "cession_pct": 0.50,
        "discount_rate": 0.06,
        "hurdle_rate": 0.10,
        "projection_years": 10,
        "acquisition_cost": 500.0,
        "maintenance_cost": 75.0,
        "use_policy_cession": False,
    }
    deal.update(deal_overrides)
    return {
        "mortality": {"source": "flat", "flat_qx": 0.003, "multiplier": 1.0},
        "lapse": {"duration_table": {"1": 0.05, "ultimate": 0.03}},
        "deal": deal,
        "policies": [
            {
                "policy_id": "TEST-001",
                "issue_age": 40,
                "attained_age": 40,
                "sex": "M",
                "smoker": False,
                "face_amount": 1_000_000.0,
                "annual_premium": 3000.0,
                "policy_term": 20,
                "duration_inforce": 0,
                "issue_date": "2025-01-01",
                "valuation_date": "2025-01-01",
            }
        ],
    }


_ALLOWANCE_BLOCK = {
    "first_year_pct": 0.40,
    "renewal_pct": 0.10,
    "months_per_year": 12,
}
_REFUND_BLOCK = {
    "refund_pct": 0.50,
    "retention": 1000.0,
    "reinsurer_margin_pct": 0.05,
}


# --------------------------------------------------------------------------- #
# 1. Config parsing → DealConfig models                                       #
# --------------------------------------------------------------------------- #


class TestConfigParsing:
    def test_expense_allowance_parsed(self) -> None:
        path = _write_config(_nested_config(expense_allowance=dict(_ALLOWANCE_BLOCK)))
        _inf, _ass, _cfg, inputs = _build_pipeline_from_config(path)
        allowance = inputs.deal.expense_allowance
        assert isinstance(allowance, ExpenseAllowance)
        assert allowance.first_year_pct == 0.40
        assert allowance.renewal_pct == 0.10

    def test_experience_refund_parsed(self) -> None:
        path = _write_config(_nested_config(experience_refund=dict(_REFUND_BLOCK)))
        _inf, _ass, _cfg, inputs = _build_pipeline_from_config(path)
        refund = inputs.deal.experience_refund
        assert isinstance(refund, ExperienceRefund)
        assert refund.refund_pct == 0.50
        assert refund.retention == 1000.0
        assert refund.reinsurer_margin_pct == 0.05

    def test_sliding_scale_parsed(self) -> None:
        block = {
            "first_year_pct": 0.40,
            "renewal_pct": 0.10,
            "sliding_scale": [
                {"max_loss_ratio": 0.60, "allowance_pct": 0.15},
                {"max_loss_ratio": 0.80, "allowance_pct": 0.10},
            ],
        }
        path = _write_config(_nested_config(expense_allowance=block))
        _inf, _ass, _cfg, inputs = _build_pipeline_from_config(path)
        allowance = inputs.deal.expense_allowance
        assert isinstance(allowance, ExpenseAllowance)
        assert allowance.sliding_scale is not None
        assert len(allowance.sliding_scale) == 2
        assert allowance.sliding_scale[0].max_loss_ratio == 0.60

    def test_absent_terms_default_none(self) -> None:
        path = _write_config(_nested_config())
        _inf, _ass, _cfg, inputs = _build_pipeline_from_config(path)
        assert inputs.deal.expense_allowance is None
        assert inputs.deal.experience_refund is None

    def test_malformed_allowance_raises_validation_error(self) -> None:
        # Non-monotone sliding scale (a lower loss ratio pays a LOWER rate)
        # must fail loudly at parse time, not silently invert the incentive.
        block = {
            "first_year_pct": 0.40,
            "renewal_pct": 0.10,
            "sliding_scale": [
                {"max_loss_ratio": 0.60, "allowance_pct": 0.10},
                {"max_loss_ratio": 0.80, "allowance_pct": 0.15},
            ],
        }
        path = _write_config(_nested_config(expense_allowance=block))
        with pytest.raises(PolarisValidationError, match="monotone non-increasing"):
            _build_pipeline_from_config(path)


# --------------------------------------------------------------------------- #
# 2. build_treaty factory threading                                           #
# --------------------------------------------------------------------------- #


class TestBuildTreatyThreading:
    def test_yrt_threads_both_terms(self) -> None:
        allowance = ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10)
        refund = ExperienceRefund(refund_pct=0.50)
        treaty = build_treaty(
            treaty_type="YRT",
            cession_pct=0.90,
            face_amount=1_000_000.0,
            yrt_rate_per_1000=2.0,
            expense_allowance=allowance,
            experience_refund=refund,
        )
        assert isinstance(treaty, YRTTreaty)
        assert treaty.expense_allowance is allowance
        assert treaty.experience_refund is refund

    def test_coinsurance_threads_both_terms(self) -> None:
        allowance = ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10)
        refund = ExperienceRefund(refund_pct=0.50)
        treaty = build_treaty(
            treaty_type="Coinsurance",
            cession_pct=0.50,
            face_amount=1_000_000.0,
            expense_allowance=allowance,
            experience_refund=refund,
        )
        assert isinstance(treaty, CoinsuranceTreaty)
        assert treaty.expense_allowance is allowance
        assert treaty.experience_refund is refund

    def test_default_none_leaves_fields_none(self) -> None:
        treaty = build_treaty(
            treaty_type="Coinsurance",
            cession_pct=0.50,
            face_amount=1_000_000.0,
        )
        assert isinstance(treaty, CoinsuranceTreaty)
        assert treaty.expense_allowance is None
        assert treaty.experience_refund is None

    def test_modco_ignores_terms(self) -> None:
        # Modco has no allowance/refund field; passing the terms must not raise.
        allowance = ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10)
        treaty = build_treaty(
            treaty_type="Modco",
            cession_pct=0.50,
            face_amount=1_000_000.0,
            modco_rate=0.045,
            expense_allowance=allowance,
        )
        assert isinstance(treaty, ModcoTreaty)


# --------------------------------------------------------------------------- #
# 3. _build_treaty_for_pipeline carries deal terms                            #
# --------------------------------------------------------------------------- #


class TestBuildTreatyForPipeline:
    @pytest.fixture()
    def gross_and_inputs(self):
        path = _write_config(_nested_config(treaty_type="Coinsurance"))
        inforce, assumptions, config, inputs = _build_pipeline_from_config(path)
        engine = get_product_engine(inforce, assumptions, config)
        return engine.project(), inputs, inforce

    def test_coinsurance_carries_deal_terms(self, gross_and_inputs) -> None:
        gross, inputs, inforce = gross_and_inputs
        allowance = ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10)
        refund = ExperienceRefund(refund_pct=0.50)
        inputs.deal.expense_allowance = allowance
        inputs.deal.experience_refund = refund
        treaty, _use_pc = _build_treaty_for_pipeline(inputs, gross, 1_000_000.0, inforce)
        assert isinstance(treaty, CoinsuranceTreaty)
        assert treaty.expense_allowance is allowance
        assert treaty.experience_refund is refund

    def test_yrt_carries_deal_terms(self, gross_and_inputs) -> None:
        gross, inputs, inforce = gross_and_inputs
        inputs.deal.treaty_type = "YRT"
        allowance = ExpenseAllowance(first_year_pct=0.40, renewal_pct=0.10)
        inputs.deal.expense_allowance = allowance
        treaty, _use_pc = _build_treaty_for_pipeline(inputs, gross, 1_000_000.0, inforce)
        assert isinstance(treaty, YRTTreaty)
        assert treaty.expense_allowance is allowance


# --------------------------------------------------------------------------- #
# 4. End-to-end: the config-supplied allowance changes the priced cash flows  #
# --------------------------------------------------------------------------- #


class TestEndToEndEffect:
    def _project_and_apply(self, config: dict):  # type: ignore[type-arg]
        path = _write_config(config)
        inforce, assumptions, proj, inputs = _build_pipeline_from_config(path)
        engine = get_product_engine(inforce, assumptions, proj)
        gross = engine.project()
        treaty, use_pc = _build_treaty_for_pipeline(
            inputs, gross, inforce.total_face_amount(), inforce
        )
        net, ceded = treaty.apply(gross, inforce=inforce if use_pc else None)
        return gross, net, ceded

    def test_allowance_shifts_expense_line_preserving_additivity(self) -> None:
        # Baseline: no allowance on the config.
        _base_gross, base_net, base_ceded = self._project_and_apply(
            _nested_config(treaty_type="Coinsurance")
        )
        # With an allowance supplied via config.
        a_gross, a_net, a_ceded = self._project_and_apply(
            _nested_config(
                treaty_type="Coinsurance",
                expense_allowance=dict(_ALLOWANCE_BLOCK),
            )
        )
        # The allowance is a reinsurer→cedant transfer: it raises ceded expense
        # and lowers net expense, and must net to zero across the pair.
        assert not np.allclose(a_ceded.expenses, base_ceded.expenses)
        np.testing.assert_allclose(
            a_net.expenses + a_ceded.expenses,
            base_net.expenses + base_ceded.expenses,
        )
        # Additivity invariant still holds with the allowance applied.
        np.testing.assert_allclose(
            a_net.net_cash_flow + a_ceded.net_cash_flow, a_gross.net_cash_flow
        )

    def test_no_terms_byte_identical_apply(self) -> None:
        # A config with the keys absent must apply exactly as today.
        _g1, n1, c1 = self._project_and_apply(_nested_config(treaty_type="Coinsurance"))
        _g2, n2, c2 = self._project_and_apply(_nested_config(treaty_type="Coinsurance"))
        np.testing.assert_array_equal(n1.net_cash_flow, n2.net_cash_flow)
        np.testing.assert_array_equal(c1.net_cash_flow, c2.net_cash_flow)

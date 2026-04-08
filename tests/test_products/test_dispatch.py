"""Tests for product engine dispatch."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.dispatch import get_product_engine
from polaris_re.products.term_life import TermLife
from polaris_re.products.universal_life import UniversalLife
from polaris_re.products.whole_life import WholeLife
from polaris_re.utils.table_io import MortalityTableArray


@pytest.fixture()
def flat_assumptions() -> AssumptionSet:
    """Build a flat-rate assumption set covering all sex/smoker combos."""
    n_ages = 121 - 18
    qx = np.full(n_ages, 0.001, dtype=np.float64)
    rates_2d = qx.reshape(-1, 1)

    tables: dict[str, MortalityTableArray] = {}
    for sex in (Sex.MALE, Sex.FEMALE):
        for smoker in (SmokerStatus.SMOKER, SmokerStatus.NON_SMOKER, SmokerStatus.UNKNOWN):
            key = f"{sex.value}_{smoker.value}"
            tables[key] = MortalityTableArray(
                rates=rates_2d.copy(),
                min_age=18,
                max_age=120,
                select_period=0,
                source_file=Path("test"),
            )

    mortality = MortalityTable(
        source=MortalityTableSource.CSO_2001,
        table_name="Test flat",
        min_age=18,
        max_age=120,
        select_period_years=0,
        has_smoker_distinct_rates=False,
        tables=tables,
    )
    lapse = LapseAssumption.from_duration_table({1: 0.05, "ultimate": 0.02})
    return AssumptionSet(
        mortality=mortality,
        lapse=lapse,
        version="test-v1",
        effective_date=date.today(),
    )


@pytest.fixture()
def config() -> ProjectionConfig:
    return ProjectionConfig(
        valuation_date=date.today(),
        projection_horizon_years=10,
        discount_rate=0.06,
    )


def _make_policy(product_type: ProductType, **overrides: object) -> Policy:
    defaults = {
        "policy_id": "TEST-001",
        "issue_age": 40,
        "attained_age": 40,
        "sex": Sex.MALE,
        "smoker_status": SmokerStatus.NON_SMOKER,
        "underwriting_class": "STANDARD",
        "face_amount": 500_000.0,
        "annual_premium": 2_000.0,
        "policy_term": 20 if product_type == ProductType.TERM else None,
        "duration_inforce": 0,
        "reinsurance_cession_pct": 0.0,
        "issue_date": date(2020, 1, 1),
        "valuation_date": date.today(),
        "product_type": product_type,
    }
    defaults.update(overrides)
    return Policy(**defaults)  # type: ignore[arg-type]


class TestProductDispatch:
    """Test that get_product_engine returns the correct engine."""

    def test_dispatch_term(self, flat_assumptions: AssumptionSet, config: ProjectionConfig) -> None:
        policy = _make_policy(ProductType.TERM)
        inforce = InforceBlock(policies=[policy])
        engine = get_product_engine(inforce, flat_assumptions, config)
        assert isinstance(engine, TermLife)

    def test_dispatch_whole_life(
        self, flat_assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        policy = _make_policy(ProductType.WHOLE_LIFE)
        inforce = InforceBlock(policies=[policy])
        engine = get_product_engine(inforce, flat_assumptions, config)
        assert isinstance(engine, WholeLife)

    def test_dispatch_ul(self, flat_assumptions: AssumptionSet, config: ProjectionConfig) -> None:
        policy = _make_policy(
            ProductType.UNIVERSAL_LIFE,
            account_value=50_000.0,
            credited_rate=0.04,
        )
        inforce = InforceBlock(policies=[policy])
        engine = get_product_engine(inforce, flat_assumptions, config)
        assert isinstance(engine, UniversalLife)

    def test_dispatch_empty_inforce_raises(
        self, flat_assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        # InforceBlock requires at least 1 policy via Pydantic validation
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            InforceBlock(policies=[])

    def test_dispatch_unsupported_type_raises(
        self, flat_assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        policy = _make_policy(ProductType.ANNUITY)
        inforce = InforceBlock(policies=[policy])
        with pytest.raises(PolarisValidationError, match="No product engine"):
            get_product_engine(inforce, flat_assumptions, config)

    def test_term_projection_runs(
        self, flat_assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        policy = _make_policy(ProductType.TERM)
        inforce = InforceBlock(policies=[policy])
        engine = get_product_engine(inforce, flat_assumptions, config)
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == ProductType.TERM
        assert len(result.death_claims) == config.projection_months

    def test_whole_life_projection_runs(
        self, flat_assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        policy = _make_policy(ProductType.WHOLE_LIFE)
        inforce = InforceBlock(policies=[policy])
        engine = get_product_engine(inforce, flat_assumptions, config)
        result = engine.project()
        assert result.basis == "GROSS"
        assert result.product_type == ProductType.WHOLE_LIFE

    def test_ul_projection_runs(
        self, flat_assumptions: AssumptionSet, config: ProjectionConfig
    ) -> None:
        policy = _make_policy(
            ProductType.UNIVERSAL_LIFE,
            account_value=50_000.0,
            credited_rate=0.04,
        )
        inforce = InforceBlock(policies=[policy])
        engine = get_product_engine(inforce, flat_assumptions, config)
        result = engine.project()
        assert result.basis == "GROSS"
        # CashFlowResult may store product_type as string or enum
        assert str(result.product_type) in (
            ProductType.UNIVERSAL_LIFE.value,
            ProductType.UNIVERSAL_LIFE.name,
        )

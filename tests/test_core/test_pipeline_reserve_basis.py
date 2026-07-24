"""Unit tests for reserve-basis plumbing in the pipeline builder (slice 4).

``DealConfig.reserve_basis`` (a string) is coerced to the ``ReserveBasis`` enum
on the ``ProjectionConfig`` by ``build_projection_config`` via
``_coerce_reserve_basis``. These tests pin that coercion, the default, and the
clean error on a bad value.
"""

import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.reserve_basis import ReserveBasis
from polaris_re.pipeline import (
    DealConfig,
    PipelineInputs,
    _coerce_reserve_basis,
    build_projection_config,
)


class TestCoerceReserveBasis:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("NET_PREMIUM", ReserveBasis.NET_PREMIUM),
            ("CRVM", ReserveBasis.CRVM),
            ("VM20", ReserveBasis.VM20),
            ("GAAP", ReserveBasis.GAAP),
            ("crvm", ReserveBasis.CRVM),
            ("  vm20  ", ReserveBasis.VM20),
            (ReserveBasis.CRVM, ReserveBasis.CRVM),
        ],
    )
    def test_valid_values(self, value: str | ReserveBasis, expected: ReserveBasis) -> None:
        assert _coerce_reserve_basis(value) == expected

    def test_unknown_value_raises_with_valid_list(self) -> None:
        with pytest.raises(PolarisValidationError, match="Unknown reserve_basis"):
            _coerce_reserve_basis("BOGUS")


class TestBuildProjectionConfigReserveBasis:
    def test_default_is_net_premium(self) -> None:
        inputs = PipelineInputs(deal=DealConfig())
        config = build_projection_config(inputs)
        assert config.reserve_basis == ReserveBasis.NET_PREMIUM

    def test_deal_basis_flows_through(self) -> None:
        inputs = PipelineInputs(deal=DealConfig(reserve_basis="VM20"))
        config = build_projection_config(inputs)
        assert config.reserve_basis == ReserveBasis.VM20

    def test_bad_deal_basis_raises(self) -> None:
        inputs = PipelineInputs(deal=DealConfig(reserve_basis="NONSENSE"))
        with pytest.raises(PolarisValidationError):
            build_projection_config(inputs)

    def test_to_dict_round_trips_basis(self) -> None:
        deal = DealConfig(reserve_basis="CRVM")
        assert deal.to_dict()["reserve_basis"] == "CRVM"

"""
Tests for the ReserveBasis enum and its plumbing through ProjectionConfig.

Slice 1 of the reserve-basis epic is pure plumbing: the enum exists, the
config carries it, NET_PREMIUM is the default (preserving historical
behaviour), and the value round-trips through Pydantic serialization. The
actuarial bases (CRVM / VM20 / GAAP) are implemented in later slices; here
they only need to be selectable and to validate.
"""

from datetime import date

import pytest

from polaris_re.core import ReserveBasis
from polaris_re.core.projection import ProjectionConfig
from polaris_re.core.reserve_basis import ReserveBasis as ReserveBasisDirect


class TestReserveBasisEnum:
    """The enum itself — members, values, string behaviour."""

    def test_expected_members(self):
        assert {b.name for b in ReserveBasis} == {
            "NET_PREMIUM",
            "CRVM",
            "VM20",
            "GAAP",
        }

    def test_str_enum_values(self):
        # StrEnum members compare equal to their string value (matches the
        # Sex / ProductType convention used elsewhere in core).
        assert ReserveBasis.NET_PREMIUM == "NET_PREMIUM"
        assert ReserveBasis.CRVM == "CRVM"
        assert ReserveBasis.VM20 == "VM20"
        assert ReserveBasis.GAAP == "GAAP"

    def test_exported_from_core_package(self):
        # Both the package re-export and the module path resolve to the same enum.
        assert ReserveBasis is ReserveBasisDirect


class TestProjectionConfigReserveBasis:
    """ProjectionConfig plumbing."""

    def _config(self, **kw) -> ProjectionConfig:
        base = dict(
            valuation_date=date(2025, 1, 1),
            projection_horizon_years=20,
            discount_rate=0.05,
        )
        base.update(kw)
        return ProjectionConfig(**base)

    def test_default_is_net_premium(self):
        # Backward compatibility: omitting the field reproduces historical behaviour.
        assert self._config().reserve_basis is ReserveBasis.NET_PREMIUM

    def test_accepts_enum_member(self):
        cfg = self._config(reserve_basis=ReserveBasis.CRVM)
        assert cfg.reserve_basis is ReserveBasis.CRVM

    def test_accepts_string_value(self):
        # JSON / CLI configs supply the basis as a bare string.
        cfg = self._config(reserve_basis="VM20")
        assert cfg.reserve_basis is ReserveBasis.VM20

    def test_rejects_unknown_basis(self):
        with pytest.raises(ValueError):
            self._config(reserve_basis="STATUTORY_MADE_UP")

    def test_serialization_round_trip(self):
        cfg = self._config(reserve_basis=ReserveBasis.GAAP)
        dumped = cfg.model_dump()
        assert dumped["reserve_basis"] == "GAAP"
        restored = ProjectionConfig.model_validate(dumped)
        assert restored.reserve_basis is ReserveBasis.GAAP

    def test_json_round_trip(self):
        cfg = self._config(reserve_basis=ReserveBasis.CRVM)
        restored = ProjectionConfig.model_validate_json(cfg.model_dump_json())
        assert restored.reserve_basis is ReserveBasis.CRVM

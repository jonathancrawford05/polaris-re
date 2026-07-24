"""Unit tests for the ``valuation_mortality`` plumbing in the pipeline builder.

Reserve-Basis Exactness epic, Slice 2 (surfacing). ``DealConfig.valuation_mortality``
(a named mortality source id) is loaded by ``build_assumption_set`` — via the
shared ``load_valuation_mortality`` helper — and threaded onto
``AssumptionSet.valuation_mortality``, the slot Slice 1 (ADR-125) added for the
statutory reserve bases. These tests pin:

* the default (``None``) leaves ``AssumptionSet.valuation_mortality`` unset;
* a named source is loaded and attached;
* the valuation table is loaded **raw** — the pricing mortality multiplier is
  *not* applied to it (prescribed statutory tables are static, ADR-125);
* an unknown source id raises ``PolarisValidationError``.

The multiplier-isolation and default tests use the synthetic ``"flat"`` source
so they run without any external mortality-table CSVs (CI-safe). One test loads
the real 2001 CSO table and is skipped when the converted CSVs are absent.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.pipeline import (
    DealConfig,
    MortalityConfig,
    PipelineInputs,
    build_assumption_set,
    load_valuation_mortality,
)

_MORTALITY_DIR = Path(os.environ.get("POLARIS_DATA_DIR", "data")) / "mortality_tables"
_HAS_CSO = (_MORTALITY_DIR / "cso_2001_male.csv").exists()
requires_cso = pytest.mark.skipif(
    not _HAS_CSO, reason="2001 CSO tables required (run scripts/convert_soa_tables.py)"
)


def _any_rate(mortality) -> float:  # type: ignore[no-untyped-def]
    """Return the first rate of an arbitrary sex/smoker table (flat tables are uniform)."""
    first_key = next(iter(mortality.tables))
    return float(mortality.tables[first_key].rates[0, 0])


class TestLoadValuationMortality:
    def test_flat_source_builds_static_table(self) -> None:
        table = load_valuation_mortality("flat")
        # Default flat_qx is 0.001 (the pipeline flat default).
        assert _any_rate(table) == pytest.approx(0.001)

    def test_unknown_source_raises(self) -> None:
        with pytest.raises(PolarisValidationError, match="Unknown mortality source"):
            load_valuation_mortality("NOT_A_TABLE")

    @requires_cso
    def test_loads_named_cso_2001(self) -> None:
        table = load_valuation_mortality("CSO_2001")
        assert table.table_name  # loaded, non-empty
        assert table.source.value == "CSO_2001"


class TestBuildAssumptionSetValuationMortality:
    def test_default_is_none(self) -> None:
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.001),
            deal=DealConfig(),
        )
        assumptions = build_assumption_set(inputs)
        assert assumptions.valuation_mortality is None

    def test_named_source_is_attached(self) -> None:
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.001),
            deal=DealConfig(valuation_mortality="flat"),
        )
        assumptions = build_assumption_set(inputs)
        assert assumptions.valuation_mortality is not None

    def test_pricing_multiplier_not_applied_to_valuation_table(self) -> None:
        """The pricing mortality multiplier scales the projection table only.

        The valuation table is prescribed and static (ADR-125): a
        ``mortality.multiplier`` of 2.0 doubles the projection q but must leave
        the valuation table at its raw prescribed rates.
        """
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.001, multiplier=2.0),
            deal=DealConfig(valuation_mortality="flat"),
        )
        assumptions = build_assumption_set(inputs)
        # Projection table is scaled: 0.001 * 2.0 = 0.002.
        np.testing.assert_allclose(_any_rate(assumptions.mortality), 0.002)
        # Valuation table is raw: still 0.001, unscaled by the pricing multiplier.
        np.testing.assert_allclose(_any_rate(assumptions.valuation_mortality), 0.001)

    def test_unknown_source_raises(self) -> None:
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.001),
            deal=DealConfig(valuation_mortality="BOGUS"),
        )
        with pytest.raises(PolarisValidationError):
            build_assumption_set(inputs)

"""
Tests for MorbidityTable — CI and DI morbidity assumption tables.
"""

import numpy as np
import pytest

from polaris_re.assumptions.morbidity import MorbidityTable, MorbidityTableType
from polaris_re.core.exceptions import PolarisValidationError


class TestMorbidityTableConstruction:
    """Tests for CI and DI table creation."""

    def test_synthetic_ci_creates_successfully(self) -> None:
        table = MorbidityTable.synthetic_ci()
        assert table.table_type == MorbidityTableType.CRITICAL_ILLNESS
        assert table.source == "SYNTHETIC_CI_2012"

    def test_synthetic_di_creates_successfully(self) -> None:
        table = MorbidityTable.synthetic_di()
        assert table.table_type == MorbidityTableType.DISABILITY_INCOME

    def test_ci_has_no_termination(self) -> None:
        table = MorbidityTable.synthetic_ci()
        assert table.male_termination is None
        assert table.female_termination is None

    def test_di_has_termination(self) -> None:
        table = MorbidityTable.synthetic_di()
        assert table.male_termination is not None
        assert table.female_termination is not None

    def test_rates_in_unit_interval(self) -> None:
        for factory in [MorbidityTable.synthetic_ci, MorbidityTable.synthetic_di]:
            table = factory()
            assert np.all(table.male_incidence >= 0.0)
            assert np.all(table.male_incidence <= 1.0)
            assert np.all(table.female_incidence >= 0.0)
            assert np.all(table.female_incidence <= 1.0)

    def test_di_termination_in_unit_interval(self) -> None:
        table = MorbidityTable.synthetic_di()
        assert table.male_termination is not None
        assert np.all(table.male_termination >= 0.0)
        assert np.all(table.male_termination <= 1.0)

    def test_invalid_min_max_age(self) -> None:
        """max_age <= min_age raises PolarisValidationError."""
        with pytest.raises(PolarisValidationError, match="max_age must be"):
            MorbidityTable(
                table_type=MorbidityTableType.CRITICAL_ILLNESS,
                source="TEST",
                min_age=50,
                max_age=30,  # invalid
                male_incidence=np.zeros(1),
                female_incidence=np.zeros(1),
            )

    def test_wrong_array_size_raises(self) -> None:
        """Array length != max_age - min_age + 1 raises PolarisValidationError."""
        with pytest.raises(PolarisValidationError, match="shape"):
            MorbidityTable(
                table_type=MorbidityTableType.CRITICAL_ILLNESS,
                source="TEST",
                min_age=18,
                max_age=75,
                male_incidence=np.zeros(5),  # wrong size
                female_incidence=np.zeros(58),
            )

    def test_di_missing_termination_raises(self) -> None:
        """DI table without termination raises PolarisValidationError."""
        n = 75 - 18 + 1
        with pytest.raises(PolarisValidationError, match="termination"):
            MorbidityTable(
                table_type=MorbidityTableType.DISABILITY_INCOME,
                source="TEST",
                min_age=18,
                max_age=75,
                male_incidence=np.full(n, 0.01),
                female_incidence=np.full(n, 0.01),
                # termination not provided
            )


class TestMorbidityTableLookup:
    """Tests for vectorized rate lookup."""

    def test_incidence_vector_shape(self) -> None:
        """Output shape matches input ages shape."""
        table = MorbidityTable.synthetic_ci()
        ages = np.array([30, 40, 50, 60], dtype=np.int32)
        result = table.get_incidence_vector(ages, "M")
        assert result.shape == (4,)

    def test_incidence_male_vs_female(self) -> None:
        """Male CI rates are higher than female (per synthetic table design)."""
        table = MorbidityTable.synthetic_ci()
        ages = np.array([40, 50, 60], dtype=np.int32)
        male = table.get_incidence_vector(ages, "M")
        female = table.get_incidence_vector(ages, "F")
        assert np.all(male > female)

    def test_di_female_incidence_higher(self) -> None:
        """Female DI incidence is higher than male (per synthetic table design)."""
        table = MorbidityTable.synthetic_di()
        ages = np.array([35, 45, 55], dtype=np.int32)
        male = table.get_incidence_vector(ages, "M")
        female = table.get_incidence_vector(ages, "F")
        assert np.all(female > male)

    def test_incidence_age_clipping(self) -> None:
        """Ages below min_age return min_age rate; ages above max_age return max_age rate."""
        table = MorbidityTable.synthetic_ci()
        ages_low = np.array([5, 10], dtype=np.int32)
        ages_high = np.array([100, 120], dtype=np.int32)
        ages_min = np.array([table.min_age, table.min_age], dtype=np.int32)
        ages_max = np.array([table.max_age, table.max_age], dtype=np.int32)
        np.testing.assert_allclose(
            table.get_incidence_vector(ages_low, "M"),
            table.get_incidence_vector(ages_min, "M"),
            rtol=1e-10,
        )
        np.testing.assert_allclose(
            table.get_incidence_vector(ages_high, "M"),
            table.get_incidence_vector(ages_max, "M"),
            rtol=1e-10,
        )

    def test_termination_vector_shape(self) -> None:
        """DI termination vector shape matches input ages."""
        table = MorbidityTable.synthetic_di()
        ages = np.array([30, 40, 50], dtype=np.int32)
        result = table.get_termination_vector(ages, "M")
        assert result.shape == (3,)

    def test_ci_termination_raises(self) -> None:
        """get_termination_vector() raises for CI tables."""
        table = MorbidityTable.synthetic_ci()
        ages = np.array([40], dtype=np.int32)
        with pytest.raises(PolarisValidationError, match="DI"):
            table.get_termination_vector(ages, "M")

    def test_incidence_rates_positive(self) -> None:
        """Incidence rates are positive for working ages."""
        table = MorbidityTable.synthetic_ci()
        ages = np.arange(30, 70, dtype=np.int32)
        rates = table.get_incidence_vector(ages, "M")
        assert np.all(rates > 0.0)

    def test_ci_incidence_increases_with_age(self) -> None:
        """CI incidence should increase with age (general trend)."""
        table = MorbidityTable.synthetic_ci()
        ages_young = np.array([25, 30, 35], dtype=np.int32)
        ages_old = np.array([55, 60, 65], dtype=np.int32)
        young_mean = table.get_incidence_vector(ages_young, "M").mean()
        old_mean = table.get_incidence_vector(ages_old, "M").mean()
        assert old_mean > young_mean

    def test_di_termination_decreases_with_age(self) -> None:
        """DI termination rate should decrease with age (harder to recover older)."""
        table = MorbidityTable.synthetic_di()
        ages_young = np.array([25, 30, 35], dtype=np.int32)
        ages_old = np.array([55, 60, 65], dtype=np.int32)
        young_mean = table.get_termination_vector(ages_young, "M").mean()
        old_mean = table.get_termination_vector(ages_old, "M").mean()
        assert young_mean > old_mean

    def test_large_age_vector(self) -> None:
        """Vectorized lookup works for large age vectors."""
        table = MorbidityTable.synthetic_ci()
        ages = np.full(10_000, 45, dtype=np.int32)
        result = table.get_incidence_vector(ages, "F")
        assert result.shape == (10_000,)
        assert np.all(result == result[0])  # all same age → same rate

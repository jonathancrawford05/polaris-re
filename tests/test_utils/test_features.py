"""Tests for ML feature engineering utilities."""

import numpy as np

from polaris_re.utils.features import (
    add_age_bands,
    add_duration_bands,
    build_feature_matrix,
    log_face_amount,
)


class TestAgeBands:
    """Tests for add_age_bands."""

    def test_standard_5_year_bands(self):
        """Ages map to correct 5-year bands."""
        ages = np.array([23, 27, 30, 45, 50], dtype=np.int32)
        result = add_age_bands(ages)
        expected = np.array([20, 25, 30, 45, 50], dtype=np.int32)
        np.testing.assert_array_equal(result, expected)

    def test_10_year_bands(self):
        """10-year bands work correctly."""
        ages = np.array([23, 30, 45], dtype=np.int32)
        result = add_age_bands(ages, width=10)
        expected = np.array([20, 30, 40], dtype=np.int32)
        np.testing.assert_array_equal(result, expected)

    def test_boundary_ages(self):
        """Band boundaries map correctly."""
        ages = np.array([20, 24, 25, 29], dtype=np.int32)
        result = add_age_bands(ages)
        expected = np.array([20, 20, 25, 25], dtype=np.int32)
        np.testing.assert_array_equal(result, expected)

    def test_output_dtype(self):
        """Output is int32."""
        result = add_age_bands(np.array([40], dtype=np.int32))
        assert result.dtype == np.int32


class TestDurationBands:
    """Tests for add_duration_bands."""

    def test_band_assignments(self):
        """Duration months map to correct bands."""
        durs = np.array([0, 11, 12, 60, 72, 120, 132, 180, 240], dtype=np.int32)
        result = add_duration_bands(durs)
        # 0 months → yr 0 → band 0
        # 11 → yr 0 → band 0
        # 12 → yr 1 → band 0
        # 60 → yr 5 → band 1
        # 72 → yr 6 → band 2
        # 120 → yr 10 → band 2
        # 132 → yr 11 → band 3
        # 180 → yr 15 → band 3
        # 240 → yr 20 → band 4
        expected = np.array([0, 0, 0, 1, 2, 2, 3, 3, 4], dtype=np.int32)
        np.testing.assert_array_equal(result, expected)

    def test_output_shape(self):
        """Output shape matches input."""
        durs = np.array([0, 12, 24], dtype=np.int32)
        assert add_duration_bands(durs).shape == (3,)


class TestLogFaceAmount:
    """Tests for log_face_amount."""

    def test_positive_values(self):
        """Log transform of positive values."""
        face = np.array([100_000, 500_000, 1_000_000], dtype=np.float64)
        result = log_face_amount(face)
        np.testing.assert_allclose(result, np.log(face + 1), rtol=1e-10)

    def test_monotonic(self):
        """Log transform preserves ordering."""
        face = np.array([100_000, 500_000, 1_000_000], dtype=np.float64)
        result = log_face_amount(face)
        assert result[0] < result[1] < result[2]


class TestBuildFeatureMatrix:
    """Tests for build_feature_matrix."""

    def test_output_columns(self):
        """Feature matrix has expected columns."""
        df = build_feature_matrix(
            ages=np.array([40, 50], dtype=np.int32),
            sexes=np.array(["M", "F"]),
            smoker_statuses=np.array(["NS", "S"]),
            durations_months=np.array([60, 120], dtype=np.int32),
            face_amounts=np.array([500_000, 300_000], dtype=np.float64),
        )
        expected_cols = {
            "age", "age_sq", "age_band", "sex_male", "is_smoker",
            "duration_months", "duration_years", "duration_band",
            "face_amount", "log_face",
        }
        assert set(df.columns) == expected_cols

    def test_sex_encoding(self):
        """Sex is encoded as binary (M=1, F=0)."""
        df = build_feature_matrix(
            ages=np.array([40, 50], dtype=np.int32),
            sexes=np.array(["M", "F"]),
            smoker_statuses=np.array(["NS", "NS"]),
            durations_months=np.array([60, 60], dtype=np.int32),
            face_amounts=np.array([500_000, 500_000], dtype=np.float64),
        )
        assert df["sex_male"].to_list() == [1, 0]

    def test_smoker_encoding(self):
        """Smoker is encoded as binary (S=1, NS=0)."""
        df = build_feature_matrix(
            ages=np.array([40, 40], dtype=np.int32),
            sexes=np.array(["M", "M"]),
            smoker_statuses=np.array(["S", "NS"]),
            durations_months=np.array([60, 60], dtype=np.int32),
            face_amounts=np.array([500_000, 500_000], dtype=np.float64),
        )
        assert df["is_smoker"].to_list() == [1, 0]

    def test_output_row_count(self):
        """Output has same row count as input."""
        n = 10
        df = build_feature_matrix(
            ages=np.full(n, 40, dtype=np.int32),
            sexes=np.array(["M"] * n),
            smoker_statuses=np.array(["NS"] * n),
            durations_months=np.full(n, 60, dtype=np.int32),
            face_amounts=np.full(n, 500_000, dtype=np.float64),
        )
        assert len(df) == n

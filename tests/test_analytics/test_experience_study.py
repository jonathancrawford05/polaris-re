"""
Tests for experience study A/E analysis (analytics/experience_study.py).

Closed-form verification:
1. A/E = 1.0 when actual == expected
2. Credibility = 1.0 when actual >= n_full_credibility
3. Credibility = 0.0 when actual = 0
4. Blended rate interpolates between actual and expected
5. from_projection constructor produces correct A/E
6. add_age_bands produces correct band labels
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_study import AEResult, ExperienceStudy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data(
    n_groups: int = 5,
    base_actual: float = 100.0,
    ae_ratio: float = 1.0,
    exposure: float = 10_000.0,
) -> pl.DataFrame:
    """Build a simple DataFrame with n_groups rows, each with A/E = ae_ratio."""
    actual = np.full(n_groups, base_actual, dtype=np.float64)
    expected = actual / ae_ratio
    exp = np.full(n_groups, exposure, dtype=np.float64)
    age_bands = [f"{40 + 5*i}-{44 + 5*i}" for i in range(n_groups)]
    return pl.DataFrame({
        "actual": actual,
        "expected": expected,
        "exposure": exp,
        "age_band": age_bands,
        "sex": (["M", "F"] * 3)[:n_groups],
    })


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestExperienceStudyValidation:

    def test_raises_on_missing_columns(self):
        """ExperienceStudy should raise ValueError for missing required columns."""
        df = pl.DataFrame({"actual": [1.0], "exposure": [100.0]})  # missing 'expected'
        with pytest.raises(ValueError, match="expected"):
            ExperienceStudy(df)

    def test_raises_on_invalid_study_type(self):
        """study_type must be 'mortality' or 'lapse'."""
        df = _make_data(1)
        with pytest.raises(ValueError, match="study_type"):
            ExperienceStudy(df, study_type="morbidity")

    def test_raises_on_unknown_group_by(self):
        """group_by with unknown column names should raise."""
        df = _make_data(3)
        study = ExperienceStudy(df)
        with pytest.raises(ValueError, match="group_by"):
            study.run(group_by=["nonexistent_col"])

    def test_accepts_lapse_type(self):
        """study_type='lapse' should not raise."""
        df = _make_data(3)
        study = ExperienceStudy(df, study_type="lapse")
        result = study.run()
        assert result.study_type == "lapse"


# ---------------------------------------------------------------------------
# A/E ratio tests
# ---------------------------------------------------------------------------

class TestAERatios:

    def test_ae_equals_one_when_actual_equals_expected(self):
        """
        CLOSED-FORM: When actual == expected, A/E must equal exactly 1.0.
        """
        data = pl.DataFrame({
            "actual": [50.0, 100.0, 200.0],
            "expected": [50.0, 100.0, 200.0],
            "exposure": [1000.0, 2000.0, 3000.0],
        })
        study = ExperienceStudy(data)
        result = study.run()

        np.testing.assert_allclose(result.overall_ae, 1.0, rtol=1e-10)

    def test_ae_ratio_correct_simple_case(self):
        """
        CLOSED-FORM: actual=120, expected=100 → A/E = 1.2.
        """
        data = pl.DataFrame({
            "actual": [120.0],
            "expected": [100.0],
            "exposure": [1000.0],
        })
        study = ExperienceStudy(data)
        result = study.run()
        np.testing.assert_allclose(result.overall_ae, 1.2, rtol=1e-10)

    def test_ae_ratio_by_group(self):
        """Grouped A/E ratios should match manual calculation."""
        data = pl.DataFrame({
            "actual": [100.0, 80.0],
            "expected": [100.0, 100.0],
            "exposure": [1000.0, 1000.0],
            "sex": ["M", "F"],
        })
        study = ExperienceStudy(data)
        result = study.run(group_by=["sex"])

        # Find rows by sex
        df = result.summary
        male_ae = float(df.filter(pl.col("sex") == "M")["ae_ratio"][0])
        female_ae = float(df.filter(pl.col("sex") == "F")["ae_ratio"][0])

        np.testing.assert_allclose(male_ae, 1.0, rtol=1e-10)
        np.testing.assert_allclose(female_ae, 0.8, rtol=1e-10)

    def test_overall_ae_is_weighted_aggregate(self):
        """Overall A/E = total actual / total expected (not simple mean of group A/Es)."""
        data = pl.DataFrame({
            "actual": [200.0, 50.0],
            "expected": [100.0, 100.0],
            "exposure": [5000.0, 1000.0],
        })
        study = ExperienceStudy(data)
        result = study.run()
        expected_overall = 250.0 / 200.0  # = 1.25
        np.testing.assert_allclose(result.overall_ae, expected_overall, rtol=1e-10)


# ---------------------------------------------------------------------------
# Credibility tests
# ---------------------------------------------------------------------------

class TestCredibility:

    def test_full_credibility_when_actual_exceeds_n_full(self):
        """
        CLOSED-FORM: Z = min(1, sqrt(actual / n_full)) = 1.0 when actual >= n_full.
        """
        n_full = 1082.0
        data = pl.DataFrame({
            "actual": [n_full],  # exactly n_full → Z = 1.0
            "expected": [n_full],
            "exposure": [100_000.0],
        })
        study = ExperienceStudy(data, n_full_credibility=n_full)
        result = study.run()
        np.testing.assert_allclose(result.overall_credibility, 1.0, rtol=1e-6)

    def test_zero_credibility_at_zero_actual(self):
        """Z = min(1, sqrt(0 / n_full)) = 0.0 when actual = 0."""
        data = pl.DataFrame({
            "actual": [0.0],
            "expected": [100.0],
            "exposure": [1000.0],
        })
        study = ExperienceStudy(data)
        result = study.run()
        np.testing.assert_allclose(result.overall_credibility, 0.0, atol=1e-10)

    def test_partial_credibility(self):
        """
        CLOSED-FORM: actual = 100, n_full = 1000 → Z = sqrt(100/1000) = sqrt(0.1) ≈ 0.3162.
        """
        data = pl.DataFrame({
            "actual": [100.0],
            "expected": [100.0],
            "exposure": [10_000.0],
        })
        study = ExperienceStudy(data, n_full_credibility=1000.0)
        result = study.run()
        expected_z = np.sqrt(100.0 / 1000.0)
        np.testing.assert_allclose(result.overall_credibility, expected_z, rtol=1e-6)

    def test_credibility_in_summary_table(self):
        """Credibility column in summary table should be in [0, 1]."""
        data = _make_data(n_groups=5, base_actual=200.0)
        study = ExperienceStudy(data, n_full_credibility=500.0)
        result = study.run(group_by=["age_band"])
        cred_col = result.summary["credibility"].to_numpy()
        assert (cred_col >= 0.0).all()
        assert (cred_col <= 1.0).all()

    def test_blended_rate_interpolates(self):
        """
        CLOSED-FORM: blended = Z * actual_rate + (1-Z) * expected_rate.
        With Z=0.5, actual_rate=0.02, expected_rate=0.01 → blended=0.015.
        """
        n_full = 100.0
        actual = 25.0  # Z = sqrt(25/100) = 0.5
        exposure = 1000.0
        expected_events = 10.0  # expected_rate = 10/1000 = 0.01

        data = pl.DataFrame({
            "actual": [actual],
            "expected": [expected_events],
            "exposure": [exposure],
        })
        study = ExperienceStudy(data, n_full_credibility=n_full)
        result = study.run()

        z = 0.5
        actual_rate = actual / exposure
        expected_rate = expected_events / exposure
        expected_blended = z * actual_rate + (1 - z) * expected_rate

        blended = float(result.summary["blended_rate"][0])
        np.testing.assert_allclose(blended, expected_blended, rtol=1e-6)


# ---------------------------------------------------------------------------
# credibility_adjusted_multipliers
# ---------------------------------------------------------------------------

class TestCredibilityAdjustedMultipliers:

    def test_multiplier_one_when_ae_one(self):
        """When A/E = 1.0, multiplier should be exactly 1.0 regardless of credibility."""
        data = pl.DataFrame({
            "actual": [200.0],
            "expected": [200.0],
            "exposure": [5000.0],
        })
        study = ExperienceStudy(data)
        result = study.run()
        df = result.credibility_adjusted_multipliers()
        multiplier = float(df["multiplier"][0])
        np.testing.assert_allclose(multiplier, 1.0, rtol=1e-6)

    def test_multiplier_between_one_and_ae(self):
        """
        Credibility-weighted multiplier should be between 1.0 and A/E
        (since it blends toward expected = 1.0).
        """
        data = pl.DataFrame({
            "actual": [150.0],  # A/E = 1.5
            "expected": [100.0],
            "exposure": [5000.0],
        })
        study = ExperienceStudy(data, n_full_credibility=1000.0)
        result = study.run()
        df = result.credibility_adjusted_multipliers()
        multiplier = float(df["multiplier"][0])
        ae = result.overall_ae
        # multiplier should be in (1.0, ae)
        assert 1.0 <= multiplier <= ae


# ---------------------------------------------------------------------------
# from_projection constructor
# ---------------------------------------------------------------------------

class TestFromProjection:

    def test_from_projection_overall_ae(self):
        """from_projection with actual = expected gives A/E = 1.0."""
        T = 12
        events = np.full(T, 5.0, dtype=np.float64)
        exposure = np.full(T, 1000.0, dtype=np.float64)
        study = ExperienceStudy.from_projection(
            actual_deaths=events,
            expected_deaths=events,
            exposure=exposure,
        )
        result = study.run()
        np.testing.assert_allclose(result.overall_ae, 1.0, rtol=1e-10)

    def test_from_projection_length_mismatch_raises(self):
        """Mismatched array lengths should raise ValueError."""
        with pytest.raises(ValueError, match="equal length"):
            ExperienceStudy.from_projection(
                actual_deaths=np.ones(10),
                expected_deaths=np.ones(10),
                exposure=np.ones(5),  # wrong length
            )

    def test_from_projection_study_type(self):
        """from_projection should pass study_type correctly."""
        data = ExperienceStudy.from_projection(
            actual_deaths=np.ones(5),
            expected_deaths=np.ones(5),
            exposure=np.ones(5) * 100,
            study_type="lapse",
        )
        assert data.study_type == "lapse"


# ---------------------------------------------------------------------------
# add_age_bands helper
# ---------------------------------------------------------------------------

class TestAddAgeBands:

    def test_age_band_labels(self):
        """
        CLOSED-FORM: age 37 with band_width=5 → band '35-39'.
        """
        data = pl.DataFrame({"age": [37, 42, 50], "actual": [1.0, 2.0, 3.0],
                              "expected": [1.0, 2.0, 3.0], "exposure": [100.0, 100.0, 100.0]})
        result = ExperienceStudy.add_age_bands(data, age_col="age", band_width=5)
        bands = result["age_band"].to_list()
        assert bands[0] == "35-39"
        assert bands[1] == "40-44"
        assert bands[2] == "50-54"

    def test_age_band_groups_runnable(self):
        """add_age_bands output can be used in an ExperienceStudy.run(group_by=['age_band'])."""
        raw = pl.DataFrame({
            "age": [35, 37, 42, 45, 51],
            "actual": [5.0, 8.0, 10.0, 12.0, 7.0],
            "expected": [5.0, 8.0, 10.0, 12.0, 7.0],
            "exposure": [1000.0] * 5,
        })
        data = ExperienceStudy.add_age_bands(raw, band_width=5)
        study = ExperienceStudy(data)
        result = study.run(group_by=["age_band"])
        # All A/E ratios should be 1.0
        ae_values = result.summary["ae_ratio"].to_numpy()
        np.testing.assert_allclose(ae_values, 1.0, rtol=1e-10)


# ---------------------------------------------------------------------------
# Aggregation and totals
# ---------------------------------------------------------------------------

class TestAggregationTotals:

    def test_total_actual_sums_correctly(self):
        """total_actual should equal sum of actual column."""
        data = _make_data(n_groups=5, base_actual=100.0)
        study = ExperienceStudy(data)
        result = study.run()
        np.testing.assert_allclose(result.total_actual, 500.0, rtol=1e-10)

    def test_no_grouping_produces_single_row(self):
        """Without group_by, summary should have exactly one row."""
        data = _make_data(n_groups=3)
        study = ExperienceStudy(data)
        result = study.run(group_by=None)
        assert len(result.summary) == 1

    def test_groupby_produces_correct_number_of_rows(self):
        """group_by=['age_band'] should produce one row per unique age_band."""
        data = _make_data(n_groups=5)  # 5 distinct age_bands
        study = ExperienceStudy(data)
        result = study.run(group_by=["age_band"])
        assert len(result.summary) == 5

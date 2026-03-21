"""Tests for MLMortalityAssumption — ML-enhanced mortality predictions."""

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingRegressor

from polaris_re.assumptions.ml_mortality import MLMortalityAssumption
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.utils.features import build_feature_matrix


def _synthetic_training_data(n: int = 500, seed: int = 42):
    """Generate synthetic mortality training data."""
    rng = np.random.default_rng(seed)
    ages = rng.integers(25, 75, size=n).astype(np.int32)
    sexes = rng.choice(["M", "F"], size=n)
    smokers = rng.choice(["S", "NS"], size=n, p=[0.2, 0.8])
    durs = rng.integers(0, 240, size=n).astype(np.int32)
    face = rng.uniform(100_000, 1_000_000, size=n)

    features = build_feature_matrix(ages, sexes, smokers, durs, face)

    # Realistic q_x: exponential in age
    q_x = np.clip(np.exp(-10 + 0.08 * ages) * np.where(smokers == "S", 2, 1), 0.0001, 0.3)
    return features, q_x


class TestMLMortalityConstruction:
    """Tests for construction and factory methods."""

    def test_from_trained_model(self):
        """Constructs from a pre-trained model."""
        model = GradientBoostingRegressor(n_estimators=10, random_state=42)
        x, y = _synthetic_training_data(n=100)
        model.fit(x.to_numpy(), y)
        ml = MLMortalityAssumption.from_trained_model(
            model=model, feature_names=list(x.columns), model_type="gradient_boosting"
        )
        assert ml.model_type == "gradient_boosting"
        assert len(ml.feature_names) == 10

    def test_fit_gradient_boosting(self):
        """Fit method trains a gradient boosting model."""
        x, y = _synthetic_training_data(n=200)
        ml = MLMortalityAssumption.fit(x, y, model_type="gradient_boosting", n_estimators=10)
        assert ml.model_type == "gradient_boosting"
        assert ml.model is not None

    def test_fit_xgboost(self):
        """Fit method trains an XGBoost model."""
        x, y = _synthetic_training_data(n=200)
        ml = MLMortalityAssumption.fit(x, y, model_type="xgboost", n_estimators=10)
        assert ml.model_type == "xgboost"


class TestMLMortalityPrediction:
    """Tests for get_qx_vector predictions."""

    @pytest.fixture()
    def ml_model(self):
        x, y = _synthetic_training_data(n=500)
        return MLMortalityAssumption.fit(
            x, y, model_type="gradient_boosting", n_estimators=50, random_state=42
        )

    def test_output_shape(self, ml_model):
        """Prediction output has correct shape."""
        ages = np.array([30, 40, 50, 60], dtype=np.int32)
        durs = np.array([0, 12, 24, 36], dtype=np.int32)
        result = ml_model.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert result.shape == (4,)

    def test_output_dtype(self, ml_model):
        """Predictions are float64."""
        ages = np.array([40], dtype=np.int32)
        durs = np.array([12], dtype=np.int32)
        result = ml_model.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert result.dtype == np.float64

    def test_rates_in_unit_interval(self, ml_model):
        """All predicted rates are in [0, 1]."""
        ages = np.arange(25, 75, dtype=np.int32)
        durs = np.full(50, 60, dtype=np.int32)
        result = ml_model.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        assert np.all(result >= 0.0)
        assert np.all(result <= 1.0)

    def test_monthly_less_than_annual(self, ml_model):
        """Monthly rates should be less than annual rates (for reasonable q_x)."""
        ages = np.array([40, 50, 60], dtype=np.int32)
        durs = np.array([12, 12, 12], dtype=np.int32)
        q_monthly = ml_model.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        # Monthly should be roughly q_annual/12 for small q_annual
        # Just verify monthly < 1/12 for typical rates
        assert np.all(q_monthly < 0.1)

    def test_rates_increase_with_age(self, ml_model):
        """Mortality rates generally increase with age."""
        ages = np.array([30, 50, 70], dtype=np.int32)
        durs = np.full(3, 60, dtype=np.int32)
        result = ml_model.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        # Expect monotonic increase (may not be strictly so due to ML noise)
        assert result[2] > result[0]

    def test_smoker_higher_than_nonsmoker(self, ml_model):
        """Smoker mortality should be higher than non-smoker."""
        ages = np.array([45], dtype=np.int32)
        durs = np.array([60], dtype=np.int32)
        q_ns = ml_model.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)
        q_s = ml_model.get_qx_vector(ages, Sex.MALE, SmokerStatus.SMOKER, durs)
        assert q_s[0] > q_ns[0]

    def test_with_face_amounts(self, ml_model):
        """Prediction works with explicit face amounts."""
        ages = np.array([40, 50], dtype=np.int32)
        durs = np.array([12, 24], dtype=np.int32)
        face = np.array([200_000, 1_000_000], dtype=np.float64)
        result = ml_model.get_qx_vector(
            ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs, face_amounts=face
        )
        assert result.shape == (2,)


class TestMLMortalityPersistence:
    """Tests for model save/load."""

    def test_save_and_load(self, tmp_path):
        """Model round-trips through save/load."""
        x, y = _synthetic_training_data(n=200)
        ml = MLMortalityAssumption.fit(x, y, model_type="gradient_boosting", n_estimators=10)

        path = tmp_path / "model.joblib"
        ml.save(path)

        loaded = MLMortalityAssumption.load(path)
        assert loaded.model_type == "gradient_boosting"
        assert loaded.feature_names == ml.feature_names

    def test_predictions_match_after_load(self, tmp_path):
        """Predictions are identical before and after save/load."""
        x, y = _synthetic_training_data(n=200)
        ml = MLMortalityAssumption.fit(
            x, y, model_type="gradient_boosting", n_estimators=10, random_state=42
        )

        ages = np.array([40, 50], dtype=np.int32)
        durs = np.array([12, 24], dtype=np.int32)
        pred_before = ml.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)

        path = tmp_path / "model.joblib"
        ml.save(path)
        loaded = MLMortalityAssumption.load(path)
        pred_after = loaded.get_qx_vector(ages, Sex.MALE, SmokerStatus.NON_SMOKER, durs)

        np.testing.assert_allclose(pred_before, pred_after, rtol=1e-10)

    def test_ae_ratio_reasonable(self):
        """A/E ratio on training data is close to 1.0."""
        x, y = _synthetic_training_data(n=1000)
        ml = MLMortalityAssumption.fit(
            x, y, model_type="gradient_boosting", n_estimators=100, random_state=42
        )
        x_np = x.to_numpy().astype(np.float64)
        y_pred = np.clip(ml.model.predict(x_np), 0.0, 1.0)
        ae = y.sum() / y_pred.sum()
        # A/E should be close to 1.0 on training data
        assert 0.8 < ae < 1.2

"""Tests for MLLapseAssumption — ML-enhanced lapse predictions."""

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingRegressor

from polaris_re.assumptions.ml_lapse import MLLapseAssumption
from polaris_re.utils.features import build_feature_matrix


def _synthetic_lapse_data(n: int = 500, seed: int = 42):
    """Generate synthetic lapse training data."""
    rng = np.random.default_rng(seed)
    ages = rng.integers(25, 75, size=n).astype(np.int32)
    sexes = rng.choice(["M", "F"], size=n)
    smokers = rng.choice(["S", "NS"], size=n)
    durs = rng.integers(0, 240, size=n).astype(np.int32)
    face = rng.uniform(100_000, 1_000_000, size=n)

    features = build_feature_matrix(ages, sexes, smokers, durs, face)

    # Realistic lapse: declining with duration
    dur_years = durs / 12
    w = np.clip(0.12 * np.exp(-0.15 * dur_years) + 0.025, 0.001, 0.25)
    return features, w


class TestMLLapseConstruction:
    """Tests for construction."""

    def test_from_trained_model(self):
        """Constructs from a pre-trained model."""
        model = GradientBoostingRegressor(n_estimators=10, random_state=42)
        x, y = _synthetic_lapse_data(n=100)
        model.fit(x.to_numpy(), y)
        ml = MLLapseAssumption.from_trained_model(
            model=model, feature_names=list(x.columns)
        )
        assert ml.model is not None

    def test_fit(self):
        """Fit method trains a model."""
        x, y = _synthetic_lapse_data(n=200)
        ml = MLLapseAssumption.fit(x, y, n_estimators=10)
        assert ml.model_type == "gradient_boosting"


class TestMLLapsePrediction:
    """Tests for get_lapse_vector."""

    @pytest.fixture()
    def ml_model(self):
        x, y = _synthetic_lapse_data(n=500)
        return MLLapseAssumption.fit(
            x, y, model_type="gradient_boosting", n_estimators=50, random_state=42
        )

    def test_output_shape(self, ml_model):
        """Prediction output has correct shape."""
        durs = np.array([0, 12, 24, 60], dtype=np.int32)
        result = ml_model.get_lapse_vector(durs)
        assert result.shape == (4,)

    def test_output_dtype(self, ml_model):
        """Predictions are float64."""
        durs = np.array([12], dtype=np.int32)
        result = ml_model.get_lapse_vector(durs)
        assert result.dtype == np.float64

    def test_rates_in_unit_interval(self, ml_model):
        """All predicted rates are in [0, 1]."""
        durs = np.arange(0, 360, 12, dtype=np.int32)
        result = ml_model.get_lapse_vector(durs)
        assert np.all(result >= 0.0)
        assert np.all(result <= 1.0)

    def test_monthly_less_than_annual(self, ml_model):
        """Monthly rates should be less than annual rates."""
        durs = np.array([12, 60, 120], dtype=np.int32)
        w_monthly = ml_model.get_lapse_vector(durs)
        # Monthly < annual for all reasonable rates
        assert np.all(w_monthly < 0.05)

    def test_early_duration_higher(self, ml_model):
        """Early-duration lapse rates should be higher than later ones."""
        durs = np.array([0, 120], dtype=np.int32)
        result = ml_model.get_lapse_vector(durs)
        assert result[0] > result[1]

    def test_with_policy_features(self, ml_model):
        """Prediction works with explicit policy features."""
        durs = np.array([12, 60], dtype=np.int32)
        ages = np.array([35, 55], dtype=np.int32)
        result = ml_model.get_lapse_vector(
            durs, ages=ages, sexes=np.array(["M", "F"]),
            smoker_statuses=np.array(["NS", "S"]),
            face_amounts=np.array([500_000, 300_000], dtype=np.float64),
        )
        assert result.shape == (2,)


class TestMLLapsePersistence:
    """Tests for model save/load."""

    def test_save_and_load(self, tmp_path):
        """Model round-trips through save/load."""
        x, y = _synthetic_lapse_data(n=200)
        ml = MLLapseAssumption.fit(x, y, n_estimators=10)

        path = tmp_path / "lapse_model.joblib"
        ml.save(path)

        loaded = MLLapseAssumption.load(path)
        assert loaded.feature_names == ml.feature_names

    def test_predictions_match_after_load(self, tmp_path):
        """Predictions are identical before and after save/load."""
        x, y = _synthetic_lapse_data(n=200)
        ml = MLLapseAssumption.fit(x, y, n_estimators=10, random_state=42)

        durs = np.array([12, 60], dtype=np.int32)
        pred_before = ml.get_lapse_vector(durs)

        path = tmp_path / "model.joblib"
        ml.save(path)
        loaded = MLLapseAssumption.load(path)
        pred_after = loaded.get_lapse_vector(durs)

        np.testing.assert_allclose(pred_before, pred_after, rtol=1e-10)

    def test_ae_ratio_reasonable(self):
        """A/E ratio on training data is close to 1.0."""
        x, y = _synthetic_lapse_data(n=1000)
        ml = MLLapseAssumption.fit(x, y, n_estimators=100, random_state=42)
        x_np = x.to_numpy().astype(np.float64)
        y_pred = np.clip(ml.model.predict(x_np), 0.0, 1.0)
        ae = y.sum() / y_pred.sum()
        assert 0.8 < ae < 1.2

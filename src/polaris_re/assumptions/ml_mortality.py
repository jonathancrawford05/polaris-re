"""
MLMortalityAssumption — ML-enhanced mortality rate predictions.

Wraps a fitted scikit-learn or XGBoost pipeline to produce vectorized
mortality rate predictions that satisfy the same protocol as
``MortalityTable``, allowing ML assumptions to be used as drop-in
replacements in ``AssumptionSet``.

The key contract:
    ``get_qx_vector(ages, sex, smoker_status, durations)`` → shape (N,)
    returning monthly mortality rates in [0, 1].
"""

from datetime import date
from pathlib import Path
from typing import Self

import numpy as np
import polars as pl
from pydantic import ConfigDict, Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.utils.features import build_feature_matrix
from polaris_re.utils.interpolation import constant_force_interpolate_rates

__all__ = ["MLMortalityAssumption"]


class MLMortalityAssumption(PolarisBaseModel):
    """
    ML-enhanced mortality assumption wrapping a fitted sklearn/XGBoost model.

    Satisfies the same interface as ``MortalityTable`` so ``AssumptionSet``
    requires no changes when switching from table to ML assumptions.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    model: object = Field(description="Fitted sklearn/XGBoost estimator.", exclude=True)
    feature_names: list[str] = Field(description="Ordered feature column names used by the model.")
    model_type: str = Field(description="Model type identifier (e.g. 'xgboost', 'sklearn').")
    trained_date: date = Field(description="Date the model was trained.")
    source_description: str = Field(default="ML model", description="Description for audit trail.")

    @classmethod
    def from_trained_model(
        cls,
        model: object,
        feature_names: list[str],
        model_type: str = "sklearn",
        trained_date: date | None = None,
        source_description: str = "ML model",
    ) -> Self:
        """
        Construct from a pre-trained model.

        Args:
            model:              Fitted estimator with a ``.predict()`` method.
            feature_names:      Ordered list of feature column names.
            model_type:         Identifier string (e.g. "xgboost", "gradient_boosting").
            trained_date:       Training date (defaults to today).
            source_description: Description for audit trail.

        Returns:
            MLMortalityAssumption instance.
        """
        if trained_date is None:
            trained_date = date.today()
        return cls(
            model=model,
            feature_names=feature_names,
            model_type=model_type,
            trained_date=trained_date,
            source_description=source_description,
        )

    @classmethod
    def fit(
        cls,
        x: pl.DataFrame,
        y: np.ndarray,
        model_type: str = "gradient_boosting",
        source_description: str = "ML model",
        **model_kwargs: object,
    ) -> Self:
        """
        Train a model from features and target rates.

        Args:
            x:                  Feature DataFrame (columns become ``feature_names``).
            y:                  Target annual mortality rates, shape (N,).
            model_type:         "gradient_boosting" or "xgboost".
            source_description: Description for audit trail.
            **model_kwargs:     Passed to the model constructor.

        Returns:
            Fitted MLMortalityAssumption instance.
        """
        feature_names = list(x.columns)
        x_np = x.to_numpy().astype(np.float64)

        if model_type == "xgboost":
            from xgboost import XGBRegressor

            model = XGBRegressor(**model_kwargs)  # type: ignore[arg-type]
        else:
            from sklearn.ensemble import GradientBoostingRegressor

            model = GradientBoostingRegressor(**model_kwargs)  # type: ignore[arg-type]

        model.fit(x_np, y)  # type: ignore[union-attr]

        return cls.from_trained_model(
            model=model,
            feature_names=feature_names,
            model_type=model_type,
            source_description=source_description,
        )

    def get_qx_vector(
        self,
        ages: np.ndarray,
        sex: Sex,
        smoker_status: SmokerStatus,
        durations: np.ndarray,
        face_amounts: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Return monthly mortality rates for a vector of policies.

        Builds a feature matrix from the input args, runs prediction,
        clips to [0, 1], and converts from annual to monthly.

        Args:
            ages:          Attained ages, shape (N,), dtype int32.
            sex:           Single sex value.
            smoker_status: Single smoker status.
            durations:     Duration in select period (months), shape (N,), dtype int32.
            face_amounts:  Face amounts (optional), shape (N,). Uses $500k default.

        Returns:
            Monthly q_x rates, shape (N,), dtype float64.
        """
        n = len(ages)
        if face_amounts is None:
            face_amounts = np.full(n, 500_000.0, dtype=np.float64)

        sexes = np.array([sex.value] * n)
        smokers = np.array([smoker_status.value] * n)

        feature_df = build_feature_matrix(
            ages=ages,
            sexes=sexes,
            smoker_statuses=smokers,
            durations_months=durations,
            face_amounts=face_amounts,
        )

        # Select only the features the model was trained on
        available = [c for c in self.feature_names if c in feature_df.columns]
        x_np = feature_df.select(available).to_numpy().astype(np.float64)

        # Predict annual q_x
        q_annual = np.asarray(self.model.predict(x_np), dtype=np.float64)  # type: ignore[union-attr]

        # Clip to valid range
        q_annual = np.clip(q_annual, 0.0, 1.0)

        # Convert annual to monthly
        q_monthly = constant_force_interpolate_rates(q_annual, fraction=1.0 / 12.0)

        return q_monthly

    def save(self, path: Path) -> None:
        """
        Persist the model and metadata to disk via joblib.

        Saves a dict with keys: model, feature_names, model_type,
        trained_date, source_description.
        """
        import joblib

        data = {
            "model": self.model,
            "feature_names": self.feature_names,
            "model_type": self.model_type,
            "trained_date": self.trained_date.isoformat(),
            "source_description": self.source_description,
        }
        joblib.dump(data, path)

    @classmethod
    def load(cls, path: Path) -> Self:
        """
        Load a persisted MLMortalityAssumption from disk.

        Args:
            path: Path to the joblib file.

        Returns:
            Restored MLMortalityAssumption instance.
        """
        import joblib

        data = joblib.load(path)
        return cls(
            model=data["model"],
            feature_names=data["feature_names"],
            model_type=data["model_type"],
            trained_date=date.fromisoformat(data["trained_date"]),
            source_description=data.get("source_description", "ML model"),
        )

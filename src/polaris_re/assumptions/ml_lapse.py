"""
MLLapseAssumption — ML-enhanced lapse rate predictions.

Wraps a fitted scikit-learn or XGBoost pipeline to produce vectorized
lapse rate predictions that satisfy the same protocol as
``LapseAssumption``, allowing ML assumptions to be used as drop-in
replacements in ``AssumptionSet``.

The key contract:
    ``get_lapse_vector(durations_months)`` → shape (N,)
    returning monthly lapse rates in [0, 1].
"""

from datetime import date
from pathlib import Path
from typing import Self

import numpy as np
import polars as pl
from pydantic import ConfigDict, Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.utils.features import build_feature_matrix

__all__ = ["MLLapseAssumption"]


class MLLapseAssumption(PolarisBaseModel):
    """
    ML-enhanced lapse assumption wrapping a fitted sklearn/XGBoost model.

    Satisfies the same interface as ``LapseAssumption`` so ``AssumptionSet``
    requires no changes when switching from table to ML assumptions.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    model: object = Field(description="Fitted sklearn/XGBoost estimator.", exclude=True)
    feature_names: list[str] = Field(description="Ordered feature column names used by the model.")
    model_type: str = Field(description="Model type identifier.")
    trained_date: date = Field(description="Date the model was trained.")
    source_description: str = Field(
        default="ML lapse model", description="Description for audit trail."
    )

    @classmethod
    def from_trained_model(
        cls,
        model: object,
        feature_names: list[str],
        model_type: str = "sklearn",
        trained_date: date | None = None,
        source_description: str = "ML lapse model",
    ) -> Self:
        """Construct from a pre-trained model."""
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
        source_description: str = "ML lapse model",
        **model_kwargs: object,
    ) -> Self:
        """
        Train a model from features and target lapse rates.

        Args:
            x:                  Feature DataFrame.
            y:                  Target annual lapse rates, shape (N,).
            model_type:         "gradient_boosting" or "xgboost".
            source_description: Description for audit trail.

        Returns:
            Fitted MLLapseAssumption instance.
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

    def get_lapse_vector(
        self,
        durations_months: np.ndarray,
        ages: np.ndarray | None = None,
        sexes: np.ndarray | None = None,
        smoker_statuses: np.ndarray | None = None,
        face_amounts: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Return monthly lapse rates for a vector of policies.

        Builds a feature matrix, runs prediction, clips to [0, 1],
        and converts from annual to monthly.

        Args:
            durations_months: Duration in force (months), shape (N,), dtype int32.
            ages:             Attained ages (optional), shape (N,). Default: 40.
            sexes:            Sex values (optional), shape (N,). Default: "M".
            smoker_statuses:  Smoker statuses (optional), shape (N,). Default: "NS".
            face_amounts:     Face amounts (optional), shape (N,). Default: $500k.

        Returns:
            Monthly lapse rates, shape (N,), dtype float64.
        """
        n = len(durations_months)
        if ages is None:
            ages = np.full(n, 40, dtype=np.int32)
        if sexes is None:
            sexes = np.array(["M"] * n)
        if smoker_statuses is None:
            smoker_statuses = np.array(["NS"] * n)
        if face_amounts is None:
            face_amounts = np.full(n, 500_000.0, dtype=np.float64)

        feature_df = build_feature_matrix(
            ages=ages,
            sexes=sexes,
            smoker_statuses=smoker_statuses,
            durations_months=durations_months,
            face_amounts=face_amounts,
        )

        available = [c for c in self.feature_names if c in feature_df.columns]
        x_np = feature_df.select(available).to_numpy().astype(np.float64)

        # Predict annual lapse rate
        w_annual = np.asarray(self.model.predict(x_np), dtype=np.float64)  # type: ignore[union-attr]
        w_annual = np.clip(w_annual, 0.0, 1.0)

        # Convert annual to monthly: w_monthly = 1 - (1 - w_annual)^(1/12)
        w_monthly = 1.0 - (1.0 - w_annual) ** (1.0 / 12.0)

        return w_monthly

    def save(self, path: Path) -> None:
        """Persist the model and metadata to disk via joblib."""
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
        """Load a persisted MLLapseAssumption from disk."""
        import joblib

        data = joblib.load(path)
        return cls(
            model=data["model"],
            feature_names=data["feature_names"],
            model_type=data["model_type"],
            trained_date=date.fromisoformat(data["trained_date"]),
            source_description=data.get("source_description", "ML lapse model"),
        )

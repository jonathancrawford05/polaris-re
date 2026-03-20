"""
Feature engineering utilities for ML-enhanced actuarial assumptions.

Provides standard transformations used across mortality and lapse ML models:
age bands, duration bands, log-transformed face amounts, and a feature
matrix builder that integrates with InforceBlock.
"""

import numpy as np
import polars as pl

__all__ = [
    "add_age_bands",
    "add_duration_bands",
    "build_feature_matrix",
    "log_face_amount",
]


def add_age_bands(ages: np.ndarray, width: int = 5) -> np.ndarray:
    """
    Assign ages to bands of the given width.

    Returns the lower bound of each band:
    ``band = (age // width) * width``

    Args:
        ages:  Array of attained ages, shape (N,).
        width: Band width in years (default: 5).

    Returns:
        Array of band lower bounds, shape (N,), dtype int32.

    Examples:
        >>> add_age_bands(np.array([23, 27, 30, 45]))
        array([20, 25, 30, 45], dtype=int32)
    """
    return ((ages // width) * width).astype(np.int32)


def add_duration_bands(durations_months: np.ndarray) -> np.ndarray:
    """
    Assign durations to standard actuarial duration bands.

    Bands (in policy years):
        0 → 0-1 years
        1 → 2-5 years
        2 → 6-10 years
        3 → 11-15 years
        4 → 16+ years

    Args:
        durations_months: Duration in force in months, shape (N,).

    Returns:
        Array of band codes 0-4, shape (N,), dtype int32.
    """
    years = durations_months // 12
    bands = np.full_like(years, 4, dtype=np.int32)
    bands[years <= 1] = 0
    bands[(years >= 2) & (years <= 5)] = 1
    bands[(years >= 6) & (years <= 10)] = 2
    bands[(years >= 11) & (years <= 15)] = 3
    return bands


def log_face_amount(face_amounts: np.ndarray) -> np.ndarray:
    """
    Log-transform face amounts for ML features.

    Uses ``log(face + 1)`` to handle zero face amounts gracefully.

    Args:
        face_amounts: Face amounts in dollars, shape (N,).

    Returns:
        Log-transformed values, shape (N,), dtype float64.
    """
    return np.log(face_amounts.astype(np.float64) + 1.0)


def build_feature_matrix(
    ages: np.ndarray,
    sexes: np.ndarray,
    smoker_statuses: np.ndarray,
    durations_months: np.ndarray,
    face_amounts: np.ndarray,
) -> pl.DataFrame:
    """
    Build a standardised feature matrix from policy attributes.

    Generates both raw and engineered features suitable for ML models.

    Args:
        ages:             Attained ages, shape (N,).
        sexes:            Sex values as strings ("M"/"F"), shape (N,).
        smoker_statuses:  Smoker status strings ("S"/"NS"/"U"), shape (N,).
        durations_months: Duration in force in months, shape (N,).
        face_amounts:     Face amounts in dollars, shape (N,).

    Returns:
        Polars DataFrame with columns:
            age, age_sq, age_band, sex_male, is_smoker,
            duration_months, duration_years, duration_band,
            face_amount, log_face
    """
    ages_arr = np.asarray(ages, dtype=np.int32)
    durs_arr = np.asarray(durations_months, dtype=np.int32)
    face_arr = np.asarray(face_amounts, dtype=np.float64)

    return pl.DataFrame(
        {
            "age": ages_arr,
            "age_sq": (ages_arr**2).astype(np.int32),
            "age_band": add_age_bands(ages_arr),
            "sex_male": np.array([1 if str(s) == "M" else 0 for s in sexes], dtype=np.int32),
            "is_smoker": np.array(
                [1 if str(s) == "S" else 0 for s in smoker_statuses], dtype=np.int32
            ),
            "duration_months": durs_arr,
            "duration_years": (durs_arr // 12).astype(np.int32),
            "duration_band": add_duration_bands(durs_arr),
            "face_amount": face_arr,
            "log_face": log_face_amount(face_arr),
        }
    )

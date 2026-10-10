"""
Custom exception hierarchy for Polaris RE.

All domain-specific errors inherit from PolarisError, which allows
callers to catch all Polaris errors with a single except clause.
"""

__all__ = [
    "PolarisComputationError",
    "PolarisError",
    "PolarisRankDeficiencyWarning",
    "PolarisValidationError",
]


class PolarisError(Exception):
    """Base class for all Polaris RE exceptions."""


class PolarisValidationError(PolarisError):
    """
    Raised when a business logic validation constraint is violated.

    Examples:
    - Cession percentage outside [0, 1]
    - Projection horizon exceeds policy term
    - Mortality table does not cover the required age range
    - Negative face amounts or premiums
    """


class PolarisComputationError(PolarisError):
    """
    Raised when a numerical computation fails.

    Examples:
    - Reserve recursion produces negative reserves
    - IRR solver fails to converge
    - Overflow in present value calculation
    - Mortality rates outside [0, 1] after improvement scaling
    """


class PolarisRankDeficiencyWarning(UserWarning):
    """
    Emitted when a GAM specification contains coefficients the data cannot identify.

    Such a fit is valid and its fitted values, total edf and ``Vp``-based standard
    errors are well defined, but quantities that depend on *which* redundant
    coefficient is eliminated (per-term edf, the unconditional covariance) are not
    identified; ``mgcv`` itself does not reproduce them between runs (ADR-256).
    """

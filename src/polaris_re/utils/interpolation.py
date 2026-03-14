"""
Interpolation utilities for actuarial rate tables.

Standard methods:
1. UDD (Uniform Distribution of Deaths): linear interpolation — Phase 1 default.
2. Constant Force of Mortality: q_{x,f} = 1 - (1-q_x)^f — used for monthly conversion.
3. Balducci (Hyperbolic): not required.

Implementation Notes for Claude Code:
--------------------------------------
- linear_interpolate_rates: UDD linear blend between q_lower and q_upper.
  q_{x+f} = (1-f)*q_lower + f*q_upper, clipped to [0, 1].
- constant_force_interpolate_rates: one-liner — 1 - (1 - q_annual)^fraction.
  This is the standard conversion from annual to monthly mortality rates.

TODO (Phase 1, Milestone 1.2):
- Implement both functions (constant_force is a one-liner — do this first)
- Tests: at fraction=0 → rate=0; at fraction=1 → rate=q_annual;
         at fraction=1/12 with q=0.012 → ≈ 0.001005
"""

import numpy as np

__all__ = ["constant_force_interpolate_rates", "linear_interpolate_rates"]


def linear_interpolate_rates(
    q_lower: np.ndarray,
    q_upper: np.ndarray,
    fractions: np.ndarray,
) -> np.ndarray:
    """
    Interpolate mortality rates under UDD (linear blend).

    q_{x+f} = (1 - f) * q_lower + f * q_upper

    Args:
        q_lower:   Annual q_x at floor(age), shape (N,), dtype float64.
        q_upper:   Annual q_x at floor(age)+1, shape (N,), dtype float64.
        fractions: Fractional age in [0, 1), shape (N,), dtype float64.

    Returns:
        Interpolated annual rates, shape (N,), clipped to [0, 1].

    TODO: Implement — one vectorized expression plus np.clip.
    """
    result = (1.0 - fractions) * q_lower + fractions * q_upper
    return np.clip(result, 0.0, 1.0)


def constant_force_interpolate_rates(
    q_annual: np.ndarray,
    fraction: float,
) -> np.ndarray:
    """
    Convert annual mortality rates to sub-annual via constant force assumption.

        q_{x, fraction} = 1 - (1 - q_x)^fraction

    Used to convert annual table rates to monthly rates (fraction = 1/12).

    Args:
        q_annual: Annual mortality rates, shape (N,), dtype float64. Must be in [0, 1].
        fraction: Sub-annual fraction, e.g. 1/12 for monthly.

    Returns:
        Sub-annual rates, shape (N,), dtype float64.

    Examples:
        constant_force_interpolate_rates(np.array([0.012]), 1/12)
        → array([0.00100503])   # ≈ 0.001005

        At fraction=1.0: returns q_annual unchanged.
        At fraction=0.0: returns zeros.

    TODO: Implement — one vectorized expression: 1.0 - (1.0 - q_annual) ** fraction
    """
    return 1.0 - (1.0 - q_annual) ** fraction

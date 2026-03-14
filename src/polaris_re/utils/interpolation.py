"""
Interpolation utilities for actuarial rate tables.

Mortality tables provide rates at integer ages. For policies with
fractional ages (which is every real policy), interpolation is required.

Standard actuarial interpolation methods:
1. UDD (Uniform Distribution of Deaths): linear interpolation of q_x.
   q_{x+f} = f * q_x  for fractional age f in [0,1).
   This is the most common assumption and simplest to implement.

2. Constant Force of Mortality: exponential interpolation.
   μ_{x+f} = -ln(1 - q_x), giving q_{x+f} = 1 - (1-q_x)^f
   More theoretically defensible but slightly more complex.

3. Balducci (Hyperbolic): less common, not required for Phase 1.

Phase 1 uses UDD throughout. The method is configurable via a flag
on MortalityTable for future flexibility.

Implementation Notes for Claude Code:
--------------------------------------
- `linear_interpolate_rates` handles the UDD case for vectorized lookups.
- Input: base integer-age rates q[ages] and fractional offsets.
- Output: interpolated rates at the exact fractional age.
- Clip output to [0, 1] to prevent numerical issues at old ages (q_x near 1).

TODO (Phase 1, Milestone 1.2):
- Implement linear_interpolate_rates
- Implement constant_force_interpolate_rates (may be needed for VBT)
- Add tests verifying UDD: interpolated rate at f=0 == q_x, at f=1 == q_{x+1}
"""

from __future__ import annotations

import numpy as np

__all__ = ["linear_interpolate_rates", "constant_force_interpolate_rates"]


def linear_interpolate_rates(
    q_lower: np.ndarray,
    q_upper: np.ndarray,
    fractions: np.ndarray,
) -> np.ndarray:
    """
    Interpolate mortality rates under the UDD (Uniform Distribution of Deaths) assumption.

    Under UDD: q_{x+f} = f * q_{x+1} + (1-f) * q_x  [NOTE: this is linear interpolation]
    More precisely for UDD: the force of mortality is constant within each year of age,
    and q_{x+f} satisfies: (1 - q_{x+f}) = (1 - q_x)^(1-f) ... but for Phase 1,
    simple linear interpolation is an acceptable approximation.

    Args:
        q_lower: Annual mortality rates at floor(age), shape (N,).
        q_upper: Annual mortality rates at floor(age)+1, shape (N,).
        fractions: Fractional part of age in [0, 1), shape (N,).

    Returns:
        Interpolated annual mortality rates, shape (N,), clipped to [0, 1].

    TODO: Implement.
    """
    raise NotImplementedError("linear_interpolate_rates not yet implemented.")


def constant_force_interpolate_rates(
    q_annual: np.ndarray,
    fraction: float,
) -> np.ndarray:
    """
    Convert annual mortality rates to sub-annual rates under constant force assumption.

    Under constant force of mortality:
        q_{x, fraction} = 1 - (1 - q_x)^fraction

    This is used to convert annual table rates to monthly rates (fraction = 1/12).

    Args:
        q_annual: Annual mortality rates, shape (N,), dtype float64.
        fraction: Sub-annual fraction (e.g. 1/12 for monthly).

    Returns:
        Sub-annual mortality rates, shape (N,), dtype float64.

    Example:
        Monthly rate from annual 0.001:
        q_monthly = 1 - (1 - 0.001)^(1/12) ≈ 0.0000835

    TODO: Implement. This is a one-liner once you know the formula.
    """
    raise NotImplementedError("constant_force_interpolate_rates not yet implemented.")

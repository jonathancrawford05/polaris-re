"""
Stochastic Interest Rate Models for scenario generation.

Provides two short-rate models commonly used in life insurance and reinsurance:

**Hull-White One-Factor Model** (extended Vasicek):
    dr_t = (theta - a*r_t) dt + sigma dW_t
    - theta: drift calibrated to long-run mean reversion target (theta = a * r_mean)
    - a: mean-reversion speed (higher = faster pull to r_mean)
    - sigma: volatility of the short rate
    - Discretisation (Euler-Maruyama, monthly steps):
        r_{t+1} = r_t + a(r_mean - r_t)*dt + sigma*sqrt(dt)*Z,  Z ~ N(0,1)

**Cox-Ingersoll-Ross (CIR) Model**:
    dr_t = a*(b - r_t) dt + sigma*sqrt(r_t) dW_t
    - b: long-run mean of the short rate
    - a: mean-reversion speed
    - sigma: volatility parameter
    - Discretisation (Euler-Maruyama with positivity floor):
        r_{t+1} = max(0, r_t + a(b - r_t)*dt + sigma*sqrt(max(r_t,0)*dt)*Z)
    - Feller condition for non-negativity: 2ab > sigma^2

Both models simulate N paths of monthly short rates over T periods.
Discount factors are computed from the path using monthly compounding:
    P(0,t) = exp(-∫₀ᵗ r_s ds) ≈ ∏_{s=0}^{t-1} (1 + r_s·dt)^(-1)

References:
    Hull, J., White, A. (1990). "Pricing Interest-Rate-Derivative Securities."
    Cox, J., Ingersoll, J., Ross, S. (1985). "A Theory of the Term Structure."
"""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

__all__ = ["CIRModel", "HullWhiteModel", "RateScenarios"]


@dataclass
class RateScenarios:
    """
    Output of a stochastic short-rate simulation.

    Contains N paths of monthly short rates and derived discount factors,
    suitable for pricing interest-rate-sensitive insurance liabilities
    and for stochastic IFRS 17 discount curve generation.
    """

    model: Literal["HULL_WHITE", "CIR"]
    n_paths: int
    n_periods: int
    seed: int

    short_rates: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """Simulated annualised short rates. Shape (n_paths, n_periods)."""

    discount_factors: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    """
    Cumulative discount factors P(0, t). Shape (n_paths, n_periods).
    discount_factors[i, t] = product of (1 + r_s * dt)^(-1) for s = 0 to t.
    """

    @property
    def mean_short_rate(self) -> np.ndarray:
        """Mean short rate across paths at each time step. Shape (n_periods,)."""
        return self.short_rates.mean(axis=0)

    @property
    def std_short_rate(self) -> np.ndarray:
        """Standard deviation of short rate across paths at each time step. Shape (n_periods,)."""
        return self.short_rates.std(axis=0)

    def path_pv(self, cash_flows: np.ndarray) -> np.ndarray:
        """
        Present value of a deterministic cash flow vector under each path.

        Uses the path-specific discount factors for stochastic discounting.

        Args:
            cash_flows: Shape (n_periods,) array of cash flows (one per period).

        Returns:
            Shape (n_paths,) array of PV under each simulated rate path.
        """
        if len(cash_flows) != self.n_periods:
            raise ValueError(f"cash_flows length {len(cash_flows)} != n_periods {self.n_periods}")
        # discount_factors[i, t] = P(0, t+1), so PV = sum_t CF[t] * P(0, t+1)
        return (self.discount_factors * cash_flows[np.newaxis, :]).sum(axis=1)

    def pv_percentile(self, cash_flows: np.ndarray, pct: float) -> float:
        """
        Percentile of the PV distribution across all paths.

        Args:
            cash_flows: Shape (n_periods,) cash flow vector.
            pct: Percentile in [0, 100].

        Returns:
            Scalar percentile value.
        """
        pvs = self.path_pv(cash_flows)
        return float(np.percentile(pvs, pct))

    def terminal_discount_factor(self) -> np.ndarray:
        """
        Discount factor to the end of the projection horizon, P(0, T). Shape (n_paths,).
        """
        return self.discount_factors[:, -1]


class HullWhiteModel:
    """
    Hull-White one-factor (extended Vasicek) short-rate model.

    Generates stochastic interest rate paths via Euler-Maruyama discretisation
    of the SDE: dr_t = a(r_mean - r_t) dt + sigma dW_t

    The model is mean-reverting: rates are pulled toward r_mean at speed a.
    The drift term ensures E[r_t] → r_mean as t → ∞.

    Args:
        r0:       Initial short rate (annualised). Default 0.04.
        r_mean:   Long-run mean reversion target. Default 0.04.
        a:        Mean reversion speed. Typical range 0.01-0.30. Default 0.10.
        sigma:    Short rate volatility. Typical range 0.005-0.02. Default 0.01.
        n_paths:  Number of Monte Carlo paths. Default 1000.
        seed:     Random seed for reproducibility. Default 42.
    """

    def __init__(
        self,
        r0: float = 0.04,
        r_mean: float = 0.04,
        a: float = 0.10,
        sigma: float = 0.01,
        n_paths: int = 1000,
        seed: int = 42,
    ) -> None:
        self.r0 = r0
        self.r_mean = r_mean
        self.a = a
        self.sigma = sigma
        self.n_paths = n_paths
        self.seed = seed

    def simulate(self, n_periods: int) -> RateScenarios:
        """
        Simulate Hull-White short rate paths.

        Args:
            n_periods: Number of monthly time steps to simulate.

        Returns:
            RateScenarios with simulated rates and discount factors.
        """
        rng = np.random.default_rng(self.seed)
        dt = 1.0 / 12.0  # monthly step
        sqrt_dt = np.sqrt(dt)

        # Shape: (n_paths, n_periods)
        rates = np.zeros((self.n_paths, n_periods), dtype=np.float64)
        rates[:, 0] = self.r0

        # Vectorised path simulation over all paths simultaneously
        z_norm = rng.standard_normal((self.n_paths, n_periods - 1))
        for t in range(1, n_periods):
            r_prev = rates[:, t - 1]
            drift = self.a * (self.r_mean - r_prev) * dt
            diffusion = self.sigma * sqrt_dt * z_norm[:, t - 1]
            rates[:, t] = r_prev + drift + diffusion

        # Compute cumulative discount factors: P(0, t+1) = ∏_{s=0}^{t} (1 + r_s·dt)^(-1)
        # Using monthly compounding: (1 + r_annual / 12)^(-1)
        monthly_rates = rates * dt  # r * (1/12) ≈ monthly rate
        discount_factors = np.cumprod(1.0 / (1.0 + monthly_rates), axis=1)

        return RateScenarios(
            model="HULL_WHITE",
            n_paths=self.n_paths,
            n_periods=n_periods,
            seed=self.seed,
            short_rates=rates,
            discount_factors=discount_factors,
        )


class CIRModel:
    """
    Cox-Ingersoll-Ross (CIR) short-rate model.

    Generates stochastic interest rate paths via Euler-Maruyama discretisation
    of the SDE: dr_t = a(b - r_t) dt + sigma*sqrt(r_t) dW_t

    Key properties:
    - Mean-reverting toward b at speed a
    - Volatility is proportional to √r, preventing negative rates (probabilistically)
    - Feller condition for guaranteed non-negativity: 2ab > σ²

    Args:
        r0:       Initial short rate (annualised). Default 0.04.
        b:        Long-run mean (reversion target). Default 0.04.
        a:        Mean reversion speed. Typical range 0.05-0.50. Default 0.15.
        sigma:    Volatility parameter. Typical range 0.01-0.10. Default 0.02.
        n_paths:  Number of Monte Carlo paths. Default 1000.
        seed:     Random seed for reproducibility. Default 42.
    """

    def __init__(
        self,
        r0: float = 0.04,
        b: float = 0.04,
        a: float = 0.15,
        sigma: float = 0.02,
        n_paths: int = 1000,
        seed: int = 42,
    ) -> None:
        self.r0 = r0
        self.b = b
        self.a = a
        self.sigma = sigma
        self.n_paths = n_paths
        self.seed = seed

        # Warn if Feller condition is violated (rates may go negative)
        if 2.0 * a * b <= sigma**2:
            import warnings

            warnings.warn(
                f"CIR Feller condition violated: 2ab={2 * a * b:.4f} <= sigma^2={sigma**2:.4f}. "
                "Rates may become negative. Consider increasing a or b, or decreasing sigma.",
                stacklevel=2,
            )

    def simulate(self, n_periods: int) -> RateScenarios:
        """
        Simulate CIR short rate paths.

        Args:
            n_periods: Number of monthly time steps to simulate.

        Returns:
            RateScenarios with simulated rates and discount factors.
        """
        rng = np.random.default_rng(self.seed)
        dt = 1.0 / 12.0

        rates = np.zeros((self.n_paths, n_periods), dtype=np.float64)
        rates[:, 0] = self.r0

        z_norm = rng.standard_normal((self.n_paths, n_periods - 1))
        for t in range(1, n_periods):
            r_prev = rates[:, t - 1]
            r_pos = np.maximum(r_prev, 0.0)  # floor for diffusion term
            drift = self.a * (self.b - r_prev) * dt
            diffusion = self.sigma * np.sqrt(r_pos * dt) * z_norm[:, t - 1]
            rates[:, t] = np.maximum(r_prev + drift + diffusion, 0.0)

        # Cumulative discount factors
        monthly_rates = rates * dt
        discount_factors = np.cumprod(1.0 / (1.0 + monthly_rates), axis=1)

        return RateScenarios(
            model="CIR",
            n_paths=self.n_paths,
            n_periods=n_periods,
            seed=self.seed,
            short_rates=rates,
            discount_factors=discount_factors,
        )

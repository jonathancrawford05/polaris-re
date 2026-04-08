"""
MonteCarloUQ — Monte Carlo uncertainty quantification for reinsurance deal pricing.

Samples from distributions of key assumption parameters and runs the full
pricing pipeline (product projection → treaty → profit test) for each scenario.
Collects the distribution of PV profits, IRR, and profit margin.

Parameter distributions:
    mortality_multiplier  ~ LogNormal(mean=0, sigma=mortality_log_sigma)
                            mean of ~1.0; CV = mortality_log_sigma ≈ 10%
    lapse_multiplier      ~ LogNormal(mean=0, sigma=lapse_log_sigma)
                            mean of ~1.0; CV = lapse_log_sigma ≈ 15%
    rate_shift            ~ Normal(0, interest_rate_sigma)
                            additive annual discount rate shift (e.g. ±50bps)

Reproducibility: all sampling uses np.random.default_rng(seed).

Performance note: For N=1000 scenarios, runtime scales with N * projection cost.
Large blocks or long horizons may be slow. Use @pytest.mark.slow for N > 100.
"""

from dataclasses import dataclass

import numpy as np

from polaris_re.analytics.profit_test import ProfitTester, ProfitTestResult
from polaris_re.analytics.scenario import ScenarioAdjustment, _apply_scenario
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["MonteCarloUQ", "UQParameters", "UQResult"]


@dataclass
class UQParameters:
    """
    Distribution parameters for Monte Carlo assumption sampling.

    All sigmas are standard deviations of the underlying distributions.
    """

    mortality_log_sigma: float = 0.10
    """LogNormal sigma for mortality multiplier. Gives ~10% coefficient of variation."""

    lapse_log_sigma: float = 0.15
    """LogNormal sigma for lapse multiplier. Gives ~15% coefficient of variation."""

    interest_rate_sigma: float = 0.005
    """Normal standard deviation for annual discount rate additive shift (50 bps 1-sigma)."""


@dataclass
class UQResult:
    """
    Results from a Monte Carlo UQ run.

    All arrays have length n_scenarios.
    """

    n_scenarios: int
    seed: int

    pv_profits: np.ndarray
    """Present value of profits under each scenario, shape (n_scenarios,)."""

    irrs: np.ndarray
    """IRR under each scenario, shape (n_scenarios,). NaN where solver fails."""

    profit_margins: np.ndarray
    """PV profit margin under each scenario, shape (n_scenarios,)."""

    base_pv_profit: float
    """PV profit from the base (unperturbed) scenario."""

    base_irr: float | None
    """IRR from the base (unperturbed) scenario."""

    mort_multipliers: np.ndarray
    """Sampled mortality multipliers, shape (n_scenarios,)."""

    lapse_multipliers: np.ndarray
    """Sampled lapse multipliers, shape (n_scenarios,)."""

    rate_shifts: np.ndarray
    """Sampled interest rate shifts, shape (n_scenarios,)."""

    def percentile(self, pct: float) -> dict[str, float]:
        """
        Return percentile values for key metrics.

        Args:
            pct: Percentile in [0, 100].

        Returns:
            Dict with keys 'pv_profit', 'irr', 'profit_margin'.
        """
        valid_irrs = self.irrs[~np.isnan(self.irrs)]
        return {
            "pv_profit": float(np.percentile(self.pv_profits, pct)),
            "irr": float(np.percentile(valid_irrs, pct)) if len(valid_irrs) > 0 else float("nan"),
            "profit_margin": float(np.percentile(self.profit_margins, pct)),
        }

    def var(self, confidence: float = 0.95) -> float:
        """
        Value at Risk: worst PV profit at the given confidence level.

        VaR_95 = 5th percentile of PV profits (lower = more adverse).

        Args:
            confidence: Confidence level, e.g. 0.95 for 95% VaR.

        Returns:
            VaR as a dollar value (negative means loss).
        """
        return float(np.percentile(self.pv_profits, (1.0 - confidence) * 100.0))

    def cvar(self, confidence: float = 0.95) -> float:
        """
        Conditional Value at Risk (Expected Shortfall): mean PV profit
        in the worst (1 - confidence) fraction of scenarios.

        Args:
            confidence: Confidence level, e.g. 0.95 for 95% CVaR.

        Returns:
            CVaR as a dollar value.
        """
        threshold = self.var(confidence)
        tail = self.pv_profits[self.pv_profits <= threshold]
        return float(tail.mean()) if len(tail) > 0 else threshold


class MonteCarloUQ:
    """
    Runs Monte Carlo uncertainty quantification on a reinsurance deal.

    Samples assumption multipliers from parametric distributions and runs
    the full projection pipeline for each scenario.

    Args:
        inforce:          Inforce block to project.
        base_assumptions: Base AssumptionSet (will be perturbed per scenario).
        base_config:      Base ProjectionConfig (discount_rate will be perturbed).
        treaty:           Reinsurance treaty to apply (or None for gross basis).
        hurdle_rate:      Annual hurdle rate for profit testing.
        n_scenarios:      Number of Monte Carlo scenarios. Default 1000.
        seed:             Random seed for reproducibility. Default 42.
        params:           Distribution parameters. Default UQParameters().
    """

    def __init__(
        self,
        inforce: InforceBlock,
        base_assumptions: AssumptionSet,
        base_config: ProjectionConfig,
        treaty: BaseTreaty | None,
        hurdle_rate: float,
        n_scenarios: int = 1000,
        seed: int = 42,
        params: UQParameters | None = None,
    ) -> None:
        self.inforce = inforce
        self.base_assumptions = base_assumptions
        self.base_config = base_config
        self.treaty = treaty
        self.hurdle_rate = hurdle_rate
        self.n_scenarios = n_scenarios
        self.seed = seed
        self.params = params or UQParameters()

    def _run_single(
        self,
        assumptions: AssumptionSet,
        config: ProjectionConfig,
    ) -> ProfitTestResult:
        """Run one scenario through the full pipeline and return ProfitTestResult."""
        product = get_product_engine(
            inforce=self.inforce,
            assumptions=assumptions,
            config=config,
        )
        gross = product.project()

        if self.treaty is not None:
            _net, _ = self.treaty.apply(gross)
            cashflows = _net
        else:
            cashflows = gross

        tester = ProfitTester(cashflows=cashflows, hurdle_rate=self.hurdle_rate)
        return tester.run()

    def _make_config(self, rate_shift: float) -> ProjectionConfig:
        """Create a ProjectionConfig with a shifted discount rate."""
        new_rate = max(0.0, self.base_config.discount_rate + rate_shift)
        return ProjectionConfig(
            valuation_date=self.base_config.valuation_date,
            projection_horizon_years=self.base_config.projection_horizon_years,
            discount_rate=new_rate,
            valuation_interest_rate=self.base_config.valuation_interest_rate,
        )

    def run(self) -> UQResult:
        """
        Run all Monte Carlo scenarios and return UQResult.

        Returns:
            UQResult with distributions of PV profits, IRRs, margins.
        """
        rng = np.random.default_rng(self.seed)
        n = self.n_scenarios
        p = self.params

        # Sample assumption parameters
        mort_multipliers = rng.lognormal(mean=0.0, sigma=p.mortality_log_sigma, size=n)
        lapse_multipliers = rng.lognormal(mean=0.0, sigma=p.lapse_log_sigma, size=n)
        rate_shifts = rng.normal(0.0, p.interest_rate_sigma, size=n)

        # Base case (no perturbation)
        base_result = self._run_single(self.base_assumptions, self.base_config)
        base_pv_profit = base_result.pv_profits
        base_irr = base_result.irr

        pv_profits = np.zeros(n, dtype=np.float64)
        irrs = np.full(n, np.nan, dtype=np.float64)
        profit_margins = np.zeros(n, dtype=np.float64)

        for i in range(n):
            scenario = ScenarioAdjustment(
                name=f"MC_{i}",
                mortality_multiplier=float(mort_multipliers[i]),
                lapse_multiplier=float(lapse_multipliers[i]),
            )
            scenario_assumptions = _apply_scenario(self.base_assumptions, scenario)
            scenario_config = self._make_config(float(rate_shifts[i]))

            result = self._run_single(scenario_assumptions, scenario_config)
            pv_profits[i] = result.pv_profits
            if result.irr is not None:
                irrs[i] = result.irr
            profit_margins[i] = result.profit_margin

        return UQResult(
            n_scenarios=n,
            seed=self.seed,
            pv_profits=pv_profits,
            irrs=irrs,
            profit_margins=profit_margins,
            base_pv_profit=base_pv_profit,
            base_irr=base_irr,
            mort_multipliers=mort_multipliers,
            lapse_multipliers=lapse_multipliers,
            rate_shifts=rate_shifts,
        )

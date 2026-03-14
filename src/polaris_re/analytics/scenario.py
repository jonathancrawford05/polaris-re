"""
ScenarioRunner — runs a projection under multiple assumption scenarios
for sensitivity analysis and stress testing.

Implementation Notes for Claude Code:
--------------------------------------
SCENARIO ADJUSTMENT:
    A ScenarioAdjustment specifies multiplicative changes to a base AssumptionSet.
    mortality_multiplier=1.10 means all q_x rates × 1.10 (10% adverse mortality).
    lapse_multiplier=0.80 means all lapse rates × 0.80 (20% lower lapses).

HOW TO APPLY A MULTIPLIER:
    The AssumptionSet is frozen (immutable). To apply a scenario:
    1. Build a new LapseAssumption with select_rates and ultimate_rate scaled.
    2. Wrap the original MortalityTable in a thin proxy that scales get_qx_vector
       output, OR create a new MortalityTable with scaled rate arrays.
    3. Construct a new AssumptionSet with version = f"{base.version}_{scenario.name}".

STANDARD STRESS SCENARIOS:
    BASE, MORT_110, MORT_90, LAPSE_80, LAPSE_120, MORT_110_LAPSE_80.
    Available via ScenarioRunner.standard_stress_scenarios() classmethod.

TODO (Phase 1, Milestone 1.5):
- Implement ScenarioRunner.run()
- Standard scenarios work out of the box when called with no arguments
- Tests: verify BASE scenario matches direct ProfitTester run
"""

from dataclasses import dataclass, field

from polaris_re.analytics.profit_test import ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["ScenarioRunner", "ScenarioResult", "ScenarioAdjustment"]


@dataclass
class ScenarioAdjustment:
    """Multiplicative adjustments to a base AssumptionSet."""

    name: str
    mortality_multiplier: float = 1.0
    lapse_multiplier: float = 1.0
    description: str = ""


@dataclass
class ScenarioResult:
    """Aggregated results from a multi-scenario run."""

    scenarios: list[tuple[str, ProfitTestResult]] = field(default_factory=list)

    def irr_range(self) -> tuple[float | None, float | None]:
        """(min IRR, max IRR) across scenarios with valid IRRs."""
        irrs = [r.irr for _, r in self.scenarios if r.irr is not None]
        return (min(irrs), max(irrs)) if irrs else (None, None)

    def worst_case(self) -> tuple[str, ProfitTestResult] | None:
        """Scenario with the lowest IRR."""
        valid = [(n, r) for n, r in self.scenarios if r.irr is not None]
        return min(valid, key=lambda x: x[1].irr) if valid else None  # type: ignore[return-value]

    def base_case(self) -> ProfitTestResult | None:
        """The BASE scenario result, if present."""
        for name, result in self.scenarios:
            if name == "BASE":
                return result
        return None


class ScenarioRunner:
    """
    Runs a product + treaty projection under multiple assumption scenarios.

    Args:
        inforce: The inforce block to project.
        base_assumptions: Base AssumptionSet to adjust per scenario.
        config: Projection configuration.
        treaty: Reinsurance treaty to apply after each projection.
        hurdle_rate: Annual hurdle rate for profit testing.
    """

    def __init__(
        self,
        inforce: InforceBlock,
        base_assumptions: AssumptionSet,
        config: ProjectionConfig,
        treaty: BaseTreaty,
        hurdle_rate: float,
    ) -> None:
        self.inforce = inforce
        self.base_assumptions = base_assumptions
        self.config = config
        self.treaty = treaty
        self.hurdle_rate = hurdle_rate

    @classmethod
    def standard_stress_scenarios(cls) -> list[ScenarioAdjustment]:
        """Standard North American life reinsurance stress test scenarios."""
        return [
            ScenarioAdjustment("BASE",              1.00, 1.00, "Base case"),
            ScenarioAdjustment("MORT_110",          1.10, 1.00, "10% adverse mortality"),
            ScenarioAdjustment("MORT_90",           0.90, 1.00, "10% favourable mortality"),
            ScenarioAdjustment("LAPSE_80",          1.00, 0.80, "20% lower lapses (more exposure)"),
            ScenarioAdjustment("LAPSE_120",         1.00, 1.20, "20% higher lapses"),
            ScenarioAdjustment("MORT_110_LAPSE_80", 1.10, 0.80, "Combined adverse scenario"),
        ]

    def run(
        self,
        scenarios: list[ScenarioAdjustment] | None = None,
    ) -> ScenarioResult:
        """
        Run all scenarios and return a ScenarioResult.

        Args:
            scenarios: Scenarios to run. Defaults to standard_stress_scenarios().

        Returns:
            ScenarioResult with profit metrics for each scenario.

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "ScenarioRunner.run() not yet implemented. "
            "See module docstring for how to apply multipliers to a frozen AssumptionSet."
        )

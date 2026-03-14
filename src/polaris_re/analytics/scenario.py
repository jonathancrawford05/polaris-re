"""
ScenarioRunner — runs a projection under multiple assumption scenarios.

Enables sensitivity analysis and stress testing by applying multiplicative
or additive adjustments to a base AssumptionSet and collecting the resulting
profit metrics across all scenarios.

Implementation Notes for Claude Code:
--------------------------------------
SCENARIO ADJUSTMENT MODEL:
    A ScenarioAdjustment specifies how to modify a base AssumptionSet:
        - mortality_multiplier: float (e.g. 1.10 = 10% adverse mortality)
        - lapse_multiplier: float (e.g. 0.80 = 20% lower lapses)
    Each multiplier is applied to the relevant assumption arrays at projection time.

SCENARIO RESULT:
    ScenarioResult stores a list of (scenario_name, ProfitTestResult) pairs.
    It provides convenience methods for extracting the IRR distribution,
    identifying the worst-case scenario, and summarising results as a table.

STANDARD STRESS SCENARIOS (implement as named presets):
    "BASE"              — no adjustments (multipliers = 1.0)
    "MORT_110"          — mortality × 1.10
    "MORT_90"           — mortality × 0.90
    "LAPSE_80"          — lapse × 0.80 (lower lapses = more exposure)
    "LAPSE_120"         — lapse × 1.20
    "MORT_110_LAPSE_80" — combined adverse scenario

TODO (Phase 1, Milestone 1.5):
- Implement ScenarioAdjustment dataclass
- Implement ScenarioResult dataclass with summary methods
- Implement ScenarioRunner.run() — iterates over scenarios, runs full projection each time
- Add standard scenario presets as class method ScenarioRunner.standard_stress_scenarios()
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from polaris_re.analytics.profit_test import ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.reinsurance.base_treaty import BaseTreaty

__all__ = ["ScenarioRunner", "ScenarioResult", "ScenarioAdjustment"]


@dataclass
class ScenarioAdjustment:
    """Defines multiplicative adjustments to a base AssumptionSet."""

    name: str
    mortality_multiplier: float = 1.0
    lapse_multiplier: float = 1.0
    description: str = ""


@dataclass
class ScenarioResult:
    """Results from a multi-scenario run."""

    scenarios: list[tuple[str, ProfitTestResult]] = field(default_factory=list)

    def irr_range(self) -> tuple[float | None, float | None]:
        """(min IRR, max IRR) across all scenarios with valid IRRs."""
        irrs = [r.irr for _, r in self.scenarios if r.irr is not None]
        return (min(irrs), max(irrs)) if irrs else (None, None)

    def worst_case(self) -> tuple[str, ProfitTestResult] | None:
        """Scenario with the lowest IRR."""
        valid = [(n, r) for n, r in self.scenarios if r.irr is not None]
        return min(valid, key=lambda x: x[1].irr) if valid else None  # type: ignore[return-value]

    def base_case(self) -> ProfitTestResult | None:
        """Return the BASE scenario result, if present."""
        for name, result in self.scenarios:
            if name == "BASE":
                return result
        return None


class ScenarioRunner:
    """
    Runs a product + treaty projection under multiple assumption scenarios.

    Args:
        inforce: The inforce block to project.
        base_assumptions: The base AssumptionSet to adjust per scenario.
        config: Projection configuration.
        treaty: The reinsurance treaty to apply after each projection.
        hurdle_rate: Hurdle rate for profit testing.
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
        """Return the standard set of stress test scenarios."""
        return [
            ScenarioAdjustment("BASE", 1.0, 1.0, "Base case — no adjustments"),
            ScenarioAdjustment("MORT_110", 1.10, 1.0, "10% adverse mortality"),
            ScenarioAdjustment("MORT_90", 0.90, 1.0, "10% favourable mortality"),
            ScenarioAdjustment("LAPSE_80", 1.0, 0.80, "20% lower lapses (more exposure)"),
            ScenarioAdjustment("LAPSE_120", 1.0, 1.20, "20% higher lapses"),
            ScenarioAdjustment("MORT_110_LAPSE_80", 1.10, 0.80, "Combined adverse scenario"),
        ]

    def run(
        self,
        scenarios: list[ScenarioAdjustment] | None = None,
    ) -> ScenarioResult:
        """
        Run all scenarios and return a ScenarioResult.

        Args:
            scenarios: List of ScenarioAdjustment to run. Defaults to standard_stress_scenarios().

        Returns:
            ScenarioResult containing profit metrics for each scenario.

        TODO: Implement per module docstring.
        """
        raise NotImplementedError(
            "ScenarioRunner.run() not yet implemented. "
            "See module docstring for implementation spec."
        )

"""
ScenarioRunner - runs a projection under multiple assumption scenarios
for sensitivity analysis and stress testing.

A ScenarioAdjustment specifies multiplicative changes to a base AssumptionSet.
mortality_multiplier=1.10 means all q_x rates * 1.10 (10% adverse mortality).
lapse_multiplier=0.80 means all lapse rates * 0.80 (20% lower lapses).

Standard stress scenarios:
    BASE, MORT_110, MORT_90, LAPSE_80, LAPSE_120, MORT_110_LAPSE_80.
"""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from polaris_re.analytics.profit_test import ProfitTester, ProfitTestResult
from polaris_re.assumptions.assumption_set import AssumptionSet
from polaris_re.assumptions.lapse import LapseAssumption
from polaris_re.assumptions.mortality import MortalityTable
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.inforce import InforceBlock
from polaris_re.core.projection import ProjectionConfig
from polaris_re.pipeline import ceded_to_reinsurer_view
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.base_treaty import BaseTreaty
from polaris_re.utils.table_io import MortalityTableArray

__all__ = [
    "Perspective",
    "ScenarioAdjustment",
    "ScenarioResult",
    "ScenarioRunner",
    "apply_scenario_to_assumptions",
    "select_perspective_cashflows",
]

type Perspective = Literal["reinsurer", "cedant"]
"""Whose profit position a runner reports.

- ``"reinsurer"`` — the ceded cash flows re-viewed as NET (the reinsurer's
  own economics), matching what ``polaris price`` reports. Correct primary
  surface for a reinsurer-facing tool.
- ``"cedant"`` — the cedant's retained ``net`` position (``treaty.apply()[0]``).
"""

_VALID_PERSPECTIVES: tuple[Perspective, ...] = ("reinsurer", "cedant")


def select_perspective_cashflows(
    perspective: Perspective,
    net: CashFlowResult,
    ceded: CashFlowResult | None,
) -> CashFlowResult:
    """Pick the cash flows to profit-test for a given reporting perspective.

    ``"reinsurer"`` returns ``ceded_to_reinsurer_view(ceded)`` — the ceded
    portion re-labelled NET so ``ProfitTester`` accepts it (ADR-039). When
    ``ceded is None`` (no treaty), the reinsurer view is undefined, so the
    ``net`` cash flows (which equal ``gross`` in that case) are returned
    unchanged. ``"cedant"`` always returns ``net``.
    """
    if perspective == "reinsurer" and ceded is not None:
        return ceded_to_reinsurer_view(ceded)
    return net


def _validate_perspective(perspective: str) -> Perspective:
    if perspective not in _VALID_PERSPECTIVES:
        raise PolarisValidationError(
            f"Unknown perspective {perspective!r}. Choose one of {', '.join(_VALID_PERSPECTIVES)}."
        )
    return perspective  # type: ignore[return-value]


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
    perspective: Perspective = "cedant"
    """Whose profit position these results describe (ADR-077)."""

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


def _scale_mortality(base_mortality: MortalityTable, multiplier: float) -> MortalityTable:
    """Create a new MortalityTable with scaled rate arrays."""
    if multiplier == 1.0:
        return base_mortality

    scaled_tables: dict[str, MortalityTableArray] = {}
    for key, table_array in base_mortality.tables.items():
        scaled_rates = np.clip(table_array.rates * multiplier, 0.0, 1.0)
        scaled_tables[key] = MortalityTableArray(
            rates=scaled_rates,
            min_age=table_array.min_age,
            max_age=table_array.max_age,
            select_period=table_array.select_period,
            source_file=table_array.source_file,
        )

    return MortalityTable(
        source=base_mortality.source,
        table_name=base_mortality.table_name,
        min_age=base_mortality.min_age,
        max_age=base_mortality.max_age,
        select_period_years=base_mortality.select_period_years,
        has_smoker_distinct_rates=base_mortality.has_smoker_distinct_rates,
        tables=scaled_tables,
    )


def _scale_lapse(base_lapse: LapseAssumption, multiplier: float) -> LapseAssumption:
    """Create a new LapseAssumption with scaled rates."""
    if multiplier == 1.0:
        return base_lapse

    scaled_select = tuple(min(r * multiplier, 1.0) for r in base_lapse.select_rates)
    scaled_ultimate = min(base_lapse.ultimate_rate * multiplier, 1.0)

    return LapseAssumption(
        select_rates=scaled_select,
        ultimate_rate=scaled_ultimate,
        select_period_years=base_lapse.select_period_years,
    )


def apply_scenario_to_assumptions(
    base_assumptions: AssumptionSet, scenario: ScenarioAdjustment
) -> AssumptionSet:
    """Return a new ``AssumptionSet`` with the scenario's multiplicative
    adjustments applied to the mortality and lapse components.

    The base assumptions are not mutated. The returned set carries a
    ``version`` suffixed with the scenario name so downstream consumers can
    tell which scenario produced it. Other fields (``effective_date``,
    ``notes``) are copied through unchanged.
    """
    scaled_mortality = _scale_mortality(base_assumptions.mortality, scenario.mortality_multiplier)
    scaled_lapse = _scale_lapse(base_assumptions.lapse, scenario.lapse_multiplier)
    return AssumptionSet(
        mortality=scaled_mortality,
        lapse=scaled_lapse,
        version=f"{base_assumptions.version}_{scenario.name}",
        effective_date=base_assumptions.effective_date,
        notes=base_assumptions.notes,
    )


class ScenarioRunner:
    """
    Runs a product + treaty projection under multiple assumption scenarios.

    Args:
        inforce: The inforce block to project.
        base_assumptions: Base AssumptionSet to adjust per scenario.
        config: Projection configuration.
        treaty: Reinsurance treaty to apply after each projection.
        hurdle_rate: Annual hurdle rate for profit testing.
        perspective: Whose profit position to report (ADR-077). ``"cedant"``
            (default) profit-tests the retained ``net`` position — the
            pre-ADR-077 behaviour. ``"reinsurer"`` profit-tests the ceded
            cash flows re-viewed as NET, matching ``polaris price``.
    """

    def __init__(
        self,
        inforce: InforceBlock,
        base_assumptions: AssumptionSet,
        config: ProjectionConfig,
        treaty: BaseTreaty,
        hurdle_rate: float,
        perspective: Perspective = "cedant",
    ) -> None:
        self.inforce = inforce
        self.base_assumptions = base_assumptions
        self.config = config
        self.treaty = treaty
        self.hurdle_rate = hurdle_rate
        self.perspective: Perspective = _validate_perspective(perspective)

    @classmethod
    def standard_stress_scenarios(cls) -> list[ScenarioAdjustment]:
        """Standard North American life reinsurance stress test scenarios."""
        return [
            ScenarioAdjustment("BASE", 1.00, 1.00, "Base case"),
            ScenarioAdjustment("MORT_110", 1.10, 1.00, "10% adverse mortality"),
            ScenarioAdjustment("MORT_90", 0.90, 1.00, "10% favourable mortality"),
            ScenarioAdjustment("LAPSE_80", 1.00, 0.80, "20% lower lapses (more exposure)"),
            ScenarioAdjustment("LAPSE_120", 1.00, 1.20, "20% higher lapses"),
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
        """
        if scenarios is None:
            scenarios = self.standard_stress_scenarios()

        result = ScenarioResult(perspective=self.perspective)

        # A tabular YRT treaty (``yrt_rate_table`` set) looks rates up per
        # policy and so requires a seriatim projection plus the InforceBlock
        # passed into ``apply`` (mirrors ``cli._price_single_cohort``). For a
        # flat/proportional treaty ``needs_seriatim`` is False, so both calls
        # below are byte-identical to the pre-ADR-076 aggregate path.
        needs_seriatim = getattr(self.treaty, "yrt_rate_table", None) is not None

        for scenario in scenarios:
            # Apply scenario adjustments to create a new AssumptionSet
            adjusted_assumptions = apply_scenario_to_assumptions(self.base_assumptions, scenario)

            # Run projection with adjusted assumptions
            engine = get_product_engine(self.inforce, adjusted_assumptions, self.config)
            gross = engine.project(seriatim=needs_seriatim)

            # Apply treaty
            if needs_seriatim:
                net, ceded = self.treaty.apply(gross, inforce=self.inforce)
            else:
                net, ceded = self.treaty.apply(gross)

            # Select the reporting perspective (ADR-077): cedant net (default)
            # or the reinsurer's ceded-as-net view.
            cashflows = select_perspective_cashflows(self.perspective, net, ceded)

            # Profit test
            tester = ProfitTester(cashflows, self.hurdle_rate)
            profit_result = tester.run()

            result.scenarios.append((scenario.name, profit_result))

        return result

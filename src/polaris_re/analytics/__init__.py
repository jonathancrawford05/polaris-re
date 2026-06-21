"""
Analytics engines for Polaris RE — profit testing, scenario analysis, UQ, IFRS 17,
stochastic rates, experience studies, and rate schedule generation.
"""

from polaris_re.analytics.capital import CapitalResult, LICATCapital, LICATFactors
from polaris_re.analytics.capital_base import CapitalModel, CapitalSchedule
from polaris_re.analytics.experience_study import AEResult, ExperienceStudy
from polaris_re.analytics.ifrs17 import (
    IFRS17Cohort,
    IFRS17CohortManager,
    IFRS17ComponentMovement,
    IFRS17ContractInput,
    IFRS17Measurement,
    IFRS17MovementRow,
    IFRS17MovementTable,
    IFRS17Result,
    build_movement_table,
)
from polaris_re.analytics.portfolio import (
    Deal,
    DealResult,
    Portfolio,
    PortfolioResult,
    PortfolioResultWithCapital,
    PortfolioScenarioResult,
)
from polaris_re.analytics.premium_sufficiency import (
    PremiumSufficiencyResult,
    PremiumSufficiencyTester,
)
from polaris_re.analytics.pricing import NetPremiumCalculator, NetPremiumResult
from polaris_re.analytics.profit_test import (
    ProfitResultWithCapital,
    ProfitTester,
    ProfitTestResult,
)
from polaris_re.analytics.rate_schedule import SolveMode, YRTRateSchedule
from polaris_re.analytics.rbc import RBCCapital, RBCFactors, RBCResult
from polaris_re.analytics.scenario import (
    ScenarioAdjustment,
    ScenarioResult,
    ScenarioRunner,
    apply_scenario_to_assumptions,
)
from polaris_re.analytics.stochastic import CIRModel, HullWhiteModel, RateScenarios
from polaris_re.analytics.uq import MonteCarloUQ, UQParameters, UQResult

__all__ = [
    "AEResult",
    "CIRModel",
    "CapitalModel",
    "CapitalResult",
    "CapitalSchedule",
    "Deal",
    "DealResult",
    "ExperienceStudy",
    "HullWhiteModel",
    "IFRS17Cohort",
    "IFRS17CohortManager",
    "IFRS17ComponentMovement",
    "IFRS17ContractInput",
    "IFRS17Measurement",
    "IFRS17MovementRow",
    "IFRS17MovementTable",
    "IFRS17Result",
    "LICATCapital",
    "LICATFactors",
    "MonteCarloUQ",
    "NetPremiumCalculator",
    "NetPremiumResult",
    "Portfolio",
    "PortfolioResult",
    "PortfolioResultWithCapital",
    "PortfolioScenarioResult",
    "PremiumSufficiencyResult",
    "PremiumSufficiencyTester",
    "ProfitResultWithCapital",
    "ProfitTestResult",
    "ProfitTester",
    "RBCCapital",
    "RBCFactors",
    "RBCResult",
    "RateScenarios",
    "ScenarioAdjustment",
    "ScenarioResult",
    "ScenarioRunner",
    "SolveMode",
    "UQParameters",
    "UQResult",
    "YRTRateSchedule",
    "apply_scenario_to_assumptions",
    "build_movement_table",
]

"""
Analytics engines for Polaris RE — profit testing, scenario analysis, UQ, IFRS 17,
stochastic rates, experience studies, and rate schedule generation.
"""

from polaris_re.analytics.alm import (
    DualDurationGap,
    DurationGapResult,
    DurationMeasures,
    dual_duration_gap,
    duration_gap,
    duration_measures,
    liability_cash_flows,
    reserve_liability_cash_flows,
)
from polaris_re.analytics.capital import CapitalResult, LICATCapital, LICATFactors
from polaris_re.analytics.capital_base import (
    SUPPORTED_CAPITAL_MODELS,
    CapitalModel,
    CapitalModelId,
    CapitalSchedule,
    capital_model_for,
)
from polaris_re.analytics.experience_gam import (
    BayesianMISurfaceResult,
    BayesianTensorMIModel,
    ExperienceGAM,
    GAMFitResult,
    MIProjection,
    MISurface,
    MISurfaceResult,
    SmoothEffect,
    TensorMIModel,
    aggregate_seriatim,
    attach_base_rate,
)
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
from polaris_re.analytics.solvency2 import (
    SolvencyIICapital,
    SolvencyIIFactors,
    SolvencyIIResult,
)
from polaris_re.analytics.stochastic import CIRModel, HullWhiteModel, RateScenarios
from polaris_re.analytics.uq import MonteCarloUQ, UQParameters, UQResult
from polaris_re.analytics.validation import (
    ValidationCase,
    ValidationCategory,
    ValidationReport,
    ValidationResult,
    ValidationStatus,
    run_closed_form_benchmarks,
    run_full_validation_pack,
    run_statutory_deck_benchmarks,
)

__all__ = [
    "SUPPORTED_CAPITAL_MODELS",
    "AEResult",
    "BayesianMISurfaceResult",
    "BayesianTensorMIModel",
    "CIRModel",
    "CapitalModel",
    "CapitalModelId",
    "CapitalResult",
    "CapitalSchedule",
    "Deal",
    "DealResult",
    "DualDurationGap",
    "DurationGapResult",
    "DurationMeasures",
    "ExperienceGAM",
    "ExperienceStudy",
    "GAMFitResult",
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
    "MIProjection",
    "MISurface",
    "MISurfaceResult",
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
    "SmoothEffect",
    "SolveMode",
    "SolvencyIICapital",
    "SolvencyIIFactors",
    "SolvencyIIResult",
    "TensorMIModel",
    "UQParameters",
    "UQResult",
    "ValidationCase",
    "ValidationCategory",
    "ValidationReport",
    "ValidationResult",
    "ValidationStatus",
    "YRTRateSchedule",
    "aggregate_seriatim",
    "apply_scenario_to_assumptions",
    "attach_base_rate",
    "build_movement_table",
    "capital_model_for",
    "dual_duration_gap",
    "duration_gap",
    "duration_measures",
    "liability_cash_flows",
    "reserve_liability_cash_flows",
    "run_closed_form_benchmarks",
    "run_full_validation_pack",
    "run_statutory_deck_benchmarks",
]

"""
Validation & benchmark pack — reproduce authoritative actuarial references.

Polaris RE's thesis is that it is a *credible* open-source alternative to
AXIS / Prophet. Credibility requires a published, executable demonstration that
the engine reproduces authoritative reference values — not just internal
consistency. This module is the framework for that demonstration: a curated set
of :class:`ValidationCase` references (each carrying an explicit source citation
and a documented tolerance) evaluated against live engine output into a
:class:`ValidationReport` that renders a diligence-grade pass/fail table.

Slice 1 (this module) seeds the pack with **closed-form actuarial benchmarks**
— references that are *mathematical identities*, not recalled numbers, so they
are unimpeachable and network-free:

* An ``n``-year term-insurance net single premium and a temporary
  life-annuity-due actuarial present value under a **constant force of
  mortality**, each compared against its exact discrete geometric-series
  closed form (validates the projection's survivorship and discounting
  arithmetic to machine precision).
* The same term-insurance APV compared against the **continuous** constant-force
  textbook identity :math:`\\bar A^{1}_{x:\\overline{n}|}
  = \\frac{\\mu}{\\mu+\\delta}\\,(1 - e^{-(\\mu+\\delta)n})`
  (Bowers et al., *Actuarial Mathematics* 2e, §4.2; Dickson, Hardy & Waters,
  *Actuarial Mathematics for Life Contingent Risks* 2e, §4.4) — an external
  authoritative anchor, matched within a documented monthly-discretisation
  tolerance.

Later slices extend the pack with published statutory reserve decks
(VM-20 / CRVM worked examples) and surface the report on the CLI + a
validation notebook. The models here are deliberately engine-agnostic so those
slices reuse them unchanged.
"""

from enum import StrEnum

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel

__all__ = [
    "ValidationCase",
    "ValidationCategory",
    "ValidationReport",
    "ValidationResult",
    "ValidationStatus",
    "run_closed_form_benchmarks",
]


class ValidationStatus(StrEnum):
    """Outcome of evaluating a single validation case."""

    PASS = "PASS"
    FAIL = "FAIL"


class ValidationCategory(StrEnum):
    """Provenance class of a validation reference.

    * ``CLOSED_FORM`` — the reference is an exact discrete closed form derived
      from the same first principles the engine implements (validates the
      engine's arithmetic to numerical precision).
    * ``TEXTBOOK`` — the reference is a published textbook identity
      (an external authoritative anchor), matched within a documented
      modelling-convention tolerance.
    * ``STATUTORY_DECK`` — reserved for later slices: a published regulatory
      worked example (e.g. a VM-20 reserve deck).
    """

    CLOSED_FORM = "CLOSED_FORM"
    TEXTBOOK = "TEXTBOOK"
    STATUTORY_DECK = "STATUTORY_DECK"


class ValidationResult(PolarisBaseModel):
    """The outcome of comparing one engine-computed value to a reference."""

    case_id: str = Field(description="Stable identifier of the validation case.")
    name: str = Field(description="Human-readable case name.")
    category: ValidationCategory = Field(description="Provenance class of the reference.")
    source: str = Field(description="Citation for the reference value.")
    expected: float = Field(description="Authoritative reference value.")
    computed: float = Field(description="Value produced by the Polaris RE engine.")
    abs_error: float = Field(description="|computed - expected|.")
    rel_error: float = Field(
        description="|computed - expected| / |expected| (0.0 when expected == 0)."
    )
    tolerance_rtol: float = Field(description="Relative tolerance applied.")
    tolerance_atol: float = Field(description="Absolute tolerance applied.")
    status: ValidationStatus = Field(description="PASS if within tolerance, else FAIL.")


class ValidationCase(PolarisBaseModel):
    """A declarative reference value with its source and tolerance.

    A case holds only the *reference* — the authoritative expected value, its
    citation, and how close the engine must land. Driving the engine to produce
    the *computed* value is the caller's job; :meth:`evaluate` then scores the
    comparison. This separation keeps the reference catalogue independent of any
    particular engine wiring, so the CLI and notebook slices reuse it verbatim.
    """

    case_id: str = Field(description="Stable identifier of the validation case.")
    name: str = Field(description="Human-readable case name.")
    category: ValidationCategory = Field(description="Provenance class of the reference.")
    source: str = Field(description="Citation for the reference value.")
    description: str = Field(description="What the case checks and how it is constructed.")
    expected: float = Field(description="Authoritative reference value.")
    unit: str = Field(default="", description="Unit of the value (e.g. 'currency', 'per-$1').")
    tolerance_rtol: float = Field(
        default=1e-9,
        ge=0.0,
        description="Relative tolerance (numpy.isclose semantics).",
    )
    tolerance_atol: float = Field(
        default=0.0,
        ge=0.0,
        description="Absolute tolerance (numpy.isclose semantics).",
    )
    tolerance_rationale: str = Field(
        default="Exact closed form — machine precision.",
        description="Why this tolerance is appropriate for this reference.",
    )

    def evaluate(self, computed: float) -> ValidationResult:
        """Score an engine-computed value against this reference.

        Pass criterion mirrors :func:`numpy.isclose`:
        ``|computed - expected| <= atol + rtol * |expected|``.
        """
        abs_error = float(abs(computed - self.expected))
        denom = abs(self.expected)
        rel_error = float(abs_error / denom) if denom > 0.0 else 0.0
        threshold = self.tolerance_atol + self.tolerance_rtol * denom
        status = ValidationStatus.PASS if abs_error <= threshold else ValidationStatus.FAIL
        return ValidationResult(
            case_id=self.case_id,
            name=self.name,
            category=self.category,
            source=self.source,
            expected=self.expected,
            computed=float(computed),
            abs_error=abs_error,
            rel_error=rel_error,
            tolerance_rtol=self.tolerance_rtol,
            tolerance_atol=self.tolerance_atol,
            status=status,
        )


class ValidationReport(PolarisBaseModel):
    """A scored collection of validation results, renderable for diligence."""

    title: str = Field(description="Report title.")
    results: tuple[ValidationResult, ...] = Field(
        description="Scored results, one per validation case."
    )

    @property
    def n_cases(self) -> int:
        """Total number of cases evaluated."""
        return len(self.results)

    @property
    def n_passed(self) -> int:
        """Number of cases within tolerance."""
        return sum(1 for r in self.results if r.status is ValidationStatus.PASS)

    @property
    def n_failed(self) -> int:
        """Number of cases outside tolerance."""
        return self.n_cases - self.n_passed

    @property
    def all_passed(self) -> bool:
        """True when every case is within tolerance."""
        return self.n_failed == 0

    def to_markdown(self) -> str:
        """Render the report as a Markdown table (for the validation notebook/CLI)."""
        lines = [
            f"# {self.title}",
            "",
            f"**{self.n_passed}/{self.n_cases} cases passed.**",
            "",
            "| Case | Category | Source | Expected | Computed | Rel. error | Tol (rtol) | Status |",
            "|------|----------|--------|---------:|---------:|-----------:|-----------:|:------:|",
        ]
        for r in self.results:
            mark = "✅" if r.status is ValidationStatus.PASS else "❌"
            lines.append(
                f"| {r.name} | {r.category.value} | {r.source} "
                f"| {r.expected:,.6f} | {r.computed:,.6f} "
                f"| {r.rel_error:.2e} | {r.tolerance_rtol:.1e} | {mark} |"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Closed-form reference derivations (constant force of mortality)
# ---------------------------------------------------------------------------
#
# Under a constant annual mortality rate ``q`` and annual effective interest
# ``i``, the engine's monthly mechanics are exactly:
#     a   = (1 - q) ** (1/12)          monthly survival probability
#     q_m = 1 - a                      monthly mortality rate (constant force)
#     v   = (1 + i) ** (-1/12)         monthly discount factor
#     lx[m]           = a ** m         in-force at the start of month m
#     death_claims[m] = a ** m * (1 - a) * F   (paid end of month m)
# so the following geometric sums are the *exact* discrete APVs the engine must
# reproduce over an ``M``-month window with no lapse and no max-age forcing.


def _closed_form_term_insurance_apv(
    q_annual: float, i_annual: float, face: float, months: int
) -> float:
    """Exact discrete APV of an ``months``-month term insurance under constant force.

    :math:`F(1-a)v\\sum_{m=0}^{M-1}(av)^m = F(1-a)v\\frac{1-(av)^M}{1-av}`,
    benefit paid at the end of the month of death, discounted monthly. This is
    the closed form of the engine's own survivorship/discounting recursion.
    """
    a = (1.0 - q_annual) ** (1.0 / 12.0)
    v = (1.0 + i_annual) ** (-1.0 / 12.0)
    av = a * v
    return float(face * (1.0 - a) * v * (1.0 - av**months) / (1.0 - av))


def _closed_form_temporary_annuity_due_apv(q_annual: float, i_annual: float, months: int) -> float:
    """Exact discrete APV of an ``months``-month temporary life annuity-due.

    Unit payment at the start of each month while in force:
    :math:`\\sum_{m=0}^{M-1}(av)^m = \\frac{1-(av)^M}{1-av}`.
    """
    a = (1.0 - q_annual) ** (1.0 / 12.0)
    v = (1.0 + i_annual) ** (-1.0 / 12.0)
    av = a * v
    return float((1.0 - av**months) / (1.0 - av))


def _continuous_term_insurance_apv(
    q_annual: float, i_annual: float, face: float, years: float
) -> float:
    """Continuous constant-force textbook APV of an ``years``-year term insurance.

    :math:`\\bar A^{1}_{x:\\overline{n}|} = \\frac{\\mu}{\\mu+\\delta}
    \\left(1 - e^{-(\\mu+\\delta)n}\\right)` with force of mortality
    :math:`\\mu = -\\ln(1-q)` and force of interest :math:`\\delta = \\ln(1+i)`.
    (Bowers et al., *Actuarial Mathematics* 2e, §4.2.)
    """
    mu = -np.log(1.0 - q_annual)
    delta = np.log(1.0 + i_annual)
    return float(face * (mu / (mu + delta)) * (1.0 - np.exp(-(mu + delta) * years)))


def _run_constant_force_projection(
    q_annual: float, i_annual: float, issue_age: int, term_years: int, face: float
) -> tuple[float, float]:
    """Project a single constant-force TermLife policy; return (deaths APV, annuity APV).

    Builds a synthetic ultimate-only mortality table with a constant annual rate
    and a zero-lapse assumption, so the in-force decrements by mortality alone
    and the engine output is the pure mortality APV. The projection horizon keeps
    the attained age well below the table's max age, so no certain-death forcing
    at omega enters the window.

    Imports of the product/assumption layers are deferred to call time to keep
    this analytics module free of an import cycle with ``products``.
    """
    from datetime import date
    from pathlib import Path

    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.inforce import InforceBlock
    from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
    from polaris_re.core.projection import ProjectionConfig
    from polaris_re.products.term_life import TermLife
    from polaris_re.utils.table_io import MortalityTableArray

    min_age, max_age = 0, 120
    n_ages = max_age - min_age + 1
    rates = np.full((n_ages, 1), q_annual, dtype=np.float64)
    table_array = MortalityTableArray(
        rates=rates,
        min_age=min_age,
        max_age=max_age,
        select_period=0,
        source_file=Path("synthetic-constant-force"),
    )
    table = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name=f"Constant force q={q_annual}",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    assumptions = AssumptionSet(
        mortality=table,
        lapse=LapseAssumption.from_duration_table({1: 0.0, "ultimate": 0.0}),
        version="validation-constant-force",
    )
    config = ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=term_years,
        discount_rate=i_annual,
    )
    policy = Policy(
        policy_id="VALIDATION-CF",
        issue_age=issue_age,
        attained_age=issue_age,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=1.0,
        product_type=ProductType.TERM,
        policy_term=term_years,
        duration_inforce=0,
        reinsurance_cession_pct=0.0,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )
    block = InforceBlock(policies=[policy])
    result = TermLife(block, assumptions, config).project(seriatim=True)

    months = config.projection_months
    v = (1.0 + i_annual) ** (-1.0 / 12.0)
    disc_end = v ** np.arange(1, months + 1, dtype=np.float64)  # end-of-month
    disc_begin = v ** np.arange(0, months, dtype=np.float64)  # start-of-month

    deaths_apv = float(np.dot(result.death_claims, disc_end))
    if result.seriatim_lx is None:  # pragma: no cover - project(seriatim=True) populates it
        raise ValueError("Seriatim in-force required for the annuity APV benchmark.")
    annuity_apv = float(np.dot(result.seriatim_lx[0, :], disc_begin))
    return deaths_apv, annuity_apv


def run_closed_form_benchmarks() -> ValidationReport:
    """Build and score the Slice-1 closed-form validation pack.

    Returns a :class:`ValidationReport` comparing live TermLife engine output to
    exact discrete closed forms and to the continuous constant-force textbook
    identity. Self-contained: no external data, no network, deterministic.
    """
    results: list[ValidationResult] = []

    # Two independent parameter sets exercise the exact discrete term-insurance
    # APV (mortality/claims machinery) across low and moderate mortality/interest.
    exact_term_params = (
        ("CF-TERM-APV-1", 40, 20, 0.01, 0.05, 1_000_000.0),
        ("CF-TERM-APV-2", 55, 15, 0.02, 0.04, 500_000.0),
    )
    for case_id, age, term, q, i, face in exact_term_params:
        deaths_apv, _annuity_apv = _run_constant_force_projection(q, i, age, term, face)
        expected = _closed_form_term_insurance_apv(q, i, face, term * 12)
        case = ValidationCase(
            case_id=case_id,
            name=f"{term}-yr term insurance APV (age {age}, q={q}, i={i})",
            category=ValidationCategory.CLOSED_FORM,
            source="Discrete geometric-series closed form (constant force of mortality)",
            description=(
                "Net single premium of an n-year term insurance under a constant "
                "force of mortality: F(1-a)v(1-(av)^M)/(1-av), benefit paid at "
                "end of month of death. Compared to the engine's projected, "
                "monthly-discounted death benefits with lapse switched off."
            ),
            expected=expected,
            unit="currency",
            tolerance_rtol=1e-9,
            tolerance_rationale="Exact discrete closed form of the engine's own recursion.",
        )
        results.append(case.evaluate(deaths_apv))

    # Temporary life annuity-due APV — validates survivorship discounting.
    q_a, i_a, age_a, term_a = 0.01, 0.05, 40, 20
    _deaths_apv, annuity_apv = _run_constant_force_projection(q_a, i_a, age_a, term_a, 1.0)
    expected_annuity = _closed_form_temporary_annuity_due_apv(q_a, i_a, term_a * 12)
    annuity_case = ValidationCase(
        case_id="CF-ANNUITY-DUE",
        name=f"{term_a}-yr temporary life annuity-due APV (age {age_a}, q={q_a}, i={i_a})",
        category=ValidationCategory.CLOSED_FORM,
        source="Discrete geometric-series closed form (constant force of mortality)",
        description=(
            "APV of a unit monthly annuity-due payable while in force: "
            "sum (av)^m = (1-(av)^M)/(1-av). Compared to the engine's seriatim "
            "in-force factors discounted at the start of each month."
        ),
        expected=expected_annuity,
        unit="per-unit-monthly-payment",
        tolerance_rtol=1e-9,
        tolerance_rationale="Exact discrete closed form of the engine's survivorship.",
    )
    results.append(annuity_case.evaluate(annuity_apv))

    # Continuous-force textbook cross-check — external authoritative anchor.
    q_c, i_c, age_c, term_c, face_c = 0.01, 0.05, 40, 20, 1_000_000.0
    deaths_apv_c, _annuity_c = _run_constant_force_projection(q_c, i_c, age_c, term_c, face_c)
    expected_cont = _continuous_term_insurance_apv(q_c, i_c, face_c, float(term_c))
    cont_case = ValidationCase(
        case_id="TB-TERM-CONT",
        name=f"{term_c}-yr term insurance APV vs continuous-force identity (age {age_c})",
        category=ValidationCategory.TEXTBOOK,
        source="Bowers et al., Actuarial Mathematics 2e §4.2 (constant force)",
        description=(
            "Continuous constant-force term-insurance APV "
            "(mu/(mu+delta))(1-e^{-(mu+delta)n}), mu=-ln(1-q), delta=ln(1+i). "
            "The engine's monthly-discrete projection approximates this "
            "continuous identity."
        ),
        expected=expected_cont,
        unit="currency",
        tolerance_rtol=5e-3,
        tolerance_rationale=(
            "Monthly-discrete death timing/discounting vs the continuous "
            "textbook identity; measured discrepancy ~0.2%."
        ),
    )
    results.append(cont_case.evaluate(deaths_apv_c))

    return ValidationReport(
        title="Polaris RE — Closed-Form Actuarial Validation Pack",
        results=tuple(results),
    )

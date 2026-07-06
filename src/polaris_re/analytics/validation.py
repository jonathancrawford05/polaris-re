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

Slice 2 (``STATUTORY_DECK``) adds a **published life-table deck** — the SOA
Illustrative Life Table (Bowers et al., *Actuarial Mathematics* 2e, Appendix 2A).
The table's ``l_x`` column is vendored under ``data/validation/`` and its
whole-life net single premium :math:`A_x`, annuity-due :math:`\\ddot a_x`, and
net level premium :math:`P_x = A_x/\\ddot a_x` at ``i = 6%`` are reproduced by
the live WholeLife engine to machine precision (the constant-force monthly split
preserves the table's annual decrements exactly, so the engine's monthly
projection aggregated back to annual equals the tabulated APVs). The vendored
``l_x`` is itself generated from the table's *published Makeham law*
(:math:`\\mu_x = A + Bc^x`, ``A = 0.0007``, ``B = 0.00005``, ``c = 10^{0.04}``,
``l_0 = 100000``), so the reference is a cited parametric identity, not a
hand-copied column — yet it reproduces the printed table's tabulated
``1000 A_35 = 128.72`` / ``ä_35 = 15.3926`` to all printed digits.

Later slices surface the report on the CLI + a validation notebook. The models
here are deliberately engine-agnostic so those slices reuse them unchanged.
"""

import os
from enum import StrEnum
from pathlib import Path

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
    "run_full_validation_pack",
    "run_statutory_deck_benchmarks",
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


# ---------------------------------------------------------------------------
# Statutory / published-deck references — SOA Illustrative Life Table
# ---------------------------------------------------------------------------
#
# The SOA Illustrative Life Table (Bowers et al., *Actuarial Mathematics* 2e,
# Appendix 2A) is generated from Makeham's law
#     mu(x) = A + B c^x
# so the survival function from birth is the cited closed form
#     S(x) = exp(-A x - (B/ln c)(c^x - 1))
# and l_x = l_0 S(x). The three constants below ARE the citation — the vendored
# ``l_x`` column is regenerated from them and self-checked against the printed
# table (1000 A_35 = 128.72, ä_35 = 15.3926, …), so no hand-copied number is
# ever trusted.

_ILT_MAKEHAM_A = 0.0007
_ILT_MAKEHAM_B = 0.00005
_ILT_MAKEHAM_C = 10.0**0.04
_ILT_L0 = 100_000.0
#: Table closes here: everyone alive at age ω dies during the following year
#: (q_ω = 1, l_{ω+1} = 0), matching the engine's max-age certain-death forcing.
_ILT_OMEGA = 120
#: The Illustrative Life Table's tabulated valuation interest rate.
_ILT_INTEREST = 0.06

#: Vendored reference file (repo-relative ``data/validation/``), overridable via
#: ``$POLARIS_DATA_DIR`` for a mounted data root.
_ILT_CSV_NAME = "illustrative_life_table.csv"


def _illustrative_life_table_makeham() -> tuple[np.ndarray, np.ndarray]:
    """Generate the Illustrative Life Table ``(ages, l_x)`` from its Makeham law.

    Ages ``0 .. ω+1``; ``l_{ω+1} = 0`` closes the table. This is the single
    source of truth for both the vendored CSV and the transcription self-check.
    """
    ln_c = np.log(_ILT_MAKEHAM_C)
    ages = np.arange(0, _ILT_OMEGA + 2, dtype=np.int64)
    x = ages.astype(np.float64)
    survival = np.exp(-_ILT_MAKEHAM_A * x - (_ILT_MAKEHAM_B / ln_c) * (_ILT_MAKEHAM_C**x - 1.0))
    lx = _ILT_L0 * survival
    lx[_ILT_OMEGA + 1] = 0.0  # close the table
    return ages, lx


def _illustrative_life_table_path() -> Path:
    """Resolve the vendored Illustrative Life Table CSV path.

    Prefers ``$POLARIS_DATA_DIR/validation/`` when set (mounted data root),
    else the repo-relative ``data/validation/`` alongside the source tree.
    """
    data_dir_env = os.environ.get("POLARIS_DATA_DIR")
    if data_dir_env:
        candidate = Path(data_dir_env) / "validation" / _ILT_CSV_NAME
        if candidate.is_file():
            return candidate
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "validation" / _ILT_CSV_NAME


def _load_illustrative_life_table() -> tuple[np.ndarray, np.ndarray]:
    """Load the vendored Illustrative Life Table ``(ages, l_x)`` from CSV.

    Comment lines (``#`` prefix — the citation header) are skipped. The file
    carries ``age,l_x`` rows through ``age = ω+1`` (``l_x = 0``).
    """
    path = _illustrative_life_table_path()
    ages_list: list[int] = []
    lx_list: list[float] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.lower().startswith("age"):
            continue
        age_str, lx_str = line.split(",")
        ages_list.append(int(age_str))
        lx_list.append(float(lx_str))
    return (
        np.array(ages_list, dtype=np.int64),
        np.array(lx_list, dtype=np.float64),
    )


def _annual_whole_life_apvs(lx: np.ndarray, issue_age: int, i_annual: float) -> tuple[float, float]:
    """Annual whole-life ``(A_x, ä_x)`` from a life table ``l_x`` at rate ``i``.

    The textbook annual life-table identities:
    :math:`A_x = \\sum_{k\\ge 0} v^{k+1}(l_{x+k}-l_{x+k+1})/l_x` and
    :math:`\\ddot a_x = \\sum_{k\\ge 0} v^{k} l_{x+k}/l_x`, with ``v = 1/(1+i)``.
    These are exact given ``l_x`` and satisfy ``A_x = 1 - d ä_x`` (``d = i/(1+i)``).
    """
    v = 1.0 / (1.0 + i_annual)
    tail = lx[issue_age:]
    deaths = tail[:-1] - tail[1:]
    k_d = np.arange(deaths.shape[0], dtype=np.float64)
    a_x = float(np.sum(v ** (k_d + 1.0) * deaths) / tail[0])
    k_a = np.arange(tail.shape[0], dtype=np.float64)
    adue_x = float(np.sum(v**k_a * tail) / tail[0])
    return a_x, adue_x


def _run_illustrative_life_table_projection(
    issue_age: int, lx: np.ndarray, i_annual: float
) -> tuple[float, float]:
    """Drive the WholeLife engine on the ILT to omega; return annual ``(A_x, ä_x)``.

    Converts the vendored ``l_x`` to annual ``q_x`` (``q_ω = 1``), projects a
    single whole-life policy from ``issue_age`` to omega, then reconstructs the
    *annual* APVs from the monthly engine output: monthly death benefits are
    aggregated within each policy year and discounted to year-end, and the
    in-force is sampled at policy-year boundaries. Under the engine's
    constant-force monthly split these reconstructions equal the tabulated annual
    APVs exactly, so the engine reproduces the published table to machine
    precision.

    Imports of the product/assumption layers are deferred to call time to keep
    this analytics module free of an import cycle with ``products``.
    """
    from datetime import date

    from polaris_re.assumptions.assumption_set import AssumptionSet
    from polaris_re.assumptions.lapse import LapseAssumption
    from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
    from polaris_re.core.inforce import InforceBlock
    from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
    from polaris_re.core.projection import ProjectionConfig
    from polaris_re.products.whole_life import WholeLife
    from polaris_re.utils.table_io import MortalityTableArray

    # Annual q_x from l_x; q at omega forced to 1 (certain death).
    q_annual = np.ones(_ILT_OMEGA + 1, dtype=np.float64)
    alive = lx[: _ILT_OMEGA + 1] > 0.0
    q_annual[alive] = 1.0 - lx[1 : _ILT_OMEGA + 2][alive] / lx[: _ILT_OMEGA + 1][alive]
    q_annual[_ILT_OMEGA] = 1.0

    table_array = MortalityTableArray(
        rates=q_annual.reshape(-1, 1),
        min_age=0,
        max_age=_ILT_OMEGA,
        select_period=0,
        source_file=Path("illustrative-life-table"),
    )
    table = MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="SOA Illustrative Life Table",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )
    assumptions = AssumptionSet(
        mortality=table,
        lapse=LapseAssumption.from_duration_table({1: 0.0, "ultimate": 0.0}),
        version="validation-illustrative-life-table",
    )
    term_years = _ILT_OMEGA - issue_age  # attained age reaches omega at horizon end
    config = ProjectionConfig(
        valuation_date=date(2025, 1, 1),
        projection_horizon_years=term_years,
        discount_rate=i_annual,
    )
    face = 1_000_000.0
    policy = Policy(
        policy_id="VALIDATION-ILT",
        issue_age=issue_age,
        attained_age=issue_age,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
        underwriting_class="STANDARD",
        face_amount=face,
        annual_premium=1.0,
        product_type=ProductType.WHOLE_LIFE,
        policy_term=term_years,
        duration_inforce=0,
        reinsurance_cession_pct=0.0,
        issue_date=date(2025, 1, 1),
        valuation_date=date(2025, 1, 1),
    )
    block = InforceBlock(policies=[policy])
    result = WholeLife(block, assumptions, config).project(seriatim=True)

    months = config.projection_months
    v = 1.0 / (1.0 + i_annual)
    n_years = months // 12
    death_claims = np.asarray(result.death_claims, dtype=np.float64)
    if result.seriatim_lx is None:  # pragma: no cover - project(seriatim=True) populates it
        raise ValueError("Seriatim in-force required for the ILT annuity benchmark.")
    lx_monthly = np.asarray(result.seriatim_lx, dtype=np.float64)[0, :]

    # A_x: aggregate monthly deaths within each policy year, discount to year-end.
    year_deaths = death_claims[: n_years * 12].reshape(n_years, 12).sum(axis=1)
    a_x = float(np.sum(v ** np.arange(1, n_years + 1, dtype=np.float64) * year_deaths) / face)
    # ä_x: in-force sampled at the start of each policy year.
    adue_x = float(
        np.sum(v ** np.arange(n_years, dtype=np.float64) * lx_monthly[: n_years * 12 : 12])
    )
    return a_x, adue_x


#: Issue ages exercised against the Illustrative Life Table (young / mid / retirement).
_ILT_ISSUE_AGES: tuple[int, ...] = (35, 40, 65)


def run_statutory_deck_benchmarks() -> ValidationReport:
    """Build and score the Slice-2 published-deck validation pack.

    Reproduces the SOA Illustrative Life Table whole-life net single premium
    ``A_x``, annuity-due ``ä_x``, and net level premium ``P_x`` at ``i = 6%``
    for several issue ages, driving the live WholeLife engine and comparing to
    the tabulated annual APVs derived from the vendored ``l_x``. All references
    are machine-precision identities of the published table.
    """
    _ages, lx = _load_illustrative_life_table()
    source = (
        "SOA Illustrative Life Table, i=6% (Bowers et al., Actuarial Mathematics "
        "2e, App. 2A; Makeham mu=A+Bc^x, A=.0007, B=.00005, c=10^.04)"
    )
    results: list[ValidationResult] = []
    for issue_age in _ILT_ISSUE_AGES:
        ref_a, ref_adue = _annual_whole_life_apvs(lx, issue_age, _ILT_INTEREST)
        eng_a, eng_adue = _run_illustrative_life_table_projection(issue_age, lx, _ILT_INTEREST)
        ref_p = ref_a / ref_adue
        eng_p = eng_a / eng_adue

        a_case = ValidationCase(
            case_id=f"ILT-A-{issue_age}",
            name=f"Whole-life A_{issue_age} net single premium (ILT, i=6%)",
            category=ValidationCategory.STATUTORY_DECK,
            source=source,
            description=(
                "Whole-life net single premium A_x per $1 from the Illustrative "
                "Life Table l_x. The engine projects a whole-life policy to omega; "
                "monthly death benefits are aggregated to annual and discounted to "
                "year-end, reproducing the tabulated annual A_x."
            ),
            expected=ref_a,
            unit="per-$1-face",
            tolerance_rtol=1e-9,
            tolerance_rationale=(
                "Constant-force monthly split preserves the table's annual "
                "decrements exactly; annual reconstruction is machine precision."
            ),
        )
        results.append(a_case.evaluate(eng_a))

        adue_case = ValidationCase(
            case_id=f"ILT-ADUE-{issue_age}",
            name=f"Whole-life annuity-due ä_{issue_age} (ILT, i=6%)",
            category=ValidationCategory.STATUTORY_DECK,
            source=source,
            description=(
                "Whole-life annuity-due ä_x from the Illustrative Life Table l_x. "
                "The engine's in-force sampled at policy-year boundaries reproduces "
                "the tabulated annual ä_x."
            ),
            expected=ref_adue,
            unit="years",
            tolerance_rtol=1e-9,
            tolerance_rationale=(
                "Annual in-force sampled from the engine equals the tabulated "
                "survivorship exactly under the constant-force split."
            ),
        )
        results.append(adue_case.evaluate(eng_adue))

        p_case = ValidationCase(
            case_id=f"ILT-P-{issue_age}",
            name=f"Whole-life net level premium P_{issue_age} = A_x/ä_x (ILT, i=6%)",
            category=ValidationCategory.STATUTORY_DECK,
            source=source,
            description=(
                "Whole-life net level annual premium P_x = A_x/ä_x per $1 face, "
                "the ratio of the two reproduced APVs."
            ),
            expected=ref_p,
            unit="per-$1-face-per-year",
            tolerance_rtol=1e-9,
            tolerance_rationale=(
                "Ratio of two machine-precision APVs; the discretisation cancels."
            ),
        )
        results.append(p_case.evaluate(eng_p))

    return ValidationReport(
        title="Polaris RE — Published-Deck Validation Pack (SOA Illustrative Life Table)",
        results=tuple(results),
    )


def run_full_validation_pack() -> ValidationReport:
    """Combine every validation category into one diligence report.

    Concatenates the closed-form (Slice 1) and published-deck (Slice 2) packs so
    the CLI / notebook slices render a single pass/fail table across all
    reference categories.
    """
    closed_form = run_closed_form_benchmarks()
    deck = run_statutory_deck_benchmarks()
    return ValidationReport(
        title="Polaris RE — Full Actuarial Validation Pack",
        results=closed_form.results + deck.results,
    )

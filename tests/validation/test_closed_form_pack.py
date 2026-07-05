"""Closed-form validation pack — TermLife engine vs authoritative references.

These tests exercise the Slice-1 validation & benchmark pack
(``polaris_re.analytics.validation``). The references are closed-form actuarial
identities (constant force of mortality), so the assertions are unimpeachable
and network-free: the engine must reproduce the exact discrete geometric-series
APVs to machine precision, and land within a documented monthly-discretisation
tolerance of the continuous-force textbook identity.
"""

import numpy as np
import pytest

from polaris_re.analytics.validation import (
    ValidationCase,
    ValidationCategory,
    ValidationReport,
    ValidationStatus,
    _closed_form_temporary_annuity_due_apv,
    _closed_form_term_insurance_apv,
    _continuous_term_insurance_apv,
    _run_constant_force_projection,
    run_closed_form_benchmarks,
)


@pytest.fixture(scope="module")
def report() -> ValidationReport:
    """The Slice-1 closed-form validation report (one engine run set, reused)."""
    return run_closed_form_benchmarks()


class TestValidationCaseModel:
    """Unit tests for the ValidationCase / evaluate scoring primitive."""

    def _case(self, expected: float, rtol: float, atol: float = 0.0) -> ValidationCase:
        return ValidationCase(
            case_id="UNIT",
            name="unit case",
            category=ValidationCategory.CLOSED_FORM,
            source="unit test",
            description="unit test case",
            expected=expected,
            tolerance_rtol=rtol,
            tolerance_atol=atol,
        )

    def test_exact_match_passes(self) -> None:
        result = self._case(100.0, rtol=1e-9).evaluate(100.0)
        assert result.status is ValidationStatus.PASS
        assert result.abs_error == 0.0
        assert result.rel_error == 0.0

    def test_within_rtol_passes(self) -> None:
        # 100 * (1 + 5e-4) = 100.05, threshold at rtol=1e-3 is 0.1
        result = self._case(100.0, rtol=1e-3).evaluate(100.05)
        assert result.status is ValidationStatus.PASS

    def test_outside_rtol_fails(self) -> None:
        result = self._case(100.0, rtol=1e-3).evaluate(100.5)
        assert result.status is ValidationStatus.FAIL
        np.testing.assert_allclose(result.rel_error, 5e-3, rtol=1e-9)

    def test_zero_expected_uses_atol(self) -> None:
        # rel_error is defined as 0.0 when expected == 0; atol governs the pass.
        passes = self._case(0.0, rtol=1e-9, atol=1e-6).evaluate(5e-7)
        fails = self._case(0.0, rtol=1e-9, atol=1e-6).evaluate(5e-6)
        assert passes.status is ValidationStatus.PASS
        assert passes.rel_error == 0.0
        assert fails.status is ValidationStatus.FAIL


class TestClosedFormDerivations:
    """The reference derivations are internally consistent with known limits."""

    def test_annuity_insurance_consistency_identity(self) -> None:
        """A = 1 - d_month * a_due (monthly): the insurance/annuity identity.

        For a whole-term window run to completion, PV(benefits) + d*PV(annuity)
        relationship holds discretely. Here we verify the monthly identity
        A_term = 1 - (1 - v) * a_due - (av)^M * (1 - <tail>) reduces to the
        geometric closed forms — i.e. the two derivations share one geometric
        series and are mutually consistent.
        """
        q, i, months = 0.01, 0.05, 240
        a = (1.0 - q) ** (1.0 / 12.0)
        v = (1.0 + i) ** (-1.0 / 12.0)
        term = _closed_form_term_insurance_apv(q, i, 1.0, months)
        annuity = _closed_form_temporary_annuity_due_apv(q, i, months)
        # Monthly recursion identity: A = (1 - a) * v * annuity_over_survival...
        # Direct check: term / annuity == (1 - a) * v  (both share (1-(av)^M)/(1-av)).
        np.testing.assert_allclose(term / annuity, (1.0 - a) * v, rtol=1e-12)

    def test_continuous_limit_is_close_to_discrete(self) -> None:
        q, i, face, years = 0.01, 0.05, 1_000_000.0, 20
        discrete = _closed_form_term_insurance_apv(q, i, face, years * 12)
        continuous = _continuous_term_insurance_apv(q, i, face, float(years))
        # Discrete monthly under-values the continuous by a small, bounded amount.
        assert 0.0 < (continuous - discrete) / continuous < 1e-2

    def test_zero_mortality_gives_zero_insurance_and_full_annuity(self) -> None:
        # No deaths → no insurance APV; annuity is a pure interest annuity-certain.
        assert _closed_form_term_insurance_apv(0.0, 0.05, 1_000_000.0, 120) == 0.0
        v = (1.0 + 0.05) ** (-1.0 / 12.0)
        expected_certain = (1.0 - v**120) / (1.0 - v)
        np.testing.assert_allclose(
            _closed_form_temporary_annuity_due_apv(0.0, 0.05, 120),
            expected_certain,
            rtol=1e-12,
        )


class TestEngineReproducesClosedForms:
    """The TermLife engine reproduces the closed-form references."""

    def test_term_insurance_apv_matches_exactly(self) -> None:
        q, i, age, term, face = 0.01, 0.05, 40, 20, 1_000_000.0
        deaths_apv, _annuity = _run_constant_force_projection(q, i, age, term, face)
        expected = _closed_form_term_insurance_apv(q, i, face, term * 12)
        np.testing.assert_allclose(deaths_apv, expected, rtol=1e-9)

    def test_annuity_apv_matches_exactly(self) -> None:
        q, i, age, term = 0.01, 0.05, 40, 20
        _deaths, annuity_apv = _run_constant_force_projection(q, i, age, term, 1.0)
        expected = _closed_form_temporary_annuity_due_apv(q, i, term * 12)
        np.testing.assert_allclose(annuity_apv, expected, rtol=1e-9)

    @pytest.mark.parametrize(
        ("q", "i", "age", "term", "face"),
        [
            (0.01, 0.05, 40, 20, 1_000_000.0),
            (0.02, 0.04, 55, 15, 500_000.0),
            (0.005, 0.06, 30, 30, 250_000.0),
        ],
    )
    def test_term_insurance_apv_matches_across_parameters(
        self, q: float, i: float, age: int, term: int, face: float
    ) -> None:
        deaths_apv, _annuity = _run_constant_force_projection(q, i, age, term, face)
        expected = _closed_form_term_insurance_apv(q, i, face, term * 12)
        np.testing.assert_allclose(deaths_apv, expected, rtol=1e-9)


class TestValidationReport:
    """The assembled report passes and renders."""

    def test_all_cases_pass(self, report: ValidationReport) -> None:
        failing = [r.name for r in report.results if r.status is ValidationStatus.FAIL]
        assert report.all_passed, f"Validation cases failed: {failing}"

    def test_report_has_expected_case_count(self, report: ValidationReport) -> None:
        # 2 exact term-APV + 1 annuity + 1 continuous cross-check
        assert report.n_cases == 4
        assert report.n_passed == 4
        assert report.n_failed == 0

    def test_report_includes_both_categories(self, report: ValidationReport) -> None:
        categories = {r.category for r in report.results}
        assert ValidationCategory.CLOSED_FORM in categories
        assert ValidationCategory.TEXTBOOK in categories

    def test_exact_cases_are_machine_precision(self, report: ValidationReport) -> None:
        exact = [r for r in report.results if r.category is ValidationCategory.CLOSED_FORM]
        assert exact  # sanity
        for r in exact:
            assert r.rel_error < 1e-9

    def test_textbook_case_within_documented_tolerance(self, report: ValidationReport) -> None:
        textbook = [r for r in report.results if r.category is ValidationCategory.TEXTBOOK]
        assert len(textbook) == 1
        assert textbook[0].rel_error < 5e-3

    def test_to_markdown_renders_table(self, report: ValidationReport) -> None:
        md = report.to_markdown()
        assert md.startswith("# Polaris RE")
        assert "4/4 cases passed" in md
        assert "| Case |" in md
        # every case name appears as a row
        for r in report.results:
            assert r.name in md

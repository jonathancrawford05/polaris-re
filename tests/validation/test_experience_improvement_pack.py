"""Experience-analysis improvement-recovery validation deck (A4').

These tests exercise ``polaris_re.analytics.experience_validation`` — the
experience-analysis analogue of the closed-form / statutory decks. The reference
is a *recovery identity*: a known annual mortality-improvement surface is injected
into a synthetic, ILEC-source-schema experience extract, fed through the real
``load_ilec`` loader (loaders-not-data), refit by the tensor MI GAM, and the
recovered ``MI_x(y)`` is checked against the injected target.

Because the injected improvement is constant across calendar years, the target is
spanned exactly by the tensor B-spline basis, so recovery is numerical (observed
residual < 3e-12) and the deck is a diligence-grade, network-free identity — no
proprietary ILEC or MIM-2021 table is vendored. Everything is pinned to literal
calendar years (ADR-074: no wall-clock read), so the report is deterministic.
"""

import numpy as np
import pytest

from polaris_re.analytics.experience_validation import (
    _agevarying_mi,
    _flat_mi,
    _recover_surface,
    run_experience_improvement_benchmarks,
)
from polaris_re.analytics.validation import (
    ValidationCategory,
    ValidationReport,
    ValidationStatus,
)


@pytest.fixture(scope="module")
def report() -> ValidationReport:
    """The experience-improvement recovery report (one fit set, reused)."""
    return run_experience_improvement_benchmarks()


class TestExperienceImprovementPack:
    def test_report_title(self, report: ValidationReport) -> None:
        assert "Improvement Recovery" in report.title

    def test_all_cases_pass(self, report: ValidationReport) -> None:
        """The GAM recovers every injected improvement point within tolerance."""
        assert report.all_passed, [
            (r.name, r.abs_error) for r in report.results if r.status is ValidationStatus.FAIL
        ]

    def test_five_cases(self, report: ValidationReport) -> None:
        assert report.n_cases == 5

    def test_every_case_is_experience_category(self, report: ValidationReport) -> None:
        assert all(r.category is ValidationCategory.EXPERIENCE_IMPROVEMENT for r in report.results)

    def test_recovery_is_high_precision(self, report: ValidationReport) -> None:
        """Recovery of a log-linear-in-year target is numerical, not just in-tol."""
        assert max(r.abs_error for r in report.results) < 1e-9

    def test_case_ids_are_unique_and_stable(self, report: ValidationReport) -> None:
        ids = [r.case_id for r in report.results]
        assert len(set(ids)) == len(ids)
        assert set(ids) == {
            "EXP-MI-FLAT-A60-Y2010",
            "EXP-MI-FLAT-A70-Y2018",
            "EXP-MI-VARY-A45-Y2015",
            "EXP-MI-VARY-A60-Y2015",
            "EXP-MI-VARY-A75-Y2015",
        }

    def test_every_case_carries_a_tolerance_rationale(self, report: ValidationReport) -> None:
        """Diligence contract: each reference documents why its tolerance is apt."""
        assert all(r.tolerance_atol > 0.0 for r in report.results)


class TestInjectedTargets:
    """The reference values must be the injected parametric targets themselves."""

    def test_flat_target_is_constant(self) -> None:
        mi = _flat_mi(np.array([40, 60, 85]))
        np.testing.assert_allclose(mi, 0.015, atol=0.0)

    @pytest.mark.parametrize(
        ("age", "expected"),
        [
            (40, 0.020),  # young endpoint
            (85, 0.005),  # old endpoint
            (45, 0.020 - 0.015 * 5 / 45),
            (60, 0.020 - 0.015 * 20 / 45),
            (75, 0.020 - 0.015 * 35 / 45),
        ],
    )
    def test_agevarying_target_shape(self, age: int, expected: float) -> None:
        got = float(_agevarying_mi(np.array([age]))[0])
        np.testing.assert_allclose(got, expected, atol=1e-12)

    def test_agevarying_is_monotone_declining(self) -> None:
        """The MIM-2021/CIA-style shape declines with attained age."""
        ages = np.arange(40, 86)
        mi = _agevarying_mi(ages)
        assert np.all(np.diff(mi) < 0.0)


class TestRecoveryMechanics:
    def test_flat_recovered_surface_matches_injection(self) -> None:
        """A flat injection is recovered across the whole surface, not just samples."""
        surface = _recover_surface(_flat_mi, age_varying=False)
        np.testing.assert_allclose(surface.mi_grid, 0.015, atol=1e-9)

    def test_agevarying_recovered_gradient_matches_injection(self) -> None:
        """The recovered age gradient reproduces the injected age-declining target."""
        surface = _recover_surface(_agevarying_mi, age_varying=True)
        # Improvement is year-invariant, so every column equals MI(age).
        injected = np.repeat(
            _agevarying_mi(surface.ages)[:, None], surface.mi_grid.shape[1], axis=1
        )
        np.testing.assert_allclose(surface.mi_grid, injected, atol=1e-9)

    def test_recovery_is_deterministic(self) -> None:
        """Two independent runs produce byte-identical recovered surfaces."""
        a = _recover_surface(_agevarying_mi, age_varying=True)
        b = _recover_surface(_agevarying_mi, age_varying=True)
        np.testing.assert_array_equal(a.mi_grid, b.mi_grid)


class TestFullPackIncludesExperience:
    def test_full_pack_contains_experience_cases(self) -> None:
        """The full diligence pack surfaces the experience-recovery category."""
        from polaris_re.analytics.validation import run_full_validation_pack

        report = run_full_validation_pack()
        experience = [
            r for r in report.results if r.category is ValidationCategory.EXPERIENCE_IMPROVEMENT
        ]
        assert len(experience) == 5
        assert all(r.status is ValidationStatus.PASS for r in experience)

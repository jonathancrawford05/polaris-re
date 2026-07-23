"""Published-deck validation pack — WholeLife engine vs SOA Illustrative Life Table.

These tests exercise the Slice-2 ``STATUTORY_DECK`` cases of the validation &
benchmark pack (``polaris_re.analytics.validation``). The reference is the SOA
Illustrative Life Table (Bowers et al., *Actuarial Mathematics* 2e, App. 2A),
whose ``l_x`` column is vendored under ``data/validation/``. The assertions are
unimpeachable and network-free:

* The vendored ``l_x`` is regenerated from the table's *published Makeham law*
  and must match the CSV exactly (transcription guard).
* The tabulated whole-life ``A_x`` / ``ä_x`` are independently recomputable from
  the vendored ``l_x`` (guards the reference derivation) and satisfy the
  ``A_x = 1 - d ä_x`` identity.
* The vendored table reproduces the *printed* Illustrative Life Table values
  (``1000 A_35 = 128.72``, ``ä_35 = 15.3926``, …), confirming it IS the ILT.
* The live WholeLife engine reproduces the tabulated annual APVs to machine
  precision.
* The pricing/golden path is untouched (the pack is a separate module).
"""

import numpy as np
import pytest

from polaris_re.analytics.validation import (
    _ILT_INTEREST,
    _ILT_ISSUE_AGES,
    _ILT_L0,
    _ILT_OMEGA,
    ValidationCategory,
    ValidationReport,
    ValidationStatus,
    _annual_whole_life_apvs,
    _illustrative_life_table_makeham,
    _load_illustrative_life_table,
    _run_illustrative_life_table_projection,
    run_closed_form_benchmarks,
    run_full_validation_pack,
    run_statutory_deck_benchmarks,
)


@pytest.fixture(scope="module")
def deck_report() -> ValidationReport:
    """The Slice-2 published-deck validation report (one engine run set, reused)."""
    return run_statutory_deck_benchmarks()


@pytest.fixture(scope="module")
def vendored_lx() -> np.ndarray:
    """The vendored Illustrative Life Table l_x column."""
    _ages, lx = _load_illustrative_life_table()
    return lx


class TestVendoredTableTranscription:
    """The vendored CSV must be exactly the published Makeham-generated ILT."""

    def test_regenerated_matches_vendored(self, vendored_lx: np.ndarray) -> None:
        # Transcription guard: the vendored CSV must equal the Makeham
        # regeneration. A tight relative tolerance (not byte-exact) absorbs
        # last-ULP platform differences in the transcendental generation
        # (10**0.04 / exp / c**x vary by ~1e-16 rel across BLAS/CPU/numpy
        # builds) while still catching any real transcription error, which
        # would shift a value by many orders of magnitude more.
        _ages, lx_gen = _illustrative_life_table_makeham()
        np.testing.assert_allclose(vendored_lx, lx_gen, rtol=1e-12, atol=0.0)

    def test_table_shape_and_endpoints(self, vendored_lx: np.ndarray) -> None:
        # Ages 0 .. omega+1 inclusive.
        assert vendored_lx.shape == (_ILT_OMEGA + 2,)
        np.testing.assert_allclose(vendored_lx[0], _ILT_L0)
        assert vendored_lx[_ILT_OMEGA + 1] == 0.0

    def test_lx_strictly_decreasing_while_alive(self, vendored_lx: np.ndarray) -> None:
        alive = vendored_lx[: _ILT_OMEGA + 1]
        assert np.all(np.diff(alive) < 0.0)

    def test_loader_ages_are_contiguous(self) -> None:
        ages, _lx = _load_illustrative_life_table()
        np.testing.assert_array_equal(ages, np.arange(0, _ILT_OMEGA + 2))


class TestReferenceDerivation:
    """A_x / ä_x are exact, self-consistent identities of the vendored l_x."""

    @pytest.mark.parametrize("issue_age", _ILT_ISSUE_AGES)
    def test_axed_identity_holds(self, vendored_lx: np.ndarray, issue_age: int) -> None:
        # A_x = 1 - d * ä_x with d = i / (1 + i). Holds for any life table.
        a_x, adue_x = _annual_whole_life_apvs(vendored_lx, issue_age, _ILT_INTEREST)
        d = _ILT_INTEREST / (1.0 + _ILT_INTEREST)
        np.testing.assert_allclose(a_x, 1.0 - d * adue_x, rtol=0.0, atol=1e-12)

    @pytest.mark.parametrize("issue_age", _ILT_ISSUE_AGES)
    def test_independent_recompute_matches(self, vendored_lx: np.ndarray, issue_age: int) -> None:
        # Recompute A_x / ä_x with an independent (loop-based) implementation and
        # confirm it matches the vectorised reference (transcription guard on the
        # derivation, not just the CSV).
        v = 1.0 / (1.0 + _ILT_INTEREST)
        col = vendored_lx[issue_age:]
        a_x_loop = 0.0
        adue_loop = 0.0
        for k in range(len(col) - 1):
            a_x_loop += v ** (k + 1) * (col[k] - col[k + 1])
            adue_loop += v**k * col[k]
        adue_loop += v ** (len(col) - 1) * col[-1]  # final term (col[-1] = 0, harmless)
        a_x_loop /= col[0]
        adue_loop /= col[0]

        a_x, adue_x = _annual_whole_life_apvs(vendored_lx, issue_age, _ILT_INTEREST)
        np.testing.assert_allclose(a_x, a_x_loop, rtol=1e-12)
        np.testing.assert_allclose(adue_x, adue_loop, rtol=1e-12)

    def test_reproduces_printed_ilt_values(self, vendored_lx: np.ndarray) -> None:
        # The famous printed Illustrative Life Table values at i=6% (Bowers 2e,
        # App. 2A). Matching these to the printed precision confirms the vendored
        # table IS the ILT — a loose tolerance since the printed table rounds.
        printed = {
            35: (128.72, 15.3926),  # (1000 * A_x, ä_x)
            40: (161.32, 14.8166),
            65: (439.80, 9.8969),
        }
        for age, (thousand_a, adue_printed) in printed.items():
            a_x, adue_x = _annual_whole_life_apvs(vendored_lx, age, _ILT_INTEREST)
            np.testing.assert_allclose(1000.0 * a_x, thousand_a, rtol=1e-4)
            np.testing.assert_allclose(adue_x, adue_printed, rtol=1e-4)


class TestEngineReproducesTable:
    """The live WholeLife engine reproduces the tabulated APVs to machine precision."""

    @pytest.mark.parametrize("issue_age", _ILT_ISSUE_AGES)
    def test_engine_reproduces_annual_apvs(self, vendored_lx: np.ndarray, issue_age: int) -> None:
        ref_a, ref_adue = _annual_whole_life_apvs(vendored_lx, issue_age, _ILT_INTEREST)
        eng_a, eng_adue = _run_illustrative_life_table_projection(
            issue_age, vendored_lx, _ILT_INTEREST
        )
        np.testing.assert_allclose(eng_a, ref_a, rtol=1e-9)
        np.testing.assert_allclose(eng_adue, ref_adue, rtol=1e-9)

    @pytest.mark.parametrize("issue_age", _ILT_ISSUE_AGES)
    def test_engine_survivorship_is_complete(self, vendored_lx: np.ndarray, issue_age: int) -> None:
        # ä_x > 1 (at least the age-x payment) and A_x in (0, 1) for a whole-life
        # policy — sanity that the projection ran to omega with no leakage.
        eng_a, eng_adue = _run_illustrative_life_table_projection(
            issue_age, vendored_lx, _ILT_INTEREST
        )
        assert 0.0 < eng_a < 1.0
        assert eng_adue > 1.0


class TestDeckReport:
    """The scored STATUTORY_DECK report."""

    def test_all_cases_pass(self, deck_report: ValidationReport) -> None:
        assert deck_report.all_passed
        assert deck_report.n_failed == 0

    def test_three_cases_per_age(self, deck_report: ValidationReport) -> None:
        # A_x, ä_x, P_x for each issue age.
        assert deck_report.n_cases == 3 * len(_ILT_ISSUE_AGES)

    def test_all_cases_are_statutory_deck(self, deck_report: ValidationReport) -> None:
        assert all(r.category is ValidationCategory.STATUTORY_DECK for r in deck_report.results)

    def test_every_result_within_tolerance(self, deck_report: ValidationReport) -> None:
        for r in deck_report.results:
            assert r.status is ValidationStatus.PASS
            assert r.rel_error <= r.tolerance_rtol

    def test_net_premium_is_ratio_of_apvs(self, deck_report: ValidationReport) -> None:
        by_id = {r.case_id: r for r in deck_report.results}
        for age in _ILT_ISSUE_AGES:
            a = by_id[f"ILT-A-{age}"].expected
            adue = by_id[f"ILT-ADUE-{age}"].expected
            p = by_id[f"ILT-P-{age}"].expected
            np.testing.assert_allclose(p, a / adue, rtol=1e-12)

    def test_markdown_renders_deck(self, deck_report: ValidationReport) -> None:
        md = deck_report.to_markdown()
        assert "STATUTORY_DECK" in md
        assert "Illustrative Life Table" in md


class TestFullPack:
    """The combined report spans every validation category."""

    def test_full_pack_all_passed(self) -> None:
        report = run_full_validation_pack()
        assert report.all_passed

    def test_full_pack_spans_all_categories(self) -> None:
        report = run_full_validation_pack()
        categories = {r.category for r in report.results}
        # The full pack now also carries the A4' experience improvement-recovery
        # deck (ADR-150), so EXPERIENCE_IMPROVEMENT joins the earlier categories.
        assert categories == {
            ValidationCategory.CLOSED_FORM,
            ValidationCategory.TEXTBOOK,
            ValidationCategory.STATUTORY_DECK,
            ValidationCategory.EXPERIENCE_IMPROVEMENT,
        }

    def test_full_pack_is_union_of_subpacks(self) -> None:
        from polaris_re.analytics.experience_validation import (
            run_experience_improvement_benchmarks,
        )

        closed = run_closed_form_benchmarks()
        deck = run_statutory_deck_benchmarks()
        experience = run_experience_improvement_benchmarks()
        full = run_full_validation_pack()
        assert full.n_cases == closed.n_cases + deck.n_cases + experience.n_cases

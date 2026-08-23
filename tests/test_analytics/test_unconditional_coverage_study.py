"""The Anchor-7 coverage study harness — `scripts/unconditional_coverage_study.py`.

Slice 4 of `docs/PLAN_penalized_mi_surface.md`. The study itself is 200 replicates
over two truths, ~80,000 penalized fits and ~5 minutes, so it lives in a script whose
report is committed. What is testable in the default suite is everything *around* the
number: that the two truths are the objects they are documented to be, that the
verdict can actually fail, that a reduced replicate count is disclosed rather than
absorbed, and that the run is reproducible.

**A verdict function that cannot report failure is worse than no verdict**, because a
gate is the one place where an always-pass is indistinguishable from a pass. The
falsification tests below feed it fabricated rows for exactly that reason — the same
discipline ADR-186 amendment 2 arrived at when a test compared a report field against
the constant that populated it.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from unconditional_coverage_study import (
    AGES,
    DEFAULT_REPLICATES,
    NOMINAL,
    YEARS,
    CoverageRow,
    TruthResult,
    age_varying_quadratic_mi,
    build_cells,
    main,
    monte_carlo_se,
    to_markdown,
    truth_grid,
    verdict,
    year_quadratic_mi,
)


def _row(band: str, overall: float) -> CoverageRow:
    return CoverageRow(
        truth="t", band=band, overall=overall, young=overall, old=overall, mean_width=0.01
    )


def _result(
    *,
    conditional: float,
    unconditional: float,
    wps2016: float | None = None,
    ks_analytic: float | None = None,
    replicates: int = 200,
) -> TruthResult:
    """A fabricated row.

    ``wps2016`` defaults to ``unconditional`` so that the pre-existing callers, which
    predate the eq. (7) band, keep expressing what they were written to express. A test
    about the *shipped* band's verdict should not be silently converted into a test
    about a different band because a field was added.
    """
    wps = unconditional if wps2016 is None else wps2016
    analytic = unconditional if ks_analytic is None else ks_analytic
    return TruthResult(
        truth="t",
        replicates=replicates,
        conditional=_row("conditional", conditional),
        unconditional=_row("unconditional", unconditional),
        ks_analytic=_row("ks-analytic", analytic),
        wps2016=_row("wps2016", wps),
        mean_inflation_unconditional=1.14,
        mean_inflation_ks_analytic=1.14,
        mean_inflation_wps2016=1.45,
        mean_floored_wps_directions=0.0,
        log10_lambda_age_spread=1.0,
        log10_lambda_year_spread=2.0,
        mean_rejected_points=0.01,
        max_rejected_points=1,
        mean_evaluated_points=202.0,
        replicates_with_rejections=2,
        mean_floored_directions=0.0,
    )


# --------------------------------------------------------------------------- #
# The two truths are what the docstrings say they are
# --------------------------------------------------------------------------- #


def test_the_age_flat_truth_really_is_flat_in_age() -> None:
    """ADR-187's fixture, and the property amendment 1 turned on.

    The age penalty has nothing to identify on it — which is *why* λ_age's spread was
    5.50 decades there and 0.75 on the age-varying truth. If this fixture ever gained
    an age gradient, the study would silently stop measuring the regime it was chosen
    to measure.
    """
    grid = truth_grid(year_quadratic_mi)
    assert grid.shape == (len(AGES), len(YEARS) - 1)
    for column in grid.T:
        np.testing.assert_allclose(column, column[0], atol=1e-15)


def test_the_age_varying_truth_leaves_the_age_penalty_null_space() -> None:
    """Varying in age is not enough — it must vary in a way the penalty can *see*.

    **This test exists because the first version of the fixture failed it.** It used a
    *linear* age gradient, which is inside the second-difference penalty's null space
    along the age margin: λ_age → ∞ costs nothing there, so the "age-varying" truth
    reproduced exactly the degeneracy the "age-flat" truth was chosen to exhibit, and
    the study's two rows were one row measured twice. A non-zero *second* difference in
    age is the property that makes them different objects, so that is what is asserted
    rather than "the values differ across ages", which the broken fixture also passed.

    Both truths still carry the identical year curve, which is what makes the pair a
    controlled comparison rather than two unrelated measurements.
    """
    grid = truth_grid(age_varying_quadratic_mi)
    age_profile = grid.mean(axis=1)
    second_difference = np.diff(age_profile, n=2)
    assert np.max(np.abs(second_difference)) > 1e-8, (
        "the age profile is linear (or flat), so it sits inside the age penalty's null "
        f"space and lambda_age is unidentifiable: second differences {second_difference}"
    )

    flat = truth_grid(year_quadratic_mi)
    np.testing.assert_allclose(np.diff(np.mean(flat, axis=1), n=2), 0.0, atol=1e-15)

    year_shape_varying = grid.mean(axis=0) - grid.mean(axis=0).mean()
    year_shape_flat = flat.mean(axis=0) - flat.mean(axis=0).mean()
    np.testing.assert_allclose(year_shape_varying, year_shape_flat, atol=1e-12)


def test_the_study_fixture_is_the_same_object_as_the_test_modules() -> None:
    """The one assertion that licenses quoting ADR-187's delta-method row beside these.

    `docs/MEASUREMENT_unconditional_coverage.md` prints the unpenalized band's 0.9586
    next to this study's 0.8516 and calls it "the identical truth and the identical
    replicate seeds". That claim rests entirely on the study's `build_cells` /
    `year_quadratic_mi` generating the same frames as the test module's `_cells_from` /
    `_quadratic_mi` — and they are **duplicated source**, agreeing today because they
    were copied, with nothing holding them together (PR #190 review [P2]).

    So this pins it. If either copy is edited, the 10-point interval gap stops being a
    paired comparison and becomes two studies stapled together — and this fails first,
    which is the point. Frames are compared exactly: identical arithmetic and identical
    RNG draw order must give identical Poisson draws, not merely close ones.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_sibling_penalized_tests",
        Path(__file__).with_name("test_experience_gam_penalized.py"),
    )
    assert spec is not None and spec.loader is not None
    sibling = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sibling)

    for seed in (1000, 1199):
        np.testing.assert_array_equal(
            build_cells(year_quadratic_mi, seed=seed).to_numpy(),
            sibling._cells_from(sibling._quadratic_mi, seed=seed).to_numpy(),
            err_msg=f"the two fixture copies diverged at seed {seed}",
        )

    # And the truths themselves, before any sampling — a difference here would be
    # masked by the frames matching only because both copies changed together.
    np.testing.assert_allclose(
        truth_grid(year_quadratic_mi),
        np.array(
            [[sibling._quadratic_mi(float(a), int(y)) for y in YEARS[1:]] for a in AGES],
            dtype=np.float64,
        ),
        rtol=0.0,
        atol=0.0,
    )


def test_the_fixture_is_seeded_and_not_clock_dependent() -> None:
    """Two builds at one seed agree exactly; two seeds do not (ADR-074)."""
    first = build_cells(year_quadratic_mi, seed=4242)
    again = build_cells(year_quadratic_mi, seed=4242)
    other = build_cells(year_quadratic_mi, seed=4243)

    assert first.equals(again)
    assert not first.equals(other)


# --------------------------------------------------------------------------- #
# The gate can fail
# --------------------------------------------------------------------------- #


def test_the_verdict_passes_only_when_every_truth_clears_the_floor() -> None:
    """One truth clearing and the other not is a FAIL, not an average.

    Anchor 7 licenses a *label*, and a label that is right on one fixture and wrong on
    another has not been earned. Written as three fabricated cases because the real
    study takes five minutes and a gate whose failure branch has never executed is a
    gate nobody has tested.
    """
    floor = NOMINAL - 2.0 * monte_carlo_se(200)
    assert 0.90 < floor < NOMINAL

    both_clear = [_result(conditional=0.87, unconditional=0.86, wps2016=0.951)] * 2
    assert "GATE PASSED" in verdict(both_clear)

    one_short = [
        _result(conditional=0.87, unconditional=0.86, wps2016=0.96),
        _result(conditional=0.87, unconditional=0.86, wps2016=floor - 0.01),
    ]
    assert "GATE NOT PASSED" in verdict(one_short)
    assert "FAIL" in verdict(one_short)

    none_clear = [_result(conditional=0.87, unconditional=0.86, wps2016=0.80)] * 2
    assert "GATE NOT PASSED" in verdict(none_clear)


def test_the_verdict_reads_the_wps_band_and_not_the_shipped_one() -> None:
    """The gate is on eq. (7), and a passing shipped band cannot carry it.

    Written because the band under test *changed* on 2026-08-23. The previous verdict
    keyed off ``unconditional``; if that reading survived anywhere, a run in which the
    shipped Kass-Steffey band happened to clear would report GATE PASSED while the
    band actually being proposed had not. The two arguments below differ only in which
    field holds the good number.
    """
    good_wps = [_result(conditional=0.87, unconditional=0.80, wps2016=0.96)] * 2
    good_shipped = [_result(conditional=0.87, unconditional=0.96, wps2016=0.80)] * 2

    assert "GATE PASSED" in verdict(good_wps)
    assert "GATE NOT PASSED" in verdict(good_shipped)


def test_the_registered_prediction_can_be_refuted() -> None:
    """ADR-190 decision 4's falsifying branch executes.

    The prediction was written before the answer existed: a larger correction should
    move coverage **up**. A resolver that could only print CONFIRMED would make that
    unfalsifiable after the fact — the precise failure ADR-186 amendment 2 found when a
    test compared a report field against the constant that populated it. So the
    refuting case is fabricated and asserted here, and the wording it produces names
    the consequence ADR-190 itself specified.
    """
    from unconditional_coverage_study import prediction_verdict

    moved_up_and_cleared = [_result(conditional=0.85, unconditional=0.86, wps2016=0.94)] * 2
    assert "CONFIRMED IN FULL" in prediction_verdict(moved_up_and_cleared)

    # The outcome that actually occurred, and the one an earlier draft of the
    # resolver would have mislabelled: coverage rises, the gate still fails. A
    # 3-point move onto a 10-point shortfall is not a diagnosis confirmed.
    moved_up_but_short = [_result(conditional=0.75, unconditional=0.78, wps2016=0.82)] * 2
    partial = prediction_verdict(moved_up_but_short)
    assert "CONFIRMED IN DIRECTION, REFUTED IN SUFFICIENCY" in partial
    assert "**a** gap and not **the** gap" in partial
    assert "Coverage is not a reason to re-point production" in partial
    assert "CONFIRMED IN FULL" not in partial

    moved_down = [_result(conditional=0.85, unconditional=0.86, wps2016=0.84)] * 2
    body = prediction_verdict(moved_down)
    assert "REFUTED" in body
    assert "decision 1 needs re-examining" in body
    assert "Do not re-point production" in body

    # Unchanged is not "moved toward the floor" either: eq. (7) adding nothing would
    # mean V'' is not being assembled, which is a refutation and not a pass.
    unchanged = [_result(conditional=0.85, unconditional=0.86, wps2016=0.86)] * 2
    assert "REFUTED" in prediction_verdict(unchanged)

    # One truth moving up and the other down is a refutation, not an average.
    split = [
        _result(conditional=0.85, unconditional=0.86, wps2016=0.94),
        _result(conditional=0.85, unconditional=0.86, wps2016=0.84),
    ]
    assert "REFUTED" in prediction_verdict(split)


def test_the_floor_widens_as_replicates_fall() -> None:
    """Fewer replicates, noisier estimate, more forgiving floor — and it must say so.

    A gate that used a fixed floor regardless of replicate count would reject a good
    band on a short run and accept a bad one on a shorter one.
    """
    assert monte_carlo_se(50) > monte_carlo_se(200) > monte_carlo_se(1000)
    np.testing.assert_allclose(monte_carlo_se(200), np.sqrt(0.95 * 0.05 / 200), rtol=1e-12)


# --------------------------------------------------------------------------- #
# A reduced study discloses itself
# --------------------------------------------------------------------------- #


def test_a_reduced_replicate_count_is_disclosed_in_the_report() -> None:
    """PLAN slice 4: *"if it is reduced say so in the report"*.

    Asserted both ways. A full-count run must NOT carry the reduction notice, or the
    notice stops carrying information — the failure mode where a warning printed
    always is a warning read never.
    """
    reduced = to_markdown([_result(conditional=0.87, unconditional=0.95, replicates=25)], gamma=1.0)
    assert "reduced from the planned" in reduced
    assert "**Replicates:** 25" in reduced

    full = to_markdown(
        [_result(conditional=0.87, unconditional=0.95, replicates=DEFAULT_REPLICATES)], gamma=1.0
    )
    assert "reduced from the planned" not in full
    assert f"**Replicates:** {DEFAULT_REPLICATES}" in full


def test_the_report_states_the_verification_status_of_the_band_it_reports() -> None:
    """PLAN Anchor 8, in its post-ADR-202 form.

    **This test previously asserted the opposite string.** Until 2026-08-23 the report
    had to say the correction was "adopted from `mgcv` and unverified", because it was:
    Anchor 8 forbids describing an adopted quantity as verified until something
    measures it. ADR-202 measured it — `unconditional_covariance` against
    `vcov(m, unconditional = TRUE)` on the tier-3 pinned oracle, 0.023-0.904%
    element-wise — so the caveat became false and keeping it would have been its own
    kind of misreporting.

    What replaces it is not silence. The report must still separate the two claims,
    because "this is the same object `mgcv` computes" and "this object is
    well-calibrated" are different statements and the whole study exists to measure
    the second one.
    """
    body = to_markdown([_result(conditional=0.87, unconditional=0.95)], gamma=1.0)
    assert "adopted from `mgcv` and unverified" not in body
    assert "verified against `mgcv`" in body
    assert "ADR-202" in body
    assert "different claims" in body


def test_the_report_states_that_no_production_path_changed() -> None:
    """PLAN Anchor 7 of `PLAN_mgcv_parity_engine.md`, made checkable.

    The two new bands are computed by a module that reads a production fit rather than
    by an edited production path, and a reader of the committed measurement cannot
    verify that from the numbers. Stating it is the only way the claim travels with the
    document — and a test is the only way the statement survives an edit.
    """
    body = to_markdown([_result(conditional=0.87, unconditional=0.95)], gamma=1.0)
    assert "No production path changed" in body
    assert "gam_uncertainty_mi" in body


def test_the_report_separates_the_two_mechanisms() -> None:
    """The `ks-analytic` row must be present and explained, not just computed.

    It is the row that licenses attributing a coverage movement to the formula rather
    than to the derivative method. A report that dropped it would still print a
    coverage change, and a reader would have no way to tell which of the two changes
    produced it.
    """
    body = to_markdown([_result(conditional=0.87, unconditional=0.95)], gamma=1.0)
    assert "ks-analytic" in body
    assert "two mechanisms" in body


# --------------------------------------------------------------------------- #
# End to end, at a replicate count the default suite can afford
# --------------------------------------------------------------------------- #


def test_the_script_runs_end_to_end_and_repeats_itself(tmp_path: Path) -> None:
    """Two runs, byte-identical JSON — the reproducibility ADR-074 requires.

    Three replicates on one truth: far too few for a coverage figure, which is why
    this asserts on *structure and repeatability* and never on the rate. The rate
    comes from the committed report.
    """
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    report = tmp_path / "a.md"

    assert (
        main(
            [
                "-o",
                str(first),
                "--markdown",
                str(report),
                "--replicates",
                "3",
                "--truth",
                "age-flat",
            ]
        )
        == 0
    )
    assert main(["-o", str(second), "--replicates", "3", "--truth", "age-flat"]) == 0

    assert first.read_text() == second.read_text()

    payload = json.loads(first.read_text())
    assert payload["replicates"] == 3
    assert payload["nominal"] == NOMINAL
    assert len(payload["truths"]) == 1
    truth = payload["truths"][0]
    assert truth["truth"] == "age-flat"
    assert 0.0 <= truth["conditional"]["overall"] <= 1.0
    assert truth["unconditional"]["mean_width"] >= truth["conditional"]["mean_width"], (
        "the unconditional band cannot be narrower — the correction is additive and PSD"
    )
    assert truth["wps2016"]["mean_width"] >= truth["unconditional"]["mean_width"], (
        "eq. (7) adds V'' on top of the Kass-Steffey term, so its band cannot be "
        "narrower than the shipped one"
    )
    assert truth["mean_inflation_wps2016"] > truth["mean_inflation_unconditional"], (
        "the eq. (7) correction must inflate more than plain Kass-Steffey — ADR-190 "
        "measured the gap at 3.2-4.1x against mgcv"
    )
    assert "reduced from the planned" in report.read_text()


def test_a_zero_replicate_run_is_refused(tmp_path: Path) -> None:
    assert main(["-o", str(tmp_path / "x.json"), "--replicates", "0"]) == 1


# --------------------------------------------------------------------------- #
# The gate itself, at the plan's replicate count
# --------------------------------------------------------------------------- #


@pytest.mark.slow
def test_unconditional_coverage_of_the_shipped_procedure() -> None:
    """PLAN slice 4's gate test — select λ per replicate, fit, count.

    Marked slow because it is ~40 replicates x ~211 penalized fits per truth. The
    committed `docs/MEASUREMENT_unconditional_coverage.md` carries the 200-replicate
    figures; this pins what must remain true of them:

    1. **The study completes at all.** Before slice 4, a single non-converging grid
       point aborted it (ADR-187 finding 5) — which is exactly why the unconditional
       study was undeliverable in slice 3.
    2. **The correction widens, never narrows.**
    3. **It moves coverage toward nominal, not away.** The direction is the claim;
       the decimals belong to the committed report, and at 40 replicates the
       Monte-Carlo SE is ~3.4pp.
    """
    from unconditional_coverage_study import run_truth

    result = run_truth("age-varying", replicates=40)

    assert result.unconditional.mean_width > result.conditional.mean_width
    assert result.unconditional.overall >= result.conditional.overall, (
        f"the Kass-Steffey correction moved coverage DOWN "
        f"({result.conditional.overall:.4f} -> {result.unconditional.overall:.4f}), "
        "which an additive PSD term cannot do"
    )
    assert result.mean_evaluated_points > 100

    # ADR-190 decision 4's direction, at a replicate count the suite can afford. The
    # decimals belong to the committed 200-replicate report; what is pinned here is
    # that eq. (7) widens further and does not move coverage down.
    assert result.wps2016.mean_width > result.unconditional.mean_width
    assert result.wps2016.overall >= result.unconditional.overall, (
        f"eq. (7) moved coverage DOWN "
        f"({result.unconditional.overall:.4f} -> {result.wps2016.overall:.4f}); it "
        "adds a PSD term to the same covariance, so it cannot"
    )
    assert result.mean_inflation_wps2016 > result.mean_inflation_ks_analytic

    # Mechanism 2 is the small one — analytic and finite-difference J, same formula.
    # If this ever fails, the coverage study's attribution of movement to the formula
    # stops being licensed and the report's claim must be rewritten before it ships.
    analytic_gap = abs(result.mean_inflation_ks_analytic - result.mean_inflation_unconditional)
    formula_gap = abs(result.mean_inflation_wps2016 - result.mean_inflation_ks_analytic)
    assert analytic_gap < 0.2 * formula_gap, (
        f"the derivative-method change ({analytic_gap:.4f}) is not small against the "
        f"formula change ({formula_gap:.4f}), so a coverage movement can no longer be "
        "attributed to eq. (7) rather than to the switch from central differences"
    )

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


def _result(*, conditional: float, unconditional: float, replicates: int = 200) -> TruthResult:
    return TruthResult(
        truth="t",
        replicates=replicates,
        conditional=_row("conditional", conditional),
        unconditional=_row("unconditional", unconditional),
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

    both_clear = [_result(conditional=0.87, unconditional=0.951)] * 2
    assert "GATE PASSED" in verdict(both_clear)

    one_short = [
        _result(conditional=0.87, unconditional=0.96),
        _result(conditional=0.87, unconditional=floor - 0.01),
    ]
    assert "GATE NOT PASSED" in verdict(one_short)
    assert "FAIL" in verdict(one_short)

    none_clear = [_result(conditional=0.87, unconditional=0.80)] * 2
    assert "GATE NOT PASSED" in verdict(none_clear)


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


def test_the_report_states_the_adopted_not_verified_caveat() -> None:
    """PLAN Anchor 8: nothing taken from mgcv is described as verified until slice 5.

    The correction, the covariance and gamma are all adopted. A measurement document that
    quotes their numbers without that sentence reads as though the implementation had
    been checked against the reference it was copied from.
    """
    body = to_markdown([_result(conditional=0.87, unconditional=0.95)], gamma=1.0)
    assert "adopted from `mgcv` and unverified" in body
    assert "Anchor 8" in body


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

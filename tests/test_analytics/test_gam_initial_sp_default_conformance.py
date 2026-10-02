"""Ladder slice 3e (ADR-240): the two-start selection rule and the passthrough
of ``initial_sp_start`` on every free-scale conformance fit helper."""

import inspect

import pytest

from polaris_re.analytics.gam_initial_sp_default_conformance import (
    CELLS,
    StartComparison,
    best_of_two,
)


def _reading(start: str, score: float, agrees: bool) -> StartComparison:
    return StartComparison(
        cell="c",
        start=start,
        max_abs_eta_diff=0.0 if agrees else 1.0,
        edf_total_diff=0.0,
        max_abs_log10_sp_diff=0.0,
        agrees=agrees,
        own_reml_score=score,
        at_bound=False,
    )


@pytest.mark.parametrize(
    ("score_a", "score_b", "expected"),
    [(1.0, 2.0, "centre"), (2.0, 1.0, "seeded"), (1.5, 1.5, "centre")],
)
def test_best_of_two_keeps_the_lower_own_criterion_score(
    score_a: float, score_b: float, expected: str
) -> None:
    a = _reading("centre", score_a, agrees=expected == "centre")
    b = _reading("seeded", score_b, agrees=expected == "seeded")
    best = best_of_two(a, b)
    assert expected in best.start
    assert best.own_reml_score == min(score_a, score_b)
    assert best.agrees  # the kept reading is the one built to agree


def test_best_of_two_never_reads_agreement() -> None:
    """The rule is own-criterion only: a lower score wins even if it disagrees."""
    a = _reading("centre", 1.0, agrees=False)
    b = _reading("seeded", 2.0, agrees=True)
    assert not best_of_two(a, b).agrees


@pytest.mark.parametrize("cell", sorted(CELLS))
def test_every_free_scale_fit_helper_accepts_initial_sp_start(cell: str) -> None:
    fit, _ = CELLS[cell]
    param = inspect.signature(fit).parameters["initial_sp_start"]
    assert param.default is False

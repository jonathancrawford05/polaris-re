"""Outer-solver slice 0 (ADR-241): closed-form checks of the landscape probe's
segment profile and central-difference gradient, on functions whose answers are
known exactly."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from gam_outer_solver_landscape_probe import central_gradient, first_move, segment_profile


def _bowl(x: np.ndarray) -> float:
    """Convex quadratic with its minimum at the origin, value 0."""
    return float(np.sum(np.asarray(x, dtype=np.float64) ** 2))


def test_segment_into_a_convex_bowl_has_no_barrier() -> None:
    a = np.array([2.0, -1.0], dtype=np.float64)
    b = np.zeros(2, dtype=np.float64)
    profile = segment_profile(_bowl, a, b, n=11, rise_tol=1e-12)
    np.testing.assert_allclose(profile.score[0], 5.0)
    np.testing.assert_allclose(profile.score[-1], 0.0, atol=1e-15)
    np.testing.assert_allclose(profile.descent, 5.0)
    np.testing.assert_allclose(profile.barrier, 0.0)
    assert profile.n_rises == 0


def _double_well(x: np.ndarray) -> float:
    """(x^2 - 1)^2 in one dimension: minima at -1 and +1, barrier of height 1 at 0."""
    v = float(np.asarray(x, dtype=np.float64)[0])
    return (v * v - 1.0) ** 2


def test_segment_across_a_double_well_reports_the_barrier_height() -> None:
    profile = segment_profile(
        _double_well,
        np.array([-1.0], dtype=np.float64),
        np.array([1.0], dtype=np.float64),
        n=21,
        rise_tol=1e-12,
    )
    np.testing.assert_allclose(profile.barrier, 1.0)  # t=0.5 is x=0 exactly
    np.testing.assert_allclose(profile.descent, 0.0, atol=1e-15)
    assert profile.n_rises == 10


def test_central_gradient_is_exact_on_a_quadratic() -> None:
    x = np.array([0.3, -2.0, 5.0], dtype=np.float64)
    np.testing.assert_allclose(central_gradient(_bowl, x, h=0.01), 2.0 * x, rtol=1e-10)


def test_central_gradient_goes_one_sided_at_the_upper_bound() -> None:
    """Backward difference of x^2 at x=12 with h: (144 - (12-h)^2)/h = 24 - h."""
    x = np.array([12.0], dtype=np.float64)
    np.testing.assert_allclose(central_gradient(_bowl, x, h=0.01, upper=12.0), [24.0 - 0.01])


def test_first_move_skips_finite_difference_probes_and_measures_the_step() -> None:
    start = np.array([2.0, 3.0], dtype=np.float64)
    trace = [
        start,
        start + np.array([1.5e-8, 0.0], dtype=np.float64),  # a gradient probe, not a move
        np.array([10.0, 12.0], dtype=np.float64),  # the move: 9 decades, one coord at bound
        np.array([9.0, 11.0], dtype=np.float64),
    ]
    move = first_move(trace, upper=12.0)
    np.testing.assert_allclose(move.point, [10.0, 12.0])
    np.testing.assert_allclose(move.max_abs_step, 9.0)
    assert move.n_at_upper == 1


def test_first_move_on_a_search_that_never_moves() -> None:
    start = np.array([1.0], dtype=np.float64)
    move = first_move([start, start + 1e-9], upper=12.0)
    np.testing.assert_allclose(move.max_abs_step, 0.0)


def test_first_move_counts_lower_bound_hits() -> None:
    """PR #250 review [P2]: a move onto the LOWER bound is reported, not read by hand."""
    trace = [np.array([5.0, 5.0], dtype=np.float64), np.array([-2.0, 9.8], dtype=np.float64)]
    move = first_move(trace, upper=12.0, lower=-2.0)
    assert move.n_at_lower == 1
    assert move.n_at_upper == 0
    np.testing.assert_allclose(move.max_abs_step, 7.0)

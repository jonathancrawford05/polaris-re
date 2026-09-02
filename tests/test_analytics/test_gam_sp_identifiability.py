"""PLAN slice 7c Part 2 (ADR-219): the Hessian-weighted distance, verified
against closed forms rather than against another implementation of itself.

R-free throughout — nothing here needs `mgcv`, because nothing here is a
comparison (see `gam_sp_identifiability`'s own module docstring).
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_sp_identifiability import (
    hessian_weighted_distance,
    identified_direction_count,
)
from polaris_re.core.exceptions import PolarisValidationError


def test_identity_hessian_reduces_to_the_euclidean_norm() -> None:
    """Closed form: with ``H = I`` the weighted distance IS ``||Δ||₂``."""
    delta = np.array([3.0, 4.0], dtype=np.float64)
    got = hessian_weighted_distance(delta, np.eye(2, dtype=np.float64))
    np.testing.assert_allclose(got, 5.0, rtol=0.0, atol=1e-12)


def test_diagonal_hessian_matches_the_hand_computed_quadratic_form() -> None:
    """Closed form: for diagonal ``H``, the distance is ``sqrt(Σ hⱼ Δⱼ²)``."""
    delta = np.array([2.0, -1.0, 0.5], dtype=np.float64)
    h = np.diag(np.array([4.0, 9.0, 16.0], dtype=np.float64))
    expected = np.sqrt(4.0 * 4.0 + 9.0 * 1.0 + 16.0 * 0.25)
    np.testing.assert_allclose(hessian_weighted_distance(delta, h), expected, rtol=0.0, atol=1e-12)


def test_a_displacement_along_a_flat_direction_costs_nothing() -> None:
    """The whole point of the metric: a direction the criterion does not
    resolve contributes zero, however many decades the raw log difference is.
    Slice 7b's own residual is exactly this shape."""
    h = np.diag(np.array([1.0, 0.0], dtype=np.float64))
    huge_along_flat = np.array([0.0, 25.0], dtype=np.float64)
    # Exactness IS the documented contract here ("0.0 exactly when delta_rho
    # lies entirely in the clipped subspace"), so the tolerance is zero — but
    # stated through assert_allclose, per CLAUDE.md's ban on float `==`.
    np.testing.assert_allclose(
        hessian_weighted_distance(huge_along_flat, h), 0.0, rtol=0.0, atol=0.0
    )


def test_a_negative_eigenvalue_from_the_noise_floor_is_clipped_not_propagated() -> None:
    """A finite-difference Hessian returns small negatives on flat directions
    (slice 7c Part 0 measured -8.7e-3 and -3.5e-3). Clipping them keeps the
    quadratic form non-negative; propagating them would make a distance
    imaginary, or — worse — silently shrink it."""
    h = np.diag(np.array([1.0, -0.5], dtype=np.float64))
    delta = np.array([1.0, 10.0], dtype=np.float64)
    # Unclipped this would be 1*1 + (-0.5)*100 = -49, i.e. sqrt of a negative.
    np.testing.assert_allclose(hessian_weighted_distance(delta, h), 1.0, rtol=0.0, atol=1e-12)


def test_rotated_hessian_gives_the_same_distance_as_the_diagonal_one() -> None:
    """Invariance: the metric is a property of the quadratic form, not of the
    basis it happens to be written in."""
    evals = np.array([2.0, 0.25], dtype=np.float64)
    theta = 0.7
    q = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]], dtype=np.float64
    )
    delta_diag = np.array([1.5, -2.0], dtype=np.float64)
    plain = hessian_weighted_distance(delta_diag, np.diag(evals))
    rotated = hessian_weighted_distance(q @ delta_diag, q @ np.diag(evals) @ q.T)
    np.testing.assert_allclose(plain, rotated, rtol=1e-12, atol=1e-12)


def test_floor_discards_directions_below_the_criterion_s_resolution() -> None:
    h = np.diag(np.array([1.0, 1.0e-4], dtype=np.float64))
    delta = np.array([1.0, 1.0], dtype=np.float64)
    np.testing.assert_allclose(
        hessian_weighted_distance(delta, h), np.sqrt(1.0 + 1.0e-4), rtol=0.0, atol=1e-12
    )
    np.testing.assert_allclose(
        hessian_weighted_distance(delta, h, floor=1.0e-3), 1.0, rtol=0.0, atol=1e-12
    )


def test_identified_direction_count_reads_the_spectrum() -> None:
    h = np.diag(np.array([2.0, 0.0, -1.0e-3, 5.0], dtype=np.float64))
    assert identified_direction_count(h) == 2
    assert identified_direction_count(np.eye(4, dtype=np.float64)) == 4


def test_rejects_a_non_square_or_asymmetric_hessian() -> None:
    with pytest.raises(PolarisValidationError, match="square"):
        hessian_weighted_distance(np.zeros(2), np.zeros((2, 3)))
    with pytest.raises(PolarisValidationError, match="symmetric"):
        hessian_weighted_distance(np.zeros(2), np.array([[1.0, 2.0], [0.0, 1.0]]))


def test_rejects_a_delta_that_does_not_match_the_hessian() -> None:
    with pytest.raises(PolarisValidationError, match="expected"):
        hessian_weighted_distance(np.zeros(3), np.eye(2, dtype=np.float64))

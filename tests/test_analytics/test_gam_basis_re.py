"""Closed-form checks for the ``bs="re"`` basis (capability ladder rung L2,
``docs/PLAN_mgcv_capability_ladder.md`` slice 2).

Compares against the ALGEBRA, not against ``mgcv`` — this repo's own
convention (CLAUDE.md §5: "every actuarial/numerical calculation must have at
least one closed-form verification test"). The ``mgcv``-parity comparison
itself lives in ``test_gam_re_conformance.py`` (Stage B) and the R-side
``smoothCon()`` comparison runs in the CI workflow's compare job (Stage A).
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_basis_re import re_basis
from polaris_re.core.exceptions import PolarisValidationError


def test_design_is_the_level_indicator_matrix() -> None:
    group = np.array([0, 2, 1, 0, 2], dtype=np.int64)
    design, _s = re_basis(group, n_levels=3)

    expected = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    np.testing.assert_array_equal(design, expected)
    # Every row sums to exactly 1 — one, and only one, level indicator fires.
    np.testing.assert_array_equal(design.sum(axis=1), np.ones(5))


def test_penalty_is_exactly_the_identity() -> None:
    group = np.array([0, 1, 2, 3], dtype=np.int64)
    _, s = re_basis(group, n_levels=4)
    np.testing.assert_array_equal(s, np.eye(4))


def test_rank_is_full_the_level_count() -> None:
    group = np.array([0, 1, 2, 0, 1, 2], dtype=np.int64)
    _, s = re_basis(group, n_levels=3)
    assert np.linalg.matrix_rank(s) == 3


def test_one_penalty_block_regardless_of_level_count() -> None:
    """``docs/MGCV_NOTATION_PRIMER.md`` §4: a ``re`` term carries exactly ONE
    smoothing parameter no matter how many levels — unlike ``sz``, which
    carries one block per level. Pinned here as the shape :func:`re_basis`
    returns: a single ``(n_levels, n_levels)`` block, not one per level."""
    for n_levels in (2, 3, 8):
        group = np.zeros(10, dtype=np.int64)
        group[:n_levels] = np.arange(n_levels)
        _, s = re_basis(group, n_levels=n_levels)
        assert s.shape == (n_levels, n_levels)


def test_width_is_n_levels_not_the_observed_level_count() -> None:
    """Anchor 4: a level absent from one particular sample must not silently
    shrink the term. Every row here is level 0, but n_levels=5 is an input."""
    group = np.zeros(20, dtype=np.int64)
    design, s = re_basis(group, n_levels=5)
    assert design.shape == (20, 5)
    assert s.shape == (5, 5)
    # Columns 1-4 are all zero (no row observed those levels) but they exist.
    np.testing.assert_array_equal(design[:, 1:], np.zeros((20, 4)))


@pytest.mark.parametrize("n_levels", [0, 1])
def test_fewer_than_two_levels_is_refused(n_levels: int) -> None:
    with pytest.raises(PolarisValidationError, match="at least 2 factor levels"):
        re_basis(np.array([0, 0], dtype=np.int64), n_levels=n_levels)


def test_a_group_code_outside_range_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match=r"must lie in \[0, 3\)"):
        re_basis(np.array([0, 1, 3], dtype=np.int64), n_levels=3)
    with pytest.raises(PolarisValidationError, match=r"must lie in \[0, 3\)"):
        re_basis(np.array([-1, 1, 2], dtype=np.int64), n_levels=3)

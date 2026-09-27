"""Closed-form checks for the unpenalized parametric block (capability ladder
rung L4, ``docs/PLAN_mgcv_capability_ladder.md`` slice 5).

Compares against the ALGEBRA, not against ``mgcv`` — this repo's own
convention (CLAUDE.md §5: "every actuarial/numerical calculation must have at
least one closed-form verification test"). The ``mgcv``-parity comparisons
themselves live in ``test_gam_parametric_conformance.py`` (Stage B) and the
R-side ``model.matrix()`` comparison runs in the CI workflow's compare job
(Stage A).
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_basis_parametric import parametric_design
from polaris_re.core.exceptions import PolarisValidationError


def test_main_effect_drops_the_reference_level() -> None:
    """A single 3-level factor: contr.treatment drops level 0, keeps one 0/1
    indicator column per remaining level, in level order."""
    group = np.array([0, 1, 2, 0, 1, 2], dtype=np.int64)
    design = parametric_design((group,), (3,))
    expected = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )
    np.testing.assert_array_equal(design, expected)


def test_interaction_matches_r_model_matrix_reference_reading() -> None:
    """``model.matrix(~A + B + A:B)`` on a 3-level/2-level factor pair, measured
    directly against R before this module was written (module docstring):

    >>> A <- factor(c("a0","a1","a2","a0","a1","a2"), levels=c("a0","a1","a2"))
    >>> B <- factor(c("b0","b0","b0","b1","b1","b1"), levels=c("b0","b1"))
    >>> model.matrix(~A + B + A:B, data.frame(A=A,B=B))
    (Intercept) Aa1 Aa2 Bb1 Aa1:Bb1 Aa2:Bb1
              1   0   0   0       0       0
              1   1   0   0       0       0
              1   0   1   0       0       0
              1   0   0   1       0       0
              1   1   0   1       1       0
              1   0   1   1       0       1

    This test pins the interaction block (the last two columns) exactly,
    including the first-named-variable-fastest column order.
    """
    a = np.array([0, 1, 2, 0, 1, 2], dtype=np.int64)
    b = np.array([0, 0, 0, 1, 1, 1], dtype=np.int64)
    interaction = parametric_design((a, b), (3, 2))
    expected = np.array(
        [
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )
    np.testing.assert_array_equal(interaction, expected)


def test_first_named_variable_varies_fastest_with_three_variables() -> None:
    """A synthetic 3-way check (no R equivalent needed — this pins the
    module's own generalisation of the 2-variable rule): adding a third
    variable folds it in as the new SLOWEST axis, so the first variable
    named stays fastest throughout."""
    a = np.array([0, 1], dtype=np.int64)  # 2 levels -> 1 dummy column
    b = np.array([0, 1], dtype=np.int64)  # 2 levels -> 1 dummy column
    c = np.array([1, 1], dtype=np.int64)  # 3 levels -> 2 dummy columns
    design = parametric_design((a, b, c), (2, 2, 3))
    # width = 1 * 1 * 2 = 2
    assert design.shape == (2, 2)
    # Row 0: a=0,b=0,c=1 -> every main-effect dummy for a and b is 0, so the
    # whole interaction is 0 regardless of c.
    np.testing.assert_array_equal(design[0], [0.0, 0.0])
    # Row 1: a=1,b=1,c=1 -> a's dummy=1, b's dummy=1, c's dummy for level 1 is
    # column 0 of c's own 2-column dummy (c has 3 levels, drops level 0).
    np.testing.assert_array_equal(design[1], [1.0, 0.0])


def test_width_is_the_product_of_levels_minus_one() -> None:
    a = np.zeros(10, dtype=np.int64)
    b = np.zeros(10, dtype=np.int64)
    design = parametric_design((a, b), (4, 3))
    assert design.shape == (10, 3 * 2)


def test_single_variable_needs_no_fold() -> None:
    """``len(groups) == 1``: the loop that folds in additional variables
    never runs, and the design is exactly that one variable's own dummy
    columns."""
    group = np.array([0, 1, 0, 1], dtype=np.int64)
    design = parametric_design((group,), (2,))
    np.testing.assert_array_equal(design, np.array([[0.0], [1.0], [0.0], [1.0]]))


def test_no_variables_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="at least one variable"):
        parametric_design((), ())


def test_mismatched_groups_and_levels_length_is_refused() -> None:
    group = np.zeros(4, dtype=np.int64)
    with pytest.raises(PolarisValidationError, match="one level count per variable"):
        parametric_design((group, group), (3,))


def test_fewer_than_two_levels_is_refused() -> None:
    group = np.zeros(4, dtype=np.int64)
    with pytest.raises(PolarisValidationError, match="at least 2 levels"):
        parametric_design((group,), (1,))


def test_mismatched_row_counts_is_refused() -> None:
    a = np.zeros(4, dtype=np.int64)
    b = np.zeros(5, dtype=np.int64)
    with pytest.raises(PolarisValidationError, match="same number of rows"):
        parametric_design((a, b), (2, 2))


def test_a_group_code_outside_range_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match=r"must lie in \[0, 3\)"):
        parametric_design((np.array([0, 1, 3], dtype=np.int64),), (3,))
    with pytest.raises(PolarisValidationError, match=r"must lie in \[0, 3\)"):
        parametric_design((np.array([-1, 1, 2], dtype=np.int64),), (3,))

"""Tests for :mod:`polaris_re.analytics.gam_basis_cr` (mgcv-parity engine, slice 2).

Two kinds of coverage, mirroring the sibling Stage-A test modules:

* pure Python, closed-form invariants that hold by construction independent of
  ``mgcv`` — a natural cubic spline reproduces a linear function exactly (so the
  design times linear knot values equals the line, and the penalty quadratic form
  on those same values is exactly zero, since a line has zero curvature) — plus
  the validation/refusal paths;
* the R-gated end-to-end comparison against ``mgcv``'s own ``smoothCon()`` lives in
  ``test_gam_stage_a.py`` alongside the other Stage-A harness proofs, since it
  needs the R script's JSON payload the same way those tests do.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_basis_cr import (
    _r_norm_inf,
    _r_norm_one,
    absorb_sum_to_zero_constraint,
    by_scale_design,
    cr_basis,
    cr_default_knots,
    sum_to_zero_null_space,
    ti_basis,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

# --- cr_default_knots -------------------------------------------------------------


def test_default_knots_span_the_data_range() -> None:
    x = np.linspace(0.0, 10.0, 200, dtype=np.float64)
    knots = cr_default_knots(x, 8)
    assert knots.shape == (8,)
    assert knots[0] == pytest.approx(0.0)
    assert knots[-1] == pytest.approx(10.0)
    assert np.all(np.diff(knots) > 0)


def test_default_knots_use_only_unique_values() -> None:
    # Heavy duplication: 50 unique values repeated, still enough for k=5 knots.
    x = np.repeat(np.arange(50, dtype=np.float64), 10)
    knots = cr_default_knots(x, 5)
    assert knots.shape == (5,)


def test_default_knots_refuses_k_below_three() -> None:
    with pytest.raises(PolarisValidationError, match="k >= 3"):
        cr_default_knots(np.arange(10, dtype=np.float64), 2)


def test_default_knots_refuses_insufficient_unique_values() -> None:
    x = np.array([1.0, 1.0, 1.0, 2.0], dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="insufficient unique"):
        cr_default_knots(x, 8)


# --- cr_basis: closed-form invariants (no mgcv needed) -----------------------------


def _rng_x(n: int = 100, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.sort(rng.uniform(0.0, 10.0, n))


def test_cr_basis_reproduces_a_linear_function_exactly() -> None:
    """A natural cubic spline through knot values that lie on a line has zero
    curvature everywhere and is itself that line — the interior second-derivative
    system solves to all-zero, so the correction (cubic) terms vanish and the
    basis reduces to pure linear interpolation. This holds independent of mgcv:
    it follows from the natural-spline definition itself."""
    x = _rng_x()
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    design, _ = cr_basis(x, knots)
    slope, intercept = 3.0, -1.5
    f_at_knots = slope * knots + intercept
    fitted = design @ f_at_knots
    np.testing.assert_allclose(fitted, slope * x + intercept, atol=1e-10)


def test_cr_basis_penalty_is_zero_on_a_linear_function() -> None:
    """The penalty is the integrated squared second derivative; a line has zero
    second derivative everywhere, so f^T S f must be exactly (numerically) zero
    for f the linear function's values at the knots — independent of mgcv."""
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    _, s = cr_basis(x, knots)
    f_at_knots = 3.0 * knots - 1.5
    quad_form = f_at_knots @ s @ f_at_knots
    assert quad_form == pytest.approx(0.0, abs=1e-9)


def test_cr_basis_penalty_is_positive_on_a_curved_function() -> None:
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    _, s = cr_basis(x, knots)
    f_at_knots = knots**2
    quad_form = f_at_knots @ s @ f_at_knots
    assert quad_form > 0.0


def test_cr_basis_penalty_is_symmetric() -> None:
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    _, s = cr_basis(x, knots)
    np.testing.assert_array_equal(s, s.T)


def test_cr_basis_penalty_rank_is_k_minus_two() -> None:
    """mgcv's own invariant (`smooth.construct.cr.smooth.spec`): the null space of
    the penalty is exactly the linear functions, dimension 2, so rank = k - 2."""
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    _, s = cr_basis(x, knots)
    assert np.linalg.matrix_rank(s) == knots.shape[0] - 2


def test_cr_basis_at_a_knot_is_a_unit_row() -> None:
    """Evaluating exactly at a knot reproduces that knot's coefficient — the basic
    interpolation property, independent of the penalty or mgcv."""
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    design, _ = cr_basis(knots.copy(), knots)
    np.testing.assert_allclose(design, np.eye(knots.shape[0]), atol=1e-10)


def test_cr_basis_refuses_fewer_than_three_knots() -> None:
    with pytest.raises(PolarisValidationError, match="at least 3 knots"):
        cr_basis(_rng_x(), np.array([0.0, 1.0], dtype=np.float64))


def test_cr_basis_refuses_non_increasing_knots() -> None:
    with pytest.raises(PolarisValidationError, match="strictly increasing"):
        cr_basis(_rng_x(), np.array([0.0, 2.0, 1.0, 3.0], dtype=np.float64))


# --- absorb_sum_to_zero_constraint --------------------------------------------------


def test_absorb_constraint_drops_one_dimension() -> None:
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    design, s = cr_basis(x, knots)
    design_c, s_c = absorb_sum_to_zero_constraint(design, s)
    assert design_c.shape == (design.shape[0], design.shape[1] - 1)
    assert s_c.shape == (design.shape[1] - 1, design.shape[1] - 1)


def test_absorb_constraint_column_means_are_zero() -> None:
    """`Z`'s columns span the null space of `w = colMeans(X)`, so
    `w @ Z = (1/n) ones(n)^T @ X @ Z = (1/n) ones(n)^T @ Xc = colMeans(Xc)` —
    every column of the *constrained* design has zero mean over the data. That is
    the practical meaning of "sum-to-zero": checkable on the constrained design
    alone, with no need to recover `Z` itself."""
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    design, s = cr_basis(x, knots)
    design_c, _ = absorb_sum_to_zero_constraint(design, s)
    np.testing.assert_allclose(design_c.mean(axis=0), 0.0, atol=1e-10)


def test_absorb_constraint_penalty_stays_symmetric() -> None:
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    design, s = cr_basis(x, knots)
    _, s_c = absorb_sum_to_zero_constraint(design, s)
    np.testing.assert_array_equal(s_c, s_c.T)


def test_absorb_constraint_refuses_a_shape_mismatch() -> None:
    design = np.zeros((10, 5), dtype=np.float64)
    s = np.eye(4, dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="but s is"):
        absorb_sum_to_zero_constraint(design, s)


def test_absorb_constraint_refuses_a_zero_constraint_row() -> None:
    design = np.zeros((10, 5), dtype=np.float64)
    s = np.eye(5, dtype=np.float64)
    with pytest.raises(PolarisComputationError, match="colMeans"):
        absorb_sum_to_zero_constraint(design, s)


# --- by_scale_design (slice 5, the MI term) ---------------------------------------
#
# R-free coverage, matching this module's existing pattern. These exist because
# they are the by-path's only *gating* verification — not, as an earlier version
# of this comment said, its only verification at all (PR #206 review, corrected in
# its own second pass):
#
#   - the by-case Stage-A comparison against mgcv DOES run automatically on every
#     PR touching this file — `mgcv-conformance.yml` has a `pull_request:` trigger
#     whose path filter names `gam_basis_cr.py`, `gam_stage_a.py` and
#     `gam_term_extract.R`;
#   - but that step is `continue-on-error: true` and its `any_cr_disagree` flag
#     only annotates the report, never exits non-zero, so a disagreement there
#     leaves every check on the PR green;
#   - R is absent from the pytest job by deliberate design (ADR-151 / Anchor 5),
#     not by oversight, so the `rscript_mgcv_available()` skip is correct.
#
# The tests below run in the gating pytest job, which is what makes a regression
# in the by-path fail a PR rather than merely print a number.


def test_by_scale_design_scales_each_row_by_its_by_value() -> None:
    """Hand-computed, not read off any implementation: row i of the result is
    row i of the design times ``by[i]``."""
    design = np.array(
        [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0], [9.0, 10.0, 11.0, 12.0]],
        dtype=np.float64,
    )
    by = np.array([2.0, 0.0, -3.0], dtype=np.float64)
    expected = np.array(
        [[2.0, 4.0, 6.0, 8.0], [0.0, 0.0, 0.0, 0.0], [-27.0, -30.0, -33.0, -36.0]],
        dtype=np.float64,
    )
    np.testing.assert_allclose(by_scale_design(design, by), expected)


def test_by_scale_design_preserves_shape() -> None:
    """A numeric-by term keeps all k columns — mgcv absorbs no identifiability
    constraint on it (ADR-200), so nothing is dropped here either."""
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    design, _ = cr_basis(x, knots)
    by = np.linspace(-2.0, 2.0, x.shape[0], dtype=np.float64)
    assert by_scale_design(design, by).shape == design.shape


def test_by_scale_design_with_unit_by_is_the_identity() -> None:
    """by == 1 everywhere must leave the design untouched — the property that
    makes the by-term reduce to the unconstrained basis."""
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    design, _ = cr_basis(x, knots)
    ones = np.ones(x.shape[0], dtype=np.float64)
    np.testing.assert_allclose(by_scale_design(design, ones), design)


def test_by_scale_design_refuses_a_length_mismatch() -> None:
    design = np.zeros((10, 5), dtype=np.float64)
    by = np.ones(9, dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="one by-value per row"):
        by_scale_design(design, by)


# --- sum_to_zero_null_space: split from absorb_sum_to_zero_constraint (slice 5) ----


def test_sum_to_zero_null_space_matches_absorb_constraint() -> None:
    """The split (module docstring) must not have changed what either call site
    computes — Z applied by hand reproduces absorb_sum_to_zero_constraint's own
    design/penalty exactly."""
    knots = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    x = _rng_x()
    design, s = cr_basis(x, knots)
    design_c, s_c = absorb_sum_to_zero_constraint(design, s)
    z = sum_to_zero_null_space(design)
    np.testing.assert_allclose(design @ z, design_c)
    np.testing.assert_allclose(z.T @ s @ z, s_c)


def test_sum_to_zero_null_space_refuses_a_zero_constraint_row() -> None:
    design = np.zeros((10, 5), dtype=np.float64)
    with pytest.raises(PolarisComputationError, match="colMeans"):
        sum_to_zero_null_space(design)


# --- ti_basis: closed-form invariants (no mgcv needed) ------------------------------
#
# R-gated parity against mgcv's own smoothCon(ti(...)) lives in test_gam_stage_a.py
# (test_the_python_ti_basis_agrees_with_smoothcon_on_every_ti_design), matching
# cr_basis's own split between this module (closed-form, no R) and that one
# (mgcv-gated).


def _ti_case(seed: int = 7, n: int = 120):
    rng = np.random.default_rng(seed)
    x1 = np.sort(rng.uniform(0.0, 10.0, n))
    x2 = rng.permutation(np.sort(rng.uniform(0.0, 5.0, n)))
    knots1 = np.array([0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 9.0, 10.0], dtype=np.float64)
    knots2 = np.array([0.0, 1.0, 2.0, 3.0, 5.0], dtype=np.float64)
    return x1, x2, knots1, knots2


def test_ti_basis_shape_is_the_product_of_the_constrained_margins() -> None:
    """Each margin drops one column to its own sum-to-zero constraint (k_i - 1);
    the tensor width is the product, independent of mgcv (module docstring steps
    1 and 4)."""
    x1, x2, knots1, knots2 = _ti_case()
    design, s1, s2 = ti_basis(x1, x2, knots1, knots2)
    d1, d2 = knots1.shape[0] - 1, knots2.shape[0] - 1
    assert design.shape == (x1.shape[0], d1 * d2)
    assert s1.shape == (d1 * d2, d1 * d2)
    assert s2.shape == (d1 * d2, d1 * d2)


def test_ti_basis_penalties_are_symmetric() -> None:
    x1, x2, knots1, knots2 = _ti_case()
    _, s1, s2 = ti_basis(x1, x2, knots1, knots2)
    np.testing.assert_allclose(s1, s1.T)
    np.testing.assert_allclose(s2, s2.T)


def test_ti_basis_penalty_ranks_are_the_kronecker_product_of_the_margin_ranks() -> None:
    """rank(A kron B) = rank(A) * rank(B) — checkable without mgcv, and the
    identity S_1 = Sm_1 kron I / S_2 = I kron Sm_2 (module docstring step 4) must
    respect it: S_1's rank is margin 1's own penalty rank times margin 2's full
    (constrained) width, and vice versa."""
    x1, x2, knots1, knots2 = _ti_case()
    design1_unc, s1_unc = cr_basis(x1, knots1)
    design2_unc, s2_unc = cr_basis(x2, knots2)
    _, s1_marg = absorb_sum_to_zero_constraint(design1_unc, s1_unc)
    _, s2_marg = absorb_sum_to_zero_constraint(design2_unc, s2_unc)
    margin_rank1 = np.linalg.matrix_rank(s1_marg)
    margin_rank2 = np.linalg.matrix_rank(s2_marg)
    d1, d2 = knots1.shape[0] - 1, knots2.shape[0] - 1

    _, s1, s2 = ti_basis(x1, x2, knots1, knots2)
    assert np.linalg.matrix_rank(s1) == margin_rank1 * d2
    assert np.linalg.matrix_rank(s2) == d1 * margin_rank2


def test_ti_basis_penalties_are_positive_semidefinite() -> None:
    """Each penalty is a curvature quadratic form (cr_basis's own PSD penalty),
    congruence-transformed (constraint, eigenvalue normalization) and Kronecker'd
    with an identity — every one of those operations preserves PSD-ness, so
    ``coef @ S_i @ coef`` must never be negative, for any coefficient vector, on
    either block — independent of mgcv."""
    x1, x2, knots1, knots2 = _ti_case()
    _, s1, s2 = ti_basis(x1, x2, knots1, knots2)
    rng = np.random.default_rng(13)
    for _ in range(20):
        coef = rng.normal(size=s1.shape[0])
        assert coef @ s1 @ coef >= -1e-9
        assert coef @ s2 @ coef >= -1e-9


def test_ti_basis_applies_the_tensor_level_rescale() -> None:
    """Pins construction step 5 (module docstring) — the step that took two
    instrumented R passes to find (ADR-205) and that every OTHER `ti_basis`
    test in this file is invariant to, since they all check shape, symmetry,
    rank or PSD-ness, none of which a positive scalar rescale of `S` changes
    (PR #209 review [P2-2]: deleting step 5 left every pre-existing test green).

    By construction, the final rescale sets
    ``S_i <- S_i / (norm_one(S_i_pre_rescale) / norm_inf(X)**2)``, so
    ``norm_one(S_i_final)`` must equal ``norm_inf(X)**2`` exactly — a
    closed-form invariant of the scaling itself, not a value read off `mgcv`,
    so this needs no R."""
    x1, x2, knots1, knots2 = _ti_case()
    design, s1, s2 = ti_basis(x1, x2, knots1, knots2)
    target = _r_norm_inf(design) ** 2
    assert _r_norm_one(s1) == pytest.approx(target)
    assert _r_norm_one(s2) == pytest.approx(target)


def test_ti_basis_refuses_a_shape_mismatch() -> None:
    x1 = np.linspace(0.0, 10.0, 50)
    x2 = np.linspace(0.0, 5.0, 40)
    knots1 = np.array([0.0, 2.0, 5.0, 8.0, 10.0], dtype=np.float64)
    knots2 = np.array([0.0, 1.0, 3.0, 5.0], dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="one value per row"):
        ti_basis(x1, x2, knots1, knots2)

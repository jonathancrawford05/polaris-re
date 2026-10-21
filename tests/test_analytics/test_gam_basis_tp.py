"""Tests for the thin-plate basis (Slice R4, ADR-261): closed forms, structure, refusals, and the
R probe round trip when R is present."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_basis_cr import (
    absorb_sum_to_zero_constraint,
    cr_basis,
    sum_to_zero_null_space,
)
from polaris_re.analytics.gam_basis_tp import (
    TP_BASIS_CLAIM,
    TP_MAX_KNOTS,
    TP_NULL_DIM,
    compare_tp_basis,
    derived_tolerance,
    eigenspace_rounding_bound,
    subspace_distance,
    tp_basis,
    tp_predict,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def x_tied() -> np.ndarray:
    rng = np.random.default_rng(7)
    return np.round(rng.uniform(20, 90, 120))


def test_the_penalty_leaves_constants_and_linear_functions_unpenalised(x_tied: np.ndarray) -> None:
    """M = 2: the last two coefficients are the polynomial part, outside the penalty's range."""
    design, s, _ = tp_basis(x_tied, 9)
    assert s.shape == (9, 9)
    np.testing.assert_allclose(s[:, 9 - TP_NULL_DIM :], 0.0, atol=1e-12)
    np.testing.assert_allclose(s[9 - TP_NULL_DIM :, :], 0.0, atol=1e-12)
    assert np.linalg.matrix_rank(s) == 9 - TP_NULL_DIM
    # a constant and a straight line lie in the design's column space
    xs = x_tied - x_tied.mean()
    for target in (np.ones_like(xs), xs):
        coef, *_ = np.linalg.lstsq(design, target, rcond=None)
        np.testing.assert_allclose(design @ coef, target, atol=1e-9)


def test_with_k_equal_nu_the_penalty_is_the_natural_cubic_spline_bending_energy() -> None:
    """Closed form: eta(r) = r^3/12 is the Green's function of d^4/dx^4, so for k = nu the tp
    penalty is the integral of f''^2 over the span, the same quadratic form the cr basis (a
    natural cubic spline through the knots) carries. The two differ only by smoothCon's
    gauge-dependent scale.penalty scalar, so the ratio must be one constant."""
    x = np.array([0.3, 1.1, 2.0, 2.2, 4.1, 5.0, 5.9, 7.3, 8.8])
    k = x.shape[0]
    design_tp, s_tp, _ = tp_basis(x, k)
    _, s_cr = cr_basis(x, np.sort(x))
    # function values at the knots are the shared coordinates
    f_to_beta, *_ = np.linalg.lstsq(design_tp, np.eye(k), rcond=None)
    rng = np.random.default_rng(1)
    ratios = []
    for _ in range(6):
        f = rng.standard_normal(k)
        beta = f_to_beta @ f
        ratios.append((beta @ s_tp @ beta) / (f @ s_cr @ f))
    np.testing.assert_allclose(ratios, ratios[0], rtol=1e-9)


def test_the_columns_have_norm_sqrt_n_and_the_range_space_is_orthogonal_to_the_polynomials(
    x_tied: np.ndarray,
) -> None:
    n = x_tied.shape[0]
    design, _, state = tp_basis(x_tied, 8)
    np.testing.assert_allclose(np.linalg.norm(design, axis=0), np.sqrt(n), rtol=1e-12)
    # delta is orthogonal to [1, xu]: T'delta = 0 for every range-space column
    t = np.column_stack([np.ones(state.xu.shape[0]), state.xu])
    delta = state.uz[: state.xu.shape[0], : 8 - TP_NULL_DIM]
    np.testing.assert_allclose(t.T @ delta, 0.0, atol=1e-10 * np.abs(delta).max())


def test_the_range_space_lies_in_the_top_k_eigenspace_of_the_kernel_matrix(
    x_tied: np.ndarray,
) -> None:
    """Truncate THEN constrain: span(U_k Z) is inside the k eigenvectors of largest |lambda| of
    the full E, an independent numpy eigendecomposition."""
    k = 7
    _, _, state = tp_basis(x_tied, k)
    xu = state.xu
    e = np.abs(xu[:, None] - xu[None, :]) ** 3 / 12.0
    values, vectors = np.linalg.eigh(e)
    top = vectors[:, np.argsort(-np.abs(values))[:k]]
    delta = state.uz[: xu.shape[0], : k - TP_NULL_DIM]
    assert subspace_distance(top, delta) < 1e-10


def test_predicting_at_the_training_rows_reproduces_the_training_design(x_tied: np.ndarray) -> None:
    design, _, state = tp_basis(x_tied, 10)
    np.testing.assert_allclose(tp_predict(x_tied, state), design, rtol=0, atol=1e-12)
    rng = np.random.default_rng(3)
    perm = rng.permutation(x_tied.shape[0])
    np.testing.assert_allclose(tp_predict(x_tied[perm], state), design[perm], atol=1e-12)


def test_the_design_is_invariant_to_row_order_up_to_the_same_permutation(
    x_tied: np.ndarray,
) -> None:
    d1, s1, _ = tp_basis(x_tied, 8)
    perm = np.random.default_rng(5).permutation(x_tied.shape[0])
    d2, s2, _ = tp_basis(x_tied[perm], 8)
    # same mean up to rounding, so the same shifted values and the same basis
    np.testing.assert_allclose(d2, d1[perm], atol=1e-9)
    np.testing.assert_allclose(s2, s1, rtol=1e-8, atol=1e-10)


def test_beyond_the_data_range_the_basis_extrapolates_without_linearising(
    x_tied: np.ndarray,
) -> None:
    """mgcv's tp does not linearise (unlike cr): the kernel |r|^3 keeps growing."""
    _, _, state = tp_basis(x_tied, 8)
    far = np.array([200.0, 400.0, 800.0])
    values = tp_predict(far, state)
    second = values[2] - 2.0 * values[1] + values[0]
    assert np.abs(second).max() > 1e-6


@pytest.mark.parametrize(
    ("k", "message"),
    [(2, "below the minimum"), (0, "below the minimum")],
)
def test_k_below_the_null_space_plus_one_is_refused(k: int, message: str) -> None:
    with pytest.raises(PolarisValidationError, match=message):
        tp_basis(np.linspace(0.0, 1.0, 20), k)


def test_fewer_distinct_values_than_k_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="distinct covariate value"):
        tp_basis(np.repeat([1.0, 2.0, 3.0, 4.0], 30), 6)


def test_the_random_subsampling_regime_is_refused_by_name() -> None:
    x = np.linspace(0.0, 1.0, TP_MAX_KNOTS + 1)
    with pytest.raises(PolarisValidationError, match=r"max\.knots"):
        tp_basis(x, 10)


def test_many_rows_few_distinct_values_is_accepted() -> None:
    x = np.tile(np.arange(40, dtype=np.float64), TP_MAX_KNOTS // 40 + 5)
    assert x.shape[0] > TP_MAX_KNOTS
    design, s, _ = tp_basis(x, 9)
    assert design.shape == (x.shape[0], 9) and s.shape == (9, 9)


def test_non_finite_input_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="finite"):
        tp_basis(np.array([0.0, 1.0, np.nan, 3.0]), 3)


def test_the_comparator_accepts_an_identical_design_and_rejects_a_different_recipe(
    x_tied: np.ndarray,
) -> None:
    """Power check without R: feeding Polaris's own constrained design back in must agree
    (a harness check, labelled as such), and a design from a different k must not."""
    k = 8
    design, s, _ = tp_basis(x_tied, k)
    dc, sc = absorb_sum_to_zero_constraint(design, s)
    same = compare_tp_basis(x_tied, k, dc, sc, int(np.linalg.matrix_rank(sc)), 0.0)
    assert same.agrees and same.subspace_distance < 1e-9
    # a different recipe input (a transformed covariate) of the same width must not agree
    shifted, shifted_s, _ = tp_basis(x_tied**1.5, k)
    sh_c, sh_sc = absorb_sum_to_zero_constraint(shifted, shifted_s)
    differ = compare_tp_basis(x_tied, k, sh_c, sh_sc, int(np.linalg.matrix_rank(sh_sc)), 0.0)
    assert not differ.agrees


def test_the_tolerance_is_the_reference_error_plus_a_priori_rounding(x_tied: np.ndarray) -> None:
    bound = eigenspace_rounding_bound(x_tied, 8)
    assert 0.0 < bound < 1e-6
    assert derived_tolerance(bound, 2.0e-8) == pytest.approx(2.0e-8 + 1.0e3 * bound)


def test_the_sum_to_zero_constraint_makes_the_column_means_vanish(x_tied: np.ndarray) -> None:
    design, s, _ = tp_basis(x_tied, 8)
    z = sum_to_zero_null_space(design)
    np.testing.assert_allclose((design @ z).mean(axis=0), 0.0, atol=1e-10)
    assert z.shape == (8, 7) and s.shape == (8, 8)


def test_the_claim_is_independent_for_every_compared_quantity() -> None:
    require_parity_evidence(TP_BASIS_CLAIM.quantities, claim="tp Stage A")


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end_and_agrees(tmp_path: Path) -> None:  # pragma: no cover
    out = tmp_path / "gam_tp_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_tp_probe.R"), str(out)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    payload = json.loads(out.read_text())
    for case in payload["cases"]:
        mg = case["mgcv"]
        cmp = compare_tp_basis(
            np.asarray(case["x"], dtype=np.float64),
            int(case["k"]),
            np.asarray(mg["X"], dtype=np.float64),
            np.asarray(mg["S"], dtype=np.float64),
            int(mg["rank"]),
            float(mg["vs_exact"]),
        )
        assert cmp.agrees, (case["name"], cmp)

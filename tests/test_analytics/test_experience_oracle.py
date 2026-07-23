"""
Tests for the Slice-4c-3 offline ``mgcv``-via-``rpy2`` oracle
(:mod:`polaris_re.analytics.experience_oracle`).

The oracle cross-checks the Python tensor-MI Poisson-GLM fit against R ``mgcv`` on a
shared synthetic dataset (docs/PLAN_experience_gam.md Design Anchor 5). R is a
**dev-only** dependency, never shipped to the runtime or CI, so the R cross-check
itself is ``@pytest.mark.slow`` and skips unless ``rpy2`` + R + ``mgcv`` are present.

The runnable tests here are the network-free guarantee that the (unrunnable-in-CI) R
comparison must hold: because the Poisson log-likelihood over the fixed unpenalized
design is strictly concave, its maximiser is unique, so proving the shipped design
sits at that maximiser (``||Xᵀ(y - μ)||∞ ≈ 0``) pins what any conformant R solve must
return. These tests therefore verify the oracle's correctness property without R.

Every dataset is deterministic under a pinned RNG seed — no test reads the wall clock
(ADR-074 guard).
"""

import numpy as np
import pytest

from polaris_re.analytics.experience_oracle import (
    OracleCase,
    build_oracle_case,
    fit_mgcv_coefficients,
    mgcv_available,
    poisson_score_infinity_norm,
)

# 31 ages (45..75) x 13 years (2008..2020) grouped cells.
_EXPECTED_CELLS = 31 * 13


@pytest.mark.parametrize("age_varying", [False, True])
def test_build_oracle_case_shapes(age_varying: bool) -> None:
    """The packaged fit exposes a consistent (deaths, design, offset, coef) bundle."""
    case = build_oracle_case(age_varying=age_varying)
    assert isinstance(case, OracleCase)
    assert case.n_cells == _EXPECTED_CELLS
    assert case.design.shape == (_EXPECTED_CELLS, case.n_params)
    assert case.deaths.shape == (_EXPECTED_CELLS,)
    assert case.offset.shape == (_EXPECTED_CELLS,)
    assert case.python_coef.shape == (case.n_params,)
    # Poisson death draws are non-negative integers stored as float.
    assert np.all(case.deaths >= 0.0)
    assert np.all(case.deaths == np.round(case.deaths))


def test_age_varying_adds_tensor_columns() -> None:
    """The age-by-year tensor interaction adds design columns over the separable fit."""
    separable = build_oracle_case(age_varying=False)
    tensor = build_oracle_case(age_varying=True)
    assert tensor.n_params > separable.n_params


@pytest.mark.parametrize("age_varying", [False, True])
def test_python_fit_at_poisson_optimum(age_varying: bool) -> None:
    """The shipped design sits at the unique Poisson MLE.

    This is the correct-by-construction guarantee: because the Poisson GLM is strictly
    concave, a near-zero score pins what R ``mgcv``/``glm`` must return on the same
    ``(deaths, design, offset)`` — so ``test_matches_mgcv_oracle`` cannot disagree
    beyond solver tolerance, even though it is unrunnable in CI.
    """
    case = build_oracle_case(age_varying=age_varying)
    assert poisson_score_infinity_norm(case) < 1e-6


@pytest.mark.parametrize("age_varying", [False, True])
def test_oracle_case_deterministic(age_varying: bool) -> None:
    """Same seed => byte-identical design, offset, deaths, and coefficients."""
    a = build_oracle_case(age_varying=age_varying, seed=20050101)
    b = build_oracle_case(age_varying=age_varying, seed=20050101)
    assert np.array_equal(a.design, b.design)
    assert np.array_equal(a.offset, b.offset)
    assert np.array_equal(a.deaths, b.deaths)
    assert np.array_equal(a.python_coef, b.python_coef)


def test_offset_is_static_log_expected() -> None:
    """The offset is ``log(exposure · q_base)`` — one distinct value per attained age.

    Exposure is constant and the static base ``q_base(x)`` depends only on age (Anchor
    1: a static, non-generational base), so the log-expected offset takes exactly one
    value per modelled age (31), never per calendar year.
    """
    case = build_oracle_case(age_varying=True)
    assert np.all(np.isfinite(case.offset))
    # 31 distinct ages => 31 distinct offsets (base rate is calendar-invariant).
    assert np.unique(np.round(case.offset, 12)).size == 31


def test_mgcv_available_returns_bool() -> None:
    """The availability guard is total — it returns a bool, never raises."""
    assert isinstance(mgcv_available(), bool)


@pytest.mark.slow
@pytest.mark.parametrize("age_varying", [False, True])
def test_matches_mgcv_oracle(age_varying: bool) -> None:
    """Dev-only: R ``mgcv::gam`` reproduces the Python coefficients on the shared design.

    Skips unless ``rpy2`` + R + ``mgcv`` are installed (Anchor 5 — R never ships to CI
    or the runtime). When it does run, ``test_python_fit_at_poisson_optimum`` is the
    proof it must pass: both solvers maximise the same strictly-concave Poisson
    likelihood over the identical design.
    """
    if not mgcv_available():
        pytest.skip("rpy2 + R + mgcv not available (dev-only oracle, Anchor 5)")
    case = build_oracle_case(age_varying=age_varying)
    mgcv_coef = fit_mgcv_coefficients(case)
    assert mgcv_coef.shape == case.python_coef.shape
    np.testing.assert_allclose(mgcv_coef, case.python_coef, atol=1e-6, rtol=1e-5)

"""Outer-solver epic Slice 1 (ADR-241/242) — the free-scale analytic gradient and
the safeguarded Newton search.

Internal self-consistency only (no ``mgcv`` comparison): the profiled gradient
is checked against a central difference of this engine's own free-scale score,
and the Newton search against the properties its docstring claims — a capped
accepted step, a gradient-test stop, the same criterion value from different
starts, and a score no worse than a dense grid. The ``mgcv`` comparison is the
conformance suite's, not this file's.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_family import gaussian_identity, poisson_log, quasipoisson_log
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient_profiled
from polaris_re.analytics.gam_reml_newton import (
    MGCV_NEWTON_MAX_NSTEP,
    newton_select_lambdas,
)
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score
from polaris_re.core.exceptions import PolarisValidationError

_LN10 = float(np.log(10.0))


def _problem(family_name: str, n: int = 240, seed: int = 20261003):
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, 1.0, n)
    p = 10
    x = np.column_stack([np.ones(n)] + [np.cos(k * np.pi * t) for k in range(1, p)])
    block_a = np.zeros((p, p))
    block_b = np.zeros((p, p))
    for k in range(1, 6):
        block_a[k, k] = float(k) ** 4
    for k in range(6, p):
        block_b[k, k] = float(k) ** 4
    signal = 1.0 + 0.8 * np.cos(np.pi * t) + 0.3 * np.cos(3 * np.pi * t)
    if family_name == "gaussian":
        y = signal + rng.normal(scale=0.4, size=n)
        family = gaussian_identity()
    else:
        y = rng.poisson(np.exp(0.5 + 0.5 * signal) * 3.0).astype(np.float64)
        family = quasipoisson_log()
    return y, x, family, (block_a, block_b)


@pytest.mark.parametrize("family_name", ["gaussian", "quasipoisson"])
@pytest.mark.parametrize(
    "log10_lambda",
    [np.array([1.0, 2.0]), np.array([3.5, -0.5]), np.array([11.0, 2.0])],
    ids=["interior", "mixed", "block_at_1e11"],
)
def test_profiled_gradient_matches_central_difference_of_the_score(
    family_name: str, log10_lambda: np.ndarray
) -> None:
    y, x, family, blocks = _problem(family_name)
    coef, _ = penalized_fit_and_score(y, x, family, blocks, log10_lambda)
    analytic = reml_score_gradient_profiled(y, x, family, coef, blocks, 10.0**log10_lambda)
    h = 1e-3
    fd = np.empty(2)
    for j in range(2):
        e = np.zeros(2)
        e[j] = h
        up = penalized_fit_and_score(y, x, family, blocks, log10_lambda + e)[1]
        dn = penalized_fit_and_score(y, x, family, blocks, log10_lambda - e)[1]
        fd[j] = (up - dn) / (2.0 * h * _LN10)  # per natural-log rho
    np.testing.assert_allclose(analytic, fd, atol=2e-4, rtol=1e-4)


def test_profiled_gradient_rejects_a_known_scale_family() -> None:
    y, x, _, blocks = _problem("quasipoisson")
    with pytest.raises(PolarisValidationError, match="fixed dispersion"):
        reml_score_gradient_profiled(y, x, poisson_log(), np.zeros(10), blocks, np.ones(2))


@pytest.mark.parametrize("family_name", ["gaussian", "quasipoisson"])
def test_newton_stops_on_the_gradient_test_with_capped_accepted_steps(family_name: str) -> None:
    y, x, family, blocks = _problem(family_name)
    result = newton_select_lambdas(y, x, family, blocks, x0=np.array([3.0, 3.0]))
    assert result.converged
    assert "gradient test" in result.message
    assert result.max_abs_projected_gradient is not None
    assert result.gradient_tolerance is not None
    assert result.max_abs_projected_gradient <= result.gradient_tolerance
    assert result.max_accepted_step_decades <= MGCV_NEWTON_MAX_NSTEP / _LN10 + 1e-9
    steps = np.abs(np.diff(np.array(result.accepted_log10), axis=0))
    assert float(steps.max()) <= MGCV_NEWTON_MAX_NSTEP / _LN10 + 1e-9


@pytest.mark.parametrize("start", [np.array([-1.0, -1.0]), np.array([1.0, 1.0])])
def test_newton_reaches_the_same_criterion_value_from_different_starts(start: np.ndarray) -> None:
    y, x, family, blocks = _problem("gaussian")
    reference = newton_select_lambdas(y, x, family, blocks, x0=np.array([3.0, 3.0]))
    other = newton_select_lambdas(y, x, family, blocks, x0=start)
    assert reference.converged
    assert other.converged
    np.testing.assert_allclose(other.reml_score, reference.reml_score, atol=1e-7)


def test_newton_from_a_plateau_start_stops_there_and_says_so_honestly() -> None:
    """A block at ``lambda = 1e5`` with no signal sits on the REML plateau,
    where its derivative vanishes: the gradient test is met at a point a
    descent path still leaves (score 117.98 against 117.26 from a better start).
    This pins the FINDING (outer-solver PLAN risk 1/2, realised): a Newton
    search is not start-free on a plateau, which is why ``initial.spg`` stays
    its start. If a later slice removes this, update the test and the ADR."""
    y, x, family, blocks = _problem("gaussian")
    plateau = newton_select_lambdas(y, x, family, blocks, x0=np.array([5.0, 5.0]))
    good = newton_select_lambdas(y, x, family, blocks, x0=np.array([3.0, 3.0]))
    assert plateau.converged  # gradient test met ...
    assert plateau.reml_score > good.reml_score + 0.1  # ... at a worse point


def test_newton_score_is_no_worse_than_a_dense_grid() -> None:
    y, x, family, blocks = _problem("gaussian")
    result = newton_select_lambdas(y, x, family, blocks, x0=np.array([3.0, 3.0]))
    grid = np.linspace(-2.0, 12.0, 15)
    best_grid = min(
        penalized_fit_and_score(y, x, family, blocks, np.array([a, b]))[1]
        for a in grid
        for b in grid
    )
    assert result.reml_score <= best_grid + 1e-9


def test_newton_requires_a_start_of_the_right_shape() -> None:
    y, x, family, blocks = _problem("gaussian")
    with pytest.raises(PolarisValidationError, match="x0 has shape"):
        newton_select_lambdas(y, x, family, blocks, x0=np.zeros(3))


def test_newton_variant_names_the_newton_search_and_keeps_provenance() -> None:
    from polaris_re.analytics.gam_gaussian_conformance import GAUSSIAN_FREE_SP_CLAIM
    from polaris_re.analytics.gam_reml_newton import newton_variant

    variant = newton_variant(GAUSSIAN_FREE_SP_CLAIM)
    text = variant.claim + "".join(q.left_producer for q in variant.quantities)
    assert "select_lambdas_continuous" not in text
    assert "newton_select_lambdas" in text
    assert [q.provenance for q in variant.quantities] == [
        q.provenance for q in GAUSSIAN_FREE_SP_CLAIM.quantities
    ]

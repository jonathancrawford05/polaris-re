"""``docs/PLAN_mgcv_parity_engine.md`` slice 4, part B — the continuous outer search.

Self-consistency and regression checks, mirroring ``test_gam_reml.py``'s own
framing: cheap to run before spending a tier-1/tier-3 R round trip. The actual
parity measurement against ``mgcv`` — does the continuous search's selected
``log10(lambda)`` land closer to ``mgcv``'s own free-``sp`` selection than the
production grid does (ADR-198's registered prediction) — is a probe script
(``scripts/reml_continuous_optimizer_probe.py``), not a pytest test: it needs
the committed ``python_reference.json`` plus a locally-generated
``mgcv_reference.json`` (produced by ``scripts/mgcv_conformance.R``, never
committed — see ``.gitignore``) and is read at tier 1/tier 3 per
``docs/ROUTINE_MGCV_PARITY.md``.
"""

from unittest.mock import patch

import numpy as np
import pytest

from polaris_re.analytics.experience_gam_penalized import select_lambdas_reml
from polaris_re.analytics.experience_mgcv_conformance import DESIGNS, build_design, synthetic_cells
from polaris_re.analytics.gam_family import binomial_logit, poisson_log
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.analytics.gam_reml_optimize import (
    penalized_fit_and_score,
    select_lambdas_continuous,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260822)


def _design(rng: np.random.Generator, n: int, p: int) -> np.ndarray:
    return np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])


class TestPenalizedFitAndScore:
    """The per-point wrapper is a thin assembly step — these are self-consistency
    checks against calling ``penalized_irls_general``/``reml_score_general``
    directly, not a fresh formula."""

    def test_matches_a_direct_call_at_one_block(self, rng: np.random.Generator) -> None:
        n, p = 60, 5
        x = _design(rng, n, p)
        y = rng.poisson(5.0, size=n).astype(np.float64)
        s = np.eye(p)
        family = poisson_log()

        coef, score = penalized_fit_and_score(y, x, family, (s,), np.array([1.5]))

        direct_fit = penalized_irls_general(x, y, family=family, penalty=(10.0**1.5) * s)
        direct_score = reml_score_general(
            y, x, family, direct_fit.coef, (s,), np.array([10.0**1.5])
        )
        np.testing.assert_allclose(coef, direct_fit.coef, rtol=1e-12)
        assert score == pytest.approx(direct_score, rel=1e-12)

    def test_sums_multiple_blocks(self, rng: np.random.Generator) -> None:
        n, p = 80, 6
        x = _design(rng, n, p)
        y = rng.poisson(5.0, size=n).astype(np.float64)
        s1 = np.eye(p)
        s2 = np.diag(np.arange(p, dtype=np.float64))
        family = poisson_log()
        log_lambda = np.array([0.5, 1.5])

        coef, score = penalized_fit_and_score(y, x, family, (s1, s2), log_lambda)

        penalty = (10.0**0.5) * s1 + (10.0**1.5) * s2
        direct_fit = penalized_irls_general(x, y, family=family, penalty=penalty)
        direct_score = reml_score_general(
            y, x, family, direct_fit.coef, (s1, s2), np.array([10.0**0.5, 10.0**1.5])
        )
        np.testing.assert_allclose(coef, direct_fit.coef, rtol=1e-12)
        assert score == pytest.approx(direct_score, rel=1e-12)

    def test_rejects_a_log_lambda_length_mismatch(self, rng: np.random.Generator) -> None:
        x = _design(rng, 20, 3)
        y = rng.poisson(5.0, size=20).astype(np.float64)
        s = np.eye(3)
        with pytest.raises(PolarisValidationError, match="penalty_blocks"):
            penalized_fit_and_score(y, x, poisson_log(), (s,), np.array([0.0, 0.0]))

    def test_propagates_non_convergence(self, rng: np.random.Generator) -> None:
        x = _design(rng, 20, 3)
        y = rng.poisson(5.0, size=20).astype(np.float64)
        s = np.eye(3)
        with (
            patch(
                "polaris_re.analytics.gam_reml_optimize.penalized_irls_general",
                side_effect=PolarisComputationError("did not converge"),
            ),
            pytest.raises(PolarisComputationError),
        ):
            penalized_fit_and_score(y, x, poisson_log(), (s,), np.array([0.0]))


class TestSelectLambdasContinuousValidation:
    def test_rejects_empty_penalty_blocks(self, rng: np.random.Generator) -> None:
        x = _design(rng, 20, 3)
        y = rng.poisson(5.0, size=20).astype(np.float64)
        with pytest.raises(PolarisValidationError, match="at least one penalty block"):
            select_lambdas_continuous(y, x, poisson_log(), ())

    def test_rejects_an_x0_shape_mismatch(self, rng: np.random.Generator) -> None:
        x = _design(rng, 20, 3)
        y = rng.poisson(5.0, size=20).astype(np.float64)
        s = np.eye(3)
        with pytest.raises(PolarisValidationError, match="x0 has shape"):
            select_lambdas_continuous(y, x, poisson_log(), (s,), x0=np.array([0.0, 0.0]))

    def test_raises_when_every_trial_point_is_rejected(self, rng: np.random.Generator) -> None:
        x = _design(rng, 20, 3)
        y = rng.poisson(5.0, size=20).astype(np.float64)
        s = np.eye(3)
        with (
            patch(
                "polaris_re.analytics.gam_reml_optimize.penalized_irls_general",
                side_effect=PolarisComputationError("did not converge"),
            ),
            pytest.raises(PolarisComputationError, match="rejected every one"),
        ):
            select_lambdas_continuous(y, x, poisson_log(), (s,), maxiter=5)


class TestSelectLambdasContinuousOnAToyProblem:
    """A single-block problem with a closed-enough optimum: does the search
    actually descend, not just run without error?"""

    def test_selects_a_finite_interior_lambda_on_a_well_posed_design(
        self, rng: np.random.Generator
    ) -> None:
        n, p = 300, 8
        x = _design(rng, n, p)
        true_coef = np.zeros(p)
        true_coef[0] = 1.0
        eta = x @ true_coef
        mu = np.exp(eta)
        y = rng.poisson(mu)
        s = np.eye(p)
        s[0, 0] = 0.0  # leave the intercept unpenalized, like a real smooth's null space

        selection = select_lambdas_continuous(y, x, poisson_log(), (s,), gtol=1e-6)

        assert selection.converged
        assert np.isfinite(selection.log_lambda).all()
        assert -2.0 < selection.log_lambda[0] < 8.0
        assert selection.n_function_evals > 0
        assert selection.coef.shape == (p,)

    def test_binomial_logit_also_converges(self, rng: np.random.Generator) -> None:
        n, p = 300, 6
        x = _design(rng, n, p)
        true_coef = np.zeros(p)
        true_coef[0] = 0.2
        eta = x @ true_coef
        mu = 1.0 / (1.0 + np.exp(-eta))
        y = rng.binomial(1, mu).astype(np.float64)
        s = np.eye(p)
        s[0, 0] = 0.0

        selection = select_lambdas_continuous(y, x, binomial_logit(), (s,), gtol=1e-6)

        assert selection.converged
        assert np.isfinite(selection.reml_score)


class TestSelectLambdasContinuousReproducesTheProductionGridWithinItsResolution:
    """PLAN slice 4 acceptance criterion (2-D case): "it reproduces the existing
    grid's selection to within the grid's own resolution — a regression check
    against something already trusted." Uses the SAME synthetic tensor-MI
    design ``select_lambdas_reml`` already searches, via
    ``experience_mgcv_conformance.build_design`` — the same design-extraction
    path the mgcv conformance exchange itself uses (ADR-189 decision 1: a
    design extracted from a fit, never re-derived).

    This is a Python-vs-Python regression check, not a claim against `mgcv` —
    it carries no ``VerificationClaim`` and belongs nowhere near ADR-193's
    provenance machinery. The `mgcv` comparison is the probe script.
    """

    def test_matches_the_grid_within_one_refine_step_on_d1(self) -> None:
        cells = synthetic_cells()
        spec = next(d for d in DESIGNS if d.design_id == "d1")
        export = build_design(spec, cells)

        grid = select_lambdas_reml(cells, k_age=spec.k_age, k_year=spec.k_year)
        continuous = select_lambdas_continuous(
            export.deaths,
            export.design,
            poisson_log(),
            (export.s_age, export.s_year),
            offset=export.offset,
            gtol=1e-6,
        )

        grid_log = np.array([np.log10(grid.lambda_age), np.log10(grid.lambda_year)])
        np.testing.assert_allclose(continuous.log_lambda, grid_log, atol=0.25)

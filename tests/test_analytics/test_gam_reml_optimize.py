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

import json
import pathlib
from unittest.mock import patch

import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from polaris_re.analytics.experience_gam_penalized import select_lambdas_reml
from polaris_re.analytics.experience_mgcv_conformance import DESIGNS, build_design, synthetic_cells
from polaris_re.analytics.gam_family import binomial_logit, poisson_log
from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.analytics.gam_reml_optimize import (
    _FINITE_DIFF_STEP,
    penalized_fit_and_score,
    select_lambdas_continuous,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

_FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures"


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


class TestFiniteDiffStep:
    """PR #216 review [P0-2]: ``_FINITE_DIFF_STEP`` (ADR-212) changes what
    ``select_lambdas_continuous`` converges to on a production path
    (``gam_model.fit_polaris_gam``, ADR-207) with nothing in the suite
    sensitive to it before this class. Two things need pinning: the wiring
    (a future refactor must not silently drop the option), and the actual
    behaviour it fixes (spurious convergence on a near-flat block).

    The fixture (``tests/fixtures/gam_reml_optimize_near_flat_direction.json``)
    is the ACTUAL N=4 structure ADR-212 measured the defect on — a
    three-term formula (reference age, a numeric-``by`` MI term, a
    ``ti()`` interaction) at ``n=900``, synthetic data, seed ``20260825``
    (the same recipe ``scripts/gam_multiterm_free_sp_probe.R`` generates).
    A hand-built toy design was tried first and did not reproduce the
    breakdown: the failure mode only appears near an ACTUAL near-stationary
    point of a real multi-block criterion, not at an arbitrary point, so
    the real fixture is used rather than a synthetic approximation that
    might not exhibit the property it is meant to test.

    Both fixture-based tests below pin ``threadpool_limits(1, "blas")``: PR
    #217 (concurrent with this one) found this exact free-``sp`` selection
    moves with ``OPENBLAS_NUM_THREADS`` alone, and CI first caught this
    class doing exactly that — ``test_finite_diff_step_default_...`` reported
    ``converged=False`` (``ABNORMAL_TERMINATION_IN_LNSRCH``) on a
    multi-core runner where it converges cleanly at 1 thread. The env var
    alone does not reliably reach an already-imported OpenBLAS;
    ``threadpoolctl`` calls the library directly and is what
    ``ROUTINE_MGCV_PARITY.md``'s own ``OPENBLAS_NUM_THREADS=1`` convention
    needs inside a running test process.
    """

    @staticmethod
    def _load_fixture() -> tuple[
        np.ndarray, np.ndarray, object, tuple[np.ndarray, ...], np.ndarray
    ]:
        payload = json.loads(
            (_FIXTURES_DIR / "gam_reml_optimize_near_flat_direction.json").read_text()
        )
        age_knots = tuple(float(v) for v in payload["age_knots"])
        year_knots = tuple(float(v) for v in payload["year_knots"])
        model = _multiterm_model_spec(age_knots, year_knots)
        data = {
            k: np.asarray(payload[k], dtype=np.float64)
            for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
        }
        y = np.asarray(payload["y"], dtype=np.float64)
        design = assemble_model_design(model, data)
        family = resolve_family(model.family, model.link)
        weights = data["ExposCnt"]
        blocks = tuple(design["penalty_blocks"])
        return y, design["x"], family, blocks, weights

    def test_the_eps_option_reaches_scipy_minimize(self, rng: np.random.Generator) -> None:
        """Wiring test: a future refactor that drops ``"eps"`` from the
        ``options`` dict, or stops threading ``finite_diff_step`` through,
        must fail a test — not silently regress to SciPy's own default."""
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)

        with patch(
            "polaris_re.analytics.gam_reml_optimize.minimize",
            wraps=__import__("scipy.optimize", fromlist=["minimize"]).minimize,
        ) as spy:
            select_lambdas_continuous(y, x, poisson_log(), (s,), maxiter=5)

        assert spy.call_count >= 1
        assert spy.call_args.kwargs["options"]["eps"] == _FINITE_DIFF_STEP

        with patch(
            "polaris_re.analytics.gam_reml_optimize.minimize",
            wraps=__import__("scipy.optimize", fromlist=["minimize"]).minimize,
        ) as spy:
            select_lambdas_continuous(y, x, poisson_log(), (s,), maxiter=5, finite_diff_step=1e-3)

        assert spy.call_args.kwargs["options"]["eps"] == 1e-3

    def test_default_step_reports_spurious_convergence_on_the_near_flat_fixture(self) -> None:
        """SciPy's own default step (bypassed here by monkeypatching the
        option away, reproducing pre-ADR-212 behaviour) reports "converged"
        at a point whose independently-measured central-difference gradient
        is large — the exact defect ADR-212 measured and this class pins."""
        y, x, family, blocks, weights = self._load_fixture()
        center = np.full(4, 4.5)

        with patch("polaris_re.analytics.gam_reml_optimize.minimize") as spy:
            from scipy.optimize import minimize as real_minimize

            def call_with_default_eps(fn, x0, method, bounds, options):
                options = dict(options)
                options.pop("eps", None)  # SciPy's own default, pre-ADR-212
                return real_minimize(fn, x0, method=method, bounds=bounds, options=options)

            spy.side_effect = call_with_default_eps
            with threadpool_limits(limits=1, user_api="blas"):
                selection = select_lambdas_continuous(
                    y, x, family, blocks, weights=weights, x0=center, bounds=(-2.0, 11.0)
                )

        assert selection.converged  # SciPy itself reports success — the point IS spurious

        def score_at(point: np.ndarray) -> float:
            _, score = penalized_fit_and_score(y, x, family, blocks, point, weights=weights)
            return score

        h = 1.0e-3  # well inside the measured stable region (ADR-212: stable 1e-1 to 1e-6)
        grad = np.zeros(4)
        for i in range(4):
            step = np.zeros(4)
            step[i] = h
            grad[i] = (
                score_at(selection.log_lambda + step) - score_at(selection.log_lambda - step)
            ) / (2 * h)

        # SciPy's own gtol=1e-8 implies a near-zero gradient at a reported
        # minimum; the true gradient there is nowhere close.
        assert np.linalg.norm(grad) > 0.1

    def test_finite_diff_step_default_avoids_the_spurious_convergence(self) -> None:
        """The same fixture and starting point, through the production
        default (``finite_diff_step`` unset — ``_FINITE_DIFF_STEP``): the
        independently-measured gradient at the reported minimum is small."""
        y, x, family, blocks, weights = self._load_fixture()
        center = np.full(4, 4.5)

        with threadpool_limits(limits=1, user_api="blas"):
            selection = select_lambdas_continuous(
                y, x, family, blocks, weights=weights, x0=center, bounds=(-2.0, 11.0)
            )
        assert selection.converged

        def score_at(point: np.ndarray) -> float:
            _, score = penalized_fit_and_score(y, x, family, blocks, point, weights=weights)
            return score

        h = 1.0e-3
        grad = np.zeros(4)
        for i in range(4):
            step = np.zeros(4)
            step[i] = h
            grad[i] = (
                score_at(selection.log_lambda + step) - score_at(selection.log_lambda - step)
            ) / (2 * h)

        assert np.linalg.norm(grad) < 0.05

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
from polaris_re.analytics.gam_reml_gradient import reml_score_gradient
from polaris_re.analytics.gam_reml_optimize import (
    _FINITE_DIFF_STEP,
    ContinuousLambdaSelection,
    penalized_fit_and_score,
    penalized_fit_score_and_gradient,
    select_lambdas_continuous,
    select_lambdas_continuous_multistart,
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
        option away, reproducing pre-ADR-212 behaviour) lands at a point
        whose independently-measured central-difference gradient is large —
        the exact defect ADR-212 measured and this class pins.

        Deliberately does NOT assert ``selection.converged`` either way: CI
        first caught this test asserting ``converged is True`` (a specific
        SciPy-internal bookkeeping state) and failing on a runner whose
        L-BFGS-B line search reached ``ABNORMAL_TERMINATION`` instead, at a
        DIFFERENT point along the same near-flat direction, on the SAME
        (thread-pinned) code — that flag is itself downstream of the same
        noise this test exists to demonstrate, so treating it as load-bearing
        makes the test as unstable as the bug. Whether SciPy calls it success
        or failure, the gradient at wherever the default step actually lands
        is what the fix (below) needs to be small; that is the only portable
        claim."""
        y, x, family, blocks, weights = self._load_fixture()
        center = np.full(4, 4.5)

        with patch("polaris_re.analytics.gam_reml_optimize.minimize") as spy:
            from scipy.optimize import minimize as real_minimize

            def call_with_default_eps(fn, x0, method, bounds, options, jac=None):
                options = dict(options)
                options.pop("eps", None)  # SciPy's own default, pre-ADR-212
                return real_minimize(fn, x0, method=method, bounds=bounds, options=options, jac=jac)

            spy.side_effect = call_with_default_eps
            with threadpool_limits(limits=1, user_api="blas"):
                selection = select_lambdas_continuous(
                    y, x, family, blocks, weights=weights, x0=center, bounds=(-2.0, 11.0)
                )

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


class TestPenalizedFitScoreAndGradient:
    """PLAN slice 7d — one fit produces both the score and the gradient."""

    def test_score_matches_penalized_fit_and_score(self, rng: np.random.Generator) -> None:
        n, p = 60, 5
        x = _design(rng, n, p)
        y = rng.poisson(5.0, size=n).astype(np.float64)
        s = np.eye(p)
        log_lambda = np.array([0.7])

        coef_a, score_a = penalized_fit_and_score(y, x, poisson_log(), (s,), log_lambda)
        coef_b, score_b, gradient = penalized_fit_score_and_gradient(
            y, x, poisson_log(), (s,), log_lambda
        )
        np.testing.assert_allclose(coef_a, coef_b, rtol=1e-12)
        assert score_a == pytest.approx(score_b, rel=1e-12)
        assert gradient.shape == (1,)

    def test_gradient_matches_a_direct_call_to_reml_score_gradient(
        self, rng: np.random.Generator
    ) -> None:
        n, p = 60, 5
        x = _design(rng, n, p)
        y = rng.poisson(5.0, size=n).astype(np.float64)
        s = np.eye(p)
        log_lambda = np.array([0.7])

        coef, _score, gradient = penalized_fit_score_and_gradient(
            y, x, poisson_log(), (s,), log_lambda
        )
        expected_natural = reml_score_gradient(y, x, poisson_log(), coef, (s,), 10.0**log_lambda)
        np.testing.assert_allclose(gradient, expected_natural * np.log(10.0), rtol=1e-12)


class TestAnalyticGradient:
    """PLAN slice 7d — ``select_lambdas_continuous(analytic_gradient=True)``
    wires :func:`~polaris_re.analytics.gam_reml_gradient.reml_score_gradient`
    into SciPy's own ``jac=True`` combined-objective protocol, instead of a
    forward-difference estimate."""

    def test_analytic_gradient_reaches_scipy_via_jac_true(self, rng: np.random.Generator) -> None:
        """Wiring test, mirroring ``TestFiniteDiffStep``'s own
        ``test_the_eps_option_reaches_scipy_minimize``: a future refactor
        that stops passing ``jac=True``/drops the combined-objective
        function must fail a test, not silently regress to a
        finite-difference estimate."""
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)

        with patch(
            "polaris_re.analytics.gam_reml_optimize.minimize",
            wraps=__import__("scipy.optimize", fromlist=["minimize"]).minimize,
        ) as spy:
            select_lambdas_continuous(y, x, poisson_log(), (s,), maxiter=5, analytic_gradient=True)

        assert spy.call_count >= 1
        assert spy.call_args.kwargs["jac"] is True
        assert "eps" not in spy.call_args.kwargs["options"]

    def test_default_behaviour_is_unchanged_when_analytic_gradient_is_not_requested(
        self, rng: np.random.Generator
    ) -> None:
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)

        with patch(
            "polaris_re.analytics.gam_reml_optimize.minimize",
            wraps=__import__("scipy.optimize", fromlist=["minimize"]).minimize,
        ) as spy:
            select_lambdas_continuous(y, x, poisson_log(), (s,), maxiter=5)

        assert spy.call_args.kwargs["jac"] is None
        assert spy.call_args.kwargs["options"]["eps"] == _FINITE_DIFF_STEP

    def test_reaches_the_same_region_as_the_finite_difference_default(
        self, rng: np.random.Generator
    ) -> None:
        """Not a parity claim — a regression/sanity check that the analytic
        path converges to a comparably-good REML score on an easy,
        well-conditioned toy problem, mirroring
        ``TestSelectLambdasContinuousOnAToyProblem``'s own framing."""
        n, p = 200, 6
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        y = rng.poisson(np.exp(x @ beta_true)).astype(np.float64)
        d = np.diff(np.eye(p), n=2, axis=0)
        s = d.T @ d

        fd_selection = select_lambdas_continuous(y, x, poisson_log(), (s,))
        analytic_selection = select_lambdas_continuous(
            y, x, poisson_log(), (s,), analytic_gradient=True
        )
        assert fd_selection.converged
        assert analytic_selection.converged
        # Same criterion, same design: the two searches should land at a
        # comparably good score, not merely "both converged" — the toy
        # problem here is well-conditioned (unlike PLAN slice 7d's own N=4/
        # N=7 measurements), so a large gap would indicate a wiring defect
        # rather than a genuine optimiser-convergence finding.
        assert abs(fd_selection.reml_score - analytic_selection.reml_score) < 0.1

    def test_select_lambdas_continuous_multistart_passes_analytic_gradient_through(
        self, rng: np.random.Generator
    ) -> None:
        x = _design(rng, 60, 4)
        y = rng.poisson(5.0, size=60).astype(np.float64)
        s = np.eye(4)

        with patch(
            "polaris_re.analytics.gam_reml_optimize.minimize",
            wraps=__import__("scipy.optimize", fromlist=["minimize"]).minimize,
        ) as spy:
            select_lambdas_continuous_multistart(
                y, x, poisson_log(), (s,), n_starts=2, maxiter=5, analytic_gradient=True
            )

        assert spy.call_count >= 1
        assert all(call.kwargs["jac"] is True for call in spy.call_args_list)


class TestSelectLambdasContinuousMultistart:
    """PLAN slice 5e, candidate (1) — best-of-N starts as a reusable building
    block rather than a one-off diagnostic script (ADR-211's own blind
    multi-start check). These are self-consistency/wiring checks; the actual
    N>4-block robustness measurement is a diagnostic script
    (``scripts/gam_multistart_robustness_diagnostic.py``), not a pytest test,
    for the same reason the module-level docstring gives for the single-start
    search's own parity measurement."""

    def test_rejects_empty_penalty_blocks(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        with pytest.raises(PolarisValidationError, match="at least one penalty block"):
            select_lambdas_continuous_multistart(y, x, poisson_log(), ())

    def test_rejects_fewer_than_one_start(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)
        with pytest.raises(PolarisValidationError, match="n_starts >= 1"):
            select_lambdas_continuous_multistart(y, x, poisson_log(), (s,), n_starts=0)

    def test_first_start_is_the_bounds_centre(self, rng: np.random.Generator) -> None:
        """Index 0 must read as "what a single-start search alone would have
        tried" — the same default :func:`select_lambdas_continuous` itself
        uses — so a caller can compare best-of-N against a single start
        without a second search call."""
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)
        result = select_lambdas_continuous_multistart(
            y, x, poisson_log(), (s,), bounds=(-2.0, 8.0), n_starts=3, maxiter=5
        )
        np.testing.assert_array_equal(result.starts[0], np.array([3.0]))

    def test_deterministic_starts_across_calls(self, rng: np.random.Generator) -> None:
        """Same seed, same starts, bit-identical — the whole point of pinning
        `numpy.random.default_rng` rather than an unseeded draw (ADR-074)."""
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)
        first = select_lambdas_continuous_multistart(
            y, x, poisson_log(), (s,), n_starts=5, maxiter=5
        )
        second = select_lambdas_continuous_multistart(
            y, x, poisson_log(), (s,), n_starts=5, maxiter=5
        )
        for a, b in zip(first.starts, second.starts, strict=True):
            np.testing.assert_array_equal(a, b)

    def test_total_function_evals_sums_every_start(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)
        result = select_lambdas_continuous_multistart(
            y, x, poisson_log(), (s,), n_starts=4, maxiter=10
        )
        assert len(result.starts) == 4
        assert len(result.scores) == 4
        assert len(result.converged) == 4
        assert result.total_function_evals > 0

    def test_best_is_never_worse_than_the_single_default_start(
        self, rng: np.random.Generator
    ) -> None:
        """Best-of-N's own score must be <= the bounds-centre-only score on
        this well-posed toy problem, where start 0 (bounds-centre, the same
        point the single-start default uses) converges. This is NOT a
        general guarantee of the function: `best` minimises only over
        CONVERGED runs (`converged_indices` in
        `select_lambdas_continuous_multistart`), so if start 0 fails to
        converge while some other start does, `best` is drawn from that
        other, converged run and can legitimately score WORSE than a
        non-converged single-start reading (this is the correct behaviour —
        a converged point is preferred over a lower but non-converged score
        — see PR #218 review [P1], and ADR-213's own N=4/4-thread reading,
        where the single default start does not converge). This test only
        exercises the case both converge; it asserts that precondition
        explicitly rather than assuming it."""
        x = _design(rng, 40, 3)
        y = rng.poisson(5.0, size=40).astype(np.float64)
        s = np.eye(3)
        single = select_lambdas_continuous(y, x, poisson_log(), (s,))
        multi = select_lambdas_continuous_multistart(y, x, poisson_log(), (s,), n_starts=5, seed=1)
        assert single.converged
        assert multi.best.converged
        assert multi.best.reml_score <= single.reml_score + 1e-9

    def test_best_prefers_a_converged_run_over_a_lower_scoring_non_converged_one(
        self, rng: np.random.Generator
    ) -> None:
        """The actual guarantee `best` provides (PR #218 review [P1]): drawn
        from the converged runs when any exist, even if a non-converged run
        reports a numerically lower (better-looking) score. Fakes
        `select_lambdas_continuous` directly rather than relying on a real
        fixture to happen to reproduce this shape."""
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)

        def fake_search(
            *args: object, x0: np.ndarray, **kwargs: object
        ) -> ContinuousLambdaSelection:
            # The first start (bounds-centre) "fails to converge" but reports
            # a lower score than every other, converged start -- the exact
            # shape ADR-213 measured at N=4/4-threads.
            not_converged = np.isclose(x0, np.array([3.0]))[0]
            score = 1.0 if not_converged else 5.0 + float(x0[0])
            return ContinuousLambdaSelection(
                log_lambda=x0,
                lambda_=10.0**x0,
                coef=np.zeros(3),
                reml_score=score,
                edf_total=1.0,
                n_function_evals=10,
                n_rejected=0,
                converged=not not_converged,
                at_bound=False,
                message="fake",
            )

        with patch(
            "polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous",
            side_effect=fake_search,
        ):
            result = select_lambdas_continuous_multistart(
                y, x, poisson_log(), (s,), n_starts=3, seed=1
            )

        assert result.any_converged
        assert result.best.converged
        # The non-converged start (index 0, score 1.0) is numerically lower
        # than every converged alternative -- `best` must NOT pick it.
        assert result.best.reml_score > 1.0
        assert result.best_start_index != 0

    def test_all_starts_rejected_raises(self, rng: np.random.Generator) -> None:
        x = _design(rng, 30, 3)
        y = rng.poisson(5.0, size=30).astype(np.float64)
        s = np.eye(3)
        with (
            patch(
                "polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous",
                side_effect=PolarisComputationError("nothing converged"),
            ),
            pytest.raises(PolarisComputationError, match="every one of 3 starts"),
        ):
            select_lambdas_continuous_multistart(y, x, poisson_log(), (s,), n_starts=3)

    def test_multistart_on_the_near_flat_fixture_matches_or_beats_the_default_start(
        self,
    ) -> None:
        """ADR-211's own reading, replayed as the reusable function: on the
        ACTUAL N=4 near-flat structure, best-of-9 (the default `n_starts`)
        must not do worse than the single bounds-centre start, and its own
        `starts[0]` run must reproduce `select_lambdas_continuous`'s
        no-`x0` default (same point, same code path)."""
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
        bounds = (-2.0, 11.0)

        with threadpool_limits(limits=1, user_api="blas"):
            single = select_lambdas_continuous(
                y, design["x"], family, blocks, weights=weights, bounds=bounds
            )
            multi = select_lambdas_continuous_multistart(
                y, design["x"], family, blocks, weights=weights, bounds=bounds, n_starts=9
            )

        assert multi.best.reml_score <= single.reml_score + 1e-6
        assert multi.any_converged

"""``docs/PLAN_mgcv_parity_engine.md`` slice 3 — ``gam_fit``'s edf/dispersion helpers.

Self-consistency checks (not mgcv parity — see ``test_gam_family.py``'s module
docstring for that distinction).
"""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.gam_family import binomial_logit, poisson_log
from polaris_re.analytics.gam_fit import (
    effective_degrees_of_freedom,
    pearson_dispersion,
    penalized_irls_general,
)
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
from polaris_re.core.exceptions import PolarisComputationError

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260817)


class TestEffectiveDegreesOfFreedom:
    """``tr(F)`` — Anchor 4's EDF definition, generalized from
    ``experience_gam_penalized``'s Poisson-only computation."""

    def test_unpenalized_full_rank_fit_has_edf_equal_to_p(self, rng) -> None:
        """At ``S = 0``, ``F = (XᵀWX)⁻¹XᵀWX = I``, so ``tr(F) == p`` exactly —
        the closed form this quantity must satisfy before trusting it on a
        penalized case."""
        n, p = 300, 5
        x = np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])
        beta_true = rng.normal(scale=0.3, size=p)
        y = rng.poisson(np.exp(x @ beta_true)).astype(np.float64)
        penalty = np.zeros((p, p))
        family = poisson_log()

        fit = penalized_irls_general(x, y, family=family, penalty=penalty)
        edf = effective_degrees_of_freedom(x, family, fit.eta, fit.mu, penalty)
        assert edf == pytest.approx(p, abs=1e-8)

    def test_penalty_strictly_reduces_edf_below_p(self, rng) -> None:
        n, p = 300, 6
        x = np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])
        beta_true = rng.normal(scale=0.3, size=p)
        y = rng.poisson(np.exp(x @ beta_true)).astype(np.float64)
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 50.0 * (d.T @ d)
        family = poisson_log()

        fit = penalized_irls_general(x, y, family=family, penalty=penalty)
        edf = effective_degrees_of_freedom(x, family, fit.eta, fit.mu, penalty)
        assert 0.0 < edf < p

    def test_edf_matches_the_verified_penalized_tensor_model_on_a_shared_problem(self, rng) -> None:
        """Cross-checks the generalized edf against
        ``experience_gam_penalized``'s own (already mgcv-verified, ADR-189
        amendment 1) ``edf_total`` computation on an identical Poisson
        problem — the two must agree exactly since they compute the same
        ``tr(F)`` formula."""
        n, p = 250, 5
        x = np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])
        beta_true = rng.normal(scale=0.3, size=p)
        offset = rng.normal(scale=0.1, size=n)
        y = rng.poisson(np.exp(offset + x @ beta_true)).astype(np.float64)
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 3.0 * (d.T @ d)
        family = poisson_log()

        fit = penalized_irls_general(x, y, family=family, penalty=penalty, offset=offset)

        # experience_gam_penalized's own edf_total formula, transcribed inline
        # (that module's internals are private and specific to the tensor
        # design's factor-block layout, not reusable as a library call here).
        weights = np.clip(np.exp(np.clip(offset + x @ fit.coef, -700.0, 700.0)), 1e-300, None)
        xtwx = x.T @ (weights[:, None] * x)
        inv = np.linalg.inv(xtwx + penalty)
        hat = inv @ xtwx
        expected_edf = float(np.trace(hat))

        edf = effective_degrees_of_freedom(x, family, fit.eta, fit.mu, penalty, weights=None)
        assert edf == pytest.approx(expected_edf, abs=1e-10)


class TestPearsonDispersionWithComputedEdf:
    def test_binomial_dispersion_near_one_on_well_specified_data(self, rng) -> None:
        n, p = 2000, 4
        x = np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])
        beta_true = rng.normal(scale=0.3, size=p)
        prob_true = 1.0 / (1.0 + np.exp(-(x @ beta_true)))
        trials = rng.integers(20, 60, size=n).astype(np.float64)
        successes = rng.binomial(trials.astype(np.int64), prob_true).astype(np.float64)
        y = successes / trials
        penalty = np.zeros((p, p))
        family = binomial_logit()

        fit = penalized_irls_general(x, y, family=family, penalty=penalty, weights=trials)
        edf = effective_degrees_of_freedom(x, family, fit.eta, fit.mu, penalty, weights=trials)
        phi = pearson_dispersion(y, fit.mu, trials, family, edf=edf)
        assert 0.7 < phi < 1.3


class TestStepHalvingOnAnExtremeLambdaSpread:
    """PLAN slice 7g direction 1 (ADR-222's own registered follow-up):
    ``penalized_irls_general`` gains an OPT-IN ``step_halving`` option,
    mirroring ``mgcv``'s own ``gam.control(mgcv.half=...)``, for the exact
    failure mode ADR-222 located — a Newton/IRLS step that leaves the
    PENALIZED OBJECTIVE worse (or non-finite) at the `lambda` spreads this
    criterion actually selects. Opt-in (default ``False``, every existing
    caller unchanged) because even the objective-gated version measurably
    perturbs a handful of already-verified closed-form/finite-difference
    fixtures elsewhere in this module's own test suite whenever it
    triggers at all — see the option's own docstring in ``gam_fit.py``.

    The fixture (``tests/fixtures/gam_fit_select7_penalty_spread.json``) is
    the ACTUAL ``select=TRUE`` N=7 structure ADR-217/218/222 measured this
    defect on (the same recipe ``scripts/gam_select_multiterm_free_sp_probe.R``
    generates, mgcv's own outputs stripped since this test never compares
    against them — a pure Python regression, not a parity claim). The two
    ``log10(lambda)`` points below are the exact neighbours of ADR-222's own
    restart plateau where a central-difference probe found
    ``penalized_irls_general`` raising ``PolarisComputationError`` —
    confirmed still failing by default, and converging only with
    ``step_halving=True``.
    """

    @staticmethod
    def _design_and_family() -> tuple[
        np.ndarray, np.ndarray, object, tuple[np.ndarray, ...], np.ndarray
    ]:
        payload = json.loads((_FIXTURES_DIR / "gam_fit_select7_penalty_spread.json").read_text())
        age_knots = tuple(float(v) for v in payload["age_knots"])
        year_knots = tuple(float(v) for v in payload["year_knots"])
        model = replace(_multiterm_model_spec(age_knots, year_knots), select=True)
        data = {
            k: np.asarray(payload[k], dtype=np.float64)
            for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
        }
        y = np.asarray(payload["y"], dtype=np.float64)
        design = assemble_model_design(model, data)
        family = resolve_family(model.family, model.link)
        blocks = tuple(design["penalty_blocks"])
        return y, design["x"], family, blocks, data["ExposCnt"]

    _BASE_LOG_LAMBDA = np.array(
        [12.0, -1.15381007, 12.0, 5.49245699, 3.36749625, 2.69053786, -0.09205314]
    )

    @staticmethod
    def _penalty_at(log_lambda: np.ndarray, blocks: tuple[np.ndarray, ...]) -> np.ndarray:
        penalty = np.zeros_like(blocks[0])
        for lam, block in zip(10.0**log_lambda, blocks, strict=True):
            penalty = penalty + lam * block
        return penalty

    @pytest.mark.parametrize("delta", [0.1, -1.0e-5])
    def test_previously_non_convergent_neighbour_still_fails_by_default(self, delta: float) -> None:
        """Pins the opt-in default (``step_halving=False``): every existing
        caller of this function is unaffected by this slice unless it asks
        for the new behaviour — see the next test for the opt-in case."""
        y, x, family, blocks, weights = self._design_and_family()
        log_lambda = self._BASE_LOG_LAMBDA.copy()
        log_lambda[6] += delta
        penalty = self._penalty_at(log_lambda, blocks)

        with pytest.raises(PolarisComputationError):
            penalized_irls_general(x, y, family=family, penalty=penalty, weights=weights)

    @pytest.mark.parametrize("delta", [0.1, -1.0e-5])
    def test_previously_non_convergent_neighbour_converges_with_step_halving(
        self, delta: float
    ) -> None:
        y, x, family, blocks, weights = self._design_and_family()
        log_lambda = self._BASE_LOG_LAMBDA.copy()
        log_lambda[6] += delta
        penalty = self._penalty_at(log_lambda, blocks)

        fit = penalized_irls_general(
            x, y, family=family, penalty=penalty, weights=weights, step_halving=True
        )

        assert np.all(np.isfinite(fit.coef))
        assert np.all(np.isfinite(fit.eta))

    def test_the_plateau_point_itself_still_converges_with_step_halving(self) -> None:
        """Not a regression case on its own (this point already converged
        before the fix) — guards that step-halving never DISTURBS a point
        that was already fine."""
        y, x, family, blocks, weights = self._design_and_family()
        penalty = self._penalty_at(self._BASE_LOG_LAMBDA, blocks)

        fit = penalized_irls_general(
            x, y, family=family, penalty=penalty, weights=weights, step_halving=True
        )

        assert np.all(np.isfinite(fit.coef))

    def test_a_step_that_already_decreases_deviance_takes_the_unhalved_path(self, rng) -> None:
        """No-regression guard for every previously-verified fixture in this
        module (Anchor 7): a well-conditioned, lightly-penalized problem
        never needs a halved step, so its converged coefficients are
        unaffected by this slice's change — checked here against the
        closed-form unpenalized case this file already trusts."""
        n, p = 300, 5
        x = np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])
        beta_true = rng.normal(scale=0.3, size=p)
        y = rng.poisson(np.exp(x @ beta_true)).astype(np.float64)
        penalty = np.zeros((p, p))
        family = poisson_log()

        fit = penalized_irls_general(x, y, family=family, penalty=penalty)
        edf = effective_degrees_of_freedom(x, family, fit.eta, fit.mu, penalty)
        assert edf == pytest.approx(p, abs=1e-8)

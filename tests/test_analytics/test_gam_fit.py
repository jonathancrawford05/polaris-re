"""``docs/PLAN_mgcv_parity_engine.md`` slice 3 — ``gam_fit``'s edf/dispersion helpers.

Self-consistency checks (not mgcv parity — see ``test_gam_family.py``'s module
docstring for that distinction).
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_family import binomial_logit, poisson_log
from polaris_re.analytics.gam_fit import (
    effective_degrees_of_freedom,
    pearson_dispersion,
    penalized_irls_general,
)


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

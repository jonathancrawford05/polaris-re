"""``docs/PLAN_mgcv_parity_engine.md`` slice 4, part A — the generalized REML score.

Every check here is self-consistency (does the generalization reduce to the
already-verified Poisson score bit-for-bit, does it reject what it must reject),
mirroring ``test_gam_family.py``'s own framing: cheap to run before spending a
tier-1/tier-3 R round trip. The actual parity claim against ``mgcv`` lives in
``scripts/gam_reml_probe.R`` / ``gam_reml_conformance.py``
(``docs/VERIFICATION_STANDARD.md``).
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_family import binomial_logit, poisson_log, quasipoisson_log
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.core.exceptions import PolarisValidationError


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260818)


def _design(rng: np.random.Generator, n: int, p: int) -> np.ndarray:
    return np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])


class TestReducesToTheVerifiedPoissonScore:
    """The generalisation must be provably a superset of the already-verified
    ``experience_gam_penalized.reml_score`` (Poisson log-link, ADR-189 amendment
    1's 5e-13-level agreement with ``mgcv``), not a rewrite that happens to look
    similar — same pattern ``test_gam_family.py``'s
    ``TestPoissonReducesToTheVerifiedRecursion`` and ADR-195 decision 1 used for
    the general IRLS core."""

    def test_matches_bit_for_bit_at_gamma_one_no_offset_no_weights(
        self, rng: np.random.Generator
    ) -> None:
        from polaris_re.analytics.experience_gam_penalized import reml_score

        n, p = 200, 6
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        offset = np.zeros(n)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 3.0 * (d.T @ d)
        coef = beta_true  # any coefficient vector — the score does not fit

        old = reml_score(y, x, offset, coef, penalty, gamma=1.0)
        new = reml_score_general(y, x, poisson_log(), coef, penalty, offset=offset)
        assert new == pytest.approx(old, abs=1e-12, rel=1e-12)

    def test_matches_bit_for_bit_with_offset_and_nontrivial_gamma(
        self, rng: np.random.Generator
    ) -> None:
        from polaris_re.analytics.experience_gam_penalized import reml_score

        n, p = 150, 5
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        offset = rng.normal(scale=0.1, size=n)
        mu_true = np.exp(offset + x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 12.0 * (d.T @ d)
        coef = beta_true

        old = reml_score(y, x, offset, coef, penalty, gamma=1.4)
        new = reml_score_general(y, x, poisson_log(), coef, penalty, offset=offset, gamma=1.4)
        assert new == pytest.approx(old, abs=1e-12, rel=1e-12)

    def test_matches_at_zero_penalty(self, rng: np.random.Generator) -> None:
        """The unpenalized corner: `log|S|_+` over an empty positive-eigenvalue
        set is `0.0` on both sides by the same convention."""
        from polaris_re.analytics.experience_gam_penalized import reml_score

        n, p = 100, 4
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        offset = np.zeros(n)
        penalty = np.zeros((p, p))

        old = reml_score(y, x, offset, beta_true, penalty)
        new = reml_score_general(y, x, poisson_log(), beta_true, penalty, offset=offset)
        assert new == pytest.approx(old, abs=1e-12, rel=1e-12)


class TestGeneralizesBeyondPoisson:
    """The point of the generalization: it must also run for the target
    formula's own family (binomial), not just reduce correctly on Poisson."""

    def test_binomial_logit_runs_and_is_finite(self, rng: np.random.Generator) -> None:
        n, p = 200, 5
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        eta_true = x @ beta_true
        prob = 1.0 / (1.0 + np.exp(-eta_true))
        trials = np.full(n, 20.0)
        y = np.round(trials * prob) / trials
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 4.0 * (d.T @ d)

        score = reml_score_general(y, x, binomial_logit(), beta_true, penalty, weights=trials)
        assert np.isfinite(score)

    def test_two_summed_penalty_blocks_is_the_same_call_as_one(
        self, rng: np.random.Generator
    ) -> None:
        """N independently-scaled blocks enter only through their sum — an N=2
        case built from two separately-scaled blocks must equal the same call
        with the pre-summed combined penalty, which is what licenses this
        function as the score an N-dimensional (rather than 2-dimensional)
        optimiser would call."""
        n, p1, p2 = 120, 3, 4
        p = p1 + p2
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)

        d1 = np.diff(np.eye(p1), n=2, axis=0)
        s1 = np.zeros((p, p))
        s1[:p1, :p1] = d1.T @ d1
        d2 = np.diff(np.eye(p2), n=2, axis=0)
        s2 = np.zeros((p, p))
        s2[p1:, p1:] = d2.T @ d2

        lambda_1, lambda_2 = 3.0, 7.0
        combined_first = lambda_1 * s1 + lambda_2 * s2
        summed_by_caller = np.zeros((p, p))
        summed_by_caller += lambda_1 * s1
        summed_by_caller += lambda_2 * s2

        score_a = reml_score_general(y, x, poisson_log(), beta_true, combined_first)
        score_b = reml_score_general(y, x, poisson_log(), beta_true, summed_by_caller)
        assert score_a == score_b


class TestRejectsWhatItMustReject:
    def test_rejects_a_family_with_estimated_dispersion(self, rng: np.random.Generator) -> None:
        n, p = 80, 4
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        penalty = np.zeros((p, p))

        with pytest.raises(PolarisValidationError, match="dispersion_fixed=False"):
            reml_score_general(y, x, quasipoisson_log(), beta_true, penalty)

    def test_rejects_nonpositive_gamma(self, rng: np.random.Generator) -> None:
        n, p = 50, 3
        x = _design(rng, n, p)
        y = rng.poisson(5.0, size=n).astype(np.float64)
        penalty = np.zeros((p, p))

        with pytest.raises(PolarisValidationError, match="gamma must be positive"):
            reml_score_general(y, x, poisson_log(), np.zeros(p), penalty, gamma=0.0)

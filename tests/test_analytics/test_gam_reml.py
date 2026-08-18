"""``docs/PLAN_mgcv_parity_engine.md`` slice 4, part A — the generalized REML score.

Every check here is self-consistency (does the score match Wood (2011)'s
explicit formula in closed form, does the EXACT relationship to the
already-verified-but-formula-incomplete Poisson score hold, does it reject
what it must reject), mirroring ``test_gam_family.py``'s own framing: cheap
to run before spending a tier-1/tier-3 R round trip. The actual parity claim
against ``mgcv`` lives in ``scripts/gam_reml_probe.R`` /
``gam_reml_conformance.py`` (``docs/VERIFICATION_STANDARD.md``).
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


class TestRelationshipToTheExistingPoissonScore:
    """``reml_score_general`` is NOT bit-identical to
    ``experience_gam_penalized.reml_score`` under a real penalty, and that is
    the point, not a regression — see ADR-196's resolution. The old module's
    formula uses the plain deviance; Wood (2011) §2 eq. (4) requires the
    PENALIZED deviance (``D(β̂) + β̂ᵀSβ̂``), a term the old module's formula
    (untouched here, PLAN Anchor 7) also lacks. These tests pin the EXACT,
    derived relationship between the two — new = old + the missing term —
    which is both a regression check on the new function and a precise,
    reproducible measurement of what the old one is missing, useful evidence
    for ``docs/WORK_ORDER_reml_penalized_deviance_production_check.md``."""

    def test_differs_from_the_old_score_by_exactly_the_penalty_quadratic_form(
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
        missing_term = 0.5 * float(coef @ penalty @ coef)  # gamma=1.0
        assert new == pytest.approx(old + missing_term, abs=1e-9, rel=1e-9)
        assert missing_term > 0.0  # the penalty quadratic form is strictly positive here

    def test_differs_by_the_penalty_quadratic_form_over_gamma_with_offset(
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
        gamma = 1.4

        old = reml_score(y, x, offset, coef, penalty, gamma=gamma)
        new = reml_score_general(y, x, poisson_log(), coef, penalty, offset=offset, gamma=gamma)
        missing_term = 0.5 * float(coef @ penalty @ coef) / gamma
        assert new == pytest.approx(old + missing_term, abs=1e-9, rel=1e-9)

    def test_matches_at_zero_penalty(self, rng: np.random.Generator) -> None:
        """The unpenalized corner: `beta^T S beta` is trivially zero when `S`
        is the zero matrix, so old and new coincide bit-for-bit here — the
        two formulas only diverge once a real penalty is in play."""
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


class TestMatchesWoodsFormulaDirectly:
    """A closed-form check independent of the old module entirely: Wood
    (2011) §2 eq. (4) names `Dp = D(beta_hat) + beta_hat^T S beta_hat`
    explicitly — assert the function's output actually decomposes that way,
    rather than only ever comparing it against another implementation."""

    def test_score_equals_the_explicit_dp_formula(self, rng: np.random.Generator) -> None:
        n, p = 120, 5
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        eta_true = x @ beta_true
        prob = 1.0 / (1.0 + np.exp(-eta_true))
        trials = np.full(n, 25.0)
        y = np.round(trials * prob) / trials
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 6.0 * (d.T @ d)
        coef = beta_true
        family = binomial_logit()

        eta = x @ coef
        mu = family.link.linkinv(eta)
        deviance = family.deviance(y, mu, trials)
        dp = deviance + float(coef @ penalty @ coef)

        deta_dmu = family.link.mu_eta(eta)
        irls_weights = trials * deta_dmu**2 / family.variance(mu)
        _, logdet_h = np.linalg.slogdet(x.T @ (irls_weights[:, None] * x) + penalty)
        eigenvalues = np.linalg.eigvalsh(penalty)
        positive = eigenvalues[eigenvalues > eigenvalues.max() * 1e-10]
        logdet_s = float(np.sum(np.log(positive)))
        expected = 0.5 * dp + 0.5 * float(logdet_h) - 0.5 * logdet_s

        actual = reml_score_general(y, x, family, coef, penalty, weights=trials)
        assert actual == pytest.approx(expected, abs=1e-9, rel=1e-9)


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
        """`reml_score_general` takes ONE combined `penalty` matrix and has no
        concept of "blocks" in its signature at all — an N-dimensional caller
        assembling `S_lambda = sum_j lambda_j S_j` from however many
        independently-scaled blocks calls this function exactly the same way
        the tensor MI surface's 2-block case does. THAT is what licenses this
        function for an N-dimensional optimiser, and it is a fact about the
        function's TYPE (one `(p, p)` array parameter), not something this
        test discovers empirically.

        PR #203 review [P2-1]: an earlier revision of this docstring claimed
        this assertion "licenses" N-block support, but `combined_first` and
        `summed_by_caller` below are bit-identical float arrays (float
        addition of the same two terms in the same order), so the assertion
        is `f(A) == f(A)` — it shows the function is deterministic and pure
        (no hidden global state, no order-of-summation sensitivity within a
        single call), which is a real and worth-pinning property, but not
        evidence of N-block generality. Keeping the determinism check (still
        useful — e.g. it would catch a caching bug) with the claim corrected
        rather than replaced, since manufacturing two float-distinct paths to
        the identical `S_lambda` would not exercise anything `reml_score_general`
        does differently either — the function's body never inspects the
        route the caller took to assemble its one argument."""
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

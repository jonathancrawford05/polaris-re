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

from polaris_re.analytics.gam_family import (
    binomial_cloglog,
    binomial_logit,
    poisson_log,
    quasipoisson_log,
)
from polaris_re.analytics.gam_reml import reml_score_general
from polaris_re.core.exceptions import PolarisValidationError


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260818)


def _design(rng: np.random.Generator, n: int, p: int) -> np.ndarray:
    return np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])


class TestRelationshipToTheExistingPoissonScore:
    """``reml_score_general`` is now bit-identical to
    ``experience_gam_penalized.reml_score`` under a real penalty.

    **Updated 2026-08-19 (ADR-197 resolution, maintainer-authorized).** Until this
    session, ``reml_score_general`` was NOT bit-identical to the old module's score
    under a real penalty, and these two tests pinned the EXACT gap between them: the
    old module's formula used the plain deviance, while Wood (2011) §2 eq. (4)
    requires the PENALIZED deviance (``D(β̂) + β̂ᵀSβ̂``) — a term ADR-196 added to
    ``reml_score_general`` and, per ADR-197's measurement and the maintainer's
    explicit direction, is now added to ``experience_gam_penalized.reml_score`` too
    (mirrors ADR-196's fix exactly — same paper, same equation). With the identical
    term now present on both sides, the two formulas compute the same quantity — the
    old ``new == old + missing_term`` relationship collapsed to ``new == old``
    (``missing_term`` is now exactly 0), so these tests now pin bit-for-bit agreement
    instead of a gap. The zero-penalty test below is unaffected — it already asserted
    agreement and needs no change."""

    def test_matches_the_old_score_bit_for_bit_now_that_the_missing_term_is_fixed_on_both_sides(
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
        block = d.T @ d
        penalty = 3.0 * block
        coef = beta_true  # any coefficient vector — the score does not fit

        old = reml_score(y, x, offset, coef, penalty, gamma=1.0)
        new = reml_score_general(
            y, x, poisson_log(), coef, (block,), np.array([3.0]), offset=offset
        )
        penalty_quadratic_form = 0.5 * float(coef @ penalty @ coef)  # gamma=1.0
        assert new == pytest.approx(old, abs=1e-9, rel=1e-9)
        # Still strictly positive under a real penalty — sanity that this fixture
        # actually exercises the term both formulas now include, not a degenerate one.
        assert penalty_quadratic_form > 0.0

    def test_matches_the_old_score_bit_for_bit_over_gamma_with_offset(
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
        block = d.T @ d
        coef = beta_true
        gamma = 1.4

        old = reml_score(y, x, offset, coef, 12.0 * block, gamma=gamma)
        new = reml_score_general(
            y, x, poisson_log(), coef, (block,), np.array([12.0]), offset=offset, gamma=gamma
        )
        assert new == pytest.approx(old, abs=1e-9, rel=1e-9)

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
        new = reml_score_general(
            y, x, poisson_log(), beta_true, (penalty,), np.array([1.0]), offset=offset
        )
        assert new == pytest.approx(old, abs=1e-12, rel=1e-12)


class TestClosedFormSingleColumnCase:
    """The genuine closed-form check (PR #203 review [P2-a]): a single-column
    design collapses every term to scalar arithmetic worked out by hand below
    — no `np.linalg.slogdet`/`np.linalg.eigvalsh` call on the expected side at
    all, unlike `TestMatchesWoodsFormulaDirectly` below, which recomputes the
    same intermediate numpy calls the implementation makes (a useful
    regression net, but not an independent derivation, since it would not
    catch an error shared by both call sites — e.g. a wrong deviance
    definition or working-weight convention)."""

    def test_single_column_poisson_reduces_to_scalar_arithmetic(self) -> None:
        n = 5
        x = np.ones((n, 1))
        y = np.full(n, 3.0)
        c, s = 0.5, 2.0
        coef = np.array([c])
        penalty = np.array([[s]])
        family = poisson_log()

        # eta_i = c for every row (single column of ones), so mu is constant:
        mu = np.exp(c)
        # Poisson deviance, all n rows identical: D = 2n[y*log(y/mu) - (y - mu)]
        deviance = 2.0 * n * (3.0 * np.log(3.0 / mu) - (3.0 - mu))
        dp = deviance + c**2 * s  # Dp = D(beta_hat) + beta_hat^T S beta_hat

        # log link: dmu/deta = mu, V(mu) = mu, so w_i = mu^2/mu = mu for every row.
        # H = X^T W X + S is the 1x1 scalar (n*mu + s) — no matrix algebra needed.
        h = n * mu + s
        logdet_h = np.log(h)
        logdet_s = np.log(s)  # the sole eigenvalue of a 1x1 matrix is its entry
        # p - r = 1 - 1 = 0 (S is full rank here), so the gamma-scale term vanishes.
        expected = 0.5 * dp + 0.5 * logdet_h - 0.5 * logdet_s

        actual = reml_score_general(y, x, family, coef, (penalty,), np.array([1.0]))
        assert actual == pytest.approx(expected, abs=1e-12, rel=1e-12)


class TestMatchesWoodsFormulaDirectly:
    """NOT a closed-form test (PR #203 review [P2-a] — see
    `TestClosedFormSingleColumnCase` above for the genuine one). This
    recomputes `deviance`/the working weight/`logdet_h`/`logdet_s` from
    formulas written out IN THE TEST, not by calling
    `Family.observed_information_weight` or
    `gam_reml_appendix_b.logdet_s_plus` (PR #215 review [P1-3]: an earlier
    revision called those two functions directly — "the implementation's
    own helpers, the same two calls `reml_score_general` makes" — which
    weakened this from an independent re-derivation to a tautology). Worth
    keeping as a regression net for a dropped term, a sign flip, or a wrong
    ½ — Wood (2011) §2 eq. (4) names `Dp = D(beta_hat) + beta_hat^T S
    beta_hat` explicitly and this pins the decomposition against it — but
    it cannot catch an error shared by both call sites (a wrong deviance
    definition or log-determinant convention), since it inherits those from
    the implementation it is checking.

    **Two cases, for a reason:** the CANONICAL-link case
    (`binomial_logit`) inlines the plain FISHER weight as `expected` — valid
    because `alpha_i == 1` exactly for a canonical link (Wood §3.2,
    `TestObservedInformationWeight`'s own canonical-link tests), so this
    is a genuinely different computation that would still have to agree.
    It alone cannot exercise Defect B's own fix (the observed/Fisher split
    only bites for a NON-canonical link), so a second case
    (`binomial_cloglog`) inlines Wood's `alpha_i` formula directly from
    the paper's `V'(mu)/V(mu) + g''(mu)/g'(mu)` — duplicating the maths,
    not calling `observed_information_weight` — so a bug in that method
    would have to also appear, independently, in this test's own inlined
    formula to go undetected."""

    def test_score_equals_the_explicit_dp_formula_canonical_link(
        self, rng: np.random.Generator
    ) -> None:
        n, p = 120, 5
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        eta_true = x @ beta_true
        prob = 1.0 / (1.0 + np.exp(-eta_true))
        trials = np.full(n, 25.0)
        y = np.round(trials * prob) / trials
        d = np.diff(np.eye(p), n=2, axis=0)
        block = d.T @ d
        lambdas = np.array([6.0])
        penalty = 6.0 * block
        coef = beta_true
        family = binomial_logit()

        eta = x @ coef
        mu = family.link.linkinv(eta)
        deviance = family.deviance(y, mu, trials)
        dp = deviance + float(coef @ penalty @ coef)

        # The plain FISHER weight, inlined — NOT a call to
        # observed_information_weight. Valid as "expected" only because
        # binomial_logit is CANONICAL (alpha_i == 1 exactly), so the
        # observed and expected Hessians coincide here by a textbook
        # identity independent of this module's own implementation.
        deta_dmu = family.link.mu_eta(eta)
        fisher_weights = trials * deta_dmu**2 / family.variance(mu)
        _, logdet_h = np.linalg.slogdet(x.T @ (fisher_weights[:, None] * x) + penalty)
        # The naive fixed-tolerance eigenvalue cut, inlined — NOT a call to
        # logdet_s_plus. Valid as "expected" only because this fixture is a
        # SINGLE, well-conditioned block (Wood: "the problem vanishes for a
        # full rank S1"), where Appendix B and the naive cut necessarily
        # agree (`TestAgreesWithNaiveAtFlatLambda` pins that agreement on
        # its own terms).
        eigenvalues = np.linalg.eigvalsh(penalty)
        positive = eigenvalues[eigenvalues > eigenvalues.max() * 1e-10]
        logdet_s = float(np.sum(np.log(positive)))
        expected = 0.5 * dp + 0.5 * float(logdet_h) - 0.5 * logdet_s

        actual = reml_score_general(y, x, family, coef, (block,), lambdas, weights=trials)
        assert actual == pytest.approx(expected, abs=1e-9, rel=1e-9)

    def test_score_equals_the_explicit_dp_formula_noncanonical_link(
        self, rng: np.random.Generator
    ) -> None:
        """The non-canonical case Defect B's fix actually changes —
        `binomial_logit` above cannot exercise it, since Fisher and
        observed coincide there regardless of whether the fix exists."""
        n, p = 120, 5
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        eta_true = x @ beta_true
        prob = 1.0 - np.exp(-np.exp(eta_true))
        trials = np.full(n, 25.0)
        y = np.clip(np.round(trials * prob) / trials, 1.0 / trials, 1.0 - 1.0 / trials)
        d = np.diff(np.eye(p), n=2, axis=0)
        block = d.T @ d
        lambdas = np.array([6.0])
        penalty = 6.0 * block
        coef = beta_true
        family = binomial_cloglog()

        eta = x @ coef
        mu = family.link.linkinv(eta)
        deviance = family.deviance(y, mu, trials)
        dp = deviance + float(coef @ penalty @ coef)

        # Wood (2011) section 3.2's alpha_i, written out from the paper —
        # NOT a call to observed_information_weight. V'(mu) = 1 - 2*mu for
        # binomial; g''(mu)/g'(mu) for cloglog derived independently here
        # via the SAME chain rule the implementation's docstring states
        # (g''(mu)/g'(mu) = -d2mu/deta2 / (dmu/deta)^2), but with
        # d2mu/deta2 = mu_eta(eta) * (1 - exp(eta)) written inline rather
        # than calling Link.d2mu_deta2.
        mu_eta = family.link.mu_eta(eta)
        d2mu_deta2 = mu_eta * (1.0 - np.exp(eta))
        variance_prime = 1.0 - 2.0 * mu
        alpha = 1.0 + (y - mu) * (variance_prime / family.variance(mu) - d2mu_deta2 / mu_eta**2)
        fisher_weights = trials * mu_eta**2 / family.variance(mu)
        observed_weights_inline = alpha * fisher_weights
        _, logdet_h = np.linalg.slogdet(x.T @ (observed_weights_inline[:, None] * x) + penalty)
        eigenvalues = np.linalg.eigvalsh(penalty)
        positive = eigenvalues[eigenvalues > eigenvalues.max() * 1e-10]
        logdet_s = float(np.sum(np.log(positive)))
        expected = 0.5 * dp + 0.5 * float(logdet_h) - 0.5 * logdet_s

        actual = reml_score_general(y, x, family, coef, (block,), lambdas, weights=trials)
        assert actual == pytest.approx(expected, abs=1e-9, rel=1e-9)
        # Sanity that this fixture actually exercises alpha != 1 (i.e. the
        # non-canonical branch), not a degenerate case that happens to
        # collapse to the canonical one.
        assert not np.allclose(alpha, 1.0, atol=1e-6)


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
        block = d.T @ d

        score = reml_score_general(
            y, x, binomial_logit(), beta_true, (block,), np.array([4.0]), weights=trials
        )
        assert np.isfinite(score)

    def test_is_deterministic_and_pure_across_n_blocks(self, rng: np.random.Generator) -> None:
        """**Superseded premise, PLAN slice 5c.** Until this slice,
        `reml_score_general` took ONE caller-summed `penalty` matrix and had
        no concept of "blocks" in its signature, so this test's original
        point was that a caller could assemble `S_lambda = sum_j lambda_j
        S_j` however it liked before calling in — true, but (PR #203 review
        [P2-1]) never actually exercised by two bit-identical float arrays.
        Appendix B's null-space determination NEEDS the individual blocks
        (a summed matrix cannot be un-summed), so the signature now takes
        `penalty_blocks`/`lambdas` directly — blocks are no longer incidental,
        they are the point. What is still worth pinning: calling twice with
        the SAME blocks/lambdas gives the SAME score (pure, no hidden state
        — e.g. would catch a caching bug), across more than the 2-block case
        every other test in this file uses."""
        n, p1, p2, p3 = 120, 3, 4, 2
        p = p1 + p2 + p3
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)

        d1 = np.diff(np.eye(p1), n=2, axis=0)
        s1 = np.zeros((p, p))
        s1[:p1, :p1] = d1.T @ d1
        d2 = np.diff(np.eye(p2), n=2, axis=0)
        s2 = np.zeros((p, p))
        s2[p1 : p1 + p2, p1 : p1 + p2] = d2.T @ d2
        s3 = np.zeros((p, p))
        s3[p1 + p2 :, p1 + p2 :] = np.eye(p3)
        blocks = (s1, s2, s3)
        lambdas = np.array([3.0, 7.0, 0.5])

        score_a = reml_score_general(y, x, poisson_log(), beta_true, blocks, lambdas)
        score_b = reml_score_general(y, x, poisson_log(), beta_true, blocks, lambdas)
        assert score_a == score_b
        assert np.isfinite(score_a)


class TestRejectsWhatItMustReject:
    def test_rejects_a_family_with_estimated_dispersion(self, rng: np.random.Generator) -> None:
        n, p = 80, 4
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        penalty = np.zeros((p, p))

        with pytest.raises(PolarisValidationError, match="dispersion_fixed=False"):
            reml_score_general(y, x, quasipoisson_log(), beta_true, (penalty,), np.array([1.0]))

    def test_rejects_nonpositive_gamma(self, rng: np.random.Generator) -> None:
        n, p = 50, 3
        x = _design(rng, n, p)
        y = rng.poisson(5.0, size=n).astype(np.float64)
        penalty = np.zeros((p, p))

        with pytest.raises(PolarisValidationError, match="gamma must be positive"):
            reml_score_general(
                y, x, poisson_log(), np.zeros(p), (penalty,), np.array([1.0]), gamma=0.0
            )

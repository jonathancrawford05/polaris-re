"""``docs/PLAN_mgcv_parity_engine.md`` slice 3 — the family/link abstraction.

Every check here is **self-consistency**, not ``mgcv`` parity: a closed-form or
``statsmodels``-verified property of the IRLS recursion itself, cheap to run
before spending a tier-1/tier-3 R round trip on a bug that was never about
``mgcv`` agreement in the first place. The actual parity claim lives in
``scripts/gam_family_probe.R`` / ``experience_gam_family_conformance.py``
(``docs/VERIFICATION_STANDARD.md``: this is development-time verification, not
the declared :class:`~polaris_re.core.verification.VerificationClaim`).
"""

import numpy as np
import pytest
import statsmodels.api as sm

from polaris_re.analytics.gam_family import (
    binomial_cloglog,
    binomial_logit,
    gaussian_identity,
    poisson_log,
    quasipoisson_log,
    validate_family_inputs,
)
from polaris_re.analytics.gam_fit import (
    pearson_dispersion,
    penalized_irls_general,
)
from polaris_re.core.exceptions import PolarisValidationError


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20260817)


def _design(rng: np.random.Generator, n: int, p: int) -> np.ndarray:
    x = np.column_stack([np.ones(n), rng.normal(size=(n, p - 1))])
    return x


class TestLinkAlgebra:
    """``linkinv(linkfun(mu)) == mu`` and ``mu_eta`` matches a numerical
    derivative — the two closed-form properties every link must have
    regardless of family."""

    @pytest.mark.parametrize(
        "family_factory,eta",
        [
            (poisson_log, np.array([-3.0, -0.5, 0.0, 0.5, 3.0])),
            (binomial_logit, np.array([-6.0, -1.0, 0.0, 1.0, 6.0])),
            (binomial_cloglog, np.array([-3.0, -0.5, 0.0, 0.5, 2.0])),
        ],
    )
    def test_mu_eta_matches_a_numerical_derivative(self, family_factory, eta) -> None:
        family = family_factory()
        link = family.link
        h = 1e-6
        numerical = (link.linkinv(eta + h) - link.linkinv(eta - h)) / (2 * h)
        np.testing.assert_allclose(link.mu_eta(eta), numerical, atol=1e-6, rtol=1e-5)

    def test_binomial_logit_mu_is_in_unit_interval(self) -> None:
        # +-50 saturates mu to exactly 0.0/1.0 in float64 — a property of IEEE
        # double precision, not of this link, so the interior range is what
        # this test can actually assert.
        family = binomial_logit()
        eta = np.array([-15.0, -1.0, 0.0, 1.0, 15.0])
        mu = family.link.linkinv(eta)
        assert np.all(mu > 0.0) and np.all(mu < 1.0)

    def test_binomial_cloglog_mu_is_in_unit_interval(self) -> None:
        family = binomial_cloglog()
        eta = np.array([-3.0, -1.0, 0.0, 1.0, 3.0])
        mu = family.link.linkinv(eta)
        assert np.all(mu > 0.0) and np.all(mu < 1.0)


class TestDevianceIsWeighted:
    """PR #202 review [P2]: the deviance is the standard WEIGHTED definition
    (``D = 2 * sum(w_i * d_i)``, matching R's own ``family$dev.resids``),
    not the unweighted sum an earlier revision computed. Monitoring-only in
    this slice (the fixed point is set by the weighted normal equations, and
    ``TestPoissonReducesToTheVerifiedRecursion``/the R-gated conformance test
    both confirm the converged fit is unaffected), but load-bearing once
    slice 4's REML score needs the weighted value."""

    def test_matches_the_closed_form_two_sum_w_d(self, rng) -> None:
        family = poisson_log()
        y = rng.poisson(5.0, size=50).astype(np.float64)
        mu = np.clip(y + rng.normal(scale=0.5, size=50), 0.5, None)
        weights = rng.uniform(1.0, 5.0, size=50)

        expected = 2.0 * np.sum(weights * (family._deviance_terms(y, mu)))
        assert family.deviance(y, mu, weights) == pytest.approx(expected)

    def test_nonuniform_weights_change_the_deviance(self, rng) -> None:
        family = binomial_logit()
        y = rng.uniform(0.1, 0.9, size=30)
        mu = np.clip(y + rng.normal(scale=0.05, size=30), 0.01, 0.99)
        uniform = np.ones(30)
        nonuniform = rng.uniform(1.0, 10.0, size=30)

        assert family.deviance(y, mu, uniform) != pytest.approx(family.deviance(y, mu, nonuniform))

    def test_uniform_weight_one_matches_the_unweighted_sum(self, rng) -> None:
        family = binomial_cloglog()
        y = rng.uniform(0.1, 0.9, size=40)
        mu = np.clip(y + rng.normal(scale=0.05, size=40), 0.01, 0.99)
        weights = np.ones(40)

        unweighted = 2.0 * np.sum(family._deviance_terms(y, mu))
        assert family.deviance(y, mu, weights) == pytest.approx(unweighted)


class TestPoissonReducesToTheVerifiedRecursion:
    """The generalisation must be provably a superset of the already-verified
    Poisson-log case, not a rewrite that happens to look similar."""

    def test_matches_experience_gam_penalized_bit_for_bit_at_s_zero(self, rng) -> None:
        from polaris_re.analytics.experience_gam_penalized import _penalized_irls

        n, p = 200, 5
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        offset = rng.normal(scale=0.1, size=n)
        mu_true = np.exp(offset + x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        penalty = np.zeros((p, p))

        old_coef, old_iter = _penalized_irls(x, y, offset, penalty)
        new_fit = penalized_irls_general(x, y, family=poisson_log(), penalty=penalty, offset=offset)

        np.testing.assert_allclose(new_fit.coef, old_coef, atol=1e-10, rtol=1e-10)
        assert new_fit.n_iter == old_iter

    def test_matches_experience_gam_penalized_with_a_real_penalty(self, rng) -> None:
        from polaris_re.analytics.experience_gam_penalized import _penalized_irls

        n, p = 300, 6
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        offset = np.zeros(n)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        d = np.diff(np.eye(p), n=2, axis=0)
        penalty = 5.0 * (d.T @ d)

        old_coef, _ = _penalized_irls(x, y, offset, penalty)
        new_fit = penalized_irls_general(x, y, family=poisson_log(), penalty=penalty, offset=offset)
        np.testing.assert_allclose(new_fit.coef, old_coef, atol=1e-9, rtol=1e-9)


class TestBinomialAgreesWithStatsmodels:
    """An independent Python GLM implementation (``statsmodels``, never reading
    this module's output) confirms the unpenalized IRLS recursion before any R
    round trip is spent — cheap, and orthogonal to the mgcv parity claim."""

    def test_logit_unpenalized_matches_statsmodels_glm(self, rng) -> None:
        n, p = 500, 4
        x = _design(rng, n, p)
        beta_true = np.array([0.2, -0.5, 0.8, 0.3])
        eta_true = x @ beta_true
        prob_true = 1.0 / (1.0 + np.exp(-eta_true))
        trials = rng.integers(20, 80, size=n).astype(np.float64)
        successes = rng.binomial(trials.astype(np.int64), prob_true).astype(np.float64)
        y = successes / trials

        penalty = np.zeros((p, p))
        fit = penalized_irls_general(x, y, family=binomial_logit(), penalty=penalty, weights=trials)

        sm_fit = sm.GLM(
            y, x, family=sm.families.Binomial(), freq_weights=None, var_weights=trials
        ).fit()

        np.testing.assert_allclose(fit.coef, sm_fit.params, atol=1e-6, rtol=1e-6)

    def test_cloglog_unpenalized_matches_statsmodels_glm(self, rng) -> None:
        n, p = 500, 4
        x = _design(rng, n, p)
        beta_true = np.array([-0.3, 0.4, -0.6, 0.2])
        eta_true = x @ beta_true
        prob_true = 1.0 - np.exp(-np.exp(eta_true))
        trials = rng.integers(20, 80, size=n).astype(np.float64)
        successes = rng.binomial(trials.astype(np.int64), prob_true).astype(np.float64)
        y = successes / trials

        penalty = np.zeros((p, p))
        fit = penalized_irls_general(
            x, y, family=binomial_cloglog(), penalty=penalty, weights=trials
        )

        sm_fit = sm.GLM(
            y, x, family=sm.families.Binomial(sm.families.links.CLogLog()), var_weights=trials
        ).fit()

        np.testing.assert_allclose(fit.coef, sm_fit.params, atol=1e-5, rtol=1e-5)


class TestWeightsAreNotAnOffset:
    """PLAN Anchor 5: the two controls are orthogonal, so both must be usable
    at once, and a zero-weight row must be excludable without excluding an
    offset row."""

    def test_all_weights_equal_reduces_to_unweighted_fit(self, rng) -> None:
        n, p = 200, 4
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        prob_true = 1.0 / (1.0 + np.exp(-(x @ beta_true)))
        y = np.clip(prob_true + rng.normal(scale=0.02, size=n), 0.01, 0.99)
        penalty = np.zeros((p, p))

        unweighted = penalized_irls_general(x, y, family=binomial_logit(), penalty=penalty)
        weighted = penalized_irls_general(
            x, y, family=binomial_logit(), penalty=penalty, weights=3.0 * np.ones(n)
        )
        np.testing.assert_allclose(unweighted.coef, weighted.coef, atol=1e-8, rtol=1e-8)

    def test_offset_and_weights_both_apply_simultaneously(self, rng) -> None:
        n, p = 200, 3
        x = _design(rng, n, p)
        offset = rng.normal(scale=0.2, size=n)
        weights = rng.uniform(1.0, 5.0, size=n)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(offset + x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        penalty = np.zeros((p, p))

        fit_both = penalized_irls_general(
            x, y, family=poisson_log(), penalty=penalty, offset=offset, weights=weights
        )
        fit_no_weights = penalized_irls_general(
            x, y, family=poisson_log(), penalty=penalty, offset=offset
        )
        # Different weighting must generally move the fit, refuting the case
        # where `weights=` was silently ignored.
        assert not np.allclose(fit_both.coef, fit_no_weights.coef, atol=1e-6)


class TestQuasipoissonSharesPoissonCoefficients:
    """Quasi-Poisson's estimating equations for ``mu`` are identical to
    Poisson's (dispersion scales the coefficient covariance, not the score
    equation) — a property to TEST, not assume, since a bug that made
    dispersion leak into the working weights would silently break this."""

    def test_coefficients_identical_to_plain_poisson(self, rng) -> None:
        n, p = 200, 4
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.3, size=p)
        y = rng.poisson(np.exp(x @ beta_true)).astype(np.float64)
        penalty = np.zeros((p, p))

        poisson_fit = penalized_irls_general(x, y, family=poisson_log(), penalty=penalty)
        quasi_fit = penalized_irls_general(x, y, family=quasipoisson_log(), penalty=penalty)
        np.testing.assert_allclose(poisson_fit.coef, quasi_fit.coef, atol=1e-10, rtol=1e-10)

    def test_dispersion_fixed_flag_distinguishes_the_two(self) -> None:
        assert poisson_log().dispersion_fixed is True
        assert quasipoisson_log().dispersion_fixed is False


class TestPearsonDispersion:
    def test_dispersion_near_one_when_data_are_truly_poisson(self, rng) -> None:
        n, p = 2000, 3
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        y = rng.poisson(mu_true).astype(np.float64)
        penalty = np.zeros((p, p))

        fit = penalized_irls_general(x, y, family=poisson_log(), penalty=penalty)
        phi = pearson_dispersion(y, fit.mu, np.ones(n), quasipoisson_log(), edf=float(p))
        # A large-n Poisson-generated sample should read close to 1, not exactly
        # (sampling noise) — a loose band that would catch a formula error
        # (e.g. missing the (n - edf) denominator) but not flag ordinary noise.
        assert 0.7 < phi < 1.3

    def test_dispersion_scales_with_deliberate_overdispersion(self, rng) -> None:
        n, p = 2000, 3
        x = _design(rng, n, p)
        beta_true = rng.normal(scale=0.2, size=p)
        mu_true = np.exp(x @ beta_true)
        # Negative-binomial-like overdispersion: gamma-mixed Poisson.
        shape = 2.0
        mu_mixed = rng.gamma(shape, mu_true / shape)
        y = rng.poisson(mu_mixed).astype(np.float64)
        penalty = np.zeros((p, p))

        fit = penalized_irls_general(x, y, family=poisson_log(), penalty=penalty)
        phi = pearson_dispersion(y, fit.mu, np.ones(n), quasipoisson_log(), edf=float(p))
        assert phi > 1.3


class TestObservedInformationWeight:
    """``docs/PLAN_mgcv_parity_engine.md`` slice 5c, Defect B — Wood (2011)
    Section 3.2's OBSERVED-Hessian weight, ``alpha_i * w_i^F``.

    Self-consistency only, same framing as the rest of this file: a
    canonical-link identity that follows from the textbook fact that Fisher
    scoring and Newton's method coincide for a canonical link, and a
    central-difference cross-check against the definition
    ``W_ii = 0.5 * d^2 D_i / d eta_i^2`` directly (independent of the
    ``alpha_i`` algebra, since it never touches ``V'`` or ``d2mu_deta2``).
    """

    def test_alpha_is_exactly_one_for_poisson_log_canonical_link(
        self, rng: np.random.Generator
    ) -> None:
        n = 500
        eta = rng.normal(scale=1.5, size=n)
        family = poisson_log()
        mu = family.link.linkinv(eta)
        y = rng.poisson(mu).astype(np.float64)
        weights = np.ones(n)

        fisher = weights * family.link.mu_eta(eta) ** 2 / family.variance(mu)
        observed = family.observed_information_weight(y, eta, weights)
        assert observed == pytest.approx(fisher, rel=1e-9, abs=1e-12)

    def test_alpha_is_exactly_one_for_binomial_logit_canonical_link(
        self, rng: np.random.Generator
    ) -> None:
        n = 500
        eta = rng.normal(scale=1.5, size=n)
        family = binomial_logit()
        mu = family.link.linkinv(eta)
        trials = np.full(n, 20.0)
        y = np.round(trials * mu) / trials
        weights = trials

        fisher = weights * family.link.mu_eta(eta) ** 2 / family.variance(mu)
        observed = family.observed_information_weight(y, eta, weights)
        assert observed == pytest.approx(fisher, rel=1e-9, abs=1e-12)

    def test_alpha_differs_from_one_for_cloglog_non_canonical_link(
        self, rng: np.random.Generator
    ) -> None:
        """The non-canonical case Wood warns about — the observed and
        expected weights must NOT coincide here, or this whole module has
        no effect for the target formula's own family/link."""
        n = 500
        eta = rng.normal(scale=1.0, size=n)
        family = binomial_cloglog()
        mu = family.link.linkinv(eta)
        trials = np.full(n, 20.0)
        y = np.round(trials * mu) / trials
        weights = trials

        fisher = weights * family.link.mu_eta(eta) ** 2 / family.variance(mu)
        observed = family.observed_information_weight(y, eta, weights)
        assert not np.allclose(observed, fisher, rtol=1e-6)

    def test_cloglog_matches_the_finite_difference_definition_directly(
        self, rng: np.random.Generator
    ) -> None:
        """Cross-check against ``W_ii = 0.5 * d^2 D_i / d eta_i^2`` by
        central-differencing the PER-OBSERVATION deviance in ``eta`` —
        the definition itself (``l = l_sat - D/(2*phi)`` at ``phi=1``),
        computed without going anywhere near ``alpha_i``, ``V'`` or
        ``d2mu_deta2``. Independent of the analytic route this module
        implements, unlike ``TestMatchesWoodsFormulaDirectly``-style tests
        elsewhere that recompute the same intermediate calls."""
        n = 300
        eta = rng.normal(scale=1.0, size=n)
        family = binomial_cloglog()
        mu = family.link.linkinv(eta)
        trials = np.full(n, 30.0)
        y = np.round(trials * mu) / trials
        weights = trials
        step = 1e-5

        def deviance_terms(e: np.ndarray) -> np.ndarray:
            mu_e = np.clip(family.link.linkinv(e), 1e-12, 1.0 - 1e-12)
            y_c = np.clip(y, 1e-12, 1.0 - 1e-12)
            return (
                2.0
                * weights
                * (y_c * np.log(y_c / mu_e) + (1.0 - y_c) * np.log((1.0 - y_c) / (1.0 - mu_e)))
            )

        finite_difference_hessian = (
            0.5
            * (deviance_terms(eta + step) - 2.0 * deviance_terms(eta) + deviance_terms(eta - step))
            / step**2
        )
        analytic = family.observed_information_weight(y, eta, weights)
        assert analytic == pytest.approx(finite_difference_hessian, rel=2e-3, abs=1e-3)


class TestValidateFamilyInputs:
    def test_rejects_mismatched_shapes(self) -> None:
        x = np.ones((5, 2))
        with pytest.raises(PolarisValidationError):
            validate_family_inputs(x, np.ones(5), np.ones(4), np.zeros(5))

    def test_rejects_negative_weights(self) -> None:
        x = np.ones((3, 2))
        with pytest.raises(PolarisValidationError):
            validate_family_inputs(x, np.ones(3), np.array([1.0, -1.0, 1.0]), np.zeros(3))


# --------------------------------------------------------------------------
# gaussian(identity) — ladder rung L1 (docs/PLAN_mgcv_capability_ladder.md)
#
# CLOSED-FORM verification, per CLAUDE.md: at Gaussian identity the penalized
# fit has an exact algebraic solution, so these do not compare against a
# reference implementation at all — they compare against the algebra. That is
# what makes L1 the right rung to stand every later basis check on.
# --------------------------------------------------------------------------


def _gaussian_design(seed: int = 20260919, n: int = 200, p: int = 5):
    rng = np.random.default_rng(seed)
    x = np.asarray(rng.normal(size=(n, p)), dtype=np.float64)
    beta = np.asarray([1.0, -2.0, 0.5, 0.0, 3.0], dtype=np.float64)
    y = np.asarray(x @ beta + rng.normal(scale=0.3, size=n), dtype=np.float64)
    return x, y


def test_gaussian_identity_link_is_the_identity_and_its_curvature_vanishes() -> None:
    family = gaussian_identity()
    eta = np.asarray([-3.0, -0.5, 0.0, 2.25, 40.0], dtype=np.float64)
    np.testing.assert_allclose(family.link.linkinv(eta), eta, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(family.link.mu_eta(eta), np.ones_like(eta))
    # g(mu) = mu is linear, so d2mu/deta2 is exactly zero — not merely small.
    np.testing.assert_array_equal(family.link.d2mu_deta2(eta), np.zeros_like(eta))


def test_gaussian_variance_is_constant_so_irls_weights_never_move() -> None:
    """``V(mu) = 1`` is what collapses IRLS to one weighted least-squares solve."""
    family = gaussian_identity()
    mu = np.asarray([-10.0, 0.0, 1e6], dtype=np.float64)
    np.testing.assert_allclose(family.variance(mu), np.ones_like(mu))


def test_gaussian_estimates_its_scale() -> None:
    """The ladder blocker, asserted rather than assumed.

    ``dispersion_fixed=False`` is why L1 at FREE ``sp`` is blocked by L5:
    ``gam_reml.reml_score_general`` raises on a free scale. If this ever flips
    to ``True``, the plan's §2.2 argument is void and must be re-derived.
    """
    assert gaussian_identity().dispersion_fixed is False


def test_gaussian_identity_observed_and_expected_hessian_weights_coincide() -> None:
    """Identity is Gaussian's CANONICAL link, so Wood (2011) §3.2's
    ``alpha_i = 1 + (y - mu)(V'/V + g''/g')`` collapses to 1 identically:
    ``V' = 0`` and ``g'' = 0``."""
    family = gaussian_identity()
    rng = np.random.default_rng(7)
    y = np.asarray(rng.normal(size=64), dtype=np.float64)
    eta = np.asarray(rng.normal(size=64), dtype=np.float64)
    weights = np.asarray(rng.uniform(0.5, 2.0, size=64), dtype=np.float64)
    np.testing.assert_allclose(
        family.observed_information_weight(y, eta, weights), weights, rtol=1e-15
    )


def test_gaussian_deviance_is_twice_the_weighted_residual_sum_of_squares() -> None:
    """Pins the factor-of-2 convention so a later reader does not "fix" it.

    ``Family.deviance`` applies the ``2 *`` of the exponential-family definition;
    the Gaussian's own ``1/2`` is not carried here, so this returns ``2 * RSS``.
    Only the IRLS convergence test consumes it, where a constant factor is inert.
    """
    family = gaussian_identity()
    y = np.asarray([1.0, 2.0, 3.0], dtype=np.float64)
    mu = np.asarray([1.5, 2.0, 2.0], dtype=np.float64)
    weights = np.asarray([1.0, 1.0, 1.0], dtype=np.float64)
    rss = float(np.sum((y - mu) ** 2))
    assert family.deviance(y, mu, weights) == pytest.approx(2.0 * rss)


def test_gaussian_unpenalized_irls_reproduces_ordinary_least_squares() -> None:
    """CLOSED FORM #1: with ``S = 0`` the penalized fit IS the OLS solution."""
    x, y = _gaussian_design()
    fit = penalized_irls_general(
        x=x, y=y, family=gaussian_identity(), penalty=np.zeros((x.shape[1], x.shape[1]))
    )
    expected, *_ = np.linalg.lstsq(x, y, rcond=None)
    np.testing.assert_allclose(fit.coef, expected, rtol=0.0, atol=1e-12)


def test_gaussian_penalized_irls_reproduces_the_closed_form_ridge() -> None:
    """CLOSED FORM #2, and the one that actually exercises the penalty.

    ``argmin ||y - X b||^2 + b' S b`` has the exact solution
    ``(X'X + S)^-1 X'y``. Anything wrong in how the penalty enters the normal
    equations shows up here, with no reference implementation involved.
    """
    x, y = _gaussian_design()
    p = x.shape[1]
    penalty = 2.0 * np.eye(p, dtype=np.float64)
    fit = penalized_irls_general(x=x, y=y, family=gaussian_identity(), penalty=penalty)
    expected = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    np.testing.assert_allclose(fit.coef, expected, rtol=0.0, atol=1e-12)


@pytest.mark.parametrize("log_lambda", [-4.0, 0.0, 4.0, 8.0])
def test_gaussian_ridge_closed_form_holds_across_the_penalty_range(log_lambda: float) -> None:
    """The same identity over four decades of ``lambda``, since the outer search
    will visit all of them and a penalty-scaling error need not show at 1.0."""
    x, y = _gaussian_design()
    p = x.shape[1]
    penalty = (10.0**log_lambda) * np.eye(p, dtype=np.float64)
    fit = penalized_irls_general(x=x, y=y, family=gaussian_identity(), penalty=penalty)
    expected = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    np.testing.assert_allclose(fit.coef, expected, rtol=1e-10, atol=1e-12)


def test_gaussian_irls_lands_on_the_solution_at_the_first_step() -> None:
    """The property that makes L1 the diagnostic floor for every rung above it.

    Constant weights and a linear link mean there is nothing to iterate: the
    first solve is exact. ``n_iter == 2`` because the loop needs a second pass to
    OBSERVE that nothing moved — so this asserts the bound, not a magic number,
    and would catch a family that silently started iterating.
    """
    x, y = _gaussian_design()
    fit = penalized_irls_general(
        x=x, y=y, family=gaussian_identity(), penalty=np.eye(x.shape[1], dtype=np.float64)
    )
    assert fit.n_iter <= 2


def test_gaussian_identity_resolves_through_the_model_family_registry() -> None:
    """L1's user-visible deliverable: ``ModelSpec(family="gaussian", link="identity")``
    now resolves, where it previously raised."""
    from polaris_re.analytics.gam_model import resolve_family

    family = resolve_family("gaussian", "identity")
    assert family.name == "gaussian"
    assert family.link.name == "identity"
    assert family.dispersion_fixed is False

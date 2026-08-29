"""Exponential-family / link abstraction for the ``mgcv``-parity GAM engine.

``docs/PLAN_mgcv_parity_engine.md`` slice 3: the existing penalized IRLS core
(:mod:`polaris_re.analytics.experience_gam_penalized`) is hardcoded to the Poisson
log-link with an offset — correct for the tensor MI surface, and left untouched
(PLAN Anchor 7: the existing engine stays). The target formula needs binomial
``cloglog``/``logit`` on a proportion response with **prior weights**, and
quasi-Poisson with an estimated dispersion. This module is the family/link
abstraction :mod:`polaris_re.analytics.gam_fit` builds a *new*, general IRLS
around, rather than widening the old module's own hardcoded Poisson recursion.

**Weights are not an offset (PLAN Anchor 5).** A prior weight scales how much a row
counts in the likelihood (``ExposCnt`` for a binomial proportion response); an
offset is a *fixed* addition to the linear predictor (``log(exposure * q_base)``
for the tensor surface's absolute idiom). Both are supported here, orthogonally,
because the target formula uses weights and the existing engine uses an offset.

The IRLS recursion implemented here is the standard generalized-linear-model
working-response/working-weight update (Wood, *Generalized Additive Models: An
Introduction with R*, 2nd ed., §3.1.2) — textbook GLM theory, not ``mgcv``-internal
machinery, so it needs no R-source archaeology the way the ``cr`` basis did
(ADR-194 decision 1). ``mgcv`` fits every family named here through exactly this
recursion (its family objects expose the same ``linkfun``/``linkinv``/``mu.eta``/
``variance`` slots R's own ``stats::binomial``/``stats::poisson`` do), which is what
makes an INDEPENDENT Stage-B comparison of ``eta`` meaningful (PLAN slice 3,
ADR-193) rather than two implementations of the same formula transcribed from one
source.

For each family/link the working weight at coefficient estimate ``eta`` is::

    w_i = prior_weight_i * (dmu/deta)^2 / V(mu_i)

and the working response is::

    z_i = eta_i - offset_i + (y_i - mu_i) / (dmu/deta)_i

which reduces to the Poisson log-link recursion already verified in
``experience_gam_penalized._penalized_irls`` when ``family=poisson_log()`` and
every prior weight is 1 — a property :mod:`tests.test_analytics.test_gam_family`
checks directly, so the generalisation is provably a superset rather than a
rewrite that might have silently changed the already-verified case.
"""

from collections.abc import Callable

import numpy as np

from polaris_re.core.exceptions import PolarisValidationError

type _VectorFn = Callable[[np.ndarray], np.ndarray]
type _DevianceTermsFn = Callable[[np.ndarray, np.ndarray], np.ndarray]

__all__ = [
    "Family",
    "Link",
    "binomial_cloglog",
    "binomial_logit",
    "poisson_log",
    "quasipoisson_log",
    "validate_family_inputs",
]

_CLOGLOG_LOG1M_FLOOR = -700.0
"""Clip on ``log(1 - mu)`` before exponentiating back, matching the ``[-700, 700]``
guard the existing Poisson recursion already uses on ``exp`` arguments — the
double-precision underflow floor, not a tuned constant."""


class Link:
    """A GLM link function: ``eta = linkfun(mu)``, ``mu = linkinv(eta)``.

    Args:
        name: matches ``mgcv``'s own link name (``"log"``, ``"logit"``,
            ``"cloglog"``), so a case built against this module reads the same in
            the R harness that fits the mirrored ``mgcv`` family/link call.
        linkinv: ``eta -> mu``, vectorized.
        mu_eta: ``eta -> dmu/deta``, vectorized. The IRLS working weight and
            working response are both stated in terms of this derivative rather
            than the link's own derivative (``deta/dmu``), which is the
            numerically stable direction the recursion actually uses.
        d2mu_deta2: ``eta -> d^2 mu / d eta^2``, vectorized. Needed only for
            Wood (2011) Section 3.2's OBSERVED-Hessian weight
            (:meth:`Family.observed_information_weight`, PLAN slice 5c
            Defect B) — not used by the IRLS recursion itself, which only
            ever needs the first derivative. Stated in ``eta``, the same
            variable :meth:`mu_eta` is stated in, rather than in ``mu``,
            because it is always evaluated at an ``eta`` already on hand and
              chain-ruling through ``mu`` a second time would reintroduce the
            numerical-stability problem :meth:`mu_eta` was written to avoid.
    """

    def __init__(
        self, name: str, linkinv: _VectorFn, mu_eta: _VectorFn, d2mu_deta2: _VectorFn
    ) -> None:
        self.name = name
        self._linkinv = linkinv
        self._mu_eta = mu_eta
        self._d2mu_deta2 = d2mu_deta2

    def linkinv(self, eta: np.ndarray) -> np.ndarray:
        return self._linkinv(eta)

    def mu_eta(self, eta: np.ndarray) -> np.ndarray:
        return self._mu_eta(eta)

    def d2mu_deta2(self, eta: np.ndarray) -> np.ndarray:
        return self._d2mu_deta2(eta)


class Family:
    """An exponential-family distribution paired with a :class:`Link`.

    Args:
        name: matches ``mgcv``'s own family name (``"poisson"``, ``"binomial"``,
            ``"quasipoisson"``).
        link: the paired :class:`Link`.
        variance: ``mu -> V(mu)``, the mean-variance relationship (Poisson:
            ``mu``; binomial: ``mu * (1 - mu)``).
        variance_prime: ``mu -> V'(mu)``, needed only for the OBSERVED-Hessian
            weight (:meth:`observed_information_weight`, Wood (2011) Section 3.2,
            PLAN slice 5c Defect B) — the IRLS recursion and the REML score's
            other terms never need it.
        dispersion_fixed: ``True`` when the family holds the scale at 1 (Poisson,
            binomial); ``False`` when it is estimated from the Pearson residuals
            (quasi-Poisson) — mirrors ``mgcv``'s own ``family$family`` distinction
            between ``"poisson"`` (``m$scale.estimated == FALSE``) and
            ``"quasipoisson"`` (``TRUE``).
        deviance_terms: ``(y, mu) -> per-observation deviance contribution``
            (unsigned, before the ``sign(y - mu)`` that turns it into a residual) —
            used for the IRLS convergence criterion, matching
            ``experience_gam_penalized._penalized_irls``'s own deviance-based stop
            rather than a coefficient-shift criterion (that module's docstring:
            coefficients rattle at round-off in penalty-dominated directions long
            after the deviance has settled).
    """

    def __init__(
        self,
        name: str,
        link: Link,
        variance: _VectorFn,
        variance_prime: _VectorFn,
        *,
        dispersion_fixed: bool,
        deviance_terms: _DevianceTermsFn,
    ) -> None:
        self.name = name
        self.link = link
        self._variance = variance
        self._variance_prime = variance_prime
        self.dispersion_fixed = dispersion_fixed
        self._deviance_terms = deviance_terms

    def variance(self, mu: np.ndarray) -> np.ndarray:
        return self._variance(mu)

    def observed_information_weight(
        self, y: np.ndarray, eta: np.ndarray, weights: np.ndarray
    ) -> np.ndarray:
        """The OBSERVED-Hessian IRLS weight, Wood (2011) Section 3.2 —
        ``w_i^o = alpha_i * w_i^F`` where ``w_i^F`` is the ordinary
        EXPECTED (Fisher) weight this family's IRLS recursion already uses
        and::

            alpha_i = 1 + (y_i - mu_i) * (V'(mu_i)/V(mu_i) + g''(mu_i)/g'(mu_i))

        Wood states ``alpha_i`` in terms of the link's derivatives in
        ``mu`` (``g'``, ``g''``); this evaluates the algebraically
        equivalent form in ``eta`` instead, since chain-ruling
        ``g''(mu)/g'(mu) = -d2mu_deta2(eta) / mu_eta(eta)**2`` needs only
        quantities the fit already has at ``eta`` and avoids re-deriving
        ``mu``-space derivatives that :class:`Link` deliberately does not
        expose (see :meth:`Link.d2mu_deta2`'s docstring).

        For a CANONICAL link, ``alpha_i == 1`` identically — verified
        analytically for both canonical cases this module defines
        (:mod:`tests.test_analytics.test_gam_family`,
        ``TestObservedInformationWeight``): the observed and expected
        Hessians coincide there, which is the textbook reason Fisher scoring
        and Newton's method are the same algorithm for a canonical link.
        Wood flags the NON-canonical case explicitly (Section 3.2): using
        the expected Hessian there "gave worse performance than GCV" — the
        target formula's ``binomial(link="cloglog")`` is exactly that case.
        """
        mu = self.link.linkinv(eta)
        fisher_weight = weights * self.link.mu_eta(eta) ** 2 / self.variance(mu)
        g_double_over_g_prime = -self.link.d2mu_deta2(eta) / self.link.mu_eta(eta) ** 2
        alpha = 1.0 + (y - mu) * (
            self._variance_prime(mu) / self.variance(mu) + g_double_over_g_prime
        )
        return alpha * fisher_weight

    def deviance(self, y: np.ndarray, mu: np.ndarray, weights: np.ndarray) -> float:
        """The weighted deviance ``D = 2 * sum(w_i * d_i(y_i, mu_i))`` — the
        standard definition (matching R's own ``family$dev.resids``, e.g.
        ``stats::poisson()$dev.resids``, which multiplies by ``wt`` before
        summing). ``weights`` is required rather than defaulted, so a caller
        cannot silently reproduce the unweighted bug this signature exists to
        prevent (PR #202 review [P2]: an earlier revision omitted the prior
        weight here while the IRLS working weights correctly included it —
        harmless for convergence monitoring on this slice's cases, since the
        fixed point is set by the weighted normal equations and the criterion
        is a relative one, but wrong as a general deviance and load-bearing
        once slice 4's REML score needs the weighted definition)."""
        return float(2.0 * np.sum(weights * self._deviance_terms(y, mu)))


def _poisson_variance(mu: np.ndarray) -> np.ndarray:
    return np.clip(mu, 1e-300, None)


def _poisson_variance_prime(mu: np.ndarray) -> np.ndarray:
    """``V(mu) = mu``, so ``V'(mu) = 1`` everywhere — needed only for
    :meth:`Family.observed_information_weight` (PLAN slice 5c Defect B)."""
    return np.ones_like(mu)


def _poisson_deviance_terms(y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        log_ratio = np.where(y > 0.0, y * np.log(np.where(y > 0.0, y / mu, 1.0)), 0.0)
    return log_ratio - (y - mu)


def poisson_log() -> Family:
    """Poisson, log link. The tensor MI surface's own family — reproduced here
    (not imported from ``experience_gam_penalized``, which stays untouched per
    Anchor 7) so :func:`polaris_re.analytics.gam_fit.penalized_irls_general` can
    be checked against that module's already-verified ``_penalized_irls`` on the
    ``S=0``, ``weights=1`` case."""
    log_link = Link(
        "log",
        linkinv=lambda eta: np.exp(np.clip(eta, -700.0, 700.0)),
        mu_eta=lambda eta: np.clip(np.exp(np.clip(eta, -700.0, 700.0)), 1e-300, None),
        # d/deta[exp(eta)] = exp(eta) again — the log link's mu_eta and
        # d2mu_deta2 are the identical function (PLAN slice 5c Defect B).
        d2mu_deta2=lambda eta: np.clip(np.exp(np.clip(eta, -700.0, 700.0)), 1e-300, None),
    )
    return Family(
        "poisson",
        log_link,
        _poisson_variance,
        _poisson_variance_prime,
        dispersion_fixed=True,
        deviance_terms=_poisson_deviance_terms,
    )


def quasipoisson_log() -> Family:
    """Poisson mean/variance and log link, but with the dispersion **estimated**
    rather than held at 1 (``mgcv``'s ``quasipoisson()``). The estimating
    equations for ``mu`` are identical to :func:`poisson_log` — dispersion scales
    the variance of the coefficients, not the score equation that determines
    them — so this shares :func:`poisson_log`'s IRLS recursion exactly and differs
    only in :attr:`Family.dispersion_fixed`, which
    :mod:`polaris_re.analytics.gam_fit` reads to decide whether to estimate
    ``phi`` from the Pearson residuals.
    """
    base = poisson_log()
    return Family(
        "quasipoisson",
        base.link,
        base.variance,
        _poisson_variance_prime,
        dispersion_fixed=False,
        deviance_terms=_poisson_deviance_terms,
    )


def _binomial_variance(mu: np.ndarray) -> np.ndarray:
    return np.clip(mu * (1.0 - mu), 1e-300, None)


def _binomial_variance_prime(mu: np.ndarray) -> np.ndarray:
    """``V(mu) = mu*(1-mu)``, so ``V'(mu) = 1 - 2*mu`` — needed only for
    :meth:`Family.observed_information_weight` (PLAN slice 5c Defect B)."""
    return 1.0 - 2.0 * mu


def _binomial_deviance_terms(y: np.ndarray, mu: np.ndarray) -> np.ndarray:
    mu = np.clip(mu, 1e-300, 1.0 - 1e-300)
    with np.errstate(divide="ignore", invalid="ignore"):
        term_1 = np.where(y > 0.0, y * np.log(np.where(y > 0.0, y / mu, 1.0)), 0.0)
        term_0 = np.where(
            y < 1.0,
            (1.0 - y) * np.log(np.where(y < 1.0, (1.0 - y) / (1.0 - mu), 1.0)),
            0.0,
        )
    return term_1 + term_0


def binomial_logit() -> Family:
    """Binomial, logit link — the canonical link, so the log-likelihood is
    concave in the coefficients (Wood §3.1.2), matching the strict-concavity
    argument ADR-189 decision 1 makes for the Poisson log-link case."""

    def _p(eta: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(eta, -700.0, 700.0)))

    logit_link = Link(
        "logit",
        linkinv=_p,
        mu_eta=lambda eta: np.clip(_p(eta) * (1.0 - _p(eta)), 1e-300, None),
        # d/deta[mu(1-mu)] = (1-2mu) * dmu/deta = (1-2mu) * mu(1-mu) — the
        # same mu(1-mu) product mu_eta already computes, times (1-2mu).
        d2mu_deta2=lambda eta: (
            np.clip(_p(eta) * (1.0 - _p(eta)), 1e-300, None) * (1.0 - 2.0 * _p(eta))
        ),
    )
    return Family(
        "binomial",
        logit_link,
        _binomial_variance,
        _binomial_variance_prime,
        dispersion_fixed=True,
        deviance_terms=_binomial_deviance_terms,
    )


def binomial_cloglog() -> Family:
    """Binomial, complementary log-log link: ``eta = log(-log(1 - mu))``.

    **Not the canonical link for the binomial family** — unlike
    :func:`binomial_logit`, concavity of the log-likelihood in the coefficients
    is not guaranteed by the general canonical-link argument, so the "every
    disagreement is our arithmetic" reasoning ADR-189 decision 1 makes does not
    transfer automatically to this link. Marked here rather than assumed
    (CLAUDE.md: mark uncertainty rather than guess); the target formula uses
    this link because it is the standard survival-analysis link for a discrete
    hazard from a continuous force of mortality, not because it is convenient
    to verify.

    ``dmu/deta = exp(eta - exp(eta))`` — apply the chain rule to
    ``mu = 1 - exp(-exp(eta))`` directly rather than going through ``1 - mu``,
    which loses precision as ``mu -> 1``.
    """

    def linkinv(eta: np.ndarray) -> np.ndarray:
        eta = np.clip(eta, -700.0, 700.0)
        return 1.0 - np.exp(-np.exp(eta))

    def mu_eta(eta: np.ndarray) -> np.ndarray:
        eta = np.clip(eta, -700.0, 700.0)
        return np.clip(np.exp(eta - np.exp(eta)), 1e-300, None)

    def d2mu_deta2(eta: np.ndarray) -> np.ndarray:
        """``d/deta[exp(eta - exp(eta))] = exp(eta - exp(eta)) * (1 - exp(eta))``
        — the product rule applied to ``mu_eta`` directly, so this is
        ``mu_eta(eta) * (1 - exp(eta))`` rather than a second derivation
        through ``mu``."""
        eta = np.clip(eta, -700.0, 700.0)
        return mu_eta(eta) * (1.0 - np.exp(eta))

    cloglog_link = Link("cloglog", linkinv=linkinv, mu_eta=mu_eta, d2mu_deta2=d2mu_deta2)
    return Family(
        "binomial",
        cloglog_link,
        _binomial_variance,
        _binomial_variance_prime,
        dispersion_fixed=True,
        deviance_terms=_binomial_deviance_terms,
    )


def validate_family_inputs(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray, offset: np.ndarray
) -> None:
    """Shape/sign checks shared by every caller of a family's IRLS recursion
    (:mod:`polaris_re.analytics.gam_fit`) — one place for the boundary
    validation CLAUDE.md's error-handling section asks for, rather than
    duplicated per fitter."""
    n = x.shape[0]
    for name, arr in (("y", y), ("weights", weights), ("offset", offset)):
        if arr.shape != (n,):
            raise PolarisValidationError(
                f"{name} has shape {arr.shape}, expected ({n},) to match x's {n} rows."
            )
    if np.any(weights < 0.0):
        raise PolarisValidationError("Prior weights must be non-negative.")

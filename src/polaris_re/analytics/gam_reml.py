"""Generalized REML score — mgcv-parity engine, slice 4, part A: the criterion itself.

``docs/PLAN_mgcv_parity_engine.md`` slice 4 is the outer N-dimensional (f)REML
optimiser — "the largest single piece of work in the epic." Before any optimiser
can search over smoothing parameters it needs a criterion that (a) works for the
target formula's actual families (binomial ``logit``/``cloglog``, PLAN §1) and
(b) accepts however many independently-scaled penalty blocks a model has, not
just the tensor MI surface's fixed two. This module builds that criterion —
generalized from ``experience_gam_penalized.reml_score`` (Poisson log-link,
exactly two hardcoded blocks) onto ``gam_fit``'s general IRLS core — and stops
there. **The search over log(lambda) itself is not attempted in this module**;
see ``docs/CONTINUATION_mgcv_parity_engine.md`` for why slice 4 was split this
way and what is left.

**Known-scale families only, and that is the target's own scope, not an
arbitrary cut.** ``experience_gam_penalized.reml_score``'s formula holds the
dispersion at ``gamma`` (Wood's smoothness multiplier, default 1) rather than
treating it as an estimated scale. Generalizing to an ESTIMATED dispersion
(quasi-Poisson) needs a materially different criterion — ``mgcv`` profiles
``phi`` out of the marginal likelihood rather than holding it fixed — that PLAN
slice 3 never had to solve at fixed ``sp`` and this module does not attempt.
The target formula's own family, binomial with a fixed dispersion of 1
(PLAN Anchor 5), never needs it, so the cut does not block slice 4's actual
target. :func:`reml_score_general` raises rather than silently reusing the
known-scale formula against a family it was not derived for.

**ADR-196: the score uses the PENALIZED deviance, not the plain one — derived
from Wood (2011), not guessed.** ADR-196's first measurement generalized
``experience_gam_penalized.reml_score``'s formula verbatim, including its use
of the plain deviance ``D(β̂)``. That disagreed with ``mgcv`` on all three
tested pairwise score differences, tier 1 and tier 3 identical. Wood, S.N.
(2011), *JRSS-B* 73(1), 3-36, "Fast stable restricted maximum likelihood and
marginal likelihood estimation of semiparametric generalized linear models",
§2 p.4, equation (4), names the quantity the criterion actually needs:

    ``Dₚ = D(β̂) + β̂ᵀSβ̂``       (the PENALIZED deviance)
    ``2lᵣ = 2l(β̂) + log|S/φ|₊ - β̂ᵀSβ̂/φ - log|H + S/φ| + Mₚlog(2π)``

i.e. the criterion needs the penalty's quadratic form ``β̂ᵀSβ̂`` ADDED to the
deviance — a term the naive generalization omitted entirely. Adding it closed
the gap to ~1e-12 (float round-trip noise) on every tested point, tier 1 and
tier 3. See ADR-196's resolution section for the full derivation and
measurement, and ``docs/WORK_ORDER_reml_penalized_deviance_production_check.md``
for whether the SAME omission is present in the already-shipped
``experience_gam_penalized.reml_score`` this module was generalized from
(that module is untouched here — PLAN Anchor 7).

**PLAN slice 5c, Defects A and B: two more terms of this SAME formula, found
on the N=4/``ti()``-sharing-a-span structure ADR-208's amendment localised an
``sp``-dependent criterion discrepancy to.**

*Defect A — ``log|S|+``.* The first generalization eigendecomposed the
CALLER-SUMMED ``S = Σⱼ λⱼSⱼ`` and cut its null space at a fixed relative
tolerance of ``1e-10``. When the ``λⱼ`` span many decades that cut misreads
the model's own (``λ``-independent) null space — Wood (2011) §3.1's
"numerical zero leakage" — and the score moves discretely as eigenvalues are
misclassified. :func:`~polaris_re.analytics.gam_reml_appendix_b.logdet_s_plus`
(Appendix B) replaces it: it determines the rank structurally, from the
INDIVIDUAL blocks, which is why this function now takes ``penalty_blocks``
and ``lambdas`` separately rather than one caller-summed ``penalty`` — the
old signature could not express the information Appendix B needs. No tuned
tolerance remains in this path.

*Defect B — the Hessian in ``log|XᵀWX + S|``.* Wood's eq. (4) builds this
term on ``H = -∂²l/∂β∂βᵀ``, the OBSERVED Hessian a Newton-based PIRLS would
produce. The first generalization used the EXPECTED (Fisher) weight instead
— correct for a canonical link, where the two coincide exactly (see
:meth:`~polaris_re.analytics.gam_family.Family.observed_information_weight`'s
own canonical-link tests), but the target family is binomial/**cloglog**,
which is non-canonical. Wood flags exactly this substitution: the expected
Hessian "gave worse performance than GCV when non-canonical links were
used." :meth:`Family.observed_information_weight` supplies the analytic
``αᵢ`` of Wood §3.2 instead.

Both were measured on the fixed-``sp`` diagnostic
(``scripts/gam_fixed_sp_score_probe.R`` / ``gam_fixed_sp_score_compare.py``,
``gam_hessian_weight_probe.py``) before being wired in here — see
``docs/CONFORMANCE_LEDGER.md`` and the slice 5c ADR for the gap-before/after
figures and the term-by-term audit against eq. (4).
"""

import numpy as np

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_reml_appendix_b import appendix_b_transform
from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["reml_score_general"]


def reml_score_general(
    y: np.ndarray,
    x: np.ndarray,
    family: Family,
    coef: np.ndarray,
    penalty_blocks: tuple[np.ndarray, ...],
    lambdas: np.ndarray,
    *,
    offset: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    gamma: float = 1.0,
) -> float:
    """Laplace-approximate REML for a penalized known-scale GLM (lower is better).

    Wood (2011) §2 eq. (4), specialized to known scale (``φ = gamma``, Wood's
    smoothness multiplier — see the ``gamma`` argument below):

        ``V = Dₚ/(2*gamma) + log|XᵀWX + S|/2 - log|S|₊/2 - (p - r)*log(gamma)/2``

    where ``Dₚ = D(β̂) + β̂ᵀSβ̂`` is the PENALIZED deviance — plain deviance plus
    the penalty's quadratic form at the supplied coefficients. **This differs
    from ``experience_gam_penalized.reml_score``'s formula**, which uses the
    plain deviance ``D(β̂)`` alone: that omission is ADR-196's finding, derived
    from and cited to Wood (2011) in this module's docstring, not present in
    the (untouched, PLAN Anchor 7) module this one was generalized from. See
    :func:`~polaris_re.analytics.gam_reml_conformance` for the measurement
    that found it and confirmed the fix.

    ``W`` in ``log|XᵀWX + S|`` is the OBSERVED-Hessian weight (PLAN slice 5c
    Defect B, :meth:`Family.observed_information_weight`) — Wood's own eq.
    (4), not the expected/Fisher weight the IRLS recursion converges under.
    ``D`` in ``Dₚ`` is the ordinary deviance from ``family``
    (:mod:`gam_family`) rather than hardcoded to the Poisson log-link.

    ``S = Σⱼ λⱼ · penalty_blocks[j]`` is assembled here from the INDIVIDUAL
    blocks rather than accepted pre-summed, because ``log|S|+`` (PLAN slice
    5c Defect A) needs the individual blocks to determine ``S``'s rank
    structurally (:func:`~polaris_re.analytics.gam_reml_appendix_b.logdet_s_plus`)
    — a single combined matrix cannot be un-summed back into them. Evaluated
    at the supplied ``coef``, so callers own convergence: this function does
    not fit anything.

    Args:
        y: response, ``(n,)`` — counts, or a proportion for binomial.
        x: design matrix, ``(n, p)``.
        family: the distribution/link pair (:mod:`gam_family`). Must have
            ``dispersion_fixed=True`` — see the module docstring.
        coef: the converged penalized-IRLS coefficients at this ``S``.
        penalty_blocks: one independently-scaled ``(p, p)`` penalty block per
            smoothing parameter, already padded to the full design width
            (:func:`~polaris_re.analytics.gam_reml_optimize.penalized_fit_and_score`'s
            own convention).
        lambdas: one positive smoothing parameter per block, matching
            ``penalty_blocks`` in order and length.
        offset: fixed addition to the linear predictor, ``(n,)``. Defaults to
            all-zero.
        weights: prior weights, ``(n,)``. Defaults to all-one.
        gamma: Wood's smoothness multiplier — see
            ``experience_gam_penalized.reml_score``'s docstring for the full
            derivation of what it does to the criterion. Same default (1.0,
            a no-op) and same status (adopted from ``mgcv``, unsettled —
            ADR-189 amendment 1).

    Returns:
        The REML score, lower is better.

    Raises:
        PolarisValidationError: if ``family.dispersion_fixed`` is ``False``,
            ``gamma`` is not positive, ``penalty_blocks`` is empty, or
            ``lambdas`` does not have one entry per block. (PR #215 review
            [P2-1]: an earlier revision let ``penalty_blocks[0]``/``zip``
            raise the bare ``IndexError``/``ValueError`` this validation now
            pre-empts, before ever reaching
            :func:`~polaris_re.analytics.gam_reml_appendix_b.appendix_b_transform`'s
            own — correct, but unreachable for these two cases.)
    """
    if not family.dispersion_fixed:
        raise PolarisValidationError(
            f"reml_score_general: family {family.name!r} estimates its own "
            "dispersion (dispersion_fixed=False). The known-scale REML formula "
            "this function implements does not apply to it — see the module "
            "docstring for why quasi-Poisson's REML criterion is out of scope."
        )
    if gamma <= 0.0:
        raise PolarisValidationError(f"gamma must be positive, got {gamma}.")
    if not penalty_blocks:
        raise PolarisValidationError("reml_score_general: penalty_blocks must be non-empty.")
    if len(lambdas) != len(penalty_blocks):
        raise PolarisValidationError(
            f"reml_score_general: lambdas has {len(lambdas)} entries, but "
            f"{len(penalty_blocks)} penalty_blocks were supplied — one lambda "
            "per block."
        )

    n = y.shape[0]
    offset = np.zeros(n, dtype=np.float64) if offset is None else np.asarray(offset)
    weights = np.ones(n, dtype=np.float64) if weights is None else np.asarray(weights)
    lambdas = np.asarray(lambdas, dtype=np.float64)

    penalty = np.zeros_like(penalty_blocks[0], dtype=np.float64)
    for lam, block in zip(lambdas, penalty_blocks, strict=True):
        penalty = penalty + lam * block

    eta = offset + x @ coef
    mu = family.link.linkinv(eta)
    deviance = family.deviance(y, mu, weights)
    # Wood (2011) §2 eq. (4): Dp = D(beta_hat) + beta_hat^T S beta_hat — the
    # PENALIZED deviance. ADR-196: this term was missing entirely in the first
    # generalization (and, per experience_gam_penalized.reml_score's own
    # formula, is absent there too); adding it is the derived fix, not a
    # tuned constant — see the module docstring's citation.
    penalized_deviance = deviance + float(coef @ penalty @ coef)

    # Defect B: the OBSERVED Hessian, not the expected/Fisher one — see the
    # module docstring. Identical to the Fisher weight for a canonical link
    # (logit, log), so this is a strict generalization: it changes nothing
    # for a canonical-link caller and fixes the non-canonical (cloglog) case.
    observed_weights = family.observed_information_weight(y, eta, weights)
    _, logdet_h = np.linalg.slogdet(x.T @ (observed_weights[:, None] * x) + penalty)

    # Defect A: Appendix B's structural rank and log|S|+, not a fixed
    # relative-tolerance eigenvalue cut on the summed S — see the module
    # docstring. One call: `rank` (below, the `r` in `(p - r) * log(gamma)`)
    # and `logdet_s_plus` must come from the SAME null-space decision, or
    # the two terms could disagree about what "positive" means.
    appendix_b = appendix_b_transform(penalty_blocks, lambdas)
    logdet_s = appendix_b.logdet_s_plus
    rank_s = appendix_b.rank

    # No `gamma == 1.0` short-circuit, matching `experience_gam_penalized.reml_score`
    # (PR #190 review [P2]): `np.log(1.0)` is exactly `0.0`, so the criterion is
    # bit-identical at the default without a float-equality guard.
    scale = float(x.shape[1] - rank_s) * float(np.log(gamma))
    return float(
        0.5 * penalized_deviance / gamma + 0.5 * float(logdet_h) - 0.5 * logdet_s - 0.5 * scale
    )

"""``mgcv::bgam.fitd``'s performance iteration, ported — real-data readiness epic Slice R3,
Stage B (``docs/PLAN_gam_real_data_readiness.md`` §4, ADR-260 amendments 2-4).

**Claim sentence (ADR-193), written before the code.** *"Polaris
(:func:`bam_fitd`, a port of the iteration read from the ``mgcv`` **1.9.1**
``bgam.fitd`` / ``Sl.fitChol`` source, constants cited below) runs the performance
iteration — at each PIRLS step one Newton step on ``log(sp)`` of the fixed-weight Gaussian
REML criterion, step-halving on the penalised deviance, stop on the relative change in
penalised deviance — from a design ``X``, penalty blocks ``S``, response, family and
offset; ``mgcv`` (the pinned digest) runs it as ``bam(method="fREML", discrete=TRUE)``;
compared per iteration on ``log(sp)``, the linear predictor ``eta`` and the iteration
count, and at the end on ``edf_total`` and the ``Vp`` standard errors."*

**Provenance, per column.** The iteration quantities (``log(sp)``, ``eta``, iteration
count, ``edf``, ``se``) are INDEPENDENT *given the same design*: :func:`bam_fitd` takes
``X`` and ``S`` and nothing from ``mgcv``'s fit (its signature has no ``mgcv`` payload),
and ``mgcv`` is run on the formula. **But when the probe hands Polaris ``mgcv``'s own
``X`` and ``S``** (``scripts/bam_fitd_probe.R`` exports them through ``Xbd``), the design
is an ECHO and is labelled as such: that comparison isolates the *algorithm* from the
*design*. Whether Polaris can build the design ``bam`` builds is a separate comparison
(see "Finding" below), not this module's claim.

**Finding that shapes this module (tier 1 HYPOTHESIS until the tier-3 probe reads it).**
Fed ``gam``'s design, the same iteration lands 2.8e-3 from ``bam`` in ``eta`` on a
replicated Poisson cell where exact REML (``gam``) is 2.4e-3 away, so the *algorithm port
alone does not close the gap*. Fed ``bam``'s own ``X`` and ``S``, it lands 1.6e-6 away and
reproduces all 13 iterations' ``log(sp)`` to ~1e-5. The remainder is the **design**:
``bam(discrete=TRUE)`` builds its smooths on a padded frame (``discrete.mf`` pads each
variable's unique values with a seeded ``sample`` up to ``max(nr)`` rows — 1000 whenever an
offset or other parametric column has more unique values than any covariate), so the
sum-to-zero constraint, the penalty scale ``norm(X, "I")^2`` and the ``ti`` margin order all
differ from ``gam``'s. See ADR-260 amendment 4.

**Constants are ported, not tuned** (ADR-260 amendment 2, rule 3), each from
``gam.control()`` / ``bgam.fitd`` / ``Sl.fitChol``: ``epsilon = 1e-7``, ``maxit = 200``,
the step-halving cap ``30`` with ``stepr = 2``, the sp-step cap ``4`` (max absolute
``log(sp)`` step), the ``1e-7`` descent test on halving ``Nstep``, the eigenvalue floor
``max|eig| * sqrt(eps)`` on the Hessian, the convergence tolerance
``|reml| * sqrt(eps)`` below which a coordinate is not stepped, and ``0.1`` in the
deviance-change denominator.

**Supported subset (refused by name otherwise).** Poisson/log and binomial families (the
fixed-scale branch, ``scale > 0``); ``gamma = 1``; no ``rho`` (AR1), no linear map ``L``
on ``sp``. Gaussian with free scale, quasi and extended families are different builds.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.linalg import LinAlgError as SciPyLinAlgError
from scipy.linalg import cho_factor, cho_solve

from polaris_re.analytics.gam_family import Family
from polaris_re.analytics.gam_initial_sp import initial_log10_lambda_from_xx_diag
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "BamFitdIteration",
    "BamFitdResult",
    "PenaltyBlockStructure",
    "bam_fitd",
    "penalty_block_structure",
]

MAXIT = 200
"""``gam.control()$maxit``."""
EPSILON = 1.0e-7
"""``gam.control()$epsilon`` — the relative penalised-deviance change that stops ``bgam.fitd``."""
_HALVING_CAP = 30
"""``bgam.fitd``'s ``kk < 30``."""
_STEPR = 2.0
"""``bgam.fitd``'s ``stepr``."""
_SP_STEP_CAP = 4.0
"""``Sl.fitChol``'s cap on the largest absolute ``log(sp)`` step."""
_DESCENT_TOL = 1.0e-7
"""``bgam.fitd``'s ``sum(grad * Nstep) > dev * 1e-7`` test."""
_DEV_FLOOR = 0.1
"""The ``0.1`` in ``abs(dev - devold) / (0.1 + abs(dev))``."""
_EPS = float(np.finfo(np.float64).eps)
_RANK_RTOL = 1.0e-10
"""Relative eigenvalue threshold fixing the rank of a penalty block's sum (Polaris's own
choice: ``Sl.setup`` fixes the rank once from the block; the eigenvalues of a genuine
penalty are separated from round-off by many orders of magnitude)."""


@dataclass(frozen=True)
class PenaltyBlockStructure:
    """Which penalties share columns (``Sl.setup``'s blocks) and each penalty's support.

    ``groups[b]`` lists the indices (into the penalty list) of the penalties of block
    ``b``; ``supports[j]`` is the sorted column indices where penalty ``j`` is non-zero;
    ``ranks[b]`` is the rank of the block's unit-normalised sum."""

    groups: tuple[tuple[int, ...], ...]
    supports: tuple[np.ndarray, ...]
    ranks: tuple[int, ...]


def penalty_block_structure(penalty_blocks: tuple[np.ndarray, ...]) -> PenaltyBlockStructure:
    """Group penalties that overlap in columns (union-find on their supports) and fix each
    group's rank from the sum of its unit-normalised members."""
    n = len(penalty_blocks)
    supports: list[np.ndarray] = []
    for j, s in enumerate(penalty_blocks):
        cols = np.flatnonzero(np.any(s != 0.0, axis=0))
        if cols.size == 0:
            raise PolarisValidationError(f"penalty_block_structure: penalty block {j} is zero.")
        supports.append(cols)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    owner: dict[int, int] = {}
    for j, cols in enumerate(supports):
        for c in cols.tolist():
            if c in owner:
                parent[find(j)] = find(owner[c])
            else:
                owner[c] = j
    by_root: dict[int, list[int]] = {}
    for j in range(n):
        by_root.setdefault(find(j), []).append(j)
    groups = tuple(tuple(v) for v in sorted(by_root.values(), key=lambda v: v[0]))
    ranks: list[int] = []
    for g in groups:
        cols = np.unique(np.concatenate([supports[j] for j in g]))
        total = np.zeros((cols.size, cols.size), dtype=np.float64)
        for j in g:
            sub = penalty_blocks[j][np.ix_(cols, cols)]
            total += sub / np.linalg.norm(sub)
        ev = np.linalg.eigvalsh(total)
        ranks.append(int(np.sum(ev > ev.max() * _RANK_RTOL)))
    return PenaltyBlockStructure(groups=groups, supports=tuple(supports), ranks=tuple(ranks))


@dataclass(frozen=True)
class BamFitdIteration:
    """One performance-iteration step, as ``bam(maxit = k)`` would report it after step k."""

    iteration: int
    log_sp: np.ndarray
    """``log(sp)`` that ``Sl.fitChol`` was evaluated at in this iteration."""
    coef: np.ndarray
    penalised_deviance: float
    """``dev + bSb`` entering the convergence test (iteration 1: the deviance alone)."""
    n_halvings: int


@dataclass(frozen=True)
class BamFitdResult:
    """The converged (or ``maxit``) ``bgam.fitd`` fit."""

    coef: np.ndarray
    eta: np.ndarray
    mu: np.ndarray
    log_sp: np.ndarray
    n_iter: int
    converged: bool
    deviance: float
    edf: np.ndarray
    """``diag(PP %*% X'WX)``, per coefficient (``object$edf``)."""
    vp: np.ndarray
    """``PP * scale`` (scale 1 for the supported families)."""
    trace: tuple[BamFitdIteration, ...] = field(default_factory=tuple)


def _initial_mu(family: Family, y: np.ndarray, weights: np.ndarray) -> np.ndarray:
    if family.name == "poisson":
        return np.asarray(y + 0.1, dtype=np.float64)
    if family.name == "binomial":
        return np.asarray((weights * y + 0.5) / (weights + 1.0), dtype=np.float64)
    raise PolarisValidationError(
        f"bam_fitd: family {family.name!r} is not in the supported subset (poisson, binomial "
        "with fixed scale); gaussian with free scale, quasi and extended families are "
        "different builds (ADR-260 amendment 2)."
    )


def _linkfun(family: Family, mu: np.ndarray) -> np.ndarray:
    name = family.link.name
    if name == "log":
        return np.asarray(np.log(mu), dtype=np.float64)
    if name == "logit":
        return np.asarray(np.log(mu / (1.0 - mu)), dtype=np.float64)
    if name == "cloglog":
        return np.asarray(np.log(-np.log1p(-mu)), dtype=np.float64)
    raise PolarisValidationError(f"bam_fitd: no linkfun for link {name!r}.")


def _weighted_cross_products(
    x: np.ndarray, w: np.ndarray, wz: np.ndarray, block_rows: int = 65_536
) -> tuple[np.ndarray, np.ndarray]:
    """``X'WX`` and ``X'(w z)`` accumulated over row blocks (no ``n x p`` temporary)."""
    n, p = x.shape
    xx = np.zeros((p, p), dtype=np.float64)
    xy = np.zeros(p, dtype=np.float64)
    for start in range(0, n, block_rows):
        xb = x[start : start + block_rows]
        xx += (xb * w[start : start + block_rows, None]).T @ xb
        xy += xb.T @ wz[start : start + block_rows]
    return xx, xy


@dataclass
class _FitChol:
    beta: np.ndarray
    grad: np.ndarray
    step: np.ndarray
    pp: np.ndarray
    ldet_s: float
    ldet_xxs: float


def _fit_chol(
    xx: np.ndarray,
    f: np.ndarray,
    penalty_blocks: tuple[np.ndarray, ...],
    structure: PenaltyBlockStructure,
    rho: np.ndarray,
    tol: float,
) -> _FitChol:
    """``Sl.fitChol`` for a fixed scale: ``beta``, the gradient and exact Hessian of the
    fixed-weight working-model REML in ``rho = log(sp)``, and the capped Newton step."""
    lam = np.exp(rho)
    p = xx.shape[0]
    n_sp = len(penalty_blocks)
    s_lam = np.zeros((p, p), dtype=np.float64)
    for lj, s in zip(lam, penalty_blocks, strict=True):
        s_lam += lj * s
    a = xx + s_lam
    d = np.diag(a).copy()
    d = np.where(d > 0.0, np.sqrt(np.where(d > 0.0, d, 1.0)), 1.0)
    try:
        chol = cho_factor((a / d[:, None]) / d[None, :], lower=False)
    except (SciPyLinAlgError, ValueError) as exc:
        raise PolarisComputationError(
            "bam_fitd: X'WX + S_lambda is not positive definite — the design is not identified "
            "under this penalty (bgam.fitd would pivot; the supported subset does not)."
        ) from exc
    beta = cho_solve(chol, f / d) / d
    pp = cho_solve(chol, np.eye(p)) / d[:, None] / d[None, :]

    # ldetS derivatives, block by block (pseudo-determinant on the fixed-rank range)
    ldet1 = np.zeros(n_sp)
    ldet2 = np.zeros((n_sp, n_sp))
    ldet_s = 0.0
    for g, rk in zip(structure.groups, structure.ranks, strict=True):
        cols = np.unique(np.concatenate([structure.supports[j] for j in g]))
        sub = [penalty_blocks[j][np.ix_(cols, cols)] for j in g]
        s_g = sum(lam[j] * sj for j, sj in zip(g, sub, strict=True))
        ev, u = np.linalg.eigh(s_g)
        keep = np.argsort(ev)[::-1][:rk]
        ur, evr = u[:, keep], ev[keep]
        ldet_s += float(np.sum(np.log(evr)))
        s_plus = (ur / evr) @ ur.T
        sps = [s_plus @ sj for sj in sub]
        for a_i, ja in enumerate(g):
            ldet1[ja] = lam[ja] * np.trace(sps[a_i])
            for c_i, jc in enumerate(g):
                ldet2[ja, jc] = (ldet1[ja] if a_i == c_i else 0.0) - lam[ja] * lam[jc] * float(
                    np.sum(sps[a_i] * sps[c_i].T)
                )

    # log|X'WX + S| and (rss + bSb) derivatives, restricted to each penalty's support
    ps_cols: list[np.ndarray] = []  # P S_j restricted to the support columns, (p x m_j)
    u_vec: list[np.ndarray] = []  # S_j beta, padded to p
    s_sub: list[np.ndarray] = []
    for j, s in enumerate(penalty_blocks):
        cols = structure.supports[j]
        sj = s[np.ix_(cols, cols)]
        s_sub.append(sj)
        ps_cols.append(pp[:, cols] @ sj)
        uj = np.zeros(p, dtype=np.float64)
        uj[cols] = sj @ beta[cols]
        u_vec.append(uj)
    d1 = np.zeros(n_sp)
    d2 = np.zeros((n_sp, n_sp))
    r1 = np.zeros(n_sp)
    r2 = np.zeros((n_sp, n_sp))
    pu = [pp @ uj for uj in u_vec]
    for j in range(n_sp):
        cj = structure.supports[j]
        d1[j] = lam[j] * float(np.trace(ps_cols[j][cj, :]))
        bsb = float(beta @ u_vec[j])
        r1[j] = lam[j] * bsb
        for k in range(n_sp):
            ck = structure.supports[k]
            tr_jk = float(np.sum(ps_cols[j][ck, :] * ps_cols[k][cj, :].T))
            d2[j, k] = (d1[j] if j == k else 0.0) - lam[j] * lam[k] * tr_jk
            r2[j, k] = (r1[j] if j == k else 0.0) - 2.0 * lam[j] * lam[k] * float(u_vec[j] @ pu[k])
    grad = (d1 - ldet1 + r1) / 2.0
    hess = (d2 - ldet2 + r2) / 2.0

    unconv = (np.abs(grad) > tol) | (np.abs(np.diag(hess)) > tol)
    step = np.zeros(n_sp)
    if n_sp > 0 and bool(unconv.any()):
        h = hess[np.ix_(unconv, unconv)]
        ev, vec = np.linalg.eigh(h)
        ev = np.abs(ev)
        floor = ev.max() * np.sqrt(_EPS)
        ev = np.where(ev < floor, floor, ev)
        step[unconv] = -vec @ ((vec.T @ grad[unconv]) / ev)
        ms = float(np.max(np.abs(step)))
        if ms > _SP_STEP_CAP:
            step = _SP_STEP_CAP * step / ms
    ldet_xxs = 2.0 * float(np.sum(np.log(np.diag(chol[0])) + np.log(d)))
    return _FitChol(beta=beta, grad=grad, step=step, pp=pp, ldet_s=ldet_s, ldet_xxs=ldet_xxs)


def bam_fitd(
    x: np.ndarray,
    penalty_blocks: tuple[np.ndarray, ...],
    y: np.ndarray,
    family: Family,
    *,
    offset: np.ndarray | None = None,
    prior_weights: np.ndarray | None = None,
    maxit: int = MAXIT,
    epsilon: float = EPSILON,
    structure: PenaltyBlockStructure | None = None,
) -> BamFitdResult:
    """Run ``mgcv:::bgam.fitd``'s performance iteration on the supplied design.

    Args:
        x: ``(n, p)`` design (intercept and parametric columns included).
        penalty_blocks: one ``(p, p)`` matrix per smoothing parameter, zero outside its
            term's columns (:class:`~polaris_re.analytics.gam_model.ModelDesign` layout).
        y: response (counts for Poisson; proportion for binomial with ``prior_weights``
            the trial counts).
        family: Poisson or binomial (fixed scale).
        offset: linear-predictor offset (default zero).
        prior_weights: prior weights (default one).
        maxit, epsilon: ``gam.control()`` defaults; exposed only so the iteration trace
            can be compared with ``bam(control = gam.control(maxit = k))``.
        structure: precomputed :func:`penalty_block_structure` (computed if omitted).

    Raises:
        PolarisValidationError: an unsupported family/link or malformed input.
        PolarisComputationError: ``X'WX + S`` not positive definite, non-finite deviance
            or coefficients (``bgam.fitd`` stops in the same places).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n, p = x.shape
    off = np.zeros(n) if offset is None else np.asarray(offset, dtype=np.float64)
    wt = np.ones(n) if prior_weights is None else np.asarray(prior_weights, dtype=np.float64)
    if not family.dispersion_fixed:
        raise PolarisValidationError(
            f"bam_fitd: family {family.name!r} estimates its scale; the scale <= 0 branch adds "
            "log(phi) to the sp vector and is a different build (ADR-260 amendment 2)."
        )
    if len(penalty_blocks) == 0:
        raise PolarisValidationError("bam_fitd: no penalty blocks — nothing for bam to select.")
    st = structure if structure is not None else penalty_block_structure(penalty_blocks)
    n_sp = len(penalty_blocks)

    mu = family.link.linkinv(_linkfun(family, _initial_mu(family, y, wt)))
    eta = _linkfun(family, _initial_mu(family, y, wt))
    dev = family.deviance(y, mu, wt)
    coef = np.zeros(p)
    coef0 = eta0 = mu0 = b0 = None
    nstep = np.zeros(n_sp)
    lsp0 = np.zeros(n_sp)
    lsp = np.zeros(n_sp)
    pen_dev = dev  # `reml <- dev` at iteration 1 is the tolerance scale
    reml = dev
    trace: list[BamFitdIteration] = []
    prop: _FitChol | None = None
    converged = False
    xx = np.zeros((p, p))
    n_iter = 0

    def s_lambda(log_sp: np.ndarray) -> np.ndarray:
        out = np.zeros((p, p))
        for lj, s in zip(np.exp(log_sp), penalty_blocks, strict=True):
            out += lj * s
        return out

    for it in range(1, maxit + 1):
        n_iter = it
        devold = pen_dev
        n_halv = 0
        if it > 1:
            eta = x @ coef + off
            slam = s_lambda(lsp)
            beta_cur = coef.copy()
            if it > 2:
                bsb0 = float(b0 @ slam @ b0)
                dev0 = family.deviance(y, mu0, wt)
        kk = 1
        while True:
            mu = family.link.linkinv(eta)
            dev = family.deviance(y, mu, wt)
            if it > 2:
                bsb = float(beta_cur @ slam @ beta_cur)
                if ((not np.isfinite(dev)) or dev0 + bsb0 < dev + bsb) and kk < _HALVING_CAP:
                    istepr = 1.0 - 1.0 / _STEPR
                    coef = coef0 * istepr + coef / _STEPR
                    eta = eta0 * istepr + eta / _STEPR
                    beta_cur = b0 * istepr + beta_cur / _STEPR
                    kk += 1
                    n_halv += 1
                    continue
            break
        if it > 1:
            coef0, eta0, mu0, b0 = coef.copy(), eta.copy(), mu.copy(), beta_cur.copy()
            pen_dev = dev + float(beta_cur @ slam @ beta_cur)
        else:
            pen_dev = dev
            reml = dev
        mu_eta = family.link.mu_eta(eta)
        good = mu_eta != 0.0
        mu_eta = np.where(good, mu_eta, 0.1)
        z = (eta - off) + (y - mu) / mu_eta
        w = (wt * mu_eta**2) / family.variance(mu)
        xx, f = _weighted_cross_products(x, w, w * z)
        if not np.isfinite(pen_dev):
            raise PolarisComputationError("bam_fitd: non-finite deviance.")
        if it > 2 and abs(pen_dev - devold) / (_DEV_FLOOR + abs(pen_dev)) < epsilon:
            converged = True
            break
        if it == 1:
            lsp0 = np.log(10.0) * initial_log10_lambda_from_xx_diag(
                np.diag(xx).copy(), penalty_blocks
            )
        while True:
            lsp = lsp0 + nstep
            prop = _fit_chol(xx, f, penalty_blocks, st, lsp, tol=abs(reml) * np.sqrt(_EPS))
            if float(np.max(nstep)) == 0.0:
                nstep, lsp0 = prop.step, lsp
                break
            if float(np.sum(prop.grad * nstep)) > pen_dev * _DESCENT_TOL:
                nstep = nstep / 2.0
            else:
                nstep, lsp0 = prop.step, lsp
                break
        coef = prop.beta.copy()
        if not np.all(np.isfinite(coef)):
            raise PolarisComputationError(f"bam_fitd: non-finite coefficients at iteration {it}.")
        reml = (pen_dev - prop.ldet_s + prop.ldet_xxs) / 2.0
        trace.append(
            BamFitdIteration(
                iteration=it,
                log_sp=lsp.copy(),
                coef=coef.copy(),
                penalised_deviance=float(pen_dev),
                n_halvings=n_halv,
            )
        )
    if prop is None:
        raise PolarisComputationError("bam_fitd: converged before any smoothing step.")
    eta_out = x @ coef + off
    f_mat = prop.pp @ xx
    return BamFitdResult(
        coef=coef,
        eta=eta_out,
        mu=family.link.linkinv(eta_out),
        log_sp=lsp,
        n_iter=n_iter,
        converged=converged,
        deviance=float(dev),
        edf=np.diag(f_mat).copy(),
        vp=prop.pp.copy(),
        trace=tuple(trace),
    )

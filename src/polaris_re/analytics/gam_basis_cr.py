"""Wood's cubic regression spline basis (mgcv-parity engine, slice 2).

``docs/PLAN_mgcv_parity_engine.md`` slice 2, the epic's first Stage-A **parity**
slice (ADR-193): a Python ``cr`` basis built from a knot vector and Wood's basis /
penalty definition, independent of any ``mgcv`` output — the referent
:func:`~polaris_re.analytics.gam_stage_a.extract_smooth_terms` (slice 1b) packages
is ``mgcv``'s ``smoothCon(..., absorb.cons=TRUE)``.

**Parity claim (per ``docs/VERIFICATION_STANDARD.md``, written before the code):**
``polaris_re``'s new ``cr`` basis computes ``design_X`` and ``penalty_S`` from the
knot vector and Wood's basis/penalty definition; ``mgcv`` computes them via
``smoothCon(s(x, bs="cr", k=k), absorb.cons=TRUE)``; compared on ``design_X``,
``penalty_S``, ``rank`` and (for default-placed knots) ``knots`` itself.

Every formula below was pinned by reading ``mgcv``'s own R source
(``mgcv:::smooth.construct.cr.smooth.spec``, ``mgcv::smoothCon``) rather than
guessed, and then verified numerically against local (tier-1) R output before
being written here — CLAUDE.md's "do not guess at a penalty derivation."

Construction, in order
-----------------------
1. **Knots.** Supplied verbatim when given (Anchor 4 — never derived when
   supplied). When not supplied, ``mgcv``'s own default:
   ``quantile(unique(x), seq(0, 1, length = k))`` — R's type-7 quantile (linear
   interpolation of order statistics) over the *unique* data values, reproduced
   here with ``numpy.quantile(..., method="linear")``. Read directly out of
   ``smooth.construct.cr.smooth.spec``, not inferred from behaviour.

2. **The unconstrained natural cubic spline basis and penalty** (Wood, *Generalized
   Additive Models*, 2nd ed., §5.3.1). Given knots ``x*_1 < ... < x*_k`` with gaps
   ``h_j = x*_{j+1} - x*_j``, the natural cubic spline through knot values ``f`` has
   second derivatives at the interior knots ``δ = F f`` where ``F = B⁻¹D``: ``D`` is
   ``(k-2, k)`` and ``B`` is ``(k-2, k-2)`` tridiagonal,

   ``D[i,i] = 1/h_i``, ``D[i,i+1] = -1/h_i - 1/h_{i+1}``, ``D[i,i+2] = 1/h_{i+1}``

   ``B[i,i] = (h_i + h_{i+1})/3``, ``B[i,i+1] = B[i+1,i] = h_{i+1}/6``

   for interior index ``i``. The natural boundary condition sets ``δ_1 = δ_k = 0``,
   so ``F`` is padded with zero rows at the two ends to act on the full
   ``k``-vector. A basis row at ``x`` in interval ``[x*_j, x*_{j+1}]`` is
   ``a_j(x)·e_j + a_{j+1}(x)·e_{j+1} + c_j(x)·F*_j + c_{j+1}(x)·F*_{j+1}`` (the
   standard cubic-Hermite-with-curvature form; see :func:`_hermite_weights`), and
   the penalty on the full ``k``-vector is ``S = Fᵀ D`` (symmetric because
   ``BF = D``, so ``FᵀBF = FᵀD``).

3. **Penalty rescaling.** ``smoothCon``'s *own* ``scale.penalty`` argument
   (default ``TRUE``) — a different setting from this repo's existing
   ``gam.control(scalePenalty=...)`` used on the ``raw``/``paraPen`` path
   (``experience_mgcv_conformance.py``); the two are unrelated despite the
   similar name. Measured directly against ``smoothCon()`` output: without it the
   penalty is a constant multiple too large (ratio pinned per case, not a
   tolerance-bending "close enough"). The rescaling divides ``S`` by
   ``norm_1(S) / norm_inf(X)²`` — R's ``norm(S)`` (one-norm, i.e. the largest
   absolute column sum) over R's ``norm(X, type="I")²`` (infinity-norm, i.e. the
   largest absolute row sum, squared). :func:`_r_norm_one` / :func:`_r_norm_inf`
   name the convention because NumPy has no built-in for either.

4. **Identifiability constraint.** ``mgcv``'s default for an unconstrained smooth
   with no ``by`` variable and no factor structure (read out of ``smoothCon``,
   not guessed): the constraint row is ``C = colMeans(X)`` (a mean, not the sum —
   confirmed against source), absorbed via the null space of ``C`` computed
   through a **full QR decomposition of ``Cᵀ``**: ``Z`` is every column of ``Q``
   after the first. Measured to confirm ``numpy.linalg.qr(..., mode="complete")``
   reproduces R's ``qr()``/``qr.Q()`` bit-for-bit on a single-column input (both
   use the same cancellation-avoiding Householder sign convention), which is what
   makes ``Z`` — and therefore the constrained ``X`` and ``S`` — comparable
   element-wise rather than only up to an arbitrary rotation of the null space.

The ``ti`` tensor interaction, two ``cr`` margins (slice 5, ``ti(AttdAge, PolYear)``)
-------------------------------------------------------------------------------------
:func:`ti_basis` builds a two-margin ``ti(x1, x2, k=(k1,k2), bs="cr")`` term:
tensor interaction with the marginal main effects excluded, so it can sit beside
``s(x1)`` and ``s(x2)`` main-effect terms in one model without confounding them.
Every step below was *measured*, not read off documentation — instrumenting
``mgcv:::smooth.construct.tensor.smooth.spec`` directly (assigning its internal
locals to the global environment mid-execution) and comparing each intermediate
against a hand-replica, the same discipline the ``cr`` construction above used,
because ``ti()``'s own R source (``mgcv::ti`` → ``mgcv::te`` →
``smooth.construct.tensor.smooth.spec``) does not itself state the exact
normalization order in a form that can be transcribed without running it.

1. **Each margin is its own constrained ``cr`` smooth**, independently: knots per
   Anchor 4 (supplied verbatim, or :func:`cr_default_knots` on that margin's own
   covariate), :func:`cr_basis` for the unconstrained design/penalty, then
   :func:`sum_to_zero_null_space` / :func:`absorb_sum_to_zero_constraint` — the
   *same* per-margin construction :func:`~polaris_re.analytics.gam_stage_a.build_python_cr_term`
   already uses for a standalone ``s(x)`` term, because ``ti()``'s ``mc[i]`` flag
   defaults ``TRUE`` for every margin (``mgcv::ti`` sets ``inter=TRUE``, and
   ``smooth.construct.tensor.smooth.spec`` reads ``object$mc <- rep(TRUE, m)``
   whenever ``inter`` and no explicit ``mc=`` override — the target formula
   supplies none).

2. **No further reparameterization runs for ``cr`` margins.** ``mgcv::ti``'s
   ``np=TRUE`` default would ordinarily re-express each 1-D margin via an
   SVD-based change of basis (evaluating the constrained margin at
   ``ncol(margin$X)`` equally spaced points and inverting), but
   ``smooth.construct.cr.smooth.spec`` sets ``object$noterp <- TRUE`` on every
   ``cr`` margin, and the tensor constructor's own reparam loop is gated on
   ``is.null(object$margin[[i]]$noterp)`` — false for ``cr``, so the branch
   assigns ``XP[[i]] <- NULL`` (a no-op on an empty list) and the per-margin
   design/penalty from step 1 passes through unchanged. **This does not
   generalize to other basis classes** — a future ``ti()`` over a basis that
   does *not* set ``noterp`` (this project has none yet) would need that
   reparameterization implemented; :func:`ti_basis` has no code for it and
   would silently build the wrong thing if handed one, which is why this
   function validates nothing about the marginal basis beyond taking ``cr``
   inputs by construction.

3. **Each margin's penalty is rescaled by its own leading eigenvalue**,
   ``Sm_i ← Sm_i / λ_max(Sm_i)`` — a step ``smooth.construct.tensor.smooth.spec``
   always runs, independent of whether step 2 changed anything.

4. **The tensor design is the row-wise Kronecker product** of the (in this case,
   untouched) marginal designs, margin 1 varying *slower* than margin 2 in the
   column ordering — confirmed against ``mgcv::tensor.prod.model.matrix`` on a
   tiny hand-built example before being written here, not assumed from the name
   alone. **The tensor penalties** are ``S_1 = Sm_1 ⊗ I_{d2}``,
   ``S_2 = I_{d1} ⊗ Sm_2`` (``mgcv::tensor.prod.penalties``), where ``d_i`` is
   margin ``i``'s own (constrained) width.

5. **A second, *tensor-level* rescaling** — ``smoothCon()``'s own
   ``scale.penalty`` step (the same one :func:`cr_basis` applies for a
   standalone ``cr`` term, read from the same source lines), but now over the
   **full tensor** ``X``/``S_i``, not the margin's: ``S_i ← S_i /
   (norm₁(S_i) / norm∞(X)²)``, using the tensor ``X`` from step 4. This is a
   *second* application of the same formula the margin's own :func:`cr_basis`
   call already ran once at step 1 — ``smoothCon()`` rescales every smooth it
   returns, and a tensor-product smooth is itself a ``smoothCon()`` return
   value, so the rescaling fires twice, once at each level. Skipping this step
   reproduces ``mgcv``'s design exactly but its penalty by a constant factor per
   block (measured: the two mismatched, before this step was added, at a
   *different* ratio per block — 8.06x on one case's ``S_1`` — which is why
   catching this needed instrumenting the source rather than trusting the
   margin-level rescaling to be the only one).

Verified against ``smoothCon(ti(x1, x2, k=(k1,k2), bs="cr"), absorb.cons=TRUE)``
to float round-trip precision (~1e-15) on both a synthetic case and the target
formula's own ``ti(AttdAge, PolYear, k=c(13,6))`` knot vectors, tier 1, before
this function was written (module tests carry the tier-1 reading; the
CI-dispatched tier-3 reading is in ``docs/CONFORMANCE_LEDGER.md``).

Not handled yet
----------------
**Extrapolation beyond the knot range.** All five of slice 2's cases place ``x``
strictly inside ``[knots[0], knots[-1]]`` (default knots are quantiles of ``x``
itself; the supplied-knot cases, including the target formula's own
``AttdAge``/``PolYear`` knot vectors, draw ``x`` from the same range the knots
span), so this was never exercised and is not verified. The natural boundary condition
(``δ`` at the two end knots is zero) makes extrapolation locally linear only in
the immediate neighbourhood of a boundary knot with zero curvature there — the
per-interval Hermite formula used for interior evaluation does not by itself
reduce to that outside the range, and nothing here has measured what ``mgcv``
actually does at ``x`` outside ``[knots[0], knots[-1]]``. A future slice needing
knots that do not span the data range (e.g. the target formula's own hand-chosen
``AttdAge``/``PolYear`` knots against real data) must verify this before relying
on it — CLAUDE.md: mark the uncertainty rather than guess the derivation.
"""

import numpy as np

from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "absorb_sum_to_zero_constraint",
    "by_scale_design",
    "cr_basis",
    "cr_default_knots",
    "sum_to_zero_null_space",
    "ti_basis",
]

_MIN_K = 3
"""mgcv's own floor (`smooth.construct.cr.smooth.spec`): `bs.dim < 3` is bumped to
3 with a warning. Below 3, `k - 2 < 1` and the interior tridiagonal system this
basis solves is empty or ill-formed."""


def cr_default_knots(x: np.ndarray, k: int) -> np.ndarray:
    """``mgcv``'s default ``cr`` knot placement: quantiles of the *unique* data.

    Read directly from ``mgcv:::smooth.construct.cr.smooth.spec``:
    ``quantile(unique(x), seq(0, 1, length = k))``. R's ``quantile()`` default is
    type 7 (linear interpolation between order statistics), which is also
    ``numpy.quantile``'s default ``method``, made explicit below rather than left
    to NumPy's own default in case that default ever changes.
    """
    if k < _MIN_K:
        raise PolarisValidationError(f"cr_default_knots needs k >= {_MIN_K}; got k={k}.")
    xu = np.unique(np.asarray(x, dtype=np.float64))
    if xu.shape[0] < k:
        raise PolarisValidationError(
            f"cr_default_knots: only {xu.shape[0]} unique x value(s) but k={k} "
            "knots were requested — mgcv refuses this too ('insufficient unique "
            "values to support k knots')."
        )
    probs = np.linspace(0.0, 1.0, k, dtype=np.float64)
    return np.quantile(xu, probs, method="linear")


def _r_norm_one(matrix: np.ndarray) -> float:
    """R's ``norm(A)`` default (``type="O"``, the one-norm): the largest absolute
    column sum. NumPy's ``ord=1`` on ``np.linalg.norm`` matches this exactly, but
    named here so the convention is not left to a bare ``ord=1`` at the call site."""
    return float(np.max(np.sum(np.abs(matrix), axis=0)))


def _r_norm_inf(matrix: np.ndarray) -> float:
    """R's ``norm(A, type="I")`` — the infinity-norm: the largest absolute row sum."""
    return float(np.max(np.sum(np.abs(matrix), axis=1)))


def _hermite_weights(x: np.ndarray, knots: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-point bracket index and the four cubic-Hermite-with-curvature weights.

    Returns ``(j, a, c)`` where ``j`` is the 0-indexed left knot of each point's
    bracketing interval, ``a`` is ``(n, 2)`` — the linear weights on
    ``f_j, f_{j+1}`` — and ``c`` is ``(n, 2)`` — the cubic weights on the interval's
    two curvature terms, following Wood §5.3.1's
    ``a_j(x) = (x*_{j+1}-x)/h_j``, ``c_j(x) = [(x*_{j+1}-x)³/h_j - h_j(x*_{j+1}-x)]/6``
    (and the mirrored pair at ``j+1``).
    """
    k = knots.shape[0]
    j = np.clip(np.searchsorted(knots, x, side="right") - 1, 0, k - 2)
    h_j = knots[j + 1] - knots[j]
    left = knots[j + 1] - x
    right = x - knots[j]
    a = np.stack([left / h_j, right / h_j], axis=1)
    c = np.stack(
        [
            (left**3 / h_j - h_j * left) / 6.0,
            (right**3 / h_j - h_j * right) / 6.0,
        ],
        axis=1,
    )
    return j, a, c


def cr_basis(x: np.ndarray, knots: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The **unconstrained** ``cr`` design and (rescaled) penalty, rank ``k``.

    One column per knot — this is Wood's natural-cubic-spline basis in terms of
    the knot *values* ``f``, before ``mgcv``'s identifiability constraint is
    absorbed (:func:`absorb_sum_to_zero_constraint` does that). Matches
    ``smoothCon(..., absorb.cons=FALSE)$X`` / ``$S[[1]]`` to float round-trip
    precision (module docstring).

    Args:
        x: Covariate values, ``(n,)``.
        knots: Strictly increasing knot locations, ``(k,)``, ``k >= 3``.
    """
    knots = np.asarray(knots, dtype=np.float64)
    x = np.asarray(x, dtype=np.float64)
    k = knots.shape[0]
    if k < _MIN_K:
        raise PolarisValidationError(f"cr_basis needs at least {_MIN_K} knots; got {k}.")
    if np.any(np.diff(knots) <= 0):
        raise PolarisValidationError("cr_basis: knots must be strictly increasing.")

    h = np.diff(knots)
    n_interior = k - 2

    d_op = np.zeros((n_interior, k), dtype=np.float64)
    b_op = np.zeros((n_interior, n_interior), dtype=np.float64)
    for i in range(n_interior):
        d_op[i, i] = 1.0 / h[i]
        d_op[i, i + 1] = -1.0 / h[i] - 1.0 / h[i + 1]
        d_op[i, i + 2] = 1.0 / h[i + 1]
        b_op[i, i] = (h[i] + h[i + 1]) / 3.0
    for i in range(n_interior - 1):
        b_op[i, i + 1] = h[i + 1] / 6.0
        b_op[i + 1, i] = h[i + 1] / 6.0

    try:
        f_inner = np.linalg.solve(b_op, d_op)
    except np.linalg.LinAlgError as exc:
        raise PolarisComputationError(
            f"cr_basis: the interior curvature system is singular for knots {knots!r}."
        ) from exc

    s_full = f_inner.T @ d_op
    s_full = (s_full + s_full.T) / 2.0

    f_star = np.zeros((k, k), dtype=np.float64)
    f_star[1:-1, :] = f_inner  # natural boundary condition: rows 0 and k-1 stay zero

    n = x.shape[0]
    j, a, c = _hermite_weights(x, knots)
    design = np.zeros((n, k), dtype=np.float64)
    rows = np.arange(n)
    np.add.at(design, (rows, j), a[:, 0])
    np.add.at(design, (rows, j + 1), a[:, 1])
    design += c[:, [0]] * f_star[j, :]
    design += c[:, [1]] * f_star[j + 1, :]

    max_x_inf_norm_sq = _r_norm_inf(design) ** 2
    if max_x_inf_norm_sq == 0.0:
        raise PolarisComputationError("cr_basis: the design matrix is identically zero.")
    scale = _r_norm_one(s_full) / max_x_inf_norm_sq
    if scale == 0.0:
        raise PolarisComputationError("cr_basis: the unscaled penalty is identically zero.")
    return design, s_full / scale


def by_scale_design(design: np.ndarray, by: np.ndarray) -> np.ndarray:
    """Apply ``mgcv``'s numeric-``by`` construction to an **unconstrained** basis.

    Slice 5 (``docs/PLAN_mgcv_parity_engine.md``, the MI term
    ``s(AttdAge, by=StudyYear_C)``). Read directly off ``mgcv``'s own behaviour
    (measured against ``smoothCon(s(x, by=z, bs="cr", k), absorb.cons=TRUE)`` before
    being written here, CLAUDE.md's "do not guess at a derivation" — not merely
    read from documentation): a numeric-``by`` smooth's identifiability constraint
    matrix ``C`` has **zero rows** — ``mgcv`` does not absorb a sum-to-zero
    constraint on it at all, because (``?s``'s own stated reason) ``by * constant``
    need not be collinear with anything else in the model the way a bare smooth's
    constant term is with the intercept. So the by-term's design is the
    **unconstrained** ``k``-column :func:`cr_basis` output with each row scaled by
    the by-variable value at that row, and its penalty is that same unconstrained
    ``S`` — untouched by the scaling, and not put through
    :func:`absorb_sum_to_zero_constraint`.

    Args:
        design: The **unconstrained** ``(n, k)`` design from :func:`cr_basis` — not
            the constrained output of :func:`absorb_sum_to_zero_constraint`, which
            a numeric-``by`` term never applies.
        by: The by-variable value at each row, ``(n,)``.

    Returns:
        ``(n, k)`` — same shape as ``design``, each row ``i`` multiplied by
        ``by[i]``. The penalty ``S`` is unchanged by this operation and is not
        returned here; callers reuse :func:`cr_basis`'s own ``S``.
    """
    by = np.asarray(by, dtype=np.float64)
    if by.shape != (design.shape[0],):
        raise PolarisValidationError(
            f"by_scale_design: design has {design.shape[0]} row(s) but by has shape "
            f"{by.shape} — one by-value per row is required."
        )
    # np.asarray, not a bare product: mypy infers Any from the ndarray operator
    # and this function declares a concrete return type (PR #206 review [P1]).
    return np.asarray(design * by[:, np.newaxis], dtype=np.float64)


def sum_to_zero_null_space(design: np.ndarray) -> np.ndarray:
    """``mgcv``'s constraint null-space basis ``Z`` for ``colMeans(X) · β = 0``.

    Split out of :func:`absorb_sum_to_zero_constraint` (slice 5's ``ti()`` work,
    ``docs/PLAN_mgcv_parity_engine.md`` slice 5) because the tensor-interaction
    construction needs the SAME ``Z`` applied to a margin's training-row design
    reused to build that margin's own penalty — sharing this helper is what keeps
    the two call sites from ever computing two different null spaces for the same
    margin.

    Args:
        design: The unconstrained ``(n, k)`` design from :func:`cr_basis`.

    Returns:
        ``(k, k-1)`` — every column of ``Q`` after the first, from the full QR of
        ``colMeans(X)ᵀ`` (module docstring §4).
    """
    constraint = design.mean(axis=0).reshape(-1, 1)
    if np.allclose(constraint, 0.0):
        raise PolarisComputationError(
            "sum_to_zero_null_space: colMeans(X) is (numerically) zero — the "
            "constraint row carries no information to build a null space from."
        )
    q, _ = np.linalg.qr(constraint, mode="complete")
    return np.asarray(q[:, 1:], dtype=np.float64)


def absorb_sum_to_zero_constraint(
    design: np.ndarray, s: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Apply ``mgcv``'s default identifiability constraint: ``colMeans(X) · β = 0``.

    Args:
        design: The unconstrained ``(n, k)`` design from :func:`cr_basis`.
        s: The unconstrained ``(k, k)`` penalty from :func:`cr_basis`.

    Returns:
        ``(design_constrained, s_constrained)``, ``(n, k-1)`` and ``(k-1, k-1)``.
    """
    k = design.shape[1]
    if s.shape != (k, k):
        raise PolarisValidationError(
            f"absorb_sum_to_zero_constraint: design has {k} column(s) but s is {s.shape}."
        )
    z = sum_to_zero_null_space(design)
    design_c = design @ z
    s_c = z.T @ s @ z
    return design_c, (s_c + s_c.T) / 2.0


def _leading_eigenvalue(matrix: np.ndarray) -> float:
    """Largest eigenvalue of a symmetric matrix — ``eigen(S, symmetric=TRUE,
    only.values=TRUE)$values[1]`` in R, which orders eigenvalues descending."""
    return float(np.max(np.linalg.eigvalsh(matrix)))


def ti_basis(
    x1: np.ndarray,
    x2: np.ndarray,
    knots1: np.ndarray,
    knots2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The two-margin ``ti(x1, x2, bs="cr")`` tensor-interaction design and
    penalties (slice 5's ``ti(AttdAge, PolYear)``, module docstring's numbered
    construction).

    Every step is derived from ``mgcv``'s own source, not guessed (module
    docstring), and both margins are ``cr`` — the only basis this function
    handles, since the reparameterization ``cr`` margins skip (step 2) does not
    generalize to a basis that does not set ``noterp``.

    Args:
        x1: Margin-1 covariate values, ``(n,)``.
        x2: Margin-2 covariate values, ``(n,)``.
        knots1: Margin-1 knot vector, ``(k1,)``, ``k1 >= 3``.
        knots2: Margin-2 knot vector, ``(k2,)``, ``k2 >= 3``.

    Returns:
        ``(design, s1, s2)``: ``design`` is ``(n, (k1-1)*(k2-1))``, column order
        margin 1 slower / margin 2 faster (module docstring step 4); ``s1`` and
        ``s2`` are each ``((k1-1)*(k2-1), (k1-1)*(k2-1))``, the two penalty
        blocks ``mgcv`` assigns independent smoothing parameters to.
    """
    x1 = np.asarray(x1, dtype=np.float64)
    x2 = np.asarray(x2, dtype=np.float64)
    if x1.shape != x2.shape:
        raise PolarisValidationError(
            f"ti_basis: x1 has shape {x1.shape} but x2 has shape {x2.shape} — one "
            "value per row is required for both margins."
        )

    design1_unc, s1_unc = cr_basis(x1, knots1)
    design2_unc, s2_unc = cr_basis(x2, knots2)
    design1, s1_marg = absorb_sum_to_zero_constraint(design1_unc, s1_unc)
    design2, s2_marg = absorb_sum_to_zero_constraint(design2_unc, s2_unc)
    # Step 2 (no-op for cr margins — module docstring): mgcv's np=TRUE
    # reparameterization is skipped whenever every margin sets `noterp`, which
    # smooth.construct.cr.smooth.spec always does. Nothing to apply here.

    s1_norm = s1_marg / _leading_eigenvalue(s1_marg)
    s2_norm = s2_marg / _leading_eigenvalue(s2_marg)

    d1 = design1.shape[1]
    d2 = design2.shape[1]
    design = np.einsum("ij,ik->ijk", design1, design2).reshape(design1.shape[0], d1 * d2)

    eye1 = np.eye(d1, dtype=np.float64)
    eye2 = np.eye(d2, dtype=np.float64)
    s1_full = np.kron(s1_norm, eye2)
    s2_full = np.kron(eye1, s2_norm)

    max_x_inf_norm_sq = _r_norm_inf(design) ** 2
    if max_x_inf_norm_sq == 0.0:
        raise PolarisComputationError("ti_basis: the tensor design matrix is identically zero.")
    s1_scale = _r_norm_one(s1_full) / max_x_inf_norm_sq
    s2_scale = _r_norm_one(s2_full) / max_x_inf_norm_sq
    if s1_scale == 0.0 or s2_scale == 0.0:
        raise PolarisComputationError("ti_basis: an unscaled tensor penalty is identically zero.")

    return design, s1_full / s1_scale, s2_full / s2_scale

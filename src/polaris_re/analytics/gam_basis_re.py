"""``mgcv``'s ``bs="re"`` random-effect basis (capability ladder rung L2,
``docs/PLAN_mgcv_capability_ladder.md`` slice 2).

**Why this basis needs no spline machinery at all.** Unlike ``cr``/``ti``/``sz``
(:mod:`polaris_re.analytics.gam_basis_cr`), ``s(<factor>, bs="re")`` builds no
spline: the design is the factor's own **level-indicator matrix** — one column
per level, no reference level dropped — and the penalty is the **identity
matrix** over that same width. Measured directly against
``smoothCon(s(fac, bs="re"), absorb.cons=...)`` before this module was written
(the plan's own instruction: "verify by reading what ``smoothCon`` actually
returns rather than assuming symmetry with the ``cr`` basis's own
constraint-absorption story"):

* ``dim(X)`` is ``(n, n_levels)`` regardless of ``absorb.cons`` — ``TRUE`` and
  ``FALSE`` produce **bit-identical** ``X``.
* ``S[[1]]`` is exactly ``diag(n_levels)``.
* ``sm$C`` (the constraint matrix ``smoothCon`` would absorb) has **0 rows** —
  ``mgcv`` absorbs no identifiability constraint on a ``bs="re"`` term at all,
  regardless of the ``absorb.cons`` argument. This is documented ``mgcv``
  behaviour, not an accident of this probe: a random-effect smooth is
  identified by its ridge penalty (it must be free to shrink toward the
  overall mean at high smoothing, which a sum-to-zero constraint would
  prevent), not by a constraint the way ``cr``/``ti``/``sz`` are.
* ``sm$rank`` is ``n_levels`` (the penalty is full rank).

So :func:`re_basis` has no knot recipe, no rescaling and no constraint step —
every one of :mod:`gam_basis_cr`'s four construction stages collapses to
"build the indicator matrix, penalise it by the identity." The claim this
module carries (``docs/VERIFICATION_STANDARD.md`` §3.2, written before this
code): **polaris_re's ``re`` basis computes ``design_X``/``penalty_S`` from
the factor's level indicators and the identity penalty; ``mgcv`` computes them
via ``smoothCon(s(fac, bs="re"), absorb.cons=...)``; compared on ``design_X``,
``penalty_S`` and ``rank``.** ``absorb.cons`` does not enter the claim as a
variable — both settings of it produce the same ``mgcv`` output, verified
above, so there is only one ``mgcv`` producer to compare against regardless of
which setting a caller passes.

**Column order.** Column ``j`` is the indicator for level ``j`` in the
factor's own level order — the same 0-indexed convention
:mod:`gam_basis_cr`'s ``sz_basis`` already uses for its ``group`` argument
(``as.integer(fac) - 1`` on the R side), so a caller reading a factor column
out of the same data source needs no re-encoding between the two bases.

**One smoothing parameter regardless of level count** (measured,
``scripts/mgcv_penalty_count_probe.R`` and ``docs/MGCV_NOTATION_PRIMER.md``
§4): :func:`re_basis` returns exactly one penalty block — the whole
``n_levels x n_levels`` identity — never one block per level, which is what
makes this the cheapest basis in the library and what makes a Bühlmann-Straub
credibility structure (one ridge penalty over every level, one credibility
constant) fall out of the ordinary GAM machinery rather than needing its own
code path.
"""

import numpy as np

from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["re_basis"]


def re_basis(group: np.ndarray, n_levels: int) -> tuple[np.ndarray, np.ndarray]:
    """The ``s(<factor>, bs="re")`` design and its single penalty block.

    Args:
        group: 0-indexed factor-level code per row, ``(n,)`` integers in
            ``[0, n_levels)`` — the same convention
            :func:`~polaris_re.analytics.gam_basis_cr.sz_basis` uses for its
            own ``group`` argument (``as.integer(fac) - 1`` on the R side).
        n_levels: Number of factor levels (``mgcv``'s ``length(levels(fac))``)
            — an input, not derived from ``group``'s own observed range
            (Anchor 4: a level absent from one particular sample must not
            silently shrink the term).

    Returns:
        ``(design, s)``: ``design`` is ``(n, n_levels)``, the 0/1 level-
        indicator matrix (column ``j`` is 1 exactly where ``group == j``,
        matching ``smoothCon(s(fac, bs="re"))$X`` for **either** setting of
        ``absorb.cons`` — measured, module docstring); ``s`` is
        ``(n_levels, n_levels)``, exactly ``numpy.eye(n_levels)``, matching
        ``smoothCon(...)$S[[1]]``.

    Raises:
        PolarisValidationError: if ``n_levels < 2``, or if ``group`` carries a
            code outside ``[0, n_levels)``.
    """
    group = np.asarray(group, dtype=np.int64)
    if n_levels < 2:
        raise PolarisValidationError(f"re_basis needs at least 2 factor levels; got {n_levels}.")
    if group.size and (group.min() < 0 or group.max() >= n_levels):
        raise PolarisValidationError(
            f"re_basis: group codes must lie in [0, {n_levels}); got range "
            f"[{int(group.min())}, {int(group.max())}]."
        )
    n = group.shape[0]
    design = np.zeros((n, n_levels), dtype=np.float64)
    design[np.arange(n), group] = 1.0
    s = np.eye(n_levels, dtype=np.float64)
    return design, s

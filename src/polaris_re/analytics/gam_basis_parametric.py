"""``mgcv``'s unpenalized parametric block (capability ladder rung **L4**,
``docs/PLAN_mgcv_capability_ladder.md`` slice 5).

**Why this is the last rung this epic climbs.** The target formula
(``docs/MGCV_FEATURE_COVERAGE.md`` §1) opens with ``FaceSize + Smoke +
FaceSize:Smoke`` — parametric terms, not smooths — and until this module
existed, :func:`~polaris_re.analytics.gam_model.assemble_model_design` built an
intercept and then penalized terms only. There was no route for unpenalized
parametric *columns* at all, so the target formula was inexpressible for this
reason quite independently of any basis.

**Why this basis needs no spline machinery, no penalty, and no identifiability
constraint at all.** Unlike every other basis in this engine
(:mod:`~polaris_re.analytics.gam_basis_cr`, :mod:`~polaris_re.analytics.gam_basis_re`),
a parametric main effect or interaction is not one of ``mgcv``'s smooth classes
— ``s()``/``ti()``/``te()`` all build a *penalized* basis with its own knot
recipe. A parametric term in a ``gam()`` formula is built by the exact same
``model.matrix()`` call an ``lm()``/``glm()`` formula would use, under R's
default ``contr.treatment`` contrasts, and it is never penalized: it
contributes zero smoothing parameters and zero rows to ``paraPen``/the smooth
list. That is why :func:`parametric_design` returns a design only, no
penalty — a term built from it carries ``s=()`` in its
:class:`~polaris_re.analytics.gam_stage_a.TermExtract` (empty for an
unpenalized term, the same convention the existing ``"raw"`` factor-block
path already uses, ``gam_stage_a.extract_raw_terms``).

**The convention, measured directly against R before this module was written
(Anchor 8 — never guessed):**

.. code-block:: r

    > A <- factor(c("a0","a1","a2","a0","a1","a2"), levels=c("a0","a1","a2"))
    > B <- factor(c("b0","b0","b0","b1","b1","b1"), levels=c("b0","b1"))
    > colnames(model.matrix(~A + B + A:B, data.frame(A=A,B=B)))
    [1] "(Intercept)" "Aa1" "Aa2" "Bb1" "Aa1:Bb1" "Aa2:Bb1"

So a factor's own main-effect block drops its first (reference) level — 0 in
this module's 0-indexed convention, the same one
:mod:`~polaris_re.analytics.gam_basis_re`/``sz`` already use for their own
``group`` argument — and keeps one 0/1 indicator column per remaining level,
in level order. An interaction's columns are the outer product of the named
variables' own main-effect columns, with the **first-named variable varying
fastest** (``scripts/gam_parametric_stage_a_probe.R`` re-confirms this
convention on the tier-3 oracle for the exact ``FaceSize``/``Smoke`` case this
module's own conformance module fits, not only on the toy example above).

**Column order does not need to match ``mgcv``'s for Stage B (Anchor 2).**
Coefficients are basis-dependent; ``eta`` is not. Two designs that span the
same column space produce an identical fitted surface regardless of which
order their columns are in — this module still matches ``mgcv``'s own order
exactly (verified in :mod:`~polaris_re.analytics.gam_parametric_conformance`'s
Stage-A comparison), but that exactness is a Stage-A finding, not something
Stage B depends on.
"""

import numpy as np

from polaris_re.core.exceptions import PolarisValidationError

__all__ = ["parametric_design"]


def parametric_design(groups: tuple[np.ndarray, ...], levels: tuple[int, ...]) -> np.ndarray:
    """mgcv's own ``contr.treatment`` parametric block: one main effect
    (``len(groups) == 1``) or an interaction of two or more factors.

    Args:
        groups: One 0-indexed factor-level-code array per named variable,
            each ``(n,)``, in the term's own variable order (the order that
            determines which variable "varies fastest" in an interaction —
            module docstring). The same convention
            :func:`~polaris_re.analytics.gam_basis_re.re_basis` uses for its
            own ``group`` argument.
        levels: One factor-level count per entry of ``groups``, in the same
            order — an input, not derived from a sample's own observed range
            (Anchor 4: a level absent from one particular sample must not
            silently shrink the term).

    Returns:
        ``(n, width)``, ``width = prod(n_levels - 1 for n_levels in levels)``:
        for one variable, its own treatment-coded dummy columns (dropping
        level 0); for two or more, the outer product of every variable's own
        dummy columns, first-named variable fastest, matching
        ``model.matrix(~A + B + A:B, ...)``'s own column order under R's
        default contrasts.

    Raises:
        PolarisValidationError: if ``groups`` and ``levels`` have different
            lengths, either is empty, the group arrays disagree on row count,
            a level count is below 2, or a group code lies outside
            ``[0, n_levels)`` for its own variable.
    """
    if not groups:
        raise PolarisValidationError("parametric_design needs at least one variable.")
    if len(groups) != len(levels):
        raise PolarisValidationError(
            f"parametric_design: {len(groups)} group array(s) but {len(levels)} "
            "level count(s) — one level count per variable is required."
        )
    dummies: list[np.ndarray] = []
    n_rows: int | None = None
    for group, n_levels in zip(groups, levels, strict=True):
        group = np.asarray(group, dtype=np.int64)
        if n_levels < 2:
            raise PolarisValidationError(
                f"parametric_design: every variable needs at least 2 levels; got {n_levels}."
            )
        if n_rows is None:
            n_rows = group.shape[0]
        elif group.shape[0] != n_rows:
            raise PolarisValidationError(
                "parametric_design: every variable's group array must have the "
                f"same number of rows; got {n_rows} and {group.shape[0]}."
            )
        if group.size and (group.min() < 0 or group.max() >= n_levels):
            raise PolarisValidationError(
                f"parametric_design: group codes must lie in [0, {n_levels}); got "
                f"range [{int(group.min())}, {int(group.max())}]."
            )
        dummy = np.zeros((group.shape[0], n_levels - 1), dtype=np.float64)
        nonreference = group > 0
        dummy[nonreference, group[nonreference] - 1] = 1.0
        dummies.append(dummy)

    design = dummies[0]
    for dummy in dummies[1:]:
        n = design.shape[0]
        # First-named variable stays fastest as each subsequent variable is
        # folded in as the new "slowest" axis (module docstring's measured
        # convention) — `einsum` builds (n, new_width, existing_width) and the
        # row-major reshape flattens with the existing (faster) axis last.
        design = np.einsum("ni,nj->nji", design, dummy).reshape(n, dummy.shape[1] * design.shape[1])
    return design

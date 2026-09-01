"""``select = TRUE``'s double penalty — mgcv-parity engine, PLAN slice 7
(``docs/PLAN_mgcv_parity_engine.md``).

``select = TRUE`` is what takes the target formula's smoothing-parameter count
from 13 to 21 (PLAN §1): Marra & Wood's null-space shrinkage adds one extra
penalty per smooth term, penalising exactly the null space its own existing
penalty block(s) leave unpenalised, with its own independent smoothing
parameter — so a term with no signal can be driven all the way to zero under
REML, not merely made smoother.

**The rule, read off ``mgcv``'s own setup path at tier 1 before any code was
written here** (never from ``mgcv``'s R source — Anchor 8's companion
licensing rule): let ``S_1, ..., S_m`` be a term's own already-existing
penalty blocks, each at its natural (unscaled, ``lambda = 1``) magnitude.
Eigendecompose ``S_combined = S_1 + ... + S_m`` and let ``U0`` span the
eigenvectors whose eigenvalue falls below :func:`numpy.linalg.matrix_rank`'s
own tolerance — the null space ``S_combined`` leaves unpenalised. The extra
penalty is ``S_null = U0 @ U0.T``.

This rule is **basis-agnostic** — measured, not assumed, against ``mgcv``'s
own ``gam(..., select=TRUE, fit=FALSE)$smooth[[i]]$S`` (the last entry, which
``select=TRUE`` appends) across every term archetype the target formula
uses: a single-block ``cr`` term, a two-block numeric-``by`` ``cr`` term, a
three-block ``ti`` term and a three-block ``sz`` term (two of its three
blocks are the term's own existing per-level penalties). All four agreed to
float round-trip precision with no per-basis special-casing, which is why
this module takes a term's penalty blocks generically rather than
dispatching on ``TermSpec.basis``.

``fit = FALSE`` is exact for this purpose, not an approximation of fitting:
``S`` depends only on the model's structure (knots, basis, ``by``/factor
variables), never on ``y`` — see ``scripts/gam_select_penalty_probe.R``'s
own header for the measurement this module is built from.

**Parity claim (per ``docs/VERIFICATION_STANDARD.md``, written before the
code):** ``polaris_re``'s :func:`null_space_penalty` computes the extra
penalty from a term's own already-independently-verified penalty block(s)
(ADR-194/200/205/215's ``cr``/``by``/``ti``/``sz`` producers) via NumPy's own
eigendecomposition and ``matrix_rank`` tolerance; ``mgcv`` computes it via
``gam(formula, family, data, knots, select = TRUE, fit = FALSE)$smooth[[i]]$S``
(the last entry) — the setup-only path that builds every smooth's own
null-space penalty without fitting a model; compared on the null-space
penalty matrix ``S_null``, for each of the six target-formula-shaped cases
:data:`~polaris_re.analytics.gam_select_penalty.SELECT_PENALTY_CLAIM`'s own
comparator reads off ``scripts/gam_select_penalty_probe.R``.

This module is Stage A only. :func:`~polaris_re.analytics.gam_model.assemble_model_design`
now dispatches on ``ModelSpec.select`` and appends each term's own extra
block built here (PLAN slice 7's Stage B,
:mod:`~polaris_re.analytics.gam_select_multiterm_conformance`, ADR-217).
**Not yet built:** extending
:func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous` /
:func:`~polaris_re.analytics.gam_model.fit_polaris_gam`'s own free-``sp``
search to the doubled block count ``select = True`` produces — every case
this module and its Stage-B counterpart verify uses a fixed, externally-
supplied ``sp``. See ``docs/PLAN_mgcv_parity_engine.md`` slice 7 for what
remains.
"""

from typing import TypedDict

import numpy as np

from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "SELECT_PENALTY_CLAIM",
    "NullSpacePenaltyComparison",
    "RSelectPenaltyCase",
    "compare_null_space_penalty",
    "null_space_penalty",
]


class RSelectPenaltyCase(TypedDict):
    """The two keys :func:`compare_null_space_penalty` reads off one entry of
    ``scripts/gam_select_penalty_probe.R``'s own ``cases`` mapping. Each
    case's own extra covariate-recipe keys (``x``, and archetype-specific
    ones like ``by_var``/``x2``/``group``/``n_levels``) vary by term
    archetype and are read directly by callers building that term's own
    penalty blocks — not through this type, which only names what this
    module's own comparator needs."""

    S: list[list[list[float]]]
    rank: list[int]


_AGREEMENT_TOLERANCE = 1e-9
"""Same order as slice 2/5/6's own Stage-A tolerance
(``gam_stage_a._AGREEMENT_TOLERANCE``) — not imported from there, because
that constant belongs to the per-term extraction comparator this module
does not touch, and a shared value is not the same thing as a shared owner.
Both are right for the identical reason: float round-trip precision on a
comparison this small is ~1e-12 to 1e-14 (module docstring), three orders of
magnitude inside this bound."""


def null_space_penalty(s_blocks: tuple[np.ndarray, ...]) -> tuple[np.ndarray, int] | None:
    """The extra penalty ``select = TRUE`` adds for one term — see the module
    docstring for the rule and how it was measured.

    Args:
        s_blocks: A term's own already-existing penalty block(s), each
            ``(p, p)`` — e.g. :attr:`~polaris_re.analytics.gam_stage_a.TermExtract.s`.
            Never a value read from ``mgcv``'s own output (the ADR-193
            mechanical test): every block here comes from an
            already-independently-verified Python producer
            (:func:`~polaris_re.analytics.gam_basis_cr.cr_basis` and friends).

    Returns:
        ``(s_null, null_dim)`` — the extra penalty and its rank — or ``None``
        if the combined block is already full rank (no null space left to
        penalise, so ``select = TRUE`` would add nothing for this term).
        ``s_null`` is symmetrised (``(s + s.T) / 2``) to absorb the
        floating-point asymmetry an eigendecomposition-then-outer-product
        can introduce, matching
        :func:`~polaris_re.analytics.gam_basis_cr.absorb_sum_to_zero_constraint`'s
        own convention.

    Raises:
        PolarisValidationError: if ``s_blocks`` is empty, or its blocks are
            not all the same shape.
    """
    if not s_blocks:
        raise PolarisValidationError("null_space_penalty needs at least one penalty block.")
    shapes = {block.shape for block in s_blocks}
    if len(shapes) != 1:
        raise PolarisValidationError(
            f"null_space_penalty: penalty blocks have mismatched shapes {shapes} — "
            "they must all belong to the same term's design."
        )
    (p, p2) = next(iter(shapes))
    if p != p2:
        raise PolarisValidationError(
            f"null_space_penalty: penalty blocks are {p}x{p2}, not square."
        )

    combined = np.zeros((p, p), dtype=np.float64)
    for block in s_blocks:
        combined = combined + block
    combined = (combined + combined.T) / 2.0

    rank = int(np.linalg.matrix_rank(combined))
    null_dim = p - rank
    if null_dim == 0:
        return None

    evals, evecs = np.linalg.eigh(combined)
    order = np.argsort(evals)  # ascending — the smallest `null_dim` are the null space.
    u0 = evecs[:, order[:null_dim]]
    s_null = u0 @ u0.T
    return (s_null + s_null.T) / 2.0, null_dim


SELECT_PENALTY_CLAIM = VerificationClaim(
    claim=(
        "polaris_re.analytics.gam_select_penalty.null_space_penalty computes "
        "select=TRUE's extra penalty from a term's own already-independently-"
        "verified penalty block(s), via NumPy's own eigendecomposition and "
        "matrix_rank tolerance (module docstring: the null space of the "
        "blocks' unscaled sum); mgcv computes it via gam(formula, family, "
        "data, knots, select=TRUE, fit=FALSE)$smooth[[i]]$S (the last entry) "
        "— the setup-only path that builds every smooth's own null-space "
        "penalty without fitting a model (scripts/gam_select_penalty_probe.R); "
        "compared on the null-space penalty matrix S_null, one case per "
        "target-formula term archetype (cr, cr-by, ti, sz)."
    ),
    quantities=(
        ComparedQuantity(
            quantity="S_null",
            left_producer=(
                "gam_select_penalty.null_space_penalty (eigendecomposition of the "
                "term's own already-verified penalty blocks' unscaled sum)"
            ),
            right_producer=("mgcv gam(..., select=TRUE, fit=FALSE)$smooth[[i]]$S, last entry"),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""ADR-217's provenance declaration for PLAN slice 7 Stage A.
:func:`null_space_penalty`'s signature takes only ``s_blocks`` — a term's own
penalty block(s), themselves independently produced by ADR-194/200/205/215's
basis producers — never an R payload, so the ADR-193 mechanical test passes
by construction. The comparator (:func:`compare_null_space_penalty`) reads
``scripts/gam_select_penalty_probe.R``'s output only for the LAST entry of
each case's ``S`` list; the EXISTING blocks that same script emits are used
only to sanity-check that Python's own already-verified producers reproduce
them (a repeat of slice 2/5/6's own Stage-A claim, not re-declared here)."""


class NullSpacePenaltyComparison:
    """One case's Stage-A verdict for the null-space penalty — index range
    intentionally absent (this compares one matrix, not a term's full
    design/penalty/rank triple the way
    :class:`~polaris_re.analytics.gam_stage_a.TermExtractComparison` does)."""

    __slots__ = ("agrees", "case", "evidence", "max_abs_s_null_diff", "null_dim")

    def __init__(
        self,
        case: str,
        max_abs_s_null_diff: float,
        null_dim: int,
        agrees: bool,
        evidence: VerificationClaim,
    ) -> None:
        self.case = case
        self.max_abs_s_null_diff = max_abs_s_null_diff
        self.null_dim = null_dim
        self.agrees = agrees
        self.evidence = evidence


def compare_null_space_penalty(
    case: str, python_s_blocks: tuple[np.ndarray, ...], r_case: RSelectPenaltyCase
) -> NullSpacePenaltyComparison:
    """Compare Python's :func:`null_space_penalty` against one case of
    ``scripts/gam_select_penalty_probe.R``'s output.

    Args:
        case: The case name, e.g. ``"cr-ref-attdage-k13"`` — one of
            ``gam_select_penalty_probe.json``'s ``cases`` keys.
        python_s_blocks: The term's own already-existing penalty block(s) —
            never read from ``r_case``.
        r_case: ``r_json["cases"][case]`` — carries ``"S"`` (every block,
            existing ones first, the null-space one last) and ``"rank"``.
    """
    r_s_all = [np.asarray(block, dtype=np.float64) for block in r_case["S"]]
    if len(r_s_all) != len(python_s_blocks) + 1:
        raise PolarisComputationError(
            f"compare_null_space_penalty {case!r}: R emitted {len(r_s_all)} penalty "
            f"block(s) total, but Python supplied {len(python_s_blocks)} existing "
            "block(s) -- expected R to carry exactly one more (its own appended "
            "null-space penalty)."
        )
    r_s_null = r_s_all[-1]

    result = null_space_penalty(python_s_blocks)
    if result is None:
        raise PolarisComputationError(
            f"compare_null_space_penalty {case!r}: Python's combined penalty block "
            "is already full rank -- no null-space penalty to compare against R's."
        )
    python_s_null, null_dim = result

    if python_s_null.shape != r_s_null.shape:
        raise PolarisComputationError(
            f"compare_null_space_penalty {case!r}: R's null-space penalty is "
            f"{r_s_null.shape}, Python's is {python_s_null.shape}."
        )
    max_abs_s_null_diff = float(np.max(np.abs(r_s_null - python_s_null)))
    agrees = max_abs_s_null_diff < _AGREEMENT_TOLERANCE
    return NullSpacePenaltyComparison(
        case=case,
        max_abs_s_null_diff=max_abs_s_null_diff,
        null_dim=null_dim,
        agrees=agrees,
        evidence=SELECT_PENALTY_CLAIM,
    )

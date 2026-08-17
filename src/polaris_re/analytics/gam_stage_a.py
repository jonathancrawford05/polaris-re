"""Stage-A per-term extraction and comparison (mgcv-parity engine, slices 1 and 1b).

``docs/PLAN_mgcv_parity_engine.md`` slice 1's remaining scope, per
``docs/CONTINUATION_mgcv_parity_engine.md``: the R-side per-term extractor
(``scripts/gam_term_extract.R``) and its Python comparator. ADR-191 already settled
*what* Stage A compares for mgcv-native bases (``smoothCon(..., absorb.cons=TRUE)``);
this module builds the comparator and proves the extraction machinery on the "raw"
basis first, per Anchor 1's "prove the harness on a known-good basis before trusting
it on a new one."

Why "raw" needs its own code path
----------------------------------
``TermSpec.basis == "raw"`` names the tensor MI surface's own route through
``paraPen`` (ADR-189 decision 1) — a single flat design and two supplied penalty
matrices, with no ``mgcv`` smooth-class object behind it (a ``paraPen``-only fit has
an empty smooth list, ADR-189 amendment 1). There is nothing to call ``smoothCon()``
on. So both sides read what the fit actually used rather than a basis recipe:
``scripts/gam_term_extract.R`` reads ``m$paraPen$S`` and ``m$paraPen$rank`` off the
fitted ``mgcv`` object; :func:`extract_raw_terms` reads the already-fitted
:class:`~polaris_re.analytics.experience_mgcv_conformance.DesignExport`, never
re-derived — the same discipline
:func:`~polaris_re.analytics.experience_mgcv_conformance.build_design` itself
follows, because a comparison against a design the model did not actually fit
measures the exporter rather than the fitter.

mgcv-native extraction (slice 1b, ``docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md``)
--------------------------------------------------------------------------------------
:func:`extract_smooth_terms` is the ``cr``/``ti``/``sz`` counterpart to
:func:`extract_raw_terms`, but it does not compute an independent Python basis —
that is slice 2's job, paired with the first Python basis construction that needs a
referent (ADR-192). What ADR-191 already proved is that ``scripts/gam_term_extract.R``'s
``smoothCon(..., absorb.cons=TRUE)`` extraction agrees, term by term, with the
independent ``predict(type="lpmatrix")`` / ``m$smooth[[j]]`` route — the R script's own
internal guard, promoted from that ADR's one-off diagnostic into a standing check that
fails the R side loudly if it ever stops holding. So :func:`extract_smooth_terms`'s job
is packaging that already-verified R output into the same :class:`TermExtract` shape
:func:`extract_raw_terms` produces, not re-verifying it.

What Stage A has and has not proven (ADR-193)
---------------------------------------------
Neither path here is a basis-parity comparison yet, and both now say so in the
type rather than only in prose. :data:`RAW_PATH_CLAIM` marks the ``raw`` path's
design and penalties as ``ECHO`` (Python builds them, mgcv is fitted *on them*,
so a zero diff proves no tampering) with ``rank`` the one independently produced
column; :data:`SMOOTH_PATH_CLAIM` marks every mgcv-native quantity as
``TRANSPORT`` (one producer, parsed by the other). Slice 2 — a Python ``cr``
basis built from knots and Wood's definition — is the first Stage-A work that
can carry ``INDEPENDENT`` provenance, and ``docs/VERIFICATION_STANDARD.md``
requires it to declare that before the comparison is reported as parity.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.experience_mgcv_conformance import DesignExport
from polaris_re.analytics.gam_term_spec import SUPPORTED_BASES, TermSpec
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "RAW_PATH_CLAIM",
    "SMOOTH_PATH_CLAIM",
    "RTermPayload",
    "TermExtract",
    "TermExtractComparison",
    "compare_term_extract",
    "extract_raw_terms",
    "extract_smooth_terms",
    "raw_term_specs",
]


class RTermPayload(TypedDict):
    """The keys read from one term entry of ``scripts/gam_term_extract.R``'s JSON
    output — either ``designs.<id>.terms.<label>`` (raw/paraPen) or
    ``smooth_designs.<label>`` (mgcv-native, slice 1b) — the R-side schema
    :func:`compare_term_extract` reads, documented in the type rather than left as
    ``Any`` (CLAUDE.md §5)."""

    index_start: int
    index_end: int
    X: list[list[float]]
    S: list[list[list[float]]]
    rank: list[int]
    knots: list[float] | None


_AGREEMENT_TOLERANCE = 1e-9
"""Stage A compares a shared design and shared penalties at fixed sp (RUNBOOK
level 1's regime) — the same regime ADR-189 amendment 1 verified to 5e-13 through the
fitter, so an exact-comparison tolerance is appropriate here too, not a fitted-value
tolerance. An order of magnitude looser than that measurement, matching Anchor 8:
derived from an existing verified quantity, not chosen to make this check green."""


RAW_PATH_CLAIM = VerificationClaim(
    claim=(
        "extract_raw_terms slices the term's design and penalty blocks out of the "
        "DesignExport the Python fitter produced; gam_term_extract.R reads the same "
        "quantities back off an mgcv fit that was HANDED that design and those "
        "penalties (y ~ 0 + X + offset(off) with paraPen, scalePenalty=FALSE). Only "
        "the penalty rank is computed independently on the two sides."
    ),
    quantities=(
        ComparedQuantity(
            quantity="index_range",
            left_producer="extract_raw_terms (assigned from DesignExport.n_tensor/n_coef)",
            right_producer="gam_term_extract.R (assigned by the same convention, ADR-192)",
            provenance=ComparisonProvenance.ECHO,
        ),
        ComparedQuantity(
            quantity="design_X",
            left_producer="PenalizedTensorMIModel's fitted design (Python B-spline tensor)",
            right_producer="mgcv predict(type='lpmatrix') — returning the X it was supplied",
            provenance=ComparisonProvenance.ECHO,
        ),
        ComparedQuantity(
            quantity="penalty_S",
            left_producer="tensor_penalties (Python difference penalties)",
            right_producer="mgcv m$paraPen$S — the penalties it was supplied, unscaled",
            provenance=ComparisonProvenance.ECHO,
        ),
        ComparedQuantity(
            quantity="rank",
            left_producer="numpy.linalg.matrix_rank on the Python penalty block",
            right_producer="mgcv m$paraPen$rank (mgcv's own rank determination)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""The ``raw``/``paraPen`` path's provenance (ADR-193).

``design_X`` and ``penalty_S`` are ECHO: Python builds them, writes them to the
exchange, and mgcv is fitted **on them**, so a zero diff proves mgcv did not
reparameterise or rescale what it was handed — a real no-tampering check, and the
one ``scalePenalty=FALSE`` exists to make meaningful — but not evidence that the
two sides would agree on a basis mgcv constructed itself. ``rank`` is the single
independently produced column, which is why it is the only one that can carry a
parity claim here."""


SMOOTH_PATH_CLAIM = VerificationClaim(
    claim=(
        "gam_term_extract.R's smoothCon(absorb.cons=TRUE) branch computes the "
        "mgcv-native term; extract_smooth_terms PARSES that same payload into a "
        "TermExtract. No Python cr/ti/sz basis exists yet (slice 2), so every "
        "compared quantity has a single producer and the comparison can only fail "
        "on the JSON round trip."
    ),
    quantities=(
        ComparedQuantity(
            quantity="index_range",
            left_producer="extract_smooth_terms (read from the R payload)",
            right_producer="gam_term_extract.R extract_smooth_one (assigned [0, width), ADR-192)",
            provenance=ComparisonProvenance.TRANSPORT,
        ),
        ComparedQuantity(
            quantity="design_X",
            left_producer="extract_smooth_terms (read from the R payload)",
            right_producer="mgcv smoothCon(..., absorb.cons=TRUE)$X",
            provenance=ComparisonProvenance.TRANSPORT,
        ),
        ComparedQuantity(
            quantity="penalty_S",
            left_producer="extract_smooth_terms (read from the R payload)",
            right_producer="mgcv smoothCon(...)$S",
            provenance=ComparisonProvenance.TRANSPORT,
        ),
        ComparedQuantity(
            quantity="rank",
            left_producer="extract_smooth_terms (read from the R payload)",
            right_producer="mgcv smoothCon(...)$rank",
            provenance=ComparisonProvenance.TRANSPORT,
        ),
        ComparedQuantity(
            quantity="knots",
            left_producer="extract_smooth_terms (read from the R payload)",
            right_producer="mgcv smoothCon(...)$xp",
            provenance=ComparisonProvenance.TRANSPORT,
        ),
    ),
)
"""The mgcv-native path's provenance (ADR-193).

Every quantity is TRANSPORT: :func:`extract_smooth_terms` reads the R payload and
:func:`compare_term_extract` then compares the result against that same payload,
so the diffs are structurally zero. This is a genuine check of the JSON round trip
and the packaging, and it is *not* evidence about bases. The verification that
carries weight on this path is the R script's own internal guard, which compares
``smoothCon()`` against the independent ``predict(type="lpmatrix")`` /
``m$smooth[[j]]`` route inside R (ADR-191).

Slice 2 replaces the left producer with a Python ``cr`` basis built from the
knots and Wood's basis definition — at which point these quantities become
INDEPENDENT and the comparison starts meaning what its columns say."""


@dataclass(frozen=True)
class TermExtract:
    """One term's Stage-A artefacts, mirroring what ``gam_term_extract.R`` emits.

    Args:
        label: Matches the R side's per-term key, so a comparison keys off the same
            string on both sides rather than positional order.
        index_start: First coefficient column this term owns (inclusive).
        index_end: One past the last coefficient column this term owns (exclusive) —
            Python slice convention, since both sides of this comparison are Python
            or JSON-via-Python.
        design: This term's own columns of the fitted design, ``(n_rows, width)``.
        s: Every penalty this term carries, each ``(width, width)``. Empty for an
            unpenalized term (e.g. a factor block).
        rank: One rank per entry of :attr:`s`, same order.
        evidence: How this extract was produced relative to the R side it will be
            compared against (ADR-193). Required, and with no default on purpose:
            a new producer cannot be written without answering "who computed each
            side?", which is the question slices 1 and 1b each answered only in
            prose. :data:`RAW_PATH_CLAIM` and :data:`SMOOTH_PATH_CLAIM` are the two
            answers that exist today.
        knots: Knot locations actually used, or ``None`` — always ``None`` for
            ``basis="raw"``, which has no knot recipe (:class:`TermSpec`'s own
            validation forbids supplying knots for it). Populated for mgcv-native
            terms by :func:`extract_smooth_terms` (slice 1b).
    """

    label: str
    index_start: int
    index_end: int
    design: np.ndarray
    s: tuple[np.ndarray, ...]
    rank: tuple[int, ...]
    evidence: VerificationClaim
    knots: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not self.label:
            raise PolarisValidationError("A TermExtract needs a non-empty label.")
        if self.index_end <= self.index_start:
            raise PolarisValidationError(
                f"TermExtract {self.label!r} has index range "
                f"[{self.index_start}, {self.index_end}) — end must exceed start."
            )
        width = self.index_end - self.index_start
        if self.design.shape[1] != width:
            raise PolarisValidationError(
                f"TermExtract {self.label!r} carries a design block with "
                f"{self.design.shape[1]} column(s) but its index range spans {width}."
            )
        for j, block in enumerate(self.s):
            if block.shape != (width, width):
                raise PolarisValidationError(
                    f"TermExtract {self.label!r} penalty S[{j}] is {block.shape} but "
                    f"the term's own width is {width}x{width}."
                )
        if len(self.rank) != len(self.s):
            raise PolarisValidationError(
                f"TermExtract {self.label!r} carries {len(self.s)} penalty block(s) "
                f"but {len(self.rank)} rank value(s) — one rank per S_j is required."
            )


def raw_term_specs(*, with_factor: bool, factor_label: str = "sex") -> tuple[TermSpec, ...]:
    """The term decomposition Anchor 1's harness proof runs against.

    The tensor MI surface has no per-term structure of ``mgcv``'s own to match — a
    ``paraPen``-only fit's smooth list is empty — so this is the decomposition the
    design's own index ranges already impose: one penalized ``"tensor"`` term over
    ``[0, n_tensor)``, and, when the design carries a factor block, one unpenalized
    ``"factor:<name>"`` term over ``[n_tensor, n_coef)``. Not a label ``mgcv`` assigns
    (there is none to match), but one both sides of the comparison can key on.
    """
    terms: tuple[TermSpec, ...] = (
        TermSpec(label="tensor", variables=("attained_age", "calendar_year"), basis="raw"),
    )
    if with_factor:
        terms += (TermSpec(label=f"factor:{factor_label}", variables=(factor_label,), basis="raw"),)
    return terms


def extract_raw_terms(terms: tuple[TermSpec, ...], export: DesignExport) -> dict[str, TermExtract]:
    """Slice a fitted :class:`DesignExport` into one :class:`TermExtract` per term.

    Every term must have ``basis="raw"``; a ``ModelSpec`` mixing bases is not this
    function's problem to solve — mgcv-native extraction is slice 2's module.

    The tensor term's :attr:`~TermExtract.rank` is computed with
    :func:`numpy.linalg.matrix_rank`'s *default* tolerance, while the R side reports
    ``mgcv``'s own ``m$paraPen$rank``. Rank is the one field this comparison computes
    independently on both sides rather than round-tripping the same numbers through
    JSON, so their agreement here rests on that default tolerance rather than a
    tolerance chosen to match ``mgcv``'s convention. It agrees on the well-conditioned
    difference penalties this basis carries (PR #197 review [P2]) — worth keeping in
    mind if slice 2 extends this comparator to a less well-conditioned penalty.
    """
    n_tensor = export.n_tensor
    n_coef = export.n_coef
    result: dict[str, TermExtract] = {}
    for term in terms:
        if term.basis != "raw":
            raise PolarisValidationError(
                f"extract_raw_terms only handles basis='raw' terms; {term.label!r} "
                f"is basis={term.basis!r} (mgcv-native extraction is slice 2's module)."
            )
        s_blocks: tuple[np.ndarray, ...]
        rank: tuple[int, ...]
        if term.label == "tensor":
            start, end = 0, n_tensor
            s_blocks = (
                np.ascontiguousarray(export.s_age[start:end, start:end]),
                np.ascontiguousarray(export.s_year[start:end, start:end]),
            )
            rank = tuple(int(np.linalg.matrix_rank(block)) for block in s_blocks)
        elif term.label.startswith("factor:"):
            start, end = n_tensor, n_coef
            s_blocks = ()
            rank = ()
        else:
            raise PolarisValidationError(
                f"raw_term_specs only names 'tensor' or 'factor:*' terms; got {term.label!r}."
            )
        result[term.label] = TermExtract(
            label=term.label,
            index_start=start,
            index_end=end,
            design=np.ascontiguousarray(export.design[:, start:end]),
            s=s_blocks,
            rank=rank,
            evidence=RAW_PATH_CLAIM,
            knots=None,
        )
    return result


_MGCV_NATIVE_BASES = tuple(basis for basis in SUPPORTED_BASES if basis != "raw")
"""``SUPPORTED_BASES`` minus ``"raw"`` — the bases :func:`extract_smooth_terms`
handles, mirroring :func:`extract_raw_terms`'s own basis restriction the other way.
Derived rather than a hand-maintained literal, so a new basis added to
``SUPPORTED_BASES`` cannot silently drift out of step with this set (PR #199 review
[P2])."""


def extract_smooth_terms(
    terms: tuple[TermSpec, ...], r_terms: dict[str, RTermPayload]
) -> dict[str, TermExtract]:
    """Package the R-side ``smoothCon()`` extraction into :class:`TermExtract`.

    The mgcv-native counterpart to :func:`extract_raw_terms` (work order §2), but
    not its computational counterpart: there is no independent Python ``cr``/``ti``/
    ``sz`` basis to derive from yet (slice 2, ADR-192). ADR-191 already established
    that ``scripts/gam_term_extract.R``'s ``smoothCon(..., absorb.cons=TRUE)``
    extraction agrees with the independent ``lpmatrix``/``m$smooth[[j]]`` route, and
    the R script's own internal guard (work order §2) re-checks that on every run —
    so this function's job is reading that already-verified output into the shape
    :func:`compare_term_extract` consumes, the same shape :func:`extract_raw_terms`
    produces from an actually-fitted Python design.

    Every term must have a basis in ``("cr", "ti", "sz")`` and a matching entry in
    ``r_terms``; a ``ModelSpec`` mixing in a ``"raw"`` term is :func:`extract_raw_terms`'s
    problem to solve, not this function's.
    """
    result: dict[str, TermExtract] = {}
    for term in terms:
        if term.basis not in _MGCV_NATIVE_BASES:
            raise PolarisValidationError(
                f"extract_smooth_terms only handles mgcv-native bases "
                f"{_MGCV_NATIVE_BASES}; {term.label!r} is basis={term.basis!r} "
                f"('raw' terms use extract_raw_terms)."
            )
        if term.label not in r_terms:
            raise PolarisValidationError(
                f"extract_smooth_terms: {term.label!r} has no matching entry in "
                f"the R-side payload (available: {sorted(r_terms)})."
            )
        r_term = r_terms[term.label]
        r_knots = r_term.get("knots")
        result[term.label] = TermExtract(
            label=term.label,
            index_start=int(r_term["index_start"]),
            index_end=int(r_term["index_end"]),
            design=np.asarray(r_term["X"], dtype=np.float64),
            s=tuple(np.asarray(block, dtype=np.float64) for block in r_term["S"]),
            rank=tuple(int(v) for v in r_term["rank"]),
            evidence=SMOOTH_PATH_CLAIM,
            knots=tuple(float(v) for v in r_knots) if r_knots is not None else None,
        )
    return result


@dataclass(frozen=True)
class TermExtractComparison:
    """One term's Stage-A verdict: index range, design block, every penalty, rank,
    knots — and the provenance that says what those numbers are evidence *of*.

    :attr:`agrees` answers "did the numbers match"; :attr:`evidence` answers "who
    computed each side". Both are needed to state a result: a zero diff on an ECHO
    or TRANSPORT quantity is a working harness, not parity (ADR-193). Reports must
    render :attr:`evidence` alongside the diffs —
    :func:`~polaris_re.core.verification.evidence_markdown` does this — so the
    distinction travels with the table instead of living in a caption.
    """

    label: str
    index_range_agrees: bool
    max_abs_design_diff: float
    max_abs_s_diff: tuple[float, ...]
    rank_diff: tuple[int, ...]
    knots_agree: bool
    max_abs_knots_diff: float | None
    agrees: bool
    evidence: VerificationClaim


def compare_term_extract(python: TermExtract, r_term: RTermPayload) -> TermExtractComparison:
    """Compare a Python :class:`TermExtract` against one term of the R-side JSON.

    ``r_term`` is a ``designs.<id>.terms.<label>`` entry from
    ``scripts/gam_term_extract.R``'s output — see :class:`RTermPayload` for the keys
    read.

    The verdict carries :attr:`TermExtract.evidence` through unchanged: provenance
    is a property of how the Python operand was produced, which this function is not
    in a position to second-guess, so it is declared by the producer and reported
    here rather than re-derived (ADR-193).
    """
    r_start = int(r_term["index_start"])
    r_end = int(r_term["index_end"])
    index_range_agrees = (r_start, r_end) == (python.index_start, python.index_end)

    r_design = np.asarray(r_term["X"], dtype=np.float64)
    if r_design.shape != python.design.shape:
        raise PolarisComputationError(
            f"TermExtract {python.label!r}: R's design block is {r_design.shape} but "
            f"Python's is {python.design.shape} — not comparable element-wise."
        )
    max_abs_design_diff = float(np.max(np.abs(r_design - python.design)))

    r_s = [np.asarray(block, dtype=np.float64) for block in r_term["S"]]
    if len(r_s) != len(python.s):
        raise PolarisComputationError(
            f"TermExtract {python.label!r}: R emitted {len(r_s)} penalty block(s), "
            f"Python built {len(python.s)} — the two sides disagree on how many "
            f"penalties this term carries."
        )
    max_abs_s_diff = tuple(
        float(np.max(np.abs(r_block - py_block)))
        for r_block, py_block in zip(r_s, python.s, strict=True)
    )

    r_rank = tuple(int(v) for v in r_term["rank"])
    if len(r_rank) != len(python.rank):
        raise PolarisComputationError(
            f"TermExtract {python.label!r}: R reported {len(r_rank)} rank value(s), "
            f"Python computed {len(python.rank)}."
        )
    rank_diff = tuple(r - p for r, p in zip(r_rank, python.rank, strict=True))

    # Knots: absent on both sides (basis="raw", TermSpec forbids supplying them)
    # agrees trivially; present on both sides compares element-wise; present on
    # only one side is a real disagreement (one side thinks this term has a knot
    # recipe, the other doesn't) rather than a shape mismatch to refuse on.
    r_knots = r_term.get("knots")
    max_abs_knots_diff: float | None
    if r_knots is None and python.knots is None:
        knots_agree = True
        max_abs_knots_diff = None
    elif r_knots is None or python.knots is None:
        knots_agree = False
        max_abs_knots_diff = None
    else:
        r_knots_arr = np.asarray(r_knots, dtype=np.float64)
        py_knots_arr = np.asarray(python.knots, dtype=np.float64)
        if r_knots_arr.shape != py_knots_arr.shape:
            raise PolarisComputationError(
                f"TermExtract {python.label!r}: R emitted {r_knots_arr.shape[0]} "
                f"knot(s), Python built {py_knots_arr.shape[0]} — not comparable "
                f"element-wise."
            )
        max_abs_knots_diff = float(np.max(np.abs(r_knots_arr - py_knots_arr)))
        knots_agree = max_abs_knots_diff < _AGREEMENT_TOLERANCE

    agrees = (
        index_range_agrees
        and max_abs_design_diff < _AGREEMENT_TOLERANCE
        and all(d < _AGREEMENT_TOLERANCE for d in max_abs_s_diff)
        and all(d == 0 for d in rank_diff)
        and knots_agree
    )
    return TermExtractComparison(
        label=python.label,
        index_range_agrees=index_range_agrees,
        max_abs_design_diff=max_abs_design_diff,
        max_abs_s_diff=max_abs_s_diff,
        rank_diff=rank_diff,
        knots_agree=knots_agree,
        max_abs_knots_diff=max_abs_knots_diff,
        agrees=agrees,
        evidence=python.evidence,
    )

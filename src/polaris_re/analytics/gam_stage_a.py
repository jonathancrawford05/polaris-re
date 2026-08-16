"""Stage-A per-term extraction and comparison (mgcv-parity engine, slice 1).

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

mgcv-native bases (``cr``/``ti``/``sz``) are not extracted here. That is slice 2's
job, paired with the first Python basis construction that needs a referent.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.experience_mgcv_conformance import DesignExport
from polaris_re.analytics.gam_term_spec import TermSpec
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "RTermPayload",
    "TermExtract",
    "TermExtractComparison",
    "compare_term_extract",
    "extract_raw_terms",
    "raw_term_specs",
]


class RTermPayload(TypedDict):
    """The keys read from one ``designs.<id>.terms.<label>`` entry of
    ``scripts/gam_term_extract.R``'s JSON output — the R-side schema
    :func:`compare_term_extract` reads, documented in the type rather than left as
    ``Any`` (CLAUDE.md §5)."""

    index_start: int
    index_end: int
    X: list[list[float]]
    S: list[list[list[float]]]
    rank: list[int]


_AGREEMENT_TOLERANCE = 1e-9
"""Stage A compares a shared design and shared penalties at fixed sp (RUNBOOK
level 1's regime) — the same regime ADR-189 amendment 1 verified to 5e-13 through the
fitter, so an exact-comparison tolerance is appropriate here too, not a fitted-value
tolerance. An order of magnitude looser than that measurement, matching Anchor 8:
derived from an existing verified quantity, not chosen to make this check green."""


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
        knots: Knot locations actually used, or ``None`` — always ``None`` for
            ``basis="raw"``, which has no knot recipe (:class:`TermSpec`'s own
            validation forbids supplying knots for it). Populated once slice 2 adds
            mgcv-native extraction.
    """

    label: str
    index_start: int
    index_end: int
    design: np.ndarray
    s: tuple[np.ndarray, ...]
    rank: tuple[int, ...]
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
            knots=None,
        )
    return result


@dataclass(frozen=True)
class TermExtractComparison:
    """One term's Stage-A verdict: index range, design block, every penalty, rank."""

    label: str
    index_range_agrees: bool
    max_abs_design_diff: float
    max_abs_s_diff: tuple[float, ...]
    rank_diff: tuple[int, ...]
    agrees: bool


def compare_term_extract(python: TermExtract, r_term: RTermPayload) -> TermExtractComparison:
    """Compare a Python :class:`TermExtract` against one term of the R-side JSON.

    ``r_term`` is a ``designs.<id>.terms.<label>`` entry from
    ``scripts/gam_term_extract.R``'s output — see :class:`RTermPayload` for the keys
    read.
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

    agrees = (
        index_range_agrees
        and max_abs_design_diff < _AGREEMENT_TOLERANCE
        and all(d < _AGREEMENT_TOLERANCE for d in max_abs_s_diff)
        and all(d == 0 for d in rank_diff)
    )
    return TermExtractComparison(
        label=python.label,
        index_range_agrees=index_range_agrees,
        max_abs_design_diff=max_abs_design_diff,
        max_abs_s_diff=max_abs_s_diff,
        rank_diff=rank_diff,
        agrees=agrees,
    )

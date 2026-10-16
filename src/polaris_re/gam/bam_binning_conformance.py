"""``bam(discrete=TRUE)``'s covariate discretisation, ported and compared — real-data
readiness epic Slice R3, Stage A (``docs/PLAN_gam_real_data_readiness.md`` §4, ADR-260
amendment 1).

**Claim sentence (ADR-193), written before the code.** *"Polaris
(:func:`compress_covariates` / :func:`discretise_frame`, a port of the rule read from
``mgcv`` 1.9.1's ``compress.df`` / ``discrete.mf`` source) discretises the covariate
columns of a formula from the formula string and the raw data columns; ``mgcv`` (the pinned
digest) discretises them through ``mgcv:::discrete.mf`` on the same formula and data;
compared on the number of unique covariate rows per term (``nr``), the discretised value
each data row is mapped to, and the partition of rows into discrete cells."*

**Provenance.** The three columns are INDEPENDENT: :func:`discretise_frame` takes the
formula string and the data columns only (its signature has no ``mgcv`` payload), and the
R probe is handed the same raw columns, never Polaris's index. The *cell labels* are NOT
compared: ``discrete.mf`` shuffles the unique rows with a seeded ``sample`` (seed 8547), so
its labels are an arbitrary permutation of ours; the **partition** they induce is what
``bam`` accumulates over, so that is what is compared.

**What the source says (mgcv 1.9.1; the pinned 1.9.4 is checked by the same probe in CI).**
For one covariate (``d = 1``) ``m = 1000``; two covariates jointly ``m = 100``; more,
``25``. If the covariate(s) have no more than ``m ** n_numeric * prod(n_factor_levels)``
unique rows, **nothing is binned** and the cells are the unique rows. Only above that are
numeric columns snapped to ``m`` evenly spaced points over their range. So for the ILEC
trial's integer ``attained_age`` / ``duration`` (well under 1000 unique values) the
discretisation is the *identity* and ``bam``'s difference from ``gam`` is the algorithm
(performance iteration on ``fREML``), not the binning (ADR-260 amendment 1).
"""

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam.formula import (
    ParametricCall,
    SmoothCall,
    TensorCall,
    parse_formula,
)

__all__ = [
    "ALGORITHM_CLAIM",
    "BINNING_CLAIM",
    "BinningCase",
    "BinningComparison",
    "CompressedTerm",
    "compare_binning_case",
    "compare_joint_case",
    "compress_covariates",
    "default_m",
    "discretise_frame",
]

BINNING_CLAIM = VerificationClaim(
    claim=(
        "Polaris (compress_covariates / discretise_frame, a port of mgcv 1.9.1's compress.df "
        "and discrete.mf) discretises the covariates of a formula from the formula string and "
        "the raw data columns; mgcv discretises them via mgcv:::discrete.mf on the same "
        "formula and data; compared on nr, the discretised value per row and the row "
        "partition."
    ),
    quantities=(
        ComparedQuantity(
            quantity="nr (unique covariate rows per term)",
            left_producer="polaris_re.gam.bam_binning_conformance.discretise_frame",
            right_producer="mgcv:::discrete.mf (via scripts/bam_binning_probe.R)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="discretised value per row",
            left_producer="polaris_re.gam.bam_binning_conformance.discretise_frame",
            right_producer="mgcv:::discrete.mf (via scripts/bam_binning_probe.R)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="row partition (cell membership)",
            left_producer="polaris_re.gam.bam_binning_conformance.discretise_frame",
            right_producer="mgcv:::discrete.mf (via scripts/bam_binning_probe.R)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)

ALGORITHM_CLAIM = VerificationClaim(
    claim=(
        "mgcv gam(method='REML') and mgcv bam(method='fREML', discrete=FALSE) and "
        "bam(method='fREML', discrete=TRUE) fit the same formula on the same cell with no "
        "covariate binned; compared on eta, edf_total and per-smooth edf. Polaris is not "
        "in this comparison: it measures the reference against itself."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta: gam vs bam(discrete=FALSE)",
            left_producer="mgcv::gam(method='REML')",
            right_producer="mgcv::bam(method='fREML', discrete=FALSE)",
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
        ComparedQuantity(
            quantity="eta: bam(discrete=FALSE) vs bam(discrete=TRUE)",
            left_producer="mgcv::bam(method='fREML', discrete=FALSE)",
            right_producer="mgcv::bam(method='fREML', discrete=TRUE)",
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
        ComparedQuantity(
            quantity="edf_total: gam vs bam(discrete=TRUE)",
            left_producer="mgcv::gam(method='REML')",
            right_producer="mgcv::bam(method='fREML', discrete=TRUE)",
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
    ),
)

_M_ONE_D = 1000
_M_TWO_D = 100
_M_MORE_D = 25


def default_m(n_columns: int, m: int | None = None) -> int:
    """``compress.df``'s per-dimension grid size.

    ``m = NULL``: 1000 / 100 / 25 for one / two / more columns. ``m`` supplied and more than
    one column: ``round(m ** (1 / d)) + 1`` (R's round is half-to-even, as ``np.rint``)."""
    if m is None:
        return _M_ONE_D if n_columns == 1 else _M_TWO_D if n_columns == 2 else _M_MORE_D
    if n_columns > 1:
        return int(np.rint(m ** (1.0 / n_columns))) + 1
    return m


@dataclass(frozen=True)
class CompressedTerm:
    """One ``compress.df`` call's result: the unique covariate rows and each data row's cell.

    ``values[name][index]`` is the discretised covariate for every data row. Factor columns
    are carried as integer codes (sorted-unique order); they are never binned. ``index`` is
    0-based. ``binned`` records whether the grid rule fired."""

    names: tuple[str, ...]
    values: dict[str, np.ndarray]
    index: np.ndarray
    binned: bool

    @property
    def nr(self) -> int:
        return int(next(iter(self.values.values())).shape[0])

    def row_values(self, name: str) -> np.ndarray:
        return self.values[name][self.index]


def _unique_rows(
    columns: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Unique rows (``np.unique`` lexicographic order) and each row's 0-based unique index."""
    stacked = np.column_stack(columns).astype(np.float64)
    uniq, inverse = np.unique(stacked, axis=0, return_inverse=True)
    return uniq, inverse.reshape(-1).astype(np.int64)


def compress_covariates(
    columns: dict[str, np.ndarray],
    factors: frozenset[str] = frozenset(),
    *,
    m: int | None = None,
) -> CompressedTerm:
    """Port of ``mgcv:::compress.df`` for one term's covariate columns.

    Args:
        columns: name to 1-d float array (numeric) or integer codes (factor), equal length.
        factors: names in ``columns`` that are factors (never binned; they multiply the
            threshold by their number of levels).
        m: ``bam``'s ``m`` argument (``None`` = the defaults).

    Raises:
        PolarisValidationError: empty input, ragged columns, or non-finite values.
    """
    if not columns:
        raise PolarisValidationError("compress_covariates: no covariate columns given.")
    names = tuple(columns)
    arrays = {k: np.asarray(v, dtype=np.float64) for k, v in columns.items()}
    n = next(iter(arrays.values())).shape[0]
    if any(a.shape != (n,) for a in arrays.values()):
        raise PolarisValidationError("compress_covariates: columns must be 1-d of equal length.")
    if any(not np.all(np.isfinite(a)) for a in arrays.values()):
        raise PolarisValidationError(
            "compress_covariates: non-finite covariate values (NaN/Inf) are not discretised."
        )
    d = len(names)
    m_eff = default_m(d, m)
    factor_levels = 1
    numeric = [k for k in names if k not in factors]
    for k in names:
        if k in factors:
            factor_levels *= int(np.unique(arrays[k]).shape[0])
    threshold = (m_eff ** len(numeric)) * factor_levels

    uniq, _ = _unique_rows([arrays[k] for k in names])
    binned = False
    if uniq.shape[0] > threshold:
        binned = True
        for k in numeric:
            lo, hi = float(arrays[k].min()), float(arrays[k].max())
            # R: xu <- seq(xl[1], xl[2], length = m); dx <- xu[2] - xu[1]
            by = (hi - lo) / (m_eff - 1)
            grid = lo + np.arange(m_eff, dtype=np.float64) * by
            grid[-1] = hi
            dx = grid[1] - grid[0]
            kx = np.rint((arrays[k] - lo) / dx).astype(np.int64)
            arrays[k] = grid[kx]
        uniq, _ = _unique_rows([arrays[k] for k in names])

    if uniq.shape[0] == n:
        # R returns the (possibly binned) data itself with index 1:n.
        return CompressedTerm(
            names=names,
            values={k: arrays[k] for k in names},
            index=np.arange(n, dtype=np.int64),
            binned=binned,
        )
    uniq, inverse = _unique_rows([arrays[k] for k in names])
    return CompressedTerm(
        names=names,
        values={k: uniq[:, i] for i, k in enumerate(names)},
        index=inverse,
        binned=binned,
    )


def _is_factor(series: pl.Series) -> bool:
    return series.dtype in (pl.String, pl.Categorical, pl.Enum, pl.Boolean)


def _codes(series: pl.Series) -> np.ndarray:
    if series.dtype == pl.Boolean:
        return series.cast(pl.Int8).to_numpy().astype(np.float64)
    labels = series.cast(pl.String).to_list()
    levels = {lab: i for i, lab in enumerate(sorted(set(labels)))}
    return np.array([levels[lab] for lab in labels], dtype=np.float64)


def _term_groups(formula: str) -> tuple[list[tuple[str, ...]], list[str]]:
    """The covariate groups ``discrete.mf`` compresses, in its order, and the parametric names.

    A smooth contributes its ``by`` variable (first) then its covariate; a ``ti`` its margins
    one at a time (``ti`` margins are separate 1-d terms). Parametric variables follow."""
    parsed = parse_formula(formula)
    groups: list[tuple[str, ...]] = []
    parametric: list[str] = []
    for term in parsed.terms:
        if isinstance(term, SmoothCall):
            if term.by is not None:
                groups.append((term.by,))
            groups.append((term.variable,))
        elif isinstance(term, TensorCall):
            groups.extend((v,) for v in term.variables)
        elif isinstance(term, ParametricCall):
            parametric.extend(term.variables)
    return groups, parametric


def discretise_frame(
    formula: str, data: pl.DataFrame, *, m: int | None = None
) -> dict[str, CompressedTerm]:
    """Discretise every covariate of ``formula`` as ``mgcv:::discrete.mf`` does.

    Returns variable name to its :class:`CompressedTerm`. A variable already compressed by an
    earlier term is reused (``check.term``); parametric variables not in any smooth follow,
    each compressed on its own. Only single-variable terms occur in the verified formula
    subset (``ti`` margins are separate), so multi-column groups are exercised through
    :func:`compress_covariates` directly.

    Raises:
        PolarisValidationError: a name absent from ``data``, or an unparseable formula."""
    groups, parametric = _term_groups(formula)
    out: dict[str, CompressedTerm] = {}
    for group in [*groups, *((v,) for v in parametric)]:
        (name,) = group
        if name in out:
            continue
        if name not in data.columns:
            raise PolarisValidationError(f"discretise_frame: column {name!r} is not in the data.")
        series = data[name]
        fac = _is_factor(series)
        col = _codes(series) if fac else series.cast(pl.Float64).to_numpy()
        out[name] = compress_covariates({name: col}, frozenset({name}) if fac else frozenset(), m=m)
    return out


@dataclass(frozen=True)
class BinningCase:
    """The recipe the R probe was handed: a formula string and the raw columns."""

    name: str
    formula: str
    data: pl.DataFrame
    m: int | None = None


@dataclass
class BinningComparison:
    """Per-variable comparison of the port against ``discrete.mf``."""

    case: str
    variable: str
    nr_polaris: int
    nr_mgcv: int
    binned_polaris: bool
    max_value_diff: float
    partition_equal: bool
    notes: list[str] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return (
            self.nr_polaris == self.nr_mgcv and self.partition_equal and self.max_value_diff == 0.0
        )


def _same_partition(a: np.ndarray, b: np.ndarray) -> bool:
    """True when two labelings induce the same partition of rows (labels may differ)."""
    pairs = np.unique(np.column_stack([a, b]), axis=0)
    return pairs.shape[0] == np.unique(a).shape[0] == np.unique(b).shape[0]


def compare_binning_case(
    case: BinningCase,
    mgcv_nr: dict[str, int],
    mgcv_values: dict[str, list[float]],
    mgcv_index: dict[str, list[int]],
    *,
    value_rtol: float = 1e-12,
) -> list[BinningComparison]:
    """Compare :func:`discretise_frame` with ``mgcv``'s per-variable payload.

    ``mgcv_values`` holds the discretised value per data row (factors as integer codes in
    sorted order, as :func:`_codes` produces). The value tolerance is a *derived* relative
    1e-12: both sides compute ``lo + i * by`` on IEEE doubles, so a difference above a few ulp
    would be a different rule, not rounding. It is reported, not widened."""
    mine = discretise_frame(case.formula, case.data, m=case.m)
    rows: list[BinningComparison] = []
    for var, term in mine.items():
        if var not in mgcv_nr:
            rows.append(
                BinningComparison(
                    case.name, var, term.nr, -1, term.binned, float("nan"), False, ["not in mgcv"]
                )
            )
            continue
        theirs = np.asarray(mgcv_values[var], dtype=np.float64)
        mine_v = term.row_values(var)
        scale = max(float(np.max(np.abs(theirs))), 1.0)
        diff = float(np.max(np.abs(mine_v - theirs))) / scale
        diff = 0.0 if diff <= value_rtol else diff
        rows.append(
            BinningComparison(
                case=case.name,
                variable=var,
                nr_polaris=term.nr,
                nr_mgcv=int(mgcv_nr[var]),
                binned_polaris=term.binned,
                max_value_diff=diff,
                partition_equal=_same_partition(term.index, np.asarray(mgcv_index[var])),
            )
        )
    return rows


def compare_joint_case(
    name: str,
    columns: dict[str, np.ndarray],
    factors: frozenset[str],
    m: int | None,
    mgcv_nr: int,
    mgcv_values: dict[str, list[float]],
    mgcv_index: list[int],
    *,
    value_rtol: float = 1e-12,
) -> BinningComparison:
    """Compare :func:`compress_covariates` on a multi-column term with ``mgcv:::compress.df``.

    ``columns`` holds raw numerics and factor *codes* (sorted-unique order). One row is
    returned for the whole term; ``max_value_diff`` is the worst over its columns."""
    term = compress_covariates(columns, factors, m=m)
    worst = 0.0
    for k in term.names:
        theirs = np.asarray(mgcv_values[k], dtype=np.float64)
        scale = max(float(np.max(np.abs(theirs))), 1.0)
        worst = max(worst, float(np.max(np.abs(term.row_values(k) - theirs))) / scale)
    worst = 0.0 if worst <= value_rtol else worst
    return BinningComparison(
        case=name,
        variable="+".join(term.names),
        nr_polaris=term.nr,
        nr_mgcv=int(mgcv_nr),
        binned_polaris=term.binned,
        max_value_diff=worst,
        partition_equal=_same_partition(term.index, np.asarray(mgcv_index)),
    )

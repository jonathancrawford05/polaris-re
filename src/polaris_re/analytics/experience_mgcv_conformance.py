"""
``mgcv`` conformance for the penalized tensor MI surface — exchange, reference, comparator.

Slice 5 of ``docs/PLAN_penalized_mi_surface.md``. Three quantities the penalized
estimator now reports are **adopted from ``mgcv`` and unverified** (PLAN Anchor 8):
``tr(F)`` as the per-term EDF (Anchor 4), the Kass-Steffey unconditional covariance
(ADR-188 decision 2), and Wood's ``gamma`` (ADR-188 decision 3). One R run settles all
three, and this module builds every artefact that run needs.

Why the comparison is exact — *correct by construction*
-------------------------------------------------------
ADR-151's unpenalized oracle works because the Poisson log-likelihood over a **shared**
design is strictly concave, so its maximiser is unique and any conformant solver must
return it. **That argument extends to the penalized case:** adding a positive
semi-definite penalty keeps the objective strictly concave, so at fixed λ over a shared
``(X, S_age, S_year)`` the penalized MLE is unique too.

So this module ships **our** design and **our** penalties to ``mgcv`` through
``paraPen`` rather than asking it to build a ``te(attained_age, calendar_year)``. That
choice is the whole point: matching ``te()`` would compare two bases, two knot
placements and two identifiability constraints, and a disagreement would be
uninterpretable. With the design and the penalties supplied, **every disagreement is
our arithmetic.**

The property is checkable **without R present**, which is what keeps this slice's
correctness claim runnable in CI: :func:`penalized_score_infinity_norm` verifies that
the exported coefficients satisfy ``Xᵀ(y - μ) - Sβ = 0``, the stationarity condition of
the penalized Poisson log-likelihood. A near-zero norm proves the exported coefficients
sit at the unique penalized maximiser of the exported problem, and strict concavity then
pins what any conformant R solver must return.

The governing workflow decision — a COMMITTED GOLDEN, not a live oracle
-----------------------------------------------------------------------
The expensive resource is the **round trip**, not the R compute: each one costs a
session boundary. The R side is a pure function of the exchange file, so once the
maintainer runs it the reference is committed and the implementer iterates entirely
offline against it. A second run is needed only if the design or the penalties change
(which changes the exchange), or to add cells.

For the **synthetic** case there is no licensing reason to withhold the reference — it
is generated from a pinned seed — so exchange *and* reference are both committed. HMD
and ILEC are unchanged: the exchange is cell-grain experience, stays in the
maintainer's working directory, and only the comparison report comes back
(``DATA_LICENSING.md`` §1, Design Anchor 6).

**The guard that matters:** :func:`compare_reference` recomputes the exchange hash from
the files on disk and refuses a reference whose recorded hash differs. Iterating
against a stale reference and declaring parity with a file R never saw is a silent,
confident wrong answer of exactly the class this epic keeps catching.

What level 4 can and cannot settle
----------------------------------
``vcov(m, unconditional = TRUE)`` exists in ``mgcv`` only when the smoothing parameters
were **estimated** — there is no ``Vc`` at fixed ``sp``. But at free ``sp`` the two
implementations select *different* λ (ours from a 0.25-decade grid, R's continuously),
so the two covariance matrices differ for a reason that is not the correction's
arithmetic. Level 4 is therefore two metrics rather than one:

1. the conditional ``Vb`` at **fixed** λ, where the comparison is exact and tight; and
2. the **inflation factor** ``mean(diag(Vc)) / mean(diag(Vb))`` at free λ, which is the
   most scale-free summary of the correction that survives a λ disagreement.

This is a stated limitation, not a silent one: the second metric cannot distinguish a
wrong Kass-Steffey Jacobian from a λ disagreement on its own, and reading it requires
level 2 to have passed first.

No wall clock anywhere — the synthetic case is a pinned seed and two exports produce
byte-identical files (ADR-074).

ADR-189.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.analytics.experience_gam_penalized import (
    LAMBDA_LOG10_BOUNDS,
    PenalizedTensorMIModel,
    fit_reml,
    reml_score,
    smoothing_uncertainty,
)
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

__all__ = [
    "CONFORMANCE_CELLS",
    "DESIGNS",
    "FLOAT_FORMAT",
    "LEVEL_METRICS",
    "REAL_DATA_CASES",
    "SCHEMA_VERSION",
    "SYNTHETIC_CASE",
    "SYNTHETIC_SEED",
    "CellComparison",
    "ConformanceCell",
    "ConformanceComparison",
    "DesignExport",
    "DesignSpec",
    "ExchangeBundle",
    "MetricCheck",
    "MetricSpec",
    "PythonCellResult",
    "build_exchange",
    "compare_reference",
    "exchange_hash",
    "penalized_score_infinity_norm",
    "python_reference",
    "read_exchange",
    "render_comparison_markdown",
    "rscript_mgcv_available",
    "synthetic_cells",
    "write_exchange",
    "write_python_reference",
]

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

SCHEMA_VERSION = 1
"""Bumped when the manifest or reference layout changes shape. The comparator refuses a
version it does not know rather than reading fields that moved."""

FLOAT_FORMAT = "%.17g"
"""17 significant digits round-trips an IEEE-754 double exactly, so the design R fits is
bit-for-bit the design Python fit. Anything shorter would make every level-1
disagreement partly a formatting artefact."""

SYNTHETIC_CASE = "synthetic"
REAL_DATA_CASES = ("hmd-usa", "ilec-banded")
"""Cases whose exchange is cell-grain experience: local-only, never committed
(``DATA_LICENSING.md`` §1). Only the comparison report comes back into the repo."""

SYNTHETIC_SEED = 20120101
"""Pinned — never the wall clock (ADR-074). Two exports produce identical files."""

# --- The synthetic case: the diligence epic's ILEC-shaped fixture, narrowed ----------
#
# The age RANGE is narrowed (45-85 rather than the coverage study's 25-95) so the
# committed exchange stays a few hundred KB. The age STEP and the per-cell exposure are
# the fixture's own, and narrowing the range rather than coarsening the step is what
# keeps lambda identified: **measured**, at a 2-year age step both penalties saturate at
# the search bound (1e8, 1e8) and `edf_total` lands on exactly 4.000 — the dimension of
# the bilinear null space the two second-difference penalties share. Level 2 would then
# be comparing a bounded grid against an unbounded optimiser on a problem where the data
# identify neither smoothing parameter, which is the degenerate-fixture trap this epic
# has already walked into three times (ADR-186, ADR-187, ADR-188).
#
# The calendar margin is untouched at ILEC's eight years: it is the margin every finding
# in this epic is about, and the one Anchor 5 says cannot support a large `k`.
_AGES: np.ndarray = np.arange(45, 86, dtype=np.int64)
_YEARS: np.ndarray = np.arange(2012, 2020, dtype=np.int64)
_EXPOSURE = 6.0e4


def _q_base(age: float) -> float:
    """The diligence epic's static base rate — reused, not re-invented."""
    return 0.004 * float(np.exp(0.08 * (age - 45.0)))


def _mi(age: float, year: int) -> float:
    """Quadratic in **both** margins — ADR-188's corrected fixture, and deliberately so.

    A truth that is flat (or merely linear) in age lies **inside** the second-difference
    penalty's null space along that margin, so λ_age costs nothing to saturate and the
    age penalty is unidentifiable. That trap bit this epic three times (ADR-186 with an
    unrepresentable truth, ADR-187 by design, ADR-188's first age-varying fixture with a
    linear gradient). A conformance case built on it would compare two implementations
    on a problem where one of the two smoothing parameters is not determined by the
    data — so level 2 would be measuring grid noise against optimiser noise.

    Quadratic in both margins is outside both null spaces and inside both bases.
    """
    return 0.010 + 0.008 * ((age - 60.0) / 35.0) ** 2 + 0.006 * ((year - 2015.5) / 3.5) ** 2


def synthetic_cells(*, with_factor: bool = False, seed: int = SYNTHETIC_SEED) -> pl.DataFrame:
    """Grouped count-basis cells with Poisson deaths under a pinned seed.

    Args:
        with_factor: Add a ``sex`` column with a level-specific mortality multiplier,
            so the design carries a factor block and the ``tr(F)`` additivity identity
            (Anchor 4) is non-trivial rather than true for free.
        seed:        Pinned RNG seed for the Poisson draw (ADR-074).
    """
    rng = np.random.default_rng(seed)
    strata: tuple[tuple[str, float], ...] = (
        (("M", 1.15), ("F", 0.85)) if with_factor else (("", 1.0),)
    )
    rows: list[tuple[int, int, str, float, float, float]] = []
    for age in _AGES:
        q0 = _q_base(float(age))
        for sex, multiplier in strata:
            actual = q0 * multiplier
            for year in _YEARS:
                if int(year) > int(_YEARS.min()):
                    actual *= 1.0 - _mi(float(age), int(year))
                rows.append(
                    (
                        int(age),
                        int(year),
                        sex,
                        q0,
                        _EXPOSURE,
                        float(rng.poisson(_EXPOSURE * actual)),
                    )
                )
    frame = pl.DataFrame(
        rows,
        schema=[
            "attained_age",
            "calendar_year",
            "sex",
            "q_base",
            "central_exposure",
            "death_count",
        ],
        orient="row",
    )
    return frame if with_factor else frame.drop("sex")


# --- The case matrix ----------------------------------------------------------------


@dataclass(frozen=True)
class DesignSpec:
    """One ``(k_age, k_year, factor-block?)`` design shared by several cells.

    Designs are separated from cells because a design is what costs bytes in the
    exchange and a cell is what costs seconds inside one R invocation. Extra cells over
    a shared design are nearly free; extra designs are not.
    """

    design_id: str
    k_age: int
    k_year: int
    with_factor: bool


DESIGNS: tuple[DesignSpec, ...] = (
    DesignSpec("d1", 7, 6, False),
    DesignSpec("d2", 7, 6, True),
    DesignSpec("d3", 10, 5, False),
)
"""Three designs, two ``(k_age, k_year)`` pairs, with and without a factor block.

``d1`` matches the coverage study's ``k_age=7, k_year=6`` so a disagreement here is
comparable with ADR-188's numbers. ``d3`` moves **both** margins at once and in opposite
directions — a bigger age basis against a smaller calendar one — because a second pair
that only widened one margin would leave a column-ordering error in the row-wise
Kronecker product undetected."""


@dataclass(frozen=True)
class ConformanceCell:
    """One R fit: a design, a smoothing-parameter regime, and the levels it settles.

    ``lambda_age is None`` means **free** ``sp`` — R estimates the smoothing parameters
    and so do we, which is what levels 2 and 5 compare. A fixed pair pins both sides to
    the identical penalty, which is what makes levels 1, 3 and the tight half of 4 exact
    rather than approximate.
    """

    name: str
    design_id: str
    levels: tuple[int, ...]
    lambda_age: float | None
    lambda_year: float | None
    gamma: float = 1.0

    @property
    def free_sp(self) -> bool:
        """Does R estimate the smoothing parameters for this cell?"""
        return self.lambda_age is None


CONFORMANCE_CELLS: tuple[ConformanceCell, ...] = (
    ConformanceCell("l1-interior", "d1", (1, 3, 4), 10.0, 100.0),
    ConformanceCell("l1-age-saturated", "d1", (1, 3), 1.0e6, 100.0),
    ConformanceCell("l1-year-saturated", "d1", (1, 3), 10.0, 1.0e6),
    ConformanceCell("l1-scale-convention", "d1", (1,), 1.0e3, 1.0),
    ConformanceCell("l1-interior-factors", "d2", (1, 3), 10.0, 100.0),
    ConformanceCell("l1-interior-kb", "d3", (1, 3), 10.0, 100.0),
    ConformanceCell("l2-free-sp", "d1", (2, 4), None, None),
    ConformanceCell("l2-free-sp-factors", "d2", (2, 4), None, None),
    ConformanceCell("l2-free-sp-kb", "d3", (2, 4), None, None),
    ConformanceCell("l5-gamma", "d1", (5,), None, None, gamma=1.4),
)
"""Ten cells over three designs — a matrix, not a case.

**A single cell can agree by accident.** ``l1-scale-convention`` exists for one such
accident in particular: the PR #190 review flagged that ``log|XᵀWX + S|`` is evaluated
at the **unscaled** penalty, which fixes a convention for λ relative to φ. Two λ of
similar magnitude would hide a convention error; ``(1e3, 1)`` is three decades apart in
opposite directions and exposes it. The two saturated corners are there because a
penalty-dominated normal equation is where conditioning bites (ADR-185: coefficients
rattle at round-off in exactly those directions while the deviance is settled)."""

_DESIGN_BY_ID: dict[str, DesignSpec] = {d.design_id: d for d in DESIGNS}


# --- Metrics and the tolerances they are judged against ------------------------------


@dataclass(frozen=True)
class MetricSpec:
    """One comparable number, the level it settles, and the tolerance it must meet."""

    metric: str
    level: int
    tolerance: float
    rationale: str


LEVEL_METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "max_abs_eta_diff",
        1,
        1.0e-9,
        "The fitted linear predictor is the identified quantity: it is invariant to the "
        "coefficient rattle a saturating penalty leaves in its own null space, so it "
        "carries the tightest tolerance here. Anything above round-off on 1e2-scale "
        "counts is a real difference in the fit.",
    ),
    MetricSpec(
        "max_abs_coef_diff",
        1,
        1.0e-6,
        "Element-wise on the coefficients, as PLAN slice 5 specifies. Looser than eta "
        "on purpose: at a saturating lambda the penalised directions are flat, so both "
        "solvers stop at slightly different points in a subspace the fit cannot see "
        "(ADR-185 — IRLS converges on the deviance for exactly this reason).",
    ),
    MetricSpec(
        "abs_edf_total_diff",
        3,
        1.0e-6,
        "At FIXED lambda, tr(F) is pure linear algebra over a shared (X, S) — no "
        "selection, no optimiser. This is the tolerance that turns Anchor 4's tr(F) "
        "from adopted into verified or refuted.",
    ),
    MetricSpec(
        "abs_edf_tensor_diff",
        3,
        1.0e-6,
        "Per-block: our edf_tensor against the sum of mgcv's per-coefficient edf over "
        "the tensor columns. Checks the SPLIT as well as the total, which is the half "
        "Anchor 4's amendment is actually about.",
    ),
    MetricSpec(
        "abs_edf_factors_diff",
        3,
        1.0e-6,
        "The other block, so the additivity Anchor 4 promises is checked against an "
        "independent implementation rather than against our own arithmetic.",
    ),
    MetricSpec(
        "max_rel_vcov_diff",
        4,
        1.0e-6,
        "Conditional Vb at FIXED lambda, relative to the largest entry of our own. The "
        "exact half of level 4 — same penalty on both sides, so a disagreement is the "
        "inverse or the scale convention and nothing else.",
    ),
    MetricSpec(
        "max_abs_log10_sp_diff",
        2,
        0.5,
        "Our selector sweeps a 0.25-decade grid, so it cannot land closer than 0.125 "
        "decades to a continuous optimum by construction; and the REML profile is "
        "SHALLOW (ADR-187 amendment 2: 3.85 units across 5.5 decades). 0.5 decades is "
        "the grid plus slack for a shallow profile. PROVISIONAL until the first R run.",
    ),
    MetricSpec(
        "abs_edf_total_diff_free_sp",
        2,
        1.0,
        "The quantity a reader actually consumes. Deliberately judged separately from "
        "the sp agreement above, because a shallow profile moves lambda a long way for "
        "very little edf — so edf is the tighter statement about whether the two "
        "selections MEAN the same thing. PROVISIONAL until the first R run.",
    ),
    MetricSpec(
        "rel_unconditional_inflation_diff",
        4,
        0.25,
        "mgcv forms Vc only when sp was ESTIMATED, so this metric is unavoidably "
        "measured at a lambda the two sides selected independently. The inflation "
        "factor mean(diag(Vc))/mean(diag(Vb)) is the most scale-free summary that "
        "survives that. Read it ONLY after level 2 passes; on its own it cannot "
        "separate a wrong Jacobian from a lambda disagreement.",
    ),
    MetricSpec(
        "max_abs_log10_sp_diff_gamma",
        5,
        0.5,
        "Level 2's metric under gamma=1.4. Same grid, same shallow profile, same "
        "tolerance — what is being checked is that gamma enters the criterion the way "
        "mgcv's documentation says (as the scale in a RE/ML criterion), not that the "
        "search got sharper.",
    ),
    MetricSpec(
        "abs_edf_total_diff_gamma",
        5,
        1.0,
        "The edf gamma is supposed to move. ADR-188 measured edf_tensor 5.836 -> 4.908 "
        "over gamma 1.0 -> 1.4 on the standard fixture; this checks the destination "
        "against mgcv rather than only the direction against ourselves.",
    ),
)


# --- Building the exchange -----------------------------------------------------------


@dataclass(frozen=True)
class DesignExport:
    """The exact ``(X, y, offset, S_age, S_year)`` a design contributes to the exchange.

    The penalties are **padded to the full design width**, matching what
    :meth:`PenalizedTensorMIModel.fit` assembles, because ``mgcv``'s ``paraPen`` wants
    one matrix per penalty at the term's own dimension. The padding is what tells R that
    the factor columns are unpenalised, and it must be exported rather than left for R
    to infer.
    """

    spec: DesignSpec
    design: np.ndarray
    deaths: np.ndarray
    offset: np.ndarray
    s_age: np.ndarray
    s_year: np.ndarray
    n_tensor: int
    factors: tuple[str, ...]

    @property
    def n_cells(self) -> int:
        return int(self.design.shape[0])

    @property
    def n_coef(self) -> int:
        return int(self.design.shape[1])


@dataclass(frozen=True)
class ExchangeBundle:
    """Everything R reads: the designs, and the cells to fit over them."""

    case: str
    seed: int
    designs: dict[str, DesignExport]
    cells: tuple[ConformanceCell, ...]


def _model(spec: DesignSpec, cells: pl.DataFrame, **overrides: object) -> PenalizedTensorMIModel:
    return PenalizedTensorMIModel(cells, k_age=spec.k_age, k_year=spec.k_year, **overrides)  # type: ignore[arg-type]


def _pad(block: np.ndarray, n_coef: int) -> np.ndarray:
    """Embed an ``(n_tensor, n_tensor)`` penalty in an ``(n_coef, n_coef)`` zero matrix."""
    padded = np.zeros((n_coef, n_coef), dtype=np.float64)
    padded[: block.shape[0], : block.shape[1]] = block
    return padded


def build_design(spec: DesignSpec, cells: pl.DataFrame) -> DesignExport:
    """Assemble one design through the shipped fitter's own public design context.

    The design is **extracted from a fit, never re-derived** — the same discipline
    ADR-151 applied, and for the same reason: a conformance run against a design the
    model did not actually fit measures the exporter.
    """
    model = _model(spec, cells, lambda_age=0.0, lambda_year=0.0)
    fit = model.fit()
    context = model.design_context
    if context is None:  # pragma: no cover - fit() always sets it
        raise PolarisComputationError("fit() did not record its design context.")
    n_coef = int(context.design.shape[1])
    return DesignExport(
        spec=spec,
        design=np.asarray(context.design, dtype=np.float64),
        deaths=np.asarray(context.deaths, dtype=np.float64),
        offset=np.asarray(context.offset, dtype=np.float64),
        s_age=_pad(context.s_age, n_coef),
        s_year=_pad(context.s_year, n_coef),
        n_tensor=int(context.n_tensor),
        # From the FIT, not re-derived from the frame's columns: the fit is what decided
        # which factors entered the design, and a second opinion on that question is a
        # second place for the block boundary to be wrong. R cuts `m$edf` at `n_tensor`,
        # so the boundary is load-bearing on both sides.
        factors=fit.factors,
    )


def build_exchange(
    case: str = SYNTHETIC_CASE,
    *,
    cells_for: Callable[[DesignSpec], pl.DataFrame] | None = None,
    seed: int = SYNTHETIC_SEED,
    designs: tuple[DesignSpec, ...] = DESIGNS,
    conformance_cells: tuple[ConformanceCell, ...] = CONFORMANCE_CELLS,
) -> ExchangeBundle:
    """Build every design the case matrix references.

    Args:
        case:  Label carried into the manifest and the report. ``"synthetic"`` uses the
               pinned generator; a real-data label must supply ``cells_for``.
        cells_for: Supplies the grouped cells for a design — the hook the real-data
               cases use, since a design that wants a factor block needs a frame that
               has one. Defaults to :func:`synthetic_cells`.
        seed:  Recorded in the manifest so a reader can regenerate the synthetic case.
        designs / conformance_cells: Overridable for tests; the defaults are the
               committed matrix.

    Raises:
        PolarisValidationError: if a cell names a design that is not being built — the
            failure R would otherwise hit halfway through a batch run.
    """
    known = {d.design_id for d in designs}
    unknown = sorted({c.design_id for c in conformance_cells} - known)
    if unknown:
        raise PolarisValidationError(
            f"Conformance cells reference design(s) {unknown} that this exchange does "
            f"not build; available: {sorted(known)}."
        )
    build_cells = cells_for or (
        lambda spec: synthetic_cells(with_factor=spec.with_factor, seed=seed)
    )
    return ExchangeBundle(
        case=case,
        seed=seed,
        designs={d.design_id: build_design(d, build_cells(d)) for d in designs},
        cells=conformance_cells,
    )


# --- Writing and reading the exchange ------------------------------------------------

_MANIFEST = "manifest.json"
_HASH_FILE = "exchange.sha256"


def _design_files(design_id: str) -> dict[str, str]:
    return {
        "data": f"design_{design_id}.tsv",
        "penalty_age": f"penalty_{design_id}_age.tsv",
        "penalty_year": f"penalty_{design_id}_year.tsv",
    }


def _write_tsv(path: Path, matrix: np.ndarray, columns: list[str]) -> None:
    """Plain TSV with a one-line header — ``read.table`` and nothing else.

    Not ``.npz``: R cannot read it without ``reticulate`` or ``RcppCNPy``, and an
    earlier revision of the plan specified exactly that. Requiring an extra R package
    would put a maintainer's round trip behind a package install.
    """
    np.savetxt(
        path,
        np.atleast_2d(matrix),
        fmt=FLOAT_FORMAT,
        delimiter="\t",
        header="\t".join(columns),
        comments="",
        newline="\n",
    )


def write_exchange(bundle: ExchangeBundle, directory: str | Path) -> str:
    """Write the exchange and return its SHA-256.

    Writes ``manifest.json``, one TSV per design carrying ``y``/``offset``/``x*``, two
    penalty TSVs per design, and ``exchange.sha256``. The hash covers the manifest and
    every TSV — never the Python reference, which is an *output* of the same inputs and
    would make the hash unable to certify what R read.
    """
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, JsonValue] = {
        "schema_version": SCHEMA_VERSION,
        "case": bundle.case,
        "seed": bundle.seed,
        "float_format": FLOAT_FORMAT,
        "generator": "polaris_re.analytics.experience_mgcv_conformance",
        "r_requirements": {
            # scalePenalty=FALSE is load-bearing, not hygiene: mgcv rescales
            # caller-supplied paraPen penalties by default, which silently redefines
            # what `sp` multiplies and would make every fixed-lambda cell disagree for
            # a reason that is not our arithmetic.
            "gam_control_scalePenalty": False,
            "method": "REML",
            "family": "poisson",
            "offset_is_supplied": True,
        },
        "designs": {},
        "cells": [],
    }
    designs_meta: dict[str, JsonValue] = {}
    for design_id, export in bundle.designs.items():
        files = _design_files(design_id)
        columns = ["y", "offset"] + [f"x{i + 1}" for i in range(export.n_coef)]
        _write_tsv(
            out / files["data"],
            np.column_stack([export.deaths, export.offset, export.design]),
            columns,
        )
        penalty_columns = [f"c{i + 1}" for i in range(export.n_coef)]
        _write_tsv(out / files["penalty_age"], export.s_age, penalty_columns)
        _write_tsv(out / files["penalty_year"], export.s_year, penalty_columns)
        designs_meta[design_id] = {
            "k_age": export.spec.k_age,
            "k_year": export.spec.k_year,
            "with_factor": export.spec.with_factor,
            "n_cells": export.n_cells,
            "n_coef": export.n_coef,
            "n_tensor": export.n_tensor,
            "factors": list(export.factors),
            "files": dict(files),
        }
    manifest["designs"] = designs_meta
    manifest["cells"] = [
        {
            "name": cell.name,
            "design": cell.design_id,
            "levels": list(cell.levels),
            "free_sp": cell.free_sp,
            "lambda_age": cell.lambda_age,
            "lambda_year": cell.lambda_year,
            "gamma": cell.gamma,
        }
        for cell in bundle.cells
    ]
    (out / _MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    digest = exchange_hash(out)
    (out / _HASH_FILE).write_text(digest + "\n")
    return digest


def exchange_hash(directory: str | Path) -> str:
    """SHA-256 over the manifest and every TSV, in sorted filename order.

    Deliberately excludes ``exchange.sha256`` (it holds the answer) and the Python
    reference (it is derived from the inputs, not one of them). The digest names each
    file before hashing its bytes, so moving content between files changes it.
    """
    root = Path(directory)
    names = sorted(
        [_MANIFEST] + [p.name for p in root.glob("*.tsv")],
    )
    digest = hashlib.sha256()
    for name in names:
        path = root / name
        if not path.exists():
            raise PolarisValidationError(f"Exchange directory {root} is missing {name}.")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def read_exchange(directory: str | Path) -> ExchangeBundle:
    """Read an exchange back, for the round-trip guarantee and for the comparator.

    The comparator needs the design to form ``eta`` from either side's coefficients,
    which is the level-1 metric that does not depend on the penalty's null space.
    """
    root = Path(directory)
    manifest = json.loads((root / _MANIFEST).read_text())
    version = int(manifest["schema_version"])
    if version != SCHEMA_VERSION:
        raise PolarisValidationError(
            f"Exchange {root} is schema version {version}; this build reads "
            f"{SCHEMA_VERSION}. Re-export rather than reading fields that may have moved."
        )
    designs: dict[str, DesignExport] = {}
    for design_id, meta in manifest["designs"].items():
        files = meta["files"]
        table = np.loadtxt(root / files["data"], delimiter="\t", skiprows=1, ndmin=2)
        designs[design_id] = DesignExport(
            spec=DesignSpec(
                design_id, int(meta["k_age"]), int(meta["k_year"]), bool(meta["with_factor"])
            ),
            design=np.ascontiguousarray(table[:, 2:], dtype=np.float64),
            deaths=np.ascontiguousarray(table[:, 0], dtype=np.float64),
            offset=np.ascontiguousarray(table[:, 1], dtype=np.float64),
            s_age=np.loadtxt(root / files["penalty_age"], delimiter="\t", skiprows=1, ndmin=2),
            s_year=np.loadtxt(root / files["penalty_year"], delimiter="\t", skiprows=1, ndmin=2),
            n_tensor=int(meta["n_tensor"]),
            factors=tuple(str(f) for f in meta["factors"]),
        )
    cells = tuple(
        ConformanceCell(
            name=str(c["name"]),
            design_id=str(c["design"]),
            levels=tuple(int(x) for x in c["levels"]),
            lambda_age=None if c["lambda_age"] is None else float(c["lambda_age"]),
            lambda_year=None if c["lambda_year"] is None else float(c["lambda_year"]),
            gamma=float(c["gamma"]),
        )
        for c in manifest["cells"]
    )
    return ExchangeBundle(
        case=str(manifest["case"]), seed=int(manifest["seed"]), designs=designs, cells=cells
    )


# --- The Python side ----------------------------------------------------------------


def penalized_score_infinity_norm(
    design: np.ndarray,
    deaths: np.ndarray,
    offset: np.ndarray,
    coef: np.ndarray,
    penalty: np.ndarray,
) -> float:
    """``||Xᵀ(y - μ) - Sβ||∞`` at the fitted coefficients — the R-free guarantee.

    For a penalized Poisson GLM with a log link and offset, ``μ = exp(Xβ + offset)`` and
    the penalized log-likelihood's gradient is ``Xᵀ(y - μ) - Sβ``. It vanishes at the
    maximiser, and the maximiser is **unique** because a PSD penalty added to a strictly
    concave log-likelihood is still strictly concave. So a near-zero norm proves the
    exported coefficients are the ones any conformant solver must return, which is why
    this slice's central correctness claim is testable in CI with no R present.

    This is ADR-151's :func:`poisson_score_infinity_norm` extended by the ``- Sβ`` term;
    at ``S = 0`` the two coincide exactly.
    """
    eta = np.asarray(design, dtype=np.float64) @ coef + np.asarray(offset, dtype=np.float64)
    mu = np.exp(np.clip(eta, -700.0, 700.0))
    gradient = design.T @ (np.asarray(deaths, dtype=np.float64) - mu) - penalty @ coef
    return float(np.max(np.abs(gradient)))


@dataclass(frozen=True)
class PythonCellResult:
    """Our answer for one conformance cell — every intermediate R will be asked for.

    ``vcov_unscaled`` is ``(XᵀWX + S)⁻¹`` **without** the quasi-Poisson dispersion, and
    that is not a detail. ``mgcv``'s ``poisson()`` family holds the scale at 1, while
    :class:`PenalizedMIFit` carries ``cov = (XᵀWX + S)⁻¹ φ̂`` with φ̂ the Pearson
    estimate. Comparing the shipped ``cov`` against ``vcov(m)`` would report a
    disagreement of exactly φ̂ and say nothing about either implementation, so the
    dispersion travels as its own number and the covariance travels unscaled.

    **The full matrix travels only where the comparison is exact** — a fixed-λ cell,
    where both sides penalise identically. At free ``sp`` the two sides select different
    λ, so the only comparable quantity is the *inflation* summary (see the module
    docstring); shipping two 50x50 matrices per cell to compute one ratio would inflate
    a committed golden for no diagnostic gain. The **diagonals** travel in both cases,
    because a per-coefficient diagonal is what lets an implementer bisect a disagreement
    offline and it costs ``p`` floats rather than ``p²``.
    """

    name: str
    design_id: str
    levels: tuple[int, ...]
    gamma: float
    lambda_age: float
    lambda_year: float
    free_sp: bool
    coef: np.ndarray
    edf_total: float
    edf_tensor: float
    edf_factors: float
    dispersion: float
    deviance: float
    reml_score: float
    n_iter: int
    penalized_score_inf_norm: float
    lambda_at_bound: bool
    vcov_unscaled: np.ndarray | None
    vcov_diag: np.ndarray | None
    vcov_unconditional_diag: np.ndarray | None
    n_rejected_points: int | None
    n_floored_directions: int | None


def _deviance(deaths: np.ndarray, mu: np.ndarray) -> float:
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(
            deaths > 0.0, deaths * np.log(np.where(deaths > 0.0, deaths / mu, 1.0)), 0.0
        )
    return float(2.0 * np.sum(terms - (deaths - mu)))


def _cell_result(
    cell: ConformanceCell, export: DesignExport, cells: pl.DataFrame
) -> PythonCellResult:
    """Fit one cell through the shipped entry points and package every intermediate."""
    spec = export.spec
    wants_vcov = 4 in cell.levels
    if cell.free_sp:
        # fit_reml, not select-then-fit by hand: the two-step dance is exactly what
        # dropped the selection metadata in slice 2 (ADR-186 amendment 1).
        fit = fit_reml(cells, k_age=spec.k_age, k_year=spec.k_year, gamma=cell.gamma)
    else:
        model = _model(spec, cells, lambda_age=cell.lambda_age, lambda_year=cell.lambda_year)
        fit = model.fit(gamma=cell.gamma)

    penalty = fit.lambda_age * export.s_age + fit.lambda_year * export.s_year
    mu = np.exp(export.design @ fit.coef + export.offset)
    unscaled = fit.cov / fit.dispersion

    correction: np.ndarray | None = None
    n_floored: int | None = None
    if wants_vcov and cell.free_sp:
        extra = smoothing_uncertainty(
            cells,
            lambda_age=fit.lambda_age,
            lambda_year=fit.lambda_year,
            gamma=cell.gamma,
            k_age=spec.k_age,
            k_year=spec.k_year,
        )
        correction = extra.correction
        n_floored = extra.n_floored

    return PythonCellResult(
        name=cell.name,
        design_id=cell.design_id,
        levels=cell.levels,
        gamma=cell.gamma,
        lambda_age=float(fit.lambda_age),
        lambda_year=float(fit.lambda_year),
        free_sp=cell.free_sp,
        coef=np.asarray(fit.coef, dtype=np.float64),
        edf_total=float(fit.edf_total),
        edf_tensor=float(fit.edf_tensor),
        edf_factors=float(fit.edf_factors),
        dispersion=float(fit.dispersion),
        deviance=_deviance(export.deaths, mu),
        reml_score=reml_score(
            export.deaths, export.design, export.offset, fit.coef, penalty, cell.gamma
        ),
        n_iter=int(fit.n_iter),
        penalized_score_inf_norm=penalized_score_infinity_norm(
            export.design, export.deaths, export.offset, fit.coef, penalty
        ),
        lambda_at_bound=bool(
            _at_bound(fit.lambda_age) or _at_bound(fit.lambda_year) if cell.free_sp else False
        ),
        # The full matrix only at fixed lambda, where the comparison is exact — see
        # PythonCellResult's docstring for why the free-sp cells carry summaries.
        vcov_unscaled=unscaled if (wants_vcov and not cell.free_sp) else None,
        vcov_diag=np.diag(unscaled).copy() if wants_vcov else None,
        vcov_unconditional_diag=None
        if correction is None
        else np.diag(unscaled + correction).copy(),
        n_rejected_points=fit.n_rejected_points,
        n_floored_directions=n_floored,
    )


def _at_bound(value: float) -> bool:
    from polaris_re.analytics.experience_gam_penalized import lambda_is_at_bound

    return lambda_is_at_bound(value, LAMBDA_LOG10_BOUNDS)


def python_reference(
    bundle: ExchangeBundle,
    *,
    cells_for: Callable[[DesignSpec], pl.DataFrame] | None = None,
    seed: int = SYNTHETIC_SEED,
) -> tuple[PythonCellResult, ...]:
    """Our answer for every cell in the bundle, in the bundle's own order."""
    build_cells = cells_for or (
        lambda spec: synthetic_cells(with_factor=spec.with_factor, seed=seed)
    )
    frames = {d_id: build_cells(export.spec) for d_id, export in bundle.designs.items()}
    return tuple(
        _cell_result(cell, bundle.designs[cell.design_id], frames[cell.design_id])
        for cell in bundle.cells
    )


def write_python_reference(
    results: tuple[PythonCellResult, ...],
    directory: str | Path,
    *,
    exchange_digest: str,
    case: str,
    filename: str = "python_reference.json",
) -> Path:
    """Write our side, stamped with the exchange hash it was computed from."""
    out = Path(directory) / filename
    payload: dict[str, JsonValue] = {
        "schema_version": SCHEMA_VERSION,
        "case": case,
        "exchange_sha256": exchange_digest,
        "side": "python",
        "cells": {r.name: _result_to_json(r) for r in results},
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return out


def _result_to_json(result: PythonCellResult) -> dict[str, JsonValue]:
    return {
        "design": result.design_id,
        "levels": list(result.levels),
        "gamma": result.gamma,
        "free_sp": result.free_sp,
        "sp": [result.lambda_age, result.lambda_year],
        "coef": [float(x) for x in result.coef],
        "edf_total": result.edf_total,
        "edf_tensor": result.edf_tensor,
        "edf_factors": result.edf_factors,
        "dispersion": result.dispersion,
        "deviance": result.deviance,
        "reml_score": result.reml_score,
        "n_iter": result.n_iter,
        "penalized_score_inf_norm": result.penalized_score_inf_norm,
        "lambda_at_bound": result.lambda_at_bound,
        "n_rejected_points": result.n_rejected_points,
        "n_floored_directions": result.n_floored_directions,
        "vcov_unscaled": None
        if result.vcov_unscaled is None
        else [[float(v) for v in row] for row in result.vcov_unscaled],
        "vcov_diag": None if result.vcov_diag is None else [float(v) for v in result.vcov_diag],
        "vcov_unconditional_diag": None
        if result.vcov_unconditional_diag is None
        else [float(v) for v in result.vcov_unconditional_diag],
    }


# --- Comparing the two sides --------------------------------------------------------


@dataclass(frozen=True)
class MetricCheck:
    """One number, its tolerance, and whether it cleared."""

    metric: str
    level: int
    value: float
    tolerance: float
    passed: bool


@dataclass(frozen=True)
class CellComparison:
    """Every metric available for one cell, plus what was missing and why."""

    name: str
    design_id: str
    levels: tuple[int, ...]
    checks: tuple[MetricCheck, ...]
    notes: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


@dataclass(frozen=True)
class ConformanceComparison:
    """The whole run: per-cell checks, the environment R ran in, and a verdict."""

    case: str
    exchange_sha256: str
    mgcv_version: str
    r_session_info: str
    cells: tuple[CellComparison, ...]
    structural: tuple[MetricCheck, ...]
    notes: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cells) and all(s.passed for s in self.structural)

    def levels_settled(self) -> dict[int, bool]:
        """Per level: did every metric assigned to it pass, everywhere it was measured?"""
        out: dict[int, bool] = {}
        for cell in self.cells:
            for check in cell.checks:
                out[check.level] = out.get(check.level, True) and check.passed
        for check in self.structural:
            out[check.level] = out.get(check.level, True) and check.passed
        return dict(sorted(out.items()))


_TOLERANCE_BY_METRIC: dict[str, MetricSpec] = {m.metric: m for m in LEVEL_METRICS}


def _check(metric: str, value: float) -> MetricCheck:
    spec = _TOLERANCE_BY_METRIC[metric]
    return MetricCheck(
        metric=metric,
        level=spec.level,
        value=float(value),
        tolerance=spec.tolerance,
        passed=bool(np.isfinite(value) and abs(value) <= spec.tolerance),
    )


def _matrix(payload: object, name: str, cell: str) -> np.ndarray:
    if payload is None:
        raise PolarisValidationError(f"Cell {cell!r} carries no {name}.")
    return np.asarray(payload, dtype=np.float64)


def _rel_max_diff(ours: np.ndarray, theirs: np.ndarray) -> float:
    scale = float(np.max(np.abs(ours)))
    if scale <= 0.0:  # pragma: no cover - a zero covariance is not a fit
        return float(np.max(np.abs(theirs)))
    return float(np.max(np.abs(ours - theirs)) / scale)


def compare_reference(
    exchange_dir: str | Path,
    python_ref: dict[str, JsonValue],
    mgcv_ref: dict[str, JsonValue],
) -> ConformanceComparison:
    """Compare the two sides, refusing anything the exchange cannot certify.

    The **hash guard is first and unconditional.** Both references record the exchange
    digest they were computed from; this recomputes it from the files on disk and
    refuses if either disagrees. Iterating against a reference produced from a file R
    never saw is the failure mode this whole construction is exposed to, and it is
    silent by nature — the numbers still look like numbers.

    Raises:
        PolarisValidationError: on a hash mismatch, a schema-version mismatch, a
            case mismatch, or a cell present on one side and not the other.
    """
    digest = exchange_hash(exchange_dir)
    for side, ref in (("python", python_ref), ("mgcv", mgcv_ref)):
        recorded = str(ref.get("exchange_sha256", ""))
        if recorded != digest:
            raise PolarisValidationError(
                f"The {side} reference was computed from exchange "
                f"{recorded[:12] or '(absent)'}… but {Path(exchange_dir)} now hashes to "
                f"{digest[:12]}…. Re-run that side against the current exchange; "
                f"comparing across a changed exchange would declare parity with a file "
                f"the other side never saw."
            )
        if int(ref.get("schema_version", -1)) != SCHEMA_VERSION:
            raise PolarisValidationError(
                f"The {side} reference is schema version "
                f"{ref.get('schema_version')}; this build reads {SCHEMA_VERSION}."
            )
    if str(python_ref.get("case")) != str(mgcv_ref.get("case")):
        raise PolarisValidationError(
            f"Case mismatch: python={python_ref.get('case')!r} vs mgcv={mgcv_ref.get('case')!r}."
        )
    # The second unconditional guard, and for the same reason as the hash: a run with
    # mgcv's penalty rescaling left ON compared a rescaled penalty against ours, so `sp`
    # did not multiply the same matrix on the two sides. Every fixed-lambda metric would
    # then disagree for a reason that is not arithmetic — a false finding expensive enough
    # to be worth refusing rather than annotating.
    if mgcv_ref.get("scale_penalty") is not False:
        raise PolarisValidationError(
            f"The mgcv reference reports scale_penalty="
            f"{mgcv_ref.get('scale_penalty')!r}; this comparison requires it FALSE so that "
            f"`sp` multiplies the supplied penalties directly. Re-run "
            f"scripts/mgcv_conformance.R — it sets gam.control(scalePenalty = FALSE) and "
            f"fails loudly if that argument is rejected."
        )

    bundle = read_exchange(exchange_dir)
    ours_cells = dict(python_ref["cells"])  # type: ignore[arg-type]
    theirs_cells = dict(mgcv_ref["cells"])  # type: ignore[arg-type]
    missing = sorted(set(ours_cells) ^ set(theirs_cells))
    if missing:
        raise PolarisValidationError(
            f"Cells present on one side only: {missing}. A partial R run is a finding, "
            f"not a comparison — re-run the batch."
        )

    comparisons: list[CellComparison] = []
    for cell in bundle.cells:
        ours = dict(ours_cells[cell.name])  # type: ignore[arg-type]
        theirs = dict(theirs_cells[cell.name])  # type: ignore[arg-type]
        export = bundle.designs[cell.design_id]
        comparisons.append(_compare_cell(cell, export, ours, theirs))

    return ConformanceComparison(
        case=str(python_ref.get("case")),
        exchange_sha256=digest,
        mgcv_version=str(mgcv_ref.get("mgcv_version", "unknown")),
        r_session_info=str(mgcv_ref.get("r_session_info", "")),
        cells=tuple(comparisons),
        structural=_structural_checks(ours_cells, theirs_cells),
        notes=(
            "Every metric's tolerance and the reason for it is in LEVEL_METRICS; the "
            "two free-sp tolerances are PROVISIONAL until the first R run.",
        ),
    )


def _compare_cell(
    cell: ConformanceCell,
    export: DesignExport,
    ours: dict[str, JsonValue],
    theirs: dict[str, JsonValue],
) -> CellComparison:
    checks: list[MetricCheck] = []
    notes: list[str] = []
    # Surfaced rather than gated: the R script probes for scaling artefacts defensively
    # (an mgcv version that does not expose one returns nothing), so their absence proves
    # nothing and their presence is the first thing to read on a level-1 disagreement.
    scaling = theirs.get("penalty_scaling")
    if scaling:
        notes.append(
            f"`{cell.name}`: mgcv exposed penalty-scaling artefacts {scaling!r}. If these "
            f"are not all ~1, `sp` did not multiply the supplied S directly and THAT is "
            f"the finding, before any arithmetic is re-derived."
        )
    supplied = theirs.get("sp_supplied")
    if supplied is not None and not cell.free_sp:
        asked = np.array([cell.lambda_age, cell.lambda_year], dtype=np.float64)
        if not np.allclose(np.asarray(supplied, dtype=np.float64), asked, rtol=1e-12, atol=0.0):
            raise PolarisValidationError(
                f"Cell {cell.name!r}: mgcv was given sp={list(supplied)} but the manifest "
                f"specifies {list(asked)}. A fixed-lambda comparison at a different lambda "
                f"is not a comparison."
            )
    our_coef = np.asarray(ours["coef"], dtype=np.float64)
    their_coef = np.asarray(theirs["coef"], dtype=np.float64)
    if our_coef.shape != their_coef.shape:
        raise PolarisValidationError(
            f"Cell {cell.name!r}: coefficient vectors differ in length "
            f"({our_coef.size} vs {their_coef.size}) — the two sides did not fit the "
            f"same design."
        )

    if 1 in cell.levels:
        checks.append(_check("max_abs_coef_diff", np.max(np.abs(our_coef - their_coef))))
        eta_ours = export.design @ our_coef
        eta_theirs = export.design @ their_coef
        checks.append(_check("max_abs_eta_diff", np.max(np.abs(eta_ours - eta_theirs))))

    if 3 in cell.levels:
        checks.append(
            _check("abs_edf_total_diff", float(ours["edf_total"]) - float(theirs["edf_total"]))
        )
        checks.append(
            _check("abs_edf_tensor_diff", float(ours["edf_tensor"]) - float(theirs["edf_tensor"]))
        )
        checks.append(
            _check(
                "abs_edf_factors_diff", float(ours["edf_factors"]) - float(theirs["edf_factors"])
            )
        )

    if 2 in cell.levels or 5 in cell.levels:
        suffix = "_gamma" if 5 in cell.levels else "_free_sp"
        sp_metric = "max_abs_log10_sp_diff" + ("_gamma" if 5 in cell.levels else "")
        our_sp = np.asarray(ours["sp"], dtype=np.float64)
        their_sp = np.asarray(theirs["sp"], dtype=np.float64)
        checks.append(_check(sp_metric, np.max(np.abs(np.log10(our_sp) - np.log10(their_sp)))))
        checks.append(
            _check(
                "abs_edf_total_diff" + suffix,
                float(ours["edf_total"]) - float(theirs["edf_total"]),
            )
        )
        if bool(ours.get("lambda_at_bound")):
            notes.append(
                "Our selected lambda sits ON the search bound, so the sp comparison "
                "reads 'at least this' rather than 'this' — mgcv is unbounded."
            )

    if 4 in cell.levels:
        if cell.free_sp:
            our_diag = _matrix(ours.get("vcov_diag"), "vcov_diag", cell.name)
            our_uncond = _matrix(
                ours.get("vcov_unconditional_diag"), "unconditional vcov diagonal", cell.name
            )
            their_diag = _matrix(theirs.get("vcov_diag"), "vcov_diag", cell.name)
            their_uncond = theirs.get("vcov_unconditional_diag")
            if their_uncond is None:
                notes.append(
                    "mgcv returned no unconditional covariance for this cell (Vc is "
                    "formed only when sp is estimated) — level 4's inflation metric is "
                    "not measured here."
                )
            else:
                ours_inflation = float(np.mean(our_uncond) / np.mean(our_diag))
                theirs_inflation = float(
                    np.mean(_matrix(their_uncond, "unconditional vcov diagonal", cell.name))
                    / np.mean(their_diag)
                )
                checks.append(
                    _check(
                        "rel_unconditional_inflation_diff",
                        ours_inflation / theirs_inflation - 1.0,
                    )
                )
                notes.append(
                    f"`{cell.name}` unconditional inflation: ours {ours_inflation:.4f}x, "
                    f"mgcv {theirs_inflation:.4f}x — measured at INDEPENDENTLY selected "
                    f"lambda, so read it only after level 2 passes."
                )
        else:
            our_v = _matrix(ours.get("vcov_unscaled"), "vcov_unscaled", cell.name)
            their_v = _matrix(theirs.get("vcov_unscaled"), "vcov_unscaled", cell.name)
            checks.append(_check("max_rel_vcov_diff", _rel_max_diff(our_v, their_v)))

    return CellComparison(
        name=cell.name,
        design_id=cell.design_id,
        levels=cell.levels,
        checks=tuple(checks),
        notes=tuple(notes),
    )


def _structural_checks(
    ours: dict[str, JsonValue], theirs: dict[str, JsonValue]
) -> tuple[MetricCheck, ...]:
    """Cross-cell checks — currently one: does ``gamma`` move ``edf`` the same way?

    ADR-188 measured ``edf_tensor`` falling monotonically in ``gamma`` on our side. That
    is a statement about our own criterion. The conformance question is whether
    ``mgcv``'s ``gamma`` moves ``edf`` in the same direction by the same rough amount,
    which needs the ``gamma = 1.0`` and ``gamma = 1.4`` cells read together — so it
    cannot live inside either one.
    """
    base, tuned = ours.get("l2-free-sp"), ours.get("l5-gamma")
    r_base, r_tuned = theirs.get("l2-free-sp"), theirs.get("l5-gamma")
    if not (base and tuned and r_base and r_tuned):
        # A reduced matrix (the tests' two-cell bundle, or a hand-trimmed one) has no
        # gamma pair to read, and a cross-cell check cannot be faked from one cell.
        return ()
    our_delta = float(dict(tuned)["edf_total"]) - float(dict(base)["edf_total"])  # type: ignore[arg-type]
    their_delta = float(dict(r_tuned)["edf_total"]) - float(dict(r_base)["edf_total"])  # type: ignore[arg-type]
    return (
        MetricCheck(
            metric="gamma_edf_delta_agrees_in_sign",
            level=5,
            value=our_delta - their_delta,
            tolerance=float(_TOLERANCE_BY_METRIC["abs_edf_total_diff_gamma"].tolerance),
            passed=bool(
                np.sign(our_delta) == np.sign(their_delta)
                and abs(our_delta - their_delta)
                <= _TOLERANCE_BY_METRIC["abs_edf_total_diff_gamma"].tolerance
            ),
        ),
    )


def rscript_mgcv_available() -> bool:
    """Return ``True`` iff ``Rscript`` is on PATH and can load ``mgcv``.

    Gates the R path exactly as ADR-151's :func:`mgcv_available` does, but over a
    **subprocess** rather than ``rpy2``: the conformance R script is a standalone
    ``Rscript`` program precisely so a maintainer needs no Python-R bridge. CI and the
    Docker runtime ship neither, so anything guarded by this skips there (Anchor 5).
    """
    import shutil
    import subprocess

    if shutil.which("Rscript") is None:
        return False
    try:  # pragma: no cover - exercised only where R is installed
        done = subprocess.run(
            ["Rscript", "-e", "library(mgcv); cat(as.character(packageVersion('mgcv')))"],
            capture_output=True,
            timeout=120,
            check=False,
        )
        return done.returncode == 0
    except Exception:
        return False


def render_comparison_markdown(comparison: ConformanceComparison) -> str:
    """The committed report — derived scalars only, never cell-grain experience.

    That is what lets the HMD/ILEC comparison come back into the repo while their
    exchange files stay local (``DATA_LICENSING.md`` §1): a max absolute coefficient
    difference is not experience.
    """
    levels = comparison.levels_settled()
    lines = [
        f"# mgcv conformance — {comparison.case}",
        "",
        "**Produced by:** `scripts/compare_mgcv_conformance.py` (slice 5, "
        "`docs/PLAN_penalized_mi_surface.md`).",
        f"**Exchange SHA-256:** `{comparison.exchange_sha256}`",
        f"**mgcv version:** {comparison.mgcv_version}",
        "",
        "## Verdict",
        "",
        (
            "**ALL LEVELS AGREE** within the stated tolerances."
            if comparison.passed
            else "**DISAGREEMENT** — see the failing rows. PLAN Anchor 8: a refutation is a "
            "successful run that changes an anchor, not a failed slice."
        ),
        "",
        "| level | settles | verdict |",
        "|---|---|---|",
    ]
    what = {
        1: "penalized IRLS at fixed λ — coefficients element-wise",
        2: "our REML criterion and grid search — selected `sp` and `edf`",
        3: "`tr(F)` as the per-term EDF (Anchor 4)",
        4: "`Vb`, and the Kass-Steffey correction (ADR-188 decision 2)",
        5: "Wood's `gamma` (ADR-188 decision 3)",
    }
    for level, ok in levels.items():
        lines.append(f"| {level} | {what.get(level, '')} | {'AGREES' if ok else 'DISAGREES'} |")
    lines += [
        "",
        "## Per-cell metrics",
        "",
        "| cell | design | metric | value | tolerance | verdict |",
        "|---|---|---|---:|---:|---|",
    ]
    for cell in comparison.cells:
        for check in cell.checks:
            lines.append(
                f"| `{cell.name}` | {cell.design_id} | `{check.metric}` | "
                f"{check.value:.3e} | {check.tolerance:.1e} | "
                f"{'PASS' if check.passed else '**FAIL**'} |"
            )
    for check in comparison.structural:
        lines.append(
            f"| _cross-cell_ | — | `{check.metric}` | {check.value:.3e} | "
            f"{check.tolerance:.1e} | {'PASS' if check.passed else '**FAIL**'} |"
        )
    notes = [n for cell in comparison.cells for n in cell.notes]
    if notes:
        lines += ["", "## Notes carried from the comparison", ""]
        lines += [f"- {n}" for n in dict.fromkeys(notes)]
    lines += ["", "## Tolerances and why they are what they are", ""]
    for spec in LEVEL_METRICS:
        lines.append(
            f"- **`{spec.metric}`** (level {spec.level}, ≤ {spec.tolerance:g}) — {spec.rationale}"
        )
    if comparison.r_session_info:
        lines += ["", "## R environment", "", "```", comparison.r_session_info.strip(), "```"]
    return "\n".join(lines) + "\n"

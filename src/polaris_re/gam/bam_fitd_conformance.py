"""Polaris's ``bgam.fitd`` port against ``bam(method="fREML", discrete=TRUE)`` — real-data
readiness epic Slice R3, Stage B checkpoints (iii) and (iv) (ADR-260 amendments 2-4).

**Claim sentence (ADR-193), written before the code.** *"Polaris
(:func:`polaris_re.gam.api.gam` with ``method="fREML", discrete=True``: it builds the design
and penalties from the formula string and the data columns, then runs
:func:`polaris_re.gam.bam_fitd.bam_fitd`) fits a Poisson cell; ``mgcv`` fits the same
formula and data with ``bam(method="fREML", discrete=TRUE)``; compared on ``eta``,
``edf_total``, the ``Vp`` standard error of ``eta`` and the iteration count at the end, with
``log(sp)`` reported and not gated (ADR-221)."* That is :data:`END_TO_END_CLAIM`, the only
parity claim here.

**Two comparisons, deliberately.**

1. *End to end* (:func:`compare_end_to_end`): every column INDEPENDENT. Polaris's design
   producer takes the data frame and the formula; ``mgcv``'s is ``bam`` on the same two.
2. *Design-conditioned* (:func:`compare_design_conditioned`): Polaris is handed the design
   ``X`` and penalties ``S`` that ``bam`` itself built (the probe rebuilds ``X`` through
   ``mgcv:::Xbd``), and :func:`~polaris_re.gam.bam_fitd.bam_fitd` runs the iteration on them.
   **By the ADR-193 mechanical test this is NOT independent**: the producing function takes
   the other side's payload as an input. It is declared ECHO (the design) and the iteration
   columns are declared ECHO as well, so the rendered headline says "harness check, NOT
   parity". It is kept because it isolates the *algorithm* from the *design*: where it agrees
   to rounding and the end-to-end comparison does not, the remainder is the design.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import polars as pl

from polaris_re.analytics.gam_model import resolve_family
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam.api import gam
from polaris_re.gam.bam_fitd import bam_fitd
from polaris_re.gam.real_data_trial import (
    EDF_GATE,
    ETA_GATE,
    SCALED_ETA_FLAG,
    SCALED_ETA_GATE,
    SE_REL_GATE,
)

__all__ = [
    "END_TO_END_CLAIM",
    "ISOLATION_CLAIM",
    "SEED_CLAIM",
    "DesignConditionedComparison",
    "EndToEndComparison",
    "SeedSensitivity",
    "compare_design_conditioned",
    "compare_end_to_end",
    "compare_seed_sensitivity",
    "polaris_formula",
]

_POLARIS_PRODUCER = "polaris_re.gam.api.gam(method='fREML', discrete=True) -> bam_fitd"
_MGCV_PRODUCER = "mgcv::bam(method='fREML', discrete=TRUE) (via scripts/bam_fitd_probe.R)"

END_TO_END_CLAIM = VerificationClaim(
    claim=(
        "Polaris (gam(method='fREML', discrete=True): design and penalties from the formula "
        "string and the data columns, then the bgam.fitd performance iteration) fits a Poisson "
        "cell; mgcv fits the same formula and data with bam(method='fREML', discrete=TRUE); "
        "compared on eta, edf_total, the Vp standard error of eta and the iteration count. "
        "log(sp) is reported and not gated (ADR-221). The exact-REML gam() baseline is "
        "mgcv against mgcv."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta (max abs)",
            left_producer=_POLARIS_PRODUCER,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total",
            left_producer=_POLARIS_PRODUCER,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="Vp se of eta (max relative)",
            left_producer=_POLARIS_PRODUCER,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="iteration count",
            left_producer=_POLARIS_PRODUCER,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log(sp) (max abs, reported not gated)",
            left_producer=_POLARIS_PRODUCER,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="eta: gam(REML) vs bam(discrete=TRUE) baseline",
            left_producer="mgcv::gam(method='REML')",
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
    ),
)

_ECHO_LEFT = "polaris_re.gam.bam_fitd.bam_fitd on MGCV'S OWN X and S (not independent: input)"
ISOLATION_CLAIM = VerificationClaim(
    claim=(
        "Polaris (bam_fitd, handed the design X and penalties S that bam built, rebuilt through "
        "mgcv:::Xbd) runs the performance iteration; mgcv runs it as bam(discrete=TRUE) on the "
        "formula; compared per iteration on log(sp) and eta, and at the end on edf_total and the "
        "iteration count. Handing Polaris the other side's design fails the ADR-193 mechanical "
        "test, so this is a diagnostic that isolates the algorithm from the design, not parity."
    ),
    quantities=(
        ComparedQuantity(
            quantity="design X, penalties S (mgcv-built, handed to Polaris)",
            left_producer="mgcv:::Xbd / bam(fit=FALSE)$S",
            right_producer="polaris_re.gam.bam_fitd.bam_fitd (input)",
            provenance=ComparisonProvenance.ECHO,
        ),
        ComparedQuantity(
            quantity="log(sp) per iteration",
            left_producer=_ECHO_LEFT,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.ECHO,
        ),
        ComparedQuantity(
            quantity="eta per iteration",
            left_producer=_ECHO_LEFT,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.ECHO,
        ),
        ComparedQuantity(
            quantity="edf_total, iteration count",
            left_producer=_ECHO_LEFT,
            right_producer=_MGCV_PRODUCER,
            provenance=ComparisonProvenance.ECHO,
        ),
    ),
)


def polaris_formula(formula: str) -> str:
    """The probe's ``offset(log(expo))`` as the plain column ``gam()`` accepts."""
    return formula.replace("offset(log(expo))", "offset(logexpo)")


@dataclass(frozen=True)
class EndToEndComparison:
    """Polaris's own-design fit against ``bam(discrete=TRUE)`` on one cell (scalars only)."""

    name: str
    n: int
    iter_polaris: int
    iter_mgcv: int
    eta_max_abs: float
    eta_scaled_max: float
    edf_total_abs: float
    se_rel_max: float
    log_sp_max_abs: float
    gam_vs_bam_eta: float
    """MEASUREMENT of the reference against itself: exact-REML ``gam`` vs ``bam``."""
    eta_gate_met: bool
    edf_gate_met: bool
    se_gate_met: bool
    scaled_gate_met: bool
    scaled_flag: bool

    @property
    def gates_met(self) -> bool:
        return self.eta_gate_met and self.edf_gate_met and self.se_gate_met and self.scaled_gate_met


@dataclass(frozen=True)
class DesignConditionedComparison:
    """Polaris's iteration on ``bam``'s own design against ``bam``'s trace (scalars only)."""

    name: str
    iter_polaris: int
    iter_mgcv: int
    eta_max_abs: float
    edf_total_abs: float
    log_sp_diff_by_iteration: tuple[float, ...]
    eta_diff_by_iteration: tuple[float, ...]


def _frame(cell: Mapping[str, object]) -> pl.DataFrame:
    data: Mapping[str, Sequence[object]] = cell["data"]  # type: ignore[assignment]
    cols: dict[str, Sequence[object]] = {k: list(v) for k, v in data.items()}
    return pl.DataFrame(cols).with_columns(logexpo=pl.col("expo").log())


def compare_end_to_end(cell: Mapping[str, object]) -> EndToEndComparison:
    """Fit the cell through ``gam(method="fREML", discrete=True)`` and reduce to scalars."""
    df = _frame(cell)
    fit = gam(
        polaris_formula(str(cell["formula"])),
        df,
        "poisson",
        select=bool(cell["select"]),
        method="fREML",
        discrete=True,
    )
    final: Mapping[str, object] = cell["final"]  # type: ignore[assignment]
    eta_m = np.asarray(final["eta"], dtype=np.float64)
    se_m = np.asarray(final["se"], dtype=np.float64)
    _, se_p = fit.predict(df, se_fit=True)
    d = np.abs(fit.eta - eta_m)
    gam_eta = np.asarray(cell["gam"]["eta"], dtype=np.float64)  # type: ignore[index]
    lsp_p = fit.log_lambda * np.log(10.0)
    lsp_m = np.asarray(final["log_sp"], dtype=np.float64)
    # gam(discrete=True) applies mgcv:::tero (margin reorder), so the sp vectors are aligned.
    lsp_diff = float(np.max(np.abs(lsp_p - lsp_m)))
    scaled = float(np.max(d / se_m))
    se_rel = float(np.max(np.abs(se_p - se_m) / se_m))
    edf_abs = abs(float(fit.edf_total) - float(final["edf_total"]))  # type: ignore[arg-type]
    return EndToEndComparison(
        name=str(cell["name"]),
        n=int(cell["n"]),  # type: ignore[call-overload]
        iter_polaris=int(fit.n_iterations or 0),
        iter_mgcv=int(final["iter"]),  # type: ignore[call-overload]
        eta_max_abs=float(d.max()),
        eta_scaled_max=scaled,
        edf_total_abs=edf_abs,
        se_rel_max=se_rel,
        log_sp_max_abs=lsp_diff,
        gam_vs_bam_eta=float(np.max(np.abs(gam_eta - eta_m))),
        eta_gate_met=float(d.max()) < ETA_GATE,
        edf_gate_met=edf_abs < EDF_GATE,
        se_gate_met=se_rel < SE_REL_GATE,
        scaled_gate_met=scaled <= SCALED_ETA_GATE,
        scaled_flag=scaled > SCALED_ETA_FLAG,
    )


def compare_design_conditioned(cell: Mapping[str, object]) -> DesignConditionedComparison:
    """Run the iteration on ``bam``'s own ``X`` and ``S`` and compare it with ``bam``'s trace."""
    x = np.asarray(cell["X_unique"], dtype=np.float64)[
        np.asarray(cell["X_index"], dtype=np.intp) - 1
    ]
    p = x.shape[1]
    blocks: list[np.ndarray] = []
    for q in cell["pen"]:  # type: ignore[attr-defined]
        s = np.atleast_2d(np.asarray(q["S"], dtype=np.float64))
        off = int(q["off"]) - 1
        full = np.zeros((p, p), dtype=np.float64)
        full[off : off + s.shape[0], off : off + s.shape[0]] = s
        blocks.append(full)
    data: Mapping[str, Sequence[float]] = cell["data"]  # type: ignore[assignment]
    y = np.asarray(data["y"], dtype=np.float64)
    offset = np.log(np.asarray(data["expo"], dtype=np.float64))
    res = bam_fitd(x, tuple(blocks), y, resolve_family("poisson", "log"), offset=offset)
    trace: Sequence[Mapping[str, object]] = cell["trace"]  # type: ignore[assignment]
    final: Mapping[str, object] = cell["final"]  # type: ignore[assignment]
    lsp_d: list[float] = []
    eta_d: list[float] = []
    for it, ref in zip(res.trace, trace, strict=False):
        lsp_d.append(float(np.max(np.abs(it.log_sp - np.asarray(ref["log_sp"])))))  # type: ignore[arg-type]
        eta_d.append(float(np.max(np.abs(x @ it.coef + offset - np.asarray(ref["eta"])))))  # type: ignore[arg-type]
    return DesignConditionedComparison(
        name=str(cell["name"]),
        iter_polaris=res.n_iter,
        iter_mgcv=int(final["iter"]),  # type: ignore[call-overload]
        eta_max_abs=float(np.max(np.abs(res.eta - np.asarray(final["eta"])))),  # type: ignore[arg-type]
        edf_total_abs=abs(float(np.sum(res.edf)) - float(final["edf_total"])),  # type: ignore[arg-type]
        log_sp_diff_by_iteration=tuple(lsp_d),
        eta_diff_by_iteration=tuple(eta_d),
    )


SEED_CLAIM = VerificationClaim(
    claim=(
        "mgcv bam(method='fREML', discrete=TRUE) is re-run with discrete.mf's hard-coded seed "
        "(8547, the seed of the sample() that pads each variable's unique values) patched to "
        "six other values, all else identical; the spread of eta across seeds is the reference's "
        "own noise floor. Polaris (deterministic, no RNG) is compared with bam at every seed."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta spread across discrete.mf seeds (max over rows of max - min)",
            left_producer="mgcv::bam(discrete=TRUE), discrete.mf seed = s1",
            right_producer="mgcv::bam(discrete=TRUE), discrete.mf seed = s2",
            provenance=ComparisonProvenance.REFERENCE_INTERNAL,
        ),
        ComparedQuantity(
            quantity="Polaris vs bam at each seed (max abs eta)",
            left_producer=_POLARIS_PRODUCER,
            right_producer=_MGCV_PRODUCER + ", seed patched",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)


@dataclass(frozen=True)
class SeedSensitivity:
    """Scalars only: the reference's seed noise floor and where Polaris sits in it."""

    name: str
    n_seeds: int
    spread: float
    """max over rows of (max - min) of bam's eta across seeds (REFERENCE_INTERNAL)."""
    max_dev_from_default_seed: float
    polaris_vs_default_seed: float
    polaris_vs_seed_min: float
    polaris_vs_seed_max: float
    edf_total_spread: float
    iter_by_seed: tuple[int, ...]


def compare_seed_sensitivity(cell: Mapping[str, object]) -> SeedSensitivity | None:
    """Seed noise floor of ``bam`` on one cell, and Polaris's distance to each seed's fit."""
    seeds: Sequence[Mapping[str, object]] | None = cell.get("seeds")  # type: ignore[assignment]
    if not seeds:
        return None
    df = _frame(cell)
    fit = gam(
        polaris_formula(str(cell["formula"])),
        df,
        "poisson",
        select=bool(cell["select"]),
        method="fREML",
        discrete=True,
    )
    etas = np.vstack([np.asarray(s["eta"], dtype=np.float64) for s in seeds])
    default = etas[0]  # SEEDS[0] is mgcv's own 8547
    spread = float(np.max(etas.max(axis=0) - etas.min(axis=0)))
    dev = float(np.max(np.abs(etas[1:] - default)))
    p_vs = np.max(np.abs(etas - fit.eta[None, :]), axis=1)
    edfs = np.asarray([float(s["edf_total"]) for s in seeds])  # type: ignore[arg-type]
    return SeedSensitivity(
        name=str(cell["name"]),
        n_seeds=len(seeds),
        spread=spread,
        max_dev_from_default_seed=dev,
        polaris_vs_default_seed=float(p_vs[0]),
        polaris_vs_seed_min=float(p_vs[1:].min()),
        polaris_vs_seed_max=float(p_vs[1:].max()),
        edf_total_spread=float(edfs.max() - edfs.min()),
        iter_by_seed=tuple(int(s["iter"]) for s in seeds),  # type: ignore[call-overload]
    )

#!/usr/bin/env python3
"""Slice R3 Stage A (ADR-260 amendment 1): Polaris's port of ``bam(discrete=TRUE)``'s
covariate discretisation vs ``mgcv:::discrete.mf`` / ``compress.df``, from
``bam_binning_probe.R``'s JSON, plus the REFERENCE_INTERNAL algorithm measurement.

Usage: bam_binning_compare.py <bam_binning_probe.json> [report.md]

Provenance (ADR-193): the binning columns are INDEPENDENT; the algorithm columns are
REFERENCE_INTERNAL (mgcv vs mgcv; Polaris is absent). Headlines come from
``evidence_markdown``; "parity" is gated by ``require_parity_evidence`` on the INDEPENDENT
claim only. Exits 0 on a completed comparison (CI annotates; it does not gate here).
"""

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.core.verification import evidence_markdown, require_parity_evidence
from polaris_re.gam.bam_binning_conformance import (
    ALGORITHM_CLAIM,
    BINNING_CLAIM,
    BinningCase,
    BinningComparison,
    compare_binning_case,
    compare_joint_case,
)


def _frame(data: dict[str, list]) -> pl.DataFrame:
    return pl.DataFrame({k: v for k, v in data.items()})


def _codes(values: list[str]) -> np.ndarray:
    levels = {lab: i for i, lab in enumerate(sorted(set(values)))}
    return np.array([levels[v] for v in values], dtype=np.float64)


def build_report(probe: Path) -> tuple[str, int, int]:
    """``(markdown, comparisons that agree, comparisons made)``; no I/O beyond the read."""
    payload = json.loads(probe.read_text())
    require_parity_evidence(BINNING_CLAIM.quantities, claim="bam discretisation vs mgcv (R3-A)")
    rows: list[BinningComparison] = []
    for cell in payload["cells"]:
        case = BinningCase(cell["name"], cell["formula"], _frame(cell["data"]), cell["m"])
        mg = cell["mgcv"]
        rows += compare_binning_case(case, mg["nr"], mg["values"], mg["index"])
    for j in payload["joint"]:
        cols: dict[str, np.ndarray] = {}
        facs: set[str] = set()
        for k, v in j["data"].items():
            if k in j["factors"]:
                facs.add(k)
                cols[k] = _codes(v)
            else:
                cols[k] = np.asarray(v, dtype=np.float64)
        mg = j["mgcv"]
        rows.append(
            compare_joint_case(
                j["name"], cols, frozenset(facs), j["m"], mg["nr"], mg["values"], mg["index"]
            )
        )
    agree = sum(r.agrees for r in rows)
    lines = [
        "",
        "### R3 Stage A: bam(discrete=TRUE) covariate discretisation vs mgcv",
        "",
        evidence_markdown(BINNING_CLAIM),
        "",
        f"mgcv {payload['mgcv_version']} / {payload['r_version']}. The value gate is a relative "
        "1e-12 (a few ulp of the shared `lo + i*by` grid); `nr` and the row partition must be "
        "exact. Cell labels are not compared (`discrete.mf` shuffles them with a seeded sample).",
        "",
        "| cell | variable | binned (Polaris) | nr Polaris | nr mgcv | value diff | "
        "partition | agrees |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.case} | {r.variable} | {r.binned_polaris} | {r.nr_polaris} | {r.nr_mgcv} | "
            f"{r.max_value_diff:.3e} | {'equal' if r.partition_equal else 'DIFFERENT'} | "
            f"**{'yes' if r.agrees else 'NO'}** |"
        )
    lines += ["", f"{agree} of {len(rows)} variable comparisons agree.", ""]

    alg = payload["algorithm"]
    f = alg["fits"]
    eta = {k: np.asarray(v["eta"]) for k, v in f.items()}

    def _gap(a: str, b: str) -> float:
        return float(np.max(np.abs(eta[a] - eta[b])))

    lines += [
        "### R3 Stage A: is bam's gap from gam the binning or the algorithm? (mgcv vs mgcv)",
        "",
        evidence_markdown(ALGORITHM_CLAIM),
        "",
        f"Cell: {alg['n_rows']} rows, Poisson with offset, no covariate binned (integer age "
        "and duration, 2 smoker levels). This is a MEASUREMENT of the reference against itself; "
        "it says nothing about Polaris.",
        "",
        "| comparison | max abs diff in eta |",
        "|---|---:|",
        f"| gam(REML) vs bam(fREML, discrete=FALSE) | {_gap('gam', 'bam_nodisc'):.3e} |",
        f"| bam(discrete=FALSE) vs bam(discrete=TRUE) | {_gap('bam_nodisc', 'bam_disc'):.3e} |",
        f"| gam(REML) vs bam(discrete=TRUE) | {_gap('gam', 'bam_disc'):.3e} |",
        "",
        "| fit | edf_total | " + " | ".join(f["gam"]["smooth_label"]) + " | iterations |",
        "|---|---:|" + "---:|" * (len(f["gam"]["smooth_label"]) + 1),
    ]
    for k, v in f.items():
        lines.append(
            f"| {k} | {v['edf_total']:.4f} | "
            + " | ".join(f"{e:.3f}" for e in v["smooth_edf"])
            + f" | {v['iter']} |"
        )
    lines.append("")
    return "\n".join(lines), agree, len(rows)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    text, agree, total = build_report(Path(argv[1]))
    if len(argv) > 2:
        Path(argv[2]).write_text(text)
    print(text)
    print(f"RESULT: {agree}/{total} agree")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

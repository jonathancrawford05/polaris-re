#!/usr/bin/env python3
"""Slice R4 Stage A (ADR-261): Polaris's thin-plate basis vs ``mgcv``'s ``smoothCon(bs="tp")``,
from ``gam_tp_probe.R``'s JSON.

Usage: gam_tp_compare.py <gam_tp_probe.json> [report.md]

Provenance (ADR-193): ``design_X`` (column space), ``penalty_S`` (in a common basis) and
``rank`` are INDEPENDENT: ``gam_basis_tp.tp_basis(x, k)`` takes the shared recipe only. The
tolerance is derived per case (``gam_basis_tp.derived_tolerance``) from Polaris's and
``mgcv``'s own distance to the exact eigenspace. A NEGATIVE CONTROL runs the same comparison on
a deliberately wrong recipe (truncate ``Z'EZ`` instead of ``E``): it must DISAGREE, otherwise
the tolerance has no power. Headlines come from ``evidence_markdown``; the parity statement is
gated by ``require_parity_evidence``. Exit status 0 on a completed comparison, 1 when any
real case disagrees or the control agrees (CI annotates).
"""

import json
import sys
from pathlib import Path

import numpy as np

from polaris_re.analytics.gam_basis_cr import absorb_sum_to_zero_constraint
from polaris_re.analytics.gam_basis_tp import (
    TP_BASIS_CLAIM,
    TP_NULL_DIM,
    TpBasisComparison,
    compare_tp_basis,
    subspace_distance,
)
from polaris_re.core.verification import evidence_markdown, require_parity_evidence


def _wrong_recipe_design(x: np.ndarray, k: int) -> np.ndarray:
    """Constrained design of the WRONG recipe: eigendecompose ``Z'EZ`` and keep ``k - M``
    eigenvectors (constrain first, truncate second). Measured to move the subspace by 0.1+."""
    xs = x - x.mean()
    xu = np.unique(xs)
    e = (1.0 / 12.0) * np.abs(xu[:, None] - xu[None, :]) ** 3
    t = np.column_stack([np.ones(xu.shape[0]), xu])
    q, _ = np.linalg.qr(t, mode="complete")
    z = q[:, TP_NULL_DIM:]
    values, vectors = np.linalg.eigh(z.T @ e @ z)
    keep = np.argsort(-np.abs(values))[: k - TP_NULL_DIM]
    delta = z @ vectors[:, keep]
    ex = (1.0 / 12.0) * np.abs(xs[:, None] - xu[None, :]) ** 3
    design = np.hstack([ex @ delta, np.column_stack([np.ones(xs.shape[0]), xs])])
    return absorb_sum_to_zero_constraint(design, np.eye(k))[0]


def build_report(probe: Path) -> tuple[str, int, int, int]:
    """``(markdown, cases agreeing, cases, negative controls that wrongly agree)``."""
    payload = json.loads(probe.read_text())
    require_parity_evidence(TP_BASIS_CLAIM.quantities, claim="tp basis vs mgcv (R4 Stage A)")
    rows: list[tuple[str, int, int, float, TpBasisComparison, float]] = []
    control_wrongly_agrees = 0
    for case in payload["cases"]:
        x = np.asarray(case["x"], dtype=np.float64)
        k = int(case["k"])
        mg = case["mgcv"]
        mgcv_design = np.asarray(mg["X"], dtype=np.float64)
        cmp = compare_tp_basis(
            x,
            k,
            mgcv_design,
            np.asarray(mg["S"], dtype=np.float64),
            int(mg["rank"]),
            float(mg["vs_exact"]),
        )
        # at k == nu the truncation keeps everything, so every recipe spans the same space
        # and the control has no power there: report n/a, do not count it
        wrong = (
            float("nan")
            if k >= int(mg["n_unique"])
            else subspace_distance(_wrong_recipe_design(x, k), mgcv_design)
        )
        if wrong <= cmp.tolerance:
            control_wrongly_agrees += 1
        rows.append((case["name"], k, int(mg["n_unique"]), wrong, cmp, 0.0))
    agree = sum(r[4].agrees for r in rows)
    lines = [
        "",
        "### R4 Stage A: thin-plate (`tp`) basis vs mgcv `smoothCon`",
        "",
        evidence_markdown(TP_BASIS_CLAIM),
        "",
        f"mgcv {payload['mgcv_version']} / {payload['r_version']}. Comparison is gauge-free "
        "(the range-space coordinates are not unique). Tolerance per case = mgcv's own distance "
        "to the exact recipe (built in R with `eigen()` on mgcv's `Xu`) + 1e3 x Polaris's a-priori "
        "eigensolver rounding bound "
        "(`derived_tolerance`); S is compared in the basis mapping Polaris's design onto "
        "mgcv's, up to the gauge-dependent `scale.penalty` scalar (column `S scale`, only a "
        "rescaling of sp), with `k` times that tolerance.",
        "",
        "| case | k | nu | space dist | tol (derived) | S rel diff | S scale | mgcv vs exact | "
        "rounding bound | rank diff | wrong-recipe control | agrees |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, k, nu, wrong, c, _ in rows:
        lines.append(
            f"| {name} | {k} | {nu} | {c.subspace_distance:.2e} | {c.tolerance:.2e} | "
            f"{c.penalty_rel_diff:.2e} | {c.penalty_scale:.3g} | {c.mgcv_vs_exact:.1e} | "
            f"{c.rounding_bound:.1e} | "
            f"{c.rank_diff} | {wrong:.2e} | **{'yes' if c.agrees else 'NO'}** |"
        )
    lines += [
        "",
        f"{agree} of {len(rows)} cases agree. Negative control (wrong recipe) wrongly agreed on "
        f"{control_wrongly_agrees} case(s); it must be 0.",
        "",
    ]
    return "\n".join(lines), agree, len(rows), control_wrongly_agrees


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    text, agree, total, bad_control = build_report(Path(argv[1]))
    if len(argv) > 2:
        Path(argv[2]).write_text(text)
    print(text)
    print(f"RESULT: {agree}/{total} agree; control wrongly agreed {bad_control}")
    return 0 if agree == total and bad_control == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

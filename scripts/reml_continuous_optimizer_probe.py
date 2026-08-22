#!/usr/bin/env python3
"""
reml_continuous_optimizer_probe.py — PLAN slice 4 part B, ADR-198's decisive test.

Does a continuous (quasi-Newton) search over log10(lambda) — never reading
mgcv's own selection — land measurably closer to mgcv's own free-sp REML
selection than the production 0.25-decade grid does? ADR-198 hypothesises
that what remains between the grid and mgcv IS the grid's own quantisation,
and names this as the decisive measurement.

No new R work: reads the already-committed ten-cell conformance exchange
(`data/mgcv_exchange/synthetic`), the committed `python_reference.json` (for
the production grid's own already-selected lambda, read not recomputed), and
an `mgcv_reference.json` (produced by `scripts/mgcv_conformance.R`, NOT
committed — regenerate it locally or read it from a CI dispatch of
`mgcv-conformance.yml`, same as every other probe in this epic).

Prints a report to stdout — readable via `get_job_logs` on a tier-3 CI
dispatch, the same discipline ADR-194's methodology fix established.

Usage:
    Rscript scripts/mgcv_conformance.R   # writes mgcv_reference.json locally
    uv run python scripts/reml_continuous_optimizer_probe.py
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402

from polaris_re.analytics.experience_mgcv_conformance import read_exchange  # noqa: E402
from polaris_re.analytics.gam_reml_optimize_conformance import (  # noqa: E402
    CONTINUOUS_LAMBDA_CLAIM,
    compare_continuous_selection,
)
from polaris_re.core.verification import evidence_markdown, require_parity_evidence  # noqa: E402

DEFAULT_EXCHANGE = REPO_ROOT / "data" / "mgcv_exchange" / "synthetic"

FREE_SP_CELLS: dict[str, str] = {
    "l2-free-sp": "d1",
    "l2-free-sp-factors": "d2",
    "l2-free-sp-kb": "d3",
}
"""Same cell/design map as ``reml_production_check_probe.py`` (PR #204 review
[P2]: read off ``DesignSpec``, not hand-restated where that matters — the
factor flag here is only used to build the matching ``synthetic_cells()``
frame, which is what ``FREE_SP_CELLS`` already names correctly per design)."""

GAMMA_CELL = "l5-gamma"
GAMMA_DESIGN = "d1"
GAMMA_VALUE = 1.4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", type=Path, default=DEFAULT_EXCHANGE)
    parser.add_argument(
        "--python-reference",
        type=Path,
        default=None,
        help="Default: <exchange>/python_reference.json",
    )
    parser.add_argument(
        "--mgcv-reference", type=Path, default=None, help="Default: <exchange>/mgcv_reference.json"
    )
    parser.add_argument(
        "--gtol",
        type=float,
        default=1.0e-8,
        help="Continuous search's own SciPy projected-gradient convergence tolerance.",
    )
    args = parser.parse_args(argv)

    python_path = args.python_reference or args.exchange / "python_reference.json"
    mgcv_path = args.mgcv_reference or args.exchange / "mgcv_reference.json"
    for path, who in ((python_path, "Python"), (mgcv_path, "mgcv")):
        if not path.exists():
            print(
                f"reml_continuous_optimizer_probe.py: missing {who} reference {path}.",
                file=sys.stderr,
            )
            return 1

    bundle = read_exchange(args.exchange)
    python_ref = json.loads(python_path.read_text())
    mgcv_ref = json.loads(mgcv_path.read_text())

    lines: list[str] = []
    lines.append("PLAN slice 4 part B — continuous REML search vs mgcv (ADR-198)")
    lines.append("")
    lines.append(f"exchange: {args.exchange}")
    lines.append(f"python_reference exchange_sha256: {python_ref.get('exchange_sha256')}")
    lines.append(f"mgcv_reference exchange_sha256:   {mgcv_ref.get('exchange_sha256')}")
    lines.append(
        f"mgcv: r_version={mgcv_ref.get('r_version')!r} "
        f"mgcv_version={mgcv_ref.get('mgcv_version')!r}"
    )
    lines.append(f"gtol: {args.gtol:.1e}")
    lines.append("")
    lines.append(evidence_markdown(CONTINUOUS_LAMBDA_CLAIM))
    lines.append("")
    require_parity_evidence(CONTINUOUS_LAMBDA_CLAIM.quantities, claim=CONTINUOUS_LAMBDA_CLAIM.claim)

    lines.append(
        "ADR-198's registered prediction: every free-sp cell's grid-vs-mgcv residual "
        "(0.0645 / 0.0791 / 0.1048 / 0.0776 decades, against a half grid-step of 0.125) "
        "IS the grid's own quantisation — a continuous search on the identical criterion "
        "should drive `max_abs_log10_sp_diff` toward its own convergence tolerance "
        "rather than leaving it near 0.1. Measured either way below."
    )
    lines.append("")
    lines.append(
        "| cell | grid log10(sp) | continuous log10(sp) | mgcv log10(sp) | "
        "grid max_abs_log10_sp_diff | continuous max_abs_log10_sp_diff | closer? | "
        "converged | n_fun_evals | edf_total diff (continuous) |"
    )
    lines.append("|---|---|---|---|---:|---:|---|---|---:|---:|")

    comparisons = []
    for cell_name, design_id in FREE_SP_CELLS.items():
        export = bundle.designs[design_id]
        p_cell = python_ref["cells"][cell_name]
        m_cell = mgcv_ref["cells"][cell_name]
        mgcv_sp = tuple(float(v) for v in m_cell["sp"])
        mgcv_edf_total = float(m_cell["edf_total"])
        grid_log = np.log10(np.asarray(p_cell["sp"], dtype=np.float64))
        gamma = float(p_cell.get("gamma", 1.0))
        comparison = compare_continuous_selection(
            cell_name, export, mgcv_sp, mgcv_edf_total, grid_log, gamma=gamma, gtol=args.gtol
        )
        comparisons.append(comparison)
        closer = (
            "yes"
            if comparison.max_abs_log10_sp_diff < comparison.grid_max_abs_log10_sp_diff
            else "NO"
        )
        lines.append(
            f"| `{cell_name}` | [{comparison.grid_log_lambda[0]:.4f}, "
            f"{comparison.grid_log_lambda[1]:.4f}] | "
            f"[{comparison.selection.log_lambda[0]:.4f}, "
            f"{comparison.selection.log_lambda[1]:.4f}] | "
            f"[{comparison.mgcv_log_lambda[0]:.4f}, {comparison.mgcv_log_lambda[1]:.4f}] | "
            f"{comparison.grid_max_abs_log10_sp_diff:.4e} | "
            f"{comparison.max_abs_log10_sp_diff:.4e} | {closer} | "
            f"{comparison.selection.converged} | {comparison.selection.n_function_evals} | "
            f"{comparison.edf_total_diff:.4e} |"
        )

    # l5-gamma — same shape, gamma=1.4, design d1 only.
    export = bundle.designs[GAMMA_DESIGN]
    p_cell = python_ref["cells"][GAMMA_CELL]
    m_cell = mgcv_ref["cells"][GAMMA_CELL]
    mgcv_sp = tuple(float(v) for v in m_cell["sp"])
    mgcv_edf_total = float(m_cell["edf_total"])
    grid_log = np.log10(np.asarray(p_cell["sp"], dtype=np.float64))
    comparison = compare_continuous_selection(
        GAMMA_CELL, export, mgcv_sp, mgcv_edf_total, grid_log, gamma=GAMMA_VALUE, gtol=args.gtol
    )
    comparisons.append(comparison)
    closer = (
        "yes" if comparison.max_abs_log10_sp_diff < comparison.grid_max_abs_log10_sp_diff else "NO"
    )
    lines.append(
        f"| `{GAMMA_CELL}` | [{comparison.grid_log_lambda[0]:.4f}, "
        f"{comparison.grid_log_lambda[1]:.4f}] | "
        f"[{comparison.selection.log_lambda[0]:.4f}, {comparison.selection.log_lambda[1]:.4f}] | "
        f"[{comparison.mgcv_log_lambda[0]:.4f}, {comparison.mgcv_log_lambda[1]:.4f}] | "
        f"{comparison.grid_max_abs_log10_sp_diff:.4e} | {comparison.max_abs_log10_sp_diff:.4e} | "
        f"{closer} | {comparison.selection.converged} | {comparison.selection.n_function_evals} | "
        f"{comparison.edf_total_diff:.4e} |"
    )
    lines.append("")

    all_closer = all(c.max_abs_log10_sp_diff < c.grid_max_abs_log10_sp_diff for c in comparisons)
    all_converged = all(c.selection.converged for c in comparisons)
    verdict = (
        "ADR-198's prediction HOLDS on every cell"
        if all_closer and all_converged
        else "ADR-198's prediction did NOT hold on every cell — see the table above"
    )
    lines.append(f"**Verdict: {verdict}.**")
    lines.append("")

    report = "\n".join(lines) + "\n"
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

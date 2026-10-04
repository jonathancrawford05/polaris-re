#!/usr/bin/env python3
"""Outer-solver slice 4c (ADR-247): gauntlet case 5, the THREAD axis — each
Newton case fit at BLAS threads 1/2/4 and a repeat at 1, compared with its own
first fit. DIAGNOSTIC, gates nothing.

Usage: gam_newton_thread_axis.py <probe_dir> [report.md]

Provenance (ADR-193): Polaris against ITSELF. There is no mgcv side, so no
VerificationClaim and nothing here is parity evidence; this is a reproducibility
MEASUREMENT (own criterion). The seed axis has no operand: Newton from
``initial.spg`` has no random component.
"""

import json
import sys
from pathlib import Path

from threadpoolctl import threadpool_limits

from polaris_re.analytics.gam_newton_gauntlet_conformance import (
    payloads_from_probe_dir,
    run_thread_axis,
)


def main(probe_dir: Path, out: Path | None) -> None:
    readings = run_thread_axis(
        payloads_from_probe_dir(lambda name: json.loads((probe_dir / name).read_text())),
        lambda n: threadpool_limits(limits=n, user_api="blas"),
    )
    lines = [
        "",
        "### Outer-solver slice 4c — gauntlet case 5: the thread axis (Newton, one start)",
        "",
        "**MEASUREMENT (own criterion), NOT parity evidence (ADR-193):** Polaris against "
        "itself across BLAS threads 1/2/4 and a repeat at 1; each row compares every fit "
        "with that case's first. No mgcv value is read. Seed axis: no operand for Newton.",
        "",
        "| case | max d eta | max d log10(sp) | max d edf_total | converged | fits per run "
        "| error |",
        "|---|---:|---:|---:|---|---|---|",
        *[
            f"| {r.case} | {r.max_abs_eta_diff:.3e} | {r.max_abs_log10_sp_diff:.3e} "
            f"| {r.max_abs_edf_total_diff:.3e} | {r.all_converged} | {list(r.n_function_evals)} "
            f"| {r.error or ''} |"
            for r in readings
        ],
        "",
        "ADR-222 amendment 1 beside it (multistart(9) + L-BFGS-B, select=TRUE N=7, "
        "cross-thread): max d eta 0.356, d edf_total 10.002.",
        "",
    ]
    report = "\n".join(lines)
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)

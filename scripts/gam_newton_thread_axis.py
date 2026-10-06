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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from threadpoolctl import threadpool_info, threadpool_limits

from polaris_re.analytics.gam_newton_gauntlet_conformance import (
    payloads_from_probe_dir,
    run_thread_axis,
)


def main(probe_dir: Path, out: Path | None) -> None:
    effective: dict[int, set[int]] = {}

    @contextmanager
    def limit(n: int) -> Iterator[None]:
        # Record the BLAS thread counts actually in force (PR #256 review P2-1): a
        # requested limit does not mean a multithreaded path was exercised.
        with threadpool_limits(limits=n, user_api="blas"):
            effective.setdefault(n, set()).update(
                int(i["num_threads"]) for i in threadpool_info() if i["user_api"] == "blas"
            )
            yield

    readings = run_thread_axis(
        payloads_from_probe_dir(lambda name: json.loads((probe_dir / name).read_text())),
        limit,
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
        "BLAS threads in force per requested limit (from `threadpool_info()`): "
        + ", ".join(f"{k} -> {sorted(v)}" for k, v in sorted(effective.items()))
        + ". OpenBLAS runs small operations single-threaded whatever the limit, so rows at "
        "~1e-13 may never have taken a multithreaded path: they show that path was not "
        "exercised, not that the fit is reproducible there. The informative rows are the "
        "ones with a nonzero movement (gaussian L1, `select=TRUE`).",
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

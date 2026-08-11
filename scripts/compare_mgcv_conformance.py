#!/usr/bin/env python3
"""
compare_mgcv_conformance.py — read both sides, verify the hash, print the verdict.

Slice 5 of `docs/PLAN_penalized_mi_surface.md`, and the **second** of the runbook's two
commands. Consumes `python_reference.json` (from `export_mgcv_case.py`) and
`mgcv_reference.json` (from `mgcv_conformance.R`), and emits a pass/fail table plus the
committed comparison report.

**The hash guard is the point of this script existing separately from the exporter.**
Both references record the exchange digest they were computed from; this recomputes it
from the files on disk and refuses to compare if either disagrees. The worst failure
mode available in this construction is iterating against a stale reference and declaring
parity with a file R never saw — silent, confident, and wrong, which is the exact class
of defect this epic keeps catching in its own work.

**Only derived scalars reach the report** — max absolute coefficient difference, edf
differences, sp ratios. That is what lets the HMD/ILEC comparison be committed while
their exchange files stay in the maintainer's working directory (`DATA_LICENSING.md` §1).

CI never grows an R dependency. This is a script rather than a test for that reason, and
`tests/test_analytics/test_experience_mgcv_conformance.py` covers the comparator's own
arithmetic against a known-agreement and a seeded known-disagreement reference so it can
actually fail.

Usage:
    uv run python scripts/compare_mgcv_conformance.py \
        --exchange data/mgcv_exchange/synthetic \
        --markdown docs/MEASUREMENT_mgcv_conformance.md

Exit status: 0 if every level agrees within its stated tolerance, 2 if any disagrees
(a disagreement is a **result** — PLAN Anchor 8 — so it is distinguished from 1, which
is a failure to compare at all).
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.analytics.experience_mgcv_conformance import (  # noqa: E402
    compare_reference,
    render_comparison_markdown,
)
from polaris_re.core.exceptions import PolarisValidationError  # noqa: E402

DEFAULT_EXCHANGE = REPO_ROOT / "data" / "mgcv_exchange" / "synthetic"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="compare_mgcv_conformance.py",
        description="Compare the Python and mgcv references for one conformance exchange.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--exchange",
        type=Path,
        default=DEFAULT_EXCHANGE,
        help=f"Exchange directory holding both reference files. Default: {DEFAULT_EXCHANGE}.",
    )
    parser.add_argument("--python-reference", type=Path, default=None)
    parser.add_argument("--mgcv-reference", type=Path, default=None)
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Write the committed comparison report here (derived scalars only).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write the comparison as JSON here.",
    )
    args = parser.parse_args(argv)

    python_path = args.python_reference or args.exchange / "python_reference.json"
    mgcv_path = args.mgcv_reference or args.exchange / "mgcv_reference.json"
    for path, who in ((python_path, "Python"), (mgcv_path, "mgcv")):
        if not path.exists():
            print(
                f"compare_mgcv_conformance.py: the {who} reference {path} does not "
                f"exist. See docs/RUNBOOK_mgcv_conformance.md for the two commands that "
                f"produce them.",
                file=sys.stderr,
            )
            return 1

    try:
        comparison = compare_reference(
            args.exchange,
            json.loads(python_path.read_text()),
            json.loads(mgcv_path.read_text()),
        )
    except PolarisValidationError as exc:
        print(f"compare_mgcv_conformance.py: {exc}", file=sys.stderr)
        return 1

    width = max(len(c.name) for c in comparison.cells)
    for cell in comparison.cells:
        for check in cell.checks:
            flag = "PASS" if check.passed else "FAIL"
            print(
                f"{flag}  {cell.name:<{width}}  {check.metric:<36s} "
                f"{check.value: .4e}  (tol {check.tolerance:.1e})"
            )
    for check in comparison.structural:
        flag = "PASS" if check.passed else "FAIL"
        print(f"{flag}  {'(cross-cell)':<{width}}  {check.metric:<36s} {check.value: .4e}")
    print()
    for level, ok in comparison.levels_settled().items():
        print(f"level {level}: {'AGREES' if ok else 'DISAGREES'}")
    print()
    for cell in comparison.cells:
        for note in cell.notes:
            print(f"note: {note}")

    if args.markdown is not None:
        args.markdown.write_text(render_comparison_markdown(comparison))
        print(f"\nreport {args.markdown}")
    if args.output is not None:
        args.output.write_text(
            json.dumps(
                {
                    "case": comparison.case,
                    "exchange_sha256": comparison.exchange_sha256,
                    "mgcv_version": comparison.mgcv_version,
                    "passed": comparison.passed,
                    "levels_settled": {str(k): v for k, v in comparison.levels_settled().items()},
                    "cells": [
                        {
                            "name": cell.name,
                            "design": cell.design_id,
                            "checks": [
                                {
                                    "metric": c.metric,
                                    "level": c.level,
                                    "value": c.value,
                                    "tolerance": c.tolerance,
                                    "passed": c.passed,
                                }
                                for c in cell.checks
                            ],
                            "notes": list(cell.notes),
                        }
                        for cell in comparison.cells
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        print(f"json   {args.output}")

    return 0 if comparison.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

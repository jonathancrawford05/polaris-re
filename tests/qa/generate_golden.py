"""Generate golden output baselines — config-driven.

Enumerates every ``data/qa/golden_config_*.json``, prices the shared golden
inforce block through the same parser/pipeline the CLI uses, and writes one
baseline per config to ``tests/qa/golden_outputs/``. Run this when the golden
configs or the projection engine change, then commit the regenerated files.

Adding a new ``data/qa/golden_config_<name>.json`` is automatically picked up
here (and guarded by ``test_pipeline_golden.py::test_every_config_has_committed_baseline``,
which fails until its baseline is committed).

Usage:
    uv run python tests/qa/generate_golden.py
    uv run python tests/qa/generate_golden.py --flat-only  # CI mode (no SOA tables)
"""

import argparse

# Run as a script: this file's own directory is on sys.path[0], so the sibling
# module imports directly. (Under pytest the package-relative form is used.)
from golden_runner import (
    discover_golden_cases,
    has_soa_tables,
    load_inputs,
    run_pricing,
    save_golden,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flat-only",
        action="store_true",
        help="Only generate baselines for flat-mortality configs (no SOA tables)",
    )
    args = parser.parse_args()

    soa_available = has_soa_tables()
    generated = 0
    for case in discover_golden_cases():
        if case.needs_soa and (args.flat_only or not soa_available):
            reason = "--flat-only" if args.flat_only else "SOA tables not found"
            print(f"SKIP {case.name}: needs SOA tables ({reason})")
            continue
        results = run_pricing(load_inputs(case))
        path = save_golden(results, case.name)
        print(f"OK {case.name}: {len(results)} cohorts -> {path}")
        generated += 1

    print(f"\nDone. Generated {generated} baseline(s). Commit tests/qa/golden_outputs/.")


if __name__ == "__main__":
    main()

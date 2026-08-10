#!/usr/bin/env python3
"""
export_mgcv_case.py — write the exchange file the ``mgcv`` conformance run consumes.

Slice 5 of `docs/PLAN_penalized_mi_surface.md`. Three quantities the penalized MI
estimator reports are **adopted from mgcv and unverified** (PLAN Anchor 8): ``tr(F)`` as
the per-term EDF, the Kass-Steffey unconditional covariance, and Wood's ``gamma``. One R
run settles all three. This script writes what that run reads, plus our own answers, so
the implementer can iterate offline against a committed reference afterwards.

    exchange (TSV + JSON manifest)  ──►  scripts/mgcv_conformance.R  ──►  reference JSON
                │                                                              │
                └──────────►  python_reference.json  ──►  compare_mgcv_conformance.py

**Two commands for the maintainer**, and they are in
`docs/RUNBOOK_mgcv_conformance.md`. This is the first.

Cases
-----
``synthetic`` (default) is generated from a pinned seed and both its exchange and its
reference are **committed**, so the primary conformance run needs no data at all.

``hmd-usa`` and ``ilec-banded`` are cell-grain experience. Their exchange is written to
the maintainer's local working directory and **never committed** (`DATA_LICENSING.md`
§1, Design Anchor 6); only the comparison report comes back. They read a grouped-cells
file rather than re-implementing the diligence harness's ingest — see the runbook for
the six lines that produce one, and ADR-189 for why a second ingest path was rejected.

Usage:
    # the committed synthetic case (idempotent — pinned seed, no wall clock)
    uv run python scripts/export_mgcv_case.py --case synthetic \
        -o data/mgcv_exchange/synthetic

    # a real-data scale check, local only
    uv run python scripts/export_mgcv_case.py --case ilec-banded \
        --cells ~/work/ilec_cells.parquet -o ~/work/mgcv_exchange/ilec

Exit status: 0 on success, 1 on a validation failure.
"""

import argparse
import sys
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.analytics.experience_mgcv_conformance import (  # noqa: E402
    CONFORMANCE_CELLS,
    DESIGNS,
    REAL_DATA_CASES,
    SYNTHETIC_CASE,
    SYNTHETIC_SEED,
    DesignSpec,
    build_exchange,
    exchange_hash,
    python_reference,
    synthetic_cells,
    write_exchange,
    write_python_reference,
)
from polaris_re.core.exceptions import PolarisValidationError  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "data" / "mgcv_exchange" / "synthetic"


def _load_cells(path: Path) -> pl.DataFrame:
    """Read a grouped-cells file in the canonical contract (parquet or CSV)."""
    if not path.exists():
        raise PolarisValidationError(f"Cells file {path} does not exist.")
    frame = pl.read_parquet(path) if path.suffix == ".parquet" else pl.read_csv(path)
    required = {"attained_age", "calendar_year", "q_base"}
    missing = required - set(frame.columns)
    if missing:
        raise PolarisValidationError(
            f"{path} is missing canonical grouped-cell columns {sorted(missing)}. The "
            f"runbook's snippet produces a frame with all of them — a file that has "
            f"exposure and deaths but no q_base has not been through "
            f"attach_empirical_base()."
        )
    return frame


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="export_mgcv_case.py",
        description=(
            "Write the mgcv conformance exchange (TSV + JSON manifest) and our own "
            "reference for the same cells."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--case",
        default=SYNTHETIC_CASE,
        choices=(SYNTHETIC_CASE, *REAL_DATA_CASES),
        help=(
            "synthetic = pinned seed, committed. hmd-usa / ilec-banded = cell-grain "
            "experience, local only, and they require --cells."
        ),
    )
    parser.add_argument(
        "--cells",
        type=Path,
        default=None,
        help=(
            "Grouped-cells parquet/CSV in the canonical contract (with q_base). "
            "Required for the real-data cases, refused for synthetic."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=f"Exchange directory. Default for the synthetic case: {DEFAULT_OUTPUT}.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SYNTHETIC_SEED,
        help="Pinned RNG seed for the synthetic Poisson draw (never the wall clock).",
    )
    parser.add_argument(
        "--no-python-reference",
        action="store_true",
        help=(
            "Write only the exchange. The reference costs a few seconds of fitting and "
            "is what the comparator reads, so this is for inspecting the exchange alone."
        ),
    )
    args = parser.parse_args(argv)

    try:
        if args.case == SYNTHETIC_CASE:
            if args.cells is not None:
                raise PolarisValidationError(
                    "--cells is refused for the synthetic case: its whole point is that "
                    "the exchange is reproducible from a pinned seed, and a supplied "
                    "frame would make the committed files unverifiable."
                )
            output = args.output or DEFAULT_OUTPUT

            def cells_for(spec: DesignSpec) -> pl.DataFrame:
                return synthetic_cells(with_factor=spec.with_factor, seed=args.seed)
        else:
            if args.cells is None:
                raise PolarisValidationError(
                    f"--case {args.case} needs --cells: the loaders are not re-run here, "
                    f"so the grouped cells (with q_base) come from a file. See "
                    f"docs/RUNBOOK_mgcv_conformance.md."
                )
            if args.output is None:
                raise PolarisValidationError(
                    f"--case {args.case} needs an explicit -o OUTSIDE the repository. "
                    f"Its exchange is cell-grain experience and must not be committed "
                    f"(DATA_LICENSING.md §1)."
                )
            output = args.output
            frame = _load_cells(args.cells)
            has_factor = any(
                spec.with_factor for spec in DESIGNS
            )  # only to decide whether to warn below

            def cells_for(spec: DesignSpec) -> pl.DataFrame:
                return frame

            if has_factor:
                print(
                    "NOTE: designs that ask for a factor block will use whatever factor "
                    "columns the supplied cells carry, which may be none — the "
                    "manifest records what was actually found per design.",
                    file=sys.stderr,
                )

        bundle = build_exchange(
            args.case,
            cells_for=cells_for,
            seed=args.seed,
            designs=DESIGNS,
            conformance_cells=CONFORMANCE_CELLS,
        )
        digest = write_exchange(bundle, output)
        print(f"exchange   {output}  sha256 {digest}")
        for design_id, export in bundle.designs.items():
            print(
                f"  {design_id}: {export.n_cells} cells x {export.n_coef} coef "
                f"(tensor {export.n_tensor}, factors {list(export.factors) or 'none'}), "
                f"k=({export.spec.k_age}, {export.spec.k_year})"
            )
        if not args.no_python_reference:
            results = python_reference(bundle, cells_for=cells_for, seed=args.seed)
            path = write_python_reference(results, output, exchange_digest=digest, case=args.case)
            print(f"python ref {path}  ({len(results)} cells)")
            worst = max(r.penalized_score_inf_norm for r in results)
            print(
                f"  penalized score ||X'(y-mu) - S.beta||_inf, worst cell: {worst:.3e} "
                f"— near zero is the R-free proof that these coefficients are the "
                f"unique penalized MLE of the exported problem."
            )
            for r in results:
                if r.lambda_at_bound:
                    print(
                        f"  WARNING {r.name}: selected lambda sits on the search bound, "
                        f"so level 2 reads 'at least this' rather than 'this'.",
                        file=sys.stderr,
                    )
        # Recompute rather than trust: the digest above was returned by the writer, and
        # a hash the reader cannot reproduce is not a guard.
        if exchange_hash(output) != digest:  # pragma: no cover - defensive
            raise PolarisValidationError(f"The exchange at {output} does not re-hash to {digest}.")
    except PolarisValidationError as exc:
        print(f"export_mgcv_case.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
experience_diligence.py — fit the tensor MI surface to REAL experience and report.

Slice 1 of `docs/PLAN_experience_gam_realdata.md`. The A4' epic validated the
tensor GAM exclusively against synthetic data with an injected surface; this is
the harness that runs it against HMD population or SOA-ILEC insured experience
and emits a **committable findings report**.

The division of labour is structural, not a phase (PLAN §3): you run this, the
routine commits the findings. Licensed data never enters the repo, the Docker
image, or CI — see `docs/RUNBOOK_experience_data_acquisition.md` for acquisition.
Nothing here reads or writes anything inside the repo tree; input comes from
$POLARIS_EXPERIENCE_CACHE_DIR and output goes wherever you point -o.

What the report is *for*: PLAN §2 names in advance what the fit could fail to
reproduce — the post-2010 US improvement slowdown, and (on ILEC) agreement with
SOA's own published expected deaths. **A run that reports "no slowdown" is a
successful run.** Nothing here tunes anything until it agrees.

No plots: numbers and tables commit and diff, images do not. And two runs over
the same cache produce byte-identical JSON — no timestamps, and floats rounded
below the run-to-run jitter that multithreaded BLAS puts into the delta-method
band — so a committed finding diffs cleanly against a re-run.

Usage:
    # HMD population — the primary fixture. Stop at 2019: a smooth surface
    # fitted through the COVID shock attributes it to improvement.
    uv run python scripts/experience_diligence.py --source hmd \
        --country USA --min-year 1990 --max-year 2019 \
        -o hmd_usa.json --markdown hmd_usa.md

    # SOA-ILEC insured experience, with SOA's own expected deaths as the
    # independent A/E denominator (2012-2019 release: tab-delimited).
    uv run python scripts/experience_diligence.py --source ilec \
        -o ilec.json --markdown ilec.md

    # A coarser or finer aggregation level, stated in the report either way:
    uv run python scripts/experience_diligence.py --source ilec \
        --group-by attained_age calendar_year sex smoker

Exit status: 0 on a completed run (whatever its verdict), 2 on a missing or
ambiguous data cache, 1 on any other failure.
"""

import argparse
import sys
from pathlib import Path

# Allow "uv run python scripts/experience_diligence.py" without an editable install.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.analytics.experience_diligence import (  # noqa: E402
    DEFAULT_DURATION_BAND_EDGES,
    DEFAULT_REFERENCE_AGES,
    HMD_GROUP_KEYS,
    ILEC_GROUP_KEYS,
    ILEC_VINTAGES,
    RUNBOOK_PATH,
    ExperienceCacheMissingError,
    render_markdown,
    run_diligence,
)
from polaris_re.core.exceptions import (  # noqa: E402
    PolarisComputationError,
    PolarisValidationError,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_DATA = 2


def _window(text: str) -> tuple[int, int]:
    """Parse a ``START:END`` calendar window."""
    parts = text.replace("-", ":").split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"expected START:END, got {text!r}")
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"non-integer year in {text!r}") from exc
    return start, end


def build_parser() -> argparse.ArgumentParser:
    """The command-line contract."""
    parser = argparse.ArgumentParser(
        prog="experience_diligence.py",
        description=(
            "Fit the tensor mortality-improvement surface to real HMD or SOA-ILEC "
            "experience and emit a findings report (JSON + Markdown). Reads from the "
            f"local experience cache only — see {RUNBOOK_PATH}."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=("hmd", "ilec"),
        required=True,
        help="hmd = population (free, registration); ilec = SOA insured (manual download).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help=(
            "Experience cache root. Default: $POLARIS_EXPERIENCE_CACHE_DIR, else "
            "$POLARIS_DATA_DIR/experience_cache, else ./data/experience_cache."
        ),
    )
    parser.add_argument(
        "--country",
        default="USA",
        help="HMD country code (USA, GBRTENW, CAN, ...). Ignored for --source ilec.",
    )
    parser.add_argument(
        "--ilec-file",
        default=None,
        help=(
            "ILEC file name inside {cache}/ilec/. Required when the directory holds "
            "more than one candidate — guessing between vintages would silently "
            "produce findings about the wrong release."
        ),
    )
    parser.add_argument(
        "--ilec-vintage",
        choices=tuple(ILEC_VINTAGES),
        default="2012-19",
        help=(
            "Selects the header spelling AND the delimiter. The 2012-19 release is "
            "tab-delimited despite its .txt name."
        ),
    )
    parser.add_argument(
        "--separator",
        default=None,
        help="Override the vintage's field delimiter (e.g. '\\t').",
    )
    parser.add_argument(
        "--no-expected",
        action="store_true",
        help=(
            "Skip SOA's published expected deaths. Only for a vintage that does not "
            "publish them — they are the independent A/E denominator and the "
            "strongest check in the report."
        ),
    )
    parser.add_argument("--basis", choices=("count", "amount"), default="count")
    parser.add_argument("--min-year", type=int, default=None)
    parser.add_argument(
        "--max-year",
        type=int,
        default=None,
        help=(
            "Inclusive. Pass 2019 on HMD: a smooth tensor surface fitted through the "
            "COVID shock attributes it to improvement, which is wrong."
        ),
    )
    parser.add_argument("--min-age", type=int, default=25)
    parser.add_argument("--max-age", type=int, default=95)
    parser.add_argument(
        "--group-by",
        nargs="+",
        default=None,
        metavar="KEY",
        help=(
            "Aggregation level, stated in the report either way. Defaults: "
            f"HMD {list(HMD_GROUP_KEYS)}; ILEC {list(ILEC_GROUP_KEYS)} — which keeps "
            "smoker and uw_class, because pooling those merges populations with "
            "genuinely different mortality."
        ),
    )
    parser.add_argument(
        "--reference-ages",
        nargs="+",
        type=int,
        default=list(DEFAULT_REFERENCE_AGES),
        metavar="AGE",
    )
    parser.add_argument(
        "--early-window",
        type=_window,
        default=None,
        metavar="START:END",
        help="Early comparison window. Default: first 10 observed years (or first half).",
    )
    parser.add_argument(
        "--late-window",
        type=_window,
        default=None,
        metavar="START:END",
        help="Late comparison window. Default: last 10 observed years (or second half).",
    )
    parser.add_argument("--age-df", type=int, default=6)
    parser.add_argument(
        "--year-df",
        type=int,
        default=4,
        help=(
            "Spline df for the calendar margin. A SHORT window cannot support a "
            "large value: the ILEC 2012-2019 release is 8 years, and 4 there bends "
            "at the boundary and spikes the terminal year. A margin carries "
            "df - degree interior knots, so df == degree is a global polynomial "
            "rather than a spline. To make the trend LESS flexible, lower "
            "--year-degree, not this. The report warns when this is large."
        ),
    )
    parser.add_argument("--age-degree", type=int, default=3)
    parser.add_argument(
        "--year-degree",
        type=int,
        default=3,
        help=(
            "Polynomial degree of the calendar margin: 1 piecewise-linear, 3 cubic "
            "(default, and what every committed report used). THIS is the knob for "
            "a short window. With --year-df 1 --year-degree 1 the trend is a global "
            "straight line and fitted MI is constant in time by construction, which "
            "cannot manufacture the swing an unpenalized cubic produces wherever "
            "deaths are scarce (ADR-184). The cost is that a genuine change in the "
            "improvement rate becomes invisible too -- see "
            "docs/MEASUREMENT_gam_ramp_mechanism.md before using it."
        ),
    )
    parser.add_argument("--duration-degree", type=int, default=3)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument(
        "--overdispersion",
        choices=("auto", "on", "off"),
        default="auto",
        help=(
            "auto (default) applies the quasi-Poisson covariance scaling whenever "
            "the Pearson dispersion exceeds 1. Real experience is never Poisson — "
            "HMD 1990-2019 comes back at phi=21.8, which would understate every "
            "band by 4.7x. Scaling changes the covariance, never the surface."
        ),
    )
    parser.add_argument(
        "--duration-bands",
        action="store_true",
        help=(
            "Control for duration mix using banded policy years "
            f"{list(DEFAULT_DURATION_BAND_EDGES)} — 1/2/3 singly, then 4-5, 6-10, "
            "11-15, 16-20, 21-25, 26+, aligned to VBT 2015's 25-year select period. "
            "Costs ~9x the cells; raw duration_months in --group-by would cost ~60x "
            "for a dimension whose signal is a smooth selection curve. Watch "
            "n_strata_dropped in the report: banding multiplies base strata too."
        ),
    )
    parser.add_argument(
        "--duration-band-edges",
        nargs="+",
        type=int,
        default=None,
        metavar="YEAR",
        help=(
            "Custom band start policy years, ascending, starting at 1. Implies "
            "--duration-bands. Use fewer bands if n_strata_dropped is material."
        ),
    )
    parser.add_argument("--duration-df", type=int, default=4)
    parser.add_argument(
        "--keep-unknown-uw-class",
        action="store_true",
        help=(
            "Keep ILEC uw_class == 'U' rows. Off by default: 'U' is the missing-data "
            "sentinel, not a stratum ('NA' — no preferred structure — is a stratum "
            "and is always kept)."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write the JSON report here. Defaults to stdout.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Also write the Markdown rendering here — the committable artefact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the harness. Returns the process exit status."""
    args = build_parser().parse_args(argv)

    if args.duration_band_edges:
        duration_band_edges = tuple(args.duration_band_edges)
    elif args.duration_bands:
        duration_band_edges = DEFAULT_DURATION_BAND_EDGES
    else:
        duration_band_edges = None

    try:
        report = run_diligence(
            source=args.source,
            cache_dir=args.cache_dir,
            country=args.country,
            ilec_filename=args.ilec_file,
            ilec_vintage=args.ilec_vintage,
            ilec_separator=args.separator,
            include_expected=not args.no_expected,
            basis=args.basis,
            min_year=args.min_year,
            max_year=args.max_year,
            min_age=args.min_age,
            max_age=args.max_age,
            group_keys=tuple(args.group_by) if args.group_by else None,
            reference_ages=tuple(args.reference_ages),
            early_window=args.early_window,
            late_window=args.late_window,
            age_df=args.age_df,
            year_df=args.year_df,
            age_degree=args.age_degree,
            year_degree=args.year_degree,
            duration_degree=args.duration_degree,
            confidence_level=args.confidence_level,
            overdispersion=args.overdispersion,
            duration_band_edges=duration_band_edges,
            duration_df=args.duration_df,
            keep_unknown_uw_class=args.keep_unknown_uw_class,
        )
    except ExperienceCacheMissingError as exc:
        # A missing cache is the expected first-run outcome, and it deserves a
        # sentence rather than a traceback. Classified by exception TYPE — the
        # first cut matched on message wording and silently missed the ILEC
        # missing-directory case, which is the one a maintainer meets first
        # (PR #185 review [P1]).
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_NO_DATA
    except PolarisValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except PolarisComputationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    payload = report.to_json()
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"JSON report: {args.output}", file=sys.stderr)
    else:
        print(payload)

    if args.markdown is not None:
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
        print(f"Markdown report: {args.markdown}", file=sys.stderr)

    if report.window_comparison is not None:
        print(
            f"slowdown test: {report.window_comparison.verdict} "
            f"({report.window_comparison.n_ages_slower}/"
            f"{report.window_comparison.n_ages} reference ages slower)",
            file=sys.stderr,
        )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

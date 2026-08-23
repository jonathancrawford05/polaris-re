#!/usr/bin/env python3
"""
measurement_stamp.py — stamp and check provenance on committed measurement documents.

ADR-203 found a committed measurement carrying figures that no longer reproduced,
invalidated by a *correct* production fix that nothing re-ran. This is the gate that
makes that visible. See `polaris_re.utils.measurement_provenance` for what a stamp is
and — more importantly — what it is not.

## Commands

    # CI: fail on drift, warn on unstamped
    uv run python scripts/measurement_stamp.py check

    # Regenerate the document here and stamp it (strongest form)
    uv run python scripts/measurement_stamp.py stamp \
        docs/MEASUREMENT_unconditional_coverage.md --run

    # Stamp a document regenerated elsewhere — e.g. a session holding the experience
    # cache. The note is REQUIRED and is carried in the document.
    uv run python scripts/measurement_stamp.py stamp docs/MEASUREMENT_experience_gam_hmd.md \
        --assert --note "regenerated 2026-08-23 in a session with the HMD cache at v2026.1"

    # What is the state of everything?
    uv run python scripts/measurement_stamp.py list

## Why unstamped warns rather than fails

Four documents were already at risk when this landed, two of which cannot be
regenerated without the experience cache. A gate that failed the build on day one for
all of them is a gate somebody disables inside a week, and a disabled gate catches
nothing. So the rule is narrow and enforceable: **fail only when a document we have
vouched for has drifted.** Unstamped is reported on every run and is visible in
`list`; it is a backlog, not a build break.

Exit status: 0 if no document has drifted, 1 if any has, 2 on a usage error.
"""

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from polaris_re.utils.measurement_provenance import (  # noqa: E402
    MANIFEST,
    MeasurementSource,
    Stamp,
    StampMethod,
    StampStatus,
    check_manifest,
    closure_fingerprint,
    dependency_closure,
    format_stamp,
    git_head,
    strip_stamp,
)

_SYMBOL = {
    StampStatus.OK: "ok      ",
    StampStatus.DRIFTED: "DRIFTED ",
    StampStatus.UNSTAMPED: "unstamped",
    StampStatus.MISSING: "MISSING ",
}


def _source_for(document: str) -> MeasurementSource:
    for source in MANIFEST:
        if source.document == document:
            return source
    known = "\n  ".join(s.document for s in MANIFEST)
    raise SystemExit(
        f"{document} is not in the manifest. Add it to "
        f"`polaris_re.utils.measurement_provenance.MANIFEST` first — a document "
        f"stamped without a manifest entry would never be checked.\nKnown:\n  {known}"
    )


def command_check(_: argparse.Namespace) -> int:
    findings = check_manifest(REPO_ROOT)
    drifted = [f for f in findings if f.status is StampStatus.DRIFTED]
    missing = [f for f in findings if f.status is StampStatus.MISSING]
    unstamped = [f for f in findings if f.status is StampStatus.UNSTAMPED]

    for finding in findings:
        print(f"{_SYMBOL[finding.status]} {finding.document}")
        if finding.status is not StampStatus.OK:
            print(f"          {finding.detail}")

    print()
    print(
        f"{len(findings) - len(drifted) - len(missing) - len(unstamped)} ok, "
        f"{len(unstamped)} unstamped, {len(missing)} missing, {len(drifted)} drifted"
    )
    if unstamped:
        print(
            "\nUnstamped documents are a backlog, not a build break — see this "
            "script's docstring for why."
        )
    if missing:
        print("\nA MISSING row is a manifest bug: it names a path that is not there.")
    if drifted:
        print(
            "\nFAIL: a document we vouched for no longer matches the code that "
            "produced it. This is exactly the ADR-203 condition."
        )
        return 1
    return 0


def command_list(_: argparse.Namespace) -> int:
    for finding in check_manifest(REPO_ROOT):
        source = _source_for(finding.document)
        cache = " [needs experience cache]" if source.requires_experience_cache else ""
        method = f" ({finding.stamp.method.value})" if finding.stamp else ""
        print(f"{_SYMBOL[finding.status]} {finding.document}{method}{cache}")
        print(f"          producer: {source.producer}")
        if source.note:
            print(f"          note: {source.note}")
    return 0


def command_stamp(args: argparse.Namespace) -> int:
    source = _source_for(args.document)
    document = REPO_ROOT / source.document

    if args.run:
        if source.requires_experience_cache:
            print(
                f"{source.document} needs the local experience cache, which is not "
                "in the repository. Regenerate it in a session that has the cache "
                "and stamp with --assert --note '...' instead.",
                file=sys.stderr,
            )
            return 2
        print(f"running: {source.regeneration}")
        result = subprocess.run(source.regeneration, shell=True, cwd=REPO_ROOT, check=False)
        if result.returncode != 0:
            print(
                f"regeneration exited {result.returncode}; not stamping. A stamp on a "
                "document whose producer just failed would be a false vouching.",
                file=sys.stderr,
            )
            return 2
        method = StampMethod.REGENERATED
    else:
        method = StampMethod.ASSERTED

    if not document.is_file():
        print(f"{source.document} does not exist.", file=sys.stderr)
        return 2

    fingerprint = closure_fingerprint(
        dependency_closure(REPO_ROOT / source.producer, REPO_ROOT), REPO_ROOT
    )
    stamp = Stamp(
        fingerprint=fingerprint,
        generated=datetime.now(UTC).date().isoformat(),
        producer=source.producer,
        method=method,
        note=args.note or "",
        head=git_head(REPO_ROOT),
    )
    body = strip_stamp(document.read_text(encoding="utf-8")).rstrip("\n")
    document.write_text(body + "\n\n" + format_stamp(stamp), encoding="utf-8")
    print(f"stamped {source.document}: {fingerprint[:12]} ({method.value})")
    if method is StampMethod.ASSERTED:
        print(
            "  Recorded as ASSERTED — weaker than a regeneration done here, and the "
            "document says so."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measurement_stamp.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="verify every stamp; exit 1 on drift").set_defaults(
        handler=command_check
    )
    sub.add_parser("list", help="show every manifest entry and its state").set_defaults(
        handler=command_list
    )

    stamp = sub.add_parser("stamp", help="write or refresh a document's stamp")
    stamp.add_argument("document", help="repository-relative path, as it appears in the manifest")
    mode = stamp.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--run",
        action="store_true",
        help="regenerate the document here, then stamp it (method: regenerated)",
    )
    mode.add_argument(
        "--assert",
        dest="assert_",
        action="store_true",
        help="stamp a document regenerated elsewhere (method: asserted); requires --note",
    )
    stamp.add_argument(
        "--note", default=None, help="required with --assert; carried in the document"
    )
    stamp.set_defaults(handler=command_stamp)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "stamp" and args.assert_ and not (args.note or "").strip():
        print(
            "--assert requires --note. An asserted stamp is one person's word that a "
            "regeneration happened somewhere this checkout cannot see; without the "
            "note, a reader has no way to judge it.",
            file=sys.stderr,
        )
        return 2
    handler = args.handler
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

"""Provenance stamps for committed measurement documents.

**Why this exists.** ADR-203 found `docs/MEASUREMENT_unconditional_coverage.md`
carrying figures that no longer reproduced. The cause was `ce0b9f1`, a *correct*
maintainer-authorized fix to `experience_gam_penalized.reml_score` that changed
the REML criterion and therefore the selected lambda on every replicate. Nothing
re-ran the study, so a committed measurement was silently invalidated and stayed
cited as current for four days across seven documents — including the very ADR
whose registered prediction was being tested against it.

The defect was never in the fix. It was that **a measurement document with no
re-run trigger is a snapshot wearing the clothes of a fact**.

## What a stamp is

The SHA-256 of the *transitive* ``polaris_re`` import closure of the document's
producer, over file contents. If any module the producer reaches changes, the
fingerprint changes, and :func:`check_manifest` says so.

Content hashing rather than commit dates, deliberately: ADR-203's audit used
dates and could not distinguish two same-day commits, which is precisely the
resolution the `ce0b9f1` case needed. Contents rather than git blob hashes so an
uncommitted working-tree edit is caught too — a developer who edits the fitter
and regenerates nothing should see the gate before CI does.

## What a stamp is not

It is **not** evidence the numbers are right. It says only that the code the
document was generated from is the code that is here now. A stamp on a wrong
measurement is a stamp on a wrong measurement.

Nor is it a re-run. Re-running is what :func:`MeasurementSource.regeneration`
describes and what an operator does; the stamp records that it happened and
against what.

## The two honest verification methods

Some documents cannot be regenerated in CI at all — `MEASUREMENT_experience_gam_hmd`
and `..._ilec` read a local experience cache that is not in the repository (see
`docs/RUNBOOK_experience_data_acquisition.md`). Pretending otherwise would make
the gate lie, so :class:`StampMethod` records which of two things happened:

* ``regenerated`` — the stamping tool ran the producer itself, here, now.
* ``asserted`` — an operator with the inputs regenerated it elsewhere and says
  so, in a note that is required and carried in the document.

A reader can tell the difference, which is the whole point. An ``asserted``
stamp is weaker evidence than a ``regenerated`` one and the document says which
it holds.
"""

import ast
import hashlib
import re
import subprocess
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "MANIFEST",
    "Finding",
    "MeasurementSource",
    "Stamp",
    "StampMethod",
    "StampStatus",
    "check_manifest",
    "closure_fingerprint",
    "dependency_closure",
    "format_stamp",
    "git_head",
    "parse_stamp",
    "strip_stamp",
]

_STAMP_OPEN = "<!-- measurement-provenance"
_STAMP_CLOSE = "-->"
_STAMP_PATTERN = re.compile(
    re.escape(_STAMP_OPEN) + r"\n(?P<body>.*?)\n" + re.escape(_STAMP_CLOSE) + r"\n?",
    re.DOTALL,
)


class StampMethod(StrEnum):
    """How the stamped document was verified against the code it names."""

    REGENERATED = "regenerated"
    """The stamping tool ran the producer in this checkout. Strongest form."""

    ASSERTED = "asserted"
    """An operator regenerated it elsewhere — typically a session holding the
    experience cache — and recorded a note saying so. Weaker, and labelled."""


class StampStatus(StrEnum):
    """The verdict :func:`check_manifest` reaches for one document."""

    OK = "ok"
    """Stamped, and the closure fingerprint still matches."""

    DRIFTED = "drifted"
    """Stamped, and the closure has changed since. **This is the failure.**"""

    UNSTAMPED = "unstamped"
    """No stamp. Reported, never fatal — see :func:`check_manifest`."""

    MISSING = "missing"
    """The document or its producer is not on disk."""


class MeasurementSource(PolarisBaseModel):
    """One committed measurement document and how it is produced."""

    document: str = Field(description="Repository-relative path to the measurement document.")
    producer: str = Field(
        description="Repository-relative path to the entry point whose import closure is "
        "fingerprinted. A script for generated reports; the module itself where a "
        "document reports on one module's behaviour."
    )
    regeneration: str = Field(
        description="The exact command that regenerates the document, quoted in the "
        "gate's failure message so a reader is told what to run rather than left to "
        "reconstruct it."
    )
    requires_experience_cache: bool = Field(
        default=False,
        description="Does regeneration need the local experience cache "
        "(`docs/RUNBOOK_experience_data_acquisition.md`)? Cache-backed documents "
        "cannot be regenerated in CI or in a fresh container, so their stamps are "
        "expected to be `asserted` rather than `regenerated`.",
    )
    note: str = Field(
        default="",
        description="Anything a reader needs to interpret this row that the fields "
        "above do not carry.",
    )


MANIFEST: tuple[MeasurementSource, ...] = (
    MeasurementSource(
        document="docs/MEASUREMENT_unconditional_coverage.md",
        producer="scripts/unconditional_coverage_study.py",
        regeneration=(
            "uv run python scripts/unconditional_coverage_study.py "
            "-o /tmp/unconditional.json "
            "--markdown docs/MEASUREMENT_unconditional_coverage.md"
        ),
        note=(
            "The document ADR-203 found stale. ~20 minutes at the default 200 "
            "replicates, which is why it is stamped rather than re-run per commit."
        ),
    ),
    MeasurementSource(
        document="docs/MEASUREMENT_experience_gam_ilec.md",
        producer="scripts/experience_diligence.py",
        regeneration=(
            "TWO STEPS, and the first must NOT target this file. Regenerate the raw "
            "harness output (see docs/measurements/README.md for the exact flags): "
            "`--source ilec --year-df 3`, `--source ilec --year-df 3 --duration-bands`, "
            "and `--source ilec --year-df 2 --year-degree 2 --duration-bands`, each "
            "written into docs/measurements/. THEN check whether this document's "
            "written reading still matches those numbers, and revise it if not."
        ),
        requires_experience_cache=True,
        note=(
            "SOA-ILEC extract; not in the repository. Expect an `asserted` stamp. "
            "**This file is a written reading, not harness output** — the generated "
            "artifacts are docs/measurements/experience_gam_ilec*.{json,md}, and "
            "docs/measurements/README.md is explicit that those are overwritten by a "
            "re-run while these analyses are not. Pointing a regeneration command at "
            "this path would replace a hand-written analysis with raw output."
        ),
    ),
    MeasurementSource(
        document="docs/MEASUREMENT_experience_gam_hmd.md",
        producer="scripts/experience_diligence.py",
        regeneration=(
            "TWO STEPS, and the first must NOT target this file. Regenerate the raw "
            "harness output (see docs/measurements/README.md): "
            "`--source hmd --country USA --min-year 1990 --max-year 2019` and "
            "`--source hmd --country GBRTENW --min-year 1990 --max-year 2019`, each "
            "written into docs/measurements/. THEN check whether this document's "
            "written reading still matches those numbers, and revise it if not."
        ),
        requires_experience_cache=True,
        note=(
            "HMD extract; not in the repository. Expect an `asserted` stamp. **This "
            "file is a written reading, not harness output** — see the ILEC entry."
        ),
    ),
    MeasurementSource(
        document="docs/MEASUREMENT_gam_ramp_mechanism.md",
        producer="src/polaris_re/analytics/experience_gam.py",
        regeneration="see the document's own header — it reports on this module's behaviour",
        note=(
            "Not script-generated, so the producer is the module the document "
            "describes. ADR-203's audit flagged it as older than "
            "`experience_gam.py`'s 2026-08-09 change (a behaviour-preserving "
            "extraction of the band layer), unverified either way."
        ),
    ),
    MeasurementSource(
        document="docs/MEASUREMENT_engine_recursion_prework.md",
        producer="src/polaris_re/analytics/perf_harness.py",
        regeneration="see the document's own header",
        note="ADR-203's audit flagged it as older than `products/dispatch.py`.",
    ),
    MeasurementSource(
        document="docs/MEASUREMENT_portfolio_parallel_macbook_air.md",
        producer="src/polaris_re/analytics/portfolio.py",
        regeneration="see the document's own header",
        note=(
            "Timings measured on specific hardware named in the title, so a "
            "regeneration here would not reproduce them by design. The stamp still "
            "answers the useful question: has the measured code moved?"
        ),
    ),
)
"""Every committed measurement document, and what produces it.

Declared here rather than parsed out of each document's prose, because the prose is
exactly what cannot be trusted to stay accurate — that is the failure this module
exists to catch.
"""


class Stamp(PolarisBaseModel):
    """A parsed provenance stamp."""

    fingerprint: str = Field(description="SHA-256 of the producer's import closure.")
    generated: str = Field(description="ISO date the stamp was written.")
    producer: str = Field(description="The entry point the fingerprint was taken over.")
    method: StampMethod = Field(
        description="How the document was verified. See :class:`StampMethod`."
    )
    note: str = Field(default="", description="Required for `asserted`; free text otherwise.")
    head: str = Field(
        default="",
        description="Short git HEAD sha at stamping time. **Context, not identity** — "
        "the fingerprint is what `check` compares, and it is content-addressed, so a "
        "stamp stays valid across commits that do not touch the closure. This exists so "
        "a reader auditing an `asserted` stamp — one vouching for work done in a session "
        "this checkout cannot see — can locate what the operator was standing on. Empty "
        "outside a git checkout, and on stamps written before PR #208's review, which "
        "found the sha being computed and then discarded.",
    )


class Finding(PolarisBaseModel):
    """One document's verdict."""

    document: str = Field(description="Repository-relative path.")
    status: StampStatus = Field(description="See :class:`StampStatus`.")
    detail: str = Field(description="Human-readable explanation, including what to run.")
    stamp: Stamp | None = Field(default=None, description="The stamp found, if any.")


def dependency_closure(entry: Path, repo_root: Path) -> tuple[Path, ...]:
    """Every ``polaris_re`` module the entry point transitively imports, plus itself.

    Absolute imports only. This repository uses no relative imports inside
    ``polaris_re`` (checked), and a walker that silently skipped them would
    under-report the closure — which for a staleness gate means a false pass, the
    one failure mode that matters here. If relative imports are ever introduced,
    :func:`dependency_closure` must be extended before they land.

    Args:
        entry: the producer's path.
        repo_root: repository root, used to resolve ``polaris_re.x.y`` to a file.

    Returns:
        Sorted, de-duplicated paths. Sorted so the fingerprint does not depend on
        walk order.
    """
    src = repo_root / "src"
    seen: set[Path] = set()
    queue = [entry.resolve()]
    while queue:
        current = queue.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        for dotted in _polaris_imports(current):
            for candidate in _candidates(src, dotted):
                if candidate.is_file() and candidate.resolve() not in seen:
                    queue.append(candidate.resolve())
    return tuple(sorted(seen))


def _candidates(src: Path, dotted: str) -> tuple[Path, ...]:
    """The two files a dotted name can resolve to: a module, or a package.

    **The package form is not an edge case, it is a live idiom** —
    ``from polaris_re.core import ReserveBasis`` re-exports through
    ``core/__init__.py``, and this repository already does it in four test modules.
    Resolving only ``core/ReserveBasis.py`` (absent) and ``core.py`` (absent) drops
    the defining module and everything below it: measured on this checkout, a
    producer importing that way omitted ``core/reserve_basis.py`` from its closure
    entirely.

    That is a **false pass** — the document would be stamped, look vouched-for, and
    never detect drift in the module it actually depends on — which is the one
    failure mode ADR-204 decision 1 singles out as mattering. Found by PR #208's
    review, not by the original walker's tests.
    """
    stem = dotted.replace(".", "/")
    return (src / (stem + ".py"), src / stem / "__init__.py")


def _polaris_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_polaris(node.module):
            found.add(node.module)
            # `from polaris_re.pkg import module` — the imported name may itself be
            # a module rather than an attribute, and missing it would under-report.
            for alias in node.names:
                found.add(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if _is_polaris(alias.name))
    return found


def _is_polaris(dotted: str) -> bool:
    return dotted == "polaris_re" or dotted.startswith("polaris_re.")


def closure_fingerprint(paths: tuple[Path, ...], repo_root: Path) -> str:
    """SHA-256 over ``(relative path, file contents)`` for every path, in order.

    The path is hashed alongside the contents so that renaming a module changes the
    fingerprint. A rename can change behaviour through import resolution even when
    every byte of every file is preserved.
    """
    digest = hashlib.sha256()
    for path in paths:
        try:
            relative = path.relative_to(repo_root)
        except ValueError:
            relative = path
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def format_stamp(stamp: Stamp) -> str:
    """Render a stamp as the HTML comment block that lives in the document."""
    lines = [
        _STAMP_OPEN,
        f"fingerprint: {stamp.fingerprint}",
        f"generated: {stamp.generated}",
        f"producer: {stamp.producer}",
        f"method: {stamp.method.value}",
    ]
    if stamp.head:
        lines.append(f"head: {stamp.head}")
    if stamp.note:
        # Single line: the parser is line-oriented and a wrapped note would be
        # silently truncated, which is worse than a long line.
        lines.append(f"note: {' '.join(stamp.note.split())}")
    lines.append(_STAMP_CLOSE)
    return "\n".join(lines) + "\n"


def parse_stamp(text: str) -> Stamp | None:
    """Read the stamp out of a document, or ``None`` if it carries no stamp.

    Raises:
        PolarisValidationError: if a stamp block is present but malformed. A
            corrupt stamp is not the same as no stamp — treating it as absent
            would downgrade a hard failure to a warning, so it raises.
    """
    match = _STAMP_PATTERN.search(text)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise PolarisValidationError(
                f"measurement stamp: line {line!r} is not `key: value`. A malformed "
                "stamp is reported rather than ignored, because ignoring it would "
                "turn a drift failure into a silent pass."
            )
        fields[key.strip()] = value.strip()
    missing = {"fingerprint", "generated", "producer", "method"} - set(fields)
    if missing:
        raise PolarisValidationError(
            f"measurement stamp is missing required field(s): {sorted(missing)}."
        )
    return Stamp(
        fingerprint=fields["fingerprint"],
        generated=fields["generated"],
        producer=fields["producer"],
        method=StampMethod(fields["method"]),
        note=fields.get("note", ""),
        head=fields.get("head", ""),
    )


def strip_stamp(text: str) -> str:
    """Remove any stamp block, so stamping is idempotent.

    Necessary because several of these documents are *fully rewritten* by their
    producer on every run. Stamping is therefore a post-step, and re-stamping must
    not accumulate blocks.
    """
    return _STAMP_PATTERN.sub("", text)


def git_head(repo_root: Path) -> str:
    """Short HEAD sha, or ``"unknown"`` outside a git checkout."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def check_manifest(
    repo_root: Path, manifest: tuple[MeasurementSource, ...] = MANIFEST
) -> list[Finding]:
    """Verify every manifest entry's stamp against its recomputed closure.

    Returns findings; the caller decides what is fatal.
    :data:`StampStatus.DRIFTED` is the only status the CI gate fails on — see
    `scripts/measurement_stamp.py` for why an unstamped document warns instead.
    """
    findings: list[Finding] = []
    for source in manifest:
        document = repo_root / source.document
        producer = repo_root / source.producer
        if not document.is_file() or not producer.is_file():
            findings.append(
                Finding(
                    document=source.document,
                    status=StampStatus.MISSING,
                    detail=(
                        f"document exists: {document.is_file()}; "
                        f"producer {source.producer} exists: {producer.is_file()}. "
                        "A manifest entry naming a path that is not there is a "
                        "manifest bug, not a measurement problem."
                    ),
                )
            )
            continue

        stamp = parse_stamp(document.read_text(encoding="utf-8"))
        current = closure_fingerprint(dependency_closure(producer, repo_root), repo_root)
        if stamp is None:
            findings.append(
                Finding(
                    document=source.document,
                    status=StampStatus.UNSTAMPED,
                    detail=(
                        "no provenance stamp. Its figures may or may not reproduce "
                        "against the code that is here now — nobody has said. To "
                        f"stamp it: {source.regeneration}"
                    ),
                )
            )
        elif stamp.fingerprint != current:
            findings.append(
                Finding(
                    document=source.document,
                    status=StampStatus.DRIFTED,
                    detail=(
                        f"stamped {stamp.generated} against closure "
                        f"{stamp.fingerprint[:12]}, which is now {current[:12]}. The "
                        f"code that produced this document has changed. Re-run it "
                        f"({source.regeneration}) and re-stamp, or record why the "
                        "change does not touch the measured path."
                    ),
                    stamp=stamp,
                )
            )
        else:
            findings.append(
                Finding(
                    document=source.document,
                    status=StampStatus.OK,
                    detail=f"closure {current[:12]} unchanged since {stamp.generated}.",
                    stamp=stamp,
                )
            )
    return findings

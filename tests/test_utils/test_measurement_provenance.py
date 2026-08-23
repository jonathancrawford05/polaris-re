"""Tests for measurement provenance stamps.

R-free and fast. The centre of gravity is **that the gate bites**: a staleness
gate which cannot report drift is worse than no gate, because it converts "nobody
checked" into "CI is green". ADR-203 is the whole reason this module exists, and
the condition it found — a stamped document whose producer changed underneath it
— is fabricated here and asserted to fail.

The closure tests build a synthetic `polaris_re` tree in `tmp_path` rather than
walking the real one. The real tree changes with every commit, which would make
these tests measure the repository rather than the walker.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.utils.measurement_provenance import (
    MANIFEST,
    MeasurementSource,
    Stamp,
    StampMethod,
    StampStatus,
    check_manifest,
    closure_fingerprint,
    dependency_closure,
    format_stamp,
    parse_stamp,
    strip_stamp,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/measurement_stamp.py"

_FULL_CHECKOUT = (REPO_ROOT / "docs" / "DECISIONS.md").is_file()
"""Is the whole repository present, or only the subset the Docker image carries?

The image copies `scripts/`, `tests/` and `src/` in full but only a *subset* of
`docs/` — `docs/measurements/`, `DATA_LICENSING.md`, and two of the six
`MEASUREMENT_*.md` files (Dockerfile:81-86). The two tests below assert things
about the repository's structure, so in the image they are not weaker, they are
meaningless. `DECISIONS.md` is the sentinel because it is large, permanent, and
deliberately not shipped in the runtime image.

Found by CI, not by reasoning: the first version of this file had no such guard
and turned the Docker job red.
"""

_PARTIAL_CHECKOUT_REASON = (
    "needs a full source checkout; the Docker image copies only part of docs/, so "
    "this asserts repository structure that is legitimately absent there"
)


def _tree(root: Path) -> Path:
    """A synthetic repo: producer -> alpha -> beta, plus an unimported gamma."""
    package = root / "src" / "polaris_re" / "analytics"
    package.mkdir(parents=True)
    (root / "src" / "polaris_re" / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "beta.py").write_text("VALUE = 1\n")
    (package / "alpha.py").write_text("from polaris_re.analytics.beta import VALUE\n")
    (package / "gamma.py").write_text("VALUE = 99\n")
    scripts = root / "scripts"
    scripts.mkdir()
    producer = scripts / "producer.py"
    producer.write_text("from polaris_re.analytics.alpha import VALUE\nprint(VALUE)\n")
    return producer


# --------------------------------------------------------------------------- #
# The closure
# --------------------------------------------------------------------------- #


def test_the_closure_is_transitive_and_excludes_what_is_not_imported(tmp_path: Path) -> None:
    """Two hops deep, and `gamma` — present but unimported — must not appear.

    Both halves matter. Missing a transitive dependency is a **false pass**: the
    fitter could change and the gate stay green. Including an unimported module is a
    false failure, which trains people to ignore the gate.
    """
    producer = _tree(tmp_path)
    names = {p.name for p in dependency_closure(producer, tmp_path)}
    assert names == {"producer.py", "alpha.py", "beta.py"}


def test_a_from_package_import_module_form_is_followed(tmp_path: Path) -> None:
    """`from polaris_re.analytics import beta` reaches `beta`, not just `analytics`.

    Written because the naive walker records only `node.module`, which for this very
    common form is the *package*, not the module actually depended on — and the
    package `__init__` may import nothing. That is a silent under-report, i.e. a
    false pass.
    """
    producer = _tree(tmp_path)
    producer.write_text("from polaris_re.analytics import beta\n")
    names = {p.name for p in dependency_closure(producer, tmp_path)}
    assert "beta.py" in names


def test_the_fingerprint_moves_when_a_transitive_dependency_changes(tmp_path: Path) -> None:
    """**The ADR-203 condition, in miniature.**

    `beta` is two hops from the producer and is never named by the document. Editing
    it is exactly what `ce0b9f1` did to the coverage study: a correct change to code
    the measurement quietly depended on.
    """
    producer = _tree(tmp_path)
    before = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)

    (tmp_path / "src/polaris_re/analytics/beta.py").write_text("VALUE = 2\n")
    after = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)

    assert before != after


def test_the_fingerprint_ignores_a_module_outside_the_closure(tmp_path: Path) -> None:
    """Editing `gamma` must not move it, or every commit invalidates every stamp."""
    producer = _tree(tmp_path)
    before = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)
    (tmp_path / "src/polaris_re/analytics/gamma.py").write_text("VALUE = 100\n")
    assert closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path) == before


def test_the_fingerprint_moves_on_a_rename_even_with_identical_bytes(tmp_path: Path) -> None:
    """Path is hashed alongside content.

    A rename can change behaviour through import resolution while preserving every
    byte, so hashing contents alone would miss it.
    """
    producer = _tree(tmp_path)
    before = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)

    package = tmp_path / "src/polaris_re/analytics"
    (package / "beta.py").rename(package / "delta.py")
    (package / "alpha.py").write_text("from polaris_re.analytics.delta import VALUE\n")
    after = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)

    assert before != after


def test_the_fingerprint_is_stable_across_repeated_calls(tmp_path: Path) -> None:
    """Sorted closure, so walk order cannot leak into the hash (ADR-074)."""
    producer = _tree(tmp_path)
    first = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)
    second = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)
    assert first == second


# --------------------------------------------------------------------------- #
# The stamp block
# --------------------------------------------------------------------------- #


def _stamp(fingerprint: str = "abc123", note: str = "") -> Stamp:
    return Stamp(
        fingerprint=fingerprint,
        generated="2026-08-23",
        producer="scripts/producer.py",
        method=StampMethod.REGENERATED,
        note=note,
    )


def test_a_stamp_round_trips(tmp_path: Path) -> None:
    parsed = parse_stamp("# Report\n\nbody\n\n" + format_stamp(_stamp(note="hello there")))
    assert parsed is not None
    assert parsed.fingerprint == "abc123"
    assert parsed.method is StampMethod.REGENERATED
    assert parsed.note == "hello there"


def test_an_unstamped_document_parses_as_none() -> None:
    assert parse_stamp("# Report\n\nno stamp here\n") is None


def test_a_malformed_stamp_raises_rather_than_reading_as_absent() -> None:
    """**The most dangerous failure this module could have.**

    If a corrupt stamp parsed as `None`, the document would report `unstamped` —
    which this gate deliberately treats as a warning — and a real drift would pass
    the build silently. So a present-but-broken stamp raises.
    """
    broken = "# Report\n\n<!-- measurement-provenance\nthis line has no colon\n-->\n"
    with pytest.raises(PolarisValidationError, match="not `key: value`"):
        parse_stamp(broken)

    incomplete = "# Report\n\n<!-- measurement-provenance\nfingerprint: abc\n-->\n"
    with pytest.raises(PolarisValidationError, match="missing required field"):
        parse_stamp(incomplete)


def test_stamping_is_idempotent_and_does_not_accumulate_blocks() -> None:
    """Several of these documents are fully rewritten by their producer.

    Stamping is therefore a post-step that runs repeatedly, and a stripper that left
    the old block behind would grow one stamp per run — with the *stale* one first,
    which is what a line-oriented parser would then read.
    """
    body = "# Report\n\nbody\n"
    once = strip_stamp(body + format_stamp(_stamp("aaa"))) + format_stamp(_stamp("bbb"))
    twice = strip_stamp(once) + format_stamp(_stamp("ccc"))

    assert twice.count("measurement-provenance") == 1
    parsed = parse_stamp(twice)
    assert parsed is not None and parsed.fingerprint == "ccc"


def test_a_multi_line_note_is_flattened_rather_than_truncated() -> None:
    """The parser is line-oriented, so a wrapped note would lose everything after
    the first newline. Flattening is ugly; silently dropping half an operator's
    justification for an `asserted` stamp is worse."""
    parsed = parse_stamp(format_stamp(_stamp(note="line one\nline two\n  line three")))
    assert parsed is not None
    assert parsed.note == "line one line two line three"


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


def test_the_gate_reports_drift_when_a_dependency_moves(tmp_path: Path) -> None:
    """**The bite test.** Stamp a document, change code two hops away, expect DRIFTED."""
    producer = _tree(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    document = docs / "MEASUREMENT_synthetic.md"
    fingerprint = closure_fingerprint(dependency_closure(producer, tmp_path), tmp_path)
    document.write_text("# Synthetic\n\n" + format_stamp(_stamp(fingerprint)))

    manifest = (
        MeasurementSource(
            document="docs/MEASUREMENT_synthetic.md",
            producer="scripts/producer.py",
            regeneration="uv run python scripts/producer.py",
        ),
    )

    assert check_manifest(tmp_path, manifest)[0].status is StampStatus.OK

    (tmp_path / "src/polaris_re/analytics/beta.py").write_text("VALUE = 2\n")
    finding = check_manifest(tmp_path, manifest)[0]
    assert finding.status is StampStatus.DRIFTED
    # The failure has to tell the reader what to run, or it is a puzzle not a gate.
    assert "uv run python scripts/producer.py" in finding.detail


def test_the_gate_reports_a_manifest_entry_pointing_at_nothing(tmp_path: Path) -> None:
    """A MISSING row is a manifest bug and must not masquerade as `unstamped`."""
    _tree(tmp_path)
    manifest = (
        MeasurementSource(
            document="docs/does_not_exist.md",
            producer="scripts/producer.py",
            regeneration="x",
        ),
    )
    assert check_manifest(tmp_path, manifest)[0].status is StampStatus.MISSING


@pytest.mark.skipif(not _FULL_CHECKOUT, reason=_PARTIAL_CHECKOUT_REASON)
def test_every_manifest_entry_points_at_real_paths() -> None:
    """The manifest describes this repository, so it can be checked against it.

    Guards the ordinary decay: a document renamed, a script moved, and a manifest
    row left behind that quietly stops checking anything.

    **This is also the assertion that catches a broken manifest row at all.**
    `check` reports a missing path as `MISSING` and does *not* fail the build,
    deliberately — the Docker image is a legitimately partial checkout and a gate
    that failed there would be failing on packaging rather than on provenance. So
    the manifest-integrity guarantee lives here, in a test that runs where the
    whole repository is present, rather than in the gate.
    """
    for source in MANIFEST:
        assert (REPO_ROOT / source.document).is_file(), f"missing document: {source.document}"
        assert (REPO_ROOT / source.producer).is_file(), f"missing producer: {source.producer}"


@pytest.mark.skipif(not _FULL_CHECKOUT, reason=_PARTIAL_CHECKOUT_REASON)
def test_the_manifest_covers_every_measurement_document_on_disk() -> None:
    """A measurement document absent from the manifest is never checked at all.

    The silent-hole case: adding `docs/MEASUREMENT_new_thing.md` without a manifest
    row leaves it outside the gate forever, and nothing else would ever say so.

    Skipped on a partial checkout for a subtler reason than its sibling: there it
    would *pass*, vacuously. The image carries two of the six documents, so
    `on_disk - declared` is trivially empty and the test would report success
    while checking nothing. A vacuous pass is worse than a skip, because only one
    of the two is visible in the output.
    """
    on_disk = {f"docs/{p.name}" for p in (REPO_ROOT / "docs").glob("MEASUREMENT_*.md")}
    declared = {source.document for source in MANIFEST}
    assert on_disk - declared == set(), (
        "measurement documents exist that the manifest does not declare, so nothing "
        "checks them: add them to MANIFEST in measurement_provenance.py"
    )


# --------------------------------------------------------------------------- #
# The CLI's refusals
# --------------------------------------------------------------------------- #


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_asserting_without_a_note_is_refused() -> None:
    """An asserted stamp is one person's word about work done somewhere this
    checkout cannot see. Without the note a reader cannot weigh it, so the tool
    will not write one."""
    result = _run("stamp", "docs/MEASUREMENT_experience_gam_hmd.md", "--assert")
    assert result.returncode == 2
    assert "--assert requires --note" in result.stderr


def test_an_empty_note_is_refused_like_a_missing_one() -> None:
    """Whitespace is not a justification."""
    result = _run("stamp", "docs/MEASUREMENT_experience_gam_hmd.md", "--assert", "--note", "   ")
    assert result.returncode == 2


def test_running_a_cache_backed_producer_is_refused_with_the_alternative() -> None:
    """`--run` on a cache-backed document cannot work here, and the refusal has to
    name the route that does — otherwise the operator's next move is to guess."""
    result = _run("stamp", "docs/MEASUREMENT_experience_gam_hmd.md", "--run")
    assert result.returncode == 2
    assert "--assert" in result.stderr


def test_stamping_a_document_outside_the_manifest_is_refused() -> None:
    """Otherwise it would be stamped, look vouched-for, and never be checked."""
    result = _run("stamp", "docs/ROADMAP.md", "--assert", "--note", "x")
    assert result.returncode != 0
    assert "not in the manifest" in (result.stdout + result.stderr)


def test_check_passes_on_the_current_repository() -> None:
    """The gate must land green.

    Not a tautology — it is the rollout decision made checkable. Six documents were
    unstamped when this landed and two of them cannot be regenerated here at all; a
    gate that failed the build for those would be switched off within the week, and
    a disabled gate catches nothing. Drift on a *vouched-for* document is the only
    fatal condition, and `test_the_gate_reports_drift_when_a_dependency_moves` is
    what proves that condition still fires.
    """
    assert _run("check").returncode == 0

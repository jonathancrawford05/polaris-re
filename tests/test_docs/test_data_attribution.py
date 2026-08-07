"""Attribution and licensing guards for the committed experience findings.

Every number under ``docs/measurements/`` was computed from somebody else's data —
the Human Mortality Database and the SOA Individual Life Experience Committee —
obtained by the maintainer under their own account and terms acceptance. The
credit for that is prose, and prose does not fail CI on its own, so it is pinned
here: a document that quietly loses its attribution block fails.

The second guard is sharper and is the reason this module exists at all. Until
2026-08-07 the repository asserted things about the HMD and SOA licences —
"keeps you inside both licences", "Why committing these is not a licence
problem" — with **nothing behind them**: no section number, no quotation, no URL
to a terms document anywhere in the tree. ``docs/DATA_LICENSING.md`` §4 now
records that the terms have not been read and why. These tests exist so that
status cannot be upgraded to a settled one by editing a heading; if someone wants
to claim the terms permit this, the claim has to survive deleting the file that
says otherwise, which is a deliberate act rather than a drive-by reword.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSING = REPO_ROOT / "docs" / "DATA_LICENSING.md"

ATTRIBUTION_BEARING = (
    REPO_ROOT / "docs" / "measurements" / "README.md",
    REPO_ROOT / "docs" / "MEASUREMENT_experience_gam_hmd.md",
    REPO_ROOT / "docs" / "MEASUREMENT_experience_gam_ilec.md",
)


def test_licensing_document_exists() -> None:
    assert LICENSING.is_file(), f"missing provenance/licensing record: {LICENSING}"


@pytest.mark.parametrize("path", ATTRIBUTION_BEARING, ids=lambda p: p.name)
def test_document_credits_its_data_source(path: Path) -> None:
    """A findings document must name whose data produced the findings."""
    text = path.read_text()
    hmd = "hmd" in path.name.lower()
    ilec = "ilec" in path.name.lower()
    # The measurements README covers both; the two measurement docs one each.
    if hmd or not (hmd or ilec):
        assert "Human Mortality Database" in text
        assert "mortality.org" in text
    if ilec or not (hmd or ilec):
        assert "Society of Actuaries" in text
        assert "soa.org" in text
    assert "DATA_LICENSING.md" in text, "attribution must point at the full provenance record"


@pytest.mark.parametrize("path", ATTRIBUTION_BEARING, ids=lambda p: p.name)
def test_document_disclaims_endorsement(path: Path) -> None:
    """Neither body reviewed this work, and neither should appear to have."""
    text = path.read_text().lower()
    assert "endorse" in text, f"{path.name} must disclaim endorsement by the data provider"


def test_licensing_record_does_not_claim_the_terms_were_read() -> None:
    """The whole point of the document is that this remains an open question.

    Fails if the "not verified" status is edited away while the section that
    explains the blocker is still standing — i.e. it catches an upgrade of the
    claim, not an honest update. Genuinely reading the terms means rewriting §4,
    which necessarily changes these anchors and is meant to.
    """
    text = LICENSING.read_text()
    assert "NOT read" in text
    assert "have not read them" in text
    # And the three questions a reader has to answer must still be stated.
    for question in ("derived aggregates", "prescribed attribution wording", "non-commercial"):
        assert question in text, f"licensing record no longer poses: {question!r}"


@pytest.mark.skipif(
    not (REPO_ROOT / ".dockerignore").is_file(),
    reason=(
        "build-time inputs; absent inside the image by design. This guard is about "
        "the REPO's build configuration and has nothing to assert from within a "
        "container built from it."
    ),
)
def test_attribution_documents_ship_into_the_docker_image() -> None:
    """The runtime image runs this suite, so what this suite reads must be in it.

    ``docs/`` is excluded wholesale by ``.dockerignore`` bar an explicit allowlist,
    so adding a docs-reading test without extending that list turns the Docker job
    red while every other check passes — which is exactly how it failed on
    2026-08-05 for the measurement reports. Asserted structurally because the
    failure is invisible without a Docker daemon.
    """
    ignore = [
        line.strip()
        for line in (REPO_ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    for path in (LICENSING, *ATTRIBUTION_BEARING):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative.startswith("docs/measurements/"):
            continue  # covered by the !docs/measurements/** allowlist
        assert f"!{relative}" in ignore, f".dockerignore must re-include {relative}"
        assert relative in dockerfile, f"Dockerfile must COPY {relative}"


def test_second_hand_licence_claims_are_not_reintroduced() -> None:
    """The exact heading that asserted a legal conclusion nobody had checked."""
    readme = (REPO_ROOT / "docs" / "measurements" / "README.md").read_text()
    assert "Why committing these is not a licence problem" not in readme

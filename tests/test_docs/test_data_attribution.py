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
to a terms document anywhere in the tree. Both sets have since been read — SOA on
2026-08-07 (§3) and HMD on 2026-08-08 (§4) — and they came out **opposite**: SOA
restrictive with permission as the only route, HMD permissive under CC BY 4.0 with
attribution as the condition.

That asymmetry is what these tests protect. The pressure now runs in two
directions: softening the SOA record into something more comfortable, and rounding
the favourable HMD answer up to "fine" when its attribution condition is not yet
met. Both would be a single-word edit, so the clause text, the two-tier split and
the outstanding DOI are each pinned to a failing assertion.
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


def test_hmd_findings_are_recorded_with_their_two_tier_structure() -> None:
    """HMD was read 2026-08-08 and the answer was favourable — which is exactly when
    a record gets sloppy.

    The load-bearing fact is the **two-tier split**: CC BY 4.0 covers HMD's own
    estimates (derivatives and commercial use permitted), while the input data
    carries the original provider's licence plus a no-commercial-gain restriction.
    Collapsing that into "HMD is CC BY 4.0" would be the natural simplification and
    would be wrong for any future series drawn from the Input Database, so both
    halves are pinned.
    """
    text = LICENSING.read_text()
    assert "CC BY 4.0" in text
    assert "Input data" in text, "the non-CC-BY tier must stay visible"
    assert "used for commercial gain or re-published in any form" in text, (
        "the input-data restriction is quoted, not paraphrased"
    )
    # The provenance determination is what makes the favourable answer apply to us.
    assert "Statistics" in text and "Input Database" in text


def test_the_hmd_attribution_gap_is_not_rounded_to_compliant() -> None:
    """CC BY 4.0's condition IS the attribution, so an incomplete one is the breach.

    The DOI is missing and only the maintainer can supply it. Until then §2a does
    not meet HMD's prescribed form, and this test exists so that shortfall cannot
    quietly become "HMD: fine" — the same failure mode §3e caught on the SOA side.
    Closing it means pasting the DOI in, which removes the marker and fails here.
    """
    text = LICENSING.read_text()
    assert "[TO SUPPLY — see §4d]" in text, (
        "either the DOI has been supplied (update this test) or the marker was "
        "dropped without supplying it (put it back)"
    )
    assert "does not meet the licence's own stated form" in text


def test_soa_terms_are_recorded_with_their_actual_clause_text() -> None:
    """Paraphrase is what this document exists to replace, so quote or fail.

    Each string below is clause text from the SOA Website Terms of Use. If a
    future edit softens the record into a summary, the quotes go and this fails —
    which is the same guard the notebook applies to the measurement prose.
    """
    text = LICENSING.read_text()
    for clause in (
        "personal or other non-commercial, educational purposes",
        "for any public or commercial purpose",
        "any derivative work",
        "customerservice@soa.org",
    ):
        assert clause in text, f"SOA clause text no longer recorded: {clause!r}"


def test_the_public_hook_is_not_reframed_as_a_future_commercial_risk() -> None:
    """The restriction binds a public repository today, not on some later trigger.

    The comfortable reading — "we are educational and non-commercial, so this
    becomes an issue only if the project commercialises" — misreads a clause that
    says public *or* commercial. It is also the reading a caveat naturally drifts
    toward, so it is pinned against.
    """
    text = LICENSING.read_text()
    assert 'binding hook is "public", not "commercial"' in text
    assert "CLAUDE.md" in text, "the stated commercial vision must be reconciled, not ignored"


def test_the_position_taken_carries_its_change_triggers() -> None:
    """A risk position without triggers is a shrug with a date on it."""
    text = LICENSING.read_text()
    for trigger in ("A second contributor", "90 days"):
        assert trigger in text, f"position no longer names the trigger: {trigger!r}"


def test_the_permission_request_carries_real_dates() -> None:
    """The 90-day trigger is only actionable if it resolves to a calendar date.

    "90 days from sending" is a sentiment; a date is a deadline. The request was
    sent 2026-08-08 and drew an automated high-volume acknowledgement, which is
    the outcome most likely to quietly become a permanent state — so the dates it
    keys are pinned here rather than left in prose.
    """
    text = LICENSING.read_text()
    for anchor in ("2026-08-08", "2026-11-06"):
        assert anchor in text, f"licensing record no longer carries the date {anchor!r}"
    assert "Not a substantive response" in text, (
        "an auto-acknowledgement must stay marked as granting nothing — it is the "
        "easiest thing in this file to misread as progress"
    )


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

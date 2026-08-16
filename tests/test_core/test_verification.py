"""Verification provenance (ADR-193).

The rule these tests hold in place: a comparison is parity evidence only when two
independent producers computed the compared quantity. The cases below are the
three ways that rule gets broken in practice — claiming independence while naming
one producer, asserting a parity claim over echoed evidence, and rendering a
harness table under a parity headline.
"""

import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
    evidence_headline,
    evidence_markdown,
    require_parity_evidence,
)


def _independent(quantity: str = "rank") -> ComparedQuantity:
    return ComparedQuantity(
        quantity=quantity,
        left_producer="numpy.linalg.matrix_rank",
        right_producer="mgcv m$paraPen$rank",
        provenance=ComparisonProvenance.INDEPENDENT,
    )


def _echo(quantity: str = "design_X") -> ComparedQuantity:
    return ComparedQuantity(
        quantity=quantity,
        left_producer="Python fitted design",
        right_producer="mgcv lpmatrix echo of the supplied X",
        provenance=ComparisonProvenance.ECHO,
    )


def _transport(quantity: str = "penalty_S") -> ComparedQuantity:
    return ComparedQuantity(
        quantity=quantity,
        left_producer="extract_smooth_terms (read from the R payload)",
        right_producer="mgcv smoothCon(...)$S",
        provenance=ComparisonProvenance.TRANSPORT,
    )


# --- the taxonomy ---------------------------------------------------------------------


def test_only_independent_provenance_is_parity_evidence() -> None:
    assert ComparisonProvenance.INDEPENDENT.is_parity_evidence
    assert not ComparisonProvenance.ECHO.is_parity_evidence
    assert not ComparisonProvenance.TRANSPORT.is_parity_evidence


# --- ComparedQuantity's own guards ----------------------------------------------------


def test_a_quantity_cannot_claim_independence_from_a_single_producer() -> None:
    """The exact error ADR-193 exists to catch, refused where the author is."""
    with pytest.raises(PolarisValidationError, match="same producer on both sides"):
        ComparedQuantity(
            quantity="design_X",
            left_producer="gam_term_extract.R smoothCon()",
            right_producer="gam_term_extract.R smoothCon()",
            provenance=ComparisonProvenance.INDEPENDENT,
        )


def test_one_producer_compared_against_itself_is_allowed_when_declared_transport() -> None:
    """The same pair is fine — it is the *claim* that has to be honest."""
    quantity = ComparedQuantity(
        quantity="design_X",
        left_producer="gam_term_extract.R smoothCon()",
        right_producer="gam_term_extract.R smoothCon()",
        provenance=ComparisonProvenance.TRANSPORT,
    )
    assert not quantity.provenance.is_parity_evidence


@pytest.mark.parametrize(
    ("left", "right"),
    [("", "mgcv"), ("numpy", "   "), ("", "")],
)
def test_a_quantity_must_name_both_producers(left: str, right: str) -> None:
    with pytest.raises(PolarisValidationError, match="must name both producers"):
        ComparedQuantity(
            quantity="design_X",
            left_producer=left,
            right_producer=right,
            provenance=ComparisonProvenance.ECHO,
        )


def test_a_quantity_needs_a_name() -> None:
    with pytest.raises(PolarisValidationError, match="non-empty quantity name"):
        ComparedQuantity(
            quantity="  ",
            left_producer="numpy",
            right_producer="mgcv",
            provenance=ComparisonProvenance.ECHO,
        )


# --- VerificationClaim ----------------------------------------------------------------


def test_a_claim_splits_parity_from_harness_quantities() -> None:
    claim = VerificationClaim(
        claim="Stage A, raw path.",
        quantities=(_echo("design_X"), _echo("penalty_S"), _independent("rank")),
    )
    assert [q.quantity for q in claim.parity_quantities] == ["rank"]
    assert [q.quantity for q in claim.harness_quantities] == ["design_X", "penalty_S"]


def test_a_claim_is_a_parity_claim_only_when_every_quantity_is_independent() -> None:
    mixed = VerificationClaim(
        claim="One independent column among echoes.",
        quantities=(_echo(), _independent()),
    )
    whole = VerificationClaim(
        claim="Both sides built from the same recipe.",
        quantities=(_independent("design_X"), _independent("rank")),
    )
    assert not mixed.is_parity_claim
    assert whole.is_parity_claim


def test_a_claim_refuses_a_duplicated_quantity() -> None:
    with pytest.raises(PolarisValidationError, match="more than"):
        VerificationClaim(
            claim="Same quantity declared twice, with two different provenances.",
            quantities=(_echo("design_X"), _independent("design_X")),
        )


def test_a_claim_refuses_an_empty_quantity_list() -> None:
    with pytest.raises(PolarisValidationError, match="declares no compared quantities"):
        VerificationClaim(claim="Nothing compared.", quantities=())


def test_a_claim_needs_a_claim_sentence() -> None:
    with pytest.raises(PolarisValidationError, match="non-empty claim sentence"):
        VerificationClaim(claim="   ", quantities=(_independent(),))


# --- require_parity_evidence ----------------------------------------------------------


def test_require_parity_evidence_passes_independent_quantities() -> None:
    quantities = (_independent("design_X"), _independent("rank"))
    assert require_parity_evidence(quantities, claim="Python cr basis matches mgcv's") == quantities


def test_require_parity_evidence_refuses_echoed_evidence() -> None:
    """A gate that says 'parity' cannot be satisfied by a no-tampering check."""
    with pytest.raises(PolarisValidationError) as excinfo:
        require_parity_evidence((_independent("rank"), _echo("design_X")), claim="Stage A exact")
    message = str(excinfo.value)
    assert "'design_X' is ECHO" in message
    assert "rank" not in message.split("produced:")[1]


def test_require_parity_evidence_refuses_transported_evidence() -> None:
    with pytest.raises(PolarisValidationError, match="is TRANSPORT"):
        require_parity_evidence((_transport(),), claim="mgcv-native Stage A exact")


def test_require_parity_evidence_refuses_an_empty_claim() -> None:
    with pytest.raises(PolarisValidationError, match="cites no quantities"):
        require_parity_evidence((), claim="Stage A exact")


# --- the rendered headline, which is what actually travels ----------------------------


def test_headline_of_a_pure_harness_claim_says_not_parity() -> None:
    claim = VerificationClaim(
        claim="Slice 1b: one producer, parsed by the other.",
        quantities=(_transport("design_X"), _transport("penalty_S")),
    )
    headline = evidence_headline(claim)
    assert "NOT parity" in headline
    assert "`design_X`" in headline


def test_headline_of_a_mixed_claim_names_the_parity_column() -> None:
    claim = VerificationClaim(
        claim="Slice 1: echoed design, independently computed rank.",
        quantities=(_echo("design_X"), _independent("rank")),
    )
    headline = evidence_headline(claim)
    assert "NOT basis parity" in headline
    assert "Parity evidence: `rank`" in headline


def test_headline_of_a_full_parity_claim_says_parity() -> None:
    claim = VerificationClaim(
        claim="Slice 2: two independent bases from one recipe.",
        quantities=(_independent("design_X"), _independent("penalty_S")),
    )
    headline = evidence_headline(claim)
    assert headline.startswith("**Parity comparison**")
    assert "NOT" not in headline


def test_evidence_markdown_carries_the_headline_claim_and_every_producer() -> None:
    claim = VerificationClaim(
        claim="Stage A, raw path.",
        quantities=(_echo("design_X"), _independent("rank")),
    )
    rendered = evidence_markdown(claim)
    assert evidence_headline(claim) in rendered
    assert "*Claim:* Stage A, raw path." in rendered
    assert (
        "| `design_X` | Python fitted design | mgcv lpmatrix echo of the supplied X | ECHO | no |"
        in rendered
    )
    assert (
        "| `rank` | numpy.linalg.matrix_rank | mgcv m$paraPen$rank | INDEPENDENT | yes |"
        in rendered
    )
    # One header row, one separator, one row per quantity — a table a reader can
    # scan without the surrounding prose.
    assert len(rendered.splitlines()) == 8


def test_evidence_markdown_is_deterministic() -> None:
    """No clock, no set iteration — safe to commit and to diff across CI runs."""
    claim = VerificationClaim(
        claim="Stage A, raw path.",
        quantities=(_echo("design_X"), _echo("penalty_S"), _independent("rank")),
    )
    assert evidence_markdown(claim) == evidence_markdown(claim)

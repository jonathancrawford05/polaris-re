"""
Verification provenance — what makes a comparison *parity evidence* (ADR-193).

A comparison between this engine and a reference implementation only demonstrates
parity when **two independent producers** computed the compared quantity from the
same recipe. Three relationships all render as a table of near-zero diffs, and
nothing in a rendered table distinguishes them:

- ``INDEPENDENT`` — both sides computed the quantity from the same *recipe*
  (a spec, a set of knots, a formula), neither reading the other's output. This
  is the only relationship that demonstrates parity, and the only one that can
  produce a genuine disagreement.
- ``ECHO`` — one side supplied the quantity and the other returned it. A real
  check (it proves the reference did not silently reparameterise or rescale what
  it was handed) but a *no-tampering* check, not a parity check.
- ``TRANSPORT`` — one side computed the quantity and the other parsed it. Proves
  serialisation and packaging work; cannot disagree on values.

The failure this module exists to prevent is not dishonesty — it is that a prose
caveat sitting next to a table does not survive into the CI job summary, the
ledger's "agrees" column, or a PR description, while a column of ``0.000e+00``
diffs travels everywhere and reads as parity to every downstream reader. So
provenance is declared **in the type**, by the function that produces the
operand, and the headline a report prints is *derived from that declaration*
rather than written by hand.

See ``docs/VERIFICATION_STANDARD.md`` for the project-wide rule, including the
mechanical test (a producer that takes the other side's payload as an input
cannot be an independent producer) and the wording required of acceptance
criteria and conformance-ledger rows.
"""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field, model_validator

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.exceptions import PolarisValidationError

__all__ = [
    "ComparedQuantity",
    "ComparisonProvenance",
    "VerificationClaim",
    "evidence_headline",
    "evidence_markdown",
    "require_parity_evidence",
]


class ComparisonProvenance(StrEnum):
    """How the two operands of a comparison came to exist."""

    INDEPENDENT = "INDEPENDENT"
    ECHO = "ECHO"
    TRANSPORT = "TRANSPORT"

    @property
    def is_parity_evidence(self) -> bool:
        """Only an independent comparison demonstrates parity.

        ``ECHO`` and ``TRANSPORT`` comparisons are harness evidence: worth running
        and worth reporting, but never the basis of a parity claim.
        """
        return self is ComparisonProvenance.INDEPENDENT


class ComparedQuantity(PolarisBaseModel):
    """One compared quantity, and who computed each side of it."""

    quantity: str = Field(
        description="The compared quantity, named as the report column names it "
        "(e.g. 'design_X', 'penalty_S', 'rank')."
    )
    left_producer: str = Field(
        description="What computed the left operand — a function, module or "
        "external call, specific enough that a reader can tell whether it read "
        "the right operand's output."
    )
    right_producer: str = Field(
        description="What computed the right operand, to the same standard."
    )
    provenance: ComparisonProvenance = Field(
        description="The relationship between the two producers. Declared by the "
        "function that produces the operand, never by the report that renders it."
    )

    @model_validator(mode="after")
    def _check_producers(self) -> "ComparedQuantity":
        """Refuse the two ways a provenance declaration is self-evidently wrong.

        A blank producer defeats the whole point (the declaration is what a reader
        audits), and naming the *same* producer on both sides while claiming
        independence is the exact error this module exists to catch — caught at
        construction, where the author is, rather than in review.
        """
        if not self.quantity.strip():
            raise PolarisValidationError("A ComparedQuantity needs a non-empty quantity name.")
        if not self.left_producer.strip() or not self.right_producer.strip():
            raise PolarisValidationError(
                f"ComparedQuantity {self.quantity!r} must name both producers — an "
                "unnamed producer cannot be audited, which is what the declaration is for."
            )
        if (
            self.provenance.is_parity_evidence
            and self.left_producer.strip() == self.right_producer.strip()
        ):
            raise PolarisValidationError(
                f"ComparedQuantity {self.quantity!r} claims INDEPENDENT provenance but "
                f"names the same producer on both sides ({self.left_producer!r}). One "
                "producer compared against itself is TRANSPORT or ECHO, never parity."
            )
        return self


class VerificationClaim(PolarisBaseModel):
    """A comparison's full provenance: the claim, and every quantity behind it.

    The claim sentence is the one required at authoring time (see
    ``docs/VERIFICATION_STANDARD.md``): *"<left> computes <quantity> from
    <recipe>; <right> computes it via <call>; compared on <quantities>."* If that
    sentence cannot be filled in with two distinct computations, the work is a
    harness slice and its quantities carry ``ECHO``/``TRANSPORT`` provenance.
    """

    claim: str = Field(
        description="The parity claim in one sentence — what is compared, and by "
        "which two producers."
    )
    quantities: tuple[ComparedQuantity, ...] = Field(
        description="Every quantity this comparison reports, in the order a report "
        "renders them. Provenance is per-quantity: one comparison may carry an "
        "independently computed column alongside echoed ones."
    )

    @model_validator(mode="after")
    def _check_quantities(self) -> "VerificationClaim":
        if not self.claim.strip():
            raise PolarisValidationError("A VerificationClaim needs a non-empty claim sentence.")
        if not self.quantities:
            raise PolarisValidationError(
                f"VerificationClaim {self.claim!r} declares no compared quantities."
            )
        seen = [q.quantity for q in self.quantities]
        duplicates = sorted({name for name in seen if seen.count(name) > 1})
        if duplicates:
            raise PolarisValidationError(
                f"VerificationClaim {self.claim!r} declares {duplicates} more than "
                "once — one provenance per compared quantity."
            )
        return self

    @property
    def parity_quantities(self) -> tuple[ComparedQuantity, ...]:
        """The quantities that actually demonstrate parity."""
        return tuple(q for q in self.quantities if q.provenance.is_parity_evidence)

    @property
    def harness_quantities(self) -> tuple[ComparedQuantity, ...]:
        """The echoed/transported quantities — real checks, but not parity."""
        return tuple(q for q in self.quantities if not q.provenance.is_parity_evidence)

    @property
    def is_parity_claim(self) -> bool:
        """True only when *every* reported quantity is independently produced.

        Deliberately strict: a comparison with one independent column and three
        echoed ones is a harness check that happens to carry a parity column, and
        a report that calls the whole table "parity" is the mislabelling ADR-193
        is about. Cite the specific column instead, via
        :func:`require_parity_evidence`.
        """
        return bool(self.quantities) and all(
            q.provenance.is_parity_evidence for q in self.quantities
        )


def require_parity_evidence(
    quantities: Iterable[ComparedQuantity], *, claim: str
) -> tuple[ComparedQuantity, ...]:
    """Assert that every named quantity is independently produced.

    Call this wherever a parity claim is *asserted* — an acceptance check, a gate,
    a report that prints the word "parity" — so a harness result cannot silently
    satisfy it.

    Raises:
        PolarisValidationError: naming each quantity that is not independently
            produced, and what produced each side of it.
    """
    ordered = tuple(quantities)
    if not ordered:
        raise PolarisValidationError(
            f"Parity claim {claim!r} cites no quantities — an empty claim cannot be evidence."
        )
    offenders = [q for q in ordered if not q.provenance.is_parity_evidence]
    if offenders:
        detail = "; ".join(
            f"{q.quantity!r} is {q.provenance.value} ({q.left_producer} vs {q.right_producer})"
            for q in offenders
        )
        raise PolarisValidationError(
            f"Parity claim {claim!r} rests on evidence that is not independently "
            f"produced: {detail}. An ECHO or TRANSPORT comparison cannot demonstrate "
            "parity — see docs/VERIFICATION_STANDARD.md."
        )
    return ordered


def evidence_headline(claim: VerificationClaim) -> str:
    """The one-line verdict a report prints *above* its diff table.

    Derived from the declared provenance rather than written by hand, so a table
    of near-zero diffs cannot be titled "parity" unless it is one. This is the
    piece that travels: it is what a reader skimming a CI job summary sees next
    to the zeros.
    """
    parity = ", ".join(f"`{q.quantity}`" for q in claim.parity_quantities)
    harness = ", ".join(f"`{q.quantity}` ({q.provenance.value})" for q in claim.harness_quantities)
    if claim.is_parity_claim:
        return f"**Parity comparison** — independently produced on both sides: {parity}."
    if not parity:
        # What a zero actually proves differs by kind, so say only what holds:
        # a TRANSPORT column structurally cannot disagree, while an ECHO column
        # can (the reference may reparameterise or rescale what it was handed) —
        # which is exactly why a zero there is worth reporting.
        kinds = {q.provenance for q in claim.harness_quantities}
        if kinds == {ComparisonProvenance.TRANSPORT}:
            proves = (
                "These columns cannot disagree on values; a zero proves the harness "
                "serialises and parses correctly."
            )
        elif kinds == {ComparisonProvenance.ECHO}:
            proves = (
                "A zero proves the reference returned what it was handed unchanged — "
                "no reparameterisation or rescaling — not that two sides agree."
            )
        else:
            proves = (
                "A zero proves the harness round-trips its TRANSPORT columns and that "
                "the reference did not alter its ECHO ones — not that two sides agree."
            )
        return (
            "**Harness check — NOT parity.** No column here is independently "
            f"produced: {harness}. {proves}"
        )
    return (
        f"**Harness check with one parity column — NOT basis parity.** Parity "
        f"evidence: {parity}. Harness only: {harness}."
    )


def evidence_markdown(claim: VerificationClaim) -> str:
    """Render the provenance legend that must accompany any published diff table.

    A GitHub-flavoured markdown block: the headline, the claim sentence, and one
    row per compared quantity naming both producers. Deterministic — no clock, no
    ordering surprises — so it is safe in a CI job summary and in committed docs.
    """
    lines = [
        evidence_headline(claim),
        "",
        f"*Claim:* {claim.claim}",
        "",
        "| quantity | left producer | right producer | provenance | parity evidence |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| `{q.quantity}` | {q.left_producer} | {q.right_producer} | "
        f"{q.provenance.value} | {'yes' if q.provenance.is_parity_evidence else 'no'} |"
        for q in claim.quantities
    )
    return "\n".join(lines)
